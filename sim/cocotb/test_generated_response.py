"""Real inverse lookup -> BoW -> incremental UTF-8 -> response acceptance.

Native tiktoken/codecs/json/Protobuf fixtures are generated on Windows. The
Linux test owns stimulus and an independent AXI memory BFM, including read
faults. RPC admission and HTTP/2 response framing are outside this component.
"""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_tokenizer_mmio import cycles
from test_tokenizer_mmio_system import Memory


def value(d, name):
    return int(getattr(d, name).value)


COMMAND_PORTS = {
    'user': 'lease_user', 'axis_user': 's_axis_tokens_tuser',
    'application': 'lease_application', 'stream': 'lease_stream',
    'generation': 'lease_generation', 'model_epoch': 'lease_model_epoch',
    'schema_epoch': 'lease_schema_epoch', 'active_epoch': 'cfg_active_model_epoch',
    'lease_valid': 'lease_valid', 'token': 's_axis_tokens_tdata',
    'keep': 's_axis_tokens_tkeep', 'eos': 's_axis_tokens_tlast',
    'replace': 'cfg_replace_invalid', 'strip': 'cfg_strip_special',
    'format': 'cfg_format', 'field': 'cfg_protobuf_field',
    'directory_base': 'cfg_directory_base', 'directory_bytes': 'cfg_directory_bytes',
    'pool_base': 'cfg_pool_base', 'pool_bytes': 'cfg_pool_bytes',
    'carry': 'carry_in', 'carry_count': 'carry_in_count',
}
RESULT_PORTS = ('result_stage', 'result_status', 'result_memory_status',
                'carry_out', 'carry_out_count', 'result_bytes', 'result_user',
                'result_application', 'result_stream', 'result_generation',
                'result_model_epoch', 'result_schema_epoch', 'result_eos')


class Bench:
    def __init__(self, d, memory):
        self.d = d
        self.memory = memory
        self.rng = random.Random(20261120)
        self.case = None
        self.actual_tx = bytearray()
        self.actual_bow = bytearray()
        self.tx_last = self.bow_last = False
        self.tx_held = self.bow_held = self.result_held = None
        self.reads = 0
        self.clocks = self.tx_stalls = self.bow_stalls = self.result_stalls = 0
        self.cases = self.successes = self.rejections = self.faults = 0
        self.tx_bytes = self.bow_bytes = self.logical_reads = 0
        self.carried_sequences = {}

    def set(self, **signals):
        for name, data in signals.items():
            getattr(self.d, name).value = data

    async def ready_driver(self):
        while True:
            await FallingEdge(self.d.clk)
            # Force several held cycles on every packet, as well as random
            # stalls. A failed transaction must never assert TX valid.
            self.d.m_axis_tx_tready.value = (
                not value(self.d, 'rst') and self.clocks % 31 >= 9
                and self.rng.randrange(4) != 0)

    def capture(self, target, prefix, lanes, previous, is_bow=False):
        valid = value(target, prefix + 'tvalid')
        snapshot = tuple(value(target, prefix + suffix)
                         for suffix in ('tdata', 'tkeep', 'tlast', 'tuser')) if valid else None
        if previous is not None:
            assert snapshot == previous, ('Changed stalled stream', prefix, self.case['key'])
        ready = value(target, prefix + 'tready')
        held = snapshot if valid and not ready else None
        if held:
            if is_bow:
                self.bow_stalls += 1
            else:
                self.tx_stalls += 1
        if valid:
            assert self.case is not None, ('Output without an owner', prefix)
            expected = self.case['expected']
            assert is_bow or expected['status'] == 0, ('Failed chunk exposed TX valid', self.case)
            assert not is_bow or expected['bow_hex'] is not None, ('Rejected binding reached BoW', self.case)
            if ready:
                data, keep, last, user = snapshot
                assert user == self.case['command']['application']
                assert keep == (1 << keep.bit_count()) - 1, ('Sparse output', prefix, keep)
                assert keep.bit_count() == lanes or last, ('Partial non-final beat', prefix)
                sink = self.actual_bow if is_bow else self.actual_tx
                assert not (self.bow_last if is_bow else self.tx_last), ('Data after TLAST', prefix)
                for lane in range(lanes):
                    byte = data >> (8 * lane) & 255
                    if keep >> lane & 1:
                        sink.append(byte)
                    else:
                        assert byte == 0, ('Nonzero output padding', prefix, lane)
                if last:
                    if is_bow:
                        self.bow_last = True
                    else:
                        self.tx_last = True
        return held

    async def observe(self):
        d = self.d
        while True:
            await RisingEdge(d.clk)
            if value(d, 'rst'):
                continue
            self.clocks += 1
            assert not value(d, 'm_axi_awvalid') and not value(d, 'm_axi_wvalid'), 'Return lookup wrote model memory'
            if value(d, 'mem_rd_valid') and value(d, 'mem_rd_ready'):
                assert self.case is not None
                command = self.case['command']
                address = value(d, 'mem_rd_addr')
                size = value(d, 'mem_rd_bytes')
                region = 'directory' if self.reads == 0 else 'pool'
                base, capacity = command[region + '_base'], command[region + '_bytes']
                assert size == 8 and base <= address and address + size <= base + capacity, (
                    'Read escaped leased region', self.case['key'], region, address, size)
                self.reads += 1
                self.logical_reads += 1
            self.tx_held = self.capture(d, 'm_axis_tx_', 64, self.tx_held)
            self.bow_held = self.capture(d.dut.bow, 'm_egress_', 16, self.bow_held, True)
            snapshot = tuple(value(d, name) for name in RESULT_PORTS) if value(d, 'result_valid') else None
            if self.result_held is not None:
                assert snapshot == self.result_held, 'Completion changed while held'
            self.result_held = snapshot if snapshot is not None and not value(d, 'result_ready') else None
            if self.result_held is not None:
                self.result_stalls += 1
                assert not value(d, 's_axis_tokens_tready'), 'Accepted a new token before retiring the result'
            if snapshot is not None:
                assert self.case is not None
                expected = self.case['expected']
                assert self.tx_last or expected['status'] != 0, 'Completion preceded final TX acceptance'
                assert value(d, 'fabric_idle'), 'Completion preceded memory response drain'
            if self.clocks % 100000 == 0:
                Path('progress.json').write_text(json.dumps(self.statistics(), indent=2) + '\n')
                d._log.info('Return progress: %d/%d cases, %d logical reads, %d BoW bytes',
                            self.cases, self.cases + 1, self.logical_reads, self.bow_bytes)

    def statistics(self):
        return dict(cases=self.cases, successes=self.successes, rejections=self.rejections,
                    injected_faults=self.faults, logical_reads=self.logical_reads,
                    bow_bytes=self.bow_bytes, response_bytes=self.tx_bytes,
                    clock_cycles=self.clocks, tx_stall_cycles=self.tx_stalls,
                    bow_stall_cycles=self.bow_stalls, result_stall_cycles=self.result_stalls,
                    axi_line_refills=self.memory.reads, axi_writes=self.memory.writes)

    async def run_case(self, case, ordinal):
        d = self.d
        await FallingEdge(d.clk)
        assert value(d, 'idle') and self.case is None
        command, expected = case['command'], case['expected']
        if not case['reset']:
            assert self.carried_sequences[case['key']] == (command['carry'], command['carry_count'])
            command = dict(command)
            command['carry'], command['carry_count'] = self.carried_sequences[case['key']]
        self.case = case
        self.actual_tx.clear()
        self.actual_bow.clear()
        self.tx_last = self.bow_last = False
        self.reads = 0
        self.set(**{port: command[name] for name, port in COMMAND_PORTS.items()})
        self.set(fault_mode=case['fault_mode'], fault_target=case['fault_target'], fault_arm=1)
        await cycles(d)
        d.fault_arm.value = 0
        d.s_axis_tokens_tvalid.value = 1
        while True:
            await RisingEdge(d.clk)
            if value(d, 's_axis_tokens_tready'):
                break
        await FallingEdge(d.clk)
        d.s_axis_tokens_tvalid.value = 0
        # Poison every live binding/configuration input after the handshake.
        # Continuations feed back the actual prior result, checked above.
        for port in COMMAND_PORTS.values():
            handle = getattr(d, port)
            handle.value = (1 << len(handle)) - 1
        while not value(d, 'result_valid'):
            await FallingEdge(d.clk)
        observed = tuple(value(d, name) for name in RESULT_PORTS)
        wanted = (expected['stage'], expected['status'], expected['memory_status'],
                  expected['carry'], expected['carry_count'], expected['decoded_bytes'],
                  command['user'], command['application'], command['stream'],
                  command['generation'], command['model_epoch'], command['schema_epoch'], command['eos'])
        assert observed == wanted, ('Result', ordinal, case, observed, wanted)
        assert bytes(self.actual_tx).hex() == expected['packet_hex'], ('TX bytes', ordinal, case, bytes(self.actual_tx).hex())
        assert self.tx_last == (expected['status'] == 0)
        assert bytes(self.actual_bow).hex() == (expected['bow_hex'] or ''), (
            'BoW bytes', ordinal, case, bytes(self.actual_bow).hex())
        assert self.bow_last == (expected['bow_hex'] is not None), ('Missing BoW end marker', ordinal)
        assert self.reads == expected['logical_reads'], ('Logical reads', ordinal, self.reads, expected['logical_reads'])
        assert value(d, 'fault_injected') == int(case['fault_mode'] != 0), ('Fault did not reach its target', ordinal)
        self.carried_sequences[case['key']] = observed[3:5]
        for _ in range(7 + ordinal % 5):
            await cycles(d)
            assert value(d, 'result_valid') and tuple(value(d, name) for name in RESULT_PORTS) == observed
        d.result_ready.value = 1
        await cycles(d)
        d.result_ready.value = 0
        assert not value(d, 'result_valid') and value(d, 'idle')
        self.cases += 1
        self.successes += expected['status'] == 0
        self.rejections += expected['status'] != 0
        self.faults += case['fault_mode'] != 0
        self.tx_bytes += len(self.actual_tx)
        self.bow_bytes += len(self.actual_bow)
        self.case = None
        if self.cases % 100 == 0:
            d._log.info('Passed %d generated-token response cases', self.cases)


@cocotb.test(timeout_time=50, timeout_unit='ms')
async def generated_tokens_to_application_responses(d):
    folder = Path(os.environ['PARSER_RESPONSE_FIXTURES'])
    image = (folder / 'memory.bin').read_bytes()
    manifest = json.loads((folder / 'model_manifest.json').read_text())
    fixtures = json.loads((folder / 'fixture_manifest.json').read_text())
    assert len(image) == 8 * 1024 * 1024
    assert hashlib.sha256(image).hexdigest() == manifest['image_sha256'] == fixtures['model_image_sha256']
    for region in manifest['regions']:
        if 'sha256' in region:
            assert hashlib.sha256(image[region['base']:region['base'] + region['bytes']]).hexdigest() == region['sha256']
    cases = json.loads((folder / 'cases.json').read_text())
    assert len(cases) == fixtures['cases']
    memory = Memory(d, bytearray(image))
    bench = Bench(d, memory)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    bench.set(rst=1, s_axis_tokens_tvalid=0, result_ready=0, m_axis_tx_tready=0, fault_arm=0, fault_mode=0)
    await cycles(d, 5)
    d.rst.value = 0
    await cycles(d, 3)
    cocotb.start_soon(bench.ready_driver())
    cocotb.start_soon(bench.observe())
    for ordinal, case in enumerate(cases):
        await bench.run_case(case, ordinal)
    await cycles(d, 10)
    assert bytes(memory.data) == image and memory.writes == 0, 'The full vocabulary image changed'
    assert bench.successes == fixtures['successes'] and bench.rejections == fixtures['rejections']
    assert bench.tx_bytes == fixtures['response_bytes']
    assert bench.tx_stalls and bench.bow_stalls and bench.result_stalls
    result = dict(bench.statistics(), phase='passed', model_image_sha256=manifest['image_sha256'],
                  ordinary_entries_verified=fixtures['ordinary_entries_verified'],
                  special_entries_verified=fixtures['special_entries_verified'],
                  full_transport_verified=False, whole_rpc_lease_verified=False,
                  physical_throughput_verified=False)
    Path('acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
    d._log.info('PASS: generated-token response acceptance: %s', result)
