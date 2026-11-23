"""Audit real dual-ledger FORMAT and retained-window recovery on the full join."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure
from generate_two_fpga_application import header_end

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/window-format'
    manifests={n:json.loads((folder/n).read_text()) for n in ('generation.json','sim/generation.json','drain/generation.json')}
    generation=manifests['generation.json']
    retained=json.loads((root/'build/experiments/retained-window-reset/generation.json').read_text())
    parent=json.loads((root/'build/validation/receive-format-experiment.json').read_text())
    executions={};parser_hashes=tokenizer_hashes=None
    for label,name,profile,test in (
        ('native','window_format_native','native','test_raw_grpc_enveloped.py'),
        ('other_connection','window_format_other_connection','duplex','test_raw_grpc_duplex.py'),
        ('ledger_faults','window_format_all_ledger_ack_faults','shutdown-faults','test_raw_shutdown_faults.py'),
        ('retained_shutdown','window_format_retained_shutdown','shutdown-faults','test_raw_shutdown_faults.py'),
        ('owned_gpu_drain','window_format_owned_gpu_drain','shutdown-faults','test_raw_shutdown_faults.py')):
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
            dag=closure(top,source);assert len(dag)==size;hashes.append({n:sha(p) for n,p in dag.items()})
            for p in dag.values():
                relative=p.relative_to(source)
                assert inputs[relative.as_posix()]==generation['generated_sha256'].get(p.name,sha(source_path(root, relative)))
        assert parser_hashes is None or parser_hashes==hashes[0]
        assert tokenizer_hashes is None or tokenizer_hashes==hashes[1]
        parser_hashes,tokenizer_hashes=hashes
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n]==parent['executions']['native']['inputs_sha256'][n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        if label=='native':
            assert inputs['sim/cocotb/'+test]==parent['executions']['native']['inputs_sha256']['sim/cocotb/'+test]
            assert [accepted[n] for n in ('native_complete_grpc_calls','actual_forward_dma_ids',
                'actual_gpu_descriptors_accepted','actual_captured_dma_ids_returned')]==[2,6,8,4]
            pool=accepted['actual_receive_pool_ownership']
            assert pool['receive_memory_acks']==pool['receive_memory_commands']==403
            assert pool['receive_grants']==pool['receive_unlocks']==4
            for n in ('actual_raw_rst_drains_offered_initial_header','actual_raw_rst_drains_offered_final_trailer',
                      'actual_header_commit_failure_propagates_through_raw_reset','failed_header_commit_never_processes_reset'):assert accepted[n]
        elif label=='other_connection':
            assert inputs['sim/cocotb/'+test]==parent['executions']['other_connection']['inputs_sha256']['sim/cocotb/'+test]
            assert [accepted[k] for k in ('actual_other_connection_user','actual_other_stream',
                'actual_other_rpc_address','actual_other_generation','actual_same_rpc_address','actual_reused_generation')]==[1,1,7232128,2,7232000,3]
            assert accepted['actual_other_regions_unchanged_through_reopen'] and accepted['actual_other_rpc_closed_after_its_own_response']
            assert accepted['actual_other_captured_dma_ids']==accepted['actual_reopened_dma_ids_returned']==[15339,1917]
            assert accepted['actual_other_response_hex']==accepted['actual_reopened_native_response_hex']
        elif label=='ledger_faults':
            assert inputs['sim/cocotb/'+test]==manifests['sim/generation.json']['fixture_sha256']
            assert inputs['sim/cocotb/window_format_witness.py']==manifests['sim/generation.json']['witness_sha256']
            assert [c['phase'] for c in accepted['actual_receive_format_fault_cases']]==list(range(12))
            assert [c['phase'] for c in accepted['actual_window_format_fault_cases']]==list(range(6))
            records=accepted['actual_format_transactions'];assert len(records)==41
            receive_errors=[r for r in records if r['result'][:3]==[5,7,0x75]]
            window_errors=[r for r in records if r['result'][:3]==[5,2,0x75]]
            assert len(receive_errors)==12 and len(window_errors)==6
            for phase,r in enumerate(receive_errors):
                assert [a['status'] for a in r['acks']['26']]==[0]*phase+[0x75]
                assert not r['acks']['22'] and not r['commands']['22']
                assert [(a['client'],a['op']) for a in r['requests']]==[(26,11)]
            for phase,r in enumerate(window_errors):
                assert len(r['acks']['26'])==12 and all(a['status']==0 for a in r['acks']['26'])
                assert [a['status'] for a in r['acks']['22']]==[0]*phase+[0x75]
            assert records[0]['result'][:3]==[7,2,0] and not records[0]['requests']
            assert records[2]['result'][:3]==[2,1,0] and not records[2]['acks']['22']
            assert records[-2]['result'][:3]==[6,1,0] and records[-2]['bases']['22']==0x7f0100
            assert not records[-2]['acks']['22']
            assert sum(r['result'][0]==0 for r in records)==20
            for n in ('captured_window_scope_and_maintenance_verified','actual_pool_lock_for_both_ledgers_verified',
                      'explicit_same_scope_retry_without_reset','alternate_window_scope_cannot_clear_quarantine',
                      'missing_maintenance_and_invalid_window_geometry_rejected','actual_post_retry_open_and_headers_admitted'):assert accepted[n]
        elif label=='retained_shutdown':
            assert inputs['sim/cocotb/'+test]==retained['fixture_sha256']
            assert inputs['sim/cocotb/retained_window_witness.py']==retained['witness_sha256']
            expected=[dict(service=kind,phase=p,memory_commands=p+1,reset_processed=kind=='directory')
                for kind,count in (('directory',9),('window',14),('peer',18)) for p in range(count)]
            assert accepted['actual_raw_fault_cases']==expected and accepted['actual_memory_error']==0x75
            assert accepted['retained_window_arena_warm_reset_verified']
            assert accepted['fresh_disjoint_window_arena_per_global_reset'] is False
            assert accepted['global_resets_only_after_actual_owners_drained'] and accepted['successful_reset_after_explicit_root_reinitialization']
            trace=read('window_trace.json')
            requests=[a for a in trace if a['event']=='actual_admission_window_request' and a['op']==1]
            assert len(requests)==42
            assert all((a['generation'],a['record_address'],a['window_address'],a['retained_window_hex'])==
                (1,7232000,0x7f0000,'00'*16) for a in requests)
            assert all(a['status']==0 for a in trace if a['event']=='actual_admission_window_result')
        else:
            assert inputs['sim/cocotb/'+test]==manifests['drain/generation.json']['fixture_sha256']
            assert inputs['sim/cocotb/window_format_witness.py']==manifests['drain/generation.json']['witness_sha256']
            assert accepted['actual_captured_dma_ids']==[15339,1917] and accepted['actual_gpu_token']==15339
            order=accepted['actual_ordering']
            assert [e['event'] for e in order]==['actual_gpu_result_ack','actual_format_request_ack']
            assert order[0]['clock']<order[1]['clock'] and accepted['held_wire_cycles']==17
            assert accepted['actual_native_response_hex']=='00000000088a010568656c6c6f'
            assert accepted['actual_format_waited_for_offered_wire_and_gpu_lease'] and accepted['actual_format_completed_without_reset']
        if 'actual_format_transactions' in accepted:
            for r in accepted['actual_format_transactions']:
                assert r['held_public_cycles']>=13
                for key in ('26','22'):
                    assert len(r['acks'][key])==len(r['commands'][key])
                    for index,(command,ack) in enumerate(zip(r['commands'][key],r['acks'][key])):
                        assert command['write']==1 and command['bytes']==8 and command['data']==0
                        assert command['address']==r['bases'][key]+8*index
                        assert command['clock']<ack['ack_clock']<r['first_offer_clock']<=r['result_ack_clock']
                if r['result'][0]==0:
                    assert [(e['client'],e['op']) for e in r['requests']]==[(26,11),(22,12)]
                    assert len(r['acks']['26'])==12 and len(r['acks']['22'])==6
                if r['acks']['22']:assert r['acks']['26'][-1]['ack_clock']<r['acks']['22'][0]['clock']
        executions[label]=dict(snapshot=name,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    changed=sorted(n for n,h in parser_hashes.items() if h!=parent['executed_parser_sha256'][n])
    assert changed==['http2_enveloped_frame_grants','http2_enveloped_parser_core','http2_owned_pipelined_cancel_windows',
        'http2_pipelined_cancel_window_store','rpc_grpc_http2_return']
    assert tokenizer_hashes==parent['executed_tokenizer_sha256']
    current=(folder/'rtl/http2_enveloped_parser_core.v').read_text()
    previous=(root/'build/experiments/receive-format/rtl/http2_enveloped_parser_core.v').read_text()
    assert current[:header_end(current,'http2_enveloped_parser_core')]==previous[:header_end(previous,'http2_enveloped_parser_core')]
    replay=root/'build/validation/window-format-generation-replay'
    paths=set(generation['input_sha256'])|{'tools/generate_window_format_experiment.py','tools/generate_window_format_cases.py',
        'tools/generate_window_format_drain_case.py','tools/generate_receive_pool_experiment.py','tools/generate_two_fpga_application.py',
        'tools/generate_bidirectional_application.py','sim/cocotb/window_format_witness.py',
        'build/experiments/receive-format/sim/test_raw_shutdown_faults.py','build/experiments/receive-format/drain/test_raw_shutdown_faults.py'}
    for n in paths:
        assert n not in generation['input_sha256'] or sha(source_path(root, n))==generation['input_sha256'][n]
        destination=replay/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, n),destination)
    for generator,manifest_path in (('generate_window_format_experiment.py','generation.json'),
        ('generate_window_format_cases.py','sim/generation.json'),('generate_window_format_drain_case.py','drain/generation.json')):
        assert manifests[manifest_path]['generator_sha256']==sha(root/'tools'/generator)
        subprocess.run([sys.executable,str(replay/'tools'/generator)],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/experiments/window-format'/manifest_path).read_text())==manifests[manifest_path]
    result=dict(phase='actual_global_both_ledger_format_and_retained_shutdown_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,executed_parser_sha256=parser_hashes,executed_tokenizer_sha256=tokenizer_hashes,
        exact_parser_modules=75,exact_tokenizer_modules=22,changed_parser_modules=changed,parent_audit_key=parent['key'],
        actual_receive_format_faults_verified=12,actual_window_format_faults_verified=6,full_41_retained_window_shutdown_faults_verified=True,
        actual_receive_then_send_clear_ack_order_verified=True,explicit_same_scope_retry_without_global_reset_verified=True,
        retained_window_generation_reuse_counterexample_resolved=True,public_core_interface_unchanged=True,
        generator_replay_verified=True,late_cleanup_receive_error_publication_verified=False,
        whole_system_retained_state_recovery_verified=False,current_native_implementation_verified=False,
        formal_induction_verified=False,full_system_complete=False,generation_sha256=sha(folder/'generation.json'),
        verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/window-format-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_window_format_experiment.py',root/'tools/generate_window_format_cases.py',
              root/'tools/generate_window_format_drain_case.py',root/'sim/cocotb/window_format_witness.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/window-format-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=len(executions),format_faults=18,retained_shutdown_faults=41)))


if __name__=='__main__':main()
