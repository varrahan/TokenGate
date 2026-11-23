"""Prove the full controller using a sound deterministic arithmetic abstraction.

Unchanged products are shared across equal operands in the two controllers.
The retimed product is an arbitrary binary function, with same-argument
consistency within each sample and across adjacent samples. Every concrete
unsigned multiplication satisfies these constraints. No production traffic,
memory, reset, state transition or settling property is assumed.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess

from run_receive_payload_pipeline_formal_wsl import proof_sources


COMMON = (
    ('backed','assign backed_connection_capacity=backed_stream_capacity*rpc_slots;'),
    ('required',"assign required_payload_bytes={1'b0,payload_slot_bytes}*rpc_slots;"),
    ('saved',"assign saved_connection_capacity={32'd0,initial_stream}*rpc_slots;"))


def add_ports(source, declaration):
    i = source.index(');')
    return source[:i]+',\n'+declaration+'\n'+source[i:]


def abstract_sources(old, new, slot):
    sources, signals, outputs = proof_sources(old,new,slot)
    cert = {}
    declarations = ',\n'.join('input wire [63:0] arithmetic_'+n for n in ('backed','required','saved','product'))
    for version in ('reference','candidate'):
        name = version+'.v'
        text = sources[name]
        replacements = []
        for key,statement in COMMON:
            replacement = statement[:statement.index('=')+1]+'arithmetic_'+key+';'
            replacements.append((statement,replacement))
        if version == 'reference':
            replacements.append((
                "assign expected_rpc_payload={1'b0,payloads}+(({1'b0,rpc_address}-{1'b0,rpcs})>>7)*{1'b0,payload_slot_bytes};",
                "assign expected_rpc_payload={1'b0,payloads}+arithmetic_product;"))
        else:
            replacements.append((
                "rpc_payload_product<=rpc_payload_index*{1'b0,payload_slot_bytes};",
                'rpc_payload_product<=arithmetic_product;'))
        original = text
        for before,after in replacements:
            assert text.count(before) == 1
            text = text.replace(before,after)
        inverse = text
        for before,after in reversed(replacements):
            assert inverse.count(after) == 1
            inverse = inverse.replace(after,before)
        assert inverse == original
        sources[name] = add_ports(text,declarations)
        cert[name] = dict(replacements=replacements,added_inputs=declarations,
            original_observed_sha256=hashlib.sha256(original.encode()).hexdigest())
    text = sources['miter.sv']
    text = add_ports(text,',\n'.join('input wire [63:0] '+n for n in (
        'shared_backed','shared_required','shared_saved','old_product','new_product')))
    for prefix in ('old','new'):
        anchor=prefix+'_dut('
        mapping=','.join('.arithmetic_'+n+'(shared_'+n+')' for n in ('backed','required','saved'))
        mapping+=',.arithmetic_product('+prefix+'_product),'
        assert text.count(anchor)==1
        text=text.replace(anchor,anchor+mapping)
    statement="wire [63:0] reference_product=reference_index*{1'b0,new_internal_payload_slot_bytes};"
    assert text.count(statement)==1
    text=text.replace(statement,'wire [63:0] reference_product=old_product;')
    oracle='''
wire [63:0] old_a=({1'b0,old_internal_rpc_address}-{1'b0,old_internal_rpcs})>>7;
wire [63:0] old_b={1'b0,old_internal_payload_slot_bytes};
wire [63:0] new_a=pipe_index,new_b={1'b0,new_internal_payload_slot_bytes};
reg [63:0] old_a_q,old_b_q,new_a_q,new_b_q,old_product_q,new_product_q;
always @(posedge clk)begin
    old_a_q<=old_a;old_b_q<=old_b;new_a_q<=new_a;new_b_q<=new_b;
    old_product_q<=old_product;new_product_q<=new_product;
end
// Only congruence of the abstract arithmetic function is constrained.
// Every concrete multiplication obeys these five equal-argument rules.
always @*begin
    if(old_a==new_a&&old_b==new_b)assume(old_product==new_product);
    if(past_valid)begin
        if(old_a==old_a_q&&old_b==old_b_q)assume(old_product==old_product_q);
        if(old_a==new_a_q&&old_b==new_b_q)assume(old_product==new_product_q);
        if(new_a==old_a_q&&new_b==old_b_q)assume(new_product==old_product_q);
        if(new_a==new_a_q&&new_b==new_b_q)assume(new_product==new_product_q);
    end
end
// Shared products have identical operand expressions over the compared
// captured registers. Check those operands explicitly as proof obligations.
wire [63:0] old_slots={1'b0,old_internal_rpc_bytes}>>7;
wire [63:0] new_slots={1'b0,new_internal_rpc_bytes}>>7;
wire [63:0] old_capacity={1'b0,old_internal_payload_slot_bytes}+64'd5;
wire [63:0] new_capacity={1'b0,new_internal_payload_slot_bytes}+64'd5;
always @*if(past_valid)begin
    assert(old_slots==new_slots);
    assert(old_capacity==new_capacity);
    assert(old_internal_payload_slot_bytes==new_internal_payload_slot_bytes);
    assert(old_internal_connection_record[127:96]==new_internal_connection_record[127:96]);
end
'''
    text=text.replace('endmodule',oracle+'\nendmodule')
    assert text.count('assume(')==6
    sources['miter.sv']=text
    cert['miter.sv']=dict(initial_reset_assumptions=1,arithmetic_congruence_assumptions=5,
        additional_shared_operand_equality_assertions=4,production_input_stability_assumptions=0,
        no_assumed_pipeline_settling=True,actual_memory_command_slot_retained=True)
    return sources,cert,signals,outputs


def proof_script(induct):
    script='''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
hierarchy -top proof_top -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1
prep -top proof_top -flatten
memory_map
opt
write_json prepared.json
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 120'''
    if induct:
        script+=' -tempinduct -maxsteps 10'
    return script+'\n'


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=root/'build/wsl-reports/rpc_receive_payload_pipeline_v1_20261122'
    previous=json.loads((parent/'report.json').read_text())
    assert not previous['passed'] and 'TIMEOUT!' in (parent/'induction.log').read_text()
    assert all(sha(parent/n)==h for n,h in previous['artifacts_sha256'].items())
    old=(parent/'reference-original.v').read_text();new=(parent/'candidate-original.v').read_text()
    slot=(parent/'memory_command_slot.v').read_text()
    sources,certificate,signals,outputs=abstract_sources(old,new,slot)
    name='rpc_receive_payload_pipeline_compositional_v1_20261122'
    folder=Path.home()/'development/hardware/parser/build/receive-payload-formal'/name
    archive=root/'build/wsl-reports'/name;launch=root/'build/validation'/(name+'-launch.json')
    assert not archive.exists()and not launch.exists();folder.mkdir(parents=True,exist_ok=False)
    for filename,text in sources.items():(folder/filename).write_text(text)
    for filename in ('reference-original.v','candidate-original.v','generation.json'):
        shutil.copy2(parent/filename,folder/filename)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    (folder/'arithmetic-certificate.json').write_text(json.dumps(certificate,indent=2)+'\n')
    inputs={p.name:sha(p)for p in folder.iterdir()if p.is_file()}
    report=dict(phase='proving',passed=False,started_utc=datetime.now(timezone.utc).isoformat(),
        candidate_generation_sha256=previous['candidate_generation_sha256'],parent_generation_sha256=previous['parent_generation_sha256'],
        previous_sat_report_sha256=sha(parent/'report.json'),inputs_sha256=inputs,
        all_public_outputs=[n for w,n in outputs],compared_common_registers=[n for w,n in signals],
        arithmetic_abstraction=True,initial_reset_required=True,arbitrary_later_resets_and_production_inputs=True,
        no_assumed_pipeline_settling=True,actual_memory_command_slot_retained=True,
        production_address_width=23,production_context_width=16,capacity_and_stream_format_enabled=True,
        native_timing_verified=False,full_system_complete=False,lemmas={})
    def save():
        raw=json.dumps(report,indent=2)+'\n';(folder/'report.json').write_text(raw);launch.write_text(raw)
    save()
    try:
        for label,induct in (('reset-base',False),('induction',True)):
            (folder/(label+'.ys')).write_text(proof_script(induct))
            with(folder/(label+'.log')).open('w')as log:
                process=subprocess.Popen(['yosys','-Q','-T','-s',label+'.ys'],cwd=folder,stdout=log,stderr=subprocess.STDOUT)
                report.update(active_lemma=label,process_pid=process.pid);save();code=process.wait()
            log=(folder/(label+'.log')).read_text()
            assert code==0,(label,code)
            assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log
            report['lemmas'][label]='passed';save();print(json.dumps(dict(lemma=label,passed=True)),flush=True)
        report.update(phase='receive_payload_pipeline_compositional_equivalence_proven',passed=True)
    except BaseException as error:
        report.update(phase='failed',error=str(error));raise
    finally:
        assert all(sha(folder/n)==h for n,h in inputs.items())
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        report['artifacts_sha256']={p.name:sha(p)for p in folder.iterdir()if p.is_file()and p.name!='report.json'}
        save();shutil.copytree(folder,archive)
    print(json.dumps(dict(phase=report['phase'],passed=report['passed'])))


if __name__=='__main__':main()
