"""Bind AXI-visible induction to both devices and the actual joined regressions."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser_args = argparse.ArgumentParser()
    parser_args.add_argument('--with-close-faults', action='store_true')
    args = parser_args.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/experiments/packer-keep'
    generation = json.loads((folder / 'generation.json').read_text())
    base = json.loads((root / 'build/validation/local-cancel-experiment.json').read_text())
    formal = json.loads((root / 'build/validation/packer-keep-formal.json').read_text())
    assert formal['generation_sha256'] == sha(folder / 'generation.json')
    assert formal['widths'] == [128, 512] and formal['induction_length'] == 1
    assert formal['all_ready_valid_keep_last_user_and_count_equal'] and formal['all_kept_data_equal_including_held_cycles']
    assert formal['proof_log_sha256'] == sha(folder / 'formal/proof.log')
    assert 'Induction step proven: SUCCESS!' in (folder / 'formal/proof.log').read_text()
    for n, h in generation['formal_sha256'].items():
        assert sha(folder / 'formal' / n) == h
    expected = {'rtl/' + n: h for n, h in generation['generated_sha256'].items()}
    executions, parser_hashes, tokenizer_hashes = {}, None, None
    closure_cache = {}

    def checked_closure(top, source, inputs):
        signature = (top, tuple(sorted((n,h) for n,h in inputs.items() if n.startswith('rtl/') and n.endswith('.v'))))
        if signature not in closure_cache:
            closure_cache[signature] = {n:p.relative_to(source) for n,p in closure(top,source).items()}
        return {n:source/p for n,p in closure_cache[signature].items()}

    selected = [
        ('native', 'packer_keep_native', 'native'),
        ('credit_cancel', 'packer_keep_zero_window_reopen', 'duplex'),
        ('gpu_drain', 'packer_keep_held_trailer', 'duplex')]
    if args.with_close_faults:
        assert base['fatal_close_ack_fault_matrix_verified']
        selected += [('close_fault_'+str(n),'packer_keep_close_fault_'+str(n),'duplex') for n in range(14)]
    for label, snapshot, profile in selected:
        archive = root / 'build/wsl-reports' / ('raw_envelope_' + snapshot)
        source = archive / 'execution-sources'
        inputs = json.loads((archive / 'inputs.json').read_text())
        report = json.loads((archive / 'report.json').read_text())
        state = json.loads((archive / 'snapshot.json').read_text())
        accepted = json.loads((archive / 'acceptance.json').read_text())
        assert state['exit_code'] == 0 and report['phase'] == accepted['phase'] == 'passed'
        assert report['profile'] == profile and report['tests'] == 1 and report['failures'] == 0
        assert report['input_sha256'] == inputs and report['acceptance_sha256'] == sha(archive / 'acceptance.json')
        for n, h in inputs.items():
            assert sha(source / n) == h
            if n.startswith('native-vendor/'):
                assert sha(root / '.venv312/Lib/site-packages' / n.split('/', 1)[1]) == h
        cases = ET.parse(archive / 'results.xml')
        assert len(cases.findall('.//testcase')) == 1 and not cases.findall('.//failure') and not cases.findall('.//error')
        parser = checked_closure('http2_enveloped_parser_application', source, inputs)
        tokenizer = checked_closure('tokenizer_fpga_memory_subsystem', source, inputs)
        assert (len(parser), len(tokenizer)) == (75, 22)
        p_hashes = {n: sha(p) for n, p in parser.items()}
        t_hashes = {n: sha(p) for n, p in tokenizer.items()}
        assert parser_hashes is None or parser_hashes == p_hashes
        assert tokenizer_hashes is None or tokenizer_hashes == t_hashes
        parser_hashes, tokenizer_hashes = p_hashes, t_hashes
        assert set(p_hashes) == set(base['executed_parser_sha256'])
        assert [n for n, h in p_hashes.items() if h != base['executed_parser_sha256'][n]] == ['axis_byte_packer']
        assert 'axis_byte_packer' in tokenizer
        for p in [*parser.values(), *tokenizer.values()]:
            n = p.relative_to(source).as_posix()
            assert inputs[n] == expected.get(n, sha(source_path(root, n)))
        previous = base['executions'][label]
        previous_source = root / 'build/wsl-reports' / ('raw_envelope_' + previous['snapshot']) / 'execution-sources'
        test = 'test_raw_grpc_enveloped.py' if profile == 'native' else 'test_raw_grpc_duplex.py'
        assert inputs['sim/cocotb/' + test] == sha(previous_source / 'sim/cocotb' / test)
        assert inputs['sim/cocotb_two_fpga_enveloped_top.sv'] == sha(previous_source / 'sim/cocotb_two_fpga_enveloped_top.sv')
        assert inputs['build/bidirectional-fixtures/memory.mem'] == previous['inputs_sha256']['build/bidirectional-fixtures/memory.mem']
        assert accepted == previous['acceptance'], label
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        executions[label] = dict(snapshot=snapshot, acceptance=accepted, inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    replay = root / 'build/validation/packer-keep-generation-replay'
    paths = set(generation['input_sha256']) | {'tools/generate_packer_keep_experiment.py',
        'tools/generate_receive_pool_experiment.py', 'tools/generate_two_fpga_application.py',
        'tools/generate_bidirectional_application.py'}
    assert generation['generator_sha256'] == sha(root / 'tools/generate_packer_keep_experiment.py')
    for n in paths:
        assert n not in generation['input_sha256'] or sha(source_path(root, n)) == generation['input_sha256'][n]
        destination = replay / n
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path(root, n), destination)
    subprocess.run([sys.executable, str(replay / 'tools/generate_packer_keep_experiment.py')], check=True, capture_output=True, text=True)
    for subfolder, hashes in (('rtl', generation['generated_sha256']), ('formal', generation['formal_sha256'])):
        for n, h in hashes.items():
            assert sha(replay / 'build/experiments/packer-keep' / subfolder / n) == h
    result = dict(phase='packer_keep_formal_and_joined_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions, executed_parser_sha256=parser_hashes, executed_tokenizer_sha256=tokenizer_hashes,
        exact_parser_modules=75, exact_tokenizer_modules=22, parser_memory_clients=19, tokenizer_memory_clients=9,
        baseline_direct_audit_key=base['key'], formal_key=formal['key'], formal_manifest_sha256=sha(root / 'build/validation/packer-keep-formal.json'),
        generation_sha256=sha(folder / 'generation.json'), only_changed_rtl_module='axis_byte_packer',
        all_three_acceptance_records_equal_baseline=True, all_acceptance_records_equal_baseline=True,
        generator_and_formal_source_replay_verified=True,
        complete_model_and_native_reference_verified=True, both_device_implementations_require_updated_verification=True,
        current_full_native_corpus_verified=False, fatal_close_ack_fault_matrix_verified=args.with_close_faults,
        actual_fatal_close_ack_faults=14 if args.with_close_faults else 0,
        current_native_implementation_verified=False, timing_improvement_verified=False,
        physical_interfaces_verified=False, full_system_complete=False, verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/packer-keep-evidence' / key
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    for path in (Path(__file__), root / 'tools/generate_packer_keep_experiment.py', folder / 'generation.json'):
        shutil.copy2(path, evidence / path.name)
    result.update(key=key, evidence_folder=str(evidence))
    (root / 'build/validation/packer-keep-experiment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, executions=len(executions), changed_module='axis_byte_packer')))


if __name__ == '__main__':
    main()
