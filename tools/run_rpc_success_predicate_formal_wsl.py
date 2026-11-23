"""Full production subtree induction and actual-reset base for status_zero."""
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


def proof_sources(old, new, slot):
    module='rpc_http2_response_partition'
    marker='output wire result_valid,input wire result_ready,'
    replacement='output wire result_valid,output wire result_successful,input wire result_ready,'
    assert old.count(marker)==1
    reference=old.replace(marker,replacement)
    extra='wire status_zero=result_status==0;\nassign result_successful=result_valid&&status_zero;\n'
    reference=reference.replace('endmodule',extra+'endmodule')
    assert reference.replace(extra,'').replace(replacement,marker)==old
    interface=ports(reference,module);assert interface==ports(new,module)
    body=old[old.index(');')+2:]
    symbols=[(m[1] or '',n) for m in re.finditer(r'\breg\s*(\[[^\]]+\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;',body)
        for n in m[2].replace(' ','').split(',')]
    assert len(symbols)>=42 and len({n for w,n in symbols})==len(symbols)
    symbols += [('[71:0]','slot_data'),('[7:0]','slot_status'),('[1:0]','metadata_state'),('','status_zero')]
    def memory_observation(text):
        before='memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) metadata('
        ending='.idle(slot_idle));'
        assert text.count(before)==text.count(ending)==1
        return text.replace(before,'wire [1:0] metadata_state;\n'+before).replace(ending,'.idle(slot_idle),.formal_state(metadata_state));')
    reference=observe(memory_observation(reference),module,symbols).replace('module '+module+' #(','module '+module+'_reference #(')
    candidate=observe(memory_observation(new),module,symbols)
    memory=observe(slot,'memory_command_slot',[('[1:0]','state')])
    outputs=[(w,n) for d,w,n in interface if d=='output']
    lines=['`default_nettype none','module success_predicate_miter #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384)(',
        ',\n'.join(f'input wire {w} {n}' for d,w,n in interface if d=='input'),');',
        'reg past_valid=0;always @(posedge clk)past_valid<=1;', 'always @*if(!past_valid)assume(rst);']
    lines += [f'wire {w} old_{n},new_{n};' for w,n in outputs]
    lines += [f'wire {w} old_internal_{n},new_internal_{n};' for w,n in symbols]
    for prefix,name in [('old',module+'_reference'),('new',module)]:
        mapping=[f'.{n}({n if d=="input" else prefix+"_"+n})' for d,w,n in interface]
        mapping += [f'.formal_{n}({prefix}_internal_{n})' for w,n in symbols]
        lines += [name+' #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) '+prefix+'_dut(', ',\n'.join(mapping),');']
    lines += ['always @*if(past_valid)begin']
    lines += [f'assert(old_{n}==new_{n});' for w,n in outputs]
    lines += [f'assert(old_internal_{n}==new_internal_{n});' for w,n in symbols]
    lines += ['assert(new_result_successful==(new_result_valid&&new_result_status==0));','end','endmodule','`default_nettype wire','']
    return reference,candidate,memory,'\n'.join(lines),interface,symbols


BASE='''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
prep -top success_predicate_miter -flatten
memory_map
opt
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 90
'''
STRUCTURAL='''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v
hierarchy -check
proc
memory_map
flatten rpc_http2_response_partition_reference rpc_http2_response_partition
opt_clean
equiv_make rpc_http2_response_partition_reference rpc_http2_response_partition success_predicate_equivalence
hierarchy -top success_predicate_equivalence
opt_clean
equiv_simple -seq 1
equiv_induct -seq 1
equiv_status -assert
write_json equivalence-netlist.json
'''


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'build/experiments/rpc-success-predicate-v2';generation=json.loads((source/'generation.json').read_text())
    assert all(sha(source/n)==h for n,h in generation['outputs_sha256'].items())
    deps=closure('rpc_http2_response_partition',source);assert len(deps)==2
    parent=root/'build/experiments/rpc-completion-flags/rtl/rpc_http2_response_partition.v'
    old=parent.read_text();new=deps['rpc_http2_response_partition'].read_text();slot=deps['memory_command_slot'].read_text()
    ref,actual,memory,miter,interface,symbols=proof_sources(old,new,slot)
    folder=Path('/home/varrahan/development/hardware/parser/build/rpc-success-predicate-formal')/args.name
    archive=root/'build/wsl-reports'/args.name;assert not archive.exists();folder.mkdir(parents=True,exist_ok=False)
    for name,raw in [('reference-original.v',parent.read_bytes()),('candidate-original.v',deps['rpc_http2_response_partition'].read_bytes()),
        ('memory-command-slot-original.v',deps['memory_command_slot'].read_bytes())]:
        (folder/name).write_bytes(raw)
    for name,text in [('reference.v',ref),('candidate.v',actual),('memory_command_slot.v',memory),('miter.sv',miter),('reset-base.ys',BASE),('structural.ys',STRUCTURAL)]:
        (folder/name).write_text(text)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    inputs={p.name:sha(p) for p in folder.iterdir() if p.is_file()}
    report=dict(phase='proving',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        generation_sha256=sha(source/'generation.json'),original_outputs_compared=72,all_outputs_compared=[n for d,w,n in interface if d=='output'],
        compared_internal_registers_and_memory_state=[n for w,n in symbols],actual_production_subtree_modules=2,
        initial_reset_required=True,later_inputs_and_resets_arbitrary=True,input_stability_assumptions=False,
        observation_only_source_extensions=True,passed=False,native_timing_verified=False,full_system_complete=False)
    try:
        for label in ('reset-base','structural'):
            with (folder/(label+'-stdout.log')).open('w') as stream:
                code=subprocess.call(['yosys','-Q','-T','-l',label+'.log','-s',label+'.ys'],cwd=folder,stdout=stream,stderr=subprocess.STDOUT)
            log=(folder/(label+'.log')).read_text();assert code==0 and not re.search(r'^ERROR:',log,re.M),(label,code)
            assert ('SAT proof finished - no model found: SUCCESS!' if label=='reset-base' else 'Equivalence successfully proven!') in log
        assert all(sha(folder/n)==h for n,h in inputs.items())
        report.update(phase='rpc_success_predicate_full_subtree_equivalence_verified',passed=True,
            reset_base_log_sha256=sha(folder/'reset-base.log'),structural_log_sha256=sha(folder/'structural.log'),
            equivalence_netlist_sha256=sha(folder/'equivalence-netlist.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n');shutil.copytree(folder,archive)
    print(json.dumps(dict(phase=report['phase'],passed=report['passed'])))


if __name__=='__main__':main()
