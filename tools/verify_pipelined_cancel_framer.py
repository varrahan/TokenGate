"""Audit registered byte/grant stages against native framing and owned cancellation."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure,resources,timing

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={};records={}
    def execution(label,name,test,top,count):
        archive=root/'build/wsl-reports'/name;executed=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
        snapshot=json.loads((archive/'snapshot.json').read_text());inputs=json.loads((archive/'inputs.json').read_text())
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():assert sha(executed/n)==h,n
        xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
        assert len(cases)==1 and cases[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        dag=closure(top,executed);assert len(dag)==count
        for p in dag.values():
            n=p.relative_to(executed).as_posix();assert sha(source_path(root, n))==inputs[n],'Active RTL differs: '+n
        records[label]=dict(acceptance=accepted,execution_inputs=len(inputs),production_modules=list(dag),current_active_rtl_matches=True,
            current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h])
        for n in inputs:files[Path(label)/'execution'/n]=executed/n
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path(label)/'reports'/n]=archive/n
        return accepted,executed,inputs
    framed,framed_root,framed_inputs=execution('framer','grpc_registered_framer_actual_registered_input_native_initial',
        'records_frames_credit_and_transactional_rejection','grpc_registered_input_framer',4)
    assert(framed['cases'],framed['valid_cases'],framed['rejected_cases'],framed['frames'])==(42,33,9,84)
    fixture=json.loads((framed_root/'build/grpc-response-frame-fixtures/cases.json').read_text())
    assert fixture['phase']=='native_references_passed'and fixture['native_oracle']=='hyperframe'and fixture['native_version']=='6.1.0'
    assert fixture['capacity']==65535 and fixture['generator_sha256']==framed_inputs['tools/generate_grpc_response_frame_vectors.py']
    assert framed['native_reference_sha256']==framed_inputs['build/grpc-response-frame-fixtures/cases.json']
    assert all(framed[n]>0 for n in('input_stalls','output_stalls','credit_stalls','result_stalls'))
    windows,window_root,window_inputs=execution('windows','http2_pipelined_windows_actual_registered_grant_native_faults',
        'actual_key_close_binding_cached_lease_and_every_memory_fault','http2_owned_pipelined_cancel_windows',5)
    assert windows['window_commands']==176 and windows['native_window_commands']==28 and windows['legacy_native_reference_matrix_verified']
    assert windows['key_close_memory_phases']==windows['injected_close_memory_faults']==22 and windows['applied_close_with_failed_ack']==1
    assert all(windows[n]for n in('actual_directory_and_pool_verified','resolved_binding_after_durable_close','foreign_same_stream_untouched',
        'cached_load_survives_key_close','pool_held_through_close_result','no_credit_refund','duplicate_close_idempotent','closed_reserve_has_no_grant',
        'late_closed_update_ignored','missing_key_neutral','real_generation_reuse_verified','caller_binding_metadata_rejected',
        'failed_close_never_publishes_binding','quarantined_exact_retry_has_no_memory','model_prefix_immutable'))
    joined,joined_root,joined_inputs=execution('joined','grpc_pipelined_fenced_actual_registered_grant_wire_drain',
        'actual_reserved_data_drains_before_key_close_and_cached_retirement','grpc_cancellable_pipelined_framer',12)
    assert(joined['reserved_memory_phases'],joined['cancelled_scenarios'],joined['wire_boundary_scenarios'])==(15,22,5)
    assert(joined['uncertain_debit_ack_faults'],joined['native_frames'],joined['data_frames'],joined['completed_message_result_races'])==(2,46,23,1)
    assert joined['controls_while_data_frozen']==23 and joined['wire_stalls']>0
    assert all(joined[n]for n in('completed_wire_success_not_retracted','same_edge_freeze_blocks_dispatch','actual_parked_sender_cancelled',
        'positive_reservation_drained_to_actual_wire','all_dispatched_memory_phases_frozen','stalled_wire_promises_preserved',
        'actual_key_close_waits_for_wire','actual_cached_load_held_through_terminal_result','both_debit_acks_precede_every_positive_grant',
        'no_credit_refund','nonmatching_stream_continues','uncertain_debits_never_grant_or_publish_close','model_prefix_immutable'))
    assert not any(joined[n]for n in('actual_rpc_return_integrated','actual_rst_controller_integrated','gpu_image_lease_cancellation_verified','full_system_complete'))
    for n in('rtl/grpc_registered_input_framer.v','rtl/axis_byte_unpacker.v','rtl/axis_byte_packer.v','rtl/axis_skid_buffer.v'):
        assert joined_inputs[n]==framed_inputs[n]
    for n in('rtl/http2_pipelined_cancel_window_store.v','rtl/http2_owned_pipelined_cancel_windows.v'):
        assert joined_inputs[n]==window_inputs[n]
    replay=root/'build/validation/pipelined-cancel-framer-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in joined_inputs:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(joined_root/n,p)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    for script,extra in(('generate_cancel_send_windows.py',[]),('generate_cancellable_frame_arbiter.py',[]),('generate_fenced_frame_grants.py',[]),
        ('generate_registered_input_framer.py',[]),('generate_pipelined_cancel_framer.py',[]),
        ('generate_grpc_response_frame_vectors.py',['--output',str(replay/'build/grpc-response-frame-fixtures')])):
        subprocess.run([sys.executable,str(replay/'tools'/script),*extra],check=True,capture_output=True,text=True)
    generated=('rtl/http2_cancel_send_window_store.v','rtl/http2_owned_cancel_windows.v','rtl/http2_cancel_frame_grants.v',
        'rtl/axis_cancellable_frame_arbiter.v','rtl/http2_fenced_frame_grants.v','rtl/grpc_cancellable_window_framer.v',
        'rtl/grpc_registered_input_framer.v','rtl/grpc_cancellable_registered_framer.v','rtl/http2_pipelined_cancel_window_store.v',
        'rtl/http2_owned_pipelined_cancel_windows.v','rtl/http2_fenced_pipelined_grants.v','rtl/grpc_cancellable_pipelined_framer.v',
        'build/grpc-response-frame-fixtures/cases.json')
    for n in generated:assert sha(replay/n)==joined_inputs[n],n
    framer=(joined_root/'rtl/grpc_registered_input_framer.v').read_text()
    assert 'axis_skid_buffer #(.DATA_WIDTH(8),.KEEP_WIDTH(1),.USER_WIDTH(USER_WIDTH+1)) input_stage('in framer
    assert '.s_axis_tuser(unpacked_user)'in framer and '.m_axis_tuser(input_user)'in framer
    engine=(joined_root/'rtl/http2_pipelined_cancel_window_store.v').read_text()
    assert 'selected_grant<=grant_limit;state<=RESERVE_APPLY;'in engine
    assert 'window_record[95:64]-selected_grant'in engine and 'connection_record[95:64]-selected_grant'in engine
    assert '.req_authority(directory_pool_lock_active)'in(joined_root/'rtl/http2_owned_pipelined_cancel_windows.v').read_text()
    parent=(joined_root/'rtl/grpc_cancellable_pipelined_framer.v').read_text()
    assert '.frame_tx_done(data_tvalid&&data_tready&&data_tlast)'in parent and '.a_pause(freeze_binding_valid&&freeze_drained)'in parent
    assert '.rst(rst||'not in parent
    run='grpc_pipelined_framer_scu35_initial';folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/run;log=source_path(root, f'build/{run}-implementation.log')
    marker='REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=grpc_cancellable_pipelined_framer PART=xcsu35p-sbvb625-2-e'
    native=dict(phase='route_not_yet_verified',run=run)
    if log.is_file()and marker in log.read_text():
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        dag=closure('grpc_cancellable_pipelined_framer',frozen);assert len(dag)==12
        active={p.relative_to(frozen).as_posix()for p in dag.values()}
        for n in active:assert sha(frozen/n)==joined_inputs[n]==sha(source_path(root, n))
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        clocks=timing(folder/'routed_timing.rpt');area=resources(folder/'routed_utilization.rpt')
        assert area['luts']<=16320 and area['registers']<=32640 and area['bram36']+area['bram18']/2<=48 and area['uram']==0
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        native=dict(phase='native_route_verified',run=run,exact_modules=12,resources=area,timing=clocks,timing_met=met,
            registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','route_status.rpt','routed_drc.rpt'):files[Path('native')/n]=folder/n
        files[Path('native/implementation.log')]=log
        for n in provenance['files']:
            if n in active or not n.startswith('rtl/'):files[Path('native/sources')/n]=frozen/n
    files[Path('verification/verify_pipelined_cancel_framer.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/pipelined-cancel-framer-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='registered_byte_and_grant_stages_verified',verified_utc=datetime.now(timezone.utc).isoformat(),**records,native=native,
        exact_generation_and_native_reference_replay=True,single_actual_directory_verified=True,complete_model_prefix_immutable=True,
        actual_rpc_return_integrated=False,actual_rst_controller_integrated=False,gpu_image_lease_cancellation_verified=False,
        full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/pipelined-cancel-framer.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
