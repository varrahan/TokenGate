"""Audit real late-error retirement without promoting the experimental RTL."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/post-commit-retire'
    generation=json.loads((folder/'generation.json').read_text())
    semantic=json.loads((root/'build/experiments/local-semantic-cases/generation.json').read_text())
    baseline=json.loads((root/'build/validation/packer-keep-experiment.json').read_text())
    cases=[('rst_idle_stream','post_commit_witness_rst_idle','duplex','rst_idle_stream/test_raw_grpc_duplex.py'),
        ('connection_window_overflow','post_commit_witness_window_overflow','duplex','connection_window_overflow/test_raw_grpc_duplex.py'),
        ('initial_window_overflow','post_commit_witness_initial_window','duplex','initial_window_overflow/test_raw_grpc_duplex.py'),
        ('max_frame_too_small','post_commit_witness_small_frame','duplex','max_frame_too_small/test_raw_grpc_duplex.py'),
        ('native','post_commit_witness_native','native','test_raw_grpc_enveloped.py'),
        ('held_trailer','post_commit_retire_held_trailer','duplex',None),
        ('first_directory_ack_fault','post_commit_retire_first_directory_ack_fault','duplex',None)]
    cache={};executions={};parser_hashes=tokenizer_hashes=None
    for label,name,profile,fixture in cases:
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
        read=lambda n:json.loads((archive/n).read_text())
        inputs,report,state,accepted=(read(n) for n in ('inputs.json','report.json','snapshot.json','acceptance.json'))
        assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
        assert report['profile']==state['profile']==profile and report['tests']==1 and report['failures']==0
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
        hashes=[{n:sha(source/p) for n,p in cache[signature][top].items()}
            for top in ('http2_enveloped_parser_application','tokenizer_fpga_memory_subsystem')]
        assert tuple(map(len,hashes))==(75,22)
        assert parser_hashes is None or parser_hashes==hashes[0]
        assert tokenizer_hashes is None or tokenizer_hashes==hashes[1]
        parser_hashes,tokenizer_hashes=hashes
        for top in cache[signature].values():
            for n,p in top.items():
                assert inputs[p.as_posix()]==generation['generated_sha256'].get(p.name,sha(root/p))
        previous=baseline['executions']['credit_cancel']['inputs_sha256']
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n]==previous[n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        if fixture:
            test='test_raw_grpc_enveloped.py' if profile=='native' else 'test_raw_grpc_duplex.py'
            assert inputs['sim/cocotb/'+test]==generation['sim_sha256'][fixture]
            assert inputs['sim/cocotb/post_commit_retire_witness.py']==generation['input_sha256']['sim/cocotb/post_commit_retire_witness.py']
            proof=accepted['actual_post_commit_retirement']
            required=label=='native' or semantic['cases'][label]['expected_packet_status']==11
            assert proof['actual_post_commit_request']==required
            if required:
                assert proof['actual_scope_user']==0
                assert proof['actual_held_original_result']==[1,0,0,0,0,proof['actual_scope_tag']]
                assert proof['held_original_result_cycles']>=607
                assert len(proof['actual_directory_closes'])==(3 if label=='native' else 1)
                trace=proof['actual_trace']
                assert trace[0]['event']=='actual_post_commit_abort_request'
                assert [e['event'] for e in trace[-2:]]==['actual_post_commit_retirement_ack','original_packet_result_ack']
                assert trace[-3]['event']=='actual_directory_result_ack' and (trace[-3]['op'],trace[-3]['status'])==(6,3)
                assert all(a['clock']<b['clock'] for a,b in zip(trace,trace[1:]))
                for key in ('actual_receive_streams_closed_before_directory_result_ack','actual_connection_available_not_refunded',
                            'original_packet_result_promise_preserved'):assert proof[key]
        elif label=='held_trailer':
            assert accepted==baseline['executions']['gpu_drain']['acceptance']
        else:
            probe=root/'build/experiments/post-commit-retire-fault-probe'
            probe_generation=json.loads((probe/'generation.json').read_text())
            assert inputs['sim/cocotb/test_raw_grpc_duplex.py']==probe_generation['fixture_sha256']
            assert accepted['actual_retirement_fault_client']==accepted['actual_retirement_fault_ack_phase']==0
            assert accepted['actual_retirement_error']==[13,0x82,0x75]
            assert accepted['actual_preserved_committed_result']==[1,0,0,0,0,3]
            assert accepted['actual_directory_commands_after_request']==1
            for key in ('actual_rpc_record_remains_owned','actual_gpu_retired_before_retirement_request',
                        'actual_memory_error_propagated_to_packet','actual_no_goaway_or_host_close_on_uncertain_retirement',
                        'actual_no_replay_after_injection_cleared','actual_retirement_pending_and_recovery_retained'):
                assert accepted[key]
            assert accepted['recovery_after_uncertain_retirement_verified'] is False
        if label in semantic['cases']:
            case=semantic['cases'][label]
            assert accepted['actual_semantic_case']==label
            assert accepted['actual_connection_http2_error']==case['expected_http2_error']
            assert accepted['native_reference_http2_error']==case['native_http2_error']
            assert accepted['actual_rpc_header_after_fatal_hex']=='0000000000000000'
            assert accepted['actual_reused_generation']==2 and accepted['actual_same_rpc_address']==7232000
            assert accepted['actual_reopened_dma_ids_returned']==[15339,1917]
            close=accepted['local_error_ownership']
            assert close['actual_goaway_and_host_close_http2_error']==case['expected_http2_error']
            assert close['held_goaway_cycles']==17 and close['held_host_close_cycles']==13
            assert close['wire_retired_clock']<close['host_close_retired_clock']<close['first_public_packet_result_clock']
        executions[label]=dict(snapshot=name,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    changed=sorted(n for n,h in parser_hashes.items() if h!=baseline['executed_parser_sha256'][n])
    assert changed==sorted(['grpc_external_directory_ingress','grpc_shared_directory_parser','grpc_shared_directory_prefill',
        'http2_classified_parser_transport','http2_enveloped_parser_core'])
    assert tokenizer_hashes==baseline['executed_tokenizer_sha256']
    counters={}
    for name,phase in (
        ('packer_keep_semantic_rst_idle_stream','late_semantic_error_completion_order_failure'),
        ('packer_keep_semantic_connection_window_overflow','late_semantic_error_completion_order_failure'),
        ('semantic_drain_rst_idle_stream','late_semantic_error_left_active_rpc')):
        archive=root/'build/wsl-reports'/('raw_envelope_'+name)
        failed=json.loads((archive/'failure.json').read_text())
        assert json.loads((archive/'snapshot.json').read_text())['exit_code']!=0 and failed['phase']==phase
        counters[name]=dict(phase=phase,failure_sha256=sha(archive/'failure.json'),snapshot_sha256=sha(archive/'snapshot.json'))
    replay=root/'build/validation/post-commit-retire-generation-replay'
    assert generation['generator_sha256']==sha(root/'tools/generate_post_commit_retire_experiment.py')
    paths=set(generation['input_sha256'])|{'tools/generate_post_commit_retire_experiment.py',
        'tools/generate_receive_pool_experiment.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py'}
    for n in paths:
        assert n not in generation['input_sha256'] or sha(root/n)==generation['input_sha256'][n]
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,target)
    subprocess.run([sys.executable,str(replay/'tools/generate_post_commit_retire_experiment.py')],check=True,capture_output=True,text=True)
    replayed=json.loads((replay/'build/experiments/post-commit-retire/generation.json').read_text())
    assert replayed==generation
    probe_generator=root/'tools/generate_post_commit_retire_fault_probe.py'
    assert probe_generation['generator_sha256']==sha(probe_generator)
    assert probe_generation['source_sha256']==sha(root/'build/experiments/local-semantic-cases/rst_idle_stream/test_raw_grpc_duplex.py')
    shutil.copy2(probe_generator,replay/'tools'/probe_generator.name)
    subprocess.run([sys.executable,str(replay/'tools'/probe_generator.name)],check=True,capture_output=True,text=True)
    assert json.loads((replay/'build/experiments/post-commit-retire-fault-probe/generation.json').read_text())==probe_generation
    result=dict(phase='actual_post_commit_retirement_directed_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,executed_parser_sha256=parser_hashes,executed_tokenizer_sha256=tokenizer_hashes,
        exact_parser_modules=75,exact_tokenizer_modules=22,parser_memory_clients=19,tokenizer_memory_clients=9,
        changed_parser_modules=changed,baseline_direct_audit_key=baseline['key'],counterexamples=counters,
        generation_sha256=sha(folder/'generation.json'),generator_replay_verified=True,
        actual_directory_and_receive_retirement_before_completion_verified=True,
        original_committed_result_stable_during_retirement_verified=True,
        full_model_fixture_matches_audited_baseline=True,tokenizer_rtl_unchanged=True,
        new_retirement_ack_fault_matrix_verified=False,actual_retirement_ack_faults_verified=1,
        first_directory_ack_fault_retains_recovery_and_original_result_verified=True,
        formal_induction_verified=False,
        current_parser_native_implementation_verified=False,full_native_corpus_on_new_variant_verified=False,
        complete_protocol_matrix_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/post-commit-retire-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_post_commit_retire_experiment.py',folder/'generation.json',root/'sim/cocotb/post_commit_retire_witness.py',probe_generator):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/post-commit-retire-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=len(executions),changed_modules=changed)))


if __name__=='__main__':main()
