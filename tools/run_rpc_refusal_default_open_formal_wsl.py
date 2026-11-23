"""Source-bound default-open V6/V7 bridge; no proof of refused-traffic behavior.

Transport and keyed-store child outputs are independently unconstrained. This
overapproximation proves only the local no-discard invariants. The complete
receive controller is then compared, including every internal register.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parameters(source, module):
    start=source.index('module '+module)+len('module '+module)
    opening=source.index('#(',start)+1
    depth=0
    for i in range(opening,len(source)):
        depth+=(source[i]=='(')-(source[i]==')')
        if depth==0:
            return source[opening+1:i]
    raise AssertionError('Unbalanced parameter declaration')


def binding(source,module):
    return '#('+','.join('.'+n+'('+n+')' for n in re.findall(r'\b(\w+)\s*=',parameters(source,module)))+')'


def wrapper(source,module,signals,bound,claims,old=None):
    interface=ports(source,module)
    inputs=[(d,w,n)for d,w,n in interface if d=='input' and n not in bound]
    outputs=[(w,n)for d,w,n in interface if d=='output']
    lines=['`default_nettype none','module proof_top #('+parameters(source,module)+')(',
        ',\n'.join('input wire '+w+' '+n for d,w,n in inputs),');',
        'reg past_valid=0;always @(posedge clk)past_valid<=1;',
        'always @*if(!past_valid)assume(rst);']
    versions=[('new',module)] if old is None else [('old',module+'_reference'),('new',module)]
    for prefix,name in versions:
        lines += ['wire '+w+' '+prefix+'_'+n+';'for w,n in outputs]
        lines += ['wire '+w+' '+prefix+'_internal_'+n+';'for w,n in signals]
        mapping=['.'+n+'('+(bound.get(n,n) if d=='input' else prefix+'_'+n)+')'for d,w,n in interface]
        mapping+=['.formal_'+n+'('+prefix+'_internal_'+n+')'for w,n in signals]
        lines += [name+' '+binding(source,module)+' '+prefix+'_dut('+','.join(mapping)+');']
    lines+=['always @*if(past_valid)begin']
    if old is not None:
        lines+=['assert(old_'+n+'==new_'+n+');'for w,n in outputs]
        lines+=['assert(old_internal_'+n+'==new_internal_'+n+');'for w,n in signals]
    lines += ['assert('+claim+');'for claim in claims]+['end','endmodule','`default_nettype wire','']
    return '\n'.join(lines),interface


def generate(old_folder,new_folder,folder):
    records={}
    configurations={
        'transport':('http2_classified_parser_transport',[('','refusal_at_begin'),('','refusal_seen')],
            {'admit_new_rpcs':"1'b1"},['!new_refusal_history','!new_internal_refusal_at_begin','!new_internal_refusal_seen']),
        'keyed':('http2_keyed_receive_credit_store',[('','held_allow_discard'),('','discarded_binding'),('[3:0]','state')],
            {'allow_closed_discard':"1'b0"},['!new_rsp_discarded','!new_internal_held_allow_discard',
                '!new_internal_discarded_binding','new_internal_state<10']),
    }
    for label,(module,signals,bound,claims)in configurations.items():
        slot=folder/label;slot.mkdir()
        path=new_folder/(module+'.v');source=path.read_text()
        assert path.read_bytes()==(old_folder/path.name).read_bytes()
        child_names=sorted(set(re.findall(r'(?m)^\s*(\w+)\s*#\s*\(',source)))
        assert len(child_names)==(4 if label=='transport'else 2)
        stubs=[];children={}
        for child in child_names:
            child_path=new_folder/(child+'.v');raw=child_path.read_text()
            header=raw[raw.index('module '+child):raw.index(');')+2]
            stub='(* blackbox *) '+header+'\nendmodule\n'
            stubs.append(stub)
            children[child]={'source_sha256':sha(child_path),'header_sha256':hashlib.sha256(header.encode()).hexdigest()}
            (slot/(child+'-original.v')).write_bytes(child_path.read_bytes())
        observed=observe(source,module,signals)
        top,interface=wrapper(source,module,signals,bound,claims)
        (slot/'original.v').write_bytes(path.read_bytes())
        (slot/'observed.v').write_text(observed)
        (slot/'children.v').write_text('\n'.join(stubs))
        (slot/'miter.sv').write_text(top)
        params=' -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1'if label=='keyed'else''
        (slot/'prepare.ys').write_text('read_verilog -formal -sv children.v observed.v miter.sv\n'+
            'hierarchy -top proof_top'+params+'\nproc\nflatten\nopt_clean\nwrite_json uncut.json\n')
        records[label]=dict(module=module,signals=signals,bound_inputs=bound,claims=claims,children=children,
            original_sha256=sha(path),interface=interface)
    module='http2_receive_flow_controller';slot=folder/'controller';slot.mkdir()
    old=(old_folder/(module+'.v')).read_text();new=(new_folder/(module+'.v')).read_text()
    a='state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:REPLAY_RESULT;'
    b='state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:(operation==DROP_RELEASE||operation==DROP_UPDATE)?DROP_END_ACK:REPLAY_RESULT;'
    assert old.count(a)==1 and old.replace(a,b)==new
    body=old[old.index(');')+2:]
    signals=[(m[1]or'',n)for m in re.finditer(r'\breg\s*(\[[^\]]+\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;',body)
        for n in m[2].replace(' ','').split(',')]
    assert len(signals)==16 and len({n for w,n in signals})==len(signals)
    assert ports(old,module)==ports(new,module)
    claims=[p+c for p in ('old_internal_','new_internal_')for c in ('discard_active==0','operation<=5','state<=5')]
    top,interface=wrapper(new,module,signals,{'result_discarded':"1'b0"},claims,old=old)
    for name,text in [('reference-original.v',old),('candidate-original.v',new),
        ('reference.v',observe(old,module,signals).replace('module '+module+' #(','module '+module+'_reference #(')),
        ('candidate.v',observe(new,module,signals)),('miter.sv',top)]:
        (slot/name).write_text(text)
    records['controller']=dict(module=module,signals=signals,bound_inputs={'result_discarded':"1'b0"},
        claims=claims,interface=interface,reference_sha256=sha(old_folder/(module+'.v')),candidate_sha256=sha(new_folder/(module+'.v')))
    return records


def cut_children(uncut,children):
    result=json.loads(json.dumps(uncut));top=result['modules']['proof_top'];cuts=[]
    assert set(result['modules'])=={'proof_top',*children}
    for name,cell in list(top['cells'].items()):
        if cell['type']not in children:
            assert cell['type'].startswith('$'),cell['type']
            continue
        outputs={n:b for n,b in cell['connections'].items()if cell['port_directions'][n]=='output'}
        assert outputs and not any(d=='inout'for d in cell['port_directions'].values())
        cuts.append(dict(cell_name=name,original_cell=cell,unconstrained_outputs=outputs))
        del top['cells'][name]
        for port,bits in outputs.items():
            if not bits:continue
            assert all(isinstance(bit,int)for bit in bits)
            new_name=name+'$arbitrary_output$'+port;assert new_name not in top['cells']
            top['cells'][new_name]=dict(hide_name=1,type='$anyseq',parameters={'WIDTH':format(len(bits),'032b')},
                attributes={},port_directions={'Y':'output'},connections={'Y':bits})
    assert {c['original_cell']['type']for c in cuts}==set(children)
    result['modules']={'proof_top':top}
    return result,cuts


def proof_script(label,induct):
    load='read_json cut.json\n'if label!='controller'else(
        'read_verilog -formal -sv reference.v candidate.v miter.sv\n'+
        'hierarchy -top proof_top -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1\n')
    mode=' -tempinduct -maxsteps 10'if induct else''
    return load+'prep -top proof_top -flatten\nmemory_map\nopt\n'+(
        'sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -set-def-formal -timeout 90'+mode+'\n')


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1]
    parent=root/'build/experiments/rpc-stream-refusal-v6';candidate=root/'build/experiments/rpc-stream-refusal-v7'
    for base in (parent,candidate):
        generation=json.loads((base/'generation.json').read_text())
        assert all(sha(base/n)==h for n,h in generation['outputs_sha256'].items())
    folder=Path.home()/'development/hardware/parser/build/rpc-refusal-formal'/args.name
    archive=root/'build/wsl-reports'/args.name;assert not archive.exists();folder.mkdir(parents=True,exist_ok=False)
    records=generate(parent/'joint/rtl',candidate/'joint/rtl',folder)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    inputs={p.relative_to(folder).as_posix():sha(p)for p in folder.rglob('*')if p.is_file()}
    report=dict(phase='proving',started_utc=datetime.now(timezone.utc).isoformat(),passed=False,
        parent_generation_sha256=sha(parent/'generation.json'),candidate_generation_sha256=sha(candidate/'generation.json'),
        inputs_sha256=inputs,lemmas=records,initial_reset_required=True,later_inputs_and_resets_arbitrary=True,
        input_stability_assumptions=False,production_register_initial_values_forced=False,
        scope='default-open conditional equivalence only; not refused-traffic correctness or retained reset authority',
        full_system_complete=False)
    def run(slot,name):
        with(slot/(name+'-stdout.log')).open('w')as stream:
            code=subprocess.call(['yosys','-Q','-T','-l',name+'.log','-s',name+'.ys'],cwd=slot,stdout=stream,stderr=subprocess.STDOUT)
        log=(slot/(name+'.log')).read_text();assert code==0 and not re.search(r'^ERROR:',log,re.M),(slot.name,name,code)
        return log
    try:
        for label in ('transport','keyed','controller'):
            slot=folder/label
            if label!='controller':
                run(slot,'prepare')
                cut,certificate=cut_children(json.loads((slot/'uncut.json').read_text()),records[label]['children'])
                (slot/'cut.json').write_text(json.dumps(cut,separators=(',',':'))+'\n')
                (slot/'cut-certificate.json').write_text(json.dumps(certificate,indent=2)+'\n')
            for name,induct in [('reset-base',False),('induction',True)]:
                (slot/(name+'.ys')).write_text(proof_script(label,induct))
                log=run(slot,name)
                assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log,(label,name)
            print(json.dumps(dict(lemma=label,reset_base=True,unbounded_induction=True)),flush=True)
        assert all(sha(folder/n)==h for n,h in inputs.items())
        report.update(phase='default_open_compositional_equivalence_proven',passed=True)
    except BaseException as error:
        report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        report['artifacts_sha256']={p.relative_to(folder).as_posix():sha(p)for p in folder.rglob('*')if p.is_file()and p.name!='report.json'}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n');shutil.copytree(folder,archive)
    print(json.dumps(dict(phase=report['phase'],passed=report['passed'])))


if __name__=='__main__':main()
