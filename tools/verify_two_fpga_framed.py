"""Audit full raw/DMA/framed-return execution without claiming full transport."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from hyperframe.frame import Frame
from generate_two_fpga_application import balanced
from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot-name')
    parser.add_argument('--control-fork',action='store_true')
    parser.add_argument('--scheduled-native-run',default='rpc_grpc_scheduled_scu35_native')
    parser.add_argument('--functional-only',action='store_true')
    args=parser.parse_args()
    args.snapshot_name=args.snapshot_name or ('raw_framed_full_controls_initial' if args.control_fork else 'raw_framed_control_initial')
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',x)for x in(args.snapshot_name,args.scheduled_native_run))
    root=Path(__file__).resolve().parents[1]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    suite='two_fpga_controlled' if args.control_fork else 'two_fpga_framed'
    top='http2_controlled_parser_application' if args.control_fork else 'http2_framed_parser_application'
    archive=root/'build/wsl-reports'/('cocotb_'+suite+'_'+args.snapshot_name)
    executed=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text())
    accepted=json.loads((archive/'acceptance.json').read_text())
    snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['suite']==suite and report['phase']==accepted['phase']=='passed'
    assert report['tests']==1 and report['failures']==0 and not report.get('changed_inputs')
    assert snapshot['phase']=='snapshot_run_archived' and snapshot['runner_exit_code']==0
    assert snapshot['execution_report_sha256']==sha(archive/'report.json')
    assert report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert snapshot['snapshot_runner_sha256']==sha(executed/'scripts/run_cocotb_snapshot.py')
    xml=ET.parse(archive/'results.xml')
    tests=xml.findall('.//testcase')
    test_name='raw_requests_dma_framed_returns_and_ordered_full_controls' if args.control_fork else 'raw_requests_actual_dma_framed_returns_and_control_progress'
    assert len(tests)==1 and tests[0].attrib['name']==test_name
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    inputs={**report['source_sha256'],**report['fixture_sha256']}
    for name,digest in inputs.items():
        assert digest==sha(executed/name)==snapshot['source_and_fixture_sha256'][name],name
    assert (accepted['packets'],accepted['headers'],accepted['messages'],accepted['token_ids'],accepted['response_chunks'],accepted['response_bytes'])==(39,21,16,2828,2828,144686)
    assert (accepted['packet_aborts'],accepted['connection_opens'],accepted['memory_faults'],accepted['response_rejections'],accepted['response_memory_faults'])==(4,7,2,4,1)
    assert accepted['full_model_bytes']==8388608 and accepted['model_and_policy_immutable']
    assert accepted['pending_return_jobs']==0 and accepted['actual_dma_ids_returned']
    assert accepted['shared_actual_rpc_directory'] and accepted['shared_cached_directory_integrated']
    assert accepted['response_transport_framing_verified'] and accepted['actual_http2_window_update_ingress_verified']
    assert accepted['control_probe_packets']==1 and accepted['window_updates']==[[0,101],[1,37]]
    assert (accepted['response_data_frames'],accepted['response_wire_bytes'])==(2830,184296)
    assert accepted['separate_memory_banks_verified'] and accepted['tokenizer_memory_fabric_integrated']
    for name in ('mid_packet_gpu_admissions','continued_rx_beats','early_gpu_admissions','return_waited_for_prefill_cycles',
                 'rx_beats_during_return','credit_stall_cycles','response_stall_cycles','response_held_result_cycles'):
        assert accepted[name]>0,name
    assert not accepted['credit_ledger_verified'] and not accepted['whole_rpc_gpu_image_lease_verified'] and not accepted['full_system_complete']
    parser_dag=closure(top,executed)
    tokenizer_dag=closure('tokenizer_fpga_memory_subsystem',executed)
    assert len(parser_dag)==(53 if args.control_fork else 52) and len(tokenizer_dag)==22
    if args.control_fork:
        assert {'http2_control_event_fork','http2_controlled_hpack_ingress'}<=parser_dag.keys()
        assert accepted['full_metadata_control_fork_integrated']
        assert accepted['full_metadata_window_updates']==[[0,0,101],[0,1,37]]
        assert all(accepted[n]>0 for n in('flow_control_events','flow_control_stall_cycles','flow_data_frame_begins'))
    assert {'http2_frame_reader','http2_payload_decoder','http2_rpc_admission','grpc_leased_stream_store',
            'grpc_stream_store','rpc_grpc_scheduled_return','rpc_response_parser_partition','grpc_http2_response_framer'}<=parser_dag.keys()
    assert not {'grpc_ingress_engine','http2_parser_partition_core','bpe_tokenizer_engine','detokenizer_engine','token_packager'}&parser_dag.keys()
    assert {'bpe_tokenizer_engine','inverse_tokenizer_partition','detokenizer_engine','external_memory_fabric'}<=tokenizer_dag.keys()
    assert not {'grpc_stream_store','http2_frame_reader','proto_json_serializer'}&tokenizer_dag.keys()
    # Inspect instance ownership, not just unique module names in the DAG.
    store_instances=[]
    for module,path in parser_dag.items():
        text=re.sub(r'//[^\n]*|/\*.*?\*/','',path.read_text(),flags=re.S)
        for match in re.finditer(r'\bgrpc_stream_store\s*#\s*\(',text):
            close=balanced(text,text.index('(',match.start()))
            if re.match(r'\s*\w+\s*\(',text[close+1:]):store_instances.append(module)
    assert store_instances==['grpc_leased_stream_store']
    fixture=executed/'build/bidirectional-fixtures'
    oracle=json.loads((archive/'native-reference.json').read_text())
    oracle_verifier=executed/'tools/verify_http2_prefill_references.py'
    assert oracle['phase']=='passed' and oracle['native_token_ids']==2828 and oracle['complete_model_prefix_matches_image']
    assert oracle['verifier_sha256']==sha(oracle_verifier)
    assert snapshot['source_and_fixture_sha256']['build/bidirectional-reference-validation.json']==sha(archive/'native-reference.json')
    for name,digest in report['fixture_sha256'].items():
        if Path(name).name!='framed_reference.json':assert oracle['fixture_sha256'][Path(name).name]==digest
    framed=json.loads((fixture/'framed_reference.json').read_text())
    assert framed['phase']=='native_references_passed'
    assert framed['generator_sha256']==sha(executed/'tools/generate_two_fpga_framed_vectors.py')
    assert framed['input_sha256']==sha(fixture/'response_reference.json')
    # Independently decode all new frame references, including prefix splits.
    for key,entry in framed['frames'].items():
        stream,body_hex,_=key.split(':');record=bytearray()
        assert len(entry['grants'])==len(entry['wire'])
        for grant,raw_hex in zip(entry['grants'],entry['wire']):
            raw=bytes.fromhex(raw_hex);frame,length=Frame.parse_frame_header(memoryview(raw[:9]))
            frame.parse_body(memoryview(raw[9:]))
            assert frame.type==0 and frame.stream_id==int(stream) and not frame.flags
            assert length==grant==len(frame.data) and 1<=grant<=16384
            record.extend(frame.data)
        body=bytes.fromhex(body_hex)
        assert record==b'\0'+len(body).to_bytes(4,'big')+body
    controls=bytes.fromhex(framed['window_update_wire_hex'])
    for index,(stream,increment)in enumerate(framed['window_updates']):
        raw=controls[index*13:(index+1)*13]
        frame,length=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
        assert frame.type==8 and length==4 and frame.stream_id==stream and frame.window_increment==increment
    assert len(controls)==26
    files={Path('execution')/name:executed/name for name in inputs}
    files.update({Path('reports')/name:archive/name for name in('report.json','acceptance.json','results.xml','snapshot.json','native-reference.json','simulation.log','build.log')})
    files[Path('verification/verify_two_fpga_framed.py')]=Path(__file__)
    files[Path('verification/run_cocotb_snapshot.py')]=executed/'scripts/run_cocotb_snapshot.py'
    files[Path('verification/verify_http2_prefill_references.py')]=oracle_verifier
    native_results={}
    if not args.functional_only:
        components=[
            ('scheduled_return','rpc_grpc_scheduled_return',args.scheduled_native_run,36),
            ('tokenizer_memory','tokenizer_fpga_memory_subsystem','tokenizer_fpga_scu35_memory_fabric_initial',1)]
        if args.control_fork:components.append(('control_fork','http2_control_event_fork','http2_control_fork_scu35_initial',0))
        for label,component_top,run,expected_bram in components:
            native=root/'build/implementation/xcsu35p-sbvb625-2-e'/run
            frozen=native/'sources';provenance=json.loads((native/'source-provenance.json').read_text())
            for name,record in provenance['files'].items():
                assert sha(frozen/name)==record['sha256'] and (frozen/name).stat().st_size==record['bytes']
            dependencies=closure(component_top,frozen)
            for path in set(dependencies.values()):
                relative=path.relative_to(frozen)
                assert sha(path)==inputs[relative.as_posix()]
                files[Path('native')/label/'sources'/relative]=path
            for name in provenance['files']:
                if not name.startswith('rtl/'):files[Path('native')/label/'sources'/name]=frozen/name
            implementation=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
            exceptions=[x.strip()for x in implementation.splitlines()if x.strip().startswith('set_false_path')]
            assert exceptions==['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
            log=source_path(root, f'build/{run}-implementation.log')
            assert f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={component_top} PART=xcsu35p-sbvb625-2-e' in log.read_text()
            assert 'ERROR: [Synth' not in log.read_text() and 'Found timing loop' not in log.read_text()
            clocks=timing(native/'routed_timing.rpt');area=resources(native/'routed_utilization.rpt')
            assert area['luts']<=16320 and area['bram36']+area['bram18']/2<=48 and area['uram']==0
            assert area['bram36']==expected_bram
            assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(native/'route_status.rpt').read_text())
            drc=(native/'routed_drc.rpt').read_text()
            assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|',drc)
            met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
            native_results[label]=dict(top=component_top,run=run,active_rtl_files=len(dependencies),resources=area,timing=clocks,
                routed_timing_met=met,checkpoint_sha256=sha(native/'routed.dcp'),package_paths_excluded=True)
            for name in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','route_status.rpt','routed_drc.rpt'):
                files[Path('native')/label/name]=native/name
            files[Path('native')/label/'implementation.log']=log
    key=hashlib.sha256(''.join(sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    prefix='two-fpga-controlled' if args.control_fork else 'two-fpga-framed'
    evidence=source_path(root, Path('build/validation/'+prefix+'-evidence') / (key))
    for name,source in files.items():
        target=evidence/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source)
        else:shutil.copy2(source,target)
    result=dict(phase='functional_passed_component_timing_met' if native_results and all(x['routed_timing_met']for x in native_results.values()) else 'functional_passed_component_timing_pending',
        verified_utc=datetime.now(timezone.utc).isoformat(),acceptance=accepted,parser_modules=list(parser_dag),tokenizer_modules=list(tokenizer_dag),
        execution_sources=len(report['source_sha256']),execution_fixtures=len(report['fixture_sha256']),native_components=native_results,
        current_primary_differences=[name for name,digest in inputs.items()if not(source_path(root, name)).is_file()or sha(source_path(root, name))!=digest],
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)),
        raw_application_and_framed_return_joined=True,actual_window_update_ingress_verified=True,full_metadata_control_fork_integrated=args.control_fork,
        complete_parser_native_fit_verified=False,complete_parser_native_timing_verified=False,
        credit_ledger_verified=False,headers_trailers_verified=False,whole_rpc_image_leases_verified=False,
        physical_interfaces_verified=False,independent_clocks_verified=False,full_system_complete=False)
    (source_path(root, 'build/validation/'+prefix+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
