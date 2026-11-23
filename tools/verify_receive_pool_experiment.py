"""Bind real shared-pool ownership witnesses to the executed Parser closure."""
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
    folder = root / 'build/experiments/receive-pool-locked'
    generation = json.loads((folder / 'generation.json').read_text())
    overrides = {'rtl/' + n: h for n, h in generation['generated_sha256'].items()}
    assert len(overrides) == 16
    records = {}
    executed = None
    for label, name, profile, test, filename in (
        ('native', 'receive_pool_native_ownership', 'native',
         'native_calls_return_actual_dma_ids_and_complete_grpc', 'test_raw_grpc_enveloped.py'),
        ('padding', 'receive_pool_padding_ownership', 'receive-flow',
         'native_padding_credit_replenishment_allows_next_real_prompt', 'test_raw_receive_flow.py'),
        ('interleaved', 'receive_pool_interleaved_host_queues', 'duplex',
         'interleaved_records_hold_actual_directory_ownership', 'test_raw_grpc_duplex.py')):
        archive = root / 'build/wsl-reports' / ('raw_envelope_' + name)
        source = archive / 'execution-sources'
        inputs = json.loads((archive / 'inputs.json').read_text())
        report = json.loads((archive / 'report.json').read_text())
        snapshot = json.loads((archive / 'snapshot.json').read_text())
        accepted = json.loads((archive / 'acceptance.json').read_text())
        assert report['phase'] == accepted['phase'] == 'passed' and snapshot['exit_code'] == 0
        assert report['profile'] == snapshot['profile'] == profile
        assert report['tests'] == 1 and report['failures'] == 0
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
        assert (len(dag), len(tokenizer)) == (73, 22)
        assert {'directory_pool_lock_arbiter', 'http2_receive_pool_gate',
                'grpc_pool_locked_stream_store', 'http2_keyed_receive_credit_store'} <= dag.keys()
        hashes = {module: sha(path) for module, path in dag.items()}
        assert executed is None or hashes == executed
        executed = hashes
        for path in [*dag.values(), *tokenizer.values()]:
            n = path.relative_to(source).as_posix()
            assert inputs[n] == overrides.get(n, sha(root / n)), (name, n)
        for n in ('receive_pool_witness.py',):
            assert inputs['sim/cocotb/' + n] == sha(root / 'sim/cocotb' / n)
        assert inputs['sim/cocotb/' + filename] == generation['sim_sha256'][filename]
        assert inputs['sim/cocotb_two_fpga_enveloped_top.sv'] == generation['sim_sha256']['cocotb_two_fpga_enveloped_top.sv']
        assert accepted['parser_memory_clients'] == 18 and accepted['complete_model_prefix_immutable']
        assert accepted['full_system_complete'] is False
        fixture = source / 'build/bidirectional-fixtures'
        manifest = json.loads((fixture / 'fixture_manifest.json').read_text())
        loaded = b''.join(int(s, 16).to_bytes(8, 'little') for s in (fixture / 'memory.mem').read_text().splitlines())
        original = root / 'build/scu35/image/external_memory.bin'
        assert sha(original) == 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
        assert len(loaded) == original.stat().st_size == 8388608
        assert hashlib.sha256(loaded).hexdigest() == manifest['loaded_image_sha256']
        assert loaded[:6903552] == original.read_bytes()[:6903552]
        counts = accepted['actual_receive_pool_ownership']
        assert counts['receive_grants'] == counts['receive_unlocks'] == counts['ordinary_commands'] > 0
        assert counts['receive_memory_commands'] == counts['receive_memory_acks'] > 0
        assert counts['receive_lock_cycles'] > counts['receive_grants']
        assert counts['init_commands'] > 0 and counts['close_commands'] > 0
        records[label] = dict(snapshot=name, acceptance=accepted, input_sha256=inputs,
            archive_files_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()})
    native = records['native']['acceptance']
    padding = records['padding']['acceptance']
    interleaved = records['interleaved']['acceptance']
    assert [native[n] for n in ('actual_raw_packets', 'actual_header_bindings', 'native_complete_grpc_calls',
        'actual_forward_dma_ids', 'actual_gpu_descriptors_accepted', 'native_wire_frames')] == [11, 6, 2, 6, 8, 16]
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    assert len(encoding._mergeable_ranks) == 100256
    ids = encoding.encode_ordinary('hello world')
    assert ids == [15339, 1917]
    protobuf = []
    for token in ids:
        raw = encoding.decode_single_token_bytes(token)
        body = varint(17 << 3 | 2) + varint(len(raw)) + raw
        protobuf.append(b'\0' + len(body).to_bytes(4, 'big') + body)
    assert native['expected_response_records']['3'] == [p.hex() for p in protobuf]
    assert interleaved['native_response_bytes'] == b''.join(protobuf).hex()
    assert interleaved['actual_captured_dma_returns'] == [[s, t, i] for s in (1, 3) for i, t in enumerate(ids)]
    assert interleaved['actual_receive_pool_ownership']['save_blocked_cycles'] > 0
    assert interleaved['actual_interleaved_data_frames'] == 36
    assert interleaved['actual_successful_closes'] == 2 and interleaved['native_complete_grpc_calls'] == 2
    assert padding['native_padding_payload_bytes'] == 65535 and padding['actual_window_update_frames'] == 513
    assert padding['held_actual_wire_cycles'] == 17 and padding['actual_dma_ids_returned'] == ids
    debits = padding['actual_receive_debits']
    assert [d['amount'] for d in debits] == [256] * 255 + [255, 29]
    updates = padding['actual_receive_updates']
    assert [(u['stream'], u['amount']) for u in updates] == [(s, 256) for _ in range(255) for s in (1, 0)] + [(1, 255), (0, 255), (0, 29)]
    for u in updates:
        assert u['intent_ack_clock'] < u['wire_clock'] < u['available_ack_clock'] <= u['clear_ack_clock'] < u['result_ack_clock']
    # Rebuild every override and passive fixture from the recorded inputs.
    replay = root / 'build/validation/receive-pool-generation-replay'
    replay_inputs = set(generation['input_sha256']) | {
        'tools/generate_receive_pool_experiment.py', 'tools/generate_two_fpga_application.py',
        'tools/generate_bidirectional_application.py'}
    assert generation['generator_sha256'] == sha(root / 'tools/generate_receive_pool_experiment.py')
    for name in sorted(replay_inputs):
        path = root / name
        assert name not in generation['input_sha256'] or sha(path) == generation['input_sha256'][name]
        target = replay / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    subprocess.run([sys.executable, str(replay / 'tools/generate_receive_pool_experiment.py')], check=True, capture_output=True, text=True)
    for subfolder, hashes in (('rtl', generation['generated_sha256']), ('sim', generation['sim_sha256'])):
        for name, h in hashes.items():
            assert sha(replay / 'build/experiments/receive-pool-locked' / subfolder / name) == h, name
    result = dict(phase='actual_receive_pool_direct_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        exact_parser_modules=73, exact_tokenizer_modules=22, parser_memory_clients=18, tokenizer_memory_clients=9,
        executed_parser_sha256=executed, executions=records, generation_sha256=sha(folder / 'generation.json'),
        generator_replay_verified=True, actual_pool_exclusion_under_interleaved_save_verified=True,
        actual_init_and_close_owner_reuse_verified=True, actual_padding_commit_and_close_refund_verified=True,
        complete_model_and_native_tokenizer_reference_verified=True,
        current_native_synthesis_verified=False, current_native_route_verified=False,
        full_receive_negative_matrix_verified=False, fatal_connection_refund_policy_verified=False,
        open_rpc_reclamation_verified=False, retained_reset_verified=False, full_native_corpus_verified=False,
        whole_rpc_gpu_image_leases_verified=False, physical_interfaces_verified=False, full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/receive-pool-evidence' / key
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    for path in (Path(__file__), root / 'tools/generate_receive_pool_experiment.py',
                 root / 'sim/cocotb/receive_pool_witness.py', root / 'sim/cocotb/test_receive_pool_interleaved.py'):
        shutil.copy2(path, evidence / path.name)
    result.update(key=key, evidence_folder=str(evidence))
    (root / 'build/validation/receive-pool-experiment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, full_system_complete=False)))


if __name__ == '__main__':
    main()
