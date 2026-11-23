"""Actual memory ACKs and native h2 check the receive-credit backend contract.

Directory authority and consumed-buffer witnesses are typed component stimuli.
This does not instantiate the raw receiver or actual descriptor retirement.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'native-vendor'))
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import FlowControlError
from test_tokenizer_mmio import cycles


RESULTS = ('rsp_status', 'rsp_detail', 'rsp_memory_status', 'rsp_connection_error', 'rsp_http2_error',
    'rsp_connection_available', 'rsp_stream_available', 'rsp_connection_pending', 'rsp_stream_pending',
    'rsp_debit_authorized', 'rsp_wire_retired', 'rsp_update_bytes', 'rsp_op', 'rsp_user', 'rsp_stream')


def value(d, name): return int(getattr(d, name).value)


class Memory:
    def __init__(self, d, image):
        self.d = d; self.data = bytearray(image); self.trace = []; self.pending = None
        self.fail_at = -1; self.rng = random.Random(20261121)
    async def run(self):
        d = self.d; held = None
        while True:
            await FallingEdge(d.clk)
            if value(d, 'rst'):
                assert self.pending is None
                d.mem_ready.value = 0; d.mem_rsp_valid.value = 0; held = None
                continue
            d.mem_ready.value = self.pending is None and self.rng.randrange(4) != 0
            if self.pending and self.pending['delay']: self.pending['delay'] -= 1
            valid = self.pending is not None and self.pending['delay'] == 0
            d.mem_rsp_valid.value = int(valid)
            d.mem_rsp_data.value = self.pending['data'] if valid else 0
            d.mem_rsp_status.value = self.pending['status'] if valid else 0
            await RisingEdge(d.clk)
            if valid and value(d, 'mem_rsp_ready'):
                self.pending['entry']['acked'] = True; self.pending = None
            if value(d, 'mem_valid'):
                item = tuple(value(d, n) for n in ('mem_write', 'mem_addr', 'mem_bytes', 'mem_data'))
                if held is not None: assert item == held
                held = item if not value(d, 'mem_ready') else None
                if value(d, 'mem_ready'):
                    write, address, size, data = item
                    assert self.pending is None and size == 8 and address % 8 == 0
                    assert address + 8 <= len(self.data)
                    if write:
                        assert 0x7e0800 <= address < 0x7e08c0 or 0x7e1000 <= address < 0x7e1080
                        self.data[address:address + 8] = (data & ((1 << 64) - 1)).to_bytes(8, 'little')
                    status = 0x75 if len(self.trace) == self.fail_at else 0
                    entry = dict(write=write, address=address, data=data, status=status, acked=False); self.trace.append(entry)
                    self.pending = dict(entry=entry, status=status, data=int.from_bytes(self.data[address:address + 8], 'little'), delay=self.rng.randrange(1, 8))
            else: assert held is None


class Bench:
    def __init__(self, d, memory, image, layout):
        self.d = d; self.m = memory; self.image = image; self.a = layout
        self.wire = []; self.expected_wire = []; self.ready_tx = True; self.commands = 0; self.held_tx = 0
    def set(self, **fields):
        for name, data in fields.items(): getattr(self.d, name).value = data
    async def wait(self, name):
        for _ in range(100000):
            if value(self.d, name): return
            await FallingEdge(self.d.clk)
        raise AssertionError(('Timeout', name, value(self.d, 'state')))
    async def observe_tx(self):
        d = self.d; held = None
        while True:
            await FallingEdge(d.clk); d.m_axis_tx_tready.value = int(self.ready_tx)
            await RisingEdge(d.clk)
            if value(d, 'rst'): assert held is None; continue
            if value(d, 'm_axis_tx_tvalid'):
                item = tuple(value(d, n) for n in ('m_axis_tx_tdata', 'm_axis_tx_tkeep', 'm_axis_tx_tlast', 'm_axis_tx_tuser'))
                if held is not None: assert item == held
                if not value(d, 'm_axis_tx_tready'): held = item; self.held_tx += 1
                else:
                    held = None; data, keep, last, user = item
                    assert keep == 0x1fff and last == 1 and user == 0
                    raw = data.to_bytes(64, 'little')[:13]
                    assert self.expected_wire and raw == self.expected_wire.pop(0), raw.hex()
                    self.client.receive_data(raw); self.wire.append(raw)
            else: assert held is None
    async def command(self, op, stream=0, amount=0, status=0, patch=None):
        d = self.d; a = self.a; slot = (stream - 1) // 2 if stream else 0
        fields = dict(req_op=op, req_authority=1, req_maintenance=int(op == 0), req_user=0,
            req_stream=stream, req_generation=101 + slot if stream else 0,
            req_record_address=a['stream_base'] + slot * 128 if stream else 0, req_amount=amount,
            cfg_context_base=a['context_base'], cfg_context_bytes=a['context_bytes'],
            cfg_rpc_base=a['stream_base'], cfg_rpc_bytes=a['stream_bytes'],
            cfg_receive_connection_base=0x7e0800, cfg_receive_connection_bytes=192,
            cfg_receive_stream_base=0x7e1000, cfg_receive_stream_bytes=128, cfg_work_floor=a['work_floor'])
        fields.update(patch or {}); self.set(**fields); start = len(self.m.trace)
        if op == 4 and status in (0, 5):
            address = 0x7e1000 + slot * 32 if stream else 0x7e0800
            pending = int.from_bytes(self.m.data[address + 16:address + 20], 'little')
            update = pending if amount == 0 else min(amount, pending)
            if update:
                self.server.increment_flow_control_window(update, stream_id=stream or None)
                self.expected_wire.append(self.server.data_to_send())
        await FallingEdge(d.clk); self.set(req_valid=1)
        while True:
            await RisingEdge(d.clk)
            if value(d, 'req_ready'): break
        await FallingEdge(d.clk)
        self.set(req_valid=0, req_op=15, req_authority=0, req_user=65535, req_stream=0x7fffffff,
            req_amount=0xffffffff, cfg_receive_connection_base=0, cfg_receive_connection_bytes=0)
        await self.wait('rsp_valid')
        result = {n: value(d, n) for n in RESULTS}
        assert result['rsp_status'] == status, (op, stream, result, status)
        assert (result['rsp_op'], result['rsp_user'], result['rsp_stream']) == (op, fields['req_user'], stream)
        assert all(row['acked'] for row in self.m.trace[start:])
        for _ in range(9):
            await cycles(d); assert value(d, 'rsp_valid') and result == {n: value(d, n) for n in RESULTS}
        self.set(rsp_ready=1); await cycles(d); self.set(rsp_ready=0)
        self.commands += 1
        return result, self.m.trace[start:]
    async def fresh(self):
        assert self.m.pending is None and not value(self.d, 'm_axis_tx_tvalid')
        assert self.m.data[:self.a['work_floor']] == self.image[:self.a['work_floor']]
        self.set(rst=1, req_valid=0, rsp_ready=0, context_write_busy=0, context_write_fault=0)
        await cycles(self.d, 5)
        self.m.data[:] = self.image; self.m.fail_at = -1; self.expected_wire.clear()
        for user in range(3):
            struct.pack_into('<Q', self.m.data, self.a['context_base'] + user * 256,
                (16384 << 40) | (3 << 32) | 0x48324331)
        # Actual directory bytes are typed fixture authority for this component.
        for slot, stream in enumerate((1, 3, 5, 7)):
            address = self.a['stream_base'] + slot * 128
            self.m.data[address:address + 128] = bytes(128)
            struct.pack_into('<8I', self.m.data, address, 0x47525331, 1, 100 << 16, stream,
                0x740000 + slot * 256, 256, 256, 101 + slot)
        self.client = H2Connection(H2Configuration(client_side=True))
        self.server = H2Connection(H2Configuration(client_side=False))
        self.client.initiate_connection(); self.server.initiate_connection()
        self.server.receive_data(self.client.data_to_send()); self.client.receive_data(self.server.data_to_send())
        self.server.receive_data(self.client.data_to_send()); self.server.data_to_send()
        for stream in (1, 3):
            self.client.send_headers(stream, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'), (':path', '/rpc')])
        self.server.receive_data(self.client.data_to_send()); self.server.data_to_send()
        self.set(rst=0); await cycles(self.d)
    async def setup(self, op):
        await self.fresh()
        if op != 0: await self.command(0, amount=65535)
        if op not in (0, 1): await self.command(1, 1)
        if op in (3, 4, 5, 9):
            self.client.send_data(1, b'hello', pad_length=7)
            events = self.server.receive_data(self.client.data_to_send())
            assert any(getattr(e, 'flow_controlled_length', 0) == 13 for e in events)
            await self.command(2, 1, 13)
        if op == 4: await self.command(3, 1, 13)
        if op == 9:
            # Typed successful CLOSE fixture: the real store invalidates only
            # its header, leaving the old immutable identity/generation bytes.
            self.m.data[self.a['stream_base']:self.a['stream_base'] + 8] = bytes(8)
            self.server.reset_stream(1, error_code=8); self.client.receive_data(self.server.data_to_send())


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def native_receive_credit_memory_and_wire_retirement(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text()); image = (folder / 'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    memory = Memory(d, image); b = Bench(d, memory, image, reference['layout'])
    b.set(rst=1, req_valid=0, rsp_ready=0, m_axis_tx_tready=0, context_write_busy=0, context_write_user=0,
        context_write_address=0, context_write_fault=0, context_write_fault_user=0, context_write_fault_address=0,
        context_write_fault_memory_status=0)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()); cocotb.start_soon(memory.run()); cocotb.start_soon(b.observe_tx())
    await cycles(d, 5); await b.setup(4)
    b.ready_tx = False
    returning = cocotb.start_soon(b.command(4, amount=0))
    await b.wait('m_axis_tx_tvalid')
    assert memory.pending is None and all(row['acked'] for row in memory.trace)
    assert int.from_bytes(memory.data[0x7e0814:0x7e0818], 'little') == 13
    assert b.client.outbound_flow_control_window == 65522
    await cycles(d, 17); b.ready_tx = True; result, _ = await returning
    assert result['rsp_wire_retired'] and result['rsp_connection_available'] == 65535
    await b.command(4, 1)
    assert b.client.local_flow_control_window(1) == 65535 and not b.expected_wire
    before = len(b.wire); await b.command(4, 1); assert len(b.wire) == before
    await b.command(3, 1, 1, status=2)
    _, trace = await b.command(8, 1, status=3, patch={'req_generation': 999})
    assert not any(row['write'] for row in trace) and not value(d, 'recovery_required')
    # Match the actual raw writer scope; wait and reread its committed header.
    address = b.a['context_base']; header = bytes(memory.data[address:address + 8])
    memory.data[address:address + 8] = bytes(8)
    b.set(context_write_busy=1, context_write_user=0, context_write_address=address)
    reading = cocotb.start_soon(b.command(8))
    for _ in range(100000):
        await FallingEdge(d.clk)
        if value(d, 'state') == 14: break
    else: raise AssertionError('Matching raw writer did not hold receive-credit header validation')
    commands = len(memory.trace); await cycles(d, 23)
    assert len(memory.trace) == commands and not value(d, 'rsp_valid')
    memory.data[address:address + 8] = header; b.set(context_write_busy=0); await reading
    b.set(context_write_busy=1, context_write_user=1, context_write_address=address + 256)
    await b.command(8); b.set(context_write_busy=0)
    # Both scopes enforce the native sender's budget, independently.
    await b.setup(2); await b.command(2, 1, 65536, status=4)
    for offset in range(0, 65500, 16384):
        b.client.send_data(1, b'x' * min(16384, 65500 - offset))
        b.server.receive_data(b.client.data_to_send())
    await b.command(2, 1, 65500); await b.command(3, 1, 65500); await b.command(4)
    assert b.client.outbound_flow_control_window == 65535 and b.client.local_flow_control_window(1) == 35
    try: b.client.send_data(1, b'x' * 36)
    except FlowControlError: pass
    else: raise AssertionError('Native peer did not enforce its remaining stream budget')
    r, writes = await b.command(2, 1, 36, status=4)
    assert r['rsp_connection_error'] == 0 and r['rsp_http2_error'] == 3 and not any(x['write'] for x in writes)
    await b.setup(5); r, _ = await b.command(5, 1)
    assert r['rsp_connection_pending'] == 13
    r, trace = await b.command(5, 1)
    assert r['rsp_connection_pending'] == 13 and not any(row['write'] for row in trace)
    await b.command(2, 1, 1, status=3); await b.command(4)
    await b.setup(5)
    r, trace = await b.command(9, 1, status=3)
    assert not any(row['write'] for row in trace) and r['rsp_connection_pending'] == 0
    await b.setup(9); r, trace = await b.command(9, 1, status=3, patch={'req_generation': 999})
    assert not any(row['write'] for row in trace)
    r, _ = await b.command(9, 1); assert r['rsp_connection_pending'] == 13
    r, trace = await b.command(9, 1); assert r['rsp_connection_pending'] == 13 and not any(row['write'] for row in trace)
    await b.command(4); assert b.client.outbound_flow_control_window == 65535
    # Each acknowledged phase can fail after its physical write has applied.
    cases = []; operations = [(0, 0, 65535), (1, 1, 0), (2, 1, 13), (3, 1, 13), (4, 0, 0), (4, 1, 0), (5, 1, 0), (9, 1, 0)]
    for op, stream, amount in operations:
        await b.setup(op); _, baseline = await b.command(op, stream, amount)
        count = len(baseline)
        for phase in range(count):
            await b.setup(op); memory.fail_at = len(memory.trace) + phase; wire_start = len(b.wire)
            r, trace = await b.command(op, stream, amount, status=5)
            assert r['rsp_memory_status'] == 0x75 and value(d, 'recovery_required')
            assert len(trace) == phase + 1 and len(b.wire) - wire_start == int(r['rsp_wire_retired'])
            assert not r['rsp_debit_authorized']
            _, blocked = await b.command(8, status=6); assert not blocked
            _, blocked = await b.command(0, amount=65535, status=6, patch={'req_user': 1}); assert not blocked
            cases.append(dict(op=op, stream=stream, phase=phase, memory_commands=phase + 1, wire_retired=bool(r['rsp_wire_retired'])))
        d._log.info('Verified receive-credit operation %d/stream %d: %d ACK faults', op, stream, count)
    assert memory.data[:reference['layout']['work_floor']] == image[:reference['layout']['work_floor']]
    result = dict(phase='passed', native_window_update_packets_verified=True, held_wire_cycles=b.held_tx,
        actual_intent_ack_before_wire_verified=True, actual_wire_before_available_commit_verified=True,
        matching_context_writer_wait_and_fresh_read_verified=True, foreign_writer_scope_does_not_stall=True,
        foreign_format_cannot_clear_quarantine=True, closed_stream_credit_return_is_idempotent=True,
        retired_rpc_requires_inactive_matching_binding=True, retired_rpc_credit_return_is_idempotent=True,
        every_memory_ack_fault=cases, complete_model_prefix_immutable=True, typed_directory_authority_supplied_by_fixture=True,
        typed_consumption_supplied_by_fixture=True, actual_raw_parser_integrated=False,
        actual_descriptor_consumption_integrated=False, receive_flow_control_end_to_end_verified=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
