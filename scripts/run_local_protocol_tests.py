"""Run generated native/RFC connection errors against the actual FPGA join."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', nargs='+', required=True)
    parser.add_argument('--name-prefix', default='packer_keep_protocol')
    parser.add_argument('--rtl-override', type=Path, default=Path('build/experiments/packer-keep/rtl'))
    parser.add_argument('--case-root', type=Path, default=Path('build/experiments/local-protocol-cases'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / args.case_root
    generation = json.loads((folder/'generation.json').read_text())
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name_prefix)
    assert len(set(args.cases)) == len(args.cases) and all(n in generation['cases'] for n in args.cases)
    for name in args.cases:
        fixture = folder/name/'test_raw_grpc_duplex.py'
        assert hashlib.sha256(fixture.read_bytes()).hexdigest() == generation['cases'][name]['test_sha256']
        subprocess.run([sys.executable,str(root/'scripts/run_raw_envelope_tests.py'),
            '--name',args.name_prefix+'_'+name,'--profile','duplex',
            '--rtl-override',str(root/args.rtl_override),
            '--harness-override',str(root/'build/experiments/local-cancel/sim/cocotb_two_fpga_enveloped_top.sv'),
            '--test-override',str(fixture)],check=True,cwd=root)


if __name__=='__main__':
    main()
