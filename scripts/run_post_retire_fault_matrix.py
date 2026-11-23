"""Run selected retirement ACK faults as independent frozen full-model tests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',nargs='+',required=True)
    parser.add_argument('--name-prefix',default='post_retire_fault')
    parser.add_argument('--rtl-override',type=Path,default=Path('build/experiments/post-commit-retire/rtl'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    folder=root/'build/experiments/post-retire-fault-matrix'
    cases=json.loads((folder/'generation.json').read_text())['cases']
    assert len(set(args.cases))==len(args.cases) and all(n in cases for n in args.cases)
    failed=[];deferred=[]
    for index,name in enumerate(args.cases):
        result=subprocess.run([sys.executable,str(root/'scripts/run_raw_envelope_tests.py'),
            '--name',args.name_prefix+'_'+name,'--profile','duplex',
            '--rtl-override',str(args.rtl_override.resolve()),
            '--harness-override',str(root/'build/experiments/local-cancel/sim/cocotb_two_fpga_enveloped_top.sv'),
            '--test-override',str(folder/name/'test_raw_grpc_duplex.py')],cwd=root,check=False)
        if result.returncode==75:
            deferred=args.cases[index:]
            break
        if result.returncode:failed.append(name)
    print(json.dumps(dict(cases=args.cases,failed=failed,deferred_for_disk_headroom=deferred)),flush=True)
    raise SystemExit(75 if deferred else bool(failed))


if __name__=='__main__':main()
