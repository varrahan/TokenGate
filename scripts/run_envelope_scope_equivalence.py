"""Prove the actual saved cancellation-scope cone for arbitrary capture order."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


SCOPE = ('context_base', 'context_bytes', 'stream_base', 'stream_bytes', 'window_base', 'window_bytes', 'work_floor')


def model(source, label):
    descriptor = re.search(r'if\(([^()]*)\)begin\s*(?:held_credit_\w+<=0;\s*)*saved_frame_cfg_context_base<=cfg_context_base;', source)[1]
    owner_capture = re.search(r'if\(([^()]*)\)begin envelope_owner<=s_axis_tokens_tuser;', source)[1]
    freeze = re.search(r'if\(([^()]*)\)begin envelope_frozen_user<=freeze_user;', source)[1]
    assert descriptor == owner_capture == 's_axis_tokens_tvalid&&s_axis_tokens_tready'
    assert freeze == 'freeze_valid&&freeze_ready'
    assert 'if(retire)envelope_owned<=0;' in source
    fields = [('envelope_frozen_user', 'envelope_owner', 'freeze_user', 's_axis_tokens_tuser', '[USER_WIDTH-1:0]'),
              ('envelope_frozen_stream', 'envelope_stream', 'freeze_stream', 's_stream', '[30:0]')]
    fields += [('envelope_frozen_' + n, 'saved_frame_cfg_' + n, 'freeze_cfg_' + n, 'cfg_' + n,
                '[MEMORY_ADDR_WIDTH:0]' if n.endswith('bytes') else '[MEMORY_ADDR_WIDTH-1:0]') for n in SCOPE]
    public = [('', n) for n in ('clk', 'rst', 's_axis_tokens_tvalid', 's_axis_tokens_tready', 'freeze_valid', 'freeze_ready', 'grant_frozen', 'retire')]
    for _, _, a, b, width in fields: public += [(width, a), (width, b)]
    lines = ['module envelope_scope_' + label + ' #(parameter USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join('input wire ' + w + ' ' + n for w, n in public) + ',',
        'output wire scope_value,output wire [2*(USER_WIDTH+31+7*MEMORY_ADDR_WIDTH+3):0] observed_scope', ');']
    resets = ['envelope_owned<=0;']; d_capture = ['envelope_owned<=1;']; f_capture = []; observed = ['envelope_owned']
    for a, b, ia, ib, width in fields:
        for name, rhs, captures in ((a, ia, f_capture), (b, ib, d_capture)):
            assert re.findall(r'\b' + name + r'\s*<=([^;]+);', source) == ['0', rhs], name
            lines.append('reg ' + width + ' ' + name + ';'); resets.append(name + '<=0;')
            captures.append(name + '<=' + rhs + ';'); observed.append(name)
    lines += ['reg envelope_owned;', 'always @(posedge clk)begin', 'if(rst)begin ' + ''.join(resets) + 'end',
        'else begin', 'if(' + descriptor + ')begin ' + ''.join(d_capture) + 'end', 'if(retire)envelope_owned<=0;',
        'if(' + freeze + ')begin ' + ''.join(f_capture) + 'end', 'end', 'end']
    if label == 'gold': comparison = re.search(r'^wire envelope_saved_match=[^;]+;', source, re.M)[0]
    else:
        start = source.index('reg envelope_scope_matches;'); end = source.index('\nend', start) + len('\nend')
        comparison = source[start:end] + '\n' + re.search(r'^wire envelope_saved_match=[^;]+;', source, re.M)[0]
        assert len(re.findall(r'\benvelope_scope_matches\s*<=', source)) == 4
    lines += [comparison, 'assign scope_value=envelope_saved_match;', 'assign observed_scope={' + ','.join(observed) + '};', 'endmodule']
    return '\n'.join(lines) + '\n', public


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--name'); parser.add_argument('--execute', action='store_true'); args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]; sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name)
        approved = Path.home() / 'development/hardware/parser'; assert approved.is_dir() and root != approved
        target = approved / 'build/envelope-scope-equivalence' / args.name; target.mkdir(parents=True, exist_ok=False)
        paths = {'rtl/gold_input.v': root / 'build/experiments/context-commit-guard/rtl/rpc_grpc_http2_return.v',
                 'rtl/gate_input.v': root / 'build/experiments/registered-envelope-scope/rtl/rpc_grpc_http2_return.v',
                 'scripts/run_envelope_scope_equivalence.py': Path(__file__)}; inputs = {}
        for n, p in paths.items():
            q = target / n; q.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, q); inputs[n] = sha(q)
        (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        print('Frozen actual envelope scope: ' + str(target), flush=True)
        result = subprocess.run([sys.executable, str(target / 'scripts/run_envelope_scope_equivalence.py'), '--execute'], check=False)
        assert all(sha(target / n) == h for n, h in inputs.items())
        archive = root / 'build/wsl-reports' / ('envelope_scope_equivalence_' + args.name); archive.mkdir(parents=True, exist_ok=False)
        for n in inputs:
            q = archive / 'execution-sources' / n; q.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target / n, q)
        shutil.copy2(target / 'inputs.json', archive / 'inputs.json')
        for n in ('report.json', 'gold.v', 'gate.v', 'miter.v', 'proof.ys', 'yosys.log', 'counterexample.vcd'):
            if (target / 'build/proof' / n).is_file(): shutil.copy2(target / 'build/proof' / n, archive / n)
        (archive / 'snapshot.json').write_text(json.dumps(dict(exit_code=result.returncode, finished_utc=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
        print('Archived envelope scope: ' + str(archive), flush=True); raise SystemExit(result.returncode)
    assert root.parent == Path.home() / 'development/hardware/parser/build/envelope-scope-equivalence'
    inputs = json.loads((root / 'inputs.json').read_text()); assert all(sha(root / n) == h for n, h in inputs.items())
    folder = root / 'build/proof'; folder.mkdir(parents=True, exist_ok=True)
    report = dict(phase='running', input_sha256=inputs, started_utc=datetime.now(timezone.utc).isoformat(),
        only_environment_assumption='reset on initial sampled clock; later captures, retire and scope fields unconstrained',
        proof_scope='actual projected descriptor/freeze capture assignments, ownership and saved-scope comparison',
        whole_module_equivalence_verified=False, full_system_complete=False)
    try:
        ports = []
        for label in ('gold', 'gate'):
            text, public = model((root / 'rtl' / (label + '_input.v')).read_text(), label)
            (folder / (label + '.v')).write_text(text); ports.append(public)
        assert ports[0] == ports[1]; public = ports[0]
        lines = ['module envelope_equivalence #(parameter USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
            ',\n'.join('input wire ' + w + ' ' + n for w, n in public), ');',
            'wire gold_value,gate_value;wire [2*(USER_WIDTH+31+7*MEMORY_ADDR_WIDTH+3):0] gold_observed,gate_observed;']
        for label in ('gold', 'gate'):
            lines.append('envelope_scope_' + label + ' #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) ' + label + '(' +
                ','.join('.' + n + '(' + n + ')' for _, n in public) + ',.scope_value(' + label + '_value),.observed_scope(' + label + '_observed));')
        lines += ['reg initialized=0;always @(posedge clk)begin initialized<=1;', 'if(!initialized)assume(rst);',
            'if(initialized)begin assert(gold_value==gate_value);assert(gold_observed==gate_observed);end', 'end', 'endmodule']
        (folder / 'miter.v').write_text('\n'.join(lines) + '\n')
        (folder / 'proof.ys').write_text('read_verilog -formal gold.v gate.v miter.v\nprep -top envelope_equivalence -flatten\nsat -seq 1 -tempinduct -maxsteps 8 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n')
        with (folder / 'yosys.log').open('w') as output:
            result = subprocess.run(['yosys', '-T', '-s', 'proof.ys'], cwd=folder, stdout=output, stderr=subprocess.STDOUT, check=False)
        report['yosys_exit_code'] = result.returncode
        assert result.returncode == 0 and 'Induction step proven: SUCCESS!' in (folder / 'yosys.log').read_text()
        assert all(sha(root / n) == h for n, h in inputs.items())
        report.update(phase='passed', unbounded_post_reset_saved_scope_equivalence=True, simultaneous_captures_and_retirement_unconstrained=True)
    except BaseException as error: report.update(phase='failed', error=str(error)); raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['generated_sha256'] = {n: sha(folder / n) for n in ('gold.v', 'gate.v', 'miter.v', 'proof.ys', 'yosys.log') if (folder / n).is_file()}
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
