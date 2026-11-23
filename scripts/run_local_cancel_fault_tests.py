"""Run selected fatal-close ACK phases as independent cold simulations."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phases', nargs='+', type=int, required=True)
    parser.add_argument('--name-prefix', default='local_cancel_close_fault')
    parser.add_argument('--rtl-override', type=Path, default=Path('build/experiments/local-cancel/rtl'))
    args = parser.parse_args()
    assert len(set(args.phases)) == len(args.phases) and all(0 <= n < 14 for n in args.phases)
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name_prefix)
    root = Path(__file__).resolve().parents[1]
    for phase in args.phases:
        subprocess.run([sys.executable, str(root / 'scripts/run_raw_envelope_tests.py'),
            '--name', args.name_prefix + '_' + str(phase), '--profile', 'duplex',
            '--rtl-override', str(source_path(root, args.rtl_override)),
            '--harness-override', str(root / 'build/experiments/local-cancel/sim/cocotb_two_fpga_enveloped_top.sv'),
            '--test-override', str(source_path(root, 'build/experiments/local-cancel/sim/close-fault-' + str(phase) + '/test_raw_grpc_duplex.py'))],
            check=True, cwd=root)


if __name__ == '__main__':
    main()
