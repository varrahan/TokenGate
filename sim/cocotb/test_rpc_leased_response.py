"""Concurrent directory progress while an actual framed response holds a lease."""
import json
from pathlib import Path

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from test_rpc_grpc_response import FramedBench, exercise_framed_fixture
from test_rpc_response import val
from test_tokenizer_mmio import cycles


class LeasedBench(FramedBench):
    def __init__(self, d, reference, memory):
        super().__init__(d, reference, memory, response=d.dut.response)
        self.pause_credits = False; self.probed = set(); self.probe_finished = False
        self.control_snapshot = None; self.cached_snapshot = None; self.last_control = None
        self.control_transactions = self.zero_credit_transactions = self.held_result_transactions = 0
        self.busy_responses = self.backend_idle_with_lease = self.post_ack_closes = 0
        self.busy_details = {}; self.same_binding_saves = 0

    async def ready(self):
        while True:
            await FallingEdge(self.d.clk)
            d = self.d
            d.m_axis_tx_tready.value = not val(d, 'rst') and self.clocks % 31 >= 9 and self.rng.randrange(4) != 0
            d.frame_req_ready.value = not val(d, 'rst') and not self.pause_credits and self.clocks % 29 >= 11 and self.rng.randrange(4) == 0
            grants = self.job_reference['grants'] if self.job_reference else []
            d.frame_grant_bytes.value = grants[self.job_grants] if self.job_grants < len(grants) else 0

    async def fenced_reset(self):
        self.cached_snapshot = self.control_snapshot = None
        await super().fenced_reset()

    async def run(self, binding, chunk=None, **kwargs):
        probing = self.probe_control
        self.result_hold_cycles = 2000 if probing else 9
        if probing:
            self.pause_credits = True; self.probe_finished = False
        await super().run(binding, chunk, **kwargs)
        if probing:
            assert self.probe_finished and not self.pause_credits
            await self.control(3, binding, require_lease=False)
            self.post_ack_closes += 1

    def observe_result_quiescence(self):
        # Directory/control work is independent of a held return result.
        assert not self.wire_packet
        assert (val(self.d, 'all_valid') | val(self.d, 'all_rsp_valid')) & 3 == 0

    def observe_control(self):
        d, service = self.d, self.d.dut.directory_service
        if val(d, 'host_valid') and val(d, 'host_ready'):
            self.last_control = {name: val(d, 'host_' + name) for name in
                ('op', 'address', 'user', 'stream', 'generation', 'pool_base', 'pool_bytes')}
        names = ('host_status', 'host_detail', 'host_memory_status', 'host_result_op', 'host_result_address',
            'host_result_user', 'host_result_application', 'host_result_stream', 'host_result_generation',
            'host_result_buffer_base', 'host_result_buffer_bytes', 'host_result_message_limit',
            'host_result_protobuf', 'host_result_encoding', 'host_result_state')
        current = tuple(val(d, name) for name in names) if val(d, 'host_result_valid') else None
        if self.control_snapshot is not None:
            assert current == self.control_snapshot, 'Independent control result changed while stalled'
        self.control_snapshot = current if current is not None and not val(d, 'host_result_ready') else None
        lease_names = ('lease_rsp_status', 'lease_rsp_detail', 'lease_rsp_memory_status', 'lease_rsp_op',
            'lease_rsp_address', 'lease_rsp_buffer_base', 'lease_rsp_buffer_bytes', 'lease_rsp_user',
            'lease_rsp_application', 'lease_rsp_stream', 'lease_rsp_generation', 'lease_rsp_message_limit',
            'lease_rsp_protobuf', 'lease_rsp_unsupported_encoding', 'lease_rsp_state')
        cached = tuple(val(service, name) for name in lease_names) if val(d, 'directory_result_valid') else None
        if self.cached_snapshot is not None:
            assert cached == self.cached_snapshot, 'Cached lease changed during independent control work'
        self.cached_snapshot = cached if cached is not None and not val(d, 'directory_result_ready') else None
        if val(d, 'record_lease_active'):
            self.backend_idle_with_lease += val(service, 'backend_idle')
            address = val(d, 'directory_address')
            if val(d, 'all_valid') & val(d, 'all_ready') & val(d, 'all_write') & 4:
                written = val(d, 'all_addr') >> 46 & 0x7fffff
                if written < address + 128 and written + 8 > address:
                    command = self.last_control
                    assert command is not None and command['op'] == 2, 'Destructive write crossed active record lease'
                    assert (command['address'], command['user'], command['stream'], command['generation']) == (
                        address, val(service, 'lease_rsp_user'), val(service, 'lease_rsp_stream'), val(service, 'lease_rsp_generation'))
                    assert (command['pool_base'], command['pool_bytes']) == (self.a['stream_base'], self.a['stream_bytes'])
                    assert written == address or address + 32 <= written < address + 64, 'SAVE changed immutable binding or sidecar'
        if self.probe_control and val(d, 'host_result_valid') and val(d, 'host_status') == 11:
            self.blocked_control_cycles += 1

    async def control(self, op, binding, *, status=0, detail=None, state=0, pool=None, address=None, require_lease=True):
        d, a = self.d, self.a
        base, count = pool or (a['stream_base'], a['stream_bytes'])
        target = a['stream_base'] + binding['slot'] * 128 if address is None else address
        before_commands = self.commands[2]
        await FallingEdge(d.clk)
        self.set(host_op=op, host_pool_base=base, host_pool_bytes=count, host_user=binding['user'],
            host_application=binding['application'], host_stream=binding['stream'], host_generation=binding['generation'],
            host_address=target, host_buffer_base=a['payload_base'] + binding['slot'] * a['payload_bytes'],
            host_buffer_bytes=a['payload_bytes'], host_message_limit=4096, host_protobuf=binding['protobuf'],
            host_encoding=0, host_maintenance=op in (4, 5), host_state=state, host_result_ready=0, host_valid=1)
        for _ in range(1024):
            await RisingEdge(d.clk)
            if val(d, 'host_ready'):
                break
        else:
            raise AssertionError('Control admission stalled behind cached response')
        await FallingEdge(d.clk); d.host_valid.value = 0
        # Every request must use its accepted snapshot, including conflict checks.
        self.set(host_pool_base=0x7fffff, host_pool_bytes=0, host_op=7, host_user=0xffff,
                 host_stream=0, host_generation=0, host_address=0, host_state=0)
        for _ in range(4096):
            if val(d, 'host_result_valid'):
                break
            await FallingEdge(d.clk)
        else:
            raise AssertionError('Control result stalled behind cached response')
        assert val(d, 'host_status') == status, (op, status, val(d, 'host_status'), val(d, 'host_detail'))
        if detail is not None:
            assert val(d, 'host_detail') == detail
        assert val(d, 'host_result_op') == op and val(d, 'host_result_user') == binding['user']
        if status == 11:
            assert self.commands[2] == before_commands, 'Lease conflict issued backend memory work'
            self.busy_responses += 1
            reason = val(d, 'host_detail'); self.busy_details[str(reason)] = self.busy_details.get(str(reason), 0) + 1
        result = dict(state=val(d, 'host_result_state'), address=val(d, 'host_result_address'),
                      generation=val(d, 'host_result_generation'), stream=val(d, 'host_result_stream'))
        if require_lease:
            assert val(d, 'record_lease_active') and not val(d, 'result_ready')
        if self.pause_credits:
            assert self.job_grants == 0 and not val(d, 'm_axis_tx_tvalid')
            self.zero_credit_transactions += 1
        if val(d, 'result_valid') and not val(d, 'result_ready'):
            self.held_result_transactions += 1
        await cycles(d, 5)
        d.host_result_ready.value = 1; await cycles(d); d.host_result_ready.value = 0
        self.control_transactions += 1
        return result

    async def competing_control(self):
        while True:
            await FallingEdge(self.d.clk)
            if not (self.probe_control and self.binding and self.binding['generation'] not in self.probed):
                continue
            binding = dict(self.binding); self.probed.add(binding['generation'])
            for _ in range(4096):
                if val(self.d, 'record_lease_active') and val(self.d, 'frame_req_valid'):
                    break
                await FallingEdge(self.d.clk)
            else:
                raise AssertionError('Response did not reach a leased zero-credit wait')
            address = self.a['stream_base'] + binding['slot'] * 128
            await self.control(3, binding, status=11, detail=1)
            await self.control(4, binding, status=11, detail=2)
            await self.control(5, binding, status=11, detail=3)
            await self.control(2, dict(binding, generation=binding['generation'] - 1), status=11, detail=4)
            await self.control(0, binding, pool=(address + 8, 128), status=11, detail=5)
            await self.control(1, binding, pool=(self.a['progress_base'], 128), status=11, detail=6)
            saved = 1 | 1 << 32 | 1 << 128
            snapshot_state = val(self.d.dut.directory_service, 'lease_rsp_state')
            await self.control(2, binding, state=saved); self.same_binding_saves += 1
            loaded = await self.control(1, binding)
            assert loaded['state'] == saved and val(self.d.dut.directory_service, 'lease_rsp_state') == snapshot_state
            other = dict(binding, slot=1, user=7, stream=5, generation=binding['generation'] + 100000, application=444)
            await self.control(0, other)
            loaded = await self.control(1, other)
            assert loaded['generation'] == other['generation'] and loaded['address'] == address + 128
            await self.control(2, other, state=2 | 2 << 32 | 1 << 128)
            await self.control(3, other)
            loaded = await self.control(6, binding)
            assert loaded['stream'] == binding['stream']
            assert self.job_grants == 0 and val(self.d, 'record_lease_active')
            self.pause_credits = False
            for _ in range(4096):
                if val(self.d, 'result_valid'):
                    break
                await FallingEdge(self.d.clk)
            else:
                raise AssertionError('Response did not resume after directory progress')
            await self.control(3, binding, status=11, detail=1)
            await self.control(0, other)
            await self.control(3, other)
            assert not val(self.d, 'result_ready') and val(self.d, 'record_lease_active')
            self.probe_finished = True


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def cached_authority_and_directory_progress_under_zero_credit(d):
    bench = await exercise_framed_fixture(d, LeasedBench)
    assert bench.probe_finished and bench.same_binding_saves == bench.post_ack_closes == 1
    assert bench.zero_credit_transactions == 13 and bench.held_result_transactions == 3
    assert bench.busy_responses == 7 and bench.busy_details == {'1': 2, '2': 1, '3': 1, '4': 1, '5': 1, '6': 1}
    assert bench.backend_idle_with_lease > 0
    report = json.loads(Path('acceptance.json').read_text())
    report.update(leased_directory_integrated=True, single_shared_directory_authority_verified=True,
        zero_credit_control_transactions=bench.zero_credit_transactions,
        held_result_control_transactions=bench.held_result_transactions, protected_busy_responses=bench.busy_responses,
        busy_reason_counts=bench.busy_details, same_generation_saves_under_lease=bench.same_binding_saves,
        cached_lease_snapshot_coherent=True, post_retirement_close_allowed=bench.post_ack_closes,
        backend_idle_while_lease_active_cycles=bench.backend_idle_with_lease,
        actual_http2_window_update_ingress_verified=False, complete_raw_application_joined=False)
    Path('acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
