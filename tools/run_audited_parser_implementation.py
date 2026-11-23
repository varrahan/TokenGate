"""Implement the exact Parser closure from a completed source-bound audit."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--audit', required=True, choices=('freeze-idle-experiment', 'json-simd-corpus', 'frame-event-buffer-corpus', 'frame-event-buffer-units', 'frame-owned-quiet-formal','payload-event-buffer-units','rpc-completion-flags','rpc-success-predicate','rpc-stream-refusal-v7-directed','rpc-registered-frame-select-v1-directed','receive-payload-settling'))
    args = parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    audit_path = root / 'build/validation' / (args.audit + '.json')
    audit = json.loads(audit_path.read_text())
    if args.audit=='receive-payload-settling':
        from verify_receive_payload_settling import require_settling_audit
        qualified=require_settling_audit(root)
        assert qualified['key']==audit['key']
        assert audit['production_address_width']==23 and audit['production_context_width']==16
        assert audit['capacity_and_stream_format_enabled']
        assert not audit['direct_all_public_output_induction_verified']
        candidate=root/'build/experiments/rpc-receive-payload-pipeline-v1'
        original=candidate/'joint';expected=audit['candidate_parser_sha256'];assert len(expected)==78
    elif args.audit=='rpc-registered-frame-select-v1-directed':
        from verify_registered_frame_select import require_unit_audit
        unit=require_unit_audit(root)
        assert audit['key']=='381fe48f058bf0b1'and audit['four_directed_application_runs_verified']
        assert audit['full_pair_strict_vendor_elaboration_verified']and audit['registered_selection_unit_audit_key']==unit['key']
        gpu=json.loads((root/'build/validation/rpc-registered-select-gpu.json').read_text())
        assert gpu['key']=='c5a8fb353b291447'and len(gpu['executions'])==2
        candidate=root/'build/experiments/rpc-registered-frame-select-v1'
        assert sha(candidate/'generation.json')==audit['generation_sha256']==gpu['generation_sha256']==unit['generation_sha256']
        original=candidate/'joint';expected=audit['executed_parser_sha256'];assert len(expected)==78
    elif args.audit=='rpc-stream-refusal-v7-directed':
        assert audit['key']=='950ce3b65ccb9b0a' and audit['four_directed_application_runs_verified']
        assert audit['full_pair_strict_vendor_elaboration_verified'] and audit['exact_source_edits_and_native_declaration_order_verified']
        faults=json.loads((root/'build/validation/rpc-refusal-ack-faults.json').read_text())
        formal=json.loads((root/'build/validation/rpc-refusal-default-open-equivalence.json').read_text())
        assert faults['key']=='12513e8bd9c65f5d'and faults['actual_memory_response_positions']==46
        assert formal['key']=='462e4c8b3b38971b'and formal['default_open_conditional_equivalence_verified']
        candidate=root/'build/experiments/rpc-stream-refusal-v7'
        assert sha(candidate/'generation.json')==audit['generation_sha256']==faults['generation_sha256']==formal['candidate_generation_sha256']
        original=candidate/'joint';expected=audit['executed_parser_sha256'];assert len(expected)==78
    elif args.audit == 'rpc-success-predicate':
        assert audit['key']=='a4f36fdbbab5143f' and audit['source_edit_replay_verified'] and audit['exact_parser_modules']==77
        assert audit['full_production_response_subtree_induction_verified'] and audit['actual_initial_reset_base_verified']
        assert audit['predicate_equivalence_verified'] and audit['original_output_ports_compared']==72 and audit['proven_equivalence_cells']==4295
        original=root/'build/experiments/rpc-success-predicate-v2'
        expected=audit['executed_parser_sha256']
    elif args.audit == 'rpc-completion-flags':
        assert audit['source_edit_replay_verified'] and audit['exact_parser_modules']==77
        assert audit['full_production_response_subtree_induction_verified'] and audit['actual_initial_reset_base_verified']
        assert audit['original_output_ports_compared']==72 and audit['proven_equivalence_cells']==4292
        original=root/'build/experiments/rpc-completion-flags'
        expected=audit['executed_parser_sha256']
    elif args.audit == 'payload-event-buffer-units':
        assert audit['source_edit_replay_verified'] and audit['exact_parser_modules']==77
        assert audit['unbounded_fifo_induction_verified'] and audit['semantic_packets']==2208
        assert audit['injected_connection_memory_faults']==30 and audit['completion_fence_cycles']>0
        original=root/'build/experiments/payload-event-buffer'
        expected=audit['executed_parser_sha256']
    elif args.audit == 'frame-owned-quiet-formal':
        assert audit['conservative_idle_induction_verified'] and audit['exact_parser_modules']==76
        assert audit['complete_production_owner_subtree'] and audit['all_existing_state_and_handshake_equations_preserved']
        original=root/'build/experiments/frame-owned-quiet'
        expected=audit['executed_parser_sha256']
    elif args.audit == 'frame-event-buffer-units':
        assert audit['source_edit_replay_verified'] and audit['exact_parser_modules']==76
        assert audit['fragments']==459 and audit['exact_events']==120829 and audit['completion_fence_cycles']>0
        original=root/'build/experiments/frame-event-buffer'
        expected=audit['candidate_parser_sha256']
    elif args.audit == 'freeze-idle-experiment':
        assert audit['full_original_protocol_stimulus_preserved'] and len(audit['executions']) == 7
        snapshot = audit['executions']['native']['snapshot']
        assert audit['exact_parser_modules'] == 75
    else:
        assert audit['full_native_corpus_verified'] and audit['exact_parser_modules'] == 76
        snapshot = audit['snapshot']
    if args.audit not in ('frame-event-buffer-units','frame-owned-quiet-formal','payload-event-buffer-units','rpc-completion-flags','rpc-success-predicate','rpc-stream-refusal-v7-directed','rpc-registered-frame-select-v1-directed','receive-payload-settling'):
        original = root / 'build/wsl-reports' / ('raw_envelope_' + snapshot) / 'execution-sources'
        expected = audit['executed_parser_sha256']
    top = 'http2_enveloped_parser_application'
    assert {name: sha(path) for name, path in closure(top, original).items()} == expected
    free = shutil.disk_usage(root).free
    assert free >= 10 * 1024**3, 'Need at least 10 GiB free for a full Parser implementation'
    part = 'xcau15p-ffvb676-2-e'
    inputs = root / 'build/validation' / (args.name + '-inputs')
    launch_path = root / 'build/validation' / (args.name + '-launch.json')
    assert not launch_path.exists() and not (root / 'build/implementation' / part / args.name).exists()
    inputs.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for module, digest in expected.items():
        source = original / 'rtl' / (module + '.v')
        assert sha(source) == digest and (source_path(root, Path('rtl') / (source.name))).is_file()
        destination = inputs / 'rtl' / source.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(source, destination)
        hashes['rtl/' + source.name] = digest
    for name in ('scripts/implement_registered_subsystem.tcl', 'scripts/run_registered_subsystem_implementation.ps1',
                 'tools/generate_parser_timing_harness.py', 'tools/capture_source_provenance.py', 'constraints/parser.xdc', 'tools/rtl_paths.py', 'scripts/rtl_sources.tcl'):
        target = inputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path(root, name), target)
        hashes[name] = sha(target)
    shutil.copy2(audit_path, inputs / 'source-functional-audit.json')
    shutil.copy2(Path(__file__), inputs / Path(__file__).name)
    harness = root / 'build' / (args.name + '-timing-harness.v')
    subprocess.run([sys.executable, str(inputs / 'tools/generate_parser_timing_harness.py'), '--source',
        str(inputs / 'rtl' / (top + '.v')), '--top', top, '--harness-top', top + '_timing_harness',
        '--output', str(harness)], check=True, capture_output=True)
    command = ['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat', '-mode', 'batch', '-notrace', '-source',
        str(root / 'scripts/implement_registered_subsystem.tcl'), '-log', str(root / 'build' / (args.name + '-implementation.log')),
        '-journal', str(root / 'build' / (args.name + '-implementation.jou')), '-tclargs', top, args.name,
        'implementation', 'Default', part, str(inputs / 'rtl'), '1']
    record = dict(phase='running', started_utc=datetime.now(timezone.utc).isoformat(), run=args.name, top=top, part=part,
        functional_source_audit_name=args.audit, functional_source_audit_key=audit['key'],
        functional_source_audit_sha256=sha(audit_path), exact_parser_modules=len(expected),
        inputs_sha256=hashes, harness_sha256=sha(harness), driver_sha256=sha(Path(__file__)), command=command,
        max_threads=1, free_bytes_before=free, minimum_free_bytes=10 * 1024**3, clock_period_ns=4.0,
        full_protocol_validation_pending=args.audit in ('frame-event-buffer-units','frame-owned-quiet-formal','payload-event-buffer-units','rpc-completion-flags','rpc-success-predicate','rpc-stream-refusal-v7-directed','rpc-registered-frame-select-v1-directed','receive-payload-settling'),
        package_timing_verified=False, primary_rtl_modified=False, full_system_complete=False)
    def save():
        launch_path.write_text(json.dumps(record, indent=2) + '\n')
    save()
    try:
        with (root / 'build' / (args.name + '-stdout.log')).open('w') as stream:
            process = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
            record['launcher_pid'] = process.pid
            save()
            code = process.wait()
        record['exit_code'] = code
        assert code == 0, ('Vivado failed', code)
        text = (root / 'build' / (args.name + '-stdout.log')).read_text(errors='replace')
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=' + top in text and 'ERROR:' not in text
        assert all(sha(inputs / name) == digest for name, digest in hashes.items())
        record['phase'] = 'native_process_completed'
    except BaseException as error:
        record.update(phase='stopped_with_error', error=str(error))
        raise
    finally:
        record.update(finished_utc=datetime.now(timezone.utc).isoformat(), free_bytes_after=shutil.disk_usage(root).free)
        save()
    print(json.dumps({name: record[name] for name in ('phase', 'run', 'exit_code', 'functional_source_audit_key')}))


if __name__ == '__main__':
    main()
