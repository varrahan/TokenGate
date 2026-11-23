"""Replay the five audited dual-ledger scenarios on the cause-capture child."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--private-authority',action='store_true')
    parser.add_argument('--skip-completed',action='store_true',help='Resume only cases without a successful archived conclusion')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    variant='window-authority' if args.private_authority else 'window-cause'
    prefix=variant.replace('-','_')
    cases=[('native','native','build/experiments/post-commit-retire/sim/test_raw_grpc_enveloped.py'),
        ('other_connection','duplex','build/experiments/post-retire-scope/test_raw_grpc_duplex.py'),
        ('ledger_faults','shutdown-faults','build/experiments/window-format/sim/test_raw_shutdown_faults.py'),
        ('owned_gpu_drain','shutdown-faults','build/experiments/window-format/drain/test_raw_shutdown_faults.py'),
        ('retained_shutdown','shutdown-faults','build/experiments/retained-window-reset/test_raw_shutdown_faults.py')]
    if args.private_authority:
        cases=[(name,profile,fixture.replace('build/experiments/window-format/','build/experiments/window-authority/'))
            for name,profile,fixture in cases]
        cases.insert(0,('external_denial_witness','shutdown-faults','build/experiments/window-authority/external/test_raw_shutdown_faults.py'))
    failed=[]
    for name,profile,fixture in cases:
        snapshot=root/'build/wsl-reports'/('raw_envelope_'+prefix+'_'+name)/'snapshot.json'
        if args.skip_completed and snapshot.exists():
            assert json.loads(snapshot.read_text())['exit_code']==0,(name,'Preserve the failed case and choose a new name')
            print('Retaining completed case: '+prefix+'_'+name,flush=True)
            continue
        result=subprocess.run([sys.executable,str(root/'scripts/run_raw_envelope_tests.py'),
            '--name',prefix+'_'+name,'--profile',profile,
            '--rtl-override',str(root/'build/experiments'/variant/'rtl'),
            '--harness-override',str(root/'build/experiments/local-cancel/sim/cocotb_two_fpga_enveloped_top.sv'),
            '--test-override',str(source_path(root, fixture))],cwd=root,check=False)
        if result.returncode:failed.append(name)
    print(json.dumps(dict(cases=[c[0] for c in cases],failed=failed)),flush=True)
    raise SystemExit(bool(failed))


if __name__=='__main__':main()
