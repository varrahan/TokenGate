"""Audit the durable RX-credit component without claiming raw integration."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from verify_two_fpga_application import closure, resources, timing


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--snapshot', default='receive_credit_actual_retired_binding')
    parser.add_argument('--native-run')
    args = parser.parse_args(); assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', n) for n in vars(args).values() if n)
    root = Path(__file__).resolve().parents[1]
    archive = root / 'build/wsl-reports' / ('http2_receive_credits_' + args.snapshot)
    source = archive / 'execution-sources'; sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = json.loads((archive / 'inputs.json').read_text())
    report = json.loads((archive / 'report.json').read_text()); snapshot = json.loads((archive / 'snapshot.json').read_text())
    accepted = json.loads((archive / 'acceptance.json').read_text())
    assert report['phase'] == accepted['phase'] == 'passed' and snapshot['exit_code'] == 0
    assert report['tests'] == 1 and report['failures'] == 0 and report['input_sha256'] == inputs
    assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    for name, digest in inputs.items(): assert sha(source / name) == digest, name
    dag = closure('http2_receive_credit_store', source)
    assert set(dag) == {'http2_receive_credit_store', 'memory_command_slot'}
    for p in dag.values():
        name = p.relative_to(source).as_posix(); assert sha(p) == inputs[name] == sha(root / name)
    for name in ('sim/cocotb/test_receive_credit_store.py',):
        assert inputs[name] == sha(root / name), name
    xml = ET.parse(archive / 'results.xml'); cases = xml.findall('.//testcase')
    assert len(cases) == 1 and cases[0].attrib['name'] == 'native_receive_credit_memory_and_wire_retirement'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    assert inputs['build/http2-send-window-fixtures/model.bin'] == 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    assert (source / 'build/http2-send-window-fixtures/model.bin').stat().st_size == 8 * 1024 * 1024
    for name in ('native_window_update_packets_verified', 'actual_intent_ack_before_wire_verified',
                 'actual_wire_before_available_commit_verified', 'matching_context_writer_wait_and_fresh_read_verified',
                 'foreign_writer_scope_does_not_stall', 'foreign_format_cannot_clear_quarantine',
                 'closed_stream_credit_return_is_idempotent', 'retired_rpc_requires_inactive_matching_binding',
                 'retired_rpc_credit_return_is_idempotent', 'complete_model_prefix_immutable',
                 'typed_directory_authority_supplied_by_fixture', 'typed_consumption_supplied_by_fixture'):
        assert accepted[name], name
    for name in ('actual_raw_parser_integrated', 'actual_descriptor_consumption_integrated',
                 'receive_flow_control_end_to_end_verified', 'full_system_complete'): assert accepted[name] is False, name
    assert accepted['held_wire_cycles'] >= 17
    grouped = defaultdict(list)
    for case in accepted['every_memory_ack_fault']:
        grouped[case['op'], case['stream']].append(case)
    expected = {(0, 0): 10, (1, 1): 22, (2, 1): 19, (3, 1): 19, (4, 0): 12, (4, 1): 20, (5, 1): 20, (9, 1): 20}
    assert set(grouped) == set(expected)
    for key, count in expected.items():
        cases = grouped[key]; assert [c['phase'] for c in cases] == list(range(count))
        for case in cases:
            assert case['memory_commands'] == case['phase'] + 1
            assert case['wire_retired'] is (key[0] == 4 and case['phase'] >= count - 2)
    assert len(accepted['every_memory_ack_fault']) == 142
    native = None
    if args.native_run:
        top = 'http2_receive_credit_store'; part = 'xcau15p-ffvb676-2-e'
        folder = root / 'build/implementation' / part / args.native_run; frozen = folder / 'sources'
        provenance = json.loads((folder / 'source-provenance.json').read_text())
        for n, data in provenance['files'].items(): assert sha(frozen / n) == data['sha256'], n
        assert set(closure(top, frozen)) == set(dag)
        for p in closure(top, frozen).values():
            n = p.relative_to(frozen).as_posix(); assert sha(p) == inputs[n], n
        log = root / ('build/' + args.native_run + '-implementation.log'); log_bytes = log.read_bytes(); text = log_bytes.decode()
        assert f'REGISTERED_SUBSYSTEM_SYNTHESIS_COMPLETE TOP={top} PART={part}' in text
        assert '0 Critical Warnings and 0 Errors encountered.' in text and 'synth_design completed successfully' in text
        exceptions = [line.strip() for line in (frozen / 'scripts/implement_registered_subsystem.tcl').read_text().splitlines() if line.strip().startswith('set_false_path')]
        assert exceptions == ['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]', 'set_false_path -to [all_outputs]']
        with ZipFile(folder / 'synthesized.dcp') as package: metadata_xml = package.read('dcp.xml')
        metadata = {n.tag: n.attrib.get('Name') for n in ET.fromstring(metadata_xml)}
        assert metadata['Part'] == part and metadata['Top'] == top + '_timing_harness' and metadata['OutOfContext'] == '1'
        native = dict(phase='native_synthesis_verified', run=args.native_run, resources=resources(folder / 'synthesis_utilization.rpt'),
            synthesis_timing_estimate=timing(folder / 'synthesis_timing.rpt'), checkpoint_metadata=metadata,
            checkpoint_sha256=sha(folder / 'synthesized.dcp'), source_provenance_sha256=sha(folder / 'source-provenance.json'),
            report_sha256={n: sha(folder / n) for n in ('synthesis_utilization.rpt', 'synthesis_timing.rpt')},
            synthesis_log_sha256=hashlib.sha256(log_bytes).hexdigest(), exact_executed_rtl_modules_verified=2,
            package_paths_excluded=True, routed=False, routed_timing_verified=False)
    result = dict(phase='receive_credit_component_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        snapshot=args.snapshot, archive=str(archive), input_sha256=inputs,
        report_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()}, acceptance=accepted,
        exact_rtl_modules_verified=list(dag), all_142_ack_faults_verified=True,
        post_wire_commit_faults_verified=4, original_complete_model_image_verified=True,
        actual_raw_parser_integrated=False, actual_descriptor_consumption_integrated=False,
        retained_memory_warm_reset_verified=False, native=native,
        full_system_complete=False, verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    folder = root / 'build/validation/receive-credit-store-evidence' / key; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'verified.json').write_text(json.dumps(result, indent=2) + '\n'); shutil.copy2(Path(__file__), folder / Path(__file__).name)
    result['evidence_folder'] = str(folder)
    (root / 'build/validation/receive-credit-store.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, ack_faults=142, post_wire_faults=4, full_system_complete=False)))


if __name__ == '__main__': main()
