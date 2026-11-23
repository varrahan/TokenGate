"""Real directory LOAD pinning and durable generated-token response progress."""
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
from test_tokenizer_mmio_system import Memory


def val(d, name):
    return int(getattr(d, name).value)


RESULTS = ('result_stage', 'result_status', 'result_memory_status', 'result_bytes',
           'result_tx_emitted', 'result_user', 'result_application', 'result_stream',
           'result_generation', 'result_model_epoch', 'result_schema_epoch', 'result_ordinal', 'result_eos')


class Bench:
    def __init__(self, d, reference, memory):
        self.d = d; self.ref = reference; self.a = reference['layout']; self.memory = memory
        self.rng = random.Random(20261120); self.expected = None; self.binding = None
        self.tx = bytearray(); self.bow = bytearray(); self.tx_last = self.bow_last = False
        self.tx_held = self.bow_held = self.result_held = self.directory_held = None
        self.cases = self.successes = self.rejections = self.faults = self.resets = 0
        self.clocks = self.tx_stalls = self.bow_stalls = self.result_stalls = self.lease_clocks = 0
        self.commands = [0] * 4; self.writes = [0] * 4
        self.blocked_control_cycles = 0; self.probe_control = False
        self.result_hold_cycles = 9

    def set(self, **signals):
        for name, value in signals.items(): getattr(self.d, name).value = value

    def configure(self):
        for name in ('stream_base', 'stream_bytes', 'progress_base', 'progress_bytes', 'work_floor',
                     'model_epoch', 'schema_epoch', 'directory_base', 'directory_bytes', 'pool_base', 'pool_bytes'):
            getattr(self.d, 'cfg_' + name).value = self.a[name]

    async def send(self, valid, ready):
        await FallingEdge(self.d.clk); getattr(self.d, valid).value = 1
        while True:
            await RisingEdge(self.d.clk)
            if val(self.d, ready): break
        await FallingEdge(self.d.clk); getattr(self.d, valid).value = 0

    async def acknowledge(self, valid, ready):
        while not val(self.d, valid): await FallingEdge(self.d.clk)
        await cycles(self.d, 3); getattr(self.d, ready).value = 1
        await cycles(self.d); getattr(self.d, ready).value = 0

    async def host(self, op, binding=None):
        b = binding or dict(user=0, stream=1, generation=0, application=0, protobuf=0, slot=0)
        self.set(host_op=op, host_pool_base=self.a['stream_base'], host_pool_bytes=self.a['stream_bytes'],
                 host_user=b['user'], host_stream=b['stream'], host_generation=b['generation'],
                 host_application=b['application'], host_protobuf=b['protobuf'], host_encoding=b.get('encoding', 0),
                 host_address=self.a['stream_base'] + b['slot'] * 128,
                 host_buffer_base=self.a['payload_base'] + b['slot'] * self.a['payload_bytes'],
                 host_buffer_bytes=self.a['payload_bytes'], host_message_limit=4096, host_maintenance=op == 4)
        await self.send('host_valid', 'host_ready')
        while not val(self.d, 'host_result_valid'): await FallingEdge(self.d.clk)
        assert val(self.d, 'host_status') == 0, ('Directory setup', op, b, val(self.d, 'host_status'))
        if op == 0: assert val(self.d, 'host_result_address') == self.a['stream_base'] + b['slot'] * 128
        await self.acknowledge('host_result_valid', 'host_result_ready')

    async def program(self, address, data=None):
        self.set(program_write=data is not None, program_address=address, program_bytes=8, program_data=data or 0)
        await self.send('program_valid', 'program_ready')
        while not val(self.d, 'program_result_valid'): await FallingEdge(self.d.clk)
        assert val(self.d, 'program_status') == 0
        result = val(self.d, 'program_result_data') & ((1 << 64) - 1)
        await self.acknowledge('program_result_valid', 'program_result_ready')
        return result

    async def open(self, b):
        await self.host(0, b)
        aux = bytearray(64)
        struct.pack_into('<IIII', aux, 0, 0x48325231, b['generation'], 23, 9)
        struct.pack_into('<II', aux, 44, 65535, 65535)
        struct.pack_into('<I', aux, 52, 4 | b['protobuf'] << 4 | b.get('encoding', 0) << 5 | b['application'] << 16)
        address = self.a['stream_base'] + b['slot'] * 128 + 64
        for word in range(8): await self.program(address + word * 8, int.from_bytes(aux[word * 8:word * 8 + 8], 'little'))

    async def fenced_reset(self):
        # All GPU stimulus and TX have retired before the global reset. FORMAT
        # is an explicit maintenance operation; reset is not ordinary recovery.
        assert self.expected is None and not val(self.d, 's_axis_tokens_tvalid')
        self.set(rst=1, fault_enable=0, fault_arm=0, host_valid=0, program_valid=0)
        await cycles(self.d, 5); self.d.rst.value = 0; await cycles(self.d, 3)
        self.tx_held = self.bow_held = self.result_held = self.directory_held = None
        await self.host(4); self.resets += 1

    async def ready(self):
        while True:
            await FallingEdge(self.d.clk)
            self.d.m_axis_tx_tready.value = not val(self.d, 'rst') and self.clocks % 31 >= 9 and self.rng.randrange(4) != 0

    async def competing_control(self):
        while True:
            await FallingEdge(self.d.clk)
            probe = self.probe_control and val(self.d, 'directory_lease_active') and not val(self.d, 'rst')
            if probe:
                self.set(host_valid=1, host_op=3, host_user=self.binding['user'], host_stream=self.binding['stream'],
                         host_generation=self.binding['generation'], host_address=self.a['stream_base'] + self.binding['slot'] * 128)
                assert not val(self.d, 'host_ready') and not val(self.d, 'store_ready')
            elif self.probe_control:
                self.d.host_valid.value = 0

    def stream(self, d, prefix, width, held, bow=False):
        valid = val(d, prefix + 'tvalid'); ready = val(d, prefix + 'tready')
        snapshot = tuple(val(d, prefix + suffix) for suffix in ('tdata', 'tkeep', 'tlast', 'tuser')) if valid else None
        if held is not None: assert snapshot == held, ('Stalled stream changed', prefix)
        if valid:
            assert self.expected is not None and self.binding is not None
            assert val(self.d, 'directory_lease_active'), 'TX/BoW outlived the held directory LOAD'
            expected = self.expected['bow'] if bow else self.expected['packet']
            assert expected is not None, ('Rejected command exposed stream data', prefix, self.expected)
            if not ready:
                if bow: self.bow_stalls += 1
                else: self.tx_stalls += 1
            else:
                data, keep, last, user = snapshot
                assert user == self.binding['application']
                assert keep == (1 << keep.bit_count()) - 1 and (last or keep.bit_count() == width)
                assert not (self.bow_last if bow else self.tx_last)
                sink = self.bow if bow else self.tx
                for lane in range(width):
                    byte = data >> (lane * 8) & 255
                    if keep >> lane & 1: sink.append(byte)
                    else: assert byte == 0
                if last:
                    if bow: self.bow_last = True
                    else: self.tx_last = True
        return snapshot if valid and not ready else None

    async def observe(self):
        d = self.d; a = self.a
        while True:
            await RisingEdge(d.clk)
            if val(d, 'rst'): continue
            self.clocks += 1
            active = val(d, 'all_valid') & val(d, 'all_ready')
            for client in range(4):
                if active >> client & 1:
                    address = val(d, 'all_addr') >> (23 * client) & 0x7fffff
                    count = val(d, 'all_bytes') >> (4 * client) & 15
                    write = val(d, 'all_write') >> client & 1
                    self.commands[client] += 1; self.writes[client] += write
                    assert count == 8
                    if write:
                        assert address >= a['work_floor'], ('Model write', client, address)
                        if client == 0:
                            assert a['progress_base'] <= address and address + 8 <= a['progress_base'] + a['progress_bytes']
                            assert val(d, 'directory_lease_active') and self.tx_last, 'Progress changed before TX retired'
                        elif client == 2:
                            assert a['stream_base'] <= address and address + 8 <= a['stream_base'] + a['stream_bytes']
                            assert (address - a['stream_base']) % 128 < 64
                        else: assert client == 3
                    if client in (0, 1): assert val(d, 'directory_lease_active')
            self.lease_clocks += val(d, 'directory_lease_active')
            if self.probe_control and val(d, 'host_valid'):
                assert not val(d, 'host_ready') and not val(d, 'store_ready'), 'Competing CLOSE escaped the held directory LOAD'
                self.blocked_control_cycles += 1
            self.tx_held = self.stream(d, 'm_axis_tx_', 64, self.tx_held)
            self.bow_held = self.stream(d.dut.response.bow, 'm_egress_', 16, self.bow_held, True)
            directory = tuple(val(d, name) for name in ('directory_status', 'directory_address', 'directory_application', 'directory_generation',
                'directory_protobuf', 'directory_unsupported_encoding')) if val(d, 'directory_result_valid') else None
            if self.directory_held is not None: assert directory == self.directory_held, 'Directory LOAD changed before release'
            self.directory_held = directory if directory is not None and not val(d, 'directory_result_ready') else None
            result = tuple(val(d, name) for name in RESULTS) if val(d, 'result_valid') else None
            if self.result_held is not None: assert result == self.result_held
            self.result_held = result if result is not None and not val(d, 'result_ready') else None
            if self.result_held:
                self.result_stalls += 1
                assert not val(d, 's_axis_tokens_tready') and not val(d, 'directory_lease_active')
            if result is not None: assert val(d, 'fabric_idle')

    async def run(self, b, chunk=None, *, error=(0, 0, 0), packet=None, bow=None,
                  fault=None, patch=None, policy_poison=False, application=None):
        d = self.d
        c = chunk or dict(token=self.ref['ascii_token'], eos=0, ordinal=0, decoded_bytes=1)
        good = error[1] == 0
        if good:
            packet = bytes.fromhex(c.get('packet_hex', self.ref['ascii_packet_hex']))
            bow = bytes.fromhex(c.get('bow_hex', '41'))
        self.expected = dict(error=error, packet=packet, bow=bow)
        self.binding = b; self.tx.clear(); self.bow.clear(); self.tx_last = self.bow_last = False
        await FallingEdge(d.clk); self.observe_before_admission()
        self.configure()
        self.set(s_axis_tokens_tdata=c['token'], s_axis_tokens_tkeep=15, s_axis_tokens_tlast=c['eos'], s_axis_tokens_tuser=b['user'],
                 s_stream=b['stream'], s_generation=b['generation'], s_model_epoch=23, s_schema_epoch=9, s_ordinal=c['ordinal'],
                 cfg_format=b['format'], cfg_protobuf_field=b.get('field', 17), cfg_replace_invalid=1, cfg_strip_special=1)
        if policy_poison: self.set(cfg_format=3, cfg_protobuf_field=0, cfg_replace_invalid=0, cfg_strip_special=0)
        if patch: self.set(**patch)
        self.set(fault_enable=fault is not None, fault_client=fault[0] if fault else 0, fault_target=fault[1] if fault else 0, fault_arm=1)
        await cycles(d); d.fault_arm.value = 0
        await self.send('s_axis_tokens_tvalid', 's_axis_tokens_tready')
        # All live inputs can change after the accepted descriptor.
        self.set(s_axis_tokens_tdata=0xffffffff, s_axis_tokens_tkeep=3, s_stream=0, s_generation=0,
                 cfg_stream_base=0x7fffff, cfg_stream_bytes=0, cfg_progress_base=0x7fffff, cfg_progress_bytes=0,
                 cfg_model_epoch=0xffffffff, cfg_schema_epoch=0xffffffff, cfg_directory_bytes=0, cfg_pool_bytes=0,
                 cfg_format=3, cfg_protobuf_field=0, cfg_replace_invalid=0, cfg_strip_special=0)
        while not val(d, 'result_valid'): await FallingEdge(d.clk)
        actual = tuple(val(d, name) for name in RESULTS)
        wanted_prefix = (*error, c['decoded_bytes'] if good else 0, int(packet is not None))
        assert actual[:5] == wanted_prefix, ('Result', self.cases, b, c, actual, wanted_prefix)
        assert actual[5:] == (b['user'], b['application'] if application is None else application, b['stream'],
                              patch.get('s_generation', b['generation']) if patch else b['generation'],
                              patch.get('s_model_epoch', 23) if patch else 23,
                              patch.get('s_schema_epoch', 9) if patch else 9, c['ordinal'], c['eos']), ('Identity', actual)
        assert bytes(self.tx) == (packet or b'') and self.tx_last == (packet is not None), ('TX', self.cases, self.tx.hex(), packet)
        assert bytes(self.bow) == (bow or b'') and self.bow_last == (bow is not None), ('BoW', self.cases, self.bow.hex(), bow)
        assert val(d, 'fault_injected') == int(fault is not None)
        for _ in range(self.result_hold_cycles):
            await cycles(d); assert val(d, 'result_valid') and tuple(val(d, name) for name in RESULTS) == actual
        d.result_ready.value = 1; await cycles(d); d.result_ready.value = 0
        self.observe_after_retirement()
        self.expected = None; self.binding = None
        self.cases += 1; self.successes += good; self.rejections += not good; self.faults += fault is not None
        if good:
            base = self.a['progress_base'] + b['slot'] * 32
            words = [await self.program(base + i * 8) for i in range(4)]
            wanted = [0x52535031 | b['generation'] << 32, 23 | 9 << 32,
                      c['ordinal'] + 1 | c.get('carry', 0) << 32 | c.get('carry_count', 0) << 56 | c['eos'] << 58,
                      b.get('field', 17) | b['format'] << 29 | 1 << 31 | 1 << 32]
            assert words == wanted, ('Durable carry/ordinal/policy', self.cases, words, wanted)

    def observe_before_admission(self):
        assert val(self.d, 'idle')

    def observe_after_retirement(self):
        assert val(self.d, 'idle') and not val(self.d, 'result_valid')


async def exercise_rpc_fixture(d, bench_factory=Bench):
    folder = Path(os.environ['PARSER_RPC_RESPONSE_FIXTURES'])
    image = (folder / 'memory.bin').read_bytes(); reference = json.loads((folder / 'rpc_cases.json').read_text())
    assert hashlib.sha256(image).hexdigest() == reference['model_image_sha256']
    memory = Memory(d, bytearray(image)); bench = bench_factory(d, reference, memory)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()); cocotb.start_soon(memory.run())
    bench.set(rst=1, s_axis_tokens_tvalid=0, result_ready=0, m_axis_tx_tready=0, host_valid=0, program_valid=0, fault_enable=0)
    await cycles(d, 5); d.rst.value = 0; await cycles(d, 3)
    cocotb.start_soon(bench.ready()); cocotb.start_soon(bench.observe())
    cocotb.start_soon(bench.competing_control())
    for group in reference['groups']:
        await bench.fenced_reset()
        for binding in group: await bench.open(binding)
        positions = [0] * len(group)
        while any(positions[i] < len(b['chunks']) for i, b in enumerate(group)):
            for index, binding in enumerate(group):
                position = positions[index]
                if position < len(binding['chunks']):
                    await bench.run(binding, binding['chunks'][position], policy_poison=position != 0)
                    positions[index] += 1
        for binding in group:
            await bench.run(binding, dict(token=reference['ascii_token'], eos=1, ordinal=len(binding['chunks']), decoded_bytes=1), error=(4, 4, 0))
        d._log.info('Completed bound response format %d', group[0]['format'])

    generation = 10000
    async def fresh(**patch):
        nonlocal generation
        generation += 1
        await bench.fenced_reset()
        binding = dict(slot=0, user=0, stream=1, generation=generation, application=777, format=1, field=17, protobuf=0, **patch)
        await bench.open(binding)
        return binding

    b = await fresh()
    await bench.run(b, error=(3, 1, 0), patch=dict(s_generation=b['generation'] - 1))
    await bench.run(b, error=(3, 3, 0), patch=dict(s_model_epoch=24), application=0)
    await bench.run(b, error=(3, 3, 0), patch=dict(s_schema_epoch=10), application=0)
    await bench.run(b, error=(1, 2, 0), patch=dict(s_axis_tokens_tkeep=3), application=0)
    await bench.run(b, error=(1, 1, 0), patch=dict(cfg_progress_base=bench.a['stream_base']), application=0)
    missing = dict(b, user=2, stream=127)
    await bench.run(missing, error=(2, 3, 0), application=0)
    c = dict(token=reference['ascii_token'], eos=0, ordinal=1, decoded_bytes=1)
    await bench.run(b, c, error=(4, 3, 0))
    await bench.run(b)
    await bench.run(b, error=(4, 3, 0))
    # Malformed sidecar and durable progress never authorize a response.
    base = bench.a['stream_base'] + 64
    word = await bench.program(base); await bench.program(base, word ^ 1)
    await bench.run(b, c, error=(3, 2, 0)); await bench.program(base, word)
    base = bench.a['progress_base']
    word = await bench.program(base); await bench.program(base, word ^ 1)
    await bench.run(b, c, error=(4, 1, 0)); await bench.program(base, word)
    word = await bench.program(base + 8); await bench.program(base + 8, word ^ 1)
    await bench.run(b, c, error=(4, 2, 0)); await bench.program(base + 8, word)
    word = await bench.program(base + 16); await bench.program(base + 16, word | 1 << 63)
    await bench.run(b, c, error=(4, 1, 0)); await bench.program(base + 16, word)
    await bench.run(b, c, policy_poison=True)
    # Persisted Unicode carry is checked by the real downstream decoder.
    word = await bench.program(base + 16)
    await bench.program(base + 16, 2 | 0x41 << 32 | 1 << 56)
    next_chunk = dict(token=reference['ascii_token'], eos=0, ordinal=2, decoded_bytes=1)
    await bench.run(b, next_chunk, error=(9, 2, 0), bow=b'A')
    await bench.program(base + 16, 0xffffffff)
    await bench.run(b, dict(next_chunk, ordinal=0xffffffff), error=(4, 5, 0))
    await bench.program(base + 16, word)
    # A real CLOSE/reopen preserves physical slot reuse while rejecting a
    # delayed GPU descriptor from the previous generation, without global reset.
    old = dict(b)
    await bench.host(3, b)
    b = dict(b, generation=b['generation'] + 50000)
    await bench.open(b)
    await bench.run(old, error=(3, 1, 0))
    bench.probe_control = True
    await bench.run(b)
    bench.probe_control = False
    d.host_valid.value = 0
    assert bench.blocked_control_cycles > 0
    b = await fresh(encoding=1)
    await bench.run(b, error=(3, 4, 0))
    b = await fresh()
    await bench.run(b, error=(3, 5, 0), patch=dict(cfg_format=2))
    await bench.run(b, error=(10, 2, 0), patch=dict(cfg_format=3), bow=b'A')
    await bench.run(b, dict(token=reference['invalid_token'], eos=1, ordinal=0, decoded_bytes=0),
                    error=(9, 1, 0), patch=dict(cfg_replace_invalid=0), bow=b'\xff')

    # Every sidecar/progress read and every post-TX persistence write phase.
    for target in range(17):
        b = await fresh()
        error = (5, 1 if target < 8 else 2 if target < 12 else 3, 0x75)
        escaped = target >= 12
        await bench.run(b, error=error, fault=(0, target),
                        packet=bytes.fromhex(reference['ascii_packet_hex']) if escaped else None,
                        bow=b'A' if escaped else None)
        assert val(d, 'recovery_required')
        expected_address = (bench.a['stream_base'] + 64 + target * 8 if target < 8 else
            bench.a['progress_base'] + (target - 8) * 8 if target < 12 else
            bench.a['progress_base'] + (target - 12) * 8 if target < 16 else bench.a['progress_base'])
        assert val(d, 'recovery_address') == expected_address, ('Exact quarantine address', target)
        counts = list(bench.commands)
        await bench.run(b, error=(1, 3, 0), application=0)
        assert bench.commands == counts, 'Quarantine allowed new memory work'
    for target in (0, 1, 4):
        b = await fresh()
        raw = bytes.fromhex(reference['long_bow_hex'])
        entry = struct.unpack_from('<Q', image, reference['long_token'] * 8)[0]
        offset = (entry >> 16) & 0xffffffff
        prefix = 0 if target <= 1 else 8 - offset % 8 + 8 * (target - 2)
        await bench.run(b, dict(token=reference['long_token'], eos=1, ordinal=0, decoded_bytes=0),
                        error=(8, 4 if target == 0 else 5, 0x75), fault=(1, target), bow=raw[:prefix])
        assert not val(d, 'recovery_required')
    b = await fresh()
    await bench.run(b, error=(2, 2, 0x75), fault=(2, 0), application=0)
    assert val(d, 'store_recovery')
    await bench.run(b, error=(2, 6, 0), application=0)
    await cycles(d, 10)
    assert memory.data[:bench.a['work_floor']] == image[:bench.a['work_floor']], 'Complete model image changed'
    assert bench.tx_stalls and bench.bow_stalls and bench.result_stalls and bench.lease_clocks
    result = dict(phase='passed', cases=bench.cases, successes=bench.successes, rejections=bench.rejections,
                  injected_faults=bench.faults, fenced_global_resets=bench.resets, commands=bench.commands, writes=bench.writes,
                  clock_cycles=bench.clocks, tx_stall_cycles=bench.tx_stalls, bow_stall_cycles=bench.bow_stalls,
                  result_stall_cycles=bench.result_stalls, directory_lease_cycles=bench.lease_clocks,
                  blocked_control_cycles=bench.blocked_control_cycles,
                  axi_line_refills=memory.reads, axi_writes=memory.writes, model_image_sha256=reference['model_image_sha256'],
                  actual_directory_load_verified=True, durable_rpc_carry_verified=True,
                  whole_rpc_gpu_image_lease_verified=False, full_transport_verified=False, full_system_verified=False)
    Path('acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
    d._log.info('PASS: bound generated-token responses: %s', result)
    return bench


@cocotb.test(timeout_time=50, timeout_unit='ms')
async def bound_generated_tokens_and_durable_progress(d):
    await exercise_rpc_fixture(d)
