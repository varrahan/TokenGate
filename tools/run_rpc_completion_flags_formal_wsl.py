"""Full production response-partition equivalence and state-class invariants."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess

from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe
from verify_two_fpga_application import closure


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True)
    ap.add_argument('--strengthen-state', action='store_true'); args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    candidate = root / 'build/experiments/rpc-completion-flags'
    generation = json.loads((candidate / 'generation.json').read_text())
    assert all(sha(candidate / n) == h for n, h in generation['outputs_sha256'].items())
    approved = Path('/home/varrahan/development/hardware/parser')
    assert approved.is_dir()
    folder = approved / 'build/rpc-completion-flags-formal' / args.name
    archive = root / 'build/wsl-reports' / args.name
    assert not archive.exists()
    folder.mkdir(parents=True, exist_ok=False)
    module = 'rpc_http2_response_partition'
    deps = closure(module, candidate)
    assert set(deps) == {module, 'memory_command_slot'}
    reference = root / 'build/experiments/payload-event-buffer/rtl' / (module + '.v')
    old = reference.read_text(); new = deps[module].read_text()
    interface = ports(old, module)
    assert interface == ports(new, module)
    # Observation alone adds no constraints to any production input or state.
    symbols = [('[4:0]', 'state'), ('', 'base_complete')]
    strengthened = []
    if args.strengthen_state:
        body = old[old.index(');') + 2:]
        for match in re.finditer(r'\breg\s*(\[[^\]]+\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;', body):
            for n in match[2].replace(' ', '').split(','):
                if n != 'state': strengthened.append((match[1] or '', n))
        assert len(strengthened) == 41 and len({n for w, n in strengthened}) == 41
        strengthened += [('[71:0]', 'slot_data'), ('[7:0]', 'slot_status'), ('[1:0]', 'metadata_state')]
        symbols += strengthened
        def child_state(text):
            marker = 'memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) metadata('
            before = '.idle(slot_idle));'
            after = '.idle(slot_idle),.formal_state(metadata_state));'
            assert text.count(marker) == text.count(before) == 1
            changed = text.replace(marker, 'wire [1:0] metadata_state;\n    ' + marker).replace(before, after)
            assert changed.replace('wire [1:0] metadata_state;\n    ', '').replace(after, before) == text
            return changed
        old_observed, new_observed = child_state(old), child_state(new)
    else:
        old_observed, new_observed = old, new
    golden = observe(old_observed, module, symbols)
    gold_name = module + '_reference'
    assert golden.count('module ' + module + ' #(') == 1
    golden = golden.replace('module ' + module + ' #(', 'module ' + gold_name + ' #(')
    actual = observe(new_observed, module, symbols + [('', 'transport_active')])
    for name, raw in [('reference-original.v', reference.read_bytes()), ('candidate-original.v', deps[module].read_bytes()),
                      ('memory_command_slot.v', deps['memory_command_slot'].read_bytes())]:
        (folder / name).write_bytes(raw)
    if args.strengthen_state:
        shutil.copy2(deps['memory_command_slot'], folder / 'memory-command-slot-original.v')
        (folder / 'memory_command_slot.v').write_text(observe(deps['memory_command_slot'].read_text(), 'memory_command_slot', [('[1:0]', 'state')]))
    (folder / 'reference.v').write_text(golden)
    (folder / 'candidate.v').write_text(actual)
    lines = ['`default_nettype none', 'module completion_flags_miter #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384)(',
        ',\n'.join(f'input wire {width} {name}' for direction, width, name in interface if direction == 'input'), ');',
        'reg past_valid=0;always @(posedge clk)past_valid<=1;', 'always @*if(!past_valid)assume(rst);',
        'wire [4:0] old_state,new_state;wire old_complete,new_complete,new_transport;']
    outputs = [(w, n) for d, w, n in interface if d == 'output']
    lines += [f'wire {w} old_{n},new_{n};' for w, n in outputs]
    lines += [f'wire {w} old_internal_{n},new_internal_{n};' for w, n in strengthened]
    for name, prefix in ((gold_name, 'old'), (module, 'new')):
        mapping = [f'.{n}({n if d == "input" else prefix + "_" + n})' for d, w, n in interface]
        mapping += [f'.formal_state({prefix}_state)', f'.formal_base_complete({prefix}_complete)']
        mapping += [f'.formal_{n}({prefix}_internal_{n})' for w, n in strengthened]
        if prefix == 'new': mapping.append('.formal_transport_active(new_transport)')
        lines += [name + ' #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) ' + prefix + '_dut(', ',\n'.join(mapping), ');']
    lines += ['always @*if(past_valid)begin', 'assert(old_state==new_state);', 'assert(old_complete==new_complete);',
        'assert(new_complete==(new_state==19||new_state>=20));', 'assert(new_transport==(new_state>=20));']
    # RESULT's numeric value is read from the production constants, not guessed.
    result = re.search(r'\bRESULT=(\d+)', old)
    assert result is not None
    assert re.search(r'\bT_CHECK=20\b', old)
    lines = [line.replace('new_state==19||', 'new_state==' + result[1] + '||') for line in lines]
    lines += [f'assert(old_{n}==new_{n});' for w, n in outputs]
    lines += [f'assert(old_internal_{n}==new_internal_{n});' for w, n in strengthened]
    lines += ['end', 'endmodule', '`default_nettype wire', '']
    (folder / 'miter.sv').write_text('\n'.join(lines))
    script = '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
prep -top completion_flags_miter -flatten
memory_map
opt
write_json netlist.json
sat -verify -prove-asserts -set-assumes -seq 2 -tempinduct -tempinduct-def -set-init-def -set-def-inputs -maxsteps 12 -timeout 45 -show-ports -dump_vcd counterexample.vcd
'''
    (folder / 'proof.ys').write_text(script)
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    inputs = {p.name: sha(p) for p in folder.iterdir() if p.is_file()}
    record = dict(phase='proving', started_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(candidate / 'generation.json'), inputs_sha256=inputs,
        exact_response_subtree_modules=2, actual_production_memory_slot=True,
        compared_output_ports=[n for w, n in outputs], state_class_assertions=2,
        compared_internal_registers_and_memory_state=[n for w, n in strengthened],
        initial_reset_required=True, later_resets_arbitrary=True, input_stability_assumptions=False,
        output_comparison_unconditional_after_initial_reset=True, two_state_formal=True,
        passed=False, full_protocol_matrix_verified=False, native_timing_verified=False, full_system_complete=False)
    try:
        with (folder / 'stdout.log').open('w') as stream:
            code = subprocess.call(['yosys', '-Q', '-T', '-l', 'proof.log', '-s', 'proof.ys'], cwd=folder, stdout=stream, stderr=subprocess.STDOUT)
        log = (folder / 'proof.log').read_text()
        assert code == 0 and 'Induction step proven: SUCCESS!' in log, (code, 'Retained proof output and counterexample')
        assert not re.search(r'^ERROR:', log, re.M)
        assert all(sha(folder / n) == h for n, h in inputs.items())
        record.update(phase='rpc_completion_flags_unbounded_equivalence_verified', passed=True,
            proof_log_sha256=sha(folder / 'proof.log'), netlist_sha256=sha(folder / 'netlist.json'))
    except BaseException as error:
        record.update(phase='failed', error=str(error)); raise
    finally:
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (folder / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
        shutil.copytree(folder, archive)
    print(json.dumps(dict(phase=record['phase'], compared_output_ports=len(outputs), passed=record['passed'])))


if __name__ == '__main__':
    main()
