"""Bind original V4 regressions to V6 and the proven default-open V7 condition."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from verify_frame_event_buffer_protocol import differences,timing_path
from verify_native_grpc_corpus_reference import verify_reference
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    protocol=read(root/'build/validation/receive-capacity-v4-protocol.json')
    extended=read(root/'build/validation/receive-capacity-v4-extended.json')
    corpus=read(root/'build/validation/receive-capacity-v4-corpus.json')
    assert protocol['key']=='b1c48d1b7a873357' and extended['key']=='1ed454ad98c4122f' and corpus['key']=='5c25325d35ca3718'
    baselines={k:(v['run'],protocol['key'])for k,v in protocol['executions'].items()}
    baselines.update({k:(v['snapshot'],extended['key'])for k,v in extended['executions'].items()})
    baselines['corpus']=('receive_capacity_v4_corpus_owner_20261122',corpus['key'])
    ap=argparse.ArgumentParser();ap.add_argument('--cases',nargs='+',required=True,choices=tuple(baselines))
    ap.add_argument('--candidate',choices=('rpc-stream-refusal-v6','rpc-registered-frame-select-v1'),default='rpc-stream-refusal-v6')
    ap.add_argument('--prefix',default='rpc_refusal_v6');args=ap.parse_args()
    assert len(set(args.cases))==len(args.cases)
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.prefix)
    candidate=root/'build/experiments'/args.candidate;generation=read(candidate/'generation.json')
    registered=args.candidate=='rpc-registered-frame-select-v1'
    if registered:
        from verify_registered_frame_select import require_unit_audit
        from registered_selection_assertions import input_promise_assertions
        directed=require_unit_audit(root);formal=None
        gpu_audit=read(root/'build/validation/rpc-registered-select-gpu.json')
        assert gpu_audit['generation_sha256']==sha(candidate/'generation.json')and len(gpu_audit['executions'])==2
    else:
        directed=read(root/'build/validation/rpc-stream-refusal.json');formal=read(root/'build/validation/rpc-refusal-default-open-equivalence.json')
        assert directed['key']=='5112d79cf95b87c8'and directed['generation_sha256']==sha(candidate/'generation.json')
        assert formal['key']=='462e4c8b3b38971b'and formal['default_open_conditional_equivalence_verified']
        assert formal['parent_generation_sha256']==sha(candidate/'generation.json')
        assert formal['candidate_generation_sha256']==sha(root/'build/experiments/rpc-stream-refusal-v7/generation.json')
    executions={};artifacts={Path(__file__)}
    for case in args.cases:
        baseline,key=baselines[case];run=args.prefix+'_'+case+'_20261122'
        folder=root/'build/wsl-reports'/('raw_envelope_'+run);source=folder/'execution-sources'
        parent=root/'build/wsl-reports'/('raw_envelope_'+baseline)
        launch=read(folder/'launch.json');report=read(folder/'report.json')
        inputs=read(folder/'inputs.json');accepted=read(folder/'acceptance.json');previous=read(parent/'acceptance.json')
        assert launch['phase']=='completed'and launch['exit_code']==0 and launch['case']==case
        assert launch['baseline_run']==baseline and launch['baseline_audit_key']==key
        assert launch['generation_sha256']==sha(candidate/'generation.json')==sha(folder/'refusal-generation.json')
        if registered:
            assert launch['candidate']==args.candidate and launch['registered_selection_unit_audit_key']==directed['key']
            assert launch['registered_selection_gpu_audit_key']==gpu_audit['key']and launch['actual_input_promise_assertions']==8
            assert launch['directed_runtime_audit_key']is None
            assert sha(folder/'registered_selection_assertions.py')==launch['passive_assertion_generator_sha256']==sha(root/'tools/registered_selection_assertions.py')
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0
        assert report['profile']==launch['profile']
        assert inputs==launch['inputs_sha256']==report['input_sha256']
        assert sha(folder/'acceptance.json')==report['acceptance_sha256']
        assert all(sha(source/n)==h for n,h in inputs.items())
        assert sha(folder/'regression-runner-used.py')==launch['driver_sha256']
        parent_inputs=read(parent/'inputs.json');assert parent_inputs==launch['parent_inputs_sha256']
        top='sim/cocotb_two_fpga_enveloped_top.sv';edit=launch['fixture_input_edit']
        assert edit['path']==top and edit['before_sha256']==parent_inputs[top]and edit['after_sha256']==inputs[top]
        text=(source/top).read_bytes().decode();original=text
        assert len(re.findall(r'\badmit_new_rpcs\b',text))==3
        assert re.search(r'reg\s+admit_new_rpcs=1;',text)
        if registered:
            assert input_promise_assertions()in(source/top).read_text()
            assert (source/top).read_text().count('Actual registered-selection input promise changed:')==8
        for before,after in reversed(edit['replacements']):
            assert text.count(after)==1;text=text.replace(after,before)
        assert text==(parent/'execution-sources'/top).read_bytes().decode()
        for n,h in parent_inputs.items():
            if not n.startswith('rtl/')and n!=top:assert inputs[n]==h,n
        for n in inputs:
            if n.endswith('.py'):assert b'admit_new_rpcs'not in(source/n).read_bytes(),n
        parser={n:sha(p)for n,p in closure('http2_enveloped_parser_application',source).items()}
        tokenizer={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
        assert len(parser)==78 and parser==generation['non_mmio_parser_sha256']==launch['parser_sha256']
        assert len(tokenizer)==22 and tokenizer==launch['tokenizer_sha256']=={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',parent/'execution-sources').items()}
        xml=ET.parse(folder/'results.xml');old_xml=ET.parse(parent/'results.xml')
        tests=xml.findall('.//testcase');old_tests=old_xml.findall('.//testcase')
        assert len(tests)==len(old_tests)==1 and tests[0].attrib['name']==old_tests[0].attrib['name']
        assert not xml.findall('.//failure')and not xml.findall('.//error')
        if registered and case=='duplex_faults':
            # These are physical UTF-8 link time measurements, not fault,
            # credit or ownership results. Preserve the original stall span
            # and require the actual stable-offer monitor and real ACK.
            top_text=(source/top).read_text()
            assert top_text.count('if(return_link_pause)return_link_pause_clocks<=return_link_pause_clocks+1;')==1
            assert top_text.count('if(link_s_s_axis_text_tvalid&&!return_link_source_ready)return_link_held_clocks<=return_link_held_clocks+1;')==1
            assert 'Actual inter-FPGA UTF-8 offer changed while backpressured'in top_text
            actual_faults=accepted['actual_context_commit_write_faults'];prior_faults=previous['actual_context_commit_write_faults']
            assert len(actual_faults)==len(prior_faults)==21
            for phase,(actual_fault,prior_fault)in enumerate(zip(actual_faults,prior_faults)):
                assert actual_fault['fault_phase']==prior_fault['fault_phase']==phase
                observed=actual_fault['capacity_fault_link_pause'];prior=prior_fault['capacity_fault_link_pause']
                assert observed.keys()==prior.keys()=={'held_cycles','pause_cycles','actual_fault_ack','link_released'}
                assert observed['actual_fault_ack']==prior['actual_fault_ack']==1
                assert observed['link_released']is prior['link_released']is True
                assert observed['pause_cycles']>=observed['held_cycles']>=prior['held_cycles']>0
        deltas=[]
        for path,actual,prior in differences(accepted,previous):
            extra=case=='duplex'and path==('raw_held_cycles',)
            extra=extra or (case=='duplex_faults'and len(path)==3 and path[0]=='actual_context_commit_write_faults'
                and isinstance(path[1],int)and 0<=path[1]<21 and path[2]=='raw_held_cycles')
            extra=extra or (registered and case=='duplex_faults'and len(path)==4 and path[0]=='actual_context_commit_write_faults'
                and isinstance(path[1],int)and 0<=path[1]<21 and path[2]=='capacity_fault_link_pause'
                and path[3]in('held_cycles','pause_cycles'))
            assert timing_path(path)or extra,(case,path,actual,prior)
            assert type(actual)==type(prior)==int and min(actual,prior)>=0
            deltas.append(dict(path=list(path),actual=actual,baseline=prior))
        execution=dict(run=run,baseline=baseline,baseline_audit_key=key,original_test_name=tests[0].attrib['name'],
            all_original_test_sources_images_packages_assertions_unchanged=True,
            only_top_fixture_input_added=not registered,admit_new_rpcs_constant_one_verified=True,
            operation_data_status_scope_and_order_equal=True,timing_differences_preserved=deltas,
            executed_parser_sha256=parser,executed_tokenizer_sha256=tokenizer,inputs_sha256=inputs)
        if case=='corpus':
            execution['independent_native_reference']=verify_reference(root,source,accepted,parser_memory_clients=19,native_wire_frames=2879)
        if registered:execution.update(passive_actual_input_promise_assertions=8,all_actual_input_assertions_passed=True)
        if registered and case=='duplex_faults':execution['actual_utf8_pause_time_deltas_source_bound_and_stall_coverage_preserved']=True
        executions[case]=execution
        artifacts.update(p for p in folder.iterdir()if p.is_file())
    result=dict(phase='rpc_refusal_original_regressions_source_and_trace_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,directed_v6_audit_key=None if registered else directed['key'],default_open_equivalence_audit_key=None if registered else formal['key'],
        actual_runtime_candidate=args.candidate,conditionally_equivalent_candidate=None if registered else'rpc-stream-refusal-v7',
        conditional_source_bridge_verified=not registered,default_open_condition_verified_for_all_selected_fixtures=True,
        all_seven_lifecycle_suites_verified=set(protocol['executions'])<=set(executions),
        all_five_extended_suites_verified=set(extended['executions'])<=set(executions),
        complete_16_prompt_corpus_verified='corpus'in executions,all_thirteen_original_suites_verified=set(executions)==set(baselines),
        exact_parser_modules=78,exact_tokenizer_modules=22,portable_memory_backend=True,
        new_refusal_branch_exercised=False,native_vendor_runtime_verified=False,full_protocol_fault_matrix_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in sorted(artifacts)})
    if registered:result.update(registered_selection_unit_audit_key=directed['key'],registered_selection_gpu_audit_key=gpu_audit['key'],
        actual_eight_source_promise_assertions_verified=True,phase='registered_selection_original_regressions_verified')
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-refusal-original-regressions-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    shutil.copy2(root/'tools/verify_frame_event_buffer_protocol.py',evidence/'verify_frame_event_buffer_protocol.py')
    pointer='rpc-registered-select-original-regressions.json'if registered else'rpc-refusal-original-regressions.json'
    for p in (evidence/'audit.json',root/'build/validation'/pointer):
        p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],verified_suites=len(executions))))


if __name__=='__main__':main()
