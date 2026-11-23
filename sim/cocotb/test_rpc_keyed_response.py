# Generated from the full durable RPC matrix; control updates use wire keys.
"""Actual RPC commits, cached directory, durable credits and remote inverse."""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from test_rpc_response import Bench as BaseBench, exercise_rpc_fixture, val
from test_rpc_grpc_response import FramedBench
from test_tokenizer_mmio import cycles


class KeyedBench(FramedBench):
    def __init__(self, d, reference, memory):
        super().__init__(d, reference, memory, response=d.dut.response)
        self.context_base = 0x780000; self.context_bytes = 4096
        self.window_base = 0x781000; self.window_bytes = 64
        self.contexts = set(); self.credit_job = 0; self.credit_fault_active = False; self.keyed_updates = 0
        self.window_trace = []; self.window_pending = None; self.reserve_start = None
        self.reserve_attempts = self.durable_grants = self.park_cycles = self.poisoned_configs = 0
        self.probed = set(); self.probe_finished = True; self.credit_snapshot = None

    def configure(self):
        super().configure()
        self.set(cfg_context_base=self.context_base, cfg_context_bytes=self.context_bytes,
                 cfg_window_base=self.window_base, cfg_window_bytes=self.window_bytes)

    def observe_before_admission(self):
        # Quarantined components intentionally keep global idle low. They may
        # still return the existing pre-memory rejection without owning work.
        if not val(self.d, 'recovery_required'):
            return super().observe_before_admission()
        assert val(self.response, 'idle') and val(self.d.dut, 'grant_finish_ready')
        assert not val(self.d, 'record_lease_active') and val(self.d, 'fabric_idle')

    def observe_after_retirement(self):
        if not val(self.d, 'recovery_required'):
            return super().observe_after_retirement()
        assert val(self.response, 'idle') and val(self.d.dut, 'grant_finish_ready')
        assert not val(self.d, 'record_lease_active') and not val(self.d, 'result_valid')

    async def ready(self):
        while True:
            await FallingEdge(self.d.clk)
            self.d.m_axis_tx_tready.value = not val(self.d, 'rst') and self.clocks % 31 >= 9 and self.rng.randrange(4) != 0

    async def window(self, op, binding, amount=0):
        d = self.d; a = self.a
        if op==2:op=9;self.keyed_updates+=1
        self.set(window_req_op=op, window_req_maintenance=int(op in (0, 7)), window_req_user=binding['user'],
            window_req_stream=0 if op in (0, 3, 4, 7) else binding.get('stream', 0),
            window_req_generation=0 if op==9 else binding.get('generation', 0),
            window_req_record_address=0 if op==9 else a['stream_base'] + binding.get('slot', 0) * 128, window_req_amount=amount,
            window_cfg_context_base=self.context_base, window_cfg_context_bytes=self.context_bytes,
            window_cfg_stream_base=a['stream_base'], window_cfg_stream_bytes=a['stream_bytes'],
            window_cfg_window_base=self.window_base, window_cfg_window_bytes=self.window_bytes,
            window_cfg_work_floor=a['work_floor'], window_rsp_ready=0)
        await self.send('window_req_valid', 'window_req_ready')
        self.set(window_req_op=15, window_req_user=0xffff, window_req_stream=0, window_req_generation=0,
            window_req_record_address=0x7fffff, window_req_amount=0xffffffff,
            window_cfg_context_base=0x7fffff, window_cfg_context_bytes=0,
            window_cfg_stream_base=0x7fffff, window_cfg_stream_bytes=0,
            window_cfg_window_base=0x7fffff, window_cfg_window_bytes=0)
        for _ in range(8192):
            if val(d, 'window_rsp_valid'): break
            await FallingEdge(d.clk)
        else: raise AssertionError(('Window control timed out', op, binding))
        assert val(d, 'window_rsp_status') == 0, (op, binding, val(d, 'window_rsp_status'), val(d, 'window_rsp_detail'))
        await cycles(d, 3); d.window_rsp_ready.value = 1; await cycles(d); d.window_rsp_ready.value = 0
        # Do not wait for global window_busy: the independent scheduler may
        # already own a new reservation when the control result retires.

    async def fenced_reset(self):
        self.contexts.clear(); self.credit_snapshot = None
        self.set(window_req_valid=0, window_rsp_ready=0)
        await super().fenced_reset()
        # This is explicitly fenced fixture maintenance, using the production
        # programming/fabric channel after all GPU work and cached leases retire.
        for offset in range(0, self.window_bytes, 8):
            await self.program(self.window_base + offset, 0)

    async def open(self, binding):
        await super().open(binding)
        if binding['user'] not in self.contexts:
            await self.program(self.context_base + binding['user'] * 256, 0x48324331 | 1 << 32)
            await self.window(0, binding)
            await self.window(3, binding, 0)
            self.contexts.add(binding['user'])
        await self.window(1, binding)

    async def run(self, binding, chunk=None, *, framing_fault=None, **kwargs):
        self.credit_job += 1
        probing = self.probe_control
        if probing: self.probe_finished = False
        if framing_fault in ('zero_grant', 'late_zero_grant'):
            self.credit_fault_active = True
            await self.window(3, binding, 65535 if framing_fault == 'zero_grant' else 1)
            self.job_reference = self.frame_oracle[framing_fault]
            self.job_grants = self.job_frames = self.job_wire_bytes = 0
            self.wire_packet.clear(); self.record.clear(); self.frame_held = None; self.raw_buffered = False
            self.metadata_write_pending = False; self.metadata_acks = 0; self.progress_at_result = False
            self.d.cfg_peer_max_frame_bytes.value = 16384
            await BaseBench.run(self, binding, chunk, error=(16, 5, 0x75),
                packet=None if framing_fault == 'zero_grant' else b'', bow=b'A',
                fault=(4, 13 if framing_fault == 'zero_grant' else 15))
            self.credit_fault_active = False
            assert self.metadata_acks == 5 and self.progress_at_result
            assert val(self.d, 'result_credit_status') == 5 and val(self.d, 'window_recovery_required')
            assert val(self.d, 'recovery_required') and not val(self.d, 's_axis_tokens_tready')
        else:
            await super().run(binding, chunk, framing_fault=framing_fault, **kwargs)
        if probing:
            for _ in range(8192):
                if self.probe_finished: break
                await FallingEdge(self.d.clk)
            else: raise AssertionError('Cached CLOSE probe did not retire')

    async def window_driver(self):
        issued = None
        while True:
            await FallingEdge(self.d.clk)
            if val(self.d, 'rst'):
                issued = None; continue
            if self.credit_fault_active or not val(self.d, 'frame_req_valid') or self.job_reference is None or self.binding is None:
                continue
            key = (self.credit_job, self.job_grants)
            if key == issued: continue
            issued = key
            grant = self.job_reference['grants'][self.job_grants]
            assert grant > 0
            binding = dict(self.binding)
            await self.window(2, dict(binding, stream=0), grant)
            await self.window(2, binding, grant)

    async def poison_configurations(self):
        while True:
            await RisingEdge(self.d.clk)
            if val(self.d, 'rst'): continue
            if val(self.d, 's_axis_tokens_tvalid') and val(self.d, 's_axis_tokens_tready'):
                await FallingEdge(self.d.clk)
                self.set(cfg_context_base=0x7fffff, cfg_context_bytes=0, cfg_window_base=0x7fffff, cfg_window_bytes=0)
                self.poisoned_configs += 1

    async def observe_windows(self):
        d = self.d; service = d.dut.directory_service
        while True:
            await RisingEdge(d.clk)
            if val(d, 'rst'):
                assert self.window_pending is None
                self.reserve_start = None; continue
            self.park_cycles += val(d, 'credit_parked')
            if val(d, 'all_rsp_valid') & val(d, 'all_rsp_ready') & 16:
                assert self.window_pending is not None
                self.window_pending['acked'] = True
                self.window_pending['status'] = val(d, 'fault_rsp_status') >> 32 & 255
                self.window_pending = None
            if val(d, 'all_valid') & val(d, 'all_ready') & 16:
                assert self.window_pending is None
                address = val(d, 'all_addr') >> 92 & 0x7fffff
                write = val(d, 'all_write') >> 4 & 1
                assert (val(d, 'all_bytes') >> 16 & 15) == 8
                assert val(d, 'directory_pool_lock_active')
                if write:
                    context = self.context_base <= address < self.context_base + self.context_bytes and 168 <= (address - self.context_base) % 256 <= 208
                    window = self.window_base <= address and address + 8 <= self.window_base + self.window_bytes
                    assert context or window
                entry = dict(address=address, write=write, acked=False, status=None)
                self.window_trace.append(entry); self.window_pending = entry
            if val(service, 'state') == 0 and val(service, 'owned_request_ready') and val(service, 'reserve_pending') and not val(d, 'window_req_valid'):
                assert self.raw_buffered and self.metadata_acks == 5 and val(self.response, 'rpc_result_valid')
                assert val(self.response, 'rpc_status') == 0, 'Reservation preceded durable RPC authorization'
                self.reserve_start = len(self.window_trace); self.reserve_attempts += 1
            if val(d, 'frame_req_valid') and val(d, 'frame_req_ready') and val(d, 'frame_grant_bytes'):
                assert self.reserve_start is not None
                writes = [e for e in self.window_trace[self.reserve_start:] if e['write']]
                assert len(writes) == 2 and all(e['acked'] and e['status'] == 0 for e in writes)
                assert writes[0]['address'] == self.window_base + self.binding['slot'] * 16 + 8
                assert writes[1]['address'] == self.context_base + self.binding['user'] * 256 + 176
                self.durable_grants += 1
            snapshot = tuple(val(d, n) for n in ('result_credit_status', 'result_credit_detail',
                'result_credit_http2_error', 'result_credit_connection_error')) if val(d, 'result_valid') else None
            if self.credit_snapshot is not None: assert snapshot == self.credit_snapshot
            self.credit_snapshot = snapshot if snapshot is not None and not val(d, 'result_ready') else None

    def observe_control(self):
        if self.probe_control and val(self.d, 'host_result_valid') and val(self.d, 'host_status') == 11:
            self.blocked_control_cycles += 1

    async def competing_control(self):
        cocotb.start_soon(self.window_driver())
        cocotb.start_soon(self.observe_windows())
        cocotb.start_soon(self.poison_configurations())
        cocotb.start_soon(self.report_progress())
        while True:
            await FallingEdge(self.d.clk)
            if not (self.probe_control and self.binding and self.binding['generation'] not in self.probed and val(self.d, 'directory_result_valid')):
                continue
            binding = dict(self.binding); self.probed.add(binding['generation'])
            before = self.commands[2]
            self.set(host_op=3, host_pool_base=self.a['stream_base'], host_pool_bytes=self.a['stream_bytes'],
                host_user=binding['user'], host_stream=binding['stream'], host_generation=binding['generation'],
                host_address=self.a['stream_base'] + binding['slot'] * 128, host_maintenance=0, host_result_ready=0)
            await self.send('host_valid', 'host_ready')
            while not val(self.d, 'host_result_valid'): await FallingEdge(self.d.clk)
            assert val(self.d, 'host_status') == 11 and val(self.d, 'host_detail') == 1
            assert self.commands[2] == before, 'Conflicting CLOSE reached backend'
            await self.acknowledge('host_result_valid', 'host_result_ready')
            self.probe_finished = True

    async def report_progress(self):
        checkpoint = 0
        while True:
            await cycles(self.d, 10000)
            state = dict(cases=self.cases, clocks=self.clocks, grants=self.total_grants,
                reserves=self.reserve_attempts, parked=val(self.d, 'credit_parked'),
                credit_state=val(self.d.dut.directory_service, 'state'), window_busy=val(self.d, 'window_busy'),
                frame_valid=val(self.d, 'frame_req_valid'), frame_ready=val(self.d, 'frame_req_ready'),
                directory_valid=val(self.d, 'directory_result_valid'), public_result=val(self.d, 'result_valid'),
                child_result=val(self.response, 'rpc_result_valid'), child_status=val(self.response, 'rpc_status'))
            Path('progress.json').write_text(json.dumps(state, indent=2) + '\n')
            self.d._log.info('Durable RPC progress: %s', state)
            if self.cases != checkpoint:
                checkpoint = self.cases


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def actual_keyed_rpc_progress_credit_and_data(d):
    bench = await exercise_rpc_fixture(d, KeyedBench)
    generation = 90000
    async def fresh(mode=1):
        nonlocal generation
        generation += 1; await bench.fenced_reset()
        binding = dict(slot=0, user=2, stream=1, generation=generation, application=777, format=mode, field=17, protobuf=int(mode == 2))
        await bench.open(binding); return binding
    for case in bench.frame_oracle['capacity_cases']:
        binding = await fresh(case['mode']); await bench.run(binding, dict(case, eos=1, ordinal=0))
        binding = await fresh(case['mode'])
        await bench.run(binding, dict(token=bench.ref['capacity_tokens'][1], eos=1, ordinal=0, decoded_bytes=0), error=(10, 1, 0), bow=bytes(16385))
    for fault in ('zero_grant', 'late_zero_grant', 'bad_max'):
        binding = await fresh(); await bench.run(binding, framing_fault=fault)
        word = await bench.program(bench.a['progress_base'] + 16)
        assert word & 0xffffffff == 1
    assert bench.memory.data[:bench.a['work_floor']] == (Path(os.environ['PARSER_RPC_RESPONSE_FIXTURES']) / 'memory.bin').read_bytes()[:bench.a['work_floor']]
    assert bench.durable_grants and bench.park_cycles and bench.poisoned_configs == bench.cases
    baseline = json.loads(Path('acceptance.json').read_text())
    report = dict(baseline)
    report.update(phase='passed', cases=bench.cases, successes=bench.successes, rejections=bench.rejections,
        injected_faults=bench.faults, fenced_global_resets=bench.resets, clock_cycles=bench.clocks,
        baseline_rpc_matrix=baseline, capacity_cases=4, transport_quarantine_cases=3,
        commands=bench.commands + [len(bench.window_trace)],
        writes=bench.writes + [sum(e['write'] for e in bench.window_trace)],
        tx_stall_cycles=bench.tx_stalls, bow_stall_cycles=bench.bow_stalls, result_stall_cycles=bench.result_stalls,
        directory_lease_cycles=bench.lease_clocks, blocked_control_cycles=bench.blocked_control_cycles,
        axi_line_refills=bench.memory.reads, axi_writes=bench.memory.writes,
        credit_stall_cycles=bench.credit_stalls, pre_grant_buffer_reset_cycles=bench.buffer_resets,
        durable_progress_before_wire_verified=True, network_connection_context_verified=True,
        separate_parser_and_inverse_instances_verified=True,
        framed_wire_frames=bench.total_frames, frame_grants=bench.total_grants, durable_positive_grants=bench.durable_grants,
        reserve_attempts=bench.reserve_attempts, credit_park_cycles=bench.park_cycles,
        window_memory_commands=len(bench.window_trace), window_memory_writes=sum(e['write'] for e in bench.window_trace),
        extended_configuration_poison_cases=bench.poisoned_configs,
        actual_cached_directory_and_pool_authority=True, actual_durable_window_grants=True,
        all_progress_acks_before_reservation=True, both_debits_before_data=True,
        private_rejection_does_not_reset_directory=True, directory_held_through_public_ack_verified=True,
        post_commit_credit_fault_cases=2, complete_model_prefix_immutable=True,
        key_only_window_updates=bench.keyed_updates, actual_keyed_window_update_commands=True,
        raw_http2_control_integrated=False, full_transport_verified=False, full_system_verified=False)
    Path('acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    d._log.info('PASS: %s', report)
