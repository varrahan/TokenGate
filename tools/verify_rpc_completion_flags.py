"""Audit exact registered flags, actual reset base, and full subtree induction."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    parent = read(root / 'build/validation/payload-event-buffer-corpus.json')
    native = read(root / 'build/validation/payload-event-buffer-parser-native.json')
    assert parent['key'] == 'f50480b11ead03b3' and native['key'] == '56d9fecac3bc5087'
    assert parent['full_native_corpus_verified'] and native['setup_slack_ns'] == -1.142
    candidate = root / 'build/experiments/rpc-completion-flags'
    generation = read(candidate / 'generation.json')
    assert generation['parent_corpus_audit_key'] == parent['key'] and generation['parent_native_audit_key'] == native['key']
    assert sha(candidate / 'generate_rpc_completion_flags.py') == generation['generator_sha256']
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', candidate).items()}
    assert len(parser) == 77 and parser == {Path(n).stem: h for n, h in generation['outputs_sha256'].items()}
    assert {n for n in parser if parser[n] != parent['executed_parser_sha256'][n]} == {'rpc_http2_response_partition'}
    name = 'rpc_http2_response_partition'
    p = candidate / 'rtl' / (name + '.v')
    actual = p.read_text()
    prior_source = root / 'build/experiments/payload-event-buffer/rtl' / p.name
    assert sha(prior_source) == parent['executed_parser_sha256'][name]
    restored = actual
    assert len(generation['source_edit_certificate']) == 8
    for old, new in reversed(generation['source_edit_certificate']):
        assert restored.count(new) == 1
        restored = restored.replace(new, old)
    assert restored.replace('\n', generation['original_newline']).encode() == prior_source.read_bytes()
    assert ports(actual, name) == ports(restored, name)
    archive = root / 'build/wsl-reports/rpc_completion_flags_structural_v1_20261122'
    report = read(archive / 'report.json')
    assert report['phase'] == 'rpc_completion_flags_structural_induction_and_reset_base_verified' and report['passed']
    assert report['generation_sha256'] == sha(candidate / 'generation.json')
    for path, digest in report['inputs_sha256'].items():
        assert sha(archive / path) == digest, path
    assert sha(archive / 'reference-original.v') == sha(prior_source)
    assert sha(archive / 'candidate-original.v') == sha(p)
    slot = candidate / 'rtl/memory_command_slot.v'
    assert sha(archive / 'memory-command-slot-original.v') == sha(slot)
    assert (archive / 'memory_command_slot.v').read_text() == observe(slot.read_text(), 'memory_command_slot', [('[1:0]', 'state')])
    body = restored[restored.index(');') + 2:]
    internal = [(m[1] or '', n) for m in re.finditer(r'\breg\s*(\[[^\]]+\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;', body)
        for n in m[2].replace(' ', '').split(',') if n != 'state']
    assert len(internal) == 41
    internal += [('[71:0]', 'slot_data'), ('[7:0]', 'slot_status'), ('[1:0]', 'metadata_state')]
    assert [n for w, n in internal] == report['compared_internal_registers_and_memory_state']
    symbols = [('[4:0]', 'state'), ('', 'base_complete')] + internal
    def child_observation(text):
        marker = 'memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) metadata('
        assert text.count(marker) == text.count('.idle(slot_idle));') == 1
        return text.replace(marker, 'wire [1:0] metadata_state;\n    ' + marker).replace('.idle(slot_idle));', '.idle(slot_idle),.formal_state(metadata_state));')
    expected_candidate = observe(child_observation(actual), name, symbols + [('', 'transport_active')])
    assert (archive / 'candidate.v').read_text() == expected_candidate
    expected_reference = observe(child_observation(restored), name, symbols)
    expected_reference = expected_reference.replace('module ' + name + ' #(', 'module ' + name + '_reference #(')
    marker = 'output wire  formal_base_complete'
    expected_reference = expected_reference.replace(marker, marker + ',\noutput wire formal_transport_active')
    expected_reference = expected_reference.replace('endmodule', 'wire transport_active=state>=T_CHECK;\nassign formal_transport_active=transport_active;\nendmodule')
    assert (archive / 'reference.v').read_text() == expected_reference
    interface = ports(restored, name)
    outputs = [n for d, w, n in interface if d == 'output']
    assert outputs == report['compared_output_ports'] and len(outputs) == 72
    miter = (archive / 'miter.sv').read_text()
    assert miter.count('assume(') == 1 and 'always @*if(!past_valid)assume(rst);' in miter
    assertions = re.findall(r'assert\(([^;]+)\);', miter)
    assert assertions == ['old_state==new_state', 'old_complete==new_complete',
        'new_complete==(new_state==19||new_state>=20)', 'new_transport==(new_state>=20)'] + [
        f'old_{n}==new_{n}' for n in outputs] + [f'old_internal_{n}==new_internal_{n}' for w, n in internal]
    assert 'always @*if(past_valid)begin\nassert(old_state==new_state);' in miter
    for d, w, n in interface:
        if d == 'input': assert miter.count(f'.{n}({n})') == 2, n
        else:
            assert miter.count(f'.{n}(old_{n})') == miter.count(f'.{n}(new_{n})') == 1
    base = (archive / 'reset-base.ys').read_text()
    assert base == '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
prep -top completion_flags_miter -flatten
memory_map
opt
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 90
'''
    structural = (archive / 'structural.ys').read_text()
    assert structural == '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v
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
    base_log = (archive / 'reset-base.log').read_text()
    proof_log = (archive / 'structural.log').read_text()
    assert sha(archive / 'reset-base.log') == report['reset_base_log_sha256']
    assert sha(archive / 'structural.log') == report['structural_log_sha256']
    assert 'SAT proof finished - no model found: SUCCESS!' in base_log
    assert 'Proof for induction step holds. Entire workset of 3220 cells proven!' in proof_log
    assert 'Of those cells 4292 are proven and 0 are unproven.' in proof_log and 'Equivalence successfully proven!' in proof_log
    assert not re.search(r'^ERROR:', base_log + proof_log, re.M)
    netlist = read(archive / 'equivalence-netlist.json')
    assert sha(archive / 'equivalence-netlist.json') == report['equivalence_netlist_sha256']
    cells = [c for c in netlist['modules']['completion_flags_equivalence']['cells'].values() if c['type'] == '$equiv']
    assert len(cells) == 4292 and all(c['connections']['A'] == c['connections']['B'] for c in cells)
    prior_runs = {}
    for run in ('rpc_completion_flags_formal_v1_20261122', 'rpc_completion_flags_formal_v2_20261122'):
        folder = root / 'build/wsl-reports' / run
        failed = read(folder / 'report.json')
        assert not failed['passed'] and 'ERROR: Called with -verify and proof did time out!' in (folder / 'proof.log').read_text()
        prior_runs[run] = dict(phase='inconclusive_timeout', report_sha256=sha(folder / 'report.json'), proof_log_sha256=sha(folder / 'proof.log'))
    result = dict(phase='rpc_completion_flags_source_and_equivalence_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_corpus_audit_key=parent['key'], parent_native_audit_key=native['key'], exact_parser_modules=77,
        source_edit_replay_verified=True, external_ports_unchanged=True, only_changed_module=name,
        executed_parser_sha256=parser, generation_sha256=sha(candidate / 'generation.json'),
        full_production_response_subtree_induction_verified=True, actual_memory_slot_included=True,
        original_output_ports_compared=72, original_internal_registers_and_slot_state_compared=44,
        proven_equivalence_cells=4292, actual_initial_reset_base_verified=True,
        initial_reset_required=True, arbitrary_later_resets_and_inputs=True, input_stability_assumptions=False,
        two_state_formal=True, prior_inconclusive_runs_preserved=prior_runs,
        fresh_full_application_corpus_verified=False, full_protocol_matrix_verified=False,
        native_timing_verified=False, native_vendor_runtime_verified=False, full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix(): sha(p) for p in archive.iterdir() if p.is_file()}, verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/rpc-completion-flags-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    for destination in (evidence / 'audit.json', root / 'build/validation/rpc-completion-flags.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'proven_equivalence_cells')}))


if __name__ == '__main__':
    main()
