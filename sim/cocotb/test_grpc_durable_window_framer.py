"""Actual cached binding -> durable dual debits -> exact DATA frames."""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_http2_owned_windows import Bench, Memory
from test_tokenizer_mmio import cycles


class Wire:
    def __init__(self, d, memory):
        self.d = d; self.m = memory; self.frames = []; self.grants = []; self.errors = []
        self.attempts = 0; self.stalls = 0; self.reserve_start = None; self.rng = random.Random(20261125)

    async def run(self):
        d = self.d; packet = bytearray(); held = None; granted = None
        while True:
            await FallingEdge(d.clk)
            d.m_axis_tx_tready.value = self.rng.randrange(4) != 0
            await RisingEdge(d.clk)
            if int(d.rst.value):
                assert not packet and held is None
                granted = None; continue
            if int(d.state.value) == 0 and int(d.owned_request_ready.value) and int(d.reserve_pending.value) and not int(d.window_req_valid.value):
                self.reserve_start = len(self.m.trace); self.attempts += 1
            if int(d.frame_request_valid.value) and int(d.frame_request_ready.value):
                amount = int(d.grant_bytes.value)
                if amount:
                    assert granted is None and self.reserve_start is not None
                    writes = [e for e in self.m.trace[self.reserve_start:] if e['client'] == 1 and e['write']]
                    assert len(writes) == 2 and all(e['ack_cycle'] is not None for e in writes), 'Grant preceded both durable debit ACKs'
                    assert writes[0]['address'] == self.m.a['window_base'] + 8
                    assert writes[1]['address'] == self.m.a['context_base'] + 176
                    granted = amount; self.grants.append(amount)
                else:
                    assert int(d.credit_error_valid.value) and int(d.credit_error_ready.value)
                    self.errors.append(int(d.credit_error_status.value))
            if int(d.m_axis_tx_tvalid.value):
                assert granted is not None, 'DATA escaped without a durable grant'
                item = tuple(int(getattr(d, n).value) for n in ('m_axis_tx_tdata', 'm_axis_tx_tkeep', 'm_axis_tx_tlast', 'm_axis_tx_tuser'))
                if held is not None: assert item == held, 'TX changed under backpressure'
                if not int(d.m_axis_tx_tready.value):
                    held = item; self.stalls += 1
                else:
                    held = None; data, keep, last, user = item
                    assert user == 0 and keep and keep & (keep + 1) == 0
                    raw = data.to_bytes(64, 'little'); packet.extend(raw[:keep.bit_count()])
                    if last:
                        assert len(packet) == granted + 9 and int.from_bytes(packet[:3], 'big') == granted
                        self.frames.append(bytes(packet)); packet.clear(); granted = None
            else:
                assert held is None, 'TX was withdrawn while stalled'


async def start_message(b, payload, *, premature_lease_ack=False):
    d = b.d; a = b.a
    b.set(start_valid=0, start_user=0, start_stream=1, cfg_peer_max_frame_bytes=65536,
        s_axis_message_tdata=0, s_axis_message_tkeep=0, s_axis_message_tvalid=0,
        s_axis_message_tlast=0, s_axis_message_tuser=0, s_axis_message_abort=0,
        result_ready=0, credit_error_ready=0)
    for name in ('context_base', 'context_bytes', 'stream_base', 'stream_bytes', 'window_base', 'window_bytes', 'work_floor'):
        getattr(d, 'frame_cfg_' + name).value = a[name]
    await FallingEdge(d.clk)
    d.start_valid.value = 1
    if premature_lease_ack: d.lease_rsp_ready.value = 1
    while True:
        await RisingEdge(d.clk)
        if int(d.start_ready.value): break
    await FallingEdge(d.clk)
    d.start_valid.value = 0
    # Every accepted frame uses captured pools and real cached metadata.
    b.set(start_user=0xffff, start_stream=0x7fffffff, cfg_peer_max_frame_bytes=0)
    for name in ('context_base', 'context_bytes', 'stream_base', 'stream_bytes', 'window_base', 'window_bytes', 'work_floor'):
        getattr(d, 'frame_cfg_' + name).value = 0x7fffff if name.endswith(('base', 'floor')) else 0
    for offset in range(0, max(1, len(payload)), 64):
        block = payload[offset:offset + 64]
        b.set(s_axis_message_tdata=int.from_bytes(block, 'little'), s_axis_message_tkeep=(1 << len(block)) - 1,
              s_axis_message_tlast=offset + 64 >= len(payload))
        await b.send('s_axis_message_tvalid', 's_axis_message_tready')
    b.set(s_axis_message_tdata=0, s_axis_message_tkeep=0, s_axis_message_tlast=0)


async def retire_frame(b, *, status=0):
    d = b.d; await b.wait('result_valid')
    result = tuple(int(getattr(d, n).value) for n in ('result_status', 'result_user', 'result_stream',
        'result_message_bytes', 'result_wire_bytes', 'result_frames', 'result_tx_emitted'))
    assert result[0:3] == (status, 0, 1), result
    for _ in range(17):
        await cycles(d)
        assert int(d.result_valid.value) and int(d.lease_rsp_valid.value)
        assert result == tuple(int(getattr(d, n).value) for n in ('result_status', 'result_user', 'result_stream',
            'result_message_bytes', 'result_wire_bytes', 'result_frames', 'result_tx_emitted'))
    d.lease_rsp_ready.value = 0
    await b.retire('result_ready')
    await cycles(d, 3)
    await b.retire('lease_rsp_ready')
    return result


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def actual_durable_grants_partial_frames_and_uncertain_debit(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text()); image = (folder / 'model.bin').read_bytes()
    frames = json.loads((Path(os.environ['PARSER_DURABLE_FRAMER_FIXTURES']) / 'frames.json').read_text())
    assert frames['phase'] == 'native_durable_framer_reference_passed'
    assert hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    memory = Memory(d, image, reference['layout']); b = Bench(d, memory, reference['layout']); wire = Wire(d, memory)
    b.set(rst=1, req_valid=0, rsp_ready=0, lease_valid=0, lease_rsp_ready=0, window_req_valid=0,
          window_rsp_ready=0, start_valid=0, s_axis_message_tvalid=0, result_ready=0, credit_error_ready=0)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run()); cocotb.start_soon(wire.run())
    await b.fresh(); await b.window(0)
    for stream in (1, 3):
        await b.directory(0, stream); await b.window(1, stream)
    await b.window(3, amount=0); await b.lease(1)
    await start_message(b, bytes.fromhex(frames['message_hex']), premature_lease_ack=True)
    await b.wait('credit_parked')
    attempts = wire.attempts; before = len(memory.trace)
    await cycles(d, 40)
    assert wire.attempts == attempts and len(memory.trace) == before and not wire.frames
    await b.window(2, 3, 1)
    await cycles(d, 30)
    assert int(d.credit_parked.value) and wire.attempts == attempts
    for index, frame in enumerate(frames['frames']):
        await b.window(2, 1, frame['increment'])
        while len(wire.frames) <= index: await cycles(d)
        assert wire.frames[index] == bytes.fromhex(frame['wire_hex'])
        result = await b.window(6, 1)
        assert result['rsp_connection_window'] == frame['connection_window'] and result['rsp_stream_window'] == 0
        if index + 1 < len(frames['frames']): await b.wait('credit_parked')
    result = await retire_frame(b)
    assert result[3:7] == (20000, frames['wire_bytes'], 4, 1)
    assert wire.grants == [f['payload_bytes'] for f in frames['frames']] and wire.stalls > 0

    # An applied stream debit with a failed ACK cannot produce a DATA frame or
    # release the pool/lease before the retained error and frame results retire.
    await b.fresh(); await b.window(0); await b.directory(0, 1); await b.window(1, 1); await b.lease(1)
    before_frames = len(wire.frames)
    memory.fail_client = 1; memory.fail_at = memory.count[1] + 13
    await start_message(b, b'uncertain-debit', premature_lease_ack=True)
    await b.wait('credit_error_valid')
    assert int(d.credit_error_status.value) == 5 and int(d.credit_error_memory_status.value) == 0x75
    assert int(d.window_recovery_required.value) and int(d.directory_pool_lock_active.value)
    for _ in range(23):
        await cycles(d)
        assert int(d.credit_error_valid.value) and not int(d.m_axis_tx_tvalid.value) and int(d.lease_rsp_valid.value)
    d.credit_error_ready.value = 1
    await b.wait('result_valid'); d.credit_error_ready.value = 0
    result = await retire_frame(b, status=5)
    assert result[4:7] == (0, 0, 0) and len(wire.frames) == before_frames and wire.errors == [5]
    memory.fail_client = -1
    await b.window(7)
    assert not int(d.window_recovery_required.value)

    # Real send closure rejects a subsequent frame reservation without DATA.
    await b.fresh(); await b.window(0); await b.directory(0, 1); await b.window(1, 1)
    await b.window(8, 1); await b.lease(1)
    before = memory.count[1]; trace_before = len(memory.trace)
    await start_message(b, b'closed-send')
    await b.wait('credit_error_valid')
    assert int(d.credit_error_status.value) == 8 and int(d.credit_error_http2_error.value) == 5
    assert not int(d.window_recovery_required.value)
    assert not any(e['client'] == 1 and e['write'] for e in memory.trace[trace_before:])
    d.credit_error_ready.value = 1
    await b.wait('result_valid'); d.credit_error_ready.value = 0
    await retire_frame(b, status=5)
    assert memory.count[1] - before == 13 and wire.errors == [5, 8] and len(wire.frames) == 4
    # Closing a parked sender must wake its reservation so it retires as closed
    # instead of waiting forever for credits that can no longer be used.
    await b.fresh(); await b.window(0); await b.directory(0, 1); await b.window(1, 1)
    await b.window(3, amount=0); await b.lease(1)
    await start_message(b, b'parked-cancellation')
    await b.wait('credit_parked')
    await b.window(8, 1)
    await b.wait('credit_error_valid')
    assert int(d.credit_error_status.value) == 8 and not int(d.window_recovery_required.value)
    d.credit_error_ready.value = 1
    await b.wait('result_valid'); d.credit_error_ready.value = 0
    await retire_frame(b, status=5)
    assert wire.errors == [5, 8, 8] and len(wire.frames) == 4
    await cycles(d, 4)
    assert int(d.idle.value) and not any(memory.pending)
    assert memory.data[:b.a['work_floor']] == image[:b.a['work_floor']]
    accepted = dict(phase='passed', exact_native_frames=4, application_bytes=20000,
        grpc_record_bytes=20005, wire_bytes=frames['wire_bytes'], grants=wire.grants,
        reserve_attempts=wire.attempts, tx_stall_cycles=wire.stalls, held_frame_result_cycles=68,
        actual_cached_directory_binding=True, actual_pool_authority=True, both_debits_before_grant=True,
        no_credit_parking_verified=True, unrelated_stream_does_not_retry=True,
        captured_frame_configuration_verified=True, actual_peer_max_frame_enforced=True,
        uncertain_debit_emits_no_data=True, closed_stream_emits_no_data=True,
        cached_lease_fenced_through_result=True, model_prefix_immutable=True,
        close_wakes_parked_sender=True,
        raw_http2_control_integrated=False, response_headers_trailers_implemented=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n'); d._log.info('PASS: %s', accepted)
