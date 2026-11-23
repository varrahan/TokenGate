"""Run existing frozen protocol cases with explicit global progress geometry."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser();selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--cases',nargs='+')
    selection.add_argument('--retirement-matrix',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    cases=json.loads((root/'build/experiments/progress-format/regressions/generation.json').read_text())['cases']
    if args.retirement_matrix:args.cases=[n for n in cases if n.startswith('retire_fault_')];assert len(args.cases)==39
    assert len(set(args.cases))==len(args.cases) and all(n in cases for n in args.cases)
    failed=[];deferred=[]
    for index,name in enumerate(args.cases):
        case=cases[name]
        result=subprocess.run([sys.executable,str(root/'scripts/run_raw_envelope_tests.py'),
            '--name','progress_format_'+name,'--profile',case['profile'],
            '--rtl-override',str(root/'build/experiments/progress-format/rtl'),
            '--harness-override',str(root/'build/experiments/local-cancel/sim/cocotb_two_fpga_enveloped_top.sv'),
            '--test-override',str(root/case['fixture'])],cwd=root,check=False)
        if result.returncode==75:deferred=args.cases[index:];break
        if result.returncode:failed.append(name)
    print(json.dumps(dict(cases=args.cases,failed=failed,deferred_for_disk_headroom=deferred)),flush=True)
    raise SystemExit(75 if deferred else bool(failed))


if __name__=='__main__':main()
