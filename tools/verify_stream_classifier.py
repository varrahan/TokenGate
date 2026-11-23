"""Audit native missing-key decisions, actual admission ownership and routed RTL."""
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
    parser=argparse.ArgumentParser();parser.add_argument('--raw-snapshot');parser.add_argument('--full',action='store_true');args=parser.parse_args()
    args.raw_snapshot=args.raw_snapshot or ('actual_raw_classified_full_initial'if args.full else'actual_raw_history_same_packet')
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.raw_snapshot)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={};results={}
    def execution(label,folder,test,top,count):
        archive=root/'build/wsl-reports'/folder;executed=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
        inputs=report.get('input_sha256')or{**report['source_sha256'],**report['fixture_sha256']}
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0
        assert report['acceptance_sha256']==sha(archive/'acceptance.json')and snapshot.get('exit_code',snapshot.get('runner_exit_code'))==0
        if 'execution_report_sha256'in snapshot:assert snapshot['execution_report_sha256']==sha(archive/'report.json')
        for n,h in inputs.items():assert sha(executed/n)==h,n
        xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
        assert len(tests)==1 and tests[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        dag=closure(top,executed);assert len(dag)==count
        for p in dag.values():
            n=p.relative_to(executed).as_posix();assert sha(p)==inputs[n]==sha(source_path(root, n)),'Active RTL mismatch: '+n
        native=json.loads((executed/'build/http2-classifier-fixtures/cases.json').read_text())
        assert native['phase']=='native_missing_stream_references_passed'and native['generator_sha256']==inputs['tools/generate_missing_stream_vectors.py']
        assert len(native['cases'])==48 and native['packages']=={'h2':'4.4.1','hyperframe':'6.1.0'}
        assert native['actual_headers_and_rst_used']and all(c['closed']==bool(c['stream']&1 and c['stream']<=c['last_stream'])for c in native['cases'])
        differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h]
        results[label]=dict(acceptance=accepted,execution_inputs=len(inputs),production_modules=list(dag),current_active_rtl_matches=True,current_primary_differences=differences)
        for n in inputs:files[Path(label)/'execution'/n]=executed/n
        for n in('report.json','snapshot.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path(label)/'reports'/n]=archive/n
        return accepted,executed,inputs
    unit,unit_root,unit_inputs=execution('unit','http2_classifier_actual_history_classifier_faults',
        'native_missing_key_classification_uses_fenced_actual_history','http2_missing_stream_classifier',2)
    assert(unit['commands'],unit['native_h2_cases'],unit['negative_no_memory_commands'],unit['corrupt_history_and_context_rejections'],unit['injected_memory_faults'],unit['lost_live_fences'])==(69,48,7,8,2,2)
    assert all(unit[k]for k in('actual_context_and_admission_history_read','skipped_and_closed_ids_ignored','idle_and_wrong_parity_ids_distinguished',
        'captured_configuration_poisoned','all_reads_acknowledged_before_result','read_only_no_memory_writes','unaligned_runtime_context_supported','complete_model_prefix_immutable'))
    raw,raw_root,raw_inputs=execution('raw','cocotb_two_fpga_classified_'+args.raw_snapshot,
        'full_raw_dma_returns_and_actual_missing_stream_classification'if args.full else'actual_raw_missing_keys_use_committed_admission_history',
        'http2_classified_parser_application',64)
    assert(raw['parser_memory_clients'],raw['tokenizer_memory_clients'])==(17,9)
    if args.full:
        assert(raw['packets'],raw['headers'],raw['messages'],raw['token_ids'],raw['response_chunks'],raw['response_bytes'])==(52,21,16,2828,2828,144686)
        assert raw['positive_grants']==raw['response_data_frames']==2830 and raw['response_wire_bytes']==184296 and raw['zero_grants']>0
        assert(raw['connection_initializations'],raw['stream_initializations'],raw['native_settings_ack_frames'],raw['native_server_settings_frames'])==(7,17,16,7)
        assert(raw['peer_commands'],raw['actual_peer_settings_applied'],raw['actual_settings_acknowledgments'])==(49,28,7)
        assert raw['closed_stream_probe_packets']==raw['actual_history_results']==3
        assert raw['early_gpu_admissions']>0 and raw['mid_packet_gpu_admissions']>0 and raw['response_held_result_cycles']>0
        assert all(raw[k]for k in('actual_dma_ids_returned','model_and_policy_immutable','shared_actual_rpc_directory','separate_memory_banks_verified',
            'raw_control_commit_and_replay_verified','no_fixture_credit_updates','independent_credit_model_verified','durable_debits_before_data_verified',
            'frame_arbitration_verified','no_notice_fixture','actual_peer_memory_commits_before_results','server_settings_before_open_success',
            'actual_missing_key_classification','no_classification_fixture','actual_packet_admission_fence_verified','read_only_history_before_results'))
        assert not raw['complete_http2_transport_verified']and not raw['whole_rpc_gpu_image_lease_verified']and not raw['postcommit_gpu_cancellation_verified']
    else:
        assert(raw['raw_packets'],raw['actual_header_bindings'],raw['actual_history_queries'],raw['actual_history_reads'],raw['native_control_frames'])==(14,3,8,15,10)
        assert raw['actual_history_fence_cycles']>=210 and raw['injected_history_memory_faults']==2
        assert all(raw[k]for k in('skipped_and_directory_closed_streams_ignored','future_and_even_idle_streams_protocol_error',
            'actual_high_water_written_by_admission','actual_raw_admission_fence_verified','no_classification_or_notice_fixture','native_h2_decisions_verified','same_packet_headers_and_window_update_verified',
            'protocol_error_reaches_transport_result','history_reads_are_read_only','read_failures_never_classified_closed','explicit_fenced_reopen',
            'complete_model_prefix_immutable','tokenizer_bank_untouched'))
    assert len(closure('tokenizer_fpga_memory_subsystem',raw_root))==22
    if args.full:
        from verify_full_raw_reference_bundle import verify
        results['full_native_reference']=verify(root,root/'build/wsl-reports'/('cocotb_two_fpga_classified_'+args.raw_snapshot),
            raw_root,json.loads((root/'build/wsl-reports'/('cocotb_two_fpga_classified_'+args.raw_snapshot)/'report.json').read_text()),files,'classified')
    public=ports((raw_root/'rtl/http2_classified_parser_application.v').read_text(),'http2_classified_parser_application')
    assert not any(n.startswith(('classify_','notice_'))for _,_,n in public)
    transport=(raw_root/'rtl/http2_classified_parser_transport.v').read_text()
    assert 'assign ctl_history_fence=state==CONTROL_FINISH_WAIT&&p_packet_result_valid&&p_packet_committed&&r_idle&&a_idle&&h_idle&&!header_pending&&!router_active&&control_owner==0;'in transport
    assert transport.count('raw_h2<=ctl_result_http2_error!=0?ctl_result_http2_error:32\'d2;')==2
    core=(raw_root/'rtl/http2_classified_parser_core.v').read_text()
    assert '.history_fence(ctl_history_fence)'in core and '.mem_valid(mem_valid[23*1+:3*1])'in core
    assert 'external_memory_fabric #(.CLIENTS(17)) p_fabric('in(raw_root/'sim/cocotb_two_fpga_classified_top.sv').read_text()
    replay=root/'build/validation/stream-classifier-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in raw_inputs:
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(raw_root/n,target)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    for script,extra in(('generate_missing_stream_vectors.py',[]),('generate_classified_peer_controls.py',[]),
        ('generate_http2_classified_parser.py',[]),('generate_two_fpga_harness.py',['--tokenizer-memory','--classified-parser'])):
        subprocess.run([sys.executable,str(replay/'tools'/script),*extra],check=True,capture_output=True,text=True)
    for n in('build/http2-classifier-fixtures/cases.json','rtl/http2_classified_peer_controls.v',
        'rtl/http2_classified_parser_transport.v','rtl/http2_classified_parser_core.v','rtl/http2_classified_parser_application.v','sim/cocotb_two_fpga_classified_top.sv'):
        assert sha(replay/n)==raw_inputs[n],n
    def native(label,top,run,inputs,required):
        folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/run
        if not(folder/'routed_timing.rpt').is_file():assert not required;return dict(phase='route_not_yet_verified',run=run)
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        dag=closure(top,frozen)
        for p in dag.values():
            n=p.relative_to(frozen).as_posix();assert sha(p)==inputs[n]==sha(source_path(root, n))
        log=source_path(root, f'build/{run}-implementation.log');assert f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART=xcsu35p-sbvb625-2-e'in log.read_text()
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        area=resources(folder/'routed_utilization.rpt');clocks=timing(folder/'routed_timing.rpt')
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        if required:assert met
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        for n in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/label/n]=folder/n
        files[Path('native')/label/'implementation.log']=log
        for n in provenance['files']:
            if n in{p.relative_to(frozen).as_posix()for p in dag.values()}or not n.startswith('rtl/'):files[Path('native')/label/'sources'/n]=frozen/n
        return dict(phase='native_route_verified',run=run,resources=area,timing=clocks,timing_met=met,exact_modules=len(dag),
            registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
    results['unit_native']=native('unit','http2_missing_stream_classifier','http2_classifier_scu35_initial',unit_inputs,True)
    results['controls_native']=native('controls','http2_classified_peer_controls','http2_classified_controls_scu35_initial',raw_inputs,False)
    files[Path('verification/verify_stream_classifier.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16];evidence=root/'build/validation/stream-classifier-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_classified_full_data_execution_verified'if args.full else'actual_fenced_admission_history_classification_verified',verified_utc=datetime.now(timezone.utc).isoformat(),**results,
        exact_native_reference_generators_and_harness_replay=True,actual_raw_parent_fence_verified=True,no_shadow_directory=True,
        cancellation_verified=False,postcommit_gpu_cancellation_verified=False,full_data_execution_verified=args.full,
        full_parser_native_timing_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation'/('classified-parser-full.json'if args.full else'stream-classifier.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
