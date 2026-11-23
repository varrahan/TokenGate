"""Bind actual RPC cancellation, native-reference matrix and optional native route."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

from hyperframe.frame import DataFrame, Frame
from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directed',default='actual_rpc_registered_pool_end_directed')
    parser.add_argument('--matrix',default='actual_rpc_registered_pool_end_matrix')
    parser.add_argument('--native-run',default='rpc_cancel_scu35_registered_pool_end')
    parser.add_argument('--functional-only',action='store_true')
    args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',v)for v in(args.directed,args.matrix,args.native_run))
    root=Path(__file__).resolve().parents[1];files={};records={}
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    top='rpc_grpc_cancellable_return'

    def execution(label,name,test):
        archive=root/'build/wsl-reports'/('rpc_cancel_'+name);source=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
        snapshot=json.loads((archive/'snapshot.json').read_text());inputs=json.loads((archive/'inputs.json').read_text())
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():assert sha(source/n)==h,n
        xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
        assert len(cases)==1 and cases[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        parser_dag=closure(top,source);inverse_dag=closure('inverse_tokenizer_partition',source)
        assert len(parser_dag)==18 and 'detokenizer_engine'not in parser_dag
        assert 'detokenizer_engine'in inverse_dag and 'proto_json_serializer'not in inverse_dag
        for p in[*parser_dag.values(),*inverse_dag.values()]:
            n=p.relative_to(source).as_posix();assert sha(source_path(root, n))==inputs[n],'Current active RTL differs: '+n
        harness=(source/'sim/cocotb_rpc_cancel_top.sv').read_text()
        assert 'external_memory_fabric #(.CLIENTS(5))'in harness and 'inverse_tokenizer_partition #'in harness
        assert 'grpc_stream_store registry('not in harness
        records[label]=dict(acceptance=accepted,execution_inputs=len(inputs),parser_modules=list(parser_dag),inverse_modules=list(inverse_dag),
            current_active_rtl_matches=True,current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h])
        for n in inputs:files[Path(label)/'execution'/n]=source/n
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','results.xml','simulation.log','build.log'):
            files[Path(label)/'reports'/n]=archive/n
        return accepted,source,inputs

    directed,source,inputs=execution('directed',args.directed,'actual_rpc_prelookup_and_loaded_cancel_preserve_all_owners')
    matrix,matrix_source,matrix_inputs=execution('matrix',args.matrix,'actual_cancellable_rpc_preserves_full_native_matrix')
    for p in closure(top,source).values():
        n=p.relative_to(source).as_posix();assert inputs[n]==matrix_inputs[n]
    assert(directed['actual_parser_rpc_modules'],directed['prelookup_matching_cancel_cases'],directed['prelookup_generation_mismatch_cases'])==(18,4,1)
    assert directed['runtime_window_context_and_protected_prefix_scope_negatives']==3
    assert directed['prelookup_actual_directory_inverse_and_progress_commands']==0
    assert(directed['uncertain_close_fault_phases'],directed['actual_gpu_descriptors'],directed['actual_directory_lookups'])==(14,29,10)
    assert(directed['native_data_frames'],directed['native_control_frames'])==(5,1)and directed['held_wire_cycles']>0
    assert all(directed[n]for n in('simultaneous_generic_open_and_cancel_without_ready_feedback','closed_binding_allocation_invalidation_verified',
        'different_key_and_pool_geometry_do_not_cancel','lookup_admission_remains_low_during_early_cancel',
        'cached_load_retained_through_public_terminal_ack','expected_stream_closed_has_no_transport_quarantine',
        'ordinary_other_stream_continues_without_global_reset','real_inverse_and_bow_used','positive_frame_drained_before_actual_key_close',
        'actual_wire_first_stall_and_frame_gap_verified','controls_continue_through_actual_wire_arbiter','complete_message_success_not_retracted',
        'offered_result_preserved_during_window_commands','gpu_ack_deferred_until_actual_window_owner_retires',
        'zero_keep_and_eos_descriptor_cancellation_verified','uncertain_close_never_publishes_binding',
        'prelookup_recovery_abort_without_shared_work','model_prefix_immutable'))
    assert not any(directed[n]for n in('actual_raw_rst_controller_integrated','whole_rpc_gpu_image_lease_verified','full_system_complete'))
    assert(matrix['cases'],matrix['successes'],matrix['rejections'],matrix['injected_faults'])==(185,110,75,23)
    assert matrix['baseline_rpc_matrix']['cases']==178 and matrix['extended_configuration_poison_cases']==185
    assert matrix['framed_wire_frames']==matrix['durable_positive_grants']==449 and matrix['frame_grants']==451
    assert matrix['key_only_window_updates']==896 and matrix['post_commit_credit_fault_cases']==2
    assert all(matrix[n]for n in('actual_cached_directory_and_pool_authority','actual_durable_window_grants',
        'all_progress_acks_before_reservation','both_debits_before_data','private_rejection_does_not_reset_directory',
        'directory_held_through_public_ack_verified','complete_model_prefix_immutable','actual_keyed_window_update_commands'))
    assert not matrix['raw_http2_control_integrated']and not matrix['whole_rpc_gpu_image_lease_verified']

    fixture=source/'build/rpc-grpc-fixtures';frames=json.loads((fixture/'frame_cases.json').read_text())
    reference=json.loads((fixture/'rpc_cases.json').read_text());manifest=json.loads((fixture/'model_manifest.json').read_text())
    for n in('memory.bin','rpc_cases.json','frame_cases.json','model_manifest.json'):
        assert inputs['build/rpc-grpc-fixtures/'+n]==matrix_inputs['build/rpc-grpc-fixtures/'+n]
    assert frames['phase']=='native_references_passed'and frames['generator_sha256']==inputs['tools/generate_rpc_grpc_vectors.py']
    assert reference['generator_sha256']==inputs['tools/generate_rpc_response_vectors.py']
    assert frames['model_image_sha256']==reference['model_image_sha256']==manifest['image_sha256']==matrix['model_image_sha256']==sha(fixture/'memory.bin')
    patterns=0
    for key,pattern in frames['frames'].items():
        stream,encoded=key.split(':',1);body=bytes.fromhex(encoded);record=b'\0'+len(body).to_bytes(4,'big')+body;reconstructed=bytearray()
        assert pattern['complete']and pattern['body']==encoded
        assert len(pattern['frames'])==len(pattern['grants'])==len(pattern['maxima'])
        for raw,grant,maximum in zip(pattern['frames'],pattern['grants'],pattern['maxima']):
            assert maximum==min(16384,len(record)-len(reconstructed))and 0<grant<=maximum
            wire=bytes.fromhex(raw);frame,size=Frame.parse_frame_header(memoryview(wire[:9]))
            assert isinstance(frame,DataFrame)and frame.stream_id==int(stream)and not set(frame.flags)and size==grant and len(wire)==size+9
            frame.parse_body(memoryview(wire[9:]));assert frame.serialize()==wire;reconstructed.extend(frame.data)
        assert reconstructed==record;patterns+=1
    original_path=root/'build/scu35/image/external_memory.bin';original=original_path.read_bytes();image=(fixture/'memory.bin').read_bytes()
    assert sha(original_path)==frames['original_complete_image_sha256']==reference['original_complete_image_sha256']
    candidate=bytearray(image);assert len(original)==len(candidate)==8388608 and reference['capacity_tokens']==[120000,120001]
    for token,length in zip(reference['capacity_tokens'],(16384,16385)):
        offset=reference['layout']['directory_base']+token*8
        assert struct.unpack_from('<Q',original,offset)[0]==0
        assert struct.unpack_from('<Q',candidate,offset)[0]==2|900000<<16|length<<48
        candidate[offset:offset+8]=original[offset:offset+8]
    assert candidate==original
    for region in manifest['regions']:
        assert hashlib.sha256(image[region['base']:region['base']+region['bytes']]).hexdigest()==region['sha256']
    files[Path('model/original_complete_image.bin')]=original_path

    replay=root/'build/validation/rpc-cancel-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in inputs:
        if n.startswith(('rtl/','tools/','sim/')):
            target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,target)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(replay/'tools/generate_rpc_cancel_return.py')],check=True,capture_output=True,text=True)
    generation=json.loads((replay/'build/validation/rpc-cancel-return-generation.json').read_text())
    for n,h in generation['input_sha256'].items():assert h==inputs[n]
    for n,h in generation['generated_sha256'].items():assert sha(replay/n)==h==inputs[n]
    parent=(source/f'rtl/{top}.v').read_text();backend=(source/'rtl/rpc_cancel_response_partition.v').read_text()
    child=(source/'rtl/rpc_grpc_cancel_parser_response.v').read_text()
    assert '.frame_tx_done(data_tvalid&&data_tready&&data_tlast)'in parent and '.a_pause(freeze_binding_valid&&freeze_drained)'in parent
    assert '.finish_valid(retire)'in parent and '.result_ready(retire)'in parent
    assert 'result_ack_pending||public_result_ack'in parent and 'assign result_retirement_pending=result_ack_pending;'in parent
    assert '.rst(rst||'not in parent and '.rst(rst||kill_ungranted)'in child
    assert 'window_rsp_valid&&window_rsp_ready&&window_rsp_status==0&&window_rsp_binding_valid&&window_rsp_send_closed'in parent
    closed=re.search(r'\.closed_valid\(([^\n]+)\)',parent)[1];assert 'closed_scope_matches'in closed and 'ready'not in closed
    for name in('context_base','context_bytes','window_base','window_bytes','work_floor'):
        assert f'saved_closed_{name}==saved_frame_cfg_{name}'in parent
        assert f'closing_{name}<=window_cfg_{name};'in parent and f'saved_closed_{name}<=closing_{name};'in parent
    assert 'assign directory_valid=state==DREQ&&!early_closed&&!early_abort;'in backend
    assert 'checked_stream_end<=stream_end;state<=DREQ;'in backend
    assert '{1\'b0,closed_address}+128<=checked_stream_end'in backend
    assert 'closed_pool_base==streams&&closed_pool_bytes==stream_bytes&&closed_address_good'in backend
    assert '!directory_held&&!child_started&&slot_idle&&child_idle'in backend
    assert '&&!expected_closed;'in child

    native=dict(phase='not_verified',run=args.native_run)
    if not args.functional_only:
        folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run;frozen=folder/'sources'
        provenance=json.loads((folder/'source-provenance.json').read_text());log=source_path(root, f'build/{args.native_run}-implementation.log')
        assert f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART=xcsu35p-sbvb625-2-e'in log.read_text()
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        dag=closure(top,frozen);assert len(dag)==18
        for p in dag.values():
            n=p.relative_to(frozen).as_posix();assert sha(p)==inputs[n]==sha(source_path(root, n));files[Path('native/sources')/n]=p
        script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[s.strip()for s in script.splitlines()if s.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        area=resources(folder/'routed_utilization.rpt');clocks=timing(folder/'routed_timing.rpt')
        assert area['luts']<=16320 and area['registers']<=32640 and area['bram36']+area['bram18']/2<=48 and area['uram']==area['dsps']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        native=dict(phase='native_route_verified',run=args.native_run,resources=area,timing=clocks,timing_met=met,
            exact_modules=18,registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        for n in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','route_status.rpt','routed_drc.rpt'):files[Path('native')/n]=folder/n
        files[Path('native/implementation.log')]=log
        for n in provenance['files']:
            if not n.startswith('rtl/'):files[Path('native/sources')/n]=frozen/n
    files[Path('verification/verify_rpc_cancel_return.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-cancel-return-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_rpc_cancellation_verified',verified_utc=datetime.now(timezone.utc).isoformat(),**records,native=native,
        exact_generation_replayed=True,independently_decoded_native_frame_patterns=patterns,original_complete_model_preserved=True,
        actual_raw_rst_controller_integrated=False,whole_rpc_gpu_image_lease_verified=False,physical_dma_packet_drain_verified=False,
        full_parser_fit_and_timing_verified=False,full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/rpc-cancel-return.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],native=native,directed_gpu_descriptors=directed['actual_gpu_descriptors'],
        matrix_cases=matrix['cases'],decoded_patterns=patterns,evidence_folder=str(evidence)),indent=2))


if __name__=='__main__':main()
