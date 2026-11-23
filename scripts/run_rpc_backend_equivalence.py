"""Prove actual RPC backend public-output equivalence with its real memory slot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


TOP = 'rpc_http2_response_partition'
SLOT_HELPERS = [('output', '[1:0]', 'formal_slot_state'),
                ('output', '[71:0]', 'formal_slot_data'), ('output', '[7:0]', 'formal_slot_status'),
                ('output', '', 'formal_slot_ready'), ('output', '', 'formal_slot_valid'),
                ('output', '', 'formal_slot_idle')]


def address_models(original, gate):
    generated = {}
    for label, source, bound in (('gold', original, 'checked_stream_end'), ('gate', gate, 'checked_stream_last')):
        end = re.search(r'wire \[63:0\] stream_end=[^;]+;', source)[0]
        assert 'config_good=stream_bytes>=128&&' in source
        capture = re.search(r'else begin ' + bound + r'<=([^;]+);state<=DREQ;end', source)[1]
        comparison = re.search(r'wire closed_address_good=[^;]+;', source)[0]
        generated[label + '.v'] = '\n'.join([
            f'module address_{label} #(parameter MEMORY_ADDR_WIDTH=23)(',
            'input wire [MEMORY_ADDR_WIDTH-1:0] streams,closed_address,',
            'input wire [MEMORY_ADDR_WIDTH:0] stream_bytes,output wire good);',
            end, 'wire [63:0] ' + bound + '=' + capture + ';', comparison,
            'assign good=closed_address_good;', 'endmodule', ''])
    generated['miter.v'] = '''module address_equivalence #(parameter MEMORY_ADDR_WIDTH=23)(
input wire [MEMORY_ADDR_WIDTH-1:0] streams,closed_address,
input wire [MEMORY_ADDR_WIDTH:0] stream_bytes);
wire gold_good,gate_good;
address_gold #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) gold(.streams(streams),.closed_address(closed_address),.stream_bytes(stream_bytes),.good(gold_good));
address_gate #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) gate(.streams(streams),.closed_address(closed_address),.stream_bytes(stream_bytes),.good(gate_good));
always @* if(stream_bytes>=128)assert(gold_good==gate_good);
endmodule
'''
    generated['proof.ys'] = 'read_verilog -formal gold.v gate.v miter.v\nprep -top address_equivalence -flatten\nsat -prove-asserts -verify -timeout 60\n'
    return generated


def prove_address_cone(root, inputs, sha):
    folder = root / 'build/proof'; folder.mkdir(parents=True, exist_ok=True)
    generated = address_models((source_path(root, 'rtl/gold_input.v')).read_text(), (source_path(root, 'rtl/gate_input.v')).read_text())
    for n, text in generated.items(): (folder / n).write_text(text)
    report = dict(phase='running', proof_engine='algebra', input_sha256=inputs,
        started_utc=datetime.now(timezone.utc).isoformat(), memory_address_width=23,
        proof_scope='actual closed-address comparison using actual CHECK capture expressions, for any pool with at least 128 bytes',
        only_environment_assumption='none; the assertion is conditional on the actual CHECK minimum-pool-size predicate',
        full_backend_public_output_equivalence_verified=False,
        unbounded_post_reset_public_output_equivalence=False)
    try:
        with (folder / 'yosys.log').open('w') as output:
            result = subprocess.run(['yosys', '-T', '-s', 'proof.ys'], cwd=folder, stdout=output, stderr=subprocess.STDOUT, check=False)
        report['yosys_exit_code'] = result.returncode
        assert result.returncode == 0 and 'SAT proof finished - no model found: SUCCESS!' in (folder / 'yosys.log').read_text()
        assert all(sha(source_path(root, n)) == h for n, h in inputs.items())
        report.update(phase='passed', actual_address_comparison_equivalence_verified=True,
            physical_timing_verified=False, full_system_complete=False)
    except BaseException as error:
        report.update(phase='failed', error=str(error)); raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['generated_sha256'] = {n: sha(folder / n) for n in (*generated, 'yosys.log')}
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


def private_registers(source, public):
    source = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
    # ANSI port declarations use commas between input/output directions;
    # private register declarations are in the body after the port terminator.
    source = source[source.index(');') + 2:]
    found = {}
    for width, names in re.findall(r'\breg\s*(\[[^\]]+\])?\s+([^;]+);', source):
        for name in names.split(','):
            name = name.strip()
            assert re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name), name
            if name not in public and name not in ('checked_stream_end', 'checked_stream_last'):
                assert name not in found
                found[name] = width
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--engine', choices=('sat', 'smtbmc', 'algebra'), default='sat')
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name)
        approved = Path.home() / 'development/hardware/parser'
        assert approved.is_dir() and root != approved
        target = approved / 'build/rpc-backend-equivalence' / args.name
        target.mkdir(parents=True, exist_ok=False)
        sources = {'rtl/gold_input.v': source_path(root, Path('rtl') / (TOP + '.v')),
            'rtl/gate_input.v': root / 'build/experiments/checked-close-address/rtl' / (TOP + '.v')}
        for n in ('rtl/memory_command_slot.v', 'scripts/run_rpc_backend_equivalence.py',
                  'tools/generate_bidirectional_application.py', 'tools/generate_two_fpga_application.py', 'tools/rtl_paths.py'):
            sources[n] = source_path(root, n)
        inputs = {}
        for n, p in sources.items():
            destination = target / n; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, destination); inputs[n] = sha(destination)
        (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        print('Frozen actual backend equivalence: ' + str(target), flush=True)
        result = subprocess.run([sys.executable, str(target / 'scripts/run_rpc_backend_equivalence.py'), '--execute', '--engine', args.engine], check=False)
        assert all(sha(target / n) == h for n, h in inputs.items())
        archive = root / 'build/wsl-reports' / ('rpc_backend_equivalence_' + args.name)
        archive.mkdir(parents=True, exist_ok=False)
        for n in inputs:
            p = archive / 'execution-sources' / n; p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / n, p)
        shutil.copy2(target / 'inputs.json', archive / 'inputs.json')
        for n in ('report.json', 'yosys.log', 'gold.v', 'gate.v', 'miter.v', 'memory_command_slot.v', 'proof.ys', 'counterexample.vcd', 'model.smt2', 'base.log', 'induction.log'):
            if (target / 'build/proof' / n).is_file(): shutil.copy2(target / 'build/proof' / n, archive / n)
        (archive / 'snapshot.json').write_text(json.dumps(dict(exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
        print('Archived actual backend equivalence: ' + str(archive), flush=True)
        raise SystemExit(result.returncode)
    assert root.parent == Path.home() / 'development/hardware/parser/build/rpc-backend-equivalence'
    inputs = json.loads((root / 'inputs.json').read_text())
    assert all(sha(source_path(root, n)) == h for n, h in inputs.items())
    if args.engine == 'algebra':
        prove_address_cone(root, inputs, sha)
        return
    sys.path.insert(0, str(root / 'tools'))
    from generate_bidirectional_application import ports
    from generate_two_fpga_application import add_ports, rename
    original = (source_path(root, 'rtl/gold_input.v')).read_text(); gate = (source_path(root, 'rtl/gate_input.v')).read_text()
    public = ports(original, TOP); assert public == ports(gate, TOP)
    private = private_registers(original, {n for _, _, n in public})
    assert private == private_registers(gate, {n for _, _, n in public})
    helpers = [('output', w, 'formal_' + n) for n, w in sorted(private.items())]
    helpers += [('output', '[63:0]', 'formal_bound'), ('output', '', 'formal_early_closed')]
    helpers += SLOT_HELPERS
    folder = root / 'build/proof'; folder.mkdir(parents=True, exist_ok=True)
    for name, source, bound in (('gold', original, 'checked_stream_end'), ('gate', gate, 'checked_stream_last')):
        assert 'IDLE=0,CHECK=1,DREQ=2' in source
        assignments = ['assign formal_' + n + '=' + n + ';' for n in sorted(private)]
        assignments += ['assign formal_bound=' + bound + ';', 'assign formal_early_closed=early_closed;']
        assignments += ['assign formal_slot_' + n + '=slot_' + n + ';' for n in ('data', 'status', 'ready', 'valid', 'idle')]
        source = add_ports(source, TOP, helpers)
        assert source.count('metadata(\n') == 1
        source = source.replace('metadata(\n', 'metadata(\n        .formal_state(formal_slot_state),\n')
        assert source.count('endmodule') == 1
        source = source.replace('endmodule', '\n'.join(assignments) + '\nendmodule')
        (folder / (name + '.v')).write_text(rename(source, TOP, 'backend_' + name))
    slot = add_ports((source_path(root, 'rtl/memory_command_slot.v')).read_text(), 'memory_command_slot', [('output', '[1:0]', 'formal_state')])
    slot = slot.replace('endmodule', 'assign formal_state=state;\nendmodule')
    (folder / 'memory_command_slot.v').write_text(slot)
    lines = ['`default_nettype none', 'module backend_equivalence #(parameter USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384)(',
             ',\n'.join('input wire ' + w + ' ' + n for d, w, n in public if d == 'input'), ');']
    outputs = [p for p in public if p[0] == 'output'] + helpers
    for name in ('gold', 'gate'):
        lines += ['wire ' + w + ' ' + name + '_' + n + ';' for _, w, n in outputs]
        connections = [f'.{n}({n if d == "input" else name + "_" + n})' for d, _, n in public + helpers]
        lines += [f'backend_{name} #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) {name}(' + ','.join(connections) + ');']
    lines += ['reg initialized=0;', 'always @(posedge clk)begin', 'initialized<=1;',
              'if(!initialized)assume(rst);', 'if(initialized)begin']
    lines += [f'assert(gold_{n}==gate_{n});' for _, _, n in outputs if n != 'formal_bound']
    lines += ['assert(gold_formal_state<=27);',
              "assert(gold_formal_bound<=(64'd1<<MEMORY_ADDR_WIDTH));",
              "if(gold_formal_bound==0)assert(gate_formal_bound==0);",
              "else begin assert(gold_formal_bound>=64'd128);assert(gold_formal_bound==gate_formal_bound+64'd128);end",
              "if(gold_formal_state==2)assert(gold_formal_bound>=64'd128);",
              'end', 'end', 'endmodule', '`default_nettype wire']
    (folder / 'miter.v').write_text('\n'.join(lines) + '\n')
    proof = 'read_verilog -formal -sv memory_command_slot.v gold.v gate.v miter.v\nprep -top backend_equivalence -flatten\ntechmap\nopt -full\nabc -g simple\nopt_clean\nsat -seq 1 -tempinduct -maxsteps 8 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n'
    if args.engine == 'smtbmc':
        proof = 'read_verilog -formal -sv memory_command_slot.v gold.v gate.v miter.v\nprep -top backend_equivalence -flatten\ndffunmap\nwrite_smt2 -wires model.smt2\n'
    (folder / 'proof.ys').write_text(proof)
    version = subprocess.run(['yosys', '-V'], check=True, capture_output=True, text=True).stdout.strip()
    report = dict(phase='running', input_sha256=inputs, started_utc=datetime.now(timezone.utc).isoformat(),
        yosys_version=version, actual_public_outputs=sum(d == 'output' for d, _, _ in public),
        actual_private_register_equality_lemmas=sorted(private), actual_memory_command_slot_included=True,
        memory_command_slot_observation_wires_only=True,
        asserted_bound_relation=True, memory_address_width=23,
        only_environment_assumption='reset on the initial sampled clock; all later inputs unconstrained',
        maximum_induction_steps=6 if args.engine == 'smtbmc' else 8,
        proof_engine=args.engine, timeout_per_solver_instance_seconds=60)
    try:
        with (folder / 'yosys.log').open('w') as output:
            result = subprocess.run(['yosys', '-T', '-s', 'proof.ys'], cwd=folder, stdout=output, stderr=subprocess.STDOUT, check=False)
        report['yosys_exit_code'] = result.returncode
        assert result.returncode == 0
        if args.engine == 'sat':
            assert 'Induction step proven: SUCCESS!' in (folder / 'yosys.log').read_text()
        else:
            commands = {}
            for name, extra in (('base', []), ('induction', ['-i'])):
                command = ['yosys-smtbmc', '-s', 'z3', '-t', '6', '--noprogress', '--timeout', '60', *extra, 'model.smt2']
                commands[name] = command
                with (folder / (name + '.log')).open('w') as output:
                    checked = subprocess.run(command, cwd=folder, stdout=output, stderr=subprocess.STDOUT, check=False)
                report[name + '_exit_code'] = checked.returncode
                assert checked.returncode == 0 and 'Status: PASSED' in (folder / (name + '.log')).read_text()
            report['smtbmc_commands'] = commands
        assert all(sha(source_path(root, n)) == h for n, h in inputs.items())
        report.update(phase='passed', unbounded_post_reset_public_output_equivalence=True,
            physical_timing_verified=False, full_system_complete=False)
    except BaseException as error:
        report.update(phase='failed', error=str(error)); raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['generated_sha256'] = {n: sha(folder / n) for n in ('gold.v', 'gate.v', 'miter.v', 'memory_command_slot.v', 'proof.ys', 'yosys.log', 'model.smt2', 'base.log', 'induction.log') if (folder / n).is_file()}
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
