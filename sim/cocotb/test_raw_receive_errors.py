"""A connection-fatal frame must terminate without advertising fresh credit."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'native-vendor'))

import cocotb
from cocotb.clock import Clock
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from hyperframe.frame import DataFrame, Frame
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench, varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


@cocotb.test(timeout_time=5, timeout_unit='ms')
async def fatal_padding_error_emits_goaway_without_close_refund(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    image = bytearray(b''.join(int(s, 16).to_bytes(8, 'little') for s in (folder / 'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest() == manifest['loaded_image_sha256']
    initial = bytes(image)
    memory = SeparateMemory(d, image)
    b = Bench(d, layout, memory, reverse)
    native_server = H2Connection(H2Configuration(client_side=False))
    native_server.initiate_connection()
    b.set(rst=1, fault_client=-1, fault_arm=0, s_axis_generated_tvalid=0, response_result_ready=0,
        m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
        maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated()):
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
    preface = b.client.data_to_send()
    native_server.receive_data(preface)
    await b.packet(0, 1, preface, 1)
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    headers = b.client.data_to_send()
    native_server.receive_data(headers)
    await b.packet(0, 2, headers, 1)
    # First DATA starts a real incomplete gRPC record, charged by the receive
    # backend. The next DATA declares one payload byte, all used by Pad Length,
    # whose value 1 leaves a negative content length (RFC 9113 section 6.1).
    b.client.send_data(1, b'\0\0\0\0\x0d\x0a')
    partial = b.client.data_to_send()
    native_server.receive_data(partial)
    padded = DataFrame(1)
    padded.flags.add('PADDED')
    padded.pad_length = 1
    valid = padded.serialize()
    invalid = (1).to_bytes(3, 'big') + valid[3:10]
    assert len(invalid) == 10 and invalid[-1] == 1
    try:
        native_server.receive_data(invalid)
    except ProtocolError as error:
        assert int(error.error_code) == 1
    else:
        raise AssertionError('Independent native HTTP/2 reference accepted invalid DATA padding')
    native_frames = native_server.data_to_send()
    native_goaway = None
    while native_frames:
        frame, size = Frame.parse_frame_header(memoryview(native_frames[:9]))
        frame.parse_body(memoryview(native_frames[9:9 + size]))
        native_frames = native_frames[9 + size:]
        if frame.type == 7:
            native_goaway = (frame.last_stream_id, frame.error_code)
    assert native_goaway == (1, 1)
    before = len(b.wire)
    b.phase = 'connection-fatal padded DATA after partial gRPC record'
    await b.raw_fragment(3, partial + invalid, 1)
    await b.wait('packet_result_valid')
    fields = ('packet_committed', 'packet_status', 'packet_detail', 'transport_packet_http2_error',
              'packet_control_status', 'packet_control_detail', 'packet_control_memory_status')
    result = {n: value(d, n) for n in fields}
    for _ in range(13):
        await cycles(d)
        assert value(d, 'packet_result_valid') and result == {n: value(d, n) for n in fields}
    wire = b.wire[before:]
    observed_goaway = []
    for raw in wire:
        if raw[3] == 7:
            frame, _ = Frame.parse_frame_header(memoryview(raw[:9]))
            frame.parse_body(memoryview(raw[9:]))
            observed_goaway.append((frame.last_stream_id, frame.error_code))
    actual = dict(phase='fatal_receive_error_observed', packet_result=result,
        independent_native_goaway=list(native_goaway), actual_goaway=observed_goaway,
        actual_wire_hex=[raw.hex() for raw in wire], actual_wire_types=[raw[3] for raw in wire],
        actual_receive_trace=b.receive_trace, actual_forward_dma_ids=b.ids,
        actual_receive_connection_available=int.from_bytes(image[0x7e5008:0x7e500c], 'little'),
        actual_receive_connection_pending=int.from_bytes(image[0x7e5010:0x7e5018], 'little'),
        actual_receive_stream_closed=int.from_bytes(image[0x7e6000+(b.handles[0, 1]-layout[13])//4+8:0x7e6000+(b.handles[0, 1]-layout[13])//4+16], 'little') >> 63,
        actual_raw_context_header_hex=image[layout[19]:layout[19]+8].hex(),
        actual_receive_fault=value(d.dut.core, 'receive_fault_valid'),
        actual_receive_recovery_required=value(d.dut.core, 'receive_recovery_required'),
        actual_rpc_header_hex=image[b.handles[0, 1]:b.handles[0, 1] + 8].hex(),
        full_system_complete=False)
    Path('failure.json').write_text(json.dumps(actual, indent=2) + '\n')
    assert result['packet_committed'] == 0 and result['packet_status'] == 4 and result['transport_packet_http2_error'] == 1, actual
    assert all(raw[3] != 8 for raw in wire), 'Connection-fatal cleanup advertised fresh WINDOW_UPDATE'
    assert not b.ids and not b.generated_accepts and not any(b.pending) and not b.packet_bytes
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    await b.ack('packet_result_valid', 'packet_result_ready', 0)
    # An explicit real host OPEN rekeys the closed transport, receive ledger
    # and reused RPC slot. No global reset, fresh arena or memory patch is used.
    old_generation = b.bindings[0, 1]
    b.client = H2Connection(H2Configuration(client_side=True, header_encoding='utf-8'))
    b.client.initiate_connection()
    await b.open()
    await b.packet(0, 4, b.client.data_to_send(), 1)
    reference = json.loads((folder / 'reference_cases.json').read_text())['cases'][0]
    text = bytes.fromhex(reference['prompt_utf8_hex'])
    body = b'\x0a' + varint(len(text)) + text
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    b.client.send_data(1, b'\0' + len(body).to_bytes(4, 'big') + body, end_stream=True)
    await b.packet(0, 5, b.client.data_to_send(), 1)
    assert b.bindings[0, 1] > old_generation
    await b.drain(0, 1, 101, reference['token_ids'])
    captured = list(b.received)
    for ordinal, token in enumerate(captured):
        await b.gpu(1, token, ordinal, int(ordinal + 1 == len(captured)), 2)
    assert ('StreamEnded', 1) in b.client_events
    await b.directory(3, 0, 1)
    assert b.client.outbound_flow_control_window == 65535
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    actual.update(actual_reopen_without_global_reset=True, actual_reused_generation=b.bindings[0, 1],
        actual_reopened_dma_ids_returned=captured, actual_reopened_native_response_hex=bytes(b.response_records[1]).hex(),
        actual_reopened_successful_close_refund=True)
    Path('failure.json').write_text(json.dumps(actual, indent=2) + '\n')
    # Keep the complete protocol acceptance assertion strict while retirement
    # and reopen diagnostics distinguish that remaining transport defect.
    assert observed_goaway == [native_goaway], actual
    actual.update(phase='passed', complete_model_prefix_immutable=True,
        actual_connection_fatal_goaway_without_credit_refund=True,
        full_receive_negative_matrix_verified=False)
    Path('acceptance.json').write_text(json.dumps(actual, indent=2) + '\n')
