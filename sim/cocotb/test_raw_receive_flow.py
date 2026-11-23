"""A real peer must regain receive credit after discarded padded DATA."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def native_padding_credit_replenishment_allows_next_real_prompt(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    references = json.loads((folder / 'reference_cases.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    image = bytearray(b''.join(int(word, 16).to_bytes(8, 'little') for word in (folder / 'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest() == manifest['loaded_image_sha256']
    initial = bytes(image); memory = SeparateMemory(d, image); b = Bench(d, layout, memory, reverse)
    b.set(rst=1, s_axis_generated_tvalid=0, response_result_ready=0, m_axis_tx_tready=0,
        window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
        maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure(); cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()); cocotb.start_soon(memory.run())
    for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated()): cocotb.start_soon(worker)
    await cycles(d, 5); b.set(rst=0)
    for prefix in ('queue', 'stream'):
        await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready'); await b.wait(prefix + '_cfg_result_valid')
        assert value(d, prefix + '_cfg_status') == 0
        await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
    await b.directory(4); await b.open(); await b.packet(0, 1, b.client.data_to_send(), 1)
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Json'), ('content-type', 'application/grpc+json'), ('te', 'trailers')])
    await b.packet(0, 2, b.client.data_to_send(), 1)
    # Native h2 performs the actual sender's connection and stream debits.
    # 255 * (one Pad Length byte + 255 padding bytes) + 255 = 65535.
    tag = 3; batch = bytearray(); payload_bytes = 0
    for index in range(256):
        padding = 255 if index < 255 else 254
        b.client.send_data(1, b'', pad_length=padding)
        frame = b.client.data_to_send(); assert len(frame) == 10 + padding
        batch.extend(frame); payload_bytes += 1 + padding
        if len(batch) > 12000 or index == 255:
            b.phase = 'native padded DATA consumes receive credit'
            await b.packet(0, tag, bytes(batch), 1); tag += 1; batch.clear()
    assert payload_bytes == 65535 and b.ids == 0 and not b.generated_accepts
    # A receiver can batch updates; allow its actual commit/TX queues to drain.
    # No test callback or direct ledger write replenishes either window.
    for _ in range(100000):
        if b.client.outbound_flow_control_window > 0 and b.client.local_flow_control_window(1) > 0: break
        await RisingEdge(d.clk)
    else:
        failure = dict(phase='receive_credit_starvation', native_padding_payload_bytes=payload_bytes,
            native_connection_credit=b.client.outbound_flow_control_window,
            native_stream_and_connection_credit=b.client.local_flow_control_window(1),
            actual_raw_packets=b.packets, actual_forward_dma_ids=b.ids,
            actual_wire_types=[raw[3] for raw in b.wire],
            actual_window_update_frames=sum(raw[3] == 8 for raw in b.wire),
            no_application_payload_or_gpu_work=True, full_system_complete=False)
        Path('failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        raise AssertionError(failure)
    # Use replenished native credit for a real request and echo actual DMA IDs.
    prompt = bytes.fromhex(references['cases'][0]['prompt_utf8_hex'])
    body = json.dumps({'prompt': prompt.decode()}, separators=(',', ':')).encode()
    b.client.send_data(1, b'\x00' + len(body).to_bytes(4, 'big') + body, end_stream=True)
    await b.packet(0, tag, b.client.data_to_send(), 1)
    ids = references['cases'][0]['token_ids']; await b.drain(0, 1, 100, ids)
    actual = list(b.received); assert actual == ids
    expected = bytearray()
    for ordinal, token in enumerate(actual):
        await b.gpu(1, token, ordinal, int(ordinal + 1 == len(actual)), 0)
        text = bytes.fromhex(reverse['cases'][0]['chunks'][ordinal]['bow_hex']).decode()
        payload = json.dumps({'choices': [{'delta': {'content': text}}]}, ensure_ascii=False, separators=(',', ':')).encode()
        expected.extend(b'\x00' + len(payload).to_bytes(4, 'big') + payload)
    assert bytes(b.response_records[1]) == expected and ('StreamEnded', 1) in b.client_events
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    assert not any(b.pending) and not b.packet_bytes and not value(d, 'response_record_lease_active')
    accepted = dict(phase='passed', native_padding_payload_bytes=payload_bytes,
        native_window_updates_received=True, actual_dma_ids_returned=actual,
        native_complete_grpc_calls=1, complete_model_prefix_immutable=True,
        actual_raw_packets=b.packets, actual_window_update_frames=sum(raw[3] == 8 for raw in b.wire),
        receive_flow_control_negative_matrix_verified=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
