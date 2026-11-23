"""Bind actual keyed send closure and parked-grant wakeup to frozen evidence."""
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
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={};results={}
    def execution(label,folder,test,top,count):
        archive=root/'build/wsl-reports'/folder;executed=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text());inputs=json.loads((archive/'inputs.json').read_text())
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():assert sha(executed/n)==h,n
        xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
        assert len(tests)==1 and tests[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        dag=closure(top,executed);assert len(dag)==count
        for p in dag.values():
            n=p.relative_to(executed).as_posix();assert sha(p)==inputs[n]==sha(source_path(root, n)),'Active RTL differs: '+n
        differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h]
        results[label]=dict(acceptance=accepted,execution_inputs=len(inputs),production_modules=list(dag),current_active_rtl_matches=True,current_primary_differences=differences)
        for n in inputs:files[Path(label)/'execution'/n]=executed/n
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path(label)/'reports'/n]=archive/n
        return accepted,executed,inputs
    unit,unit_root,unit_inputs=execution('windows','http2_cancel_windows_actual_key_close_native_and_faults',
        'actual_key_close_binding_cached_lease_and_every_memory_fault','http2_owned_cancel_windows',5)
    assert unit['native_window_commands']==28 and unit['native_keyed_updates']>0 and unit['legacy_native_reference_matrix_verified']
    assert unit['key_close_memory_phases']==unit['injected_close_memory_faults']==22 and unit['applied_close_with_failed_ack']==1
    assert unit['no_memory_binding_negatives']==4
    assert all(unit[k]for k in('actual_directory_and_pool_verified','resolved_binding_after_durable_close','foreign_same_stream_untouched',
        'cached_load_survives_key_close','pool_held_through_close_result','no_credit_refund','duplicate_close_idempotent','closed_reserve_has_no_grant',
        'late_closed_update_ignored','missing_key_neutral','real_generation_reuse_verified','caller_binding_metadata_rejected',
        'failed_close_never_publishes_binding','quarantined_exact_retry_has_no_memory','model_prefix_immutable'))
    grant,grant_root,grant_inputs=execution('grants','http2_cancel_grants_actual_parked_key_close_bound_sources',
        'actual_key_close_wakes_parked_sender_and_preserves_cached_load','http2_cancel_frame_grants',6)
    assert all(grant[k]for k in('key_close_wakes_actual_parked_scheduler','actual_cached_load_held_until_finish','closed_reservation_no_positive_grant',
        'typed_stream_closed_error_verified','error_and_result_backpressure_verified','actual_pool_lock_and_memory_verified','model_prefix_immutable'))
    assert not grant['actual_rpc_return_integrated']and not grant['actual_rst_controller_integrated']and not grant['inflight_wire_frame_drain_verified']
    wire,wire_root,wire_inputs=execution('wire','axis_cancellable_arbiter_actual_wire_data_fence_initial',
        'actual_wire_data_fence_preserves_promised_frames_and_control_acks','axis_cancellable_frame_arbiter',1)
    assert wire['native_frames']==wire['frames']==70 and wire['sustained_beats']==32 and wire['private_unoffered_frame_aborted']==1
    assert wire['random_pause_sequences']==8 and wire['paused_control_frames']>0 and wire['wire_handshake_checks']>0
    assert all(wire[k]for k in('stalled_first_wire_beat_preserved','inflight_data_frame_drains_across_gaps',
        'controls_continue_while_data_paused','paused_source_abort_does_not_reset_control_owner','no_new_wire_data_after_fence','input_acceptance_is_actual_wire_retirement'))
    replay=root/'build/validation/cancel-send-windows-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in unit_inputs:
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(unit_root/n,target)
    for n in wire_inputs:
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(wire_root/n,target)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(replay/'tools/generate_cancel_send_windows.py')],check=True,capture_output=True,text=True)
    for n in('rtl/http2_cancel_send_window_store.v','rtl/http2_owned_cancel_windows.v','rtl/http2_cancel_frame_grants.v'):
        assert sha(replay/n)==unit_inputs[n]==grant_inputs[n],n
    subprocess.run([sys.executable,str(replay/'tools/generate_cancellable_frame_arbiter.py')],check=True,capture_output=True,text=True)
    assert sha(replay/'rtl/axis_cancellable_frame_arbiter.v')==wire_inputs['rtl/axis_cancellable_frame_arbiter.v']
    owned=(unit_root/'rtl/http2_owned_cancel_windows.v').read_text();engine=(unit_root/'rtl/http2_cancel_send_window_store.v').read_text()
    assert '.req_authority(directory_pool_lock_active)'in owned
    assert 'wire searching=(op==WINDOW_UPDATE_KEY||op==CLOSE_SEND_KEY)&&stream_id!=0;'in engine
    assert 'assign rsp_binding_valid=rsp_valid&&rsp_status==0&&(op==CLOSE_SEND||op==CLOSE_SEND_KEY);'in engine
    grant_rtl=(grant_root/'rtl/http2_cancel_frame_grants.v').read_text()
    assert 'owned_window_rsp_op==9||owned_window_rsp_op==10)'in grant_rtl
    assert '.lease_rsp_ready(lease_rsp_ready&&(!frame_active||finish_valid)&&!start_valid&&finish_ready)'in grant_rtl
    run='http2_key_close_scu35_initial';folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/run
    if 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=http2_owned_cancel_windows PART=xcsu35p-sbvb625-2-e'in(source_path(root, f'build/{run}-implementation.log')).read_text():
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        dag=closure('http2_owned_cancel_windows',frozen);assert len(dag)==5
        active={p.relative_to(frozen).as_posix()for p in dag.values()}
        for n in active:assert sha(frozen/n)==unit_inputs[n]==sha(source_path(root, n))
        log=source_path(root, f'build/{run}-implementation.log');assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=http2_owned_cancel_windows PART=xcsu35p-sbvb625-2-e'in log.read_text()
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        clocks=timing(folder/'routed_timing.rpt');area=resources(folder/'routed_utilization.rpt')
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        results['native']=dict(phase='native_route_verified',run=run,resources=area,timing=clocks,timing_met=met,exact_modules=5,
            registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/n]=folder/n
        files[Path('native/implementation.log')]=log
        for n in provenance['files']:
            if n in active or not n.startswith('rtl/'):files[Path('native/sources')/n]=frozen/n
    else:results['native']=dict(phase='route_not_yet_verified',run=run)
    wire_run='axis_cancellable_arbiter_scu35_initial';wire_folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/wire_run
    wire_log=source_path(root, f'build/{wire_run}-implementation.log')
    if wire_log.is_file()and 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=axis_cancellable_frame_arbiter PART=xcsu35p-sbvb625-2-e'in wire_log.read_text():
        frozen=wire_folder/'sources';provenance=json.loads((wire_folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        name='rtl/axis_cancellable_frame_arbiter.v';assert sha(frozen/name)==wire_inputs[name]==sha(source_path(root, name))
        clocks=timing(wire_folder/'routed_timing.rpt');area=resources(wire_folder/'routed_utilization.rpt')
        assert area['registers']==3 and area['bram36']==area['bram18']==area['uram']==area['dsps']==0
        assert clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(wire_folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(wire_folder/'routed_drc.rpt').read_text(),re.M)
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('wire-native')/n]=wire_folder/n
        files[Path('wire-native/implementation.log')]=wire_log
        for n in provenance['files']:
            if n==name or not n.startswith('rtl/'):files[Path('wire-native/sources')/n]=frozen/n
        results['wire_native']=dict(phase='native_route_verified',run=wire_run,resources=area,timing=clocks,timing_met=True,exact_modules=1,
            registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(wire_folder/'routed.dcp'))
    else:results['wire_native']=dict(phase='route_not_yet_verified',run=wire_run)
    files[Path('verification/verify_cancel_send_windows.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16];evidence=root/'build/validation/cancel-send-windows-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_key_close_parked_scheduler_and_wire_fence_verified',verified_utc=datetime.now(timezone.utc).isoformat(),**results,
        generation_replay_exact=True,single_actual_directory_verified=True,resolved_binding_after_durable_commit=True,
        actual_wire_fence_component_verified=True,actual_rpc_return_integrated=False,actual_rst_controller_integrated=False,inflight_wire_frame_drain_verified=False,
        image_lease_cancellation_verified=False,full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/cancel-send-windows.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
