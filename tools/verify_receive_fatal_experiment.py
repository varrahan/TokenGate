"""Verify fatal retirement progress while retaining the missing-GOAWAY failure."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import tiktoken
from verify_native_grpc_corpus_reference import varint
from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/experiments/receive-fatal'
    generation = json.loads((folder / 'generation.json').read_text())
    assert len(generation['generated_sha256']) == 18
    overrides = {'rtl/' + n: h for n, h in generation['generated_sha256'].items()}
    records = {}
    current_dag = None
    for label, name, positive in (
        ('original', 'receive_pool_fatal_padding_native_reference', False),
        ('current', 'receive_fatal_reopen_same_arenas', False),
        ('native', 'receive_fatal_public_cause_native', True)):
        archive = root / 'build/wsl-reports' / ('raw_envelope_' + name)
        source = archive / 'execution-sources'
        inputs = json.loads((archive / 'inputs.json').read_text())
        report = json.loads((archive / 'report.json').read_text())
        snapshot = json.loads((archive / 'snapshot.json').read_text())
        result_file = archive / ('acceptance.json' if positive else 'failure.json')
        result = json.loads(result_file.read_text())
        assert snapshot['exit_code'] == (0 if positive else 1)
        assert report['phase'] == ('passed' if positive else 'failed')
        assert report['input_sha256'] == inputs
        for n, h in inputs.items():
            assert sha(source / n) == h, (label, n)
            if n.startswith('native-vendor/'):
                assert sha(root / '.venv312/Lib/site-packages' / n.split('/', 1)[1]) == h
        xml = ET.parse(archive / 'results.xml')
        cases = xml.findall('.//testcase')
        assert len(cases) == 1 and not xml.findall('.//error')
        failures = xml.findall('.//failure')
        assert len(failures) == (0 if positive else 1)
        assert cases[0].attrib['name'] == ('native_calls_return_actual_dma_ids_and_complete_grpc' if positive
            else 'fatal_padding_error_emits_goaway_without_close_refund')
        if label == 'current':
            assert failures[0].attrib['type'] == 'AssertionError'
            assert 'assert [] == [(1, 1)]' in failures[0].text
        dag = closure('http2_enveloped_parser_application', source)
        tokenizer = closure('tokenizer_fpga_memory_subsystem', source)
        assert (len(dag), len(tokenizer)) == (73, 22)
        hashes = {n: sha(p) for n, p in dag.items()}
        if label != 'original':
            assert current_dag is None or hashes == current_dag
            current_dag = hashes
            for path in [*dag.values(), *tokenizer.values()]:
                n = path.relative_to(source).as_posix()
                assert inputs[n] == overrides.get(n, sha(root / n)), n
            assert inputs['sim/cocotb_two_fpga_enveloped_top.sv'] == generation['sim_sha256']['cocotb_two_fpga_enveloped_top.sv']
            if positive:
                assert inputs['sim/cocotb/test_raw_grpc_enveloped.py'] == generation['sim_sha256']['test_raw_grpc_enveloped.py']
                assert report['acceptance_sha256'] == sha(result_file)
            else:
                assert inputs['sim/cocotb/test_raw_receive_errors.py'] == sha(root / 'sim/cocotb/test_raw_receive_errors.py')
        fixture = source / 'build/bidirectional-fixtures'
        manifest = json.loads((fixture / 'fixture_manifest.json').read_text())
        loaded = b''.join(int(s, 16).to_bytes(8, 'little') for s in (fixture / 'memory.mem').read_text().splitlines())
        original = root / 'build/scu35/image/external_memory.bin'
        assert len(loaded) == original.stat().st_size == 8388608
        assert sha(original) == 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
        assert hashlib.sha256(loaded).hexdigest() == manifest['loaded_image_sha256']
        assert loaded[:6903552] == original.read_bytes()[:6903552]
        records[label] = dict(snapshot=name, result=result, inputs_sha256=inputs,
            archive_files_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()})
    old = records['original']['result']
    now = records['current']['result']
    native = records['native']['result']
    assert old['packet_result']['transport_packet_http2_error'] == 2
    assert any(r['event'] == 'rx_result' and r['status'] == 3 and r['detail'] == 1 for r in old['actual_receive_trace'])
    assert now['independent_native_goaway'] == [1, 1] and now['actual_goaway'] == []
    assert now['actual_wire_hex'] == [] and now['actual_forward_dma_ids'] == 0
    assert now['packet_result']['packet_committed'] == 0 and now['packet_result']['packet_status'] == 4
    assert now['packet_result']['transport_packet_http2_error'] == 1
    assert now['actual_raw_context_header_hex'] == '0000000000000000'
    assert now['actual_receive_connection_available'] == 65528 and now['actual_receive_connection_pending'] == 0
    assert now['actual_receive_stream_closed'] == 1 and now['actual_receive_fault'] == now['actual_receive_recovery_required'] == 0
    trace = now['actual_receive_trace']
    assert all(r['status'] == 0 for r in trace if r['event'] == 'rx_result')
    closes = [r for r in trace if r['event'] == 'rx_request' and r['op'] == 10]
    assert len(closes) == 1 and (closes[0]['user'], closes[0]['stream'], closes[0]['generation'], closes[0]['address']) == (0, 1, 1, 7232000)
    close_index = next(i for i, r in enumerate(trace) if r['event'] == 'rx_request' and r['op'] == 10)
    reopen_index = next(i for i, r in enumerate(trace) if i > close_index and r['event'] == 'rx_request' and r['op'] == 0)
    assert not any(r['event'] == 'rx_request' and r['op'] == 4 for r in trace[:reopen_index])
    assert any(r['event'] == 'rx_request' and r['op'] == 9 and r['generation'] == 2 for r in trace[reopen_index:])
    assert now['actual_reopen_without_global_reset'] and now['actual_reused_generation'] == 2
    assert now['actual_reopened_successful_close_refund']
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    assert len(encoding._mergeable_ranks) == 100256
    ids = encoding.encode_ordinary('hello world')
    assert ids == now['actual_reopened_dma_ids_returned'] == [15339, 1917]
    expected = b''
    for token in ids:
        decoded = encoding.decode_single_token_bytes(token)
        packet = varint(17 << 3 | 2) + varint(len(decoded)) + decoded
        expected += b'\0' + len(packet).to_bytes(4, 'big') + packet
    assert now['actual_reopened_native_response_hex'] == expected.hex()
    assert native['native_complete_grpc_calls'] == 2 and native['native_wire_frames'] == 16
    assert native['actual_receive_pool_ownership']['receive_memory_commands'] == native['actual_receive_pool_ownership']['receive_memory_acks'] == 334
    replay = root / 'build/validation/receive-fatal-generation-replay'
    replay_inputs = set(generation['input_sha256']) | {
        'tools/generate_receive_fatal_experiment.py', 'tools/generate_receive_pool_experiment.py',
        'tools/generate_two_fpga_application.py', 'tools/generate_bidirectional_application.py'}
    assert generation['generator_sha256'] == sha(root / 'tools/generate_receive_fatal_experiment.py')
    for name in sorted(replay_inputs):
        path = root / name
        assert name not in generation['input_sha256'] or sha(path) == generation['input_sha256'][name]
        destination = replay / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    subprocess.run([sys.executable, str(replay / 'tools/generate_receive_fatal_experiment.py')], check=True, capture_output=True, text=True)
    for name, h in generation['generated_sha256'].items():
        assert sha(replay / 'build/experiments/receive-fatal/rtl' / name) == h
    result = dict(phase='fatal_retirement_verified_goaway_still_failing',
        verified_utc=datetime.now(timezone.utc).isoformat(), executions=records,
        executed_parser_sha256=current_dag, generation_sha256=sha(folder / 'generation.json'),
        actual_original_protocol_cause_preserved=True, actual_closed_connection_no_refund_verified=True,
        actual_receive_stream_retirement_verified=True, actual_same_arena_reopen_and_rpc_rekey_verified=True,
        independent_native_tokenizer_and_response_reference_verified=True, generator_replay_verified=True,
        local_connection_error_goaway_verified=False, full_receive_negative_matrix_verified=False,
        current_full_padding_regression_verified=False, current_interleaved_regression_verified=False,
        current_native_implementation_verified=False, full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/receive-fatal-evidence' / key
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    for path in (Path(__file__), root / 'tools/generate_receive_fatal_experiment.py', root / 'sim/cocotb/test_raw_receive_errors.py'):
        shutil.copy2(path, evidence / path.name)
    result.update(key=key, evidence_folder=str(evidence))
    (root / 'build/validation/receive-fatal-experiment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, full_system_complete=False)))


if __name__ == '__main__':
    main()
