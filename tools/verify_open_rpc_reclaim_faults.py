"""Audit actual reclaim ACK failures and independently replay its native RPC."""
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

from rtl_paths import source_relative


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    assembly = read(root / 'build/validation/open-rpc-reclaim-assembly.json')
    parent = read(root / 'build/validation/json-simd-corpus.json')
    assert assembly['key'] == 'ad1b6bc9beebcaf5' and parent['key'] == '2509134d2630b47e'
    launch_path = root / 'build/validation' / (args.name + '-launch.json')
    launch = read(launch_path)
    assert launch['phase'] == 'completed' and launch['exit_code'] == 0
    assert launch['profile'] == 'reclaim-faults' and launch['candidate'] == 'open-rpc-reclaim'
    assert launch['generation_sha256'] == assembly['generation_sha256']
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + args.name)
    source = archive / 'execution-sources'
    inputs, report, accepted = (read(archive / n) for n in ('inputs.json', 'report.json', 'acceptance.json'))
    assert report['phase'] == accepted['phase'] == 'passed' and report['tests'] == 1 and report['failures'] == 0
    assert read(archive / 'snapshot.json')['exit_code'] == 0
    assert inputs == report['input_sha256'] == launch['inputs_sha256']
    assert sha(archive / 'acceptance.json') == report['acceptance_sha256']
    for name, digest in inputs.items():
        assert sha(source / name) == digest, name
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', source).items()}
    tokenizer = {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', source).items()}
    assert parser == assembly['executed_parser_sha256'] and len(parser) == 77
    assert tokenizer == parent['executed_tokenizer_sha256'] and len(tokenizer) == 22
    assert sha(source / 'tools/run_open_rpc_credit_wsl.py') == launch['driver_sha256']
    edited = set()
    for edit in launch['fixture_edits']:
        text = (source / edit['path']).read_bytes().decode()
        for old, new in reversed(edit['replacements']):
            assert text.count(new) == 1
            text = text.replace(new, old)
        assert hashlib.sha256(text.encode()).hexdigest() == edit['old_sha256'] == parent['inputs_sha256'][edit['path']]
        edited.add(edit['path'])
    assert edited == {'scripts/run_raw_envelope_tests.py', 'sim/cocotb/test_http2_prefill.py'}
    for name, digest in parent['inputs_sha256'].items():
        if not name.startswith('rtl/') and name not in edited:
            assert inputs[name] == digest, name
    assert set(inputs) - set(parent['inputs_sha256']) == {
        'rtl/grpc_payload_reclaimer.v', 'sim/cocotb/test_raw_open_rpc_credit.py',
        'sim/cocotb/test_raw_reclaim_faults.py', 'tools/run_open_rpc_credit_wsl.py'}
    fault_source = (source / 'sim/cocotb/test_raw_reclaim_faults.py').read_text()
    assert 'workers = [cocotb.start_soon(memory.parser.run()), cocotb.start_soon(memory.tokenizer.run())]' in fault_source
    assert 'workers = [cocotb.start_soon(memory.run())]' not in fault_source
    xml = ET.parse(archive / 'results.xml')
    assert len(xml.findall('.//testcase')) == 1
    assert xml.findall('.//testcase')[0].attrib['name'] == 'actual_reclaim_ack_faults_preserve_ownership_and_close'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    assert accepted['complete_original_image_bytes'] == 8388608
    for flag in ('actual_reclaimer_and_receive_backend_executed', 'actual_prefix_compaction_verified',
                 'explicit_host_close_with_new_watermark_verified'):
        assert accepted[flag] is True

    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    ids = encoding.encode_ordinary('hello world')
    assert ids == [15339, 1917]
    small = b'\x0a\x0bhello world'
    body = small + b'\x9a\x06\xc0\x3e' + b'U' * 8000
    record = lambda b: b'\0' + len(b).to_bytes(4, 'big') + b
    first = record(small) * 2 + record(body)[:128]
    second = record(body)[128:]
    success = accepted['success']
    assert success['actual_captured_dma_ids_returned'] == ids * 3
    assert success['explicit_directory_close'] and success['final_connection_credit'] == 65535
    assert success['selected_text_in_compacted_partial_record_verified']
    packets = success['actual_ingress_packets']
    wire = [bytes.fromhex(raw) for raw in success['actual_wire_frames']]
    assert len(packets) == 4 and [p['tag'] for p in packets] == [1, 2, 3, 4]
    assert all(p['user'] == 0 and p['expected_commit'] == 1 for p in packets)
    parsed = []
    for raw in wire:
        frame, size = Frame.parse_frame_header(memoryview(raw[:9]))
        frame.parse_body(memoryview(raw[9:]))
        assert frame.serialize() == raw
        parsed.append(frame)
    assert [(f.stream_id, f.window_increment) for f in parsed if f.type == 8] == [(1, 36), (0, 36), (0, 8022)]
    client = H2Connection(H2Configuration(client_side=True, header_encoding='utf8'))
    server = H2Connection(H2Configuration(client_side=False, header_encoding='utf8'))
    client.initiate_connection(); server.initiate_connection(); server.data_to_send()
    assert wire[:2] == [bytes.fromhex('000000040000000000'), bytes.fromhex('000000040100000000')]
    client.receive_data(wire[0])
    assert client.data_to_send().hex() == packets[0]['raw_hex']
    server.receive_data(bytes.fromhex(packets[0]['raw_hex']))
    assert server.data_to_send() == wire[1]
    client.receive_data(wire[1])
    client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    assert client.data_to_send().hex() == packets[1]['raw_hex']
    server.receive_data(bytes.fromhex(packets[1]['raw_hex']))
    client.send_data(1, first)
    assert client.data_to_send().hex() == packets[2]['raw_hex']
    events = server.receive_data(bytes.fromhex(packets[2]['raw_hex']))
    assert b''.join(e.data for e in events if type(e).__name__ == 'DataReceived') == first
    for i, stream in enumerate((1, 0), 2):
        client.receive_data(wire[i])
        server.increment_flow_control_window(36, stream_id=stream or None)
        assert server.data_to_send() == wire[i]
    assert client.outbound_flow_control_window == server.inbound_flow_control_window == 65535 - 128
    client.send_data(1, second, end_stream=True)
    assert client.data_to_send().hex() == packets[3]['raw_hex']
    events = server.receive_data(bytes.fromhex(packets[3]['raw_hex']))
    assert b''.join(e.data for e in events if type(e).__name__ == 'DataReceived') == second
    events = [e for raw in wire[4:] for e in client.receive_data(raw)]
    assert sum(type(e).__name__ == 'ResponseReceived' for e in events) == 1
    assert sum(type(e).__name__ == 'TrailersReceived' for e in events) == 1
    assert sum(type(e).__name__ == 'StreamEnded' for e in events) == 1
    assert next(e.headers for e in events if type(e).__name__ == 'TrailersReceived') == [('grpc-status', '0')]
    assert not any(type(e).__name__ in ('StreamReset', 'ConnectionTerminated') for e in events)
    expected = b''.join(record(b'\x8a\x01' + bytes([len(raw)]) + raw)
        for token in ids * 3 for raw in [encoding.decode_single_token_bytes(token)])
    actual = b''.join(e.data for e in events if type(e).__name__ == 'DataReceived')
    assert actual == expected and hashlib.sha256(actual).hexdigest() == success['response_sha256']
    assert client.outbound_flow_control_window == 65535

    layout = list(map(int, (source / 'build/bidirectional-fixtures/layout.txt').read_text().split()))
    rpc, payload = layout[13], layout[17]
    commands = success['actual_reclaim_commands']
    assert len(commands) == 99
    # Independently reconstruct every compaction write, including the overlap
    # (cut 26 < tail 123), and the durable reclaimed-ordinal watermark.
    prefix = commands[:46]
    assert all(c['owner'] == 'compactor' for c in prefix)
    assert [(c['write'], c['address'], c['bytes']) for c in prefix[:8]] == [(0, rpc + 8 * i, 8) for i in range(8)]
    assert (prefix[8]['write'], prefix[8]['address'], prefix[8]['bytes'], prefix[8]['data']) == (1, rpc, 8, 0)
    for i, offset in enumerate(range(0, 123, 8)):
        n = min(8, 123 - offset)
        rd, wr = prefix[9 + 2 * i:11 + 2 * i]
        assert (rd['write'], rd['address'], rd['bytes']) == (0, payload + 26 + offset, n)
        assert (wr['write'], wr['address'], wr['bytes']) == (1, payload + offset, n)
        assert wr['data'] & ((1 << (8 * n)) - 1) == int.from_bytes(body[offset:offset + n], 'little')
    state_words = [123, 8017 | (123 << 32), 2 | (5 << 32) | (2 << 37), 0]
    assert [(c['write'], c['address'], c['bytes'], c['data']) for c in prefix[41:45]] == [(1, rpc + 32 + i * 8, 8, w) for i, w in enumerate(state_words)]
    assert (prefix[45]['write'], prefix[45]['address'], prefix[45]['bytes'], prefix[45]['data']) == (1, rpc, 8, 0x347525331)
    credit = commands[46:-2]
    assert len(credit) == 51 and all(c['owner'] == 'credit' for c in credit)
    arenas = [(layout[19], 256), (rpc, 32), (0x7e5000, 64), (0x7e6000, 32)]
    for c in credit:
        assert any(base <= c['address'] and c['address'] + c['bytes'] <= base + size for base, size in arenas)
        if c['write']:
            assert any(base <= c['address'] and c['address'] + c['bytes'] <= base + size for base, size in arenas[2:])
    assert [(c['owner'], c['write'], c['address'], c['bytes']) for c in commands[-2:]] == [('compactor', 0, rpc + i * 128, 8) for i in (1, 2)]
    credit_ops = success['actual_credit_commands']
    assert [(c[0], c[1], c[2], c[4], c[5]) for c in credit_ops] == [(3, 0, 1, rpc, 36), (4, 0, 1, rpc, 0), (4, 0, 0, 0, 0)]
    assert credit_ops[0][3] == credit_ops[1][3] != 0 and credit_ops[2][3] == 0
    initial_updates = success['actual_initial_window_updates']
    assert initial_updates == [wire[2].hex(), wire[3].hex()]
    faults = accepted['actual_memory_ack_faults']
    assert [f['phase'] for f in faults] == list(range(len(commands)))
    for phase, fault in enumerate(faults):
        assert fault['failed_command'] == commands[phase]
        assert fault['actual_commands'] == commands[:phase + 1]
        assert fault['actual_responses'] == [dict(command=i, status=0 if i < phase else 0x75) for i in range(phase + 1)]
        assert fault['actual_error'][2] == 0x75
        assert fault['actual_pool_retained'] and fault['new_work_denied'] and fault['model_prefixes_immutable']
        updates = fault['actual_window_updates']
        assert len(updates) <= 2 and updates == initial_updates[:len(updates)]
        ops = fault['actual_credit_commands']
        assert len(ops) <= 3 and ops == credit_ops[:len(ops)]
        if phase < 46:
            assert not ops and not updates
        if phase >= 97:
            assert ops == credit_ops and updates == initial_updates
    result = dict(phase='actual_open_rpc_reclaim_ack_faults_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name, assembly_audit_key=assembly['key'], exact_parser_modules=77, exact_tokenizer_modules=22,
        actual_memory_ack_faults=len(faults), actual_credit_backend_memory_phases=len(credit),
        actual_overlapping_partial_body_move_independently_checked=True,
        actual_durable_reclaim_watermark_checked=True, full_native_ingress_and_wire_replayed=True,
        actual_captured_dma_ids_returned=6, explicit_host_close_connection_refund_verified=True,
        quarantine_retains_actual_pool_and_denies_new_work=True, full_model_and_original_fixture_sources_verified=True,
        portable_memory_backend=True, native_vendor_runtime_verified=False, whole_system_retained_reset_verified=False,
        automatic_directory_retirement_verified=False, full_protocol_fault_matrix_verified=False,
        native_timing_verified=False, physical_interfaces_verified=False, full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix(): sha(p) for p in [launch_path, *[p for p in archive.iterdir() if p.is_file()]]},
        verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/open-rpc-reclaim-faults-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    for destination in (evidence / 'audit.json', root / 'build/validation/open-rpc-reclaim-faults.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'actual_memory_ack_faults')}))


if __name__ == '__main__':
    main()
