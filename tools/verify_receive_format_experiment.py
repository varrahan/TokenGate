"""Bind real global FORMAT/retry and shutdown evidence to the complete RTL join."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/receive-format'
    generation=json.loads((folder/'generation.json').read_text())
    cases_generation=json.loads((folder/'sim/generation.json').read_text())
    drain_generation=json.loads((folder/'drain/generation.json').read_text())
    parent=json.loads((root/'build/validation/retire-cause-experiment.json').read_text())
    baseline=json.loads((root/'build/validation/post-commit-retire-experiment.json').read_text())
    scope_generation=json.loads((root/'build/experiments/post-retire-scope/generation.json').read_text())
    executions={};parser_hashes=tokenizer_hashes=None
    for label,name,profile,test in (
        ('native','receive_format_native','native','test_raw_grpc_enveloped.py'),
        ('other_connection','receive_format_other_connection','duplex','test_raw_grpc_duplex.py'),
        ('format_ack_scope','receive_format_ack_faults_scope','shutdown-faults','test_raw_shutdown_faults.py'),
        ('owned_gpu_drain','receive_format_owned_gpu_drain','shutdown-faults','test_raw_shutdown_faults.py'),
        ('shutdown','receive_format_shutdown_faults','shutdown-faults','test_raw_shutdown_faults.py')):
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
        hashes=[]
        for top,size in (('http2_enveloped_parser_application',75),('tokenizer_fpga_memory_subsystem',22)):
            dag=closure(top,source);assert len(dag)==size
            hashes.append({n:sha(p) for n,p in dag.items()})
            for p in dag.values():
                relative=p.relative_to(source)
                assert inputs[relative.as_posix()]==generation['generated_sha256'].get(p.name,sha(root/relative))
        assert parser_hashes is None or parser_hashes==hashes[0]
        assert tokenizer_hashes is None or tokenizer_hashes==hashes[1]
        parser_hashes,tokenizer_hashes=hashes
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n]==baseline['executions']['native']['inputs_sha256'][n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        if label=='native':
            assert inputs['sim/cocotb/'+test]==baseline['executions']['native']['inputs_sha256']['sim/cocotb/'+test]
            assert [accepted[n] for n in ('native_complete_grpc_calls','actual_forward_dma_ids',
                'actual_gpu_descriptors_accepted','actual_captured_dma_ids_returned')]==[2,6,8,4]
            assert accepted['actual_receive_pool_ownership']['receive_memory_acks']==403
            assert accepted['actual_receive_pool_ownership']['receive_grants']==accepted['actual_receive_pool_ownership']['receive_unlocks']==4
            for n in ('actual_raw_rst_drains_offered_initial_header','actual_raw_rst_drains_offered_final_trailer',
                      'actual_header_commit_failure_propagates_through_raw_reset','failed_header_commit_never_processes_reset'):
                assert accepted[n]
        elif label=='other_connection':
            assert inputs['sim/cocotb/'+test]==scope_generation['fixture_sha256']
            assert [accepted[k] for k in ('actual_other_connection_user','actual_other_stream',
                'actual_other_rpc_address','actual_other_generation','actual_same_rpc_address','actual_reused_generation')]==[1,1,7232128,2,7232000,3]
            assert accepted['actual_other_regions_unchanged_through_reopen'] and accepted['actual_other_rpc_closed_after_its_own_response']
            assert accepted['actual_other_captured_dma_ids']==accepted['actual_reopened_dma_ids_returned']==[15339,1917]
            assert accepted['actual_other_response_hex']==accepted['actual_reopened_native_response_hex']
        elif label=='format_ack_scope':
            assert inputs['sim/cocotb/'+test]==cases_generation['fixture_sha256']
            assert inputs['sim/cocotb/receive_format_witness.py']==cases_generation['witness_sha256']
            cases=accepted['actual_format_ack_fault_cases'];assert [c['phase'] for c in cases]==list(range(12))
            assert all(c['actual_error']==0x75 and c['explicit_same_scope_retry_without_reset'] for c in cases)
            records=accepted['actual_format_transactions'];assert len(records)==29
            assert records[0]['result'][:3]==[7,2,0] and records[0]['backend_requests']==0
            assert records[2]['result'][:3]==[2,1,0] and records[2]['backend_requests']==1 and not records[2]['commands']
            assert records[-2]['result'][:3]==[6,1,0] and records[-2]['base']==0x7e6100 and not records[-2]['commands']
            failed=[r for r in records if r['result'][0]==5]
            assert len(failed)==12
            for phase,r in enumerate(failed):
                assert len(r['acks'])==phase+1 and r['acks'][-1]['status']==0x75
                assert [a['status'] for a in r['acks']]==[0]*phase+[0x75]
                assert r['result'][:3]==[5,7,0x75]
            for r in records:
                assert r['held_public_cycles']>=13 and r['held_directory_cycles']>=13
                assert len(r['commands'])==len(r['acks'])
                for index,(command,ack) in enumerate(zip(r['commands'],r['acks'])):
                    assert command['address']==r['base']+8*index and command['write']==1
                    assert command['bytes']==8 and command['data']==0
                    assert command['clock']<ack['ack_clock']<r['first_offer_clock']<=r['result_ack_clock']
                if r['result'][0]==0:assert len(r['acks'])==12 and all(a['status']==0 for a in r['acks'])
            for n in ('captured_runtime_scope_and_maintenance_verified','actual_pool_lock_for_format_verified',
                      'explicit_same_scope_retry_without_global_reset','missing_maintenance_rejected_without_receive_memory',
                      'invalid_receive_geometry_rejected_without_receive_memory','mismatched_receive_scope_cannot_clear_quarantine',
                      'post_retry_open_and_native_headers_admitted'):assert accepted[n]
            assert accepted['retained_window_warm_reset_verified'] is False
        elif label=='owned_gpu_drain':
            assert inputs['sim/cocotb/'+test]==drain_generation['fixture_sha256']
            assert accepted['actual_captured_dma_ids']==[15339,1917] and accepted['actual_gpu_token']==15339
            assert accepted['actual_ordering'][0]['event']=='actual_gpu_result_ack'
            assert accepted['actual_ordering'][1]['event']=='actual_format_request_ack'
            assert accepted['actual_ordering'][0]['clock']<accepted['actual_ordering'][1]['clock']
            assert accepted['actual_native_response_hex']=='00000000088a010568656c6c6f'
            assert accepted['held_wire_cycles']==17 and len(accepted['actual_format_transactions'])==2
            for record in accepted['actual_format_transactions']:
                assert record['result'][0]==0 and len(record['acks'])==12
                assert all(a['status']==0 for a in record['acks'])
            for n in ('actual_format_waited_for_offered_wire_and_gpu_lease',
                      'actual_gpu_lookup_and_response_drained_while_format_waited','actual_format_completed_without_reset'):
                assert accepted[n]
        else:
            assert inputs['sim/cocotb/'+test]==sha(root/'sim/cocotb'/test)
            expected=[dict(service=kind,phase=p,memory_commands=p+1,reset_processed=kind=='directory')
                for kind,count in (('directory',9),('window',14),('peer',18)) for p in range(count)]
            assert accepted['actual_raw_fault_cases']==expected
            assert accepted['actual_memory_error']==0x75 and accepted['applied_write_errors']
            assert accepted['successful_reset_after_explicit_root_reinitialization']
            assert accepted['fresh_disjoint_window_arena_per_global_reset']
            assert accepted['retained_window_arena_warm_reset_verified'] is False
        executions[label]=dict(snapshot=name,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    changed=sorted(n for n,h in parser_hashes.items() if h!=parent['executed_parser_sha256'][n])
    assert changed==['http2_enveloped_parser_core','http2_keyed_receive_credit_store','http2_receive_credit_store','http2_receive_flow_controller']
    assert tokenizer_hashes==parent['executed_tokenizer_sha256']
    replay=root/'build/validation/receive-format-generation-replay'
    paths=set(generation['input_sha256'])|{'tools/generate_receive_format_experiment.py',
        'tools/generate_receive_format_cases.py','tools/generate_receive_format_drain_case.py','tools/generate_receive_pool_experiment.py',
        'tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
        'sim/cocotb/receive_format_witness.py'}
    assert generation['generator_sha256']==sha(root/'tools/generate_receive_format_experiment.py')
    assert cases_generation['generator_sha256']==sha(root/'tools/generate_receive_format_cases.py')
    assert drain_generation['generator_sha256']==sha(root/'tools/generate_receive_format_drain_case.py')
    assert drain_generation['source_sha256']==cases_generation['fixture_sha256']
    for n in paths:
        assert n not in generation['input_sha256'] or sha(root/n)==generation['input_sha256'][n]
        destination=replay/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,destination)
    for generator,manifest,manifest_path in (
        ('generate_receive_format_experiment.py',generation,'generation.json'),
        ('generate_receive_format_cases.py',cases_generation,'sim/generation.json'),
        ('generate_receive_format_drain_case.py',drain_generation,'drain/generation.json')):
        subprocess.run([sys.executable,str(replay/'tools'/generator)],check=True,capture_output=True,text=True)
        generated=replay/'build/experiments/receive-format'/manifest_path
        assert json.loads(generated.read_text())==manifest
    result=dict(phase='actual_global_receive_format_and_shutdown_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,executed_parser_sha256=parser_hashes,executed_tokenizer_sha256=tokenizer_hashes,
        exact_parser_modules=75,exact_tokenizer_modules=22,changed_parser_modules=changed,parent_audit_key=parent['key'],
        actual_receive_format_ack_faults_verified=12,explicit_same_scope_reformat_recovery_verified=True,
        actual_receive_scope_captured_and_pool_locked=True,full_41_shutdown_fault_matrix_verified=True,
        actual_format_waits_for_owned_gpu_and_allows_its_response_to_drain=True,
        retained_receive_reset_counterexample_resolved=True,retained_window_warm_reset_verified=False,
        generator_replay_verified=True,current_native_implementation_verified=False,
        new_retirement_ack_matrix_verified=False,formal_induction_verified=False,full_system_complete=False,
        generation_sha256=sha(folder/'generation.json'),case_generation_sha256=sha(folder/'sim/generation.json'),
        verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-format-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_receive_format_experiment.py',root/'tools/generate_receive_format_cases.py',root/'tools/generate_receive_format_drain_case.py',
              root/'sim/cocotb/receive_format_witness.py',folder/'generation.json'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/receive-format-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=len(executions),format_faults=12,shutdown_faults=41)))


if __name__=='__main__':main()
