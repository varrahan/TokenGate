"""Bind real GOAWAY/history/host-close and offered-GPU drain to executed RTL."""
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

from rtl_paths import source_path


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/experiments/local-error'
    generation = json.loads((folder / 'generation.json').read_text())
    overrides = {'rtl/' + n: h for n, h in generation['generated_sha256'].items()}
    assert len(overrides) == 18
    executions = {}
    hashes = None
    for label, name, profile, test, test_file, overlay in (
        ('native', 'local_error_drain_native', 'native', 'native_calls_return_actual_dma_ids_and_complete_grpc',
         'test_raw_grpc_enveloped.py', 'test_raw_grpc_enveloped.py'),
        ('goaway', 'local_error_drain_close', 'receive-errors', 'fatal_padding_error_emits_goaway_without_close_refund',
         'test_raw_receive_errors.py', 'test_raw_receive_errors.py'),
        ('context_fault', 'local_error_drain_context_fault', 'receive-errors', 'fatal_padding_error_emits_goaway_without_close_refund',
         'test_raw_receive_errors.py', 'fault-0/test_raw_receive_errors.py'),
        ('history_fault', 'local_error_drain_highwater_fault', 'receive-errors', 'fatal_padding_error_emits_goaway_without_close_refund',
         'test_raw_receive_errors.py', 'fault-1/test_raw_receive_errors.py'),
        ('gpu_drain', 'local_error_held_gpu_trailer', 'duplex', 'fatal_packet_drains_offered_trailer_and_gpu_owner',
         'test_raw_grpc_duplex.py', 'test_raw_grpc_duplex.py')):
        archive = root / 'build/wsl-reports' / ('raw_envelope_' + name)
        source = archive / 'execution-sources'
        inputs = json.loads((archive / 'inputs.json').read_text())
        report = json.loads((archive / 'report.json').read_text())
        snapshot = json.loads((archive / 'snapshot.json').read_text())
        accepted = json.loads((archive / 'acceptance.json').read_text())
        assert report['phase'] == accepted['phase'] == 'passed' and snapshot['exit_code'] == 0
        assert report['profile'] == snapshot['profile'] == profile and report['tests'] == 1 and report['failures'] == 0
        assert report['input_sha256'] == inputs and report['acceptance_sha256'] == sha(archive / 'acceptance.json')
        for n, h in inputs.items():
            assert sha(source / n) == h, (name, n)
            if n.startswith('native-vendor/'):
                assert sha(root / '.venv312/Lib/site-packages' / n.split('/', 1)[1]) == h
        xml = ET.parse(archive / 'results.xml')
        cases = xml.findall('.//testcase')
        assert len(cases) == 1 and cases[0].attrib['name'] == test
        assert not xml.findall('.//failure') and not xml.findall('.//error')
        dag = closure('http2_enveloped_parser_application', source)
        tokenizer = closure('tokenizer_fpga_memory_subsystem', source)
        assert (len(dag), len(tokenizer)) == (74, 22)
        assert 'http2_local_error_response' in dag
        current = {n: sha(p) for n, p in dag.items()}
        assert hashes is None or current == hashes
        hashes = current
        for path in [*dag.values(), *tokenizer.values()]:
            n = path.relative_to(source).as_posix()
            assert inputs[n] == overrides.get(n, sha(source_path(root, n))), n
        expected = generation['fault_test_sha256'][overlay] if '/' in overlay else generation['sim_sha256'][overlay]
        assert inputs['sim/cocotb/' + test_file] == expected
        assert inputs['sim/cocotb_two_fpga_enveloped_top.sv'] == generation['sim_sha256']['cocotb_two_fpga_enveloped_top.sv']
        if label != 'native':
            assert inputs['sim/cocotb/local_error_witness.py'] == sha(root / 'sim/cocotb/local_error_witness.py')
        if label in ('context_fault', 'history_fault'):
            assert inputs['sim/cocotb/local_error_fault_witness.py'] == sha(root / 'sim/cocotb/local_error_fault_witness.py')
        harness = (source / 'sim/cocotb_two_fpga_enveloped_top.sv').read_text()
        assert 'external_memory_fabric #(.CLIENTS(19)) p_fabric(' in harness and 'client<28' in harness
        assert 'assign mem_ready[27*1+:1]=p_mem_ready[18*1+:1];' in harness
        assert 'assign fabric_status[27*8+:8]=p_fabric_status[18*8+:8];' in harness
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        fixture = source / 'build/bidirectional-fixtures'
        manifest = json.loads((fixture / 'fixture_manifest.json').read_text())
        loaded = b''.join(int(s, 16).to_bytes(8, 'little') for s in (fixture / 'memory.mem').read_text().splitlines())
        original = root / 'build/scu35/image/external_memory.bin'
        assert len(loaded) == original.stat().st_size == 8388608
        assert sha(original) == 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
        assert hashlib.sha256(loaded).hexdigest() == manifest['loaded_image_sha256']
        assert loaded[:6903552] == original.read_bytes()[:6903552]
        executions[label] = dict(snapshot=name, acceptance=accepted, inputs_sha256=inputs,
            archive_files_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()})
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    assert len(encoding._mergeable_ranks) == 100256
    ids = encoding.encode_ordinary('hello world')
    assert ids == [15339, 1917]
    packets = []
    for token in ids:
        raw = encoding.decode_single_token_bytes(token)
        body = varint(17 << 3 | 2) + varint(len(raw)) + raw
        packets.append(b'\0' + len(body).to_bytes(4, 'big') + body)
    native = executions['native']['acceptance']
    assert [native[k] for k in ('actual_raw_packets', 'actual_header_bindings', 'native_complete_grpc_calls',
        'actual_forward_dma_ids', 'actual_gpu_descriptors_accepted', 'actual_captured_dma_ids_returned', 'native_wire_frames')] == [11, 6, 2, 6, 8, 4, 16]
    assert native['parser_memory_clients'] == 19 and native['tokenizer_memory_clients'] == 9
    assert native['expected_response_records']['3'] == [p.hex() for p in packets]
    for label in ('goaway', 'context_fault', 'history_fault'):
        accepted = executions[label]['acceptance']
        assert accepted['actual_reopen_without_global_reset'] and accepted['actual_reused_generation'] == 2
        assert accepted['actual_reopened_dma_ids_returned'] == ids
        assert accepted['actual_reopened_native_response_hex'] == b''.join(packets).hex()
        assert accepted['actual_reopened_successful_close_refund']
        assert accepted['actual_receive_connection_available'] == 65528 and accepted['actual_receive_connection_pending'] == 0
        assert accepted['actual_receive_stream_closed'] == 1
        assert accepted['actual_receive_fault'] == accepted['actual_receive_recovery_required'] == 0
        proof = accepted['local_error_ownership']
        assert proof['held_host_close_cycles'] == 13
        assert proof['actual_read_acks'][-1]['clock'] < proof['host_close_retired_clock'] < proof['first_public_packet_result_clock']
        if label == 'goaway':
            assert accepted['packet_result']['packet_status'] == 4 and accepted['actual_goaway'] == [[1, 1]]
            assert accepted['actual_wire_hex'] == ['0000080700000000000000000100000001']
            assert proof['held_goaway_cycles'] == 17
            assert [r['address'] for r in proof['actual_reads']] == [7231232, 7231392]
            assert [r['data'] for r in proof['actual_read_acks']] == [0, (1 << 32) | 0x48325731]
            assert proof['actual_read_acks'][-1]['clock'] < proof['wire_retired_clock'] < proof['host_close_retired_clock']
        else:
            target = 0 if label == 'context_fault' else 1
            assert accepted['packet_result']['packet_status'] == 15 and accepted['actual_goaway'] == [] and accepted['actual_wire_hex'] == []
            assert proof['actual_fault_target'] == target and proof['goaway_not_offered']
            assert len(proof['actual_reads']) == len(proof['actual_read_acks']) == target + 1
            assert proof['actual_read_acks'][-1]['status'] == proof['actual_memory_error'] == 0x75
    drain = executions['gpu_drain']['acceptance']
    for k in ('actual_failed_packet_waited_for_gpu_and_wire_drain', 'actual_successful_gpu_result_preserved', 'actual_native_stream_completed_before_goaway'):
        assert drain[k]
    assert drain['held_prior_final_trailer_cycles'] == 17 and drain['actual_captured_dma_ids_returned'] == ids
    assert drain['actual_wire_types_after_fatal_packet'] == [1, 7]
    proof = drain['local_error_ownership']
    assert proof['held_goaway_cycles'] == 17 and proof['held_host_close_cycles'] == 13
    assert proof['wire_retired_clock'] < proof['host_close_retired_clock'] < proof['first_public_packet_result_clock']
    assert drain['stalled_send_credit_abort_verified'] is False
    replay = root / 'build/validation/local-error-generation-replay'
    paths = set(generation['input_sha256']) | {
        'tools/generate_local_error_experiment.py', 'tools/generate_receive_pool_experiment.py',
        'tools/generate_two_fpga_application.py', 'tools/generate_bidirectional_application.py'}
    assert generation['generator_sha256'] == sha(root / 'tools/generate_local_error_experiment.py')
    for name in sorted(paths):
        path = source_path(root, name)
        assert name not in generation['input_sha256'] or sha(path) == generation['input_sha256'][name]
        destination = replay / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    subprocess.run([sys.executable, str(replay / 'tools/generate_local_error_experiment.py')], check=True, capture_output=True, text=True)
    for subfolder, expected in (('rtl', generation['generated_sha256']), ('sim', generation['sim_sha256']), ('sim', generation['fault_test_sha256'])):
        for name, h in expected.items():
            assert sha(replay / 'build/experiments/local-error' / subfolder / name) == h, name
    result = dict(phase='actual_local_error_goaway_close_and_gpu_drain_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), executions=executions,
        executed_parser_sha256=hashes, exact_parser_modules=74, exact_tokenizer_modules=22,
        parser_memory_clients=19, tokenizer_memory_clients=9, generation_sha256=sha(folder / 'generation.json'),
        actual_highwater_goaway_wire_host_close_packet_order_verified=True, both_actual_history_read_ack_faults_verified=True,
        actual_offered_final_trailer_and_gpu_result_drain_before_rollback_verified=True,
        actual_same_arena_reopen_and_rpc_rekey_verified=True, complete_model_and_native_reference_verified=True,
        generator_replay_verified=True, current_native_implementation_verified=False,
        stalled_send_credit_abort_verified=False, complete_error_phase_matrix_verified=False,
        current_full_padding_verified=False, current_interleaved_partial_records_verified=False,
        full_native_corpus_verified=False, physical_interfaces_verified=False, full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/local-error-evidence' / key
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    for path in (Path(__file__), root / 'tools/generate_local_error_experiment.py', source_path(root, 'rtl/http2_local_error_response.v'),
                 root / 'sim/cocotb/local_error_witness.py', root / 'sim/cocotb/local_error_fault_witness.py', root / 'sim/cocotb/test_local_error_gpu_drain.py'):
        shutil.copy2(path, evidence / path.name)
    result.update(key=key, evidence_folder=str(evidence))
    (root / 'build/validation/local-error-experiment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, full_system_complete=False)))


if __name__ == '__main__':
    main()
