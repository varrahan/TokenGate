"""Bind unchanged full protocol/fault replays to the one-line idle correction."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path, source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    read = lambda path: json.loads(path.read_text())
    folder = root / 'build/experiments/freeze-idle'
    generation_path = folder / 'generation.json'
    generation = read(generation_path)
    generator = root / 'tools/generate_freeze_idle_experiment.py'
    assert sha(generator) == generation['generator_sha256']
    parent_path = root / 'build/validation/progress-format-corpus.json'
    parent = read(parent_path)
    assert parent['key'] == generation['parent_corpus_audit_key'] == '6dd529d376e06926'
    for name, digest in generation['inputs_sha256'].items():
        assert sha(source_path(root, name)) == digest
    for name, digest in generation['outputs_sha256'].items():
        assert sha(folder / name) == digest
    old = root / 'build/wsl-reports/raw_envelope_progress_format_full_native_corpus/execution-sources/rtl/rpc_grpc_http2_return.v'
    text = (folder / 'rtl/rpc_grpc_http2_return.v').read_text()
    assert text.replace(generation['new_assignment'], generation['old_assignment']) == old.read_text()
    stripped = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
    assert len(re.findall(r'(?<!\.)\bidle\b', stripped)) == 2
    helpers = [root / 'tools/verify_two_fpga_application.py', root / 'tools/generate_two_fpga_application.py',
               root / 'tools/generate_bidirectional_application.py']
    with tempfile.TemporaryDirectory(prefix='fi-', dir=root / 'build') as temporary:
        replay = Path(temporary)
        assert replay.resolve().is_relative_to((root / 'build').resolve())
        for relative in list(generation['inputs_sha256']) + [str(source_relative(path, root)) for path in [generator, parent_path, *helpers]]:
            target = replay / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path(root, relative), target)
        result = subprocess.run([sys.executable, str(replay / 'tools/generate_freeze_idle_experiment.py')],
                                capture_output=True, text=True)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert read(replay / 'build/experiments/freeze-idle/generation.json') == generation
    cases = {}
    for audit_name, key in [('progress-format-regressions', '736eec1fa78adf7d'),
                           ('progress-format-experiment', 'c7aebf98ee6f7e25')]:
        audit = read(root / 'build/validation' / (audit_name + '.json'))
        assert audit['key'] == key
        cases.update({name: (key, state) for name, state in audit['executions'].items()})
    assert set(cases) == {'native', 'other_connection', 'owned_gpu_drain', 'external_denial',
                          'retained_shutdown', 'retained_native', 'all_ledger_faults'}
    executions = {}
    parser_hashes = tokenizer_hashes = None
    for case, (key, baseline) in cases.items():
        name = 'freeze_idle_' + case + '_20261122'
        archive = root / 'build/wsl-reports' / ('raw_envelope_' + name)
        source = archive / 'execution-sources'
        inputs, report, snapshot, accepted = (read(archive / name) for name in
            ('inputs.json', 'report.json', 'snapshot.json', 'acceptance.json'))
        launch = read(root / 'build/validation' / (name + '-launch.json'))
        assert launch['phase'] == 'completed' and launch['exit_code'] == snapshot['exit_code'] == 0
        assert snapshot['baseline_audit_key'] == launch['baseline_audit_key'] == key
        assert snapshot['baseline_snapshot'] == baseline['snapshot']
        assert report['phase'] == accepted['phase'] == 'passed'
        assert report['profile'] == snapshot['profile'] == baseline['profile']
        assert report['tests'] == 1 and report['failures'] == 0
        assert inputs == report['input_sha256'] == launch['inputs_sha256']
        assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
        for relative, digest in inputs.items():
            assert sha(source / relative) == digest, (case, relative)
            if relative.startswith('native-vendor/'):
                assert sha(root / '.venv312/Lib/site-packages' / relative.split('/', 1)[1]) == digest
        assert inputs.keys() == baseline['inputs_sha256'].keys()
        assert [relative for relative in inputs if inputs[relative] != baseline['inputs_sha256'][relative]] == ['rtl/rpc_grpc_http2_return.v']
        assert inputs['rtl/rpc_grpc_http2_return.v'] == generation['outputs_sha256']['rtl/rpc_grpc_http2_return.v']
        assert sha(archive / 'protocol-runner-used.py') == launch['driver_sha256']
        assert sha(archive / 'freeze-idle-generation.json') == sha(generation_path)
        xml = ET.parse(archive / 'results.xml')
        assert len(xml.findall('.//testcase')) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        current_parser = {name: sha(path) for name, path in closure('http2_enveloped_parser_application', source).items()}
        current_tokenizer = {name: sha(path) for name, path in closure('tokenizer_fpga_memory_subsystem', source).items()}
        assert (len(current_parser), len(current_tokenizer)) == (75, 22)
        assert parser_hashes is None or parser_hashes == current_parser
        assert tokenizer_hashes is None or tokenizer_hashes == current_tokenizer
        parser_hashes, tokenizer_hashes = current_parser, current_tokenizer
        assert accepted == baseline['acceptance'], case
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        executions[case] = dict(snapshot=name, profile=baseline['profile'], acceptance=accepted,
            inputs_sha256=inputs, archive_files_sha256={path.name: sha(path) for path in archive.iterdir() if path.is_file()})
    assert tokenizer_hashes == parent['executed_tokenizer_sha256']
    assert [name for name in parser_hashes if parser_hashes[name] != parent['executed_parser_sha256'][name]] == ['rpc_grpc_http2_return']
    result = dict(phase='actual_freeze_handshake_idle_guard_protocol_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), executions=executions,
        exact_parser_modules=75, exact_tokenizer_modules=22,
        executed_parser_sha256=parser_hashes, executed_tokenizer_sha256=tokenizer_hashes,
        parent_corpus_audit_key=parent['key'], all_selected_acceptance_records_equal_baselines=True,
        full_original_protocol_stimulus_preserved=True, no_internal_idle_feedback=True,
        only_module_idle_output_equation_changed=True, no_state_or_handshake_equations_changed=True,
        scope_comparison_and_immediate_cancellation_unchanged=True,
        generator_replay_verified=True, generation_sha256=sha(generation_path),
        full_native_corpus_on_candidate_verified=False, current_native_implementation_verified=False,
        native_timing_improvement_verified=False, full_system_complete=False,
        artifacts_sha256={source_relative(path, root).as_posix(): sha(path) for path in
                         [Path(__file__), generator, generation_path, *helpers]})
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/freeze-idle-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=True)
    for relative in result['artifacts_sha256']:
        target = evidence / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path(root, relative), target)
    output = root / 'build/validation/freeze-idle-experiment.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(output, evidence / 'verified.json')
    print(json.dumps(dict(phase=result['phase'], key=result['key'], executions=len(executions))))


if __name__ == '__main__':
    main()
