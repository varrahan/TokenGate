"""Structural cut-point induction, plus a separate actual-reset base proof."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True); args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    original = root / 'build/wsl-reports/rpc_completion_flags_formal_v2_20261122'
    prior = json.loads((original / 'report.json').read_text())
    assert prior['phase'] == 'failed' and not prior['passed']
    assert len(prior['compared_internal_registers_and_memory_state']) == 44
    assert 'ERROR: Called with -verify and proof did time out!' in (original / 'proof.log').read_text()
    folder = Path('/home/varrahan/development/hardware/parser/build/rpc-completion-flags-formal') / args.name
    archive = root / 'build/wsl-reports' / args.name
    assert not archive.exists()
    folder.mkdir(parents=True, exist_ok=False)
    for n, digest in prior['inputs_sha256'].items():
        assert sha(original / n) == digest
        shutil.copy2(original / n, folder / n)
    reference = folder / 'reference.v'
    text = reference.read_text()
    insert = 'wire transport_active=state>=T_CHECK;\n'
    # Match the additional candidate observation port with the original state
    # expression. No production state equation or handshake is changed.
    marker = 'output wire  formal_base_complete'
    assert text.count(marker) == 1
    changed = text.replace(marker, marker + ',\noutput wire formal_transport_active')
    assignments = insert + 'assign formal_transport_active=transport_active;\n'
    changed = changed.replace('endmodule', assignments + 'endmodule')
    assert changed.replace(assignments, '').replace(marker + ',\noutput wire formal_transport_active', marker) == text
    reference.write_text(changed)
    # The base proof retains every output/internal-state assertion and the
    # initial-reset-only assumption of the full production miter.
    base = '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
prep -top completion_flags_miter -flatten
memory_map
opt
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 90
'''
    structural = '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v
hierarchy -check
proc
memory_map
flatten rpc_http2_response_partition_reference rpc_http2_response_partition
opt_clean
equiv_make rpc_http2_response_partition_reference rpc_http2_response_partition completion_flags_equivalence
hierarchy -top completion_flags_equivalence
opt_clean
equiv_simple -seq 1
equiv_induct -seq 1
equiv_status -assert
write_json equivalence-netlist.json
'''
    (folder / 'reset-base.ys').write_text(base)
    (folder / 'structural.ys').write_text(structural)
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    inputs = {p.name: sha(p) for p in folder.iterdir() if p.is_file()}
    report = dict(phase='proving', started_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=prior['generation_sha256'], prior_full_miter_run='rpc_completion_flags_formal_v2_20261122',
        inputs_sha256=inputs, prior_report_sha256=sha(original / 'report.json'),
        observation_extension_inverse_verified=True, compared_output_ports=prior['compared_output_ports'],
        compared_internal_registers_and_memory_state=prior['compared_internal_registers_and_memory_state'],
        reset_base_steps=2, structural_induction_steps=1,
        initial_reset_required=True, later_resets_arbitrary=True, input_stability_assumptions=False,
        actual_production_subtree_modules=2, actual_memory_slot_preserved=True,
        passed=False, full_protocol_verified=False, native_timing_verified=False, full_system_complete=False)
    try:
        for label, script in [('reset-base', base), ('structural', structural)]:
            with (folder / (label + '-stdout.log')).open('w') as stream:
                code = subprocess.call(['yosys', '-Q', '-T', '-l', label + '.log', '-s', label + '.ys'], cwd=folder, stdout=stream, stderr=subprocess.STDOUT)
            log = (folder / (label + '.log')).read_text()
            assert code == 0 and not re.search(r'^ERROR:', log, re.M), (label, code, 'Retained proof evidence')
            if label == 'reset-base': assert 'SAT proof finished - no model found: SUCCESS!' in log
            else: assert 'Equivalence successfully proven!' in log
        assert all(sha(folder / n) == digest for n, digest in inputs.items())
        report.update(phase='rpc_completion_flags_structural_induction_and_reset_base_verified', passed=True,
            reset_base_log_sha256=sha(folder / 'reset-base.log'), structural_log_sha256=sha(folder / 'structural.log'),
            equivalence_netlist_sha256=sha(folder / 'equivalence-netlist.json'))
    except BaseException as error:
        report.update(phase='failed', error=str(error)); raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        shutil.copytree(folder, archive)
    print(json.dumps(dict(phase=report['phase'], passed=report['passed'])))


if __name__ == '__main__':
    main()
