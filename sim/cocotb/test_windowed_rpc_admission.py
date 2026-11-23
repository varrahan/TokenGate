"""Real HEADERS allocation, sidecar commit and pool-owned INIT_STREAM.

Connection creation and packet commit remain the parent's responsibility. This
test bootstraps the connection through the real typed window interface and
never supplies an invented INIT_STREAM completion to admission.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_tokenizer_mmio import cycles
from test_http2_owned_windows import Bench as Helpers
from test_http2_send_windows import RESULTS


LAYOUT = dict(context_base=0x700003, context_bytes=768, stream_base=0x710007,
    stream_bytes=512, window_base=0x720005, window_bytes=64,
    payload_base=0x760003, payload_bytes=1024, payload_slot_bytes=256,
    work_floor=0x695700, model_epoch=23, schema_epoch=9)
AUTHORITY = ('result_application', 'result_generation', 'result_model_epoch',
    'result_schema_epoch', 'result_address', 'result_buffer_base', 'result_buffer_bytes',
    'result_protobuf', 'result_unsupported_encoding')
PUBLIC = ('result_status', 'result_detail', 'result_memory_status', 'result_control_status',
    'result_cleanup_status', 'result_window_status', 'result_connection_error',
    'result_http2_error', 'result_user', 'result_stream', 'result_trailers', 'result_end_stream') + AUTHORITY


class Memory:
    def __init__(self, d, image):
        self.d = d; self.data = bytearray(image); self.pending = [None] * 3
        self.count = [0] * 3; self.writes = [0] * 3; self.trace = []; self.clock = 0
        self.rng = random.Random(20261125); self.failures = set(); self.fail_close = False
        self.delay_last_aux = False; self.init_requests = []; self.init_completions = []

    async def run(self):
        d = self.d; a = LAYOUT; held = [None] * 3
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert not any(self.pending), 'Reset abandoned a memory command'
                d.mem_ready.value = 0; d.mem_rsp_valid.value = 0
                d.mem_rsp_data.value = 0; d.mem_rsp_status.value = 0
                held = [None] * 3; continue
            ready = valid = data = status = 0
            for client, pending in enumerate(self.pending):
                if pending and pending['delay']: pending['delay'] -= 1
                if pending and not pending['delay']:
                    valid |= 1 << client; data |= pending['data'] << (72 * client)
                    status |= pending['entry']['status'] << (8 * client)
                if pending is None and self.rng.randrange(4): ready |= 1 << client
            d.mem_ready.value = ready; d.mem_rsp_valid.value = valid
            d.mem_rsp_data.value = data; d.mem_rsp_status.value = status
            await RisingEdge(d.clk); self.clock += 1
            locked = int(d.directory_pool_lock_active.value)
            if locked: assert not (int(d.mem_valid.value) & 2), 'Directory memory during exclusive window ownership'
            if int(d.control_valid.value) and int(d.control_ready.value) and int(d.control_op.value) == 3 and self.fail_close:
                self.failures.add((1, self.count[1])); self.fail_close = False
            if int(d.init_valid.value) and int(d.init_ready.value):
                identity = tuple(int(getattr(d, 'init_' + n).value) for n in ('user', 'stream', 'generation', 'record_address'))
                assert identity[0] == 0 and identity[2] > 0
                address = identity[3]
                prior = [e for e in self.trace if e['client'] == 0 and e['write'] and address + 64 <= e['address'] < address + 128]
                assert len(prior) >= 8 and all(e['ack_cycle'] is not None for e in prior[-8:])
                assert struct.unpack_from('<I', self.data, address)[0] == 0x47525331
                self.init_requests.append(dict(identity=identity, cycle=self.clock, trace_start=len(self.trace)))
            if int(d.init_result_valid.value) and int(d.init_result_ready.value):
                self.init_completions.append(dict(cycle=self.clock, status=int(d.init_status.value)))
            for client in range(3):
                if valid >> client & 1 and int(d.mem_rsp_ready.value) >> client & 1:
                    self.pending[client]['entry']['ack_cycle'] = self.clock; self.pending[client] = None
                if int(d.mem_valid.value) >> client & 1:
                    item = (int(d.mem_write.value) >> client & 1,
                        int(d.mem_addr.value) >> (23 * client) & 0x7fffff,
                        int(d.mem_bytes.value) >> (4 * client) & 15,
                        int(d.mem_data.value) >> (72 * client) & ((1 << 72) - 1))
                    if held[client] is not None: assert item == held[client], 'Command changed while stalled'
                    held[client] = item if not (ready >> client & 1) else None
                    if ready >> client & 1:
                        write, address, size, value = item
                        assert self.pending[client] is None and size == 8 and a['work_floor'] <= address and address + 8 <= len(self.data)
                        context = a['context_base'] <= address and address + 8 <= a['context_base'] + a['context_bytes']
                        rpc = a['stream_base'] <= address and address + 8 <= a['stream_base'] + a['stream_bytes']
                        offset = (address - a['stream_base']) % 128
                        if client == 2: assert locked, 'Window access without actual pool ownership'
                        if write:
                            if client == 0: allowed = context and (address - a['context_base']) % 256 == 160 or rpc and 64 <= offset <= 120
                            elif client == 1: allowed = rpc and offset <= 56
                            else: allowed = (context and 168 <= (address - a['context_base']) % 256 <= 208 or
                                a['window_base'] <= address and address + 8 <= a['window_base'] + a['window_bytes'])
                            assert allowed, ('Write ownership', client, hex(address))
                            self.data[address:address + 8] = (value & ((1 << 64) - 1)).to_bytes(8, 'little')
                            self.writes[client] += 1
                        failed = (client, self.count[client]) in self.failures
                        entry = dict(client=client, write=write, address=address, cycle=self.clock,
                            ack_cycle=None, status=(0x75 if client == 2 else 0x76) if failed else 0)
                        self.trace.append(entry); self.count[client] += 1
                        delay = 150 if self.delay_last_aux and client == 0 and write and offset == 120 else self.rng.randrange(3, 13)
                        self.pending[client] = dict(delay=delay, data=int.from_bytes(self.data[address:address + 8], 'little'), entry=entry)
                else: assert held[client] is None, 'Stalled request withdrawn'


class Bench(Helpers):
    def __init__(self, d, m):
        self.d = d; self.m = m; self.a = LAYOUT; self.headers = 0

    def configure(self, patch=None):
        fields = {'cfg_' + n: v for n, v in self.a.items()}; fields.update(patch or {}); self.set(**fields)

    async def host(self, op, address=0):
        self.set(host_req_op=op, host_req_maintenance=int(op in (4, 5)), host_req_user=0,
            host_req_stream=0, host_req_generation=0, host_req_address=address,
            host_req_application=0, host_req_buffer_base=0, host_req_buffer_bytes=0,
            host_req_message_limit=0, host_req_protobuf=0, host_req_unsupported_encoding=0,
            host_req_state=0, host_cfg_pool_base=self.a['stream_base'], host_cfg_pool_bytes=self.a['stream_bytes'])
        await self.send('host_req_valid', 'host_req_ready'); await self.wait('host_rsp_valid')
        assert int(self.d.host_rsp_status.value) == 0, ('Maintenance', op, int(self.d.host_rsp_status.value))
        await self.retire('host_rsp_ready')

    async def window(self, op, stream=0, amount=0, identity=None, retire=True):
        a = self.a; generation, address = identity or (0, 0)
        fields = dict(req_op=op, req_maintenance=int(op in (0, 7)), req_user=0, req_stream=stream,
            req_generation=generation, req_record_address=address, req_amount=amount)
        fields.update({'cfg_' + n: a[n] for n in ('context_base', 'context_bytes', 'stream_base', 'stream_bytes', 'window_base', 'window_bytes', 'work_floor')})
        self.set(**{'window_' + n: v for n, v in fields.items()})
        await self.send('window_req_valid', 'window_req_ready'); await self.wait('window_rsp_valid')
        result = {n: int(getattr(self.d, 'window_' + n).value) for n in RESULTS}
        assert result['rsp_status'] == 0, ('Window', op, stream, result)
        if retire:
            await self.retire('window_rsp_ready')
            while int(self.d.window_busy.value): await cycles(self.d)
        return result

    async def reset_connection(self):
        self.configure(); self.set(reset_user=0, maintenance_grant=1)
        await self.send('reset_valid', 'reset_ready'); await self.wait('result_valid')
        assert int(self.d.result_status.value) == 0 and int(self.d.result_is_reset.value)
        await self.retire('result_ready')

    async def fresh(self):
        await cycles(self.d, 4); assert not any(self.m.pending)
        self.set(rst=1, reset_valid=0, begin_valid=0, candidate_valid=0, context_ready=0,
            result_ready=0, host_req_valid=0, host_rsp_ready=0, window_req_valid=0, window_rsp_ready=0)
        await cycles(self.d, 5)
        a = self.a; first = a['context_base']; end = a['payload_base'] + a['payload_bytes']
        self.m.data[first:end] = bytes(end - first); self.m.failures.clear(); self.m.fail_close = False; self.m.delay_last_aux = False
        for user in range(3):
            base = first + 256 * user
            struct.pack_into('<Q', self.m.data, base, 0x48324331 | 3 << 32 | 16384 << 40)
            struct.pack_into('<Q', self.m.data, base + 80, 0x730003 + 65536 * user | 65536 << 32)
        self.set(rst=0); await cycles(self.d, 2)
        await self.host(4); await self.reset_connection(); await self.window(0)

    async def begin(self, stream, end_stream=False, patch=None):
        self.configure(patch); self.set(begin_user=0, begin_stream=stream, begin_end_stream=int(end_stream), admit_new=1)
        await self.send('begin_valid', 'begin_ready')
        self.set(cfg_context_base=0x7fffff, cfg_context_bytes=0, cfg_stream_base=0x7fffff, cfg_stream_bytes=0,
            cfg_payload_base=0x7fffff, cfg_payload_bytes=0, cfg_window_base=0x7fffff, cfg_window_bytes=0,
            cfg_work_floor=0x7fffff, cfg_model_epoch=999, cfg_schema_epoch=998, begin_user=0xffff, begin_stream=0x7fffffff)
        await self.wait('context_valid')
        assert (int(self.d.context_user.value), int(self.d.context_stream.value)) == (0, stream)
        await self.retire('context_ready')

    async def candidate(self, stream, end_stream=False, admissible=True):
        self.set(candidate_status=0, candidate_http_status=200, candidate_user=0, candidate_stream=stream,
            candidate_end_stream=int(end_stream), candidate_admissible=int(admissible), candidate_application=17,
            candidate_format=0, candidate_identity_encoding=1, candidate_message_limit=256,
            candidate_model_epoch=23, candidate_schema_epoch=9, candidate_route_entry=7,
            candidate_length_valid=0, candidate_content_length=0, candidate_timeout_valid=0,
            candidate_timeout_value=0, candidate_timeout_unit=0)
        await self.send('candidate_valid', 'candidate_ready')
        self.set(candidate_user=0xffff, candidate_stream=0x7fffffff, candidate_model_epoch=999,
            candidate_schema_epoch=998, candidate_application=0xffff, candidate_message_limit=0)

    async def result(self, status=0, detail=None):
        await self.wait('result_valid'); d = self.d
        result = {n: int(getattr(d, n).value) for n in PUBLIC}
        assert result['result_status'] == status, result
        if detail is not None: assert result['result_detail'] == detail, result
        if status: assert all(result[n] == 0 for n in AUTHORITY), 'Failed HEADERS published authority'
        assert not any(self.m.pending), 'Result preceded memory completion'
        for _ in range(11):
            await cycles(d); assert int(d.result_valid.value)
            assert result == {n: int(getattr(d, n).value) for n in PUBLIC}
        await self.retire('result_ready'); self.headers += 1
        return result

    async def header(self, stream, end_stream=False, admissible=True, patch=None, status=0, detail=None):
        await self.begin(stream, end_stream, patch); await self.candidate(stream, end_stream, admissible)
        return await self.result(status, detail)


@cocotb.test(timeout_time=30, timeout_unit='ms')
async def real_admission_waits_for_window_commit_and_recovers_every_phase(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text()); image = (folder / 'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    assert LAYOUT['work_floor'] == reference['layout']['work_floor']
    m = Memory(d, image); b = Bench(d, m); d.rst.value = 1
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()); cocotb.start_soon(m.run())
    await b.fresh(); before = m.count[2]; start = len(m.trace)
    first = await b.header(1); phases = m.count[2] - before
    assert phases == 16 and len(m.init_requests) == 1 and m.init_completions[-1]['status'] == 0
    assert m.init_completions[-1]['cycle'] > max(e['ack_cycle'] for e in m.trace[start:] if e['client'] == 2)
    identity = (first['result_generation'], first['result_address'])
    assert identity == (1, LAYOUT['stream_base']) and first['result_model_epoch'] == 23 and first['result_schema_epoch'] == 9
    assert struct.unpack_from('<4I', m.data, LAYOUT['window_base']) == (0x48325357, 1, 65535, 1)
    await b.window(5, 1, 100, identity)
    before = m.count[2]; requests = len(m.init_requests); trailer = await b.header(1, end_stream=True)
    assert trailer['result_trailers'] == 1 and m.count[2] == before and len(m.init_requests) == requests
    assert struct.unpack_from('<I', m.data, LAYOUT['window_base'] + 8)[0] == 65435
    await b.window(3, amount=16384); second = await b.header(3)
    assert second['result_generation'] == 2 and struct.unpack_from('<I', m.data, LAYOUT['window_base'] + 24)[0] == 16384
    requests = len(m.init_requests); await b.header(5, admissible=False, status=3, detail=4)
    assert len(m.init_requests) == requests

    await b.fresh(); before = list(m.count)
    await b.header(1, patch={'cfg_window_base': LAYOUT['payload_base']}, status=5, detail=1)
    assert m.count == before, 'Aliased window configuration reached actual directory or memory'
    await b.fresh(); struct.pack_into('<Q', m.data, LAYOUT['context_base'] + 80, LAYOUT['window_base'] | 64 << 32)
    requests = len(m.init_requests); await b.header(1, status=5, detail=21)
    assert len(m.init_requests) == requests and int(d.recovery_required.value)

    # The last sidecar write is in flight while an unrelated connection READ
    # takes the real window service. INIT must wait for its held result ACK.
    await b.fresh(); m.delay_last_aux = True; start = len(m.trace)
    header = cocotb.start_soon(b.header(1))
    while not any(e['client'] == 0 and e['write'] and e['address'] == LAYOUT['stream_base'] + 120 for e in m.trace[start:]): await cycles(d)
    await b.window(6, retire=False); await b.wait('init_valid')
    requests = len(m.init_requests)
    for _ in range(23):
        await cycles(d); assert not int(d.result_valid.value) and not int(d.init_ready.value)
        assert len(m.init_requests) == requests
    await b.retire('window_rsp_ready'); await header

    faults = 0
    for phase in range(phases):
        await b.fresh(); m.failures.add((2, m.count[2] + phase)); requests = len(m.init_requests)
        result = await b.header(1, status=5, detail=22)
        assert result['result_window_status'] == 5 and result['result_memory_status'] == 0x75 and result['result_cleanup_status'] == 0
        assert len(m.init_requests) == requests + 1 and int(d.window_recovery_required.value) and int(d.recovery_required.value)
        failed = [e for e in m.trace if e['client'] == 2 and e['status']][-1]
        assert int(d.window_recovery_address.value) == int(d.recovery_address.value) == failed['address']
        assert m.data[LAYOUT['stream_base']:LAYOUT['stream_base'] + 8] == bytes(8), 'Tentative RPC survived rollback'
        counts = list(m.count); await b.header(3, status=5, detail=2)
        assert m.count == counts and len(m.init_requests) == requests + 1
        m.failures.clear(); await b.window(7); await b.reset_connection(); await b.window(0)
        recovered = await b.header(3); assert recovered['result_generation'] == 2
        faults += 1
    await b.fresh(); m.failures.add((2, m.count[2] + 15)); m.fail_close = True
    result = await b.header(1, status=5, detail=11)
    # The actual directory reports read-command failure as status 2; window
    # status 5 and both independent quarantine addresses must remain visible.
    assert result['result_window_status'] == 5 and result['result_cleanup_status'] == 2 and result['result_control_status'] == 2
    assert result['result_memory_status'] == 0x76
    assert int(d.directory_recovery_required.value) and int(d.window_recovery_required.value) and int(d.recovery_required.value)
    m.failures.clear(); await b.host(5, int(d.directory_recovery_address.value))
    await b.window(7); await b.reset_connection(); await b.window(0); await b.header(3)
    await cycles(d, 5); assert not any(m.pending) and int(d.idle.value) and int(d.service_idle.value)
    assert m.data[:LAYOUT['work_floor']] == image[:LAYOUT['work_floor']]
    accepted = dict(phase='passed', header_transactions=b.headers, actual_init_requests=len(m.init_requests),
        init_memory_phases=phases, injected_init_faults=faults, double_fault_rollback_cases=1,
        memory_commands=m.count, memory_writes=m.writes, clock_cycles=m.clock,
        sidecar_and_window_acks_before_authority=True, actual_shared_directory_and_windows=True,
        held_window_result_blocks_admission=True, trailer_preserves_debited_window=True,
        inherited_peer_initial_window_verified=True, configuration_and_candidate_poisoning_verified=True,
        window_and_scratch_alias_rejected=True, failed_init_never_publishes_authority=True,
        actual_rpc_rollback_verified=True, independent_recovery_domains_verified=True,
        unaligned_runtime_pool_bases_verified=True, complete_model_prefix_immutable=True,
        connection_bootstrap_supplied_by_typed_fixture=True, full_forward_application_integrated=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n'); d._log.info('PASS: %s', accepted)
