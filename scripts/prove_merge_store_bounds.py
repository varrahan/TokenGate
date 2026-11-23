"""Prove an isolated bounds-cone candidate with the installed WSL Yosys."""
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
    output = root / 'build/isolated-store-bounds/formal'
    output.mkdir(parents=True, exist_ok=False)
    baseline = args.candidate.parent / 'baseline-bpe_external_merge_unit.v'
    for source, name in [(baseline, 'baseline.v'), (args.candidate, 'candidate.v')]:
        shutil.copy2(source, output / name)
    # store_good differs outside STORE_CHECK, where it has no state-machine
    # effect. It must remain an unmatched internal cone, not an assumed cutpoint.
    # All outputs and matching state registers are still checked by equiv_make.
    (output / 'internal-only.txt').write_text('store_good\n')
    script = """read_verilog baseline.v
rename bpe_external_merge_unit gold
read_verilog candidate.v
rename bpe_external_merge_unit gate
proc
opt_clean
equiv_make -blacklist internal-only.txt gold gate equiv
hierarchy -top equiv
equiv_simple -undef
equiv_induct -undef -seq 4
equiv_status -assert
write_json proven.json
"""
    (output / 'prove.ys').write_text(script)
    command = ['yosys', '-Q', '-T', '-s', 'prove.ys']
    with (output / 'proof.log').open('w') as log:
        result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=False)
    log = (output / 'proof.log').read_text()
    print(log[-2400:])
    if result.returncode:
        raise SystemExit(result.returncode)
    assert 'Equivalence successfully proven!' in log
    design = json.loads((output / 'proven.json').read_text())['modules']['equiv']
    comparisons = [cell for cell in design['cells'].values() if cell['type'] == '$equiv']
    assert comparisons and all(cell['connections']['A'] == cell['connections']['B'] for cell in comparisons)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    proof = dict(phase='component_equivalence_proven_for_synced_reset_state',
        baseline_sha256=sha(baseline), candidate_sha256=sha(args.candidate),
        yosys_version=subprocess.check_output(['yosys', '-V'], text=True).strip(),
        formal_compare_cells=len(comparisons), unmatched_internal_cones=['store_good'],
        unmatched_internal_cones_assumed_equal=False, all_output_ports_checked=True,
        memory_addr_width=23, user_width=16, id_width=17, rank_width=17,
        induction_depth=4, undef_modeling=True, primary_rtl_changed=False,
        input_sha256={name: sha(output / name) for name in ('baseline.v', 'candidate.v', 'internal-only.txt', 'prove.ys')},
        proof_log_sha256=sha(output / 'proof.log'), proven_netlist_sha256=sha(output / 'proven.json'),
        verifier_sha256=sha(Path(__file__)), full_system_complete=False)
    (output / 'proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
