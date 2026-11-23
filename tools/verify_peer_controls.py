"""Bind actual peer-state behavior, real raw integration and native component timing."""
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

from verify_two_fpga_application import closure,resources,timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--raw-snapshot');parser.add_argument('--full',action='store_true');args=parser.parse_args()
    args.raw_snapshot=args.raw_snapshot or ('actual_raw_peer_full_initial'if args.full else'actual_raw_peer_controls_faults')
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.raw_snapshot)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={};records={}
    def execution(label,folder,test,top,count):
        archive=root/'build/wsl-reports'/folder;executed=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
        inputs=report.get('input_sha256')or{**report['source_sha256'],**report['fixture_sha256']}
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0
        assert report['acceptance_sha256']==sha(archive/'acceptance.json')
        assert snapshot.get('exit_code',snapshot.get('runner_exit_code'))==0
        for n,h in inputs.items():assert sha(executed/n)==h,n
        if 'execution_report_sha256'in snapshot:assert snapshot['execution_report_sha256']==sha(archive/'report.json')
        xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
        assert len(tests)==1 and tests[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        dag=closure(top,executed);assert len(dag)==count
        active={p.relative_to(executed).as_posix()for p in dag.values()}
        assert all(sha(source_path(root, n))==inputs[n]for n in active),'Active RTL differs from the executed snapshot'
        differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h]
        records[label]=dict(acceptance=accepted,execution_inputs=len(inputs),production_modules=list(dag),current_primary_differences=differences,current_active_rtl_matches=True)
        for n in inputs:files[Path(label)/'execution'/n]=executed/n
        for n in('report.json','snapshot.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path(label)/'reports'/n]=archive/n
        return accepted,executed,inputs
    unit,unit_root,unit_inputs=execution('unit','http2_peer_state_peer_state_exact_retries',
        'durable_peer_parameters_wire_requests_and_all_commit_faults','http2_peer_state',2)
    assert unit['injected_memory_faults']==100 and unit['wire_retired_before_failed_commit']==18
    assert unit['corrupt_record_bindings_quarantined']==6 and unit['negative_configuration_and_authority_commands']==7
    assert all(unit[n]for n in('actual_tx_handshake_tracking','no_pending_count_before_wire','no_ack_of_ack','ordered_settings_ack_tracking',
        'matching_ping_ack_only','unknown_settings_ignored','pending_settings_overflow_no_tx','all_applied_write_errors_quarantined',
        'no_repeat_wire_after_uncertain_commit','fenced_owner_recovery_verified','captured_configuration_poisoned','complete_model_prefix_immutable'))
    joined,joined_root,joined_inputs=execution('controls','http2_peer_controls_real_peer_controls_server_preface',
        'committed_peer_settings_and_acks_use_actual_rtl','http2_peer_controls',7)
    assert joined['injected_peer_memory_faults']==46 and joined['native_frames']==108 and joined['actual_memory_clients']==4
    assert all(joined[n]for n in('actual_notice_controller_verified','notice_fixture_removed','journal_format_initializes_peer_state',
        'server_settings_before_format_result','all_non_window_settings_persisted','settings_and_actual_window_updates_before_ack',
        'partial_and_aborted_settings_do_not_apply','actual_local_settings_and_ping_wire_verified','ordered_settings_ack_tracking',
        'matching_ping_ack_only','invalid_enable_push_propagates_protocol_error','held_cached_load_survives','uncertain_peer_write_suppresses_ack','fenced_format_recovers_both'))
    raw,raw_root,raw_inputs=execution('raw','cocotb_two_fpga_peer_'+args.raw_snapshot,
        'full_raw_dma_returns_with_actual_peer_state_and_server_settings'if args.full else'actual_raw_peer_notices_server_preface_and_fault_recovery',
        'http2_peer_parser_application',62)
    assert raw['parser_memory_clients']==16 and raw['tokenizer_memory_clients']==9
    if args.full:
        assert(raw['packets'],raw['headers'],raw['messages'],raw['token_ids'],raw['response_chunks'],raw['response_bytes'])==(49,21,16,2828,2828,144686)
        assert(raw['connection_initializations'],raw['stream_initializations'],raw['native_settings_ack_frames'],raw['native_server_settings_frames'])==(7,17,16,7)
        assert(raw['peer_commands'],raw['actual_peer_settings_applied'],raw['actual_settings_acknowledgments'])==(49,28,7)
        assert raw['positive_grants']==raw['response_data_frames']==2830 and raw['response_wire_bytes']==184296 and raw['zero_grants']>0
        assert raw['early_gpu_admissions']>0 and raw['mid_packet_gpu_admissions']>0 and raw['response_held_result_cycles']>0
        assert all(raw[n]for n in('actual_dma_ids_returned','model_and_policy_immutable','separate_memory_banks_verified','shared_actual_rpc_directory',
            'raw_control_commit_and_replay_verified','no_fixture_credit_updates','independent_credit_model_verified','durable_debits_before_data_verified',
            'frame_arbitration_verified','no_notice_fixture','actual_peer_memory_commits_before_results','server_settings_before_open_success'))
        assert not raw['complete_http2_transport_verified']and not raw['whole_rpc_gpu_image_lease_verified']and not raw['postcommit_gpu_cancellation_verified']
    else:
        assert raw['raw_packets']==9 and raw['native_frames']==14 and raw['actual_header_bindings']==1 and raw['peer_initialization_and_wire_commit_faults']==6
        assert all(raw[n]for n in('no_notice_fixture','actual_raw_non_window_settings','server_settings_before_open_success','actual_settings_ack_tracking',
            'no_ack_of_ack','partial_settings_and_real_windows','peer_memory_failure_suppresses_ack','raw_closed_before_failed_public_result',
            'explicit_fenced_reopen','complete_model_prefix_immutable','tokenizer_bank_untouched'))
    assert len(closure('tokenizer_fpga_memory_subsystem',raw_root))==22
    if args.full:
        from verify_full_raw_reference_bundle import verify
        records['full_native_reference']=verify(root,root/'build/wsl-reports'/('cocotb_two_fpga_peer_'+args.raw_snapshot),
            raw_root,json.loads((root/'build/wsl-reports'/('cocotb_two_fpga_peer_'+args.raw_snapshot)/'report.json').read_text()),files,'peer')
    # Replay exact frozen generators, including the passive memory harness.
    replay=root/'build/validation/peer-controls-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in joined_inputs:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(joined_root/n,p)
    for n in raw_inputs:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(raw_root/n,p)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    for script,arguments in(('generate_peer_controls.py',[]),('generate_http2_peer_parser.py',[]),('generate_two_fpga_harness.py',['--tokenizer-memory','--peer-parser'])):
        subprocess.run([sys.executable,str(replay/'tools'/script),*arguments],check=True,capture_output=True,text=True)
    regenerated=['rtl/http2_peer_controls.v','rtl/http2_peer_parser_transport.v','rtl/http2_peer_parser_core.v',
        'rtl/http2_peer_parser_application.v','sim/cocotb_peer_controls_top.sv','sim/cocotb_two_fpga_peer_top.sv']
    # The component fixture is not needed by the raw simulator; copy its exact
    # archived source when it is absent from the raw runner's execution set.
    for n in regenerated:
        expected=raw_root/n if(raw_root/n).is_file()else joined_root/n
        assert sha(replay/n)==sha(expected),n
    assert not any(n.startswith('notice_')for _,_,n in __import__('generate_bidirectional_application').ports(
        (raw_root/'rtl/http2_peer_parser_application.v').read_text(),'http2_peer_parser_application'))
    core=(raw_root/'rtl/http2_peer_parser_core.v').read_text()
    assert '.mem_valid(mem_valid[23*1+:2*1])'in core and '.peer_cmd_req_valid(0)'in core
    assert 'external_memory_fabric #(.CLIENTS(16)) p_fabric('in(raw_root/'sim/cocotb_two_fpga_peer_top.sv').read_text()
    def native(label,top,run,inputs,required):
        folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/run
        if not(folder/'routed_timing.rpt').is_file():
            assert not required;return dict(phase='route_not_yet_verified',run=run)
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        dag=closure(top,frozen)
        for p in dag.values():
            n=p.relative_to(frozen).as_posix();assert sha(p)==inputs[n]==sha(source_path(root, n))
        log=source_path(root, f'build/{run}-implementation.log');assert f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART=xcsu35p-sbvb625-2-e'in log.read_text()
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        clocks=timing(folder/'routed_timing.rpt');area=resources(folder/'routed_utilization.rpt')
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        if required:assert met
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/label/n]=folder/n
        files[Path('native')/label/'implementation.log']=log
        for n in provenance['files']:
            if n in {p.relative_to(frozen).as_posix()for p in dag.values()}or not n.startswith('rtl/'):files[Path('native')/label/'sources'/n]=frozen/n
        return dict(phase='native_route_verified',run=run,resources=area,timing=clocks,timing_met=met,exact_modules=len(dag),
            routed_checkpoint_sha256=sha(folder/'routed.dcp'),registered_neighbors=True,package_paths_excluded=True)
    records['unit_native']=native('unit','http2_peer_state','http2_peer_state_scu35_verilog',unit_inputs,True)
    records['controls_native']=native('controls','http2_peer_controls','http2_peer_controls_scu35_initial',joined_inputs,False)
    files[Path('verification/verify_peer_controls.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/peer-controls-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_peer_full_data_execution_verified'if args.full else'actual_peer_state_and_raw_integration_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        **records,exact_generators_and_harnesses_regenerated=True,no_notice_fixture_in_raw_top=True,
        response_hpack_encoder_consumers_verified=False,cancellation_and_classification_verified=False,
        postcommit_gpu_cancellation_verified=False,full_data_execution_verified=args.full,full_parser_native_timing_verified=False,
        physical_interfaces_verified=False,full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation'/('peer-parser-full.json'if args.full else'peer-controls.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
