"""Bind the isolated bounds change, component tests, formal proof and route."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_two_fpga_application import closure, resources, timing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-run', default='tokenizer_fpga_scu35_store_bounds_refined')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    candidate_folder = root / 'build/merge-store-bounds-candidate'
    candidate = candidate_folder / 'bpe_external_merge_unit.v'
    baseline = candidate_folder / 'baseline-bpe_external_merge_unit.v'
    metadata = json.loads((candidate_folder / 'candidate.json').read_text())
    assert metadata['baseline_sha256'] == sha(baseline)
    assert metadata['candidate_sha256'] == sha(candidate)
    assert metadata['generator_sha256'] == sha(root / 'tools/prepare_merge_store_bounds_candidate.py')
    current = sha(root / 'rtl/bpe_external_merge_unit.v')
    assert current in (sha(baseline), sha(candidate)), 'Primary RTL has an unrelated change'
    archive = root / 'build/validation/merge-store-bounds-candidate-inputs'
    archive_record = json.loads((archive / 'archive.json').read_text())
    for name, digest in archive_record['files_sha256'].items():
        assert sha(archive / name) == digest, ('Archived candidate evidence changed', name)
    for suite in ('external_merge', 'tokenizer'):
        folder = archive / (suite + '-verilator')
        report = json.loads((folder / 'reports/verilator-report.json').read_text())
        assert report['suite'] == suite and report['phase'] == 'passed'
        assert report['source_sha256']['rtl/bpe_external_merge_unit.v'] == sha(candidate)
        for name, digest in report['source_sha256'].items():
            assert sha(folder / name) == digest
        inputs = json.loads((folder / 'isolated-inputs.json').read_text())
        assert inputs['candidate_sha256'] == sha(candidate)
        for name, digest in inputs['source_and_fixture_sha256'].items():
            assert sha(folder / name) == digest
    merge_log = (archive / 'external_merge-verilator/reports/verilator-simulation.log').read_text()
    tokenizer_log = (archive / 'tokenizer-verilator/reports/verilator-simulation.log').read_text()
    assert '1701 native-reference pieces/6623 exact IDs' in merge_log and '7 errors, 6 cancellation phases' in merge_log
    assert '291 sequences/24833 reference IDs' in tokenizer_log and '16 errors' in tokenizer_log
    proof = json.loads((archive / 'formal/proof.json').read_text())
    assert proof['phase'] == 'component_equivalence_proven_for_synced_reset_state'
    assert proof['baseline_sha256'] == sha(baseline) and proof['candidate_sha256'] == sha(candidate)
    assert proof['formal_compare_cells'] == 1060 and proof['all_output_ports_checked']
    assert proof['unmatched_internal_cones'] == ['store_good'] and not proof['unmatched_internal_cones_assumed_equal']
    assert (proof['memory_addr_width'], proof['user_width'], proof['id_width'], proof['rank_width']) == (23, 16, 17, 17)
    assert proof['proof_log_sha256'] == sha(archive / 'formal/proof.log')
    assert proof['proven_netlist_sha256'] == sha(archive / 'formal/proven.json')
    assert '1060 are proven and 0 are unproven' in (archive / 'formal/proof.log').read_text()
    netlist = json.loads((archive / 'formal/proven.json').read_text())['modules']['equiv']
    comparisons = [cell for cell in netlist['cells'].values() if cell['type'] == '$equiv']
    assert len(comparisons) == 1060 and all(c['connections']['A'] == c['connections']['B'] for c in comparisons)
    reset = json.loads((archive / 'formal-reset/proof.json').read_text())
    assert reset['phase'] == 'reset_base_case_proven'
    assert reset['baseline_sha256'] == sha(baseline) and reset['candidate_sha256'] == sha(candidate)
    assert reset['checked_cycles_after_reset'] == [2, 3, 4] and not reset['output_cones_excluded']
    assert reset['proof_log_sha256'] == sha(archive / 'formal-reset/proof.log')
    assert 'SAT proof finished - no model found: SUCCESS!' in (archive / 'formal-reset/proof.log').read_text()
    native = root / 'build/implementation/xcsu35p-sbvb625-2-e' / args.native_run
    provenance = json.loads((native / 'source-provenance.json').read_text())
    dependencies = closure('tokenizer_fpga_application')
    assert len(dependencies) == 18
    for source in set(dependencies.values()):
        relative = source.relative_to(root)
        expected = candidate if relative.as_posix() == 'rtl/bpe_external_merge_unit.v' else source
        assert sha(expected) == sha(native / 'sources' / relative) == provenance['files'][relative.as_posix()]['sha256']
    log_file = root / f'build/{args.native_run}-implementation.log'
    log = log_file.read_text()
    assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=tokenizer_fpga_application PART=xcsu35p-sbvb625-2-e' in log
    assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (native / 'route_status.rpt').read_text())
    clocks = timing(native / 'routed_timing.rpt')
    measured = resources(native / 'routed_utilization.rpt')
    passed = clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0
    files = {Path('checks') / name: archive / name for name in archive_record['files_sha256']}
    for name in ('source-provenance.json', 'routed_timing.rpt', 'routed_utilization.rpt', 'route_status.rpt', 'routed_drc.rpt'):
        files[Path('native') / name] = native / name
    files[Path('native/implementation.log')] = log_file
    for path in set(dependencies.values()):
        files[Path('native/sources') / path.relative_to(root)] = native / 'sources' / path.relative_to(root)
    for name in ('candidate.json', 'bpe_external_merge_unit.v', 'baseline-bpe_external_merge_unit.v'):
        files[Path('candidate') / name] = candidate_folder / name
    for name in ('tools/verify_merge_store_bounds_candidate.py', 'tools/prepare_merge_store_bounds_candidate.py',
                 'scripts/prove_merge_store_bounds.py', 'scripts/prove_merge_reset_base.py', 'scripts/run_isolated_merge_candidate.py',
                 'scripts/collect_merge_store_bounds_candidate.py'):
        files[Path('verification') / name] = root / name
    key = hashlib.sha256((sha(archive / 'archive.json') + sha(native / 'source-provenance.json') + sha(Path(__file__))).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/merge-store-bounds-candidate-evidence' / key
    for name, source in files.items():
        target = evidence / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert sha(target) == sha(source), ('Immutable candidate evidence differs', name)
        else:
            shutil.copy2(source, target)
    result = dict(phase='component_equivalent_native_timing_met' if passed else 'component_equivalent_native_timing_pending',
        verified_utc=datetime.now(timezone.utc).isoformat(), component_regressions_passed=True,
        bpe_reference_pieces=1701, bpe_reference_ids=6623, raw_text_sequences=291, raw_text_reference_ids=24833,
        formal_equivalence=proof, formal_reset_base_case=reset, native_run=args.native_run, native_exact_rtl_files=18,
        candidate_sha256=sha(candidate), baseline_sha256=sha(baseline), primary_candidate_promoted=current == sha(candidate),
        resources=measured, timing=clocks, routed_timing_met=passed, native_memory_fabric_included=False,
        physical_adapters_verified=False, full_split_regression_on_candidate_verified=False,
        full_system_complete=False, evidence_folder=str(evidence), verifier_sha256=sha(Path(__file__)))
    (root / 'build/validation/merge-store-bounds-candidate.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: value for name, value in result.items() if name not in ('formal_equivalence','formal_reset_base_case')}, indent=2))


if __name__ == '__main__':
    main()
