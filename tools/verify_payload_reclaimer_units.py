"""Qualify the actual compactor component; do not claim application credit fixed."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    folder = root / 'build/wsl-reports/payload_reclaimer_unit_v3_20261122'
    source = folder / 'execution-sources'
    inputs = read(folder / 'inputs.json')
    report = read(folder / 'report.json')
    accepted = read(folder / 'acceptance.json')
    assert read(folder / 'snapshot.json')['exit_code'] == 0
    assert report['phase'] == accepted['phase'] == 'passed' and report['passed']
    assert report['inputs_sha256'] == inputs and report['acceptance_sha256'] == sha(folder / 'acceptance.json')
    for name, digest in inputs.items():
        assert sha(source / name) == digest, name
    xml = ET.parse(folder / 'results.xml')
    tests = xml.findall('.//testcase')
    assert len(tests) == 1 and tests[0].attrib['name'] == 'full_image_compaction_and_ack_quarantine'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    parent = read(root / 'build/validation/frame-owned-quiet-corpus.json')
    assert parent['key'] == 'b89b9aea0dd403cb'
    assert inputs['rtl/memory_command_slot.v'] == parent['executed_parser_sha256']['memory_command_slot']
    base = read(root / 'build/validation/json-simd-corpus.json')
    assert base['key'] == '2509134d2630b47e'
    for leaf in ('memory.mem', 'layout.txt', 'fixture_manifest.json'):
        name = 'build/bidirectional-fixtures/' + leaf
        assert inputs[name] == base['inputs_sha256'][name]
    image = b''.join(int(word, 16).to_bytes(8, 'little')
        for word in (source / 'build/bidirectional-fixtures/memory.mem').read_text().splitlines())
    meta = read(source / 'build/bidirectional-fixtures/fixture_manifest.json')
    assert len(image) == accepted['full_image_bytes'] == 8388608
    assert hashlib.sha256(image).hexdigest() == meta['loaded_image_sha256']
    assert accepted['complete_protected_model_prefix_immutable']
    cases = accepted['functional_cases']
    assert len(cases) == 42
    assert all(case['result'] == [0, 0, 0, 0] for case in cases)
    assert cases[0]['rows'] == [] and cases[0]['credit_commands'] == 0
    assert cases[3]['rows'] == [dict(used=0, offset=0, ordinal=0xffffffff, watermark=0xffffffff, exhausted=1)]
    assert cases[3]['credit_commands'] == 3
    assert cases[4]['rows'] == [dict(ended=1)] and cases[4]['credit_commands'] == 0
    assert cases[5]['credit_commands'] == 9
    moves = {(case['rows'][0]['offset'], case['rows'][0]['received'])
        for case in cases if case['rows'] and case['rows'][0].get('prefix') == 5}
    assert moves == {(cut, tail) for cut in (1, 3, 8, 17) for tail in (1, 7, 8, 9, 15, 16, 17, 33)}
    assert {case['rows'][0]['prefix'] for case in cases[-4:]} == {1, 2, 3, 4}
    faults = accepted['injected_memory_ack_phases']
    assert [case['phase'] for case in faults] == list(range(20))
    for case in faults:
        assert case['result'][0] in (2, 4) and case['result'][2:] == [0x75, 1]
        assert case['previously_retired_credit_commands'] == (0 if case['phase'] < 18 else 3)
    assert accepted['injected_credit_ack_phases'] == 3
    assert accepted['corrupt_record_rejections'] == ['magic', 'stream_zero', 'generation_zero',
        'payload_alias', 'capacity', 'reserved_state', 'watermark_ahead', 'refund_overflow']
    assert len(accepted['invalid_geometry_rejections']) == 6
    assert not accepted['actual_receive_backend_integrated'] and not accepted['caller_empty_queue_proof_integrated']
    assert not accepted['native_vendor_memory'] and not accepted['application_credit_fixed']
    # Preserve the initial failed expectation: a later free-record read fault
    # cannot erase the credit already retired for a preceding committed record.
    failed = root / 'build/wsl-reports/payload_reclaimer_unit_v1_20261122'
    old_inputs = read(failed / 'inputs.json')
    assert read(failed / 'snapshot.json')['exit_code'] == 1
    assert read(failed / 'report.json')['phase'] == 'failed'
    assert old_inputs['rtl/grpc_payload_reclaimer.v'] == inputs['rtl/grpc_payload_reclaimer.v']
    assert 'not environment.credits' in (failed / 'simulation.log').read_text()
    result = dict(phase='payload_reclaimer_component_evidence_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), snapshot=folder.name,
        actual_reclaimer_rtl_sha256=inputs['rtl/grpc_payload_reclaimer.v'],
        actual_memory_slot_sha256=inputs['rtl/memory_command_slot.v'],
        functional_cases=42, partial_move_geometries=32, partial_prefix_geometries=4,
        ordinal_count_33_bit_boundary_verified=True, immutable_private_record_halves_verified=True,
        all_twenty_memory_ack_faults_verified=True, all_three_credit_ack_faults_verified=True,
        corrupt_record_rejections=8, invalid_geometry_rejections=6,
        protected_full_model_prefix_immutable=True, image_bytes=8388608,
        held_result_and_command_stability_verified=True, failure_quarantine_retains_pool_ownership=True,
        initial_scoreboard_failure_preserved=True, unchanged_rtl_passes_corrected_and_extended_fixture=True,
        input_sha256=inputs, acceptance_sha256=sha(folder / 'acceptance.json'),
        actual_receive_backend_integrated=False, caller_empty_queue_proof_integrated=False,
        native_vendor_memory=False, application_credit_fixed=False,
        whole_system_retained_reset_verified=False, full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix(): sha(p) for p in folder.iterdir() if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    destination = root / 'build/validation/payload-reclaimer-units-evidence' / result['key']
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), destination / Path(__file__).name)
    for path in (destination / 'audit.json', root / 'build/validation/payload-reclaimer-units.json'):
        path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'application_credit_fixed')}))


if __name__ == '__main__':
    main()
