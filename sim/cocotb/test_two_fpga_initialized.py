"""Actual raw OPEN/HEADERS, DMA IDs and independently modeled durable grants.

Peer window controls are a typed fixture. The raw WINDOW_UPDATE probe is
applied only after packet commit; production raw-control journaling is pending.
"""
from collections import deque
import importlib.metadata
import struct

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from hyperframe.frame import DataFrame, WindowUpdateFrame
from test_bidirectional_application import JointBench, RESULTS, run_bidirectional
from test_http2_prefill import Bench, value
from test_two_fpga_application import SeparateMemory, separate_memory_acceptance
from test_two_fpga_controlled import ControlledBench
from test_tokenizer_mmio import cycles


WINDOW_BASE = 0x7f0000


class InitializedBench(ControlledBench):
    def __init__(self, *args):
        super().__init__(*args)
        self.windows = self.d.dut.core.reverse.directory_service.owned
        self.connection_credit = {}; self.initial_credit = {}; self.stream_credit = {}
        self.pending_window = None; self.window_write_acks = 0; self.window_write_pending = False
        self.reserved = deque(); self.window_commands = self.positive_grants = self.zero_grants = 0
        self.connection_initializations = self.stream_initializations = self.peer_updates = 0
        self.record_cursor = 0; self.zeroed_first = False; self.raw_probe = False

    def configure(self):
        super().configure(); self.set(cfg_window_base=WINDOW_BASE, cfg_window_bytes=self.layout[14] // 8)

    def poison(self):
        super().poison(); self.set(cfg_window_base=0x7fffff, cfg_window_bytes=0)

    async def opening(self, user):
        await super().opening(user)
        assert self.connection_credit[user] == self.initial_credit[user] == 65535
        assert value(self.d, 'command_window_status') == value(self.d, 'command_window_cleanup_status') == 0
        if user == 0 and not self.zeroed_first:
            await self.window(3, user, amount=0); self.zeroed_first = True

    async def window(self, op, user, stream=0, amount=0):
        a = self.layout
        self.set(window_req_op=op, window_req_maintenance=0, window_req_user=user,
            window_req_stream=stream, window_req_generation=0, window_req_record_address=0, window_req_amount=amount,
            window_cfg_context_base=a[19], window_cfg_context_bytes=a[20],
            window_cfg_stream_base=a[13], window_cfg_stream_bytes=a[14],
            window_cfg_window_base=WINDOW_BASE, window_cfg_window_bytes=a[14] // 8, window_cfg_work_floor=a[6])
        await self.send('window_req_valid', 'window_req_ready'); await self.wait('window_rsp_valid')
        assert value(self.d, 'window_rsp_status') == 0
        await self.ack('window_rsp_valid', 'window_rsp_ready', 4)

    async def response_ready(self):
        while True:
            await FallingEdge(self.d.clk)
            self.d.m_axis_tx_tready.value = not value(self.d, 'rst') and self.clocks % 31 >= 9 and self.response_rng.randrange(4) != 0

    async def send_response(self, reference, chunk, generation, error=(0, 0, 0), **kwargs):
        self.job_reference = {'wire': [], 'grants': []} if error[1] == 0 else None
        self.job_frames = self.job_grants = self.record_cursor = 0
        self.wire_packet.clear(); self.grpc_record.clear(); self.metadata_acks = 0; self.metadata_pending = False
        self.d.cfg_peer_max_frame_bytes.value = 16384
        await JointBench.send_response(self, reference, chunk, generation, error=error, **kwargs)
        if error[1] == 0:
            assert self.job_frames == self.job_grants == len(self.job_reference['wire']) and self.metadata_acks == 5
        else: assert self.job_frames == self.job_grants == 0

    def observe_windows(self):
        w = self.windows; d = self.d
        if value(w, 'window_req_valid') and value(w, 'window_req_ready'):
            assert self.pending_window is None
            self.pending_window = tuple(value(w, 'window_req_' + n) for n in ('op', 'user', 'stream', 'generation', 'record_address', 'amount'))
            self.window_write_acks = 0
        if value(d, 'mem_valid') >> 22 & value(d, 'mem_ready') >> 22 & value(d, 'mem_write') >> 22 & 1:
            assert not self.window_write_pending; self.window_write_pending = True
        if value(d, 'mem_rsp_valid') >> 22 & value(d, 'mem_rsp_ready') >> 22 & 1 and self.window_write_pending:
            assert value(d, 'mem_rsp_status') >> (22 * 8) & 255 == 0
            self.window_write_pending = False; self.window_write_acks += 1
        if not (value(w, 'window_rsp_valid') and value(w, 'window_rsp_ready')): return
        assert self.pending_window is not None
        op, user, stream, generation, address, amount = self.pending_window
        status = value(w, 'window_rsp_status'); grant = value(w, 'window_rsp_grant_bytes')
        assert (value(w, 'window_rsp_op'), value(w, 'window_rsp_user'), value(w, 'window_rsp_stream')) == (op, user, stream)
        assert status in (0, 1), ('Actual window command', self.pending_window, status)
        self.pending_window = None; self.window_commands += 1
        key = user, stream
        if op == 0:
            assert status == 0 and self.window_write_acks == 7
            self.connection_credit[user] = self.initial_credit[user] = 65535
            self.stream_credit = {k: v for k, v in self.stream_credit.items() if k[0] != user}
            self.connection_initializations += 1
        elif op == 1:
            assert status == 0 and self.window_write_acks == 3 and generation > 0
            assert address >= self.layout[13] and (address - self.layout[13]) % 128 == 0
            self.stream_credit[key] = self.initial_credit[user]; self.stream_initializations += 1
        elif op == 3:
            delta = amount - self.initial_credit[user]
            for k in self.stream_credit:
                if k[0] == user: self.stream_credit[k] += delta
            self.initial_credit[user] = amount
        elif op == 9:
            if stream: self.stream_credit[key] += amount
            else: self.connection_credit[user] += amount
            self.peer_updates += 1
        elif op == 5:
            assert self.metadata_acks == 5 and value(d, 'response_result_progress_committed')
            expected = max(0, min(amount, 16384, self.connection_credit[user], self.stream_credit[key]))
            assert grant == expected and status == int(expected == 0), ('Independent credit model', self.pending_window, grant, expected)
            if expected:
                assert self.window_write_acks == 2
                self.connection_credit[user] -= expected; self.stream_credit[key] -= expected
                self.reserved.append(expected); self.positive_grants += 1
            else:
                assert self.window_write_acks == 0; self.zero_grants += 1
        else: raise AssertionError(('Unexpected window op', op))
        assert value(w, 'window_rsp_connection_window') == self.connection_credit[user]
        if stream: assert value(w, 'window_rsp_stream_window') == self.stream_credit[key]
        assert value(w, 'window_rsp_initial_window') == self.initial_credit[user]

    def capture(self, target, prefix, width, held, is_bow=False):
        if is_bow: return JointBench.capture(self, target, prefix, width, held, True)
        valid, ready = value(target, prefix + 'tvalid'), value(target, prefix + 'tready')
        snapshot = tuple(value(target, prefix + n) for n in ('tdata', 'tkeep', 'tlast', 'tuser')) if valid else None
        if held is not None: assert snapshot == held
        if valid:
            assert self.current_response is not None and self.job_reference is not None and self.metadata_acks == 5
            if not ready: self.response_stalls += 1
            else:
                data, keep, last, user = snapshot; expected = self.current_response[4]
                assert user == self.current_response[0]['connection'] and keep == (1 << keep.bit_count()) - 1
                assert last or keep.bit_count() == 64
                self.wire_packet.extend(data >> (8 * lane) & 255 for lane in range(64) if keep >> lane & 1)
                if last:
                    wire = bytes(self.wire_packet)
                    assert wire.hex() == self.job_reference['wire'][self.job_frames]
                    self.grpc_record.extend(wire[9:]); self.wire_packet.clear()
                    self.job_frames += 1; self.total_frames += 1; self.total_wire_bytes += len(wire)
                    if self.record_cursor == len(expected) + 5 and self.job_frames == len(self.job_reference['wire']):
                        assert self.grpc_record == b'\0' + len(expected).to_bytes(4, 'big') + expected
                        self.tx.extend(expected); self.tx_last = True
        return snapshot if valid and not ready else None

    def check_return_owner(self):
        assert bool(value(self.control, 'return_pending')) == self.gpu_owned

    async def response_observer(self):
        cocotb.start_soon(self.flow_observer()); d = self.d; r = d.dut.core.reverse
        while True:
            await RisingEdge(d.clk)
            if value(d, 'rst'): continue
            self.observe_windows()
            self.check_return_owner()
            gpu = value(d, 's_axis_generated_tvalid') and value(d, 's_axis_generated_tready')
            rx = value(d, 's_axis_rx_tvalid') and value(d, 's_axis_rx_tready')
            if self.gpu_owned:
                self.owned_schedule_cycles += 1
                assert not any(value(d, n) for n in ('command_ready', 'stream_cfg_ready', 'queue_cfg_ready', 'cfg_schema_ready'))
                if rx:
                    self.rx_during_return += 1
                    if value(self.control, 'rx_active'): self.continued_rx_beats += 1
            if gpu:
                assert not self.gpu_owned
                if value(self.control, 'rx_active'): self.mid_packet_gpu_admissions += 1
                else: assert not rx
                self.gpu_owned = True
            if value(d, 'response_result_valid') and value(d, 'response_result_ready'): self.gpu_owned = False
            if rx and not value(d, 's_axis_rx_tlast') and (0, 1) in self.jobs: self.mid_packet_available = True
            if value(d, 'm_axis_tokens_tvalid') and value(d, 'm_axis_tokens_tready'):
                data, keep = value(d, 'm_axis_tokens_tdata'), value(d, 'm_axis_tokens_tkeep')
                self.dma_current.extend(data >> (32 * lane) & 0xffffffff for lane in range(16) if keep >> (4 * lane) & 15 == 15)
                if value(d, 'm_axis_tokens_tlast'):
                    self.dma_packets.append((value(d, 'dma_connection'), value(d, 'dma_stream'), value(d, 'dma_generation'), list(self.dma_current)))
                    self.dma_current.clear()
            if gpu and value(d, 'payload_lease_active'): self.early_gpu_admissions += 1
            if value(d, 'payload_lease_active') and value(self.control, 'r_directory_valid'):
                assert not value(self.control, 'r_directory_ready'); self.waited_for_prefill += 1
            self.return_lease_cycles += value(d, 'response_directory_lease_active')
            if value(d, 'mem_valid') >> 20 & value(d, 'mem_ready') >> 20 & 1:
                self.reverse_memory_commands += 1
                if value(d, 'mem_write') >> 20 & 1:
                    assert not self.metadata_pending; self.metadata_pending = True
            if value(d, 'mem_rsp_valid') >> 20 & value(d, 'mem_rsp_ready') >> 20 & 1 and self.metadata_pending:
                assert value(d, 'mem_rsp_status') >> 160 & 255 == 0
                self.metadata_pending = False; self.metadata_acks += 1
            if value(r, 'frame_req_valid') and value(r, 'frame_req_ready'):
                assert self.metadata_acks == 5 and self.reserved
                grant = self.reserved.popleft(); assert value(r, 'frame_grant_bytes') == grant
                body = self.current_response[4]; record = b'\0' + len(body).to_bytes(4, 'big') + body
                frame = DataFrame(self.current_response[0]['stream']); frame.data = record[self.record_cursor:self.record_cursor + grant]
                assert len(frame.data) == grant
                self.record_cursor += grant; self.job_reference['wire'].append(frame.serialize().hex())
                self.job_reference['grants'].append(grant); self.job_grants += 1
            self.credit_stalls += value(d, 'credit_parked')
            self.held_tx = self.capture(d, 'm_axis_tx_', 64, self.held_tx)
            self.held_bow = self.capture(self.return_bow, 'm_egress_', 16, self.held_bow, True)
            snapshot = tuple(value(d, n) for n in RESULTS) if value(d, 'response_result_valid') else None
            if self.held_result is not None: assert snapshot == self.held_result
            self.held_result = snapshot if snapshot is not None and not value(d, 'response_result_ready') else None
            if self.held_result is not None: self.response_held_cycles += 1

    async def directory(self, op, user=0, stream=0):
        if op == 3 and (user, stream) in self.jobs:
            while not self.jobs[user, stream]['done']:
                if value(self.d, 'credit_parked'):
                    reference = self.current_response[0]; owner = reference['connection']; sid = reference['stream']
                    if not self.raw_probe:
                        self.credit_paused = True
                        frames = [WindowUpdateFrame(0), WindowUpdateFrame(sid)]
                        frames[0].window_increment = 101; frames[1].window_increment = 37
                        await Bench.packet(self, owner, 0xf00d, b''.join(f.serialize() for f in frames), 1)
                        self.extra_packets += 1
                        await self.window(9, owner, amount=101); await self.window(9, owner, sid, 37)
                        await self.window(3, owner, amount=65535)
                        self.credit_paused = False; self.raw_probe = True; self.control_probe_complete = True
                    else:
                        await self.window(9, owner, amount=1048576); await self.window(9, owner, sid, 1048576)
                await cycles(self.d)
        await Bench.directory(self, op, user, stream)
        if op == 3: self.stream_credit.pop((user, stream), None)


def acceptance(memory, tested, initial):
    result = separate_memory_acceptance(memory, tested, initial)
    assert tested.raw_probe and tested.zero_grants and tested.positive_grants == tested.total_frames
    assert tested.connection_initializations == tested.opens and tested.stream_initializations > tested.messages
    assert tested.flow_updates == [[0, 0, 101], [0, 1, 37]] and not tested.reserved and tested.pending_window is None
    result.update(parser_memory_clients=14, automatic_connection_windows_verified=True,
        actual_admission_window_initialization_verified=True, independent_credit_model_verified=True,
        durable_debits_before_data_verified=True, response_transport_framing_verified=True,
        connection_initializations=tested.connection_initializations, stream_initializations=tested.stream_initializations,
        window_commands=tested.window_commands, positive_grants=tested.positive_grants, zero_grants=tested.zero_grants,
        peer_window_updates=tested.peer_updates, response_data_frames=tested.total_frames, response_wire_bytes=tested.total_wire_bytes,
        credit_park_cycles=tested.credit_stalls, flow_events=tested.flow_count, raw_update_probe_after_packet_commit=True,
        raw_controls_applied_by_external_fixture=True, full_metadata_window_updates=tested.flow_updates)
    result['hyperframe_version'] = importlib.metadata.version('hyperframe')
    return result


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def raw_open_headers_dma_and_actual_durable_return(d):
    await run_bidirectional(d, bench_factory=InitializedBench, memory_factory=SeparateMemory, extra_result=acceptance)
