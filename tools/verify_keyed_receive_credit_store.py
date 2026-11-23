"""Audit actual directory reads, delegated binding checks and RX-credit faults."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--snapshot', default='keyed_receive_verilog_regression'); args = parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.snapshot)
    root = Path(__file__).resolve().parents[1]; sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    archive = root / 'build/wsl-reports' / ('http2_keyed_receive_credits_' + args.snapshot); source = archive / 'execution-sources'
    inputs = json.loads((archive / 'inputs.json').read_text()); report = json.loads((archive / 'report.json').read_text())
    snapshot = json.loads((archive / 'snapshot.json').read_text()); accepted = json.loads((archive / 'acceptance.json').read_text())
    assert report['phase'] == accepted['phase'] == 'passed' and snapshot['exit_code'] == 0
    assert report['tests'] == 1 and report['failures'] == 0 and report['input_sha256'] == inputs
    assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    for n, h in inputs.items(): assert sha(source / n) == h, n
    dag = closure('http2_keyed_receive_credit_store', source)
    assert set(dag) == {'http2_keyed_receive_credit_store', 'http2_receive_credit_store', 'memory_command_slot'}
    for p in dag.values():
        n = p.relative_to(source).as_posix(); assert inputs[n] == sha(source_path(root, n)), n
    for n in ('sim/cocotb/test_keyed_receive_credits.py', 'sim/cocotb/test_receive_credit_store.py', 'tools/generate_keyed_receive_credit_store.py', 'tools/rtl_paths.py'):
        assert inputs[n] == sha(source_path(root, n)), n
    assert inputs['build/http2-send-window-fixtures/model.bin'] == 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    xml = ET.parse(archive / 'results.xml'); cases = xml.findall('.//testcase')
    assert len(cases) == 1 and cases[0].attrib['name'] == 'actual_key_lookup_preserves_receive_credit_ownership'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    for n in ('actual_key_lookup_reads_verified', 'nontrivial_runtime_slot_and_generation_verified',
              'held_actual_binding_matches_verified_generation', 'foreign_connection_key_skipped',
              'missing_key_does_not_authorize_or_quarantine', 'backend_revalidates_scanned_generation',
              'actual_native_window_update_packets_verified', 'accepted_input_poisoning_verified',
              'complete_model_prefix_immutable', 'directory_pool_authority_supplied_by_fixture', 'consumed_bytes_supplied_by_fixture'):
        assert accepted[n], n
    for n in ('actual_raw_parser_integrated', 'actual_descriptor_consumption_integrated', 'full_system_complete'): assert accepted[n] is False
    assert accepted['operation_memory_phase_counts'] == {'2': 37, '3': 37, '4': 38, '5': 38}
    groups = defaultdict(list)
    for case in accepted['all_memory_ack_faults']: groups[case['op']].append(case)
    assert set(groups) == {2, 3, 4, 5} and sum(len(v) for v in groups.values()) == 150
    for op, cases in groups.items():
        count = accepted['operation_memory_phase_counts'][str(op)]
        assert [c['phase'] for c in cases] == list(range(count))
        for case in cases:
            assert case['memory_commands'] == case['phase'] + 1
            assert case['wire_retired'] is (op == 4 and case['phase'] >= count - 2)
    replay = root / 'build/validation/keyed-receive-generation-replay'
    for n in ('rtl/http2_receive_credit_store.v', 'tools/generate_keyed_receive_credit_store.py', 'tools/generate_bidirectional_application.py', 'tools/rtl_paths.py'):
        p = replay / n; p.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source / n, p)
    subprocess.run([sys.executable, str(replay / 'tools/generate_keyed_receive_credit_store.py')], check=True, capture_output=True, text=True)
    assert sha(replay / 'rtl/http2_keyed_receive_credit_store.v') == inputs['rtl/http2_keyed_receive_credit_store.v']
    result = dict(phase='keyed_receive_credit_component_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        archive=str(archive), input_sha256=inputs, report_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()},
        acceptance=accepted, exact_rtl_modules_verified=list(dag), exact_generator_replayed=True,
        all_150_memory_ack_faults_verified=True, actual_directory_scan_and_backend_revalidation_verified=True,
        actual_raw_parser_integrated=False, actual_descriptor_consumption_integrated=False,
        retained_memory_warm_reset_verified=False, native_routed_timing_verified=False,
        full_system_complete=False, verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    folder = root / 'build/validation/keyed-receive-credit-evidence' / key; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'verified.json').write_text(json.dumps(result, indent=2) + '\n'); shutil.copy2(Path(__file__), folder / Path(__file__).name)
    result['evidence_folder'] = str(folder)
    (root / 'build/validation/keyed-receive-credit-store.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, ack_faults=150, full_system_complete=False)))


if __name__ == '__main__': main()
