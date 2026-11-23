"""Probe unmodified native XPM support for the complete joint validation top."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / 'build/experiments/dual-fpga-hyperram'
    generation = json.loads((folder / 'generation.json').read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert all(sha(folder / name) == digest for name, digest in generation['outputs_sha256'].items())
    assert shutil.which('verilator')
    output = root / 'build/validation/dual-fpga-hyperram-verilator-lint.json'
    log = output.with_suffix('.log')
    assert not output.exists() and not log.exists()
    command = ['verilator', '--lint-only', '--timing', '-Wno-fatal', '-DOBSOLETE',
        '--top-module', 'two_fpga_hyperram_application']
    command += [str(path) for path in sorted((folder / 'joint/rtl').glob('*.v'))]
    command += [str(folder / 'joint/vendor' / name) for name in ('glbl.v','xpm_cdc.sv','xpm_memory.sv','xpm_fifo.sv')]
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), command=command,
        generation_sha256=sha(folder / 'generation.json'), compatibility_defines=['OBSOLETE'],
        native_vendor_sources_unmodified=True, portable_memory_backend=False,
        unsupported_construct_blackboxing=False, full_system_complete=False)
    output.write_text(json.dumps(record, indent=2) + '\n')
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=folder, stdout=stream, stderr=subprocess.STDOUT)
    record.update(finished_utc=datetime.now(timezone.utc).isoformat(), exit_code=result.returncode,
                  lint_passed=result.returncode == 0, log_sha256=sha(log))
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ('exit_code','lint_passed','native_vendor_sources_unmodified')}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
