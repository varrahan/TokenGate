"""Bind the real freeze/credit/DATA-wire join to frozen simulation and routing."""
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',default='actual_owned_wire_drain_terminal_race');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.snapshot)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={}
    archive=root/'build/wsl-reports'/('grpc_fenced_framer_'+args.snapshot);executed=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    snapshot=json.loads((archive/'snapshot.json').read_text());inputs=json.loads((archive/'inputs.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    for n,h in inputs.items():assert sha(executed/n)==h,n
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='actual_reserved_data_drains_before_key_close_and_cached_retirement'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    dag=closure('grpc_cancellable_window_framer',executed);assert len(dag)==11
    assert {'grpc_stream_store','grpc_pool_locked_stream_store','http2_owned_cancel_windows','http2_cancel_send_window_store',
        'http2_fenced_frame_grants','grpc_http2_response_framer','axis_cancellable_frame_arbiter'}<=dag.keys()
    assert sum(n=='grpc_stream_store'for n in dag)==1
    active={p.relative_to(executed).as_posix()for p in dag.values()}
    for n in active:assert sha(root/n)==inputs[n],'Active RTL differs: '+n
    assert accepted['native_reference']=='hyperframe'and accepted['native_reference_version']=='6.1.0'
    assert accepted['reserved_memory_phases']==15 and accepted['cancelled_scenarios']==22 and accepted['wire_boundary_scenarios']==5
    assert accepted['uncertain_debit_ack_faults']==2 and accepted['native_frames']==46 and accepted['data_frames']==23
    assert accepted['wire_stalls']>0 and accepted['controls_while_data_frozen']==23
    assert accepted['completed_message_result_races']==1 and accepted['completed_wire_success_not_retracted']
    for n in ('same_edge_freeze_blocks_dispatch','actual_parked_sender_cancelled','positive_reservation_drained_to_actual_wire',
        'all_dispatched_memory_phases_frozen','stalled_wire_promises_preserved','actual_key_close_waits_for_wire',
        'actual_cached_load_held_through_terminal_result','both_debit_acks_precede_every_positive_grant',
        'no_credit_refund','nonmatching_stream_continues','uncertain_debits_never_grant_or_publish_close','model_prefix_immutable'):
        assert accepted[n],n
    assert not any(accepted[n]for n in('actual_rpc_return_integrated','actual_rst_controller_integrated','gpu_image_lease_cancellation_verified','full_system_complete'))
    # Regenerate from the exact executed inputs, including all template helpers.
    replay=root/'build/validation/fenced-window-framer-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in inputs:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(executed/n,p)
        files[Path('execution')/n]=executed/n
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    for script in('generate_cancel_send_windows.py','generate_cancellable_frame_arbiter.py','generate_fenced_frame_grants.py'):
        subprocess.run([sys.executable,str(replay/'tools'/script)],check=True,capture_output=True,text=True)
    for n in ('rtl/http2_cancel_send_window_store.v','rtl/http2_owned_cancel_windows.v','rtl/http2_cancel_frame_grants.v',
        'rtl/axis_cancellable_frame_arbiter.v','rtl/http2_fenced_frame_grants.v','rtl/grpc_cancellable_window_framer.v'):
        assert sha(replay/n)==inputs[n],n
    joined=(executed/'rtl/grpc_cancellable_window_framer.v').read_text()
    assert '.frame_tx_done(data_tvalid&&data_tready&&data_tlast)'in joined
    assert '.a_pause(freeze_binding_valid&&freeze_drained)'in joined
    assert '.rst(rst)'in joined and '.rst(rst||'not in joined
    for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('reports')/n]=archive/n
    native={}
    for label,top,run in (
        ('legacy_grants','http2_cancel_frame_grants','http2_cancel_grants_scu35_initial'),
        ('joined','grpc_cancellable_window_framer','grpc_fenced_framer_scu35_initial'),
        ('refined_joined','grpc_cancellable_window_framer','grpc_fenced_framer_scu35_refined')):
        folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/run;log=root/f'build/{run}-implementation.log'
        marker=f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART=xcsu35p-sbvb625-2-e'
        if not log.is_file()or marker not in log.read_text():
            native[label]=dict(phase='route_not_yet_verified',run=run);continue
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        routed_dag=closure(top,frozen);assert len(routed_dag)==(6 if label=='legacy_grants'else 11)
        routed_active={p.relative_to(frozen).as_posix()for p in routed_dag.values()}
        for n in routed_active:assert sha(frozen/n)==inputs[n]==sha(root/n)
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        clocks=timing(folder/'routed_timing.rpt');area=resources(folder/'routed_utilization.rpt')
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        native[label]=dict(phase='native_route_verified',run=run,exact_modules=len(routed_dag),resources=area,timing=clocks,
            timing_met=met,registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        if label=='refined_joined':
            assert 'REGISTERED_ROUTE_REFINEMENT_BASE=grpc_fenced_framer_scu35_initial RTL_CHANGED=0 CLOCK_CHANGED=0'in log.read_text()
            assert sha(frozen/'scripts/refine_registered_route.tcl')==sha(root/'scripts/refine_registered_route.tcl')
            base=(frozen/'refinement-base.txt').read_text()
            assert 'base_run=grpc_fenced_framer_scu35_initial\n'in base and 'rtl_changed=0\nclock_changed=0'in base
            native[label]['unchanged_rtl_and_clock_verified']=True
            native[label]['base_checkpoint_sha256']=native['joined']['routed_checkpoint_sha256']
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/label/n]=folder/n
        files[Path('native')/label/'implementation.log']=log
        for n in provenance['files']:
            if n in routed_active or not n.startswith('rtl/'):files[Path('native')/label/'sources'/n]=frozen/n
    files[Path('verification/verify_fenced_window_framer.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/fenced-window-framer-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_reserved_data_wire_drain_and_key_close_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,execution_inputs=len(inputs),production_modules=list(dag),current_active_rtl_matches=True,
        current_primary_differences=[n for n,h in inputs.items()if not(root/n).is_file()or sha(root/n)!=h],
        generation_replay_exact=True,single_actual_directory_verified=True,native=native,
        actual_rpc_return_integrated=False,actual_rst_controller_integrated=False,gpu_image_lease_cancellation_verified=False,
        full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/fenced-window-framer.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
