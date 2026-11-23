"""Verify the actual new-stream-refusal/old-RPC cleanup counterexample."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    run = 'rpc_admission_fence_live_v4_observed_20261122'
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + run)
    source = archive / 'execution-sources'
    launch = read(archive / 'launch.json')
    report = read(archive / 'report.json')
    inputs = read(archive / 'inputs.json')
    assert launch['phase'] == report['phase'] == 'failed' and launch['exit_code'] == 1
    assert inputs == launch['inputs_sha256'] == report['input_sha256']
    for name, digest in inputs.items():
        assert sha(source / name) == digest, name
    assert sha(archive / 'run_rpc_admission_fence_wsl.py') == launch['driver_sha256']
    assert sha(archive / 'fence-generation.json') == launch['generation_sha256']
    generation = read(archive / 'fence-generation.json')
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', source).items()}
    tokenizer = {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', source).items()}
    assert len(parser) == 78 and len(tokenizer) == 22
    assert parser == launch['parser_sha256'] and tokenizer == launch['tokenizer_sha256']
    assert all(digest == generation['outputs_sha256']['joint/rtl/' + n + '.v'] for n, digest in parser.items())
    assembly = read(root / 'build/validation/rpc-admission-fence.json')
    assert assembly['key'] == launch['assembly_audit_key'] == '1e606bcd79f8f20a'
    assert assembly['generation_sha256'] == sha(archive / 'fence-generation.json')
    parent = root / 'build/wsl-reports/raw_envelope_receive_capacity_v4_native_owner_admission_20261122'
    parent_inputs = read(parent / 'inputs.json')
    assert launch['parent_inputs_sha256'] == parent_inputs
    parent_tokenizer = {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', parent / 'execution-sources').items()}
    assert tokenizer == parent_tokenizer
    for name, edit in launch['fixture_edits'].items():
        assert sha(source / name) == edit['after_sha256']
        inverse = (source / name).read_bytes().decode()
        for before, after in reversed(edit['replacements']):
            assert inverse.count(after) == 1
            inverse = inverse.replace(after, before)
        assert hashlib.sha256(inverse.encode()).hexdigest() == edit['before_sha256'] == parent_inputs[name]
    # Every original fixture/model/package outside the explicitly named three
    # fixture edits is byte identical. New recording/test modules are explicit.
    for name, digest in parent_inputs.items():
        if not name.startswith('rtl/') and name not in launch['fixture_edits']:
            assert inputs[name] == digest, name
    fixture = read(source / 'build/bidirectional-fixtures/fixture_manifest.json')
    model = b''.join(int(word, 16).to_bytes(8, 'little') for word in
        (source / 'build/bidirectional-fixtures/memory.mem').read_text().splitlines())
    assert len(model) == 8388608 and hashlib.sha256(model).hexdigest() == fixture['loaded_image_sha256']
    xml = ET.parse(archive / 'results.xml')
    cases = xml.findall('.//testcase')
    assert len(cases) == 1 and cases[0].attrib['name'] == 'new_rpc_fence_preserves_old_calls_and_sampled_begin'
    assert len(cases[0].findall('failure')) == 1 and not xml.findall('.//error')
    text = (archive / 'simulation.log').read_text()
    failing_assertion = "assert int.from_bytes(image[original_binding[1]:original_binding[1] + 4], 'little') == 0x47525331"
    assert failing_assertion in text and 'AssertionError: assert 0 == 1196577585' in text
    assert 'ModuleNotFoundError' not in text
    test = (source / 'sim/cocotb/test_rpc_admission_fence.py').read_text()
    assert test.index(failing_assertion) < test.index('await b.directory(3, 0, 1)')
    observed = read(archive / 'fence_refusal_observation.json')
    before = bytes.fromhex(observed['before_record_hex'])
    after = bytes.fromhex(observed['after_record_hex'])
    assert len(before) == len(after) == 128
    assert before[:4] == (0x47525331).to_bytes(4, 'little') and before[4] & 1
    assert int.from_bytes(before[12:16], 'little') == observed['old_stream'] == 1
    assert int.from_bytes(before[28:32], 'little') == observed['old_generation'] == 1
    assert after[:8] == bytes(8)
    assert observed['refused_stream'] == 3 and observed['actual_dma_ids'] == 0
    assert observed['actual_generated_descriptors'] == []
    assert (observed['admit_packets'], observed['admit_messages'], observed['admit_new_rpcs']) == (1, 1, 0)
    rejections = observed['header_rejections']
    assert len(rejections) == 1 and rejections[0]['stream'] == 3
    expected = dict(header_status=4, header_detail=1, header_memory_status=0, header_cleanup_status=0,
        header_connection_error=0, header_http2_error=7, header_generation=0, header_model_epoch=0,
        header_schema_epoch=0, header_application=0, header_address=0)
    assert all(rejections[0][k] == v for k, v in expected.items())
    packets = read(archive / 'ingress_packets.json')
    assert len(packets) == 4 and [p['tag'] for p in packets] == [1, 2, 3, 4]
    assert [p['expected_commit'] for p in packets] == [1, 1, 1, 0]
    server = H2Connection(H2Configuration(client_side=False, header_encoding='utf8'))
    server.initiate_connection()
    events = [server.receive_data(bytes.fromhex(p['raw_hex'])) for p in packets]
    assert [e.stream_id for e in events[1] if type(e).__name__ == 'RequestReceived'] == [1]
    assert [e.stream_id for e in events[3] if type(e).__name__ == 'RequestReceived'] == [3]
    data = [e for e in events[2] if type(e).__name__ == 'DataReceived']
    assert len(data) == 1 and data[0].stream_id == 1 and data[0].data == b'\0\0\0\0\r\x0a\x0b'
    assert not any(type(e).__name__ == 'StreamEnded' for batch in events for e in batch)
    trace = read(archive / 'receive_trace.json')
    closes = [e for e in trace if e['event'] == 'service_control_req' and e['op'] == 3]
    assert len(closes) == 1 and closes[0]['stream'] == 1 and closes[0]['generation'] == 1
    assert closes[0]['address'] == observed['old_address'] and closes[0]['phase'] == 'packet 3 user 0'
    close_results = [e for e in trace if e['event'] == 'service_control_rsp' and e['op'] == 3]
    assert len(close_results) == 1 and close_results[0]['status'] == close_results[0]['memory_status'] == 0
    assert any(e['event'] == 'rx_request' and e['op'] == 10 and e['stream'] == 1 for e in trace)
    transport = (source / 'rtl/http2_classified_parser_transport.v').read_text()
    assert 'if(header_status!=0)begin packet_fatal<=1;header_pending<=0;end' in transport
    assert 'assign receive_connection_closing=control_packet_active&&(packet_fatal||' in transport
    result = dict(phase='new_rpc_fence_connection_cleanup_counterexample_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), run=run,
        actual_parser_modules=78, actual_tokenizer_modules=22,
        full_vocabulary_image_preserved=True, exact_executed_parser_sources_verified=True,
        native_http2_valid_new_headers_and_partial_old_data_verified=True,
        real_successful_directory_close_of_old_rpc_verified=True,
        old_rpc_header_invalidated_after_stream_refusal=True,
        fence_refusal_safe_for_live_rpc_drain=False,
        native_vendor_runtime_verified=False, whole_rpc_gpu_maintenance_authority_verified=False,
        full_system_complete=False, inputs_sha256=inputs,
        observation_sha256=sha(archive / 'fence_refusal_observation.json'),
        memory_trace_sha256=sha(archive / 'receive_trace.json'),
        verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    result['key'] = key
    evidence = root / 'build/validation/rpc-admission-fence-failure-evidence' / key
    evidence.mkdir(parents=True, exist_ok=False)
    for name in ('fence_refusal_observation.json', 'ingress_packets.json', 'wire_frames.json', 'receive_trace.json', 'launch.json'):
        shutil.copy2(archive / name, evidence / name)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    text = json.dumps(result, indent=2) + '\n'
    (evidence / 'audit.json').write_text(text)
    (root / 'build/validation/rpc-admission-fence-failure.json').write_text(text)
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'fence_refusal_safe_for_live_rpc_drain')}))


if __name__ == '__main__':
    main()
