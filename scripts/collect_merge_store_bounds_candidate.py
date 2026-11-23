"""Archive immutable inputs/reports from the isolated WSL candidate checks."""
import hashlib
import json
from pathlib import Path
import shutil


def main():
    primary = Path(__file__).resolve().parents[1]
    source = Path.home() / 'development/hardware/parser/build/isolated-store-bounds'
    target = primary / 'build/validation/merge-store-bounds-candidate-inputs'
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    files = {}
    for suite in ('external_merge', 'tokenizer'):
        name = suite + '-verilator'
        folder = source / name
        record = json.loads((folder / 'isolated-inputs.json').read_text())
        assert record['suite'] == suite and record['simulator'] == 'verilator'
        for path, digest in record['source_and_fixture_sha256'].items():
            assert sha(folder / path) == digest, (name, path)
            files[Path(name) / path] = folder / path
        fixture = 'external-merge' if suite == 'external_merge' else 'tokenizer-engine'
        report_file = folder / 'build' / fixture / 'verilator-report.json'
        report = json.loads(report_file.read_text())
        assert report['phase'] == 'passed' and report['suite'] == suite
        files[Path(name) / 'isolated-inputs.json'] = folder / 'isolated-inputs.json'
        for suffix in ('build.log', 'simulation.log', 'report.json'):
            path = folder / 'build' / fixture / ('verilator-' + suffix)
            files[Path(name) / 'reports' / path.name] = path
    proof = json.loads((source / 'formal/proof.json').read_text())
    for path, digest in proof['input_sha256'].items():
        assert sha(source / 'formal' / path) == digest
    assert proof['proof_log_sha256'] == sha(source / 'formal/proof.log')
    assert proof['proven_netlist_sha256'] == sha(source / 'formal/proven.json')
    for path in (source / 'formal').iterdir():
        if path.is_file():
            files[Path('formal') / path.name] = path
    reset = json.loads((source / 'formal-reset/proof.json').read_text())
    assert reset['phase'] == 'reset_base_case_proven'
    assert reset['baseline_sha256'] == proof['baseline_sha256'] and reset['candidate_sha256'] == proof['candidate_sha256']
    for path, digest in reset['input_sha256'].items():
        assert sha(source / 'formal-reset' / path) == digest
    assert reset['proof_log_sha256'] == sha(source / 'formal-reset/proof.log')
    for path in (source / 'formal-reset').iterdir():
        if path.is_file():
            files[Path('formal-reset') / path.name] = path
    archive = {}
    for relative, path in files.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            assert sha(destination) == sha(path), ('Immutable archive differs', relative)
        else:
            shutil.copy2(path, destination)
        archive[relative.as_posix()] = sha(destination)
    result = dict(phase='isolated_candidate_checks_archived', files_sha256=archive,
                  collector_sha256=sha(Path(__file__)), primary_rtl_changed=False)
    (target / 'archive.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Archived isolated candidate checks: {len(archive)} input/report files, two native-reference regressions and Yosys equivalence')


if __name__ == '__main__':
    main()
