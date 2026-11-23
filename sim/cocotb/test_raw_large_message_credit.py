"""A configured 64 KiB message must not deadlock at the initial H2 window."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_prefill import value
from test_raw_grpc_enveloped import varint
from test_raw_open_rpc_credit import RecordingBench
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


@cocotb.test(timeout_time=40, timeout_unit='ms')
async def configured_large_record_completes_before_waiting_for_dma(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    initial = b''.join(int(word, 16).to_bytes(8, 'little') for word in (folder / 'memory.mem').read_text().splitlines())
    assert len(initial) == 8388608 and hashlib.sha256(initial).hexdigest() == manifest['loaded_image_sha256']
    # Every individual field is within the existing 16 KiB field limit. The
    # complete body meets the actual route's 64 KiB message limit and fits
    # inside its separate 128 KiB allocation. The five-byte gRPC prefix also
    # consumes HTTP/2 DATA credit.
    body = ((varint(99 << 3 | 2) + varint(8000) + b'U' * 8000) * 8 +
        varint(99 << 3 | 2) + varint(1487) + b'U' * 1487 + b'\x0a\x0bhello world')
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    assert len(body) == 65536 < layout[18] == 131072
    image = bytearray(initial)
    memory = SeparateMemory(d, image)
    b = RecordingBench(d, layout, memory, reverse)
    b.completion_wait_limit = 100000 + 16 * len(body)
    b.set(rst=1, fault_client=-1, fault_target=-1, fault_arm=0,
        s_axis_generated_tvalid=0, response_result_ready=0, m_axis_tx_tready=0,
        window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
        maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    for worker in (memory.parser.run(), memory.tokenizer.run(), b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), b.observe_private_credit()):
        cocotb.start_soon(worker)
    await cycles(d, 5)
    b.set(rst=0)
    for prefix in ('queue', 'stream'):
        await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready')
        await b.wait(prefix + '_cfg_result_valid')
        assert value(d, prefix + '_cfg_status') == 0
        await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
    b.response_configuration(0)
    await b.directory(4)
    await b.open()
    await b.packet(0, 1, b.client.data_to_send(), 1)
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    await b.packet(0, 2, b.client.data_to_send(), 1)
    address = b.handles[0, 1]
    message_limit = int.from_bytes(image[address + 24:address + 28], 'little')
    assert len(body) <= message_limit == 65536
    offset = 0
    requests = []
    while offset < len(record):
        if b.client.local_flow_control_window(1) == 0:
            for _ in range(100000):
                await cycles(d)
                if b.client.local_flow_control_window(1) > 0:
                    break
            else:
                progress = int.from_bytes(image[address + 32:address + 64], 'little')
                b.save_wire_evidence()
                Path('requests.json').write_text(json.dumps(requests, indent=2) + '\n')
                failure = dict(phase='starved_before_first_message_completed',
                    configured_message_limit=message_limit, actual_message_body_bytes=len(body), actual_record_bytes=len(record),
                    actual_data_bytes_sent=offset, remaining_record_bytes=len(record) - offset,
                    actual_stream_credit=b.client.local_flow_control_window(1),
                    actual_connection_credit=b.client.outbound_flow_control_window,
                    actual_completed_messages=b.messages, actual_dma_ids=b.ids,
                    actual_generated_descriptors=len(b.generated_accepts),
                    actual_window_update_frames=sum(raw[3] == 8 for raw in b.wire),
                    actual_progress_used=progress & 0xffffffff, actual_progress_message_length=progress >> 64 & 0xffffffff,
                    actual_progress_payload_received=progress >> 96 & 0xffffffff,
                    actual_receive_fault=value(d, 'receive_fault_valid'),
                    full_model_prefixes_immutable=image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]])
                Path('failure.json').write_text(json.dumps(failure, indent=2) + '\n')
                raise AssertionError(('Configured legal gRPC message exhausted receive credit before its DMA descriptor could exist', failure))
        n = min(8192, b.client.local_flow_control_window(1), len(record) - offset)
        end = offset + n == len(record)
        b.client.send_data(1, record[offset:offset + n], end_stream=end)
        raw = b.client.data_to_send()
        requests.append(dict(offset=offset, data_bytes=n, end_stream=end, raw_hex=raw.hex()))
        Path('requests.json').write_text(json.dumps(requests, indent=2) + '\n')
        await b.packet(0, len(requests) + 2, raw, 1)
        offset += n
    await b.drain(0, 1, 101, [15339, 1917])
    captured = list(b.received)
    for ordinal, token in enumerate(captured):
        await b.gpu(1, token, ordinal, int(ordinal + 1 == len(captured)), 2)
    assert ('StreamEnded', 1) in b.client_events
    response = bytearray()
    for chunk in reverse['cases'][0]['chunks']:
        raw = bytes.fromhex(chunk['bow_hex'])
        payload = varint(17 << 3 | 2) + varint(len(raw)) + raw
        response.extend(b'\0' + len(payload).to_bytes(4, 'big') + payload)
    assert bytes(b.response_records[1]) == response
    await b.directory(3, 0, 1)
    expected_connection_capacity = layout[14] // 128 * (layout[18] + 5)
    for _ in range(100000):
        if b.client.outbound_flow_control_window == expected_connection_capacity: break
        await cycles(d)
    else: raise AssertionError('Capacity-backed CLOSE did not restore the full connection budget')
    b.save_wire_evidence()
    Path('requests.json').write_text(json.dumps(requests, indent=2) + '\n')
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed', configured_message_limit=message_limit,
        actual_message_body_bytes=len(body), actual_data_bytes_sent=offset, actual_captured_dma_ids_returned=captured,
        native_complete_grpc_calls=1, explicit_host_close=True,
        actual_gpu_descriptors=b.generated_accepts, response_hex=bytes(b.response_records[1]).hex(),
        response_sha256=hashlib.sha256(response).hexdigest(), final_connection_credit=b.client.outbound_flow_control_window,
        configured_connection_capacity=expected_connection_capacity,
        full_model_prefixes_immutable=image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]],
        full_system_complete=False), indent=2) + '\n')
