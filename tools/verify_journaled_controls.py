"""Audit committed effects, real pool-owned windows and native ACK retirement."""
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

from hyperframe.frame import SettingsFrame,PingFrame
from verify_two_fpga_application import closure,resources,timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-name',default='committed_controls_actual_windows_faults')
    parser.add_argument('--native-run',default='http2_journaled_controls_scu35_initial')
    parser.add_argument('--functional-only',action='store_true');args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',s)for s in(args.snapshot_name,args.native_run))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports'/('http2_journaled_controls_'+args.snapshot_name);executed=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    inputs=json.loads((archive/'inputs.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and snapshot['exit_code']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert report['tests']==1 and report['failures']==0
    for name,digest in inputs.items():assert sha(executed/name)==digest,name
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='committed_controls_actual_window_updates_and_native_ack_frames'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert accepted['native_ack_frames']==3 and accepted['peer_ack_callbacks']==2 and accepted['held_tx_cycles']>0
    assert all(accepted[k]for k in('actual_directory_and_window_engine_verified','partial_settings_do_not_apply',
        'settings_applied_before_ack','actual_stream_and_connection_updates','aborted_packet_no_update',
        'unknown_settings_ignored','held_cached_lease_survives_controls','actual_rst_directory_close',
        'goaway_callback_verified','missing_key_classification_callback','uncertain_window_write_quarantines_both',
        'retry_does_not_duplicate_increment','explicit_recovery_verified','ack_retired_before_failed_head_commit',
        'head_failure_does_not_duplicate_ack','missing_idle_is_connection_error','notice_failure_suppresses_ack',
        'uncertain_cancel_callback_quarantined','complete_model_prefix_immutable','non_window_callbacks_supplied_by_fixture'))
    assert not accepted['raw_parser_integrated']and not accepted['full_system_complete']
    production=closure('http2_journaled_controls',executed)
    service=closure('http2_owned_keyed_windows',executed)
    assert set(production)=={'http2_control_executor','http2_control_journal','http2_journaled_controls','memory_command_slot'}
    assert set(service)=={'http2_owned_keyed_windows','http2_keyed_send_window_store','grpc_pool_locked_stream_store','grpc_stream_store','memory_command_slot'}
    assert len(set(production)|set(service))==8 and 'grpc_stream_store'not in production
    harness=(executed/'sim/cocotb_journaled_controls_top.sv').read_text()
    assert len(re.findall(r'http2_owned_keyed_windows\s*#',harness))==1
    assert 'assign exec_window_rsp_valid=window_owner==2&&service_window_rsp_valid;'in harness
    wrapper=(executed/'rtl/http2_journaled_controls.v').read_text()
    assert '.consume_status(j_consume_status)'in wrapper and '.s_status(j_consume_status)'in wrapper
    assert '.finish_abort(j_result_status!=0)'in wrapper
    assert 'assign result_valid=j_result_valid&&(formatting||e_result_valid);'in wrapper
    actor=(executed/'rtl/http2_control_executor.v').read_text()
    assert 'assign s_ready=!rst&&state==ACK;'in actor
    assert 'TX:if(m_axis_tx_tready)begin result_ack_frames<=result_ack_frames+1\'b1;state<=ACK;end'in actor
    assert 'window(9,frame_stream,event_arg0)'in actor and 'window(3,0,event_arg1)'in actor and 'window(4,0,event_arg1)'in actor
    assert 'window_req_op==9&&window_rsp_status==3&&window_rsp_detail==10'in actor
    fixture=executed/'build/http2-send-window-fixtures';reference=json.loads((fixture/'cases.json').read_text())
    assert reference['original_image_sha256']==sha(fixture/'model.bin')==sha(root/'build/scu35/image/external_memory.bin')
    replay_key=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
    replay=root/'build/validation/journaled-control-generation-replay'/replay_key
    if not replay.exists():shutil.copytree(executed,replay)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(replay/'tools/generate_journaled_controls.py')],check=True,capture_output=True)
    for name in('rtl/http2_journaled_controls.v','sim/cocotb_journaled_controls_top.sv'):assert sha(replay/name)==inputs[name],name
    setting=SettingsFrame(0);setting.flags.add('ACK');ping=PingFrame(0);ping.flags.add('ACK');ping.opaque_data=b'journal!'
    native=dict(settings_ack=setting.serialize().hex(),ping_ack=ping.serialize().hex(),
        ack_after_settings_and_wire_retirement_required=True,head_failure_must_not_duplicate_wire_ack=True)
    reference_file=root/'build/validation/journaled-controls-native-acks.json';reference_file.write_text(json.dumps(native,indent=2)+'\n')
    files={Path('execution')/name:executed/name for name in inputs}
    files.update({Path('reports')/name:archive/name for name in('inputs.json','report.json','snapshot.json','results.xml','acceptance.json','simulation.log','build.log')})
    files[Path('verification/native-acks.json')]=reference_file;files[Path('verification/verify_journaled_controls.py')]=Path(__file__)
    result=dict(phase='committed_controls_functional_passed_native_pending',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,execution_inputs=len(inputs),production_modules=list(production),actual_service_modules=list(service),
        actual_fixture_modules=8,production_service_external_verified=True,single_actual_directory_verified=True,
        exact_wrapper_and_harness_regeneration_verified=True,current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h],
        raw_parser_joined=False,non_window_callbacks_supplied_by_fixture=True,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    if not args.functional_only:
        folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run;frozen=folder/'sources'
        provenance=json.loads((folder/'source-provenance.json').read_text())
        for name,record in provenance['files'].items():assert sha(frozen/name)==record['sha256']
        active=closure('http2_journaled_controls',frozen);assert set(active)==set(production)
        for path in active.values():
            relative=path.relative_to(frozen);assert sha(path)==inputs[relative.as_posix()]
            files[Path('native/sources')/relative]=path
        implementation=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in implementation.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        log=source_path(root, f'build/{args.native_run}-implementation.log');text=log.read_text()
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=http2_journaled_controls PART=xcsu35p-sbvb625-2-e'in text
        assert '0 Critical Warnings and 0 Errors encountered.'in text and 'ERROR: [Synth'not in text
        area=resources(folder/'routed_utilization.rpt');clocks=timing(folder/'routed_timing.rpt')
        assert area['luts']<=16320 and area['registers']<=32640 and area['bram36']==area['bram18']==area['uram']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        result.update(phase='committed_controls_functional_and_native_timing_met'if met else'committed_controls_functional_passed_timing_pending',
            native_run=args.native_run,native_exact_rtl_files=4,timing=clocks,resources=area,routed_timing_met=met,
            package_paths_excluded=True,external_window_service_timing_not_included=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        files[Path('native/implementation.log')]=log
        for name in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','route_status.rpt','routed_drc.rpt'):files[Path('native')/name]=folder/name
        for name in provenance['files']:
            if not name.startswith('rtl/'):files[Path('native/sources')/name]=frozen/name
    key=hashlib.sha256(''.join(str(p)+sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/journaled-controls-evidence'/key
    for relative,path in files.items():
        target=evidence/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(path)
        else:shutil.copy2(path,target)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/journaled-controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
