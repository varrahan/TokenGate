"""Snapshot existing regressions with one RTL candidate in an isolated WSL tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from run_wsl_sv_tests import SUITES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--suite', choices=('external_merge', 'tokenizer'), required=True)
    parser.add_argument('--simulator', choices=('iverilog', 'verilator'), default='verilator')
    args = parser.parse_args()
    assert args.name.replace('-', '').replace('_', '').isalnum()
    root = Path.home() / 'development/hardware/parser'
    assert root.is_dir(), 'Run with WSL Python in the approved Linux workspace'
    target = root / 'build' / args.name
    assert args.candidate.name == 'bpe_external_merge_unit.v' and args.candidate.is_file()
    fixture, _, source_names = SUITES[args.suite]
    # Each simulator/suite gets an immutable source/fixture snapshot and logs.
    isolated = target / (args.suite + '-' + args.simulator)
    isolated.mkdir(parents=True, exist_ok=False)
    files = [(root / name, Path(name)) for name in source_names]
    files.append((root / 'scripts/run_wsl_sv_tests.py', Path('scripts/run_wsl_sv_tests.py')))
    files.extend((path, Path('build') / fixture / path.name) for path in (root / 'build' / fixture).iterdir()
                 if path.is_file() and path.suffix in ('.mem', '.txt', '.bin', '.json') and not path.name.endswith('-report.json'))
    manifest = {}
    for source, relative in files:
        if relative.as_posix() == 'rtl/bpe_external_merge_unit.v':
            source = args.candidate
        destination = isolated / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest[relative.as_posix()] = hashlib.sha256(destination.read_bytes()).hexdigest()
    provenance = dict(candidate_path=str(args.candidate), candidate_sha256=hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
                      source_and_fixture_sha256=manifest, primary_rtl_changed=False, suite=args.suite, simulator=args.simulator)
    record = isolated / 'isolated-inputs.json'
    record.write_text(json.dumps(provenance, indent=2) + '\n')
    result = subprocess.run(['python3', str(isolated / 'scripts/run_wsl_sv_tests.py'), args.suite, '--simulator', args.simulator], check=False)
    assert all(hashlib.sha256((isolated / name).read_bytes()).hexdigest() == digest for name, digest in manifest.items())
    if result.returncode:
        raise SystemExit(result.returncode)
    print(f'PASS: isolated {args.suite}/{args.simulator}; primary/live inputs untouched; reports under {isolated}')


if __name__ == '__main__':
    main()
