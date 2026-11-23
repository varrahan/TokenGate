"""Geometry-backed credit announcements through the actual durable RX store.

Directory and maintenance/consumption authority are typed component fixtures.
This does not instantiate the Parser, packet commit owner or DMA retirement.
"""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

from test_receive_credit_store import Bench, Memory, value
from test_tokenizer_mmio import cycles


PAYLOAD = 0x740000
SLOT = 131072
SLOTS = 4
STREAM_CAPACITY = SLOT + 5
CONNECTION_CAPACITY = STREAM_CAPACITY * SLOTS


class CapacityBench(Bench):
    async def command(self, op, stream=0, amount=0, status=0, patch=None):
        fields = dict(req_maintenance=int(op in (0, 12)), cfg_payload_base=PAYLOAD,
            cfg_payload_bytes=SLOT * SLOTS, cfg_payload_slot_bytes=SLOT)
        fields.update(patch or {})
        return await super().command(op, stream, amount, status, fields)

    async def fresh(self):
        await super().fresh()
        # Each case resets both native peers and the image. Its wire log must
        # have the same scope; the base helper keeps a lifetime history.
        self.wire.clear()
        assert self.a['stream_bytes'] == SLOTS * 128
        for slot in range(SLOTS):
            struct.pack_into('<3I', self.m.data, self.a['stream_base'] + slot * 128 + 16,
                PAYLOAD + slot * SLOT, SLOT, 65536)
        # Native h2 already opened streams 1 and 3 in the unchanged helper.
        for stream in (5, 7):
            self.client.send_headers(stream, [(':method', 'POST'), (':scheme', 'https'),
                (':authority', 'parser.test'), (':path', '/rpc')])
        self.server.receive_data(self.client.data_to_send()); self.server.data_to_send()

    async def setup_capacity(self, op, stream):
        await self.fresh()
        if op != 12: await self.command(12)
        if op not in (12, 1): await self.command(1, 1)
        if op in (3, 5):
            await self.command(4, 1)
            await self.command(4)
            record = b'\0\0\1\0\0' + b'U' * 65536
            for offset in range(0, len(record), 16384):
                chunk = record[offset:offset + 16384]
                self.client.send_data(1, chunk)
                events = self.server.receive_data(self.client.data_to_send())
                assert b''.join(e.data for e in events if type(e).__name__ == 'DataReceived') == chunk
                await self.command(2, 1, len(chunk))


async def poison_after_capture(d):
    while True:
        await RisingEdge(d.clk)
        if value(d, 'req_valid') and value(d, 'req_ready'): break
    await FallingEdge(d.clk)
    d.cfg_payload_base.value = 0x7fffff
    d.cfg_payload_bytes.value = 0
    d.cfg_payload_slot_bytes.value = 0


@cocotb.test(timeout_time=40, timeout_unit='ms')
async def native_capacity_grants_geometry_and_every_ack_fault(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text())
    image = (folder / 'model.bin').read_bytes()
    assert len(image) == 8388608 and hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    memory = Memory(d, image); b = CapacityBench(d, memory, image, reference['layout'])
    b.set(rst=1, req_valid=0, rsp_ready=0, m_axis_tx_tready=0,
        cfg_payload_base=PAYLOAD, cfg_payload_bytes=SLOT * SLOTS, cfg_payload_slot_bytes=SLOT,
        context_write_busy=0, context_write_user=0, context_write_address=0,
        context_write_fault=0, context_write_fault_user=0, context_write_fault_address=0,
        context_write_fault_memory_status=0)
    for worker in (Clock(d.clk, 4, unit='ns').start(), memory.run(), b.observe_tx()): cocotb.start_soon(worker)
    await cycles(d, 5)
    await b.fresh()
    poison = cocotb.start_soon(poison_after_capture(d))
    result, _ = await b.command(12)
    await poison
    assert result['rsp_connection_available'] == 65535
    assert result['rsp_connection_pending'] == CONNECTION_CAPACITY - 65535
    assert not b.wire and b.client.outbound_flow_control_window == 65535
    assert struct.unpack_from('<2I', memory.data, 0x7e0800 + 56) == (PAYLOAD, SLOT * SLOTS)
    result, _ = await b.command(1, 1)
    assert result['rsp_stream_available'] == 65535 and result['rsp_stream_pending'] == STREAM_CAPACITY - 65535
    assert not b.wire
    # Additional backing is pending capacity, not consumed data. Neither
    # ledger may mint a consumption refund before any actual DATA debit.
    _, trace = await b.command(3, 1, 1, status=2)
    assert not any(c['write'] for c in trace)
    b.ready_tx = False
    sending = cocotb.start_soon(b.command(4, 1))
    await b.wait('m_axis_tx_tvalid')
    assert memory.pending is None and all(c['acked'] for c in memory.trace)
    assert b.client.streams[1].outbound_flow_control_window == 65535
    assert struct.unpack_from('<2I', memory.data, 0x7e1000 + 16) == (0, STREAM_CAPACITY - 65535)
    await cycles(d, 19)
    assert b.client.streams[1].outbound_flow_control_window == 65535
    b.ready_tx = True; result, _ = await sending
    assert result['rsp_wire_retired'] and result['rsp_stream_available'] == STREAM_CAPACITY
    await b.command(4)
    assert b.client.outbound_flow_control_window == CONNECTION_CAPACITY
    assert b.client.local_flow_control_window(1) == STREAM_CAPACITY
    # Exercise one complete 65536-byte body plus its gRPC prefix, using real
    # legal native DATA frames and one actual ledger debit per frame.
    record = b'\0\0\1\0\0' + b'U' * 65536
    offset = 0
    while offset < len(record):
        n = min(16384, len(record) - offset)
        b.client.send_data(1, record[offset:offset + n], end_stream=offset + n == len(record))
        events = b.server.receive_data(b.client.data_to_send())
        assert b''.join(e.data for e in events if type(e).__name__ == 'DataReceived') == record[offset:offset + n]
        result, _ = await b.command(2, 1, n)
        assert result['rsp_debit_authorized'] and result['rsp_connection_available'] == b.client.outbound_flow_control_window
        assert result['rsp_stream_available'] == b.client.streams[1].outbound_flow_control_window
        offset += n
    assert offset == 65541
    await b.command(3, 1, offset)
    await b.command(4, 1); await b.command(4)
    assert b.client.outbound_flow_control_window == CONNECTION_CAPACITY
    assert b.client.streams[1].outbound_flow_control_window == STREAM_CAPACITY
    large_case = dict(actual_data_bytes=offset, wire_hex=[raw.hex() for raw in b.wire],
        stream_capacity=STREAM_CAPACITY, connection_capacity=CONNECTION_CAPACITY)

    # Four actual allocated slots share one connection budget. Interleaved
    # native DATA consumes both ledgers; partial messages require no invented
    # application completion or RELEASE to receive the initial capacity.
    await b.fresh(); await b.command(12)
    for stream in (1, 3, 5, 7): await b.command(1, stream); await b.command(4, stream)
    await b.command(4)
    for _ in range(2):
        for stream in (1, 3, 5, 7):
            b.client.send_data(stream, b'P' * 16384)
            events = b.server.receive_data(b.client.data_to_send())
            assert sum(len(e.data) for e in events if type(e).__name__ == 'DataReceived') == 16384
            result, _ = await b.command(2, stream, 16384)
            assert result['rsp_connection_available'] == b.client.outbound_flow_control_window
    before_close = b.client.outbound_flow_control_window
    for stream in (1, 3, 5, 7): await b.command(5, stream)
    result, _ = await b.command(8)
    assert result['rsp_connection_pending'] == 4 * 32768
    await b.command(4)
    assert b.client.outbound_flow_control_window == CONNECTION_CAPACITY
    wire_count = len(b.wire)
    for stream in (1, 3, 5, 7): await b.command(5, stream)
    await b.command(4)
    assert len(b.wire) == wire_count
    interleaved = dict(streams=4, data_bytes=4 * 32768, connection_available_before_close=before_close,
        final_connection_available=b.client.outbound_flow_control_window, close_refund_idempotent=True,
        wire_hex=[raw.hex() for raw in b.wire])

    # Closing a never-debited stream must not count its unannounced extra
    # capacity as consumed DATA and refund that capacity a second time.
    await b.fresh(); await b.command(12); await b.command(1, 1)
    result, _ = await b.command(5, 1)
    assert result['rsp_connection_pending'] == CONNECTION_CAPACITY - 65535
    assert result['rsp_stream_pending'] == 0
    await b.command(4)
    assert b.client.outbound_flow_control_window == CONNECTION_CAPACITY

    bad_geometries = [dict(cfg_payload_base=b.a['work_floor'] - 8),
        dict(cfg_payload_bytes=SLOT * SLOTS - 1), dict(cfg_payload_slot_bytes=65529),
        dict(cfg_payload_base=0x7ffff8)] + [dict(cfg_payload_base=base) for base in
            (b.a['context_base'], b.a['stream_base'], 0x7e0800, 0x7e1000)]
    for patch in bad_geometries:
        await b.fresh()
        _, trace = await b.command(12, status=2, patch=patch)
        assert not trace and not value(d, 'recovery_required') and not b.wire
    bad_rpc_cases = [(16, PAYLOAD + 8), (20, SLOT - 1), (24, SLOT + 1), (24, 0)]
    for offset, data in bad_rpc_cases:
        await b.fresh(); await b.command(12)
        struct.pack_into('<I', memory.data, b.a['stream_base'] + offset, data)
        _, trace = await b.command(1, 1, status=3)
        assert not any(c['write'] for c in trace) and not b.wire
    await b.fresh(); await b.command(12)
    _, trace = await b.command(8, status=5, patch=dict(cfg_payload_base=PAYLOAD + 8))
    assert not any(c['write'] for c in trace) and value(d, 'recovery_required')
    start = len(memory.trace)
    await b.command(12, status=6)
    assert len(memory.trace) == start, 'Foreign backing configuration cleared quarantine'
    await b.command(12, patch=dict(cfg_payload_base=PAYLOAD + 8))
    assert not value(d, 'recovery_required')

    faults = []; baselines = []
    def ledgers():
        return dict(connection=bytes(memory.data[0x7e0800:0x7e0840]).hex(),
            stream=bytes(memory.data[0x7e1000:0x7e1020]).hex())
    for op, stream, amount, phases in ((12, 0, 0, 10), (1, 1, 0, 22), (4, 1, 0, 20), (4, 0, 0, 12),
        (3, 1, 65541, 19), (5, 1, 0, 20)):
        await b.setup_capacity(op, stream)
        before = ledgers()
        _, baseline = await b.command(op, stream, amount)
        assert len(baseline) == phases
        baselines.append(dict(op=op,stream=stream,amount=amount,actual_memory_trace=baseline,
            before_ledgers=before,after_ledgers=ledgers()))
        for phase in range(phases):
            await b.setup_capacity(op, stream)
            before = ledgers()
            start = len(memory.trace)
            memory.fail_at = start + phase
            result, trace = await b.command(op, stream, amount, status=5)
            assert value(d, 'recovery_required') and result['rsp_memory_status'] == 0x75
            assert len(trace) == phase + 1 and all(c['acked'] for c in trace)
            assert [c['status'] for c in trace] == [0] * phase + [0x75]
            assert result['rsp_wire_retired'] == (op == 4 and phase >= phases - 2)
            after = ledgers()
            memory.fail_at = -1
            command_count, wire_count = len(memory.trace), len(b.wire)
            await b.command(8, status=6)
            await b.command(12, status=6, patch=dict(cfg_payload_base=PAYLOAD + 8))
            assert (len(memory.trace), len(b.wire)) == (command_count, wire_count)
            await b.command(12)
            assert not value(d, 'recovery_required')
            assert len(b.wire) == wire_count, 'FORMAT emitted credit before packet/stream commit authority'
            assert memory.data[:b.a['work_floor']] == image[:b.a['work_floor']]
            faults.append(dict(op=op, stream=stream, amount=amount, phase=phase, memory_commands=len(trace),
                wire_retired=bool(result['rsp_wire_retired']), error=result['rsp_memory_status'],
                actual_memory_trace=trace,before_ledgers=before,after_ledgers=after,
                foreign_backing_cannot_clear_quarantine=True))
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed', large_record=large_case,
        interleaved=interleaved, every_capacity_memory_ack_fault=faults,
        actual_operation_baselines=baselines,
        invalid_backing_geometries=len(bad_geometries), invalid_rpc_backings=len(bad_rpc_cases),
        actual_intent_ack_before_capacity_wire=True, actual_wire_before_available_commit=True,
        captured_backing_survives_input_poison=True, unused_pending_capacity_not_refunded_twice=True,
        complete_model_prefix_immutable=True, complete_model_bytes=len(image),
        typed_directory_maintenance_and_consumption_authority=True,
        actual_parser_integrated=False, actual_dma_retirement_integrated=False,
        original_large_message_counterexample_fixed=False, whole_system_retained_reset_verified=False,
        full_system_complete=False), indent=2) + '\n')
