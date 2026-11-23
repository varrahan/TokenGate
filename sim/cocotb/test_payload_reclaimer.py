"""Actual reclaimer RTL: byte-exact partial movement and fail-closed ACKs."""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge


async def cycles(d, count=1):
    for _ in range(count):
        await RisingEdge(d.clk)
        await FallingEdge(d.clk)


def v(d, name):
    return int(getattr(d, name).value)


def record(base, capacity, *, used=37, offset=37, ordinal=2, watermark=0,
           prefix=0, length=0, received=0, ended=0, exhausted=0, user=0, stream=1, generation=7):
    progress = (used | offset << 32 | length << 64 | received << 96 | ordinal << 128 |
        prefix << 160 | ended << 163 | exhausted << 164 | watermark << 165)
    value = (0x47525331 | 1 << 32 | 1 << 33 | user << 64 | 101 << 80 | stream << 96 |
        base << 128 | capacity << 160 | capacity << 192 | generation << 224 | progress << 256)
    return value.to_bytes(64, 'little')


class Environment:
    def __init__(self, d, initial, layout):
        self.d = d
        self.initial = initial
        self.layout = layout
        self.rng = random.Random(20261122)
        self.reset_case()

    def set(self, **signals):
        for name, value in signals.items():
            getattr(self.d, name).value = value

    def reset_case(self):
        self.image = bytearray(self.initial)
        self.requests = []
        self.credits = []
        self.credit_memory_counts = []
        self.pending = None
        self.credit_pending = None
        self.lock_due = None
        self.active = False
        self.lock_accepted = False
        self.clock = 0
        self.fault = -1
        self.credit_fault = -1
        self.expected_credit = []
        self.expected_records = {}
        self.unlocks = 0
        self.memory_hold = self.credit_hold = None

    async def run(self):
        d = self.d
        while True:
            await FallingEdge(d.clk)
            resetting = v(d, 'rst')
            due = self.pending is not None and self.clock >= self.pending['due']
            credit_due = self.credit_pending is not None and self.clock >= self.credit_pending['due']
            self.set(mem_ready=int(not resetting and self.pending is None and self.rng.randrange(3) != 0),
                mem_rsp_valid=int(not resetting and due), mem_rsp_data=self.pending['data'] if due else 0,
                mem_rsp_status=self.pending['status'] if due else 0,
                lock_ready=int(not resetting and not self.lock_accepted and self.rng.randrange(3) != 0),
                lock_result_valid=int(not resetting and self.lock_due is not None and self.clock >= self.lock_due),
                lock_status=0, lock_active=int(not resetting and self.active),
                unlock_ready=int(not resetting and self.active and self.rng.randrange(3) != 0),
                credit_ready=int(not resetting and self.credit_pending is None and self.rng.randrange(3) != 0),
                credit_result_valid=int(not resetting and credit_due),
                credit_status=(5 if self.credit_pending['fault'] else 0) if credit_due else 0,
                credit_detail=(0x33 if self.credit_pending['fault'] else 0) if credit_due else 0,
                credit_memory_status=(0x75 if self.credit_pending['fault'] else 0) if credit_due else 0)
            # The real pool exposes active while its successful result waits.
            if not resetting and self.lock_due is not None and self.clock >= self.lock_due:
                self.active = True
                d.lock_active.value = 1
            await RisingEdge(d.clk)
            self.clock += 1
            if v(d, 'rst'):
                assert self.pending is None and self.credit_pending is None
                self.active = self.lock_accepted = False
                self.lock_due = None
                self.memory_hold = self.credit_hold = None
                continue
            if v(d, 'lock_valid') and v(d, 'lock_ready'):
                assert not self.active and not self.lock_accepted
                assert (v(d, 'lock_base'), v(d, 'lock_bytes')) == (self.layout[13], self.layout[14])
                self.lock_accepted = True
                self.lock_due = self.clock + 3
            if v(d, 'lock_result_valid') and v(d, 'lock_result_ready'):
                self.lock_due = None
            if v(d, 'unlock_valid') and v(d, 'unlock_ready'):
                assert self.pending is None and self.credit_pending is None
                self.unlocks += 1
                self.active = False
            if v(d, 'mem_rsp_valid') and v(d, 'mem_rsp_ready'):
                assert self.pending is not None
                self.pending = None
            if v(d, 'credit_result_valid') and v(d, 'credit_result_ready'):
                assert self.credit_pending is not None
                self.credit_pending = None
            current = tuple(v(d, n) for n in ('mem_write', 'mem_addr', 'mem_bytes', 'mem_data')) if v(d, 'mem_valid') else None
            if self.memory_hold is not None:
                assert current == self.memory_hold, 'Held memory command changed'
            self.memory_hold = current if current is not None and not v(d, 'mem_ready') else None
            if current is not None and v(d, 'mem_ready'):
                assert self.active and self.pending is None
                write, address, size, data = current
                assert 1 <= size <= 8 and self.layout[6] <= address < address + size <= 8388608
                pool, pool_bytes, payload, slot = self.layout[13], self.layout[14], self.layout[17], self.layout[18]
                metadata = pool <= address and address + size <= pool + pool_bytes and (address - pool) % 128 + size <= 64
                staging = payload <= address and address + size <= payload + 3 * slot
                assert metadata or staging, ('Memory outside owned pool/payload', current)
                index = len(self.requests)
                self.requests.append(current)
                returned = int.from_bytes(self.image[address:address + size], 'little')
                if write:
                    self.image[address:address + size] = data.to_bytes(9, 'little')[:size]
                self.pending = dict(data=returned, status=0x75 if index == self.fault else 0,
                    due=self.clock + self.rng.randrange(2, 7))
            current = tuple(v(d, n) for n in ('credit_op', 'credit_user', 'credit_stream',
                'credit_generation', 'credit_address', 'credit_amount')) if v(d, 'credit_valid') else None
            if self.credit_hold is not None:
                assert current == self.credit_hold, 'Held credit command changed'
            self.credit_hold = current if current is not None and not v(d, 'credit_ready') else None
            if current is not None and v(d, 'credit_ready'):
                assert self.active and self.pending is None and not v(d, 'memory_owner')
                index = len(self.credits)
                assert current == self.expected_credit[index], ('Credit identity/order', current, self.expected_credit)
                # Metadata is fully committed before even the first RELEASE.
                address = list(self.expected_records)[index // 3]
                assert self.image[address:address + 64] == self.expected_records[address]
                self.credits.append(current)
                self.credit_memory_counts.append(len(self.requests))
                self.credit_pending = dict(fault=index == self.credit_fault, due=self.clock + 4)

    async def reset(self):
        assert self.pending is None and self.credit_pending is None
        self.set(rst=1, start_valid=0, result_ready=0)
        await cycles(self.d, 4)
        self.reset_case()
        self.set(rst=0)
        await cycles(self.d, 2)

    async def execute(self, *, failure=False, configuration=None):
        d = self.d
        configuration_values=dict(cfg_pool_base=self.layout[13], cfg_pool_bytes=self.layout[14],
            cfg_payload_base=self.layout[17], cfg_payload_bytes=3 * self.layout[18],
            cfg_slot_bytes=self.layout[18], cfg_work_floor=self.layout[6], start_valid=1)
        configuration_values.update(configuration or {})
        self.set(**configuration_values)
        while True:
            await RisingEdge(d.clk)
            if v(d, 'start_ready'):
                break
        await FallingEdge(d.clk)
        self.set(start_valid=0, cfg_pool_base=0x7fffff, cfg_pool_bytes=0,
            cfg_payload_base=0x7fffff, cfg_payload_bytes=0, cfg_slot_bytes=0, cfg_work_floor=0x7fffff)
        for _ in range(100000):
            if v(d, 'result_valid'):
                break
            await cycles(d)
        else:
            raise AssertionError(('Reclaim timeout', v(d, 'state'), self.requests[-3:], self.credits))
        result = tuple(v(d, n) for n in ('result_status', 'result_detail', 'result_memory_status', 'recovery_required'))
        assert (result[0] != 0) == failure and bool(result[3]) == failure, result
        for _ in range(9):
            await cycles(d)
            assert v(d, 'result_valid') and tuple(v(d, n) for n in
                ('result_status', 'result_detail', 'result_memory_status', 'recovery_required')) == result
            assert not v(d, 'start_ready') and not v(d, 'idle')
        self.set(result_ready=1)
        await cycles(d)
        self.set(result_ready=0)
        await cycles(d, 3)
        assert self.pending is None and self.credit_pending is None
        assert self.image[:self.layout[6]] == self.initial[:self.layout[6]], 'Protected full-model prefix changed'
        if failure:
            before = len(self.requests), len(self.credits)
            await cycles(d, 23)
            assert before == (len(self.requests), len(self.credits)) and not v(d, 'idle')
            assert self.unlocks == 0 and v(d, 'recovery_required')
        else:
            assert len(self.credits) == len(self.expected_credit) and self.unlocks == 1
            assert v(d, 'idle') and v(d, 'start_ready') and not v(d, 'busy')
        return result

    def setup(self, rows):
        pool, payload, slot = self.layout[13], self.layout[17], self.layout[18]
        self.image[pool:pool + self.layout[14]] = bytes(self.layout[14])
        for i in range(3):
            self.image[pool + 128 * i + 64:pool + 128 * (i + 1)] = bytes([0xA0 + i]) * 64
        for i, options in enumerate(rows):
            address, base = pool + 128 * i, payload + slot * i
            args = dict(options)
            args.setdefault('user', i)
            args.setdefault('stream', i * 2 + 1)
            self.image[address:address + 64] = record(base, slot, **args)
            # Real byte content includes nontrivial unaligned, overlapping moves.
            used = args.get('used', 37)
            self.image[base:base + used] = bytes((j * 43 + i * 19 + 7) & 255 for j in range(used))
            if args.get('ended', 0):
                continue
            count = args.get('ordinal', 2) + args.get('exhausted', 0)
            watermark = args.get('watermark', 0)
            cut = args.get('offset', 37)
            refund = cut + (count - watermark) * 5
            if refund:
                current = int.from_bytes(self.image[address:address + 64], 'little')
                mask = ((1 << 64) - 1) << 256 | ((1 << 33) - 1) << 421
                expected = (current & ~mask | args.get('received', 0) << 256 | count << 421).to_bytes(64, 'little')
                self.expected_records[address] = expected
                user, stream, generation = args['user'], args['stream'], args.get('generation', 7)
                self.expected_credit += [(3, user, stream, generation, address, refund),
                    (4, user, stream, generation, address, 0), (4, user, 0, 0, 0, 0)]


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def full_image_compaction_and_ack_quarantine(d):
    folder = Path(os.environ['RECLAIM_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    metadata = json.loads((folder / 'fixture_manifest.json').read_text())
    initial = b''.join(int(word, 16).to_bytes(8, 'little') for word in (folder / 'memory.mem').read_text().splitlines())
    assert len(initial) == 8388608 and hashlib.sha256(initial).hexdigest() == metadata['loaded_image_sha256']
    environment = Environment(d, initial, layout)
    environment.set(rst=1, start_valid=0, result_ready=0)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(environment.run())
    cases = [[], [dict()], [dict(used=0, offset=0, ordinal=3, watermark=2)],
        [dict(used=0, offset=0, ordinal=0xffffffff, watermark=0xffffffff, exhausted=1)],
        [dict(ended=1)], [dict(), dict(used=0, offset=0, ordinal=1), dict()]]
    for tail in (1, 7, 8, 9, 15, 16, 17, 33):
        for cut in (1, 3, 8, 17):
            cases.append([dict(used=cut + tail, offset=cut, prefix=5, length=tail + 13,
                received=tail, ordinal=3, watermark=1)])
    for prefix in range(1, 5):
        cases.append([dict(prefix=prefix, length=(0, 17, 0x1234, 0x123456)[prefix - 1])])
    accepted = []
    for options in cases:
        await environment.reset()
        environment.setup(options)
        before = bytes(environment.image)
        result = await environment.execute()
        for address, expected in environment.expected_records.items():
            assert environment.image[address:address + 64] == expected
        for i, row in enumerate(options):
            base = layout[17] + i * layout[18]
            cut, tail = row.get('offset', 37), row.get('received', 0)
            if not row.get('ended', 0):
                assert environment.image[base:base + tail] == before[base + cut:base + cut + tail]
        for i in range(3):
            address = layout[13] + 128 * i + 64
            assert environment.image[address:address + 64] == before[address:address + 64]
        accepted.append(dict(rows=options, memory_commands=len(environment.requests), credit_commands=len(environment.credits), result=result))
    fault_row = [dict(used=14, offset=1, prefix=5, length=26, received=13, ordinal=2, watermark=1)]
    await environment.reset()
    environment.setup(fault_row)
    await environment.execute()
    memory_phases = len(environment.requests)
    committed_credit_memory_counts = list(environment.credit_memory_counts)
    fault_results = []
    for phase in range(memory_phases):
        await environment.reset()
        environment.setup(fault_row)
        environment.fault = phase
        result = await environment.execute(failure=True)
        prior_credits = sum(count <= phase for count in committed_credit_memory_counts)
        assert len(environment.requests) == phase + 1
        assert environment.credits == environment.expected_credit[:prior_credits]
        assert result[2] == 0x75
        fault_results.append(dict(phase=phase, result=result, previously_retired_credit_commands=prior_credits))
    for phase in range(3):
        await environment.reset()
        environment.setup(fault_row)
        environment.credit_fault = phase
        result = await environment.execute(failure=True)
        assert len(environment.credits) == phase + 1 and result == (5, 0x33, 0x75, 1)
    corruptions = [
        ('magic', 1), ('stream_zero', -1), ('generation_zero', -2),
        ('payload_alias', -3), ('capacity', -4), ('reserved_state', 1 << (256 + 198)),
        ('watermark_ahead', 3 << (256 + 165)),
    ]
    for name, alteration in corruptions:
        await environment.reset()
        environment.setup([dict()])
        address = layout[13]
        current = int.from_bytes(environment.image[address:address + 64], 'little')
        if alteration >= 0:
            current ^= alteration
        elif alteration == -1:
            current &= ~(((1 << 31) - 1) << 96)
        elif alteration == -2:
            current &= ~(((1 << 32) - 1) << 224)
        elif alteration == -3:
            current ^= 1 << 128
        else:
            current ^= 1 << 160
        environment.image[address:address + 64] = current.to_bytes(64, 'little')
        result = await environment.execute(failure=True)
        assert result[0] == 3 and not environment.credits
        assert not any(request[0] for request in environment.requests)
    await environment.reset()
    environment.setup([dict(used=70000, offset=70000)])
    result = await environment.execute(failure=True)
    assert result[:2] == (3, 1) and not environment.credits
    assert not any(request[0] for request in environment.requests)
    geometries = [dict(cfg_pool_bytes=127), dict(cfg_slot_bytes=0),
        dict(cfg_payload_base=layout[13]), dict(cfg_pool_base=0x7ffff0),
        dict(cfg_work_floor=0x7fffff), dict(cfg_payload_bytes=128)]
    for configuration in geometries:
        await environment.reset()
        environment.setup([])
        result = await environment.execute(failure=True, configuration=configuration)
        assert result[0] == 1 and not environment.requests and not environment.credits
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed', full_image_bytes=len(initial),
        complete_protected_model_prefix_immutable=True, functional_cases=accepted,
        injected_memory_ack_phases=fault_results, injected_credit_ack_phases=3,
        corrupt_record_rejections=[name for name, _ in corruptions] + ['refund_overflow'],
        invalid_geometry_rejections=geometries,
        actual_reclaimer_rtl_executed=True, actual_receive_backend_integrated=False,
        caller_empty_queue_proof_integrated=False, native_vendor_memory=False,
        application_credit_fixed=False, full_system_complete=False), indent=2) + '\n')
