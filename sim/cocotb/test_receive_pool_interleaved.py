"""Alternate partial gRPC records while RX owns the real directory pool."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from receive_pool_witness import observe_receive_pool, pool_counts
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench, varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


class InterleavedBench(Bench):
    async def drain(self, user, stream, application, expected):
        # The base fixture's first-completion configuration probe requires an
        # empty queue. Here a second real descriptor deliberately stays queued.
        self.phase = f'drain interleaved {user}/{stream}'
        self.received = []
        self.saw_last = False
        self.expected = (user, stream, application, expected)
        self.draining = True
        await self.wait('completion_valid')
        assert self.saw_last and self.received == expected
        fields = ('completion_status', 'completion_detail', 'completion_memory_status', 'completion_token_stage',
            'completion_count', 'completion_user', 'completion_stream', 'completion_application',
            'completion_generation', 'completion_ordinal', 'completion_packet_tag', 'payload_lease_active')
        observed = tuple(value(self.d, n) for n in fields)
        assert observed == (0, 0, 0, 0, len(expected), user, stream, application,
                            self.bindings[user, stream], 0, self.last_tag, 1)
        for _ in range(20):
            await cycles(self.d)
            assert tuple(value(self.d, n) for n in fields) == observed
        self.set(completion_ready=1)
        await cycles(self.d)
        self.set(completion_ready=0)
        self.draining = False
        self.messages += 1
        self.expected = None


@cocotb.test(timeout_time=10, timeout_unit='ms')
async def interleaved_records_hold_actual_directory_ownership(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    reference = json.loads((folder / 'reference_cases.json').read_text())['cases'][0]
    image = bytearray(b''.join(int(s, 16).to_bytes(8, 'little') for s in (folder / 'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest() == manifest['loaded_image_sha256']
    initial = bytes(image)
    memory = SeparateMemory(d, image)
    b = InterleavedBench(d, layout, memory, reverse)
    counts = pool_counts()
    b.set(rst=1, fault_client=-1, fault_arm=0, s_axis_generated_tvalid=0, response_result_ready=0,
          m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
          maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), observe_receive_pool(d, counts)):
        cocotb.start_soon(worker)
    await cycles(d, 5)
    b.set(rst=0)
    for prefix in ('queue', 'stream'):
        await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready')
        await b.wait(prefix + '_cfg_result_valid')
        assert value(d, prefix + '_cfg_status') == 0
        await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
    await b.directory(4)
    await b.open()
    await b.packet(0, 1, b.client.data_to_send(), 1)
    for tag, stream in enumerate((1, 3), 2):
        b.client.send_headers(stream, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
            (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
        await b.packet(0, tag, b.client.data_to_send(), 1)
    text = bytes.fromhex(reference['prompt_utf8_hex'])
    body = b'\x0a' + varint(len(text)) + text
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    # The native peer builds each DATA frame. Every stream switch drives the
    # production deframer's SAVE/LOAD; both complete descriptors share tag 4.
    for index, byte in enumerate(record):
        for stream in (1, 3):
            b.client.send_data(stream, bytes([byte]), end_stream=index + 1 == len(record))
    raw = b.client.data_to_send()
    await b.packet(0, 4, raw, 1)
    assert value(d, 'queued_count') == 2
    returned = []
    expected_response = b''.join(b'\0' + len(packet).to_bytes(4, 'big') + packet
        for chunk in reverse['cases'][0]['chunks']
        for decoded in (bytes.fromhex(chunk['bow_hex']),)
        for packet in (varint(17 << 3 | 2) + varint(len(decoded)) + decoded,))
    async def return_captured(stream, actual):
        for ordinal, token in enumerate(actual):
            await b.gpu(stream, token, ordinal, int(ordinal + 1 == len(actual)), 2)
            returned.append((stream, token, ordinal))
        assert bytes(b.response_records[stream]) == expected_response
        assert ('StreamEnded', stream) in b.client_events

    await b.drain(0, 1, 101, reference['token_ids'])
    # Model independent host queues: a GPU offer may wait behind stream 3's
    # already held prefill lease, while its DMA consumer continues to drain.
    first_return = cocotb.start_soon(return_captured(1, list(b.received)))
    await b.drain(0, 3, 101, reference['token_ids'])
    second_ids = list(b.received)
    await first_return
    await return_captured(3, second_ids)
    for stream in (1, 3):
        await b.directory(3, 0, stream)
    assert counts['save_blocked_cycles'] > 0, 'No real concurrent SAVE was exercised'
    assert counts['receive_grants'] == counts['receive_unlocks'] == len(record) * 2
    assert counts['ordinary_commands'] == len(record) * 2
    assert counts['close_commands'] == 4 and counts['init_commands'] == 3
    assert counts['receive_memory_commands'] == counts['receive_memory_acks']
    assert not any(b.pending) and not b.packet_bytes and not value(d, 'response_recovery_required')
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    assert b.client.outbound_flow_control_window == 65535
    accepted = dict(phase='passed', actual_interleaved_data_frames=len(record) * 2,
        actual_partial_message_streams=[1, 3], actual_forward_dma_ids=b.ids,
        actual_captured_dma_returns=returned, native_complete_grpc_calls=2,
        actual_receive_pool_ownership=counts, actual_successful_closes=2,
        native_response_bytes=expected_response.hex(), parser_memory_clients=len(d.p_mem_valid),
        complete_model_prefix_immutable=True, receive_negative_matrix_verified=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
    d._log.info('PASS: %s', accepted)
