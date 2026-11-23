"""Compare all actual controller/slot outputs, with pipeline invariants."""
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
from generate_receive_payload_pipeline import MODULE, NAME, edits
from run_frame_fifo_equivalence_wsl import observe
from run_rpc_refusal_default_open_formal_wsl import binding, parameters


def proof_sources(old, new, slot):
    interface = ports(old, MODULE)
    assert interface == ports(new, MODULE)
    body = old[old.index(');')+2:]
    signals = [(m[1] or '', n) for m in re.finditer(
        r'\breg\s*(\[[^\]]+\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;',body)
        for n in m[2].replace(' ','').split(',')]
    assert len(signals) >= 50 and len({n for w,n in signals}) == len(signals)
    # Observe every bank of the one production register array as well.
    extra = '\n'.join(f'wire [63:0] observed_end{i}=ends[{i}];' for i in range(4))+'\n'
    signals += [('[63:0]',f'observed_end{i}') for i in range(4)]
    sources = {}
    for label, text in (('reference',old),('candidate',new)):
        text = text.replace('endmodule',extra+'endmodule')
        observed = observe(text,MODULE,signals)
        if label == 'reference':
            observed = observed.replace('module '+MODULE+' #(','module '+MODULE+'_reference #(')
        else:
            observed = observe(observed,MODULE,[('[63:0]',n) for n in
                ('rpc_payload_index','rpc_payload_product','expected_rpc_payload')])
        sources[label+'.v'] = observed
    outputs = [(w,n) for d,w,n in interface if d == 'output']
    lines = ['`default_nettype none','module proof_top #('+parameters(old,MODULE)+')(',
        ',\n'.join('input wire '+w+' '+n for d,w,n in interface if d == 'input'),');',
        'reg past_valid=0;always @(posedge clk)past_valid<=1;',
        'always @*if(!past_valid)assume(rst);']
    for prefix,module in (('old',MODULE+'_reference'),('new',MODULE)):
        lines += ['wire '+w+' '+prefix+'_'+n+';' for w,n in outputs]
        lines += ['wire '+w+' '+prefix+'_internal_'+n+';' for w,n in signals]
        if prefix == 'new':
            lines += ['wire [63:0] pipe_index,pipe_product,pipe_expected;']
        mapping = ['.'+n+'('+(n if d == 'input' else prefix+'_'+n)+')' for d,w,n in interface]
        mapping += ['.formal_'+n+'('+prefix+'_internal_'+n+')' for w,n in signals]
        if prefix == 'new':
            mapping += [f'.formal_{n}({v})' for n,v in (
                ('rpc_payload_index','pipe_index'),('rpc_payload_product','pipe_product'),('expected_rpc_payload','pipe_expected'))]
        lines += [module+' '+binding(old,MODULE)+' '+prefix+'_dut('+','.join(mapping)+');']
    lines += [
        "wire [63:0] reference_index=({1'b0,new_internal_rpc_address}-{1'b0,new_internal_rpcs})>>7;",
        "wire [63:0] reference_product=reference_index*{1'b0,new_internal_payload_slot_bytes};",
        "wire [63:0] reference_expected={1'b0,new_internal_payloads}+reference_product;",
        'always @*if(past_valid)begin']
    lines += ['assert(old_'+n+'==new_'+n+');' for w,n in outputs]
    lines += ['assert(old_internal_'+n+'==new_internal_'+n+');' for w,n in signals]
    lines += [
        # All are proved assertions, never assumptions about pipeline settling.
        'if(new_internal_state!=0&&new_internal_state!=1)assert(pipe_index==reference_index);',
        'if(new_internal_state!=0&&new_internal_state!=1&&new_internal_state!=2)assert(pipe_product==reference_product);',
        'if(new_internal_state==4||new_internal_state==7)assert(pipe_expected==reference_expected);',
        'end','endmodule','`default_nettype wire','']
    sources['miter.sv'] = '\n'.join(lines)
    sources['memory_command_slot.v'] = slot
    return sources, signals, outputs


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    ap = argparse.ArgumentParser()
    ap.add_argument('--name',required=True)
    args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root = Path(__file__).resolve().parents[1]
    sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p:json.loads(p.read_text())
    candidate = root/'build/experiments'/NAME
    parent = root/'build/experiments/rpc-registered-frame-select-v1'
    generation = read(candidate/'generation.json')
    assert generation['parent_generation_sha256'] == sha(parent/'generation.json')
    for folder in (candidate,parent):
        assert all(sha(folder/n) == h for n,h in read(folder/'generation.json')['outputs_sha256'].items())
    name = 'joint/rtl/'+MODULE+'.v'
    old = (parent/name).read_text()
    new = (candidate/name).read_text()
    expected = old
    for before,after in edits():
        assert expected.count(before) == 1
        expected = expected.replace(before,after)
    assert expected == new
    slot = parent/'joint/rtl/memory_command_slot.v'
    assert slot.read_bytes() == (candidate/'joint/rtl/memory_command_slot.v').read_bytes()
    sources, signals, outputs = proof_sources(old,new,slot.read_text())
    folder = Path.home()/'development/hardware/parser/build/receive-payload-formal'/args.name
    archive = root/'build/wsl-reports'/args.name
    assert not archive.exists()
    folder.mkdir(parents=True,exist_ok=False)
    for name,text in sources.items():
        (folder/name).write_text(text)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    shutil.copy2(candidate/'generation.json',folder/'generation.json')
    (folder/'reference-original.v').write_bytes((parent/('joint/rtl/'+MODULE+'.v')).read_bytes())
    (folder/'candidate-original.v').write_bytes((candidate/('joint/rtl/'+MODULE+'.v')).read_bytes())
    report = dict(phase='proving',started_utc=datetime.now(timezone.utc).isoformat(),passed=False,
        candidate_generation_sha256=sha(candidate/'generation.json'),
        parent_generation_sha256=sha(parent/'generation.json'),
        compared_common_registers=[n for w,n in signals],all_public_outputs=[n for w,n in outputs],
        actual_memory_command_slot_retained=True,initial_reset_required=True,
        later_resets_and_inputs_arbitrary=True,pipeline_settling_assumed=False,
        source_inputs_and_memory_responses_unconstrained=True,native_timing_verified=False,full_system_complete=False)
    inputs = {p.name:sha(p) for p in folder.iterdir() if p.is_file()}
    report['inputs_sha256'] = inputs
    try:
        for label,induct in (('reset-base',False),('induction',True)):
            script = '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
hierarchy -top proof_top -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1
prep -top proof_top -flatten
memory_map
opt
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 180'''
            if induct:
                script += ' -tempinduct -maxsteps 10'
            (folder/(label+'.ys')).write_text(script+'\n')
            with (folder/(label+'-stdout.log')).open('w') as stream:
                code = subprocess.call(['yosys','-Q','-T','-l',label+'.log','-s',label+'.ys'],cwd=folder,stdout=stream,stderr=subprocess.STDOUT)
            text = (folder/(label+'.log')).read_text()
            assert code == 0 and not re.search(r'^ERROR:',text,re.M),(label,code)
            assert ('Induction step proven: SUCCESS!' if induct else 'SAT proof finished - no model found: SUCCESS!') in text
            print(json.dumps(dict(lemma=label,passed=True)),flush=True)
        assert all(sha(folder/n) == h for n,h in inputs.items())
        report.update(phase='receive_payload_pipeline_full_controller_equivalence_proven',passed=True)
    except BaseException as error:
        report.update(phase='failed',error=str(error))
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['artifacts_sha256'] = {p.name:sha(p) for p in folder.iterdir() if p.is_file()}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        shutil.copytree(folder,archive)
    print(json.dumps(dict(phase=report['phase'],passed=report['passed'])))


if __name__ == '__main__':
    main()
