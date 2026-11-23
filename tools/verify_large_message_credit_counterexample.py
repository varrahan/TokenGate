"""Verify a real legal-message receive-credit deadlock without relabeling it passed."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection

from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True); args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    assembly = read(root / 'build/validation/open-rpc-reclaim-assembly.json')
    original = read(root / 'build/validation/json-simd-corpus.json')
    assert assembly['key'] == 'ad1b6bc9beebcaf5' and original['key'] == '2509134d2630b47e'
    launch_path = root / 'build/validation' / (args.name + '-launch.json')
    launch = read(launch_path)
    assert launch['phase'] == 'failed' and launch['exit_code'] == 1
    assert launch['profile'] == 'large-message-credit' and launch['candidate'] == 'open-rpc-reclaim'
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + args.name)
    source = archive / 'execution-sources'
    report, inputs, failure = (read(archive / n) for n in ('report.json', 'inputs.json', 'failure.json'))
    # The frozen runner stops on a cocotb failure before adding its summary
    # counts. Validate the actual XML testcase and failure count below.
    assert report['phase'] == 'failed' and report['profile'] == 'large-message-credit'
    assert read(archive / 'snapshot.json')['exit_code'] == 1
    assert inputs == launch['inputs_sha256'] == report['input_sha256']
    for name, digest in inputs.items():
        assert sha(source / name) == digest, name
    assert {n: sha(p) for n, p in closure('http2_enveloped_parser_application', source).items()} == assembly['executed_parser_sha256']
    assert {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', source).items()} == original['executed_tokenizer_sha256']
    assert launch['generation_sha256'] == assembly['generation_sha256']
    assert sha(source / 'tools/run_open_rpc_credit_wsl.py') == launch['driver_sha256']
    edits = {e['path']: e for e in launch['fixture_edits']}
    assert set(edits) == {'sim/cocotb/test_http2_prefill.py', 'scripts/run_raw_envelope_tests.py'}
    for name, edit in edits.items():
        text = (source / name).read_bytes().decode()
        for before, after in reversed(edit['replacements']):
            assert text.count(after) == 1; text = text.replace(after, before)
        assert hashlib.sha256(text.encode()).hexdigest() == edit['old_sha256'] == original['inputs_sha256'][name]
    for name, digest in original['inputs_sha256'].items():
        if not name.startswith('rtl/') and name not in edits:
            assert inputs[name] == digest, name
    xml = ET.parse(archive / 'results.xml')
    failures = xml.findall('.//failure')
    assert len(xml.findall('.//testcase')) == 1 and not xml.findall('.//error')
    assert len(failures) == 1 and 'Configured legal gRPC message exhausted receive credit before its DMA descriptor could exist' in failures[0].text
    assert xml.findall('.//testcase')[0].attrib['name'] == 'configured_large_record_completes_before_waiting_for_dma'
    assert failure['phase'] == 'starved_before_first_message_completed'
    assert failure['configured_message_limit'] == failure['actual_message_body_bytes'] == 65536
    assert failure['actual_record_bytes'] == 65541 and failure['actual_data_bytes_sent'] == 65535
    assert failure['remaining_record_bytes'] == 6
    for name in ('actual_stream_credit', 'actual_connection_credit', 'actual_completed_messages',
                 'actual_dma_ids', 'actual_generated_descriptors', 'actual_window_update_frames', 'actual_receive_fault'):
        assert failure[name] == 0, name
    assert failure['actual_progress_used'] == failure['actual_progress_payload_received'] == 65530
    assert failure['actual_progress_message_length'] == 65536 and failure['full_model_prefixes_immutable']

    body = (b'\x9a\x06\xc0\x3e' + b'U' * 8000) * 8 + b'\x9a\x06\xcf\x0b' + b'U' * 1487 + b'\x0a\x0bhello world'
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    assert len(body) == 65536
    wire = [bytes.fromhex(raw) for raw in read(archive / 'wire_frames.json')]
    packets, requests = (read(archive / n) for n in ('ingress_packets.json', 'requests.json'))
    assert wire == [bytes.fromhex('000000040000000000'), bytes.fromhex('000000040100000000')]
    assert len(packets) == len(requests) + 2 == 10
    assert [p['tag'] for p in packets] == list(range(1, 11))
    assert all(p['user'] == 0 and p['expected_commit'] == 1 for p in packets)
    assert [p['raw_hex'] for p in packets[2:]] == [r['raw_hex'] for r in requests]
    client = H2Connection(H2Configuration(client_side=True, header_encoding='utf8'))
    server = H2Connection(H2Configuration(client_side=False, header_encoding='utf8'))
    client.initiate_connection(); server.initiate_connection(); server.data_to_send()
    client.receive_data(wire[0])
    assert client.data_to_send().hex() == packets[0]['raw_hex']
    server.receive_data(bytes.fromhex(packets[0]['raw_hex']))
    assert server.data_to_send() == wire[1]
    client.receive_data(wire[1])
    client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    assert client.data_to_send().hex() == packets[1]['raw_hex']
    server.receive_data(bytes.fromhex(packets[1]['raw_hex']))
    offset = 0
    for i, request in enumerate(requests):
        size = 8192 if i < 7 else 8191
        assert (request['offset'], request['data_bytes'], request['end_stream']) == (offset, size, False)
        payload = record[offset:offset + size]
        client.send_data(1, payload)
        assert client.data_to_send().hex() == request['raw_hex']
        events = server.receive_data(bytes.fromhex(request['raw_hex']))
        assert b''.join(e.data for e in events if type(e).__name__ == 'DataReceived') == payload
        offset += size
    assert offset == 65535 and client.local_flow_control_window(1) == client.outbound_flow_control_window == server.inbound_flow_control_window == 0
    result = dict(phase='configured_large_message_receive_credit_counterexample_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), run=args.name, assembly_audit_key=assembly['key'],
        configured_message_limit=65536, actual_record_bytes=65541, actual_data_bytes_sent=65535,
        remaining_record_bytes=6, complete_messages=0, actual_dma_ids=0, actual_window_update_frames=0,
        full_actual_ingress_and_wire_replayed=True, original_full_model_and_native_packages_preserved=True,
        actual_hardware_progress_matches_partial_record=True,
        diagnosis='The configured legal message cannot complete before DATA receive credit is exhausted, so no application DMA completion can trigger the current reclaimer',
        application_credit_fixed=False, native_vendor_runtime_verified=False, full_system_complete=False,
        executed_parser_sha256=assembly['executed_parser_sha256'],
        artifacts_sha256={source_relative(p, root).as_posix(): sha(p) for p in [launch_path, *[p for p in archive.iterdir() if p.is_file()]]},
        verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/large-message-credit-counterexample-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    for path in (evidence / 'audit.json', root / 'build/validation/large-message-credit-counterexample.json'):
        path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'remaining_record_bytes')}))


if __name__ == '__main__':
    main()
