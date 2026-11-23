"""Resolve real wire keys through actual runtime directory reads before credit."""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_receive_credit_store import Bench as BaseBench, Memory, value
from test_tokenizer_mmio import cycles


class Bench(BaseBench):
    async def observe_binding(self):
        held = None
        while True:
            await RisingEdge(self.d.clk)
            if value(self.d, 'rst'): held = None; continue
            if value(self.d, 'rsp_valid'):
                item = tuple(value(self.d, n) for n in ('rsp_binding_valid', 'rsp_record_address', 'rsp_generation'))
                if held is not None: assert item == held
                if value(self.d, 'rsp_status') == 0 and value(self.d, 'rsp_stream') == 1:
                    assert item == (1, self.a['stream_base'] + 3 * 128, 104)
                elif value(self.d, 'rsp_status') != 0: assert not item[0]
                held = item if not value(self.d, 'rsp_ready') else None
            else: assert held is None
    async def command(self, op, stream=0, amount=0, status=0, patch=None, *, keyed=False):
        self.set(req_keyed=int(keyed))
        patch = dict(patch or {})
        if keyed:
            patch.update(req_generation=0, req_record_address=0)
        if op == 4 and stream == 1 and status in (0, 5):
            # Stream 1 is deliberately stored in slot three, rather than its
            # natural wire-ID position. This is an independent expected packet.
            pending = int.from_bytes(self.m.data[0x7e1070:0x7e1074], 'little')
            update = pending if amount == 0 else min(amount, pending)
            if update:
                self.server.increment_flow_control_window(update, stream_id=1)
                self.expected_wire.append(self.server.data_to_send())
        async def poison_keyed_after_accept():
            while True:
                await RisingEdge(self.d.clk)
                if value(self.d, 'req_valid') and value(self.d, 'req_ready'): break
            await FallingEdge(self.d.clk); self.d.req_keyed.value = int(not keyed)
        poisoning = cocotb.start_soon(poison_keyed_after_accept())
        result, trace = await super().command(op, stream, amount, status, patch)
        await poisoning
        result.update(binding_valid=value(self.d, 'rsp_binding_valid'),
            actual_record_address=value(self.d, 'rsp_record_address'), actual_generation=value(self.d, 'rsp_generation'))
        # Public valid has retired here. Stable actual binding registers are
        # diagnostics; binding_valid is checked while held in capture below.
        return result, trace
    async def setup_keyed(self, op):
        self.set(req_keyed=0)
        await self.fresh()
        self.set(req_keyed=0)
        base = self.a['stream_base']
        struct.pack_into('<I', self.m.data, base + 8, (100 << 16) | 1)
        self.m.data[base + 256:base + 264] = bytes(8)
        struct.pack_into('<I', self.m.data, base + 3 * 128 + 12, 1)
        await self.command(0, amount=65535)
        await self.command(1, 1, patch={'req_record_address': base + 3 * 128, 'req_generation': 104})
        if op in (2, 3, 4, 5):
            self.client.send_data(1, b'hello', pad_length=7)
            events = self.server.receive_data(self.client.data_to_send())
            assert any(getattr(event, 'flow_controlled_length', 0) == 13 for event in events)
            if op != 2: await self.command(2, 1, 13, keyed=True)
        if op == 4: await self.command(3, 1, 13, keyed=True)


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def actual_key_lookup_preserves_receive_credit_ownership(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text()); image = (folder / 'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    memory = Memory(d, image); b = Bench(d, memory, image, reference['layout'])
    b.set(rst=1, req_keyed=0, req_valid=0, rsp_ready=0, m_axis_tx_tready=0,
        context_write_busy=0, context_write_user=0, context_write_address=0,
        context_write_fault=0, context_write_fault_user=0, context_write_fault_address=0, context_write_fault_memory_status=0)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()); cocotb.start_soon(memory.run()); cocotb.start_soon(b.observe_tx()); cocotb.start_soon(b.observe_binding())
    await cycles(d, 5); await b.setup_keyed(2)
    result, trace = await b.command(2, 1, 13, keyed=True)
    target = b.a['stream_base'] + 3 * 128
    assert result['actual_record_address'] == target and result['actual_generation'] == 104
    assert result['rsp_debit_authorized'] and result['rsp_stream_available'] == 65522
    assert any(row['address'] == target + 24 and not row['write'] for row in trace)
    assert all(row['address'] not in range(b.a['stream_base'], b.a['stream_base'] + b.a['stream_bytes']) for row in trace if row['write'])
    await b.command(3, 1, 13, keyed=True); await b.command(4, 1, keyed=True); await b.command(4)
    assert b.client.outbound_flow_control_window == b.client.local_flow_control_window(1) == 65535
    _, trace = await b.command(8, 7, status=3, keyed=True)
    assert not any(row['write'] for row in trace) and not value(d, 'recovery_required')
    # The delegated backend revalidates the actual generation after the scan.
    await b.setup_keyed(2)
    querying = cocotb.start_soon(b.command(2, 1, 13, status=3, keyed=True))
    for _ in range(100000):
        await FallingEdge(d.clk)
        if value(d, 'state') == 7: break
    else: raise AssertionError('Actual key scan did not reach backend delegation')
    struct.pack_into('<I', memory.data, target + 28, 999)
    result, trace = await querying
    assert not result['rsp_debit_authorized'] and not any(row['write'] for row in trace)
    faults = []; phase_counts = {}
    for op, amount in ((2, 13), (3, 13), (4, 0), (5, 0)):
        await b.setup_keyed(op); _, baseline = await b.command(op, 1, amount, keyed=True)
        phase_counts[str(op)] = len(baseline)
        for phase in range(len(baseline)):
            await b.setup_keyed(op); memory.fail_at = len(memory.trace) + phase; before = len(b.wire)
            result, trace = await b.command(op, 1, amount, status=5, keyed=True)
            assert result['rsp_memory_status'] == 0x75 and value(d, 'recovery_required')
            assert len(trace) == phase + 1 and not result['rsp_debit_authorized']
            assert len(b.wire) - before == int(result['rsp_wire_retired'])
            _, blocked = await b.command(8, status=6); assert not blocked
            _, blocked = await b.command(0, amount=65535, status=6, patch={'req_user': 1}); assert not blocked
            faults.append(dict(op=op, phase=phase, memory_commands=phase + 1, wire_retired=bool(result['rsp_wire_retired'])))
        d._log.info('Verified keyed receive operation %d: %d ACK faults', op, len(baseline))
    assert memory.data[:b.a['work_floor']] == image[:b.a['work_floor']]
    accepted = dict(phase='passed', actual_key_lookup_reads_verified=True,
        nontrivial_runtime_slot_and_generation_verified=True, foreign_connection_key_skipped=True,
        held_actual_binding_matches_verified_generation=True,
        missing_key_does_not_authorize_or_quarantine=True, backend_revalidates_scanned_generation=True,
        actual_native_window_update_packets_verified=True, accepted_input_poisoning_verified=True,
        all_memory_ack_faults=faults, operation_memory_phase_counts=phase_counts,
        complete_model_prefix_immutable=True, directory_pool_authority_supplied_by_fixture=True,
        consumed_bytes_supplied_by_fixture=True, actual_raw_parser_integrated=False,
        actual_descriptor_consumption_integrated=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
