"""Independently audit the status predicate and full production-subtree proof."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from generate_rpc_success_predicate import edits
from run_frame_fifo_equivalence_wsl import observe
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=read(root/'build/validation/rpc-completion-flags-corpus.json')
    native=read(root/'build/validation/rpc-completion-flags-parser-native.json')
    assert parent['key']=='5e0925fc997e1e08' and native['key']=='57c84d760ff80e9f' and native['setup_slack_ns']==-1.073
    source=root/'build/experiments/rpc-success-predicate-v2';generation=read(source/'generation.json')
    assert generation['parent_corpus_audit_key']==parent['key'] and generation['parent_native_audit_key']==native['key']
    assert sha(source/'generate_rpc_success_predicate.py')==generation['generator_sha256']
    parser={n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}
    assert len(parser)==77 and parser=={Path(n).stem:h for n,h in generation['outputs_sha256'].items()}
    assert {n for n,h in parser.items() if h!=parent['executed_parser_sha256'][n]}==set(edits())
    originals={}
    for n,replacements in edits().items():
        old=root/'build/experiments/rpc-completion-flags/rtl'/(n+'.v')
        assert sha(old)==parent['executed_parser_sha256'][n]
        originals[n]=old.read_text();expected=originals[n];certificate=generation['source_edit_certificates'][n]
        assert [(e['old'],e['new']) for e in certificate['edits']]==replacements
        for e in certificate['edits']:
            assert expected.count(e['old'])==e['count']
            expected=expected.replace(e['old'],e['new'])
        assert (source/'rtl'/(n+'.v')).read_bytes()==expected.replace('\n',certificate['original_newline']).encode()
    module='rpc_http2_response_partition'
    old=originals[module];new=(source/'rtl'/(module+'.v')).read_text()
    interface=ports(new,module);original_interface=ports(old,module)
    assert len([p for p in original_interface if p[0]=='output'])==72
    assert [p for p in interface if p[2]!='result_successful']==original_interface
    assert ports((source/'rtl/rpc_grpc_http2_parser_response.v').read_text(),'rpc_grpc_http2_parser_response')==ports(originals['rpc_grpc_http2_parser_response'],'rpc_grpc_http2_parser_response')
    folder=root/'build/wsl-reports'/args.name;report=read(folder/'report.json')
    assert report['passed'] and report['phase']=='rpc_success_predicate_full_subtree_equivalence_verified'
    assert report['generation_sha256']==sha(source/'generation.json')
    for n,h in report['inputs_sha256'].items():assert sha(folder/n)==h,n
    assert sha(folder/'reference-original.v')==parent['executed_parser_sha256'][module]
    assert sha(folder/'candidate-original.v')==parser[module]
    assert sha(folder/'memory-command-slot-original.v')==parser['memory_command_slot']
    symbols=[(m[1] or '',n) for m in re.finditer(r'\breg\s*(\[[^\]]+\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;',old[old.index(');')+2:])
        for n in m[2].replace(' ','').split(',')]
    symbols += [('[71:0]','slot_data'),('[7:0]','slot_status'),('[1:0]','metadata_state'),('','status_zero')]
    assert report['compared_internal_registers_and_memory_state']==[n for w,n in symbols]
    reference=old.replace('output wire result_valid,input wire result_ready,','output wire result_valid,output wire result_successful,input wire result_ready,')
    reference=reference.replace('endmodule','wire status_zero=result_status==0;\nassign result_successful=result_valid&&status_zero;\nendmodule')
    def observed(text):
        marker='memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) metadata('
        assert text.count(marker)==text.count('.idle(slot_idle));')==1
        text=text.replace(marker,'wire [1:0] metadata_state;\n'+marker).replace('.idle(slot_idle));','.idle(slot_idle),.formal_state(metadata_state));')
        return observe(text,module,symbols)
    assert (folder/'reference.v').read_text()==observed(reference).replace('module '+module+' #(','module '+module+'_reference #(')
    assert (folder/'candidate.v').read_text()==observed(new)
    slot=(source/'rtl/memory_command_slot.v').read_text()
    assert (folder/'memory_command_slot.v').read_text()==observe(slot,'memory_command_slot',[('[1:0]','state')])
    miter=(folder/'miter.sv').read_text();outputs=[n for d,w,n in interface if d=='output']
    assert outputs==report['all_outputs_compared'] and len(outputs)==73 and report['original_outputs_compared']==72
    assert miter.count('assume(')==1 and 'always @*if(!past_valid)assume(rst);' in miter
    assert re.findall(r'assert\(([^;]+)\);',miter)==[f'old_{n}==new_{n}' for n in outputs]+[
        f'old_internal_{n}==new_internal_{n}' for w,n in symbols]+['new_result_successful==(new_result_valid&&new_result_status==0)']
    assert 'always @*if(past_valid)begin' in miter
    for d,w,n in interface:
        if d=='input':assert miter.count(f'.{n}({n})')==2
        else:assert miter.count(f'.{n}(old_{n})')==miter.count(f'.{n}(new_{n})')==1
    for w,n in symbols:assert miter.count(f'.formal_{n}(old_internal_{n})')==miter.count(f'.formal_{n}(new_internal_{n})')==1
    base=(folder/'reset-base.ys').read_text();structural=(folder/'structural.ys').read_text()
    assert base=='''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
prep -top success_predicate_miter -flatten
memory_map
opt
sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -timeout 90
'''
    assert structural=='''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v
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
    base_log=(folder/'reset-base.log').read_text();proof_log=(folder/'structural.log').read_text()
    assert sha(folder/'reset-base.log')==report['reset_base_log_sha256'] and sha(folder/'structural.log')==report['structural_log_sha256']
    assert 'SAT proof finished - no model found: SUCCESS!' in base_log and 'Equivalence successfully proven!' in proof_log
    assert not re.search(r'^ERROR:',base_log+proof_log,re.M)
    assert sha(folder/'equivalence-netlist.json')==report['equivalence_netlist_sha256']
    cells=[c for c in read(folder/'equivalence-netlist.json')['modules']['success_predicate_equivalence']['cells'].values() if c['type']=='$equiv']
    assert len(cells)>4000 and all(c['connections']['A']==c['connections']['B'] for c in cells)
    assert f'Of those cells {len(cells)} are proven and 0 are unproven.' in proof_log
    result=dict(phase='rpc_success_predicate_source_and_equivalence_verified',verified_utc=datetime.now(timezone.utc).isoformat(),run=args.name,
        parent_corpus_audit_key=parent['key'],parent_native_audit_key=native['key'],exact_parser_modules=77,
        executed_parser_sha256=parser,generation_sha256=sha(source/'generation.json'),source_edit_replay_verified=True,
        full_production_response_subtree_induction_verified=True,actual_initial_reset_base_verified=True,
        original_output_ports_compared=72,all_output_ports_compared=73,proven_equivalence_cells=len(cells),
        internal_observations=len(symbols),predicate_equivalence_verified=True,actual_memory_slot_included=True,
        parent_predicate_substitution_exact=True,public_application_ports_unchanged=True,
        arbitrary_later_resets_and_inputs=True,input_stability_assumptions=False,two_state_formal=True,
        fresh_full_application_corpus_verified=False,full_protocol_matrix_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p) for p in folder.iterdir() if p.is_file()},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-success-predicate-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in (evidence/'audit.json',root/'build/validation/rpc-success-predicate.json'):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','proven_equivalence_cells')}))


if __name__=='__main__':main()
