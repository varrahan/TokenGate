"""Independent actual-wire oracle for the complete selected streaming RPCs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import Frame
import tiktoken

from verify_two_fpga_application import closure


def verify(root, name, assembly):
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    launch = read(root / 'build/validation' / (name + '-launch.json'))
    assert launch['phase'] == 'completed' and launch['exit_code'] == 0
    assert launch['candidate'] == 'open-rpc-reclaim' and launch['generation_sha256'] == assembly['generation_sha256']
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + name)
    source = archive / 'execution-sources'
    report = read(archive / 'report.json')
    accepted = read(archive / 'acceptance.json')
    inputs = read(archive / 'inputs.json')
    assert report['phase'] == accepted['phase'] == 'passed' and report['tests'] == 1 and report['failures'] == 0
    assert read(archive / 'snapshot.json')['exit_code'] == 0
    assert inputs == launch['inputs_sha256'] == report['input_sha256']
    assert sha(archive / 'acceptance.json') == report['acceptance_sha256']
    for path, digest in inputs.items():
        assert sha(source / path) == digest, path
    assert {n: sha(p) for n, p in closure('http2_enveloped_parser_application', source).items()} == assembly['executed_parser_sha256']
    original = read(root / 'build/validation/json-simd-corpus.json')
    assert original['key'] == '2509134d2630b47e'
    assert {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', source).items()} == original['executed_tokenizer_sha256']
    assert sha(source / 'tools/run_open_rpc_credit_wsl.py') == launch['driver_sha256']
    for edit in launch['fixture_edits']:
        text = (source / edit['path']).read_bytes().decode()
        for old, new in reversed(edit['replacements']):
            assert text.count(new) == 1
            text = text.replace(new, old)
        assert hashlib.sha256(text.encode()).hexdigest() == edit['old_sha256'] == original['inputs_sha256'][edit['path']]
    for path, digest in original['inputs_sha256'].items():
        if path.startswith('build/bidirectional-fixtures/') or path.startswith('native-vendor/'):
            assert inputs[path] == digest
    xml = ET.parse(archive / 'results.xml')
    cases = xml.findall('.//testcase')
    assert len(cases) == 1 and cases[0].attrib['name'] == 'consumed_messages_replenish_credit_before_rpc_close'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    count, partial = launch['requested_messages'], launch['initial_partial_record_bytes']
    assert (count, partial) in ((9, 0), (21, 128))
    assert accepted['complete_messages_acknowledged'] == accepted['requested_messages'] == count
    assert accepted['initial_partial_record_bytes'] == partial
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    ids = encoding.encode_ordinary('hello world')
    assert ids == [15339, 1917]
    actual_ids = accepted['actual_captured_dma_ids_returned']
    assert actual_ids == ids * count and accepted['actual_gpu_descriptors'] == len(actual_ids)
    body = b'\x9a\x06\xc0\x3e' + b'U' * 8000 + b'\x0a\x0bhello world'
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    assert len(record) == 8022 and accepted['actual_application_data_bytes'] == count * len(record)
    assert accepted['credit_replenished_before_gpu_eos'] and accepted['complete_model_prefixes_immutable']
    layout = list(map(int, (source / 'build/bidirectional-fixtures/layout.txt').read_text().split()))
    assert layout[18] == 131072
    assert accepted['application_bytes_exceeded_payload_allocation'] == (count * len(record) > layout[18])
    wire = [bytes.fromhex(raw) for raw in read(archive / 'wire_frames.json')]
    packets = read(archive / 'ingress_packets.json')
    requests = read(archive / 'requests.json')
    assert wire[:2] == [bytes.fromhex('000000040000000000'), bytes.fromhex('000000040100000000')]
    assert len(packets) == len(requests) + 2
    assert all(p['user'] == 0 and p['expected_commit'] == 1 for p in packets)
    assert [p['raw_hex'] for p in packets[2:]] == [r['raw_hex'] for r in requests]
    assert [p['tag'] for p in packets] == list(range(1, len(packets) + 1))
    client = H2Connection(H2Configuration(client_side=True, header_encoding='utf8'))
    server = H2Connection(H2Configuration(client_side=False, header_encoding='utf8'))
    client.initiate_connection()
    server.initiate_connection()
    server.data_to_send()  # The actual hardware advertises the same defaults with an empty SETTINGS.
    client.receive_data(wire[0])
    assert client.data_to_send().hex() == packets[0]['raw_hex']
    server.receive_data(bytes.fromhex(packets[0]['raw_hex']))
    assert server.data_to_send() == wire[1]
    client.receive_data(wire[1])
    client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    assert client.data_to_send().hex() == packets[1]['raw_hex']
    server.receive_data(bytes.fromhex(packets[1]['raw_hex']))
    prefix_refunds = ([16044] + [8022] * (count - 3)) if partial else [8022] * (count - 1)
    expected_updates = [(stream, amount) for amount in prefix_refunds for stream in (1, 0)]
    parsed = []
    for raw in wire:
        frame, size = Frame.parse_frame_header(memoryview(raw[:9]))
        frame.parse_body(memoryview(raw[9:]))
        assert frame.serialize() == raw
        parsed.append(frame)
    # This fixture ends the native gRPC response but does not issue the
    # separate host directory CLOSE used by the original complete corpus.
    # Qualify open-RPC refunds explicitly; do not infer automatic retirement.
    assert [(f.stream_id, f.window_increment) for f in parsed if f.type == 8] == expected_updates
    update_index, wire_index = 0, 2
    sent = bytearray()
    stream_refunded = connection_refunded = 0
    for i, request in enumerate(requests):
        message = (0 if i == 0 else i + 1) if partial else i
        offset = partial if partial and i == 1 else 0
        payload = record * 2 + record[:partial] if partial and i == 0 else record[offset:]
        end = message == count - 1
        assert (request['message'], request['offset'], request['data_bytes'], request['end_stream']) == (message, offset, len(payload), end)
        client.send_data(1, payload, end_stream=end)
        assert client.data_to_send().hex() == request['raw_hex']
        events = server.receive_data(bytes.fromhex(request['raw_hex']))
        assert b''.join(e.data for e in events if type(e).__name__ == 'DataReceived') == payload
        sent.extend(payload)
        available_to_refund = min(len(sent) // len(record), count - 1) * len(record)
        while update_index < len(expected_updates):
            stream, amount = expected_updates[update_index]
            refunded = stream_refunded if stream else connection_refunded
            if refunded + amount > available_to_refund:
                break
            assert (parsed[wire_index].type, parsed[wire_index].stream_id, parsed[wire_index].window_increment) == (8, stream, amount)
            client.receive_data(wire[wire_index])
            server.increment_flow_control_window(amount, stream_id=stream if stream else None)
            assert server.data_to_send() == wire[wire_index]
            if stream:
                stream_refunded += amount
            else:
                connection_refunded += amount
            wire_index += 1
            update_index += 1
    assert bytes(sent) == record * count and update_index == len(expected_updates)
    assert client.local_flow_control_window(1) == server.inbound_flow_control_window == 65535 - 8022
    events = [event for raw in wire[wire_index:] for event in client.receive_data(raw)]
    assert sum(type(e).__name__ == 'ResponseReceived' for e in events) == 1
    assert sum(type(e).__name__ == 'TrailersReceived' for e in events) == 1
    assert sum(type(e).__name__ == 'StreamEnded' for e in events) == 1
    assert not any(type(e).__name__ in ('StreamReset', 'ConnectionTerminated') for e in events)
    assert next(e.headers for e in events if type(e).__name__ == 'ResponseReceived') == [(':status', '200'), ('content-type', 'application/grpc+proto')]
    assert next(e.headers for e in events if type(e).__name__ == 'TrailersReceived') == [('grpc-status', '0')]
    expected_response = bytearray()
    for token in actual_ids:
        raw = encoding.decode_single_token_bytes(token)
        payload = b'\x8a\x01' + bytes([len(raw)]) + raw
        expected_response.extend(b'\0' + len(payload).to_bytes(4, 'big') + payload)
    actual_response = b''.join(e.data for e in events if type(e).__name__ == 'DataReceived')
    assert actual_response == expected_response and client.outbound_flow_control_window == 65535 - 8022
    assert sum(f.type == 8 for f in parsed) == accepted['actual_window_update_frames']
    return dict(run=name, messages=count, initial_partial_record_bytes=partial,
        actual_application_bytes=len(sent), actual_captured_dma_ids_returned=len(actual_ids),
        actual_window_update_frames=sum(f.type == 8 for f in parsed), native_complete_grpc_calls=1,
        byte_exact_native_response_sha256=hashlib.sha256(actual_response).hexdigest(),
        full_actual_ingress_and_wire_replayed=True, independent_tiktoken_ids_verified=True,
        receive_credit_causality_checked_against_complete_consumed_records=True,
        final_directory_close_requested=False, final_connection_bytes_awaiting_directory_close=8022,
        data_bytes_exceeded_payload_slot=len(sent) > layout[18],
        input_manifest_sha256=sha(archive / 'inputs.json'), acceptance_sha256=sha(archive / 'acceptance.json'),
        wire_sha256=sha(archive / 'wire_frames.json'), actual_generation_sha256=launch['generation_sha256'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', nargs='+', required=True)
    args = ap.parse_args()
    assert len(set(args.names)) == len(args.names) and all(re.fullmatch(r'[A-Za-z0-9_]+', n) for n in args.names)
    root = Path(__file__).resolve().parents[1]
    assembly = json.loads((root / 'build/validation/open-rpc-reclaim-assembly.json').read_text())
    assert assembly['key'] == 'ad1b6bc9beebcaf5'
    result = dict(phase='open_rpc_reclaim_selected_streaming_workloads_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), assembly_audit_key=assembly['key'],
        executions={n: verify(root, n, assembly) for n in args.names},
        original_starvation_counterexample_resolved=True, actual_receive_backend_executed=True,
        portable_tokenizer_memory_backend=True, native_vendor_runtime_verified=False,
        full_protocol_fault_matrix_verified=False, whole_system_retained_reset_verified=False,
        single_message_larger_than_initial_window_verified=False,
        distributed_rpc_gpu_model_authority_verified=False, native_timing_verified=False,
        automatic_closed_rpc_directory_retirement_verified=False,
        physical_interfaces_verified=False, full_system_complete=False,
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result['payload_reuse_beyond_slot_with_partial_record_verified'] = any(e['data_bytes_exceeded_payload_slot'] and e['initial_partial_record_bytes'] for e in result['executions'].values())
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/open-rpc-reclaim-runtime-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    for destination in (evidence / 'audit.json', root / 'build/validation/open-rpc-reclaim-runtime.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'payload_reuse_beyond_slot_with_partial_record_verified')}))


if __name__ == '__main__':
    main()
