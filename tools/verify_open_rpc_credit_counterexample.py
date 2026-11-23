"""Qualify a real failed streaming-credit execution without calling it a pass."""
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
import tiktoken

from verify_two_fpga_application import closure


def verify(root, name):
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    launch = read(root / 'build/validation' / (name + '-launch.json'))
    assert launch['phase'] == 'failed' and launch['exit_code'] == 1
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + name)
    source = archive / 'execution-sources'
    inputs = read(archive / 'inputs.json')
    report = read(archive / 'report.json')
    snapshot = read(archive / 'snapshot.json')
    failure = read(archive / 'failure.json')
    assert inputs == launch['inputs_sha256'] == report['input_sha256']
    assert report['phase'] == snapshot['phase'] == 'failed' and snapshot['exit_code'] == 1
    assert report['profile'] == snapshot['profile'] == 'open-rpc-credit'
    for path, digest in inputs.items():
        assert sha(source / path) == digest, path
    assert sha(source / 'tools/run_open_rpc_credit_wsl.py') == launch['driver_sha256']
    baseline = read(root / 'build/validation/json-simd-corpus.json')
    assert baseline['key'] == launch['baseline_audit_key'] == '2509134d2630b47e'
    assert set(inputs) - set(baseline['inputs_sha256']) == {
        'sim/cocotb/test_raw_open_rpc_credit.py', 'tools/run_open_rpc_credit_wsl.py'}
    assert set(baseline['inputs_sha256']) <= set(inputs)
    assert len(launch['fixture_edits']) == 2
    assert {e['path'] for e in launch['fixture_edits']} == {
        'sim/cocotb/test_http2_prefill.py', 'scripts/run_raw_envelope_tests.py'}
    for edit in launch['fixture_edits']:
        text = (source / edit['path']).read_bytes().decode()
        assert inputs[edit['path']] == edit['new_sha256']
        for old, new in reversed(edit['replacements']):
            assert text.count(new) == 1
            text = text.replace(new, old)
        assert hashlib.sha256(text.encode()).hexdigest() == edit['old_sha256'] == baseline['inputs_sha256'][edit['path']]
    changed = {p for p in baseline['inputs_sha256'] if baseline['inputs_sha256'][p] != inputs[p]}
    assert changed == set(launch['changed_rtl']) | {e['path'] for e in launch['fixture_edits']}
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', source).items()}
    tokenizer = {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', source).items()}
    assert len(parser) == 76 and len(tokenizer) == 22
    assert tokenizer == baseline['executed_tokenizer_sha256']
    quiet = launch['candidate'] == 'frame-owned-quiet'
    units = read(root / 'build/validation' / ('frame-owned-quiet-formal.json' if quiet else 'frame-event-buffer-units.json'))
    assert units['key'] == ('c56de709b9b5681a' if quiet else '0629d7b95661f8df')
    assert parser == units['executed_parser_sha256' if quiet else 'candidate_parser_sha256']
    assert launch['portable_memory_backend'] and launch['full_model_image_preserved']
    meta = read(source / 'build/bidirectional-fixtures/fixture_manifest.json')
    image = b''.join(int(word, 16).to_bytes(8, 'little')
        for word in (source / 'build/bidirectional-fixtures/memory.mem').read_text().splitlines())
    assert len(image) == 8388608 and hashlib.sha256(image).hexdigest() == meta['loaded_image_sha256']
    layout = list(map(int, (source / 'build/bidirectional-fixtures/layout.txt').read_text().split()))
    xml = ET.parse(archive / 'results.xml')
    cases = xml.findall('.//testcase')
    assert len(cases) == 1 and cases[0].attrib['name'] == 'consumed_messages_replenish_credit_before_rpc_close'
    assert len(xml.findall('.//failure')) == 1 and not xml.findall('.//error')
    assert failure['phase'] == 'open_rpc_application_credit_starvation'
    assert (failure['message'], failure['message_offset'], failure['actual_data_bytes_sent']) == (8, 1359, 65535)
    assert failure['complete_messages_acknowledged'] == 8 and failure['actual_forward_dma_ids'] == 16
    assert failure['native_connection_credit'] == failure['native_stream_and_connection_credit'] == 0
    assert failure['actual_window_update_frames'] == failure['actual_gpu_descriptors'] == 0
    assert not failure['stream_ended'] and failure['complete_model_prefixes_immutable']
    partial = launch.get('initial_partial_record_bytes', 0)
    requested_messages = launch.get('requested_messages', 9)
    assert (partial, requested_messages) in ((0, 9), (128, 21))
    amounts = [16172, 7894] + [8022] * 5 + [1359] if partial else [8022] * 8 + [1359]
    trace = read(archive / 'receive_trace.json')
    receive_requests = [e for e in trace if e['event'] == 'rx_request']
    receive_results = [e for e in trace if e['event'] == 'rx_result']
    assert [e['op'] for e in receive_requests] == [11, 0, 1] + [2] * len(amounts)
    assert [e['amount'] for e in receive_requests] == [0, 65535, 0] + amounts
    assert all(e['user'] == 0 for e in receive_requests)
    assert all(e['stream'] == 1 and e['generation'] == e['address'] == 0 for e in receive_requests[3:])
    assert len(receive_results) == len(receive_requests)
    assert all((e['status'], e['detail'], e['memory_status']) == (0, 0, 0) for e in receive_results)
    pending = False
    for event in trace:
        if event['event'] == 'rx_request':
            assert not pending
            pending = True
        elif event['event'] == 'rx_result':
            assert pending
            pending = False
    assert not pending
    directory_requests = [e for e in trace if e['event'] == 'service_control_req']
    assert len([e for e in directory_requests if e['op'] == 0]) == 1
    assert len([e for e in directory_requests if e['op'] == 2]) == len(amounts)
    assert not any(e['op'] == 3 for e in directory_requests)
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    expected_ids = tiktoken.get_encoding('cl100k_base').encode_ordinary('hello world')
    assert failure['actual_captured_dma_ids'] == expected_ids * 8 and expected_ids == [15339, 1917]
    # Independent native-h2 replay verifies the actual offered DATA bytes,
    # legal framing, open stream, and exact exhaustion of both peer windows.
    client = H2Connection(H2Configuration(client_side=True, header_encoding='utf8'))
    server = H2Connection(H2Configuration(client_side=False, header_encoding='utf8'))
    client.initiate_connection()
    server.initiate_connection()
    server.receive_data(client.data_to_send())
    client.receive_data(server.data_to_send())
    server.receive_data(client.data_to_send())
    client.receive_data(server.data_to_send())
    client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    server.receive_data(client.data_to_send())
    body = b'\x9a\x06\xc0\x3e' + b'U' * 8000 + b'\x0a\x0bhello world'
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    assert len(record) == 8022 and 9 * len(record) < layout[18] == 131072
    requests = read(archive / 'requests.json')
    assert len(requests) == len(amounts)
    received = bytearray()
    for i, request in enumerate(requests):
        size = amounts[i]
        message = (0 if i == 0 else i + 1) if partial else i
        offset = partial if partial and i == 1 else 0
        payload = record * 2 + record[:partial] if partial and i == 0 else record[offset:offset + size]
        assert (request['tag'], request['message'], request['offset'], request['data_bytes'], request['end_stream']) == (3 + i, message, offset, size, False)
        client.send_data(1, payload)
        actual = bytes.fromhex(request['raw_hex'])
        assert actual == client.data_to_send()
        events = server.receive_data(actual)
        assert len(events) == 1 and type(events[0]).__name__ == 'DataReceived'
        assert events[0].stream_id == 1 and events[0].flow_controlled_length == size
        received.extend(events[0].data)
    assert bytes(received) == (record * 9)[:65535]
    assert client.outbound_flow_control_window == client.local_flow_control_window(1) == 0
    assert server.inbound_flow_control_window == server.streams[1].inbound_flow_control_window == 0
    if partial:
        packets = read(archive / 'ingress_packets.json')
        wire = read(archive / 'wire_frames.json')
        assert wire == ['000000040000000000', '000000040100000000']
        assert len(packets) == len(requests) + 2
        assert all(p['user'] == 0 and p['expected_commit'] == 1 for p in packets)
        assert [p['raw_hex'] for p in packets[2:]] == [r['raw_hex'] for r in requests]
        actual_client = H2Connection(H2Configuration(client_side=True, header_encoding='utf8'))
        actual_client.initiate_connection()
        # OPEN retires the server's initial SETTINGS before this fixture
        # sends its client preface. Its ACK is therefore queued in packet 1.
        events = list(actual_client.receive_data(bytes.fromhex(wire[0])))
        assert actual_client.data_to_send().hex() == packets[0]['raw_hex']
        events += actual_client.receive_data(bytes.fromhex(wire[1]))
        assert [type(e).__name__ for e in events] == ['RemoteSettingsChanged', 'SettingsAcknowledged']
        actual_client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
            (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
        assert actual_client.data_to_send().hex() == packets[1]['raw_hex']
        for i, request in enumerate(requests):
            offset = partial if i == 1 else 0
            payload = record * 2 + record[:partial] if i == 0 else record[offset:offset + amounts[i]]
            actual_client.send_data(1, payload)
            assert actual_client.data_to_send().hex() == request['raw_hex']
        assert actual_client.local_flow_control_window(1) == 0
    assert not failure['full_system_complete']
    return dict(run=name, candidate=launch['candidate'], source_audit_key=units['key'],
        failure=failure, independent_native_h2_data_replay_verified=True,
        actual_receive_request_result_trace_verified=True,
        successful_data_debits=len(amounts), application_credit_release_commands=0,
        requested_messages=requested_messages, initial_partial_record_bytes=partial,
        actual_wire_and_complete_ingress_replayed=bool(partial),
        actual_rpc_close_commands=0,
        independent_tiktoken_ids_verified=True, full_image_bytes=8388608,
        exact_parser_modules=76, exact_tokenizer_modules=22, executed_parser_sha256=parser,
        executed_tokenizer_sha256=tokenizer, exact_fixture_inverse_verified=True,
        all_native_http2_client_sources_unchanged=True, actual_execution_source_hashes_verified=True,
        input_manifest_sha256=sha(archive / 'inputs.json'),
        artifacts_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()},
        portable_memory_backend=True, native_vendor_runtime_verified=False,
        receive_credit_fixed=False, payload_reclamation_verified=False, full_system_complete=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--names', nargs='+', required=True)
    args = ap.parse_args()
    assert len(set(args.names)) == len(args.names)
    assert all(re.fullmatch(r'[A-Za-z0-9_]+', n) for n in args.names)
    root = Path(__file__).resolve().parents[1]
    result = dict(phase='open_rpc_credit_counterexample_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),
        executions={name: verify(root, name) for name in args.names},
        receive_credit_fixed=False, full_system_complete=False,
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if len(result['executions']) >= 2:
        records=list(result['executions'].values())
        assert all(record['failure']==records[0]['failure'] for record in records)
        result['same_counterexample_on_parent_and_candidate'] = len({record['candidate'] for record in records}) > 1
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    folder = root / 'build/validation/open-rpc-credit-counterexample-evidence' / result['key']
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    for destination in (folder / 'audit.json', root / 'build/validation/open-rpc-credit-counterexample.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'receive_credit_fixed')}))


if __name__ == '__main__':
    main()
