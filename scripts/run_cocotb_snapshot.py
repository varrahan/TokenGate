"""Run a cocotb suite from an immutable, isolated WSL source/fixture snapshot.

Primary development can continue during the simulation. Reports retain the
executed sources and explicitly list any current-primary differences; a result
for a snapshot is never silently represented as a test of changed primary RTL.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path, source_relative


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=('two_fpga', 'two_fpga_memory', 'two_fpga_framed', 'two_fpga_controlled', 'two_fpga_initialized','two_fpga_journaled','two_fpga_peer','two_fpga_classified','two_fpga_shutdown', 'rpc_grpc', 'rpc_leased','rpc_durable','rpc_keyed'), required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--simulator', choices=('icarus', 'verilator'), default='icarus')
    parser.add_argument('--rtl-override', type=Path,
                        help='Replace one matching RTL basename only in the frozen snapshot')
    parser.add_argument('--test-module',choices=('test_two_fpga_initialized','test_two_fpga_bootstrap','test_raw_journaled_controls','test_raw_peer_controls','test_raw_classified_controls','test_raw_shutdown_controls','test_raw_shutdown_faults'))
    args = parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name)
    primary = Path(__file__).resolve().parents[1]
    wsl = Path.home() / 'development/hardware/parser'
    assert wsl.is_dir() and primary != wsl, 'Run the mounted primary script using the approved WSL Python'
    snapshot = wsl / 'build/cocotb-snapshots' / args.name
    snapshot.mkdir(parents=True, exist_ok=False)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    input_files = []
    for directory in ('rtl', 'sim', 'tools', 'scripts'):
        input_files += [p for p in (source_path(primary, directory)).rglob('*') if p.is_file() and not p.is_symlink()
                        and '__pycache__' not in p.parts and p.suffix in ('.v', '.sv', '.py')]
    fixture_folder='rpc-grpc-fixtures' if args.suite in('rpc_grpc','rpc_leased','rpc_durable','rpc_keyed') else 'bidirectional-fixtures'
    input_files += [p for p in (primary / 'build' / fixture_folder).iterdir()
                    if p.is_file() and p.suffix in ('.mem', '.txt', '.json', '.bin')]
    oracle = source_path(primary, 'build/rpc-grpc-fixtures/frame_cases.json' if args.suite in('rpc_grpc','rpc_leased','rpc_durable','rpc_keyed') else 'build/bidirectional-reference-validation.json')
    input_files.append(oracle)
    if args.suite in('two_fpga_classified','two_fpga_shutdown'):input_files.append(primary/'build/http2-classifier-fixtures/cases.json')
    if args.suite=='two_fpga_shutdown':input_files.append(primary/'build/http2-shutdown-fixtures/cases.json')
    inputs = {}
    for source in dict.fromkeys(input_files):
        relative = source_relative(source, primary)
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        inputs[relative.as_posix()] = sha(destination)
    override = None
    if args.rtl_override:
        candidate = args.rtl_override.resolve()
        assert candidate.is_file() and candidate.suffix == '.v'
        matches = [p for p in input_files if p.is_relative_to(primary / 'rtl') and p.name == candidate.name]
        assert len(matches) == 1, 'Override must replace exactly one existing primary RTL file'
        original = matches[0]; relative = source_relative(original, primary)
        override = dict(path=str(candidate), destination=relative.as_posix(),
                        original_sha256=sha(original), candidate_sha256=sha(candidate))
        shutil.copy2(candidate, snapshot / relative)
        inputs[relative.as_posix()] = sha(snapshot / relative)
    provenance = dict(phase='snapshot_ready', name=args.name, suite=args.suite,
        created_utc=datetime.now(timezone.utc).isoformat(), snapshot_root=str(snapshot),
        primary_source_root=str(primary), source_and_fixture_sha256=inputs,
        snapshot_runner_sha256=sha(Path(__file__)), isolated_rtl_override=override,test_module=args.test_module)
    manifest = snapshot / 'snapshot.json'
    manifest.write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'Snapshot ready: {snapshot}; {len(inputs)} source/reference files', flush=True)
    result = subprocess.run([sys.executable, str(snapshot / 'scripts/run_cocotb.py'), args.suite,
                             '--simulator', args.simulator,*(['--test-module',args.test_module]if args.test_module else[])], check=False)
    report_dir = snapshot / 'build' / ('cocotb-' + args.suite)
    report = json.loads((report_dir / 'report.json').read_text())
    assert all(sha(snapshot / name) == digest for name, digest in inputs.items()), 'Snapshot inputs changed'
    target = primary / 'build/wsl-reports' / ('cocotb_' + args.suite + '_' + args.name)
    target.mkdir(parents=True, exist_ok=False)
    for name in ('build.log', 'simulation.log', 'report.json', 'results.xml', 'acceptance.json', 'progress.json'):
        if (report_dir / name).is_file():
            shutil.copy2(report_dir / name, target / name)
    for name, digest in {**report['source_sha256'], **report['fixture_sha256']}.items():
        assert sha(snapshot / name) == digest
        destination = target / 'execution-sources' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot / name, destination)
    shutil.copy2(snapshot / source_relative(oracle, primary), target / 'native-reference.json')
    support_sources=('scripts/run_cocotb_snapshot.py',) if args.suite in('rpc_grpc','rpc_leased','rpc_durable','rpc_keyed') else ('tools/verify_http2_prefill_references.py','scripts/run_cocotb_snapshot.py')
    for relative in support_sources:
        assert sha(snapshot / relative) == inputs[relative]
        destination = target / 'execution-sources' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snapshot / relative, destination)
    provenance.update(phase='snapshot_run_archived', runner_exit_code=result.returncode,
        execution_phase=report['phase'], execution_report_sha256=sha(target / 'report.json'),
        current_primary_changed_inputs=[name for name, digest in {**report['source_sha256'], **report['fixture_sha256']}.items()
                                        if not (source_path(primary, name)).is_file() or sha(source_path(primary, name)) != digest],
        finished_utc=datetime.now(timezone.utc).isoformat())
    (target / 'snapshot.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'Archived {args.suite}/{args.name}: {report["phase"]}; current-primary differences: '
          f'{len(provenance["current_primary_changed_inputs"])}', flush=True)
    if result.returncode or report['phase'] != 'passed':
        raise SystemExit(result.returncode or 1)


if __name__ == '__main__':
    main()
