"""Real remote inverse, RPC metadata commits and framed wire retirement."""
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from test_rpc_response import Bench as BaseBench, exercise_rpc_fixture, val, RESULTS
from test_tokenizer_mmio import cycles


class FramedBench(BaseBench):
    def __init__(self, d, reference, memory, response=None):
        super().__init__(d, reference, memory)
        self.response = d.dut if response is None else response
        self.frame_oracle = json.loads((Path(os.environ['PARSER_RPC_RESPONSE_FIXTURES']) / 'frame_cases.json').read_text())
        assert self.frame_oracle['phase'] == 'native_references_passed'
        self.job_reference = None
        self.job_grants = self.job_frames = self.job_wire_bytes = 0
        self.frame_held = None
        self.wire_packet = bytearray(); self.record = bytearray()
        self.raw_buffered = False; self.metadata_write_pending = False; self.metadata_acks = 0
        self.total_frames = self.total_grants = self.credit_stalls = self.buffer_resets = 0
        self.progress_at_result = False

    async def ready(self):
        while True:
            await FallingEdge(self.d.clk)
            d = self.d
            d.m_axis_tx_tready.value = not val(d, 'rst') and self.clocks % 31 >= 9 and self.rng.randrange(4) != 0
            d.frame_req_ready.value = not val(d, 'rst') and self.clocks % 29 >= 11 and self.rng.randrange(4) == 0
            grants = self.job_reference['grants'] if self.job_reference else []
            d.frame_grant_bytes.value = grants[self.job_grants] if self.job_grants < len(grants) else 0

    async def run(self, b, chunk=None, *, framing_fault=None, **kwargs):
        c = chunk or dict(token=self.ref['ascii_token'], eos=0, ordinal=0, decoded_bytes=1)
        error = kwargs.get('error', (0, 0, 0))
        if framing_fault in ('zero_grant', 'late_zero_grant'):
            self.job_reference = self.frame_oracle[framing_fault]
            kwargs.update(error=(16, 5, 0), packet=b'' if framing_fault == 'late_zero_grant' else None, bow=b'A')
        elif framing_fault == 'bad_max':
            self.job_reference = None
            kwargs.update(error=(16, 1, 0), packet=None, bow=b'A', patch=dict(cfg_peer_max_frame_bytes=16383))
        elif error[1] == 0:
            body = bytes.fromhex(c.get('packet_hex', self.ref['ascii_packet_hex']))
            self.job_reference = self.frame_oracle['frames'][str(b['stream']) + ':' + body.hex()]
        else:
            self.job_reference = None
            # Raw serialization is buffered, so failed progress writes expose
            # no network bytes even after the old application TX completed.
            if kwargs.get('fault') and kwargs['fault'][0] == 0 and kwargs['fault'][1] >= 12:
                kwargs['packet'] = None
        self.job_grants = self.job_frames = self.job_wire_bytes = 0
        self.wire_packet.clear(); self.record.clear()
        self.frame_held = None; self.raw_buffered = False
        self.metadata_write_pending = False; self.metadata_acks = 0; self.progress_at_result = False
        self.d.cfg_peer_max_frame_bytes.value = 16384
        await super().run(b, chunk, **kwargs)
        if error[1] == 0 or framing_fault:
            assert self.metadata_acks == 5 and self.progress_at_result
        if framing_fault:
            assert val(self.d, 'recovery_required')
            assert val(self.d, 'recovery_address') == self.a['stream_base'] + b['slot'] * 128
            assert not val(self.d, 's_axis_tokens_tready'), 'Transport quarantine admitted new GPU work'

    async def observe(self):
        d, a = self.d, self.a
        extra = ('result_serialized_bytes', 'result_wire_bytes', 'result_frames', 'result_progress_committed')
        while True:
            await RisingEdge(d.clk)
            if val(d, 'rst'):
                continue
            self.clocks += 1
            if val(self.response, 'kill_ungranted'):
                assert self.job_grants == self.job_frames == 0 and not self.wire_packet
                assert not val(d, 'm_axis_tx_tvalid'), 'Private-buffer reset discarded reserved/wire traffic'
                self.buffer_resets += 1
            if val(self.response, 'raw_valid') and val(self.response, 'raw_ready'):
                assert self.binding is not None and val(d, 'directory_lease_active')
                assert val(self.response, 'raw_user') == self.binding['application']
                if val(self.response, 'raw_last'):
                    self.raw_buffered = True
            active = val(d, 'all_valid') & val(d, 'all_ready')
            for client in range(4):
                if not (active >> client & 1):
                    continue
                address = val(d, 'all_addr') >> (23 * client) & 0x7fffff
                count = val(d, 'all_bytes') >> (4 * client) & 15
                write = val(d, 'all_write') >> client & 1
                self.commands[client] += 1; self.writes[client] += write
                assert count == 8
                if write:
                    assert address >= a['work_floor'], ('Model write', client, address)
                    if client == 0:
                        assert a['progress_base'] <= address and address + 8 <= a['progress_base'] + a['progress_bytes']
                        assert self.raw_buffered and val(d, 'directory_lease_active')
                        assert self.job_grants == self.job_frames == 0 and not self.wire_packet
                        assert not self.metadata_write_pending
                        self.metadata_write_pending = True
                    elif client == 2:
                        assert a['stream_base'] <= address and address + 8 <= a['stream_base'] + a['stream_bytes']
                        assert (address - a['stream_base']) % 128 < 64
                    else:
                        assert client == 3
                if client in (0, 1):
                    assert val(d, 'directory_lease_active')
            if self.metadata_write_pending and val(d, 'all_rsp_valid') & val(d, 'all_rsp_ready') & 1:
                self.metadata_acks += 1; self.metadata_write_pending = False
            request = tuple(val(d, name) for name in ('frame_req_max_bytes', 'frame_req_user', 'frame_req_stream')) if val(d, 'frame_req_valid') else None
            if self.frame_held is not None:
                assert request == self.frame_held, 'Credit request changed under stall'
            self.frame_held = request if request is not None and not val(d, 'frame_req_ready') else None
            if request is not None:
                assert self.job_reference is not None and self.raw_buffered and self.metadata_acks == 5
                assert val(self.response, 'rpc_result_valid') and val(self.response, 'rpc_status') == 0
                assert request == (self.job_reference['maxima'][self.job_grants], self.binding['user'], self.binding['stream'])
                if val(d, 'frame_req_ready'):
                    assert val(d, 'frame_grant_bytes') == self.job_reference['grants'][self.job_grants]
                    self.job_grants += 1; self.total_grants += 1
                else:
                    self.credit_stalls += 1
            valid = val(d, 'm_axis_tx_tvalid')
            snapshot = tuple(val(d, 'm_axis_tx_' + suffix) for suffix in ('tdata', 'tkeep', 'tlast', 'tuser')) if valid else None
            if self.tx_held is not None:
                assert snapshot == self.tx_held, 'Network DATA changed under stall'
            self.tx_held = snapshot if valid and not val(d, 'm_axis_tx_tready') else None
            if valid:
                assert self.job_reference is not None and val(d, 'directory_lease_active') and self.metadata_acks == 5
                assert snapshot[3] == self.binding['user'], 'Network output lost connection context'
                if not val(d, 'm_axis_tx_tready'):
                    self.tx_stalls += 1
                else:
                    data, keep, last, _ = snapshot
                    assert keep and keep & (keep + 1) == 0 and (last or keep.bit_count() == 64)
                    self.wire_packet.extend(data.to_bytes(64, 'little')[:keep.bit_count()])
                    if last:
                        expected = bytes.fromhex(self.job_reference['frames'][self.job_frames])
                        assert bytes(self.wire_packet) == expected, ('Native wire frame differs', self.cases, self.job_frames)
                        self.record.extend(self.wire_packet[9:]); self.job_wire_bytes += len(self.wire_packet)
                        self.wire_packet.clear(); self.job_frames += 1; self.total_frames += 1
                        if self.job_frames == len(self.job_reference['frames']):
                            body = bytes.fromhex(self.job_reference['body'])
                            if self.job_reference['complete']:
                                assert self.record == b'\x00' + struct.pack('>I', len(body)) + body
                            self.tx.extend(body); self.tx_last = True
            self.bow_held = self.stream(d.inverse.bow, 'm_egress_', 16, self.bow_held, True)
            self.lease_clocks += val(d, 'directory_lease_active')
            self.observe_control()
            directory = tuple(val(d, name) for name in ('directory_status', 'directory_address', 'directory_application',
                'directory_generation', 'directory_protobuf', 'directory_unsupported_encoding')) if val(d, 'directory_result_valid') else None
            if self.directory_held is not None:
                assert directory == self.directory_held, 'Real LOAD changed before public retirement'
            self.directory_held = directory if directory is not None and not val(d, 'directory_result_ready') else None
            result = tuple(val(d, name) for name in (*RESULTS, *extra)) if val(d, 'result_valid') else None
            if self.result_held is not None:
                assert result == self.result_held
            self.result_held = result if result is not None and not val(d, 'result_ready') else None
            if result is not None:
                self.progress_at_result = bool(val(d, 'result_progress_committed'))
                assert val(d, 'result_wire_bytes') == self.job_wire_bytes and val(d, 'result_frames') == self.job_frames
                self.observe_result_quiescence()
            if self.result_held:
                self.result_stalls += 1
                assert not val(d, 's_axis_tokens_tready') and not val(d, 'directory_result_ready')
                if val(self.response, 'directory_requested'):
                    assert val(d, 'directory_lease_active') and val(d, 'directory_result_valid')

    def observe_control(self):
        if self.probe_control and val(self.d, 'host_valid'):
            assert not val(self.d, 'host_ready') and not val(self.d, 'store_ready')
            self.blocked_control_cycles += 1

    def observe_result_quiescence(self):
        assert val(self.d, 'fabric_idle') and not self.wire_packet


async def exercise_framed_fixture(d, bench_factory=FramedBench):
    bench = await exercise_rpc_fixture(d, bench_factory)
    generation = 90000

    async def fresh(mode=1):
        nonlocal generation
        generation += 1
        await bench.fenced_reset()
        binding = dict(slot=0, user=2, stream=1, generation=generation, application=777,
                       format=mode, field=17, protobuf=int(mode == 2))
        await bench.open(binding)
        return binding

    for case in bench.frame_oracle['capacity_cases']:
        binding = await fresh(case['mode'])
        chunk = dict(case, eos=1, ordinal=0)
        await bench.run(binding, chunk)
        binding = await fresh(case['mode'])
        await bench.run(binding, dict(token=bench.ref['capacity_tokens'][1], eos=1, ordinal=0, decoded_bytes=0),
                        error=(10, 1, 0), bow=bytes(16385))
    for fault in ('zero_grant', 'late_zero_grant', 'bad_max'):
        binding = await fresh()
        await bench.run(binding, framing_fault=fault)
        # Ordinal advancement is durable, so a failed network transaction
        # quarantines this binding even if it emitted no DATA bytes.
        word = await bench.program(bench.a['progress_base'] + 16)
        assert word & 0xffffffff == 1
    assert bench.memory.data[:bench.a['work_floor']] == (Path(os.environ['PARSER_RPC_RESPONSE_FIXTURES']) / 'memory.bin').read_bytes()[:bench.a['work_floor']]
    baseline = json.loads(Path('acceptance.json').read_text())
    report = dict(baseline)
    report.update(phase='passed', cases=bench.cases, successes=bench.successes, rejections=bench.rejections,
        baseline_rpc_matrix=baseline, injected_faults=bench.faults, fenced_global_resets=bench.resets,
        commands=bench.commands, writes=bench.writes, clock_cycles=bench.clocks,
        tx_stall_cycles=bench.tx_stalls, bow_stall_cycles=bench.bow_stalls, result_stall_cycles=bench.result_stalls,
        directory_lease_cycles=bench.lease_clocks, blocked_control_cycles=bench.blocked_control_cycles,
        axi_line_refills=bench.memory.reads, axi_writes=bench.memory.writes,
        framed_wire_frames=bench.total_frames, frame_grants=bench.total_grants, credit_stall_cycles=bench.credit_stalls,
        pre_grant_buffer_reset_cycles=bench.buffer_resets, complete_model_prefix_immutable=True,
        directory_held_through_public_ack_verified=True, durable_progress_before_wire_verified=True,
        original_populated_vocabulary_preserved=True, network_connection_context_verified=True,
        separate_parser_and_inverse_instances_verified=True, transport_quarantine_cases=3,
        capacity_cases=4, full_transport_verified=False, full_system_verified=False)
    Path('acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    return bench


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def bound_tokens_to_credit_granted_data_and_retirement(d):
    await exercise_framed_fixture(d)
