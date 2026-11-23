"""Collect strict native-Verilog frontend errors for every current Parser file."""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    assembly = root / 'build/experiments/dual-fpga-hyperram'
    generation = json.loads((assembly / 'generation.json').read_text())
    folder = root / 'build/validation/parser_native_declaration_scan_20261122'
    folder.mkdir(parents=True, exist_ok=False)
    records = {}
    for path in sorted((assembly / 'parser/rtl').glob('*.v')):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == generation['outputs_sha256']['parser/rtl/' + path.name]
        with (folder / (path.stem + '.log')).open('w') as log:
            code = subprocess.run(['C:/AMDDesignTools/2025.2/Vivado/bin/xvlog.bat', '--log',
                path.stem + '-compiler.log', str(path)], cwd=folder, stdout=log, stderr=subprocess.STDOUT).returncode
        text = (folder / (path.stem + '.log')).read_text(errors='replace')
        errors = [line for line in text.splitlines() if line.startswith('ERROR:')]
        records[path.name] = dict(exit_code=code, source_sha256=digest, errors=errors)
        (folder / 'report.json').write_text(json.dumps(records, indent=2) + '\n')
        if code:
            print(json.dumps(dict(file=path.name, errors=len(errors))), flush=True)
    assert len(records) == 76
    print(json.dumps(dict(files=len(records), failed=[name for name, row in records.items() if row['exit_code']])), flush=True)


if __name__ == '__main__':
    main()
