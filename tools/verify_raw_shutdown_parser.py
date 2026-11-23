"""Bind raw RST/GOAWAY execution to the actual 66-module Parser and its owners."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from generate_bidirectional_application import ports
from verify_two_fpga_application import closure,resources,timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directed',default='actual_raw_shutdown_native_reset_references')
    parser.add_argument('--faults',help='Also require the complete raw shutdown memory-fault matrix')
    parser.add_argument('--full-snapshot')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',n)for n in(vars(args).values())if n)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={};records={}

    def execution(label,name,test):
        archive=root/'build/wsl-reports'/('cocotb_two_fpga_shutdown_'+name);executed=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
        snapshot=json.loads((archive/'snapshot.json').read_text());inputs={**report['source_sha256'],**report['fixture_sha256']}
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0
        assert report['acceptance_sha256']==sha(archive/'acceptance.json')
        assert snapshot['runner_exit_code']==0 and snapshot['execution_report_sha256']==sha(archive/'report.json')
        runner=executed/'scripts/run_cocotb_snapshot.py'
        assert sha(runner)==snapshot['snapshot_runner_sha256']==snapshot['source_and_fixture_sha256']['scripts/run_cocotb_snapshot.py']
        files[Path(label)/'execution/scripts/run_cocotb_snapshot.py']=runner
        for n,h in inputs.items():
            assert sha(executed/n)==snapshot['source_and_fixture_sha256'][n]==h,n
            files[Path(label)/'execution'/n]=executed/n
        xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
        assert len(cases)==1 and cases[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        parser_dag=closure('http2_shutdown_parser_application',executed)
        tokenizer_dag=closure('tokenizer_fpga_memory_subsystem',executed)
        assert(len(parser_dag),len(tokenizer_dag))==(66,22)
        assert {'http2_stream_shutdown','rpc_grpc_cancellable_return','http2_shutdown_peer_state',
            'http2_missing_stream_classifier','axis_cancellable_frame_arbiter'}<=parser_dag.keys()
        assert 'detokenizer_engine'not in parser_dag and 'detokenizer_engine'in tokenizer_dag
        for path in[*parser_dag.values(),*tokenizer_dag.values()]:
            n=path.relative_to(executed).as_posix();assert sha(source_path(root, n))==inputs[n],'Active RTL differs: '+n
        public=ports((executed/'rtl/http2_shutdown_parser_application.v').read_text(),'http2_shutdown_parser_application')
        assert {n:d for d,_,n in public if n in('cancel_ready','cancel_result_valid','cancel_status')}=={
            'cancel_ready':'output','cancel_result_valid':'output','cancel_status':'output'}
        harness=(executed/'sim/cocotb_two_fpga_shutdown_top.sv').read_text()
        assert 'external_memory_fabric #(.CLIENTS(17)) p_fabric('in harness
        assert 'tokenizer_fpga_memory_subsystem #'in harness
        assert 'external_memory_fabric #(.CLIENTS(9),'in(executed/'rtl/tokenizer_fpga_memory_subsystem.v').read_text()
        core=(executed/'rtl/http2_shutdown_parser_core.v').read_text()
        assert 'else if(window_req_valid&&!shutdown_recovery_required)window_owner<=3;'in core
        assert 'http2_stream_shutdown #'in core and 'axis_frame_arbiter #'not in core
        assert 'assign shutdown_close_rsp_valid=window_owner==8&&service_window_rsp_valid;'in core
        assert 'return_ack_seen&&!response_record_lease_active&&!response_result_retirement_pending'in core
        records[label]=dict(acceptance=accepted,execution_inputs=len(inputs),parser_modules=list(parser_dag),
            tokenizer_modules=list(tokenizer_dag),current_active_rtl_matches=True,
            current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h])
        for n in('report.json','snapshot.json','acceptance.json','simulation.log','build.log','results.xml'):
            files[Path(label)/'reports'/n]=archive/n
        return archive,executed,report,accepted

    archive,source,report,directed=execution('directed',args.directed,'raw_reset_and_goaway_use_actual_owned_services')
    assert tuple(directed[n]for n in('actual_raw_packets','actual_header_bindings','actual_resets','actual_goaways','native_wire_frames'))==(18,5,5,3,8)
    for n in('prelookup_gpu_reset_without_inverse_or_progress','parked_cached_load_reset_without_quarantine',
        'gpu_ack_buffered_until_actual_window_retirement','actual_directory_close_after_return_retirement',
        'duplicate_reset_uses_actual_history','idle_reset_protocol_error','actual_peer_goaway_persisted',
        'client_rpc_continues_after_incoming_goaway','no_data_after_actual_reset_processing',
        'positive_actual_wire_promise_drained_before_reset_processing','actual_first_beat_stall_and_frame_gap',
        'both_debit_acks_and_all_progress_acks_before_data','repeated_goaway_never_expands_retry_boundary',
        'reset_callbacks_supplied_by_rtl','complete_model_prefix_immutable',
        'native_h2_open_and_duplicate_reset_references_verified','native_goaway_wire_references_verified',
        'idle_reset_follows_rfc_9113_6_4','native_h2_idle_reset_divergence_recorded'):assert directed[n],n
    acceptances=[directed]
    if args.faults:
        _,_,_,faults=execution('faults',args.faults,'raw_shutdown_memory_failures_preserve_quarantine_and_ownership')
        assert(faults['window_close_faults'],faults['directory_close_faults'],faults['peer_goaway_faults'])==(14,9,18)
        expected=[(kind,phase)for kind,count in(('directory',9),('window',14),('peer',18))for phase in range(count)]
        assert [(c['service'],c['phase'])for c in faults['actual_raw_fault_cases']]==expected
        assert all(c['memory_commands']==c['phase']+1 and c['reset_processed']==(c['service']=='directory')for c in faults['actual_raw_fault_cases'])
        for n in('applied_write_errors','new_admission_fenced_until_global_reset','global_resets_only_after_actual_owners_drained',
            'successful_reset_after_explicit_root_reinitialization','fresh_disjoint_window_arena_per_global_reset',
            'complete_model_prefix_immutable'):assert faults[n],n
        assert not faults['retained_window_arena_warm_reset_verified']
        assert faults['actual_memory_error']==0x75;acceptances.append(faults)
    for accepted in acceptances:
        assert not any(accepted[n]for n in('whole_rpc_gpu_image_lease_verified','physical_dma_packet_drain_verified','full_system_complete'))

    # Recreate the exact derived production modules, passive two-FPGA harness,
    # and native references from the executed source/fixture bytes.
    replay=root/'build/validation/shutdown-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in {**report['source_sha256'],**report['fixture_sha256']}:
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,target)
    shutil.copytree(root/'build/tiktoken-cache',replay/'build/tiktoken-cache',dirs_exist_ok=True)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    for generator,arguments in(('generate_http2_shutdown_controls.py',[]),('generate_http2_shutdown_parser.py',[]),
        ('generate_two_fpga_harness.py',['--shutdown-parser','--tokenizer-memory']),('generate_shutdown_vectors.py',[])):
        subprocess.run([sys.executable,str(replay/'tools'/generator),*arguments],check=True,capture_output=True,text=True)
    generated=['rtl/'+n+'.v'for n in('http2_shutdown_peer_state','http2_shutdown_control_executor',
        'http2_shutdown_journaled_controls','http2_shutdown_peer_controls','http2_shutdown_classified_controls',
        'http2_shutdown_parser_core','http2_shutdown_parser_application')]
    generated+=['sim/cocotb_two_fpga_shutdown_top.sv','build/http2-shutdown-fixtures/cases.json']
    for n in generated:assert sha(replay/n)==sha(source/n)==sha(source_path(root, n)),n
    native=json.loads((source/'build/http2-shutdown-fixtures/cases.json').read_text())
    assert native['phase']=='native_shutdown_references_passed'and native['token']==58040
    assert(native['grant'],native['packet_bytes'],native['record_bytes'])==(100,166,171)
    assert native['generator_sha256']==sha(source/'tools/generate_shutdown_vectors.py')
    assert [(c['native_http2_error'],c['rfc_http2_error'])for c in native['reset_cases']]==[(0,0),(0,0),(0,1),(0,0),(0,1)]
    fixture=source/'build/bidirectional-fixtures';layout=list(map(int,(fixture/'layout.txt').read_text().split()))
    loaded=b''.join(int(s,16).to_bytes(8,'little')for s in(fixture/'memory.mem').read_text().splitlines())
    original=root/'build/scu35/image/external_memory.bin'
    assert sha(original)=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    assert loaded[:layout[6]]==original.read_bytes()[:layout[6]]
    assert hashlib.sha256(loaded).hexdigest()==native['model_image_sha256']
    files[Path('model/original-image.bin')]=original

    # The existing routed RPC component is still exactly the return instantiated
    # by this Parser. Its 18-module timing is not timing of the whole Parser.
    run=root/'build/implementation/xcsu35p-sbvb625-2-e/rpc_cancel_scu35_registered_pool_end'
    provenance=json.loads((run/'source-provenance.json').read_text());dag=closure('rpc_grpc_cancellable_return',run/'sources')
    assert len(dag)==18
    for path in dag.values():
        n=path.relative_to(run/'sources').as_posix();assert sha(path)==provenance['files'][n]['sha256']==sha(source/n)==sha(source_path(root, n))
        files[Path('rpc-component/sources')/n]=path
    clocks=timing(run/'routed_timing.rpt');assert clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0
    assert clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
    records['rpc_component_native']=dict(exact_modules=18,resources=resources(run/'routed_utilization.rpt'),timing=clocks,
        current_active_rtl_matches=True,whole_parser_timing=False,routed_checkpoint_sha256=sha(run/'routed.dcp'))
    for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt'):
        files[Path('rpc-component')/n]=run/n
    if args.full_snapshot:
        full_archive,full_source,full_report,full=execution('full',args.full_snapshot,'full_raw_requests_and_dma_returns_use_actual_shutdown_join')
        assert tuple(full[n]for n in('packets','headers','messages','token_ids','response_chunks','response_bytes'))==(52,21,16,2828,2828,144686)
        assert full['actual_shutdown_return_joined']and not full['cancellation_supplied_externally']
        assert full['actual_internal_retirement_cycles']>0
        assert full['response_data_frames']==2830 and full['response_wire_bytes']==184296
        assert full['raw_reset_cases_in_this_workload']==full['raw_goaway_cases_in_this_workload']==0
        assert not full['complete_http2_transport_verified']and not full['whole_rpc_gpu_image_lease_verified']
        from verify_full_raw_reference_bundle import verify
        records['full_native_reference']=verify(root,full_archive,full_source,full_report,files,'shutdown')
    files[Path('verification/verify_raw_shutdown_parser.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/raw-shutdown-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_raw_shutdown_lifecycle_verified'if args.faults else'actual_raw_shutdown_directed_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        **records,exact_generation_and_native_reference_replay=True,actual_raw_rst_controller_integrated=True,
        parser_memory_clients=17,tokenizer_memory_clients=9,complete_original_model_prefix_verified=True,
        complete_raw_shutdown_memory_fault_matrix_verified=bool(args.faults),full_data_workload_verified=bool(args.full_snapshot),response_headers_and_trailers_verified=False,
        receive_flow_control_verified=False,whole_rpc_gpu_image_lease_verified=False,physical_dma_packet_drain_verified=False,
        retained_window_arena_warm_reset_verified=False,recovery_requires_fresh_window_arena=True,
        full_parser_native_timing_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/raw-shutdown-parser.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','evidence_folder','full_data_workload_verified','full_system_complete')},indent=2))


if __name__=='__main__':main()
