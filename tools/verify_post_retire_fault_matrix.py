"""Audit actual retirement ACK faults against a passively captured full-model run."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cases',nargs='+')
    variants=parser.add_mutually_exclusive_group()
    variants.add_argument('--receive-format',action='store_true',help='Audit the global receive FORMAT child replay')
    variants.add_argument('--window-authority',action='store_true',help='Audit private global FORMAT authority and cleanup cause replay')
    variants.add_argument('--progress-format',action='store_true',help='Audit global response-progress FORMAT child replay')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/post-retire-fault-matrix'
    generation=json.loads((folder/'generation.json').read_text())
    trace_folder=root/'build/experiments/post-retire-memory-trace'
    trace_generation=json.loads((trace_folder/'generation.json').read_text())
    direct=json.loads((root/'build/validation/post-commit-retire-experiment.json').read_text())
    variant='progress-format' if args.progress_format else 'window-authority' if args.window_authority else 'receive-format' if args.receive_format else None
    current=json.loads((root/'build/validation'/(variant+'-experiment.json')).read_text()) if variant else direct
    adapted=json.loads((root/'build/experiments/progress-format/regressions/generation.json').read_text()) if args.progress_format else None
    cache={}

    def execution(name,expected_direct=None):
        expected_direct=expected_direct or direct
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
        read=lambda n:json.loads((archive/n).read_text())
        inputs,report,state,accepted=(read(n) for n in ('inputs.json','report.json','snapshot.json','acceptance.json'))
        assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
        assert report['profile']==state['profile']=='duplex' and report['tests']==1 and report['failures']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():
            assert sha(source/n)==h,(name,n)
            if n.startswith('native-vendor/'):assert sha(root/'.venv312/Lib/site-packages'/n.split('/',1)[1])==h
        xml=ET.parse(archive/'results.xml')
        assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure') and not xml.findall('.//error')
        signature=tuple(sorted((n,h) for n,h in inputs.items() if n.startswith('rtl/') and n.endswith('.v')))
        if signature not in cache:
            cache[signature]={top:{n:p.relative_to(source) for n,p in closure(top,source).items()}
                for top in ('http2_enveloped_parser_application','tokenizer_fpga_memory_subsystem')}
        for top,label,size in (('http2_enveloped_parser_application','parser',75),('tokenizer_fpga_memory_subsystem','tokenizer',22)):
            hashes={n:sha(source/p) for n,p in cache[signature][top].items()}
            assert len(hashes)==size and hashes==expected_direct['executed_'+label+'_sha256']
        baseline=direct['executions']['rst_idle_stream']['inputs_sha256']
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n]==baseline[n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        return archive,inputs,accepted

    golden,golden_inputs,positive=execution('post_retire_memory_trace')
    assert golden_inputs['sim/cocotb/test_raw_grpc_duplex.py']==trace_generation['fixture_sha256']
    assert golden_inputs['sim/cocotb/post_retire_memory_witness.py']==trace_generation['witness_sha256']
    without_trace={k:v for k,v in positive.items() if k!='actual_retirement_memory'}
    assert without_trace==direct['executions']['rst_idle_stream']['acceptance']
    memory=positive['actual_retirement_memory'];traces=memory['actual_logical_client_acks']
    assert {n:len(a) for n,a in traces.items()}=={'0':20,'26':19}
    assert [(r['service'],r['op']) for r in memory['actual_service_requests']]==[('directory',6),('directory',3),('receive',10),('directory',6)]
    assert [(n,a['address'],a['data']) for n,a in enumerate(traces['0']) if a['write']]==[(16,7232000,0)]
    assert [(n,a['address'],a['data']) for n,a in enumerate(traces['26']) if a['write']]==[(17,0x7e6008,0x800000010000ffed),(18,0x7e6010,0)]
    for trace in traces.values():
        assert all(a['status']==0 and a['command_clock']<a['ack_clock'] and a['bytes']==8 for a in trace)
        assert all(a['ack_clock']<b['command_clock'] for a,b in zip(trace,trace[1:]))
    assert generation['golden_acceptance_sha256']==sha(golden/'acceptance.json')
    scope_folder=root/'build/experiments/post-retire-scope'
    scope_generation=json.loads((scope_folder/'generation.json').read_text())
    scope_archive,scope_inputs,scope=execution(variant.replace('-','_')+'_other_connection' if variant else 'post_retire_other_connection_scope',current)
    assert scope_inputs['sim/cocotb/test_raw_grpc_duplex.py']==(adapted['cases']['other_connection']['fixture_sha256'] if adapted else scope_generation['fixture_sha256'])
    if adapted:assert adapted['cases']['other_connection']['source_sha256']==scope_generation['fixture_sha256']
    assert scope_inputs['sim/cocotb/post_retire_scope_bench.py']==scope_generation['witness_sha256']
    assert [scope[k] for k in ('actual_other_connection_user','actual_other_stream','actual_other_rpc_address',
        'actual_other_generation','actual_same_rpc_address','actual_reused_generation')]==[1,1,7232128,2,7232000,3]
    assert scope['actual_other_captured_dma_ids']==scope['actual_reopened_dma_ids_returned']==[15339,1917]
    assert scope['actual_other_response_hex']==scope['actual_reopened_native_response_hex']==positive['actual_reopened_native_response_hex']
    assert scope['actual_other_regions_unchanged_through_reopen'] and scope['actual_other_rpc_closed_after_its_own_response']
    assert scope['actual_post_commit_retirement']['actual_directory_closes']==[dict(user=0,stream=1,generation=1,address=7232000)]
    selected=args.cases or list(generation['cases']);assert len(set(selected))==len(selected)
    assert all(n in generation['cases'] for n in selected)
    executions={}
    for name in selected:
        case=generation['cases'][name];client=case['client'];phase=case['ack_phase']
        snapshot=(variant.replace('-','_')+'_retire_fault_' if variant else 'post_retire_fault_')+name
        archive,inputs,accepted=execution(snapshot,current)
        assert inputs['sim/cocotb/test_raw_grpc_duplex.py']==(adapted['cases']['retire_fault_'+name]['fixture_sha256'] if adapted else case['fixture_sha256'])
        if adapted:assert adapted['cases']['retire_fault_'+name]['source_sha256']==case['fixture_sha256']
        assert inputs['sim/cocotb/post_retire_fault_witness.py']==generation['witness_sha256']
        expected=[{k:a[k] for k in ('write','address','bytes','data','response_data')} for a in traces[str(client)][:phase+1]]
        assert case['actual_successful_prefix']==expected
        assert accepted['actual_retirement_fault_client']==client and accepted['actual_retirement_fault_ack_phase']==phase
        assert accepted['actual_preserved_committed_result']==[1,0,0,0,0,3]
        assert accepted['actual_retirement_error']==case['expected_error']==[13,0x85 if client==26 or expected[-1]['write'] else 0x82,0x75]
        assert accepted['actual_selected_client_commands_after_request']==phase+1
        acks=accepted['actual_ack_prefix'];assert len(acks)==phase+1
        assert [{k:a[k] for k in expected[0]} for a in acks]==expected
        assert [a['status'] for a in acks]==[0]*phase+[0x75]
        assert accepted['actual_rpc_header_cleared']==case['expected_rpc_header_cleared']
        assert accepted['actual_receive_closed']==case['expected_receive_closed']
        assert accepted['actual_last_selected_write_applied']==bool(expected[-1]['write'])
        for key in ('actual_gpu_retired_before_retirement_request','actual_memory_error_propagated_to_packet',
                    'actual_no_goaway_or_host_close_on_uncertain_retirement','actual_no_replay_after_injection_cleared',
                    'actual_retirement_pending_and_recovery_retained'):assert accepted[key]
        assert accepted['recovery_after_uncertain_retirement_verified'] is False
        executions[name]=dict(snapshot=snapshot,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    replay=root/'build/validation/post-retire-fault-generation-replay'
    paths=['tools/generate_post_retire_memory_trace.py','tools/generate_post_retire_fault_matrix.py',
        'tools/generate_receive_pool_experiment.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
        'sim/cocotb/post_retire_memory_witness.py','sim/cocotb/post_retire_fault_witness.py',
        'build/experiments/post-commit-retire/sim/rst_idle_stream/test_raw_grpc_duplex.py',
        'build/experiments/post-commit-retire-fault-probe/test_raw_grpc_duplex.py',
        'build/wsl-reports/raw_envelope_post_retire_memory_trace/acceptance.json',
        'build/wsl-reports/raw_envelope_post_retire_memory_trace/snapshot.json',
        'tools/generate_post_retire_scope_case.py','sim/cocotb/post_retire_scope_bench.py', 'tools/rtl_paths.py']
    assert generation['generator_sha256']==sha(source_path(root, paths[1])) and generation['source_sha256']==sha(source_path(root, paths[8]))
    assert trace_generation['generator_sha256']==sha(source_path(root, paths[0])) and trace_generation['source_sha256']==sha(source_path(root, paths[7]))
    assert scope_generation['generator_sha256']==sha(source_path(root, paths[-2])) and scope_generation['source_sha256']==sha(source_path(root, paths[7]))
    for n in paths:
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, n),target)
    for generator,subfolder,manifest in (('generate_post_retire_memory_trace.py','post-retire-memory-trace',trace_generation),
        ('generate_post_retire_fault_matrix.py','post-retire-fault-matrix',generation),
        ('generate_post_retire_scope_case.py','post-retire-scope',scope_generation)):
        subprocess.run([sys.executable,str(replay/'tools'/generator)],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/experiments'/subfolder/'generation.json').read_text())==manifest
    if adapted:
        adapter='tools/generate_progress_format_regressions.py'
        assert adapted['generator_sha256']==sha(source_path(root, adapter))
        for n in {adapter}|{case['source'] for case in adapted['cases'].values()}:
            target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, n),target)
        for n in ('progress_format_witness.py',):
            target=replay/'sim/cocotb'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/'sim/cocotb'/n,target)
        subprocess.run([sys.executable,str(replay/adapter)],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/experiments/progress-format/regressions/generation.json').read_text())==adapted
    complete=len(executions)==39
    result=dict(phase='post_retire_all_actual_ack_faults_verified' if complete else 'post_retire_selected_actual_ack_faults_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),executions=executions,actual_ack_faults_verified=len(executions),
        all_39_actual_retirement_ack_faults_verified=complete,directory_faults_verified=sum(generation['cases'][n]['client']==0 for n in executions),
        receive_faults_verified=sum(generation['cases'][n]['client']==26 for n in executions),
        complete_model_and_native_packages_match_direct_audit=True,exact_parser_modules=75,exact_tokenizer_modules=22,
        executed_parser_sha256=current['executed_parser_sha256'],executed_tokenizer_sha256=current['executed_tokenizer_sha256'],
        direct_audit_key=current['key'],golden_acceptance_sha256=sha(golden/'acceptance.json'),
        actual_second_connection_same_stream_scope_verified=True,second_connection_acceptance=scope,
        second_connection_archive_sha256={p.name:sha(p) for p in scope_archive.iterdir() if p.is_file()},
        second_connection_generation_sha256=sha(scope_folder/'generation.json'),
        generation_sha256=sha(folder/'generation.json'),generator_replay_verified=True,
        uncertain_applied_write_cases_verified=[n for n in executions if generation['cases'][n]['actual_successful_prefix'][-1]['write']],
        recovery_after_uncertain_retirement_verified=False,formal_induction_verified=False,
        full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    if adapted:result['adapted_fixture_generation_sha256']=sha(root/'build/experiments/progress-format/regressions/generation.json')
    if variant:result['phase']=variant.replace('-','_')+'_'+result['phase']
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation'/((variant+'-retire-fault-evidence') if variant else 'post-retire-fault-evidence')/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),folder/'generation.json',source_path(root, paths[0]),source_path(root, paths[1]),source_path(root, paths[5]),source_path(root, paths[6]),source_path(root, paths[-2]),source_path(root, paths[-1])):shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    output=root/'build/validation'/((variant+'-' if variant else '')+('post-retire-fault-matrix.json' if complete else 'post-retire-selected-faults.json'))
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,actual_faults=len(executions),complete=complete)))


if __name__=='__main__':main()
