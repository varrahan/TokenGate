"""Recheck the actual owner induction after introducing persistent watermarks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_frame_owned_quiet_progress import witness
from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/wsl-reports/open_rpc_reclaim_owner_progress_formal_20261122'
    old = root / 'build/wsl-reports/frame_owned_quiet_progress_formal_20261122'
    parent = read(root / 'build/validation/frame-owned-quiet-progress.json')
    assembly = read(root / 'build/validation/open-rpc-reclaim-assembly.json')
    assert parent['key'] == '7baa05fb722430a4' and assembly['key'] == 'ad1b6bc9beebcaf5'
    assert sha(old / 'report.json') == parent['executions']['implementation_candidate']['report_sha256']
    report = read(folder / 'report.json')
    assert report['passed'] and report['phase'] == 'frame_owned_quiet_safety_and_bounded_progress_induction_verified'
    assert report['candidate_variant'] == 'open-rpc-reclaim'
    assert report['generation_sha256'] == assembly['generation_sha256']
    assert report['driver_sha256'] == sha(folder / 'run_frame_owned_quiet_formal_wsl.py')
    for name, digest in report['inputs_sha256'].items():
        assert sha(folder / name) == digest, name
    candidate = root / 'build/experiments/open-rpc-reclaim'
    dependencies = closure('http2_enveloped_frame_grants', candidate)
    assert len(dependencies) == 7
    for name, source in dependencies.items():
        assert sha(source) == assembly['executed_parser_sha256'][name]
        if name == 'http2_enveloped_frame_grants':
            assert (folder / 'rtl' / source.name).read_bytes() == (old / 'rtl' / source.name).read_bytes()
            assert report['original_top_sha256'] == read(old / 'report.json')['original_top_sha256']
        else:
            assert sha(folder / 'rtl' / source.name) == sha(source)
    changed = {p.name for p in (folder / 'rtl').glob('*.v') if p.read_bytes() != (old / 'rtl' / p.name).read_bytes()}
    assert changed == {'grpc_stream_store.v'}
    assert (folder / 'miter.sv').read_bytes() == (old / 'miter.sv').read_bytes()
    assert (folder / 'proof.ys').read_bytes() == (old / 'proof.ys').read_bytes()
    miter = (folder / 'miter.sv').read_text()
    assert miter.count('assume(') == 1 and miter.count('assert(') == 3
    log = (folder / 'proof.log').read_text()
    assert 'Induction step proven: SUCCESS!' in log and 'SAT solving finished - model found:' in log
    assert not re.search(r'^ERROR:', log, re.M)
    assert sha(folder / 'proof.log') == report['proof_log_sha256']
    assert sha(folder / 'netlist.json') == report['netlist_sha256']
    assert sha(folder / 'quiet_cover.vcd') == report['quiet_cover_sha256']
    reached = witness(folder / 'quiet_cover.vcd')
    result = dict(phase='open_rpc_reclaim_owner_safety_progress_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), assembly_audit_key=assembly['key'],
        parent_progress_audit_key=parent['key'], generation_sha256=assembly['generation_sha256'],
        exact_owner_modules=7, only_changed_owner_module='grpc_stream_store',
        original_assertions_and_induction_script_unchanged=True,
        no_early_idle_verified=True, maximum_extra_idle_cycles_after_stable_quiet=1,
        quiet_progress_requires_previous_and_current_reference_idle_and_no_offers=True,
        initial_reset_required=True, arbitrary_later_resets_in_induction=True,
        input_stability_assumptions=False, two_state_formal=True,
        reachable_quiet_witness=reached, complete_production_owner_subtree=True,
        memory_model_substitution=False, compactor_memory_safety_formally_verified=False,
        whole_application_liveness_verified=False, application_credit_fixed=False, full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/open-rpc-reclaim-owner-progress-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    shutil.copy2(root / 'tools/verify_frame_owned_quiet_progress.py', evidence / 'verify_frame_owned_quiet_progress.py')
    for destination in (evidence / 'audit.json', root / 'build/validation/open-rpc-reclaim-owner-progress.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'application_credit_fixed')}))


if __name__ == '__main__':
    main()
