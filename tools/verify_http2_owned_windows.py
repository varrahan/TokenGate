"""Audit actual RPC allocation and pool-derived window authority."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from generate_two_fpga_application import balanced
from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--functional-only',action='store_true')
    parser.add_argument('--lifecycle',action='store_true')
    parser.add_argument('--keyed',action='store_true')
    parser.add_argument('--snapshot-name',default='actual_pool_owned_windows_initial')
    parser.add_argument('--native-run',default='http2_owned_windows_scu35_initial')
    args=parser.parse_args()
    assert not(args.lifecycle and args.keyed)
    if args.lifecycle:
        if args.snapshot_name=='actual_pool_owned_windows_initial':args.snapshot_name='retained_send_closure_initial'
        if args.native_run=='http2_owned_windows_scu35_initial':args.native_run='http2_owned_lifecycle_scu35_initial'
    if args.keyed:
        if args.snapshot_name=='actual_pool_owned_windows_initial':args.snapshot_name='actual_pool_keyed_updates_initial'
        if args.native_run=='http2_owned_windows_scu35_initial':args.native_run='http2_keyed_windows_scu35_initial'
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',x)for x in(args.snapshot_name,args.native_run))
    top='http2_owned_keyed_windows'if args.keyed else'http2_owned_lifecycle_windows'if args.lifecycle else'http2_owned_send_windows'
    window='http2_keyed_send_window_store'if args.keyed else'http2_lifecycle_send_window_store'if args.lifecycle else'http2_send_window_store'
    label='http2_keyed_windows_'if args.keyed else'http2_lifecycle_windows_'if args.lifecycle else'http2_owned_windows_'
    evidence_label='http2-keyed-window-evidence'if args.keyed else'http2-lifecycle-window-evidence'if args.lifecycle else'http2-owned-window-evidence'
    output='http2-keyed-windows.json'if args.keyed else'http2-lifecycle-windows.json'if args.lifecycle else'http2-owned-windows.json'
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports'/(label+args.snapshot_name);executed=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    inputs=json.loads((archive/'inputs.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and snapshot['exit_code']==0 and report['input_sha256']==inputs
    assert report['acceptance_sha256']==sha(archive/'acceptance.json') and report['tests']==1 and report['failures']==0
    for name,digest in inputs.items():assert sha(executed/name)==digest
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']==('actual_keyed_updates_generation_reuse_and_every_search_fault'if args.keyed else'retained_binding_send_closure_and_all_close_faults'if args.lifecycle else'actual_directory_authority_and_owned_window_progress')
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert accepted['native_window_commands']==28
    if args.keyed:
        assert accepted['total_window_commands']==176 and accepted['native_keyed_updates']==5
        assert accepted['search_memory_phases']==accepted['injected_search_faults']==22
        assert accepted['searched_records_before_target']==2
        assert all(accepted[n]for n in('actual_directory_allocation_verified','actual_pool_authority_verified',
            'foreign_same_stream_untouched','held_result_excludes_open_and_load','retained_closed_update_ignored',
            'real_generation_reuse_verified','missing_key_classification_deferred','caller_binding_metadata_rejected','model_prefix_immutable'))
        assert not accepted['raw_http2_control_integrated']
    elif args.lifecycle:
        assert accepted['total_window_commands']==116 and accepted['close_memory_phases']==accepted['injected_close_faults']==14
        assert accepted['active_settings_affected_streams']==2
        assert all(accepted[n]for n in('actual_directory_allocation_verified','actual_pool_authority_verified',
            'retained_closed_binding_verified','closed_max_window_settings_skip_verified','idempotent_close_verified',
            'late_positive_update_ignored','closed_data_grant_rejected','real_generation_reuse_reopens_window','model_prefix_immutable'))
        assert not accepted['actual_closing_wire_frame_integrated']
    else:
        assert accepted['window_commands']==39
        assert all(accepted[n]for n in('actual_directory_allocation_verified','actual_pool_authority_verified',
            'backend_drained_before_window_access','cached_results_survive_pool_lock','uncertain_window_debit_withheld','model_prefix_immutable'))
        assert accepted['frontend_blocked_cycles']>=40 and accepted['pool_configuration_rejections']==2 and accepted['backend_quarantine_rejections']==1
        assert not accepted['actual_raw_control_integrated']
    if not args.keyed:assert not accepted['actual_framer_grants_integrated']
    assert not accepted['full_system_complete']
    dependencies=closure(top,executed)
    assert set(dependencies)=={top,window,'grpc_pool_locked_stream_store','grpc_stream_store','memory_command_slot'}
    actual=[]
    for name,path in dependencies.items():
        text=re.sub(r'//[^\n]*|/\*.*?\*/','',path.read_text(),flags=re.S)
        for match in re.finditer(r'\bgrpc_stream_store\s*#\s*\(',text):
            end=balanced(text,text.index('(',match.start()))
            if re.match(r'\s*\w+\s*\(',text[end+1:]):actual.append(name)
    assert actual==['grpc_pool_locked_stream_store']
    source=(executed/f'rtl/{top}.v').read_text()
    assert '.req_authority(directory_pool_lock_active)'in source and '.req_valid(state==ISSUE&&directory_pool_lock_active)'in source
    assert 'assign window_req_ready=!rst&&state==IDLE;'in source
    assert 'RESULT:if(engine_rsp_valid&&window_rsp_ready)state<=UNLOCK;'in source
    if args.keyed:
        source=(executed/f'rtl/{window}.v').read_text()
        assert 'wire searching=op==WINDOW_UPDATE_KEY&&stream_id!=0;'in source
        assert 'op==WINDOW_UPDATE_KEY&&(generation!=0||rpc_address!=0)'in source
        assert 'else if(searching)finish_error(3,10,0,0);'in source
    fixture=executed/'build/http2-send-window-fixtures'
    reference=json.loads((fixture/'cases.json').read_text())
    assert reference['phase']=='native_send_window_references_passed' and reference['generator_sha256']==sha(executed/'tools/generate_http2_send_window_vectors.py')
    assert reference['original_image_sha256']==sha(fixture/'model.bin')==sha(root/'build/scu35/image/external_memory.bin')
    # The separate window audit independently reproduces this exact reference;
    # bind its already-rebuilt bytes rather than regenerating unrelated models.
    key=hashlib.sha256((reference['generator_sha256']+reference['original_image_sha256']).encode()).hexdigest()[:16]
    assert sha(root/'build/validation/http2-send-window-reference-replay'/key/'build/http2-send-window-fixtures/cases.json')==sha(fixture/'cases.json')
    files={Path('execution')/name:executed/name for name in inputs}
    files.update({Path('reports')/name:archive/name for name in('report.json','inputs.json','snapshot.json','results.xml','acceptance.json','simulation.log','build.log')})
    files[Path('verification/verify_http2_owned_windows.py')]=Path(__file__)
    result=dict(phase='actual_authority_functional_passed_native_pending',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,active_rtl_modules=list(dependencies),execution_inputs=len(inputs),single_actual_directory_verified=True,
        authority_from_actual_pool_lock_verified=True,current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h],
        raw_control_integrated=False,framer_grants_integrated=False,send_closed_lifecycle_verified=args.lifecycle,
        key_only_window_update_verified=args.keyed,unknown_stream_wire_classification_integrated=False,
        actual_closing_wire_frame_integrated=False,
        whole_rpc_image_leases_verified=False,independent_clocks_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    if not args.functional_only:
        native=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run;frozen=native/'sources'
        provenance=json.loads((native/'source-provenance.json').read_text())
        for name,record in provenance['files'].items():assert sha(frozen/name)==record['sha256']and(frozen/name).stat().st_size==record['bytes']
        native_dependencies=closure(top,frozen);assert set(native_dependencies)==set(dependencies)
        for path in set(native_dependencies.values()):
            relative=path.relative_to(frozen);assert sha(path)==inputs[relative.as_posix()]
            files[Path('native/sources')/relative]=path
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in script.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        log=source_path(root, f'build/{args.native_run}-implementation.log')
        assert f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART=xcsu35p-sbvb625-2-e'in log.read_text()
        assert '0 Critical Warnings and 0 Errors encountered.'in log.read_text()and 'ERROR: [Synth'not in log.read_text()
        area=resources(native/'routed_utilization.rpt');clocks=timing(native/'routed_timing.rpt')
        assert area['luts']<=16320 and area['registers']<=32640 and area['bram36']==area['bram18']==area['uram']==area['dsps']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(native/'route_status.rpt').read_text())
        assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|',(native/'routed_drc.rpt').read_text())
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        result.update(phase='actual_authority_functional_and_timing_met'if met else'actual_authority_functional_passed_timing_pending',
            native_run=args.native_run,native_exact_rtl_files=len(native_dependencies),resources=area,timing=clocks,
            routed_timing_met=met,package_paths_excluded=True,routed_checkpoint_sha256=sha(native/'routed.dcp'))
        files[Path('native/implementation.log')]=log
        for name in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/name]=native/name
        for name in provenance['files']:
            if not name.startswith('rtl/'):files[Path('native/sources')/name]=frozen/name
    key=hashlib.sha256(''.join(sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation'/evidence_label/key
    for name,source in files.items():
        target=evidence/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source)
        else:shutil.copy2(source,target)
    result['evidence_folder']=str(evidence)
    (root/'build/validation'/output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
