"""Actual record/framing RTL against native hyperframe bytes and credit fences."""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.triggers import Timer


class Bench:
    def __init__(self, dut):
        self.d = dut
        self.rng = random.Random(20261120)
        self.cycles = 0
        self.input_stalls = self.output_stalls = self.credit_stalls = self.result_stalls = 0
        self.grants = self.frames = self.wire_bytes = 0
        self.expected = []
        self.current = bytearray()
        self.granted = []
        self.pending_output = self.pending_credit = None
        self.accepted_outputs = 0
        self.output_enabled = self.credit_enabled = True

    async def tick(self):
        d = self.d
        d.clk.value = 0
        d.m_axis_tx_tready.value = self.output_enabled and self.rng.randrange(5) != 0
        d.frame_req_ready.value = self.credit_enabled and self.rng.randrange(11) == 0
        grant_values = getattr(self, 'case', {}).get('grant_values', [])
        d.frame_grant_bytes.value = grant_values[self.grants] if self.grants < len(grant_values) else 0
        await Timer(2, unit='ns')
        if int(d.rst.value):
            d.clk.value = 1
            await Timer(2, unit='ns')
            self.pending_output = self.pending_credit = None
            return dict(start_ready=0, s_axis_message_tready=0, result_valid=0)
        snapshot = lambda names: tuple(int(getattr(d, n).value) for n in names)
        output_names = ('m_axis_tx_tdata', 'm_axis_tx_tkeep', 'm_axis_tx_tlast', 'm_axis_tx_tuser')
        credit_names = ('frame_req_max_bytes', 'frame_req_user', 'frame_req_stream')
        ov, ready = int(d.m_axis_tx_tvalid.value), int(d.m_axis_tx_tready.value)
        cv, cr = int(d.frame_req_valid.value), int(d.frame_req_ready.value)
        if self.pending_output is not None:
            assert ov and snapshot(output_names) == self.pending_output, 'TX changed while stalled'
        if self.pending_credit is not None:
            assert cv and snapshot(credit_names) == self.pending_credit, 'Credit request changed while stalled'
        self.pending_output = snapshot(output_names) if ov and not ready else None
        self.pending_credit = snapshot(credit_names) if cv and not cr else None
        if ov and not ready:
            self.output_stalls += 1
        if cv and not cr:
            self.credit_stalls += 1
        if int(d.s_axis_message_tvalid.value) and not int(d.s_axis_message_tready.value):
            self.input_stalls += 1
        if cv and cr:
            limit, user, stream = snapshot(credit_names)
            assert self.grants < len(self.case['grant_values'])
            assert (limit, user, stream) == (self.case['request_maxima'][self.grants], self.case['user'], self.case['stream'])
            length = int(d.frame_grant_bytes.value)
            assert length == self.case['grant_values'][self.grants]
            if 0 < length <= limit:
                assert length == len(self.expected[len(self.granted)]) - 9
                self.granted.append(length)
            else:
                assert self.case['status'] == 5 and self.grants + 1 == len(self.case['grant_values'])
            self.grants += 1
        if ov and ready:
            assert len(self.granted) > self.frames, 'DATA emitted before credit reservation'
            data, keep, last, user = snapshot(output_names)
            assert user == self.case['user']
            assert keep != 0 and keep & (keep + 1) == 0, 'Output keep must be packed'
            self.current.extend(data.to_bytes(64, 'little')[:keep.bit_count()])
            self.accepted_outputs += 1
            if last:
                assert bytes(self.current) == self.expected[self.frames], ('Wire frame differs', self.case['index'], self.frames)
                assert len(self.current) == self.granted[self.frames] + 9
                self.wire_bytes += len(self.current)
                self.current.clear()
                self.frames += 1
        values = {n: int(getattr(d, n).value) for n in ('start_ready', 's_axis_message_tready', 'result_valid')}
        d.clk.value = 1
        await Timer(2, unit='ns')
        self.cycles += 1
        return values

    async def send(self, name, fields):
        for key, value in fields.items():
            getattr(self.d, key).value = value
        valid = name + '_tvalid' if name == 's_axis_message' else 'start_valid'
        ready = name + '_tready' if name == 's_axis_message' else 'start_ready'
        getattr(self.d, valid).value = 1
        for _ in range(2000):
            if (await self.tick())[ready]:
                getattr(self.d, valid).value = 0
                return
        raise AssertionError('Input handshake timed out')

    async def run(self, case):
        d = self.d
        self.case = case
        self.expected = [bytes.fromhex(wire) for wire in case['frames']]
        self.grants = self.frames = self.wire_bytes = 0
        self.granted.clear()
        assert not self.current
        await self.send('start', dict(start_user=case['user'], start_stream=case['stream'],
                                     cfg_peer_max_frame_bytes=case['maximum']))
        # Live configuration changes must not alter the captured descriptor.
        d.start_user.value = 0
        d.start_stream.value = 0
        d.cfg_peer_max_frame_bytes.value = 0
        payload = bytes.fromhex(case['payload'])
        chunks = []
        position = 0
        while position < len(payload):
            lanes = sorted(self.rng.sample(range(64), self.rng.randrange(1, 65)))
            chunk = payload[position:position + len(lanes)]
            lanes = lanes[:len(chunk)]
            position += len(chunk)
            value = sum(byte << (8 * lane) for lane, byte in zip(lanes, chunk))
            chunks.append((value, sum(1 << lane for lane in lanes)))
        if not chunks:
            chunks = [(0, 0)]
        accepted_before = self.accepted_outputs
        self.credit_enabled = False
        for index, (value, keep) in enumerate(chunks):
            # Exercise zero-keep nonterminal beats as well as sparse masks.
            if index % 31 == 4:
                await self.send('s_axis_message', dict(s_axis_message_tdata=0, s_axis_message_tkeep=0,
                    s_axis_message_tlast=0, s_axis_message_tuser=case['user'], s_axis_message_abort=0))
            final = index + 1 == len(chunks)
            await self.send('s_axis_message', dict(s_axis_message_tdata=value, s_axis_message_tkeep=keep,
                s_axis_message_tlast=final, s_axis_message_tuser=case['user'] + (final and case['fault'] == 'context'),
                s_axis_message_abort=final and case['fault'] == 'abort'))
        d.s_axis_message_abort.value = 0
        for _ in range(100):
            await self.tick()
        assert self.accepted_outputs == accepted_before, 'Uncommitted/ungranted message emitted bytes'
        self.credit_enabled = True
        for _ in range(1000000):
            if int(d.result_valid.value):
                break
            await self.tick()
        else:
            raise AssertionError(('Framer did not complete', case['index']))
        fields = ('result_status', 'result_user', 'result_stream', 'result_message_bytes',
                  'result_wire_bytes', 'result_frames', 'result_tx_emitted')
        observed = tuple(int(getattr(d, name).value) for name in fields)
        expected_result = (case['status'], case['user'], case['stream'], len(payload) if not case['status'] else 0,
                           self.wire_bytes, len(self.expected), bool(self.expected))
        assert observed == expected_result, (case['index'], observed, expected_result)
        assert self.frames == len(self.expected) and self.grants == len(case['grant_values']) and not self.current
        for _ in range(7):
            await self.tick()
            self.result_stalls += 1
            assert int(d.result_valid.value) and observed == tuple(int(getattr(d, name).value) for name in fields)
            assert not int(d.start_ready.value) and not int(d.s_axis_message_tready.value)
        d.result_ready.value = 1
        await self.tick()
        d.result_ready.value = 0
        await self.tick()
        assert int(d.idle.value)
        return len(self.expected), len(payload) if not case['status'] else 0


@cocotb.test(timeout_time=50, timeout_unit='ms')
async def records_frames_credit_and_transactional_rejection(d):
    folder = Path(os.environ['PARSER_GRPC_FRAME_FIXTURES'])
    fixture = json.loads((folder / 'cases.json').read_text())
    for name in ('rst', 'start_valid', 'result_ready', 's_axis_message_tvalid', 's_axis_message_abort'):
        getattr(d, name).value = int(name == 'rst')
    for name in ('start_user', 'start_stream', 'cfg_peer_max_frame_bytes', 's_axis_message_tdata',
                 's_axis_message_tkeep', 's_axis_message_tlast', 's_axis_message_tuser'):
        getattr(d, name).value = 0
    tested = Bench(d)
    for _ in range(4):
        await tested.tick()
    d.rst.value = 0
    await tested.tick()
    frames = message_bytes = 0
    for case in fixture['cases']:
        count, size = await tested.run(case)
        frames += count
        message_bytes += size
    assert tested.input_stalls and tested.output_stalls and tested.credit_stalls and tested.result_stalls
    result = dict(phase='passed', cases=len(fixture['cases']), valid_cases=fixture['valid_cases'],
        rejected_cases=fixture['invalid_cases'], frames=frames, message_bytes=message_bytes,
        input_stalls=tested.input_stalls, output_stalls=tested.output_stalls,
        credit_stalls=tested.credit_stalls, result_stalls=tested.result_stalls,
        native_reference_sha256=hashlib.sha256((folder / 'cases.json').read_bytes()).hexdigest(),
        full_http2_transport_verified=False, physical_adapters_verified=False)
    Path('acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
