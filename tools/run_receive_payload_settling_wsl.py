"""Prove settling in actual control flow with conservative record-data cuts."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess

from run_receive_payload_pipeline_compositional_wsl import abstract_sources


def leaf_sources(old,new,slot):
    sources,arithmetic,signals,outputs=abstract_sources(old,new,slot)
    text=sources['miter.sv']
    for w,n in outputs:
        statement='assert(old_'+n+'==new_'+n+');\n'
        assert text.count(statement)==1;text=text.replace(statement,'')
    for w,n in signals:
        statement='assert(old_internal_'+n+'==new_internal_'+n+');\n'
        assert statement in text;text=text.replace(statement,'',1)
    for statement in (
        'assert(old_slots==new_slots);',
        'assert(old_capacity==new_capacity);',
        'assert(old_internal_payload_slot_bytes==new_internal_payload_slot_bytes);',
        'assert(old_internal_connection_record[127:96]==new_internal_connection_record[127:96]);'):
        assert text.count(statement)==1;text=text.replace(statement,'')
    # The reference instance is not needed by a reachable-state lemma.
    start=text.index('http2_receive_credit_store_reference #(')
    end=text.index(');',start)+2
    text=text[:start]+text[end:]
    text=text.replace('old_internal_','new_internal_')
    assert text.count('assert(')==3 and text.count('assume(')==6
    sources['miter.sv']=text
    del sources['reference.v']
    return sources,arithmetic


def record_cuts(netlist):
    result=json.loads(json.dumps(netlist));top=result['modules']['proof_top']
    assert set(result['modules'])=={'proof_top'}
    certificate=[]
    for name,width in (('connection_record',512),('rpc_record',256),('stream_record',256)):
        bits=top['netnames']['new_internal_'+name]['bits'];assert len(bits)==width
        wanted={b for b in bits if isinstance(b,int)}
        removed=[];driven=set()
        for key,cell in list(top['cells'].items()):
            outputs=[b for p,values in cell['connections'].items()if cell['port_directions'][p]=='output'for b in values]
            if not wanted.intersection(outputs):continue
            assert cell['type']in('$dff','$dffe','$sdff','$sdffe','$sdffce'),(name,key,cell['type'])
            assert set(outputs)<=wanted,(name,key)
            assert not driven.intersection(outputs);driven.update(outputs)
            removed.append(dict(name=key,cell=cell));del top['cells'][key]
        assert removed,(name,'No actual record flip-flops found')
        # Undriven unused bits may have been optimized out. They are included
        # in the overapproximation too; original constant bits remain constant.
        replacement='record_data_anyseq_'+name
        top['cells'][replacement]=dict(hide_name=1,type='$anyseq',parameters={'WIDTH':format(len(wanted),'032b')},
            attributes={},port_directions={'Y':'output'},connections={'Y':sorted(wanted)})
        certificate.append(dict(record=name,width=width,bits=bits,removed_cells=removed,
            replacement_name=replacement,arbitrary_bits=sorted(wanted),original_constant_bits=[b for b in bits if isinstance(b,str)]))
    return result,certificate


PREPARE='''read_verilog -formal -sv memory_command_slot.v candidate.v miter.sv
hierarchy -top proof_top -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1
prep -top proof_top -flatten
memory_map
opt
write_json uncut.json
'''


def proof_script(induct):
    text='''read_json cut.json
prep -top proof_top -flatten
opt_clean
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -set-def-formal -timeout 90'''
    if induct:text+=' -tempinduct -maxsteps 10'
    return text+'\n'


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=root/'build/wsl-reports/rpc_receive_payload_pipeline_v1_20261122'
    old=(parent/'reference-original.v').read_text();new=(parent/'candidate-original.v').read_text()
    slot=(parent/'memory_command_slot.v').read_text();sources,arithmetic=leaf_sources(old,new,slot)
    name='rpc_receive_payload_settling_v1_20261122'
    folder=Path.home()/'development/hardware/parser/build/receive-payload-formal'/name
    archive=root/'build/wsl-reports'/name;launch=root/'build/validation'/(name+'-launch.json')
    assert not archive.exists()and not launch.exists();folder.mkdir(parents=True,exist_ok=False)
    for n,text in sources.items():(folder/n).write_text(text)
    for n in ('reference-original.v','candidate-original.v','generation.json'):
        shutil.copy2(parent/n,folder/n)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    (folder/'arithmetic-certificate.json').write_text(json.dumps(arithmetic,indent=2)+'\n')
    (folder/'prepare.ys').write_text(PREPARE)
    report=dict(phase='proving',passed=False,started_utc=datetime.now(timezone.utc).isoformat(),
        candidate_generation_sha256=sha(folder/'generation.json'),
        inputs_sha256={p.name:sha(p)for p in folder.iterdir()if p.is_file()},
        scope='Reachable pipeline settling at RPC_CHECK; not a direct all-output comparison',
        real_candidate_control_and_memory_slot_retained=True,metadata_record_values_unconstrained=True,
        arithmetic_congruence_constraints=5,initial_reset_required=True,external_input_stability_assumptions=0,
        production_address_width=23,production_context_width=16,capacity_and_stream_format_enabled=True,
        native_timing_verified=False,full_system_complete=False,lemmas={})
    def save():
        raw=json.dumps(report,indent=2)+'\n';(folder/'report.json').write_text(raw);launch.write_text(raw)
    def run(label):
        with(folder/(label+'.log')).open('w')as output:
            process=subprocess.Popen(['yosys','-Q','-T','-s',label+'.ys'],cwd=folder,stdout=output,stderr=subprocess.STDOUT)
            report.update(active_lemma=label,process_pid=process.pid);save();code=process.wait()
        text=(folder/(label+'.log')).read_text()
        assert code==0 and not re.search(r'^ERROR:',text,re.M),(label,code)
        return text
    save()
    try:
        run('prepare')
        cut,certificate=record_cuts(json.loads((folder/'uncut.json').read_text()))
        (folder/'cut.json').write_text(json.dumps(cut,separators=(',',':'))+'\n')
        (folder/'record-cut-certificate.json').write_text(json.dumps(certificate,indent=2)+'\n')
        for label,induct in (('reset-base',False),('induction',True)):
            (folder/(label+'.ys')).write_text(proof_script(induct));log=run(label)
            assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log
            report['lemmas'][label]='passed';save();print(json.dumps(dict(lemma=label,passed=True)),flush=True)
        report.update(phase='receive_payload_pipeline_settling_proven',passed=True)
    except BaseException as error:
        report.update(phase='failed',error=str(error));raise
    finally:
        assert all(sha(folder/n)==h for n,h in report['inputs_sha256'].items())
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        report['artifacts_sha256']={p.name:sha(p)for p in folder.iterdir()if p.is_file()and p.name!='report.json'}
        save();shutil.copytree(folder,archive)
    print(json.dumps(dict(phase=report['phase'],passed=report['passed'])))


if __name__=='__main__':main()
