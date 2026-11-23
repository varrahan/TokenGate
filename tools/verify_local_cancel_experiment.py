"""Bind fatal credit-park cancellation and same-arena reopen to actual RTL."""
import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--with-close-faults', action='store_true', help='Also require all fourteen real fatal-close ACK fault phases')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/experiments/local-cancel'
    generation = json.loads((folder / 'generation.json').read_text())
    overrides = {'rtl/' + n: h for n, h in generation['generated_sha256'].items()}
    executions, hashes = {}, None
    closure_cache = {}

    def checked_closure(top, source, inputs):
        # Every input was hashed against its immutable execution copy below.
        # Reuse a parsed graph only for byte-identical complete RTL file sets;
        # paths returned to the caller still identify this execution's copies.
        signature = (top, tuple(sorted((n, h) for n, h in inputs.items() if n.startswith('rtl/') and n.endswith('.v'))))
        if signature not in closure_cache:
            closure_cache[signature] = {n: p.relative_to(source) for n, p in closure(top, source).items()}
        return {n: source / p for n, p in closure_cache[signature].items()}
    cases = [
        ('native', 'local_cancel_scoped_native', 'native', 'test_raw_grpc_enveloped.py', 'test_raw_grpc_enveloped.py'),
        ('goaway', 'local_cancel_current_goaway', 'receive-errors', 'test_raw_receive_errors.py', 'test_raw_receive_errors.py'),
        ('context_fault', 'local_cancel_current_history_fault_0', 'receive-errors', 'test_raw_receive_errors.py', 'fault-0/test_raw_receive_errors.py'),
        ('history_fault', 'local_cancel_current_history_fault_1', 'receive-errors', 'test_raw_receive_errors.py', 'fault-1/test_raw_receive_errors.py'),
        ('gpu_drain', 'local_cancel_current_held_trailer', 'duplex', 'test_raw_grpc_duplex.py', 'held-trailer/test_raw_grpc_duplex.py'),
        ('credit_cancel', 'local_cancel_zero_window_reopen_fault_capable', 'duplex', 'test_raw_grpc_duplex.py', 'test_raw_grpc_duplex.py'),
    ]
    if args.with_close_faults:
        cases += [('close_fault_' + str(n), 'local_cancel_close_fault_' + str(n), 'duplex',
            'test_raw_grpc_duplex.py', 'close-fault-' + str(n) + '/test_raw_grpc_duplex.py') for n in range(14)]
    for label, name, profile, test_file, overlay in cases:
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
        assert len(xml.findall('.//testcase')) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        dag = checked_closure('http2_enveloped_parser_application', source, inputs)
        tokenizer = checked_closure('tokenizer_fpga_memory_subsystem', source, inputs)
        assert (len(dag), len(tokenizer)) == (75, 22)
        assert {'http2_local_return_abort', 'http2_local_error_response'} <= dag.keys()
        current = {n: sha(p) for n, p in dag.items()}
        assert hashes is None or current == hashes
        hashes = current
        for path in [*dag.values(), *tokenizer.values()]:
            n = path.relative_to(source).as_posix()
            assert inputs[n] == overrides.get(n, sha(root / n)), n
        assert inputs['sim/cocotb/' + test_file] == generation['sim_sha256'][overlay]
        assert inputs['sim/cocotb_two_fpga_enveloped_top.sv'] == generation['sim_sha256']['cocotb_two_fpga_enveloped_top.sv']
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
    assert native['expected_response_records']['3'] == [p.hex() for p in packets]
    proof = executions['credit_cancel']['acceptance']
    assert proof['actual_native_initial_stream_window'] == 0 and proof['actual_captured_dma_ids'] == ids
    assert proof['actual_gpu_cancellation_result'] == [16, 5, 1] and proof['actual_closed_reservation_status'] == 8
    for key in ('actual_gpu_lease_retained_until_result_ack', 'actual_no_new_credit_required',
                'ordinary_host_fatal_opcode_denied_before_memory', 'actual_goaway_after_gpu_retirement',
                'actual_reopen_without_global_reset', 'actual_reopened_successful_close_refund'):
        assert proof[key]
    assert proof['actual_same_rpc_address'] == 7232000 and proof['actual_reused_generation'] == 2
    assert proof['actual_reopened_dma_ids_returned'] == ids
    assert proof['actual_reopened_native_response_hex'] == b''.join(packets).hex()
    trace = proof['actual_cancel_trace']
    assert [e['event'] for e in trace] == ['actual_freeze_drained', 'actual_fatal_close_request',
        'actual_send_closed_write_ack', 'actual_fatal_close_result_ack', 'actual_closed_reservation']
    assert all(a['clock'] < b['clock'] for a, b in zip(trace, trace[1:]))
    assert [trace[1][n] for n in ('user', 'stream', 'generation', 'record_address', 'amount')] == [0, 1, 0, 0, 0]
    assert trace[2]['address'] == 0x7f0008 and trace[2]['data'] == (1 << 63) | (1 << 32)
    assert [trace[3][n] for n in ('user', 'stream', 'generation', 'address')] == [0, 1, 1, 7232000]
    assert [trace[4][n] for n in ('status', 'error', 'memory_status')] == [8, 5, 0]
    ownership = proof['local_error_ownership']
    assert ownership['held_goaway_cycles'] == 17 and ownership['held_host_close_cycles'] == 13
    assert trace[-1]['clock'] < ownership['wire_retired_clock'] < ownership['host_close_retired_clock'] < ownership['first_public_packet_result_clock']
    drain = executions['gpu_drain']['acceptance']
    assert drain['held_prior_final_trailer_cycles'] == 17 and drain['actual_wire_types_after_fatal_packet'] == [1, 7]
    assert drain['actual_successful_gpu_result_preserved'] and drain['actual_captured_dma_ids_returned'] == ids
    for label in ('goaway', 'context_fault', 'history_fault'):
        p = executions[label]['acceptance']
        assert p['actual_reopen_without_global_reset'] and p['actual_reused_generation'] == 2
        assert p['actual_reopened_dma_ids_returned'] == ids
        assert p['actual_receive_connection_available'] == 65528 and p['actual_receive_connection_pending'] == 0
        assert p['actual_goaway'] == ([[1, 1]] if label == 'goaway' else [])
        assert p['packet_result']['packet_status'] == (4 if label == 'goaway' else 15)
    if args.with_close_faults:
        for n in range(14):
            p = executions['close_fault_' + str(n)]['acceptance']
            assert p['actual_fault_phase'] == n and p['actual_memory_commands'] == n + 1
            assert p['actual_native_initial_stream_window'] == 0 and p['actual_memory_error'] == 0x75
            assert p['actual_send_closed_write_applied'] == (n == 13)
            for key in ('actual_freeze_and_gpu_lease_retained', 'actual_new_admission_fenced',
                        'actual_no_error_replay_or_fabricated_completion', 'actual_goaway_and_host_close_not_published'):
                assert p[key]
            assert p['recovery_after_uncertain_close_verified'] is False

    counter = root / 'build/wsl-reports/raw_envelope_local_error_zero_window_counterexample'
    counter_state = json.loads((counter / 'snapshot.json').read_text())
    failed = json.loads((counter / 'failure.json').read_text())
    assert counter_state['exit_code'] != 0 and failed['phase'] == 'fatal_credit_park_deadlock'
    assert failed['actual_credit_parked'] == failed['actual_return_pending'] == failed['actual_gpu_lease'] == 1
    baseline = json.loads((root / 'build/validation/local-error-experiment.json').read_text())
    assert {n: sha(p) for n, p in closure('http2_enveloped_parser_application', counter / 'execution-sources').items()} == baseline['executed_parser_sha256']

    replay = root / 'build/validation/local-cancel-generation-replay'
    paths = set(generation['input_sha256']) | {'tools/generate_local_cancel_experiment.py',
        'tools/generate_receive_pool_experiment.py', 'tools/generate_two_fpga_application.py',
        'tools/generate_bidirectional_application.py'}
    assert generation['generator_sha256'] == sha(root / 'tools/generate_local_cancel_experiment.py')
    for n in sorted(paths):
        path = root / n
        assert n not in generation['input_sha256'] or sha(path) == generation['input_sha256'][n]
        destination = replay / n
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    subprocess.run([sys.executable, str(replay / 'tools/generate_local_cancel_experiment.py')], check=True, capture_output=True, text=True)
    for subfolder, expected in (('rtl', generation['generated_sha256']), ('sim', generation['sim_sha256'])):
        for name, h in expected.items():
            assert sha(replay / 'build/experiments/local-cancel' / subfolder / name) == h, name
    result = dict(phase='actual_local_credit_cancel_and_reopen_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions, executed_parser_sha256=hashes, exact_parser_modules=75, exact_tokenizer_modules=22,
        parser_memory_clients=19, tokenizer_memory_clients=9, generation_sha256=sha(folder / 'generation.json'),
        original_zero_window_deadlock_reproduced=True, actual_freeze_durable_close_and_closed_reservation_verified=True,
        actual_gpu_ack_before_goaway_and_host_close_verified=True, actual_same_arena_reopen_and_rpc_rekey_verified=True,
        ordinary_host_fatal_opcode_denied_before_memory=True, complete_model_and_native_reference_verified=True,
        generator_replay_verified=True, current_native_implementation_verified=False, complete_error_phase_matrix_verified=False,
        fatal_close_ack_fault_matrix_verified=args.with_close_faults, actual_fatal_close_ack_faults=14 if args.with_close_faults else 0,
        counterexample_archive_sha256={p.name:sha(p) for p in counter.iterdir() if p.is_file()},
        baseline_direct_audit_key=baseline['key'], current_full_padding_verified=False,
        current_interleaved_partial_records_verified=False, full_native_corpus_verified=False,
        physical_interfaces_verified=False, full_system_complete=False, verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/local-cancel-evidence' / key
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    shutil.copy2(folder / 'generation.json', evidence / 'generation.json')
    for n in ('tools/generate_local_cancel_experiment.py', 'sim/cocotb/test_local_error_credit_stall.py', 'rtl/http2_local_return_abort.v'):
        destination = evidence / n
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / n, destination)
    result.update(key=key, evidence_folder=str(evidence))
    (root / 'build/validation/local-cancel-experiment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, executions=len(executions), parser_modules=75)))


if __name__ == '__main__':
    main()
