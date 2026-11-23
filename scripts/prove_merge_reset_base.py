"""Check the reset base case complementing the component induction proof."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    root = Path.home() / 'development/hardware/parser'
    output = root / 'build/isolated-store-bounds/formal-reset'
    output.mkdir(parents=True, exist_ok=False)
    for source, name in [(args.candidate.parent / 'baseline-bpe_external_merge_unit.v', 'baseline.v'),
                         (args.candidate, 'candidate.v')]:
        shutil.copy2(source, output / name)
    script = """read_verilog baseline.v
rename bpe_external_merge_unit gold
read_verilog candidate.v
rename bpe_external_merge_unit gate
proc
opt_clean
miter -equiv -make_outputs -flatten gold gate reset_miter
prep -top reset_miter -flatten
sat -seq 4 -set-at 1 in_rst 1 -set-def-inputs -enable_undef -prove-skip 1 -prove trigger 0 -verify
"""
    (output / 'prove.ys').write_text(script)
    with (output / 'proof.log').open('w') as log:
        result = subprocess.run(['yosys', '-Q', '-T', '-s', 'prove.ys'], cwd=output,
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    log = (output / 'proof.log').read_text()
    print(log[-1800:])
    if result.returncode:
        raise SystemExit(result.returncode)
    assert 'SAT proof finished - no model found: SUCCESS!' in log
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    proof = dict(phase='reset_base_case_proven', baseline_sha256=sha(output / 'baseline.v'),
        candidate_sha256=sha(output / 'candidate.v'), checked_cycles_after_reset=[2, 3, 4],
        reset_constraint='rst=1 at cycle 1; later inputs/reset unconstrained and defined',
        inputs_assumed_equal=True, output_cones_excluded=[], undef_modeling=True,
        parameters=dict(memory_addr_width=23, user_width=16, id_width=17, rank_width=17),
        input_sha256={name: sha(output / name) for name in ('baseline.v', 'candidate.v', 'prove.ys')},
        proof_log_sha256=sha(output / 'proof.log'), verifier_sha256=sha(Path(__file__)), full_system_complete=False)
    (output / 'proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
