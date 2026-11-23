"""Audit actual response HEADERS/DATA/trailers, RPC ownership and native timing."""
import argparse
import codecs
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

import tiktoken
from verify_two_fpga_application import closure,resources,timing

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--headers',default='actual_headers_synthesis_safe_strings')
    parser.add_argument('--rpc',default='actual_rpc_registered_close_scope')
    parser.add_argument('--native-run',default='rpc_http2_scu35_registered_close_scope');parser.add_argument('--require-native',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',v)for k,v in vars(args).items()if k!='require_native')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={};records={}
    def execution(label,folder,test,top,count):
        archive=root/'build/wsl-reports'/folder;source=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
        inputs=json.loads((archive/'inputs.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():
            assert sha(source/n)==h,n;files[Path(label)/'execution'/n]=source/n
        xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
        assert len(cases)==1 and cases[0].attrib['name']==test and not xml.findall('.//failure')and not xml.findall('.//error')
        dag=closure(top,source);assert len(dag)==count
        for path in dag.values():
            n=path.relative_to(source).as_posix();assert sha(source_path(root, n))==inputs[n],'Current active RTL differs: '+n
        records[label]=dict(acceptance=accepted,execution_inputs=len(inputs),production_modules=list(dag),current_active_rtl_matches=True,
            current_primary_differences=[n for n,h in inputs.items()if not n.startswith('native-vendor/')and(not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h)])
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):
            files[Path(label)/'reports'/n]=archive/n
        return source,inputs,accepted
    unit,unit_inputs,header=execution('headers','grpc_headers_'+args.headers,
        'native_headers_trailers_and_actual_wire_abort_fences','grpc_response_headers',1)
    assert(header['native_header_cases'],header['native_client_exchanges'],header['rejected_commands'],header['actual_wire_frames'])==(122,99,8,124)
    for n in('stateless_hpack_with_zero_dynamic_decoder','config_poisoned_after_acceptance','held_results_verified',
        'private_abort_requires_actual_wire_fence','held_control_survives_private_abort','offered_header_drains_before_abort',
        'completed_header_result_not_retracted','native_client_uses_rtl_header_bytes'):assert header[n],n
    assert header['held_wire_cycles']>0 and header['client_exchange_data_is_native_fixture']
    source,inputs,rpc=execution('rpc','rpc_http2_'+args.rpc,
        'actual_rpc_native_client_headers_data_trailers_and_commit_faults','rpc_grpc_http2_return',20)
    assert(rpc['native_complete_rpc_streams'],rpc['actual_gpu_messages'],rpc['actual_gpu_descriptors'],rpc['actual_positive_grants'],rpc['actual_wire_frames'])==(8,70,99,85,133)
    assert rpc['envelope_cancellation_cases']==['prelookup_without_header_or_load','private_header_and_held_control',
        'offered_header_before_close','offered_trailer_completes_before_close','private_trailer_expected_cancel','foreign_scope_does_not_abort_header']
    faults=rpc['injected_progress_and_envelope_write_faults'];assert len(faults)==20
    for index,case in enumerate(faults):
        assert(case['phase'],case['memory_writes'])==(index,index+1)
        assert case['wire_types']==([]if index<5 else[1]if index<10 else[1,0]if index<15 else[1,0,1])
    for n in('ordinary_other_stream_completes_without_global_reset','rejected_sse_mode_retries_as_json_without_reset',
        'actual_inverse_full_vocabulary','actual_bow_and_rpc_cached_load','native_clients_consume_actual_rtl_frames',
        'all_progress_acks_before_initial_headers','header_wire_and_commit_before_actual_data','both_actual_debit_acks_before_data',
        'trailer_intent_before_end_stream','trailer_commit_before_gpu_result','physical_write_errors_do_not_repeat_wire',
        'held_gpu_results_retain_actual_load','complete_model_prefix_immutable'):assert rpc[n],n
    assert not any(rpc[n]for n in('raw_network_request_and_reset_joined','sse_transport_joined','whole_rpc_gpu_image_lease_verified','full_system_complete'))
    for path in closure('inverse_tokenizer_partition',source).values():
        n=path.relative_to(source).as_posix();assert sha(source_path(root, n))==inputs[n]
    assert unit_inputs['rtl/grpc_response_headers.v']==inputs['rtl/grpc_response_headers.v']
    assert unit_inputs['rtl/axis_cancellable_frame_arbiter.v']==inputs['rtl/axis_cancellable_frame_arbiter.v']

    # Re-run the exact frozen native HPACK/hyper-h2 generator with its frozen
    # pure-Python package code, not an unbound mutable WSL environment.
    replay=root/'build/validation/rpc-http2-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in inputs:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,p)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    code='import sys,runpy;sys.path[:0]=[sys.argv[1],sys.argv[2]];runpy.run_path(sys.argv[3],run_name="__main__")'
    subprocess.run([sys.executable,'-c',code,str(replay/'native-vendor'),str(replay/'tools'),str(replay/'tools/generate_grpc_header_vectors.py')],check=True,capture_output=True,text=True)
    assert sha(replay/'build/grpc-header-fixtures/cases.json')==inputs['build/grpc-header-fixtures/cases.json']==unit_inputs['build/grpc-header-fixtures/cases.json']
    subprocess.run([sys.executable,str(replay/'tools/generate_rpc_http2_progress.py')],check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(replay/'tools/generate_rpc_http2_return.py')],check=True,capture_output=True,text=True)
    generated=['rtl/rpc_http2_response_partition.v','rtl/http2_enveloped_frame_grants.v','rtl/rpc_grpc_http2_parser_response.v',
        'rtl/rpc_grpc_http2_return.v','sim/cocotb_rpc_http2_top.sv']
    for n in generated:assert sha(replay/n)==inputs[n]==sha(source_path(root, n)),n
    parent=(source/'rtl/rpc_grpc_http2_return.v').read_text();child=(source/'rtl/rpc_grpc_http2_parser_response.v').read_text()
    assert '.frame_tx_done(response_data_done)'in parent and '.a_pause(envelope_match_freeze&&!frame_wire_pending)'in parent
    assert 'assign data_frame_tx_done=body_tvalid&&body_tready&&body_tlast;'in child
    assert 'seq_terminal&&!transport_busy&&!transport_retirement_pending'in child
    assert 'result_ack_pending||public_result_ack'in parent and '.finish_valid(retire)'in parent
    for n in('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'):
        assert 'envelope_frozen_'+n+'==saved_frame_cfg_'+n in parent
    assert 'external_memory_fabric #(.CLIENTS(5))'in(source/'sim/cocotb_rpc_http2_top.sv').read_text()
    grants=(source/'rtl/http2_enveloped_frame_grants.v').read_text()
    assert 'reg envelope_scope_compared;reg [6:0] envelope_scope_equal;'in grants
    assert '!window_req_valid||!envelope_owned||window_req_ready'in grants
    assert '!envelope_owned||envelope_scope_compared&&(!control_matches_envelope||envelope_close_fence)'in grants

    fixture=source/'build/rpc-grpc-fixtures';reference=json.loads((fixture/'rpc_cases.json').read_text())
    image=(fixture/'memory.bin').read_bytes();manifest=json.loads((fixture/'model_manifest.json').read_text())
    assert hashlib.sha256(image).hexdigest()==reference['model_image_sha256']==manifest['image_sha256']
    assert reference['generator_sha256']==inputs['tools/generate_rpc_response_vectors.py']
    original=root/'build/scu35/image/external_memory.bin';original_bytes=original.read_bytes()
    assert sha(original)==reference['original_complete_image_sha256'];candidate=bytearray(image)
    for token,length in zip(reference['capacity_tokens'],(16384,16385)):
        offset=reference['layout']['directory_base']+token*8
        assert struct.unpack_from('<Q',original_bytes,offset)[0]==0
        assert struct.unpack_from('<Q',candidate,offset)[0]==2|900000<<16|length<<48
        candidate[offset:offset+8]=original_bytes[offset:offset+8]
    assert candidate==original_bytes
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    a=reference['layout']
    for token in range(100256):
        entry=struct.unpack_from('<Q',image,a['directory_base']+token*8)[0];raw=encoding.decode_single_token_bytes(token)
        assert entry&0xffff==2 and entry>>48==len(raw)
        offset=entry>>16&0xffffffff;assert image[a['pool_base']+offset:a['pool_base']+offset+len(raw)]==raw
    sys.path.insert(0,str(replay/'tools'));from generate_rpc_response_vectors import packet
    patterns=0
    for group in reference['groups']:
        for stream in group:
            decoder=codecs.getincrementaldecoder('utf8')('replace')
            for chunk in stream['chunks']:
                raw=encoding.decode_single_token_bytes(chunk['token']);assert raw.hex()==chunk['bow_hex']
                decoded=decoder.decode(raw,final=bool(chunk['eos'])).encode();carry=decoder.getstate()[0]
                assert packet(decoded,stream['format'],stream['field']).hex()==chunk['packet_hex']
                assert(chunk['decoded_bytes'],chunk['carry'],chunk['carry_count'])==(len(decoded),int.from_bytes(carry,'little'),len(carry))
                patterns+=1
    records['independent_native_reference']=dict(complete_original_image_verified=True,ordinary_vocab_tokens=100256,
        fresh_utf8_json_protobuf_sse_chunk_patterns=patterns,frozen_header_oracles_replayed=True,native_client_data_is_actual_rtl=True)
    files[Path('model/original_complete_image.bin')]=original

    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run
    native=dict(phase='not_yet_verified',run=args.native_run,timing_met=False)
    log=source_path(root, f'build/{args.native_run}-implementation.log')
    if(folder/'routed_timing.rpt').is_file()and'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE'in log.read_text():
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        dag=closure('rpc_grpc_http2_return',frozen);assert len(dag)==20
        for path in dag.values():
            n=path.relative_to(frozen).as_posix();assert sha(path)==inputs[n]==sha(source_path(root, n))
            files[Path('native/sources')/n]=path
        clocks=timing(folder/'routed_timing.rpt');area=resources(folder/'routed_utilization.rpt')
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        exceptions=[line.strip()for line in(frozen/'scripts/implement_registered_subsystem.tcl').read_text().splitlines()if line.strip().startswith('set_false_path')]
        assert exceptions==['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        native=dict(phase='native_route_verified',run=args.native_run,timing_met=met,exact_modules=20,resources=area,timing=clocks,
            registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/n]=folder/n
        files[Path('native/implementation.log')]=log
    if args.require_native:assert native['timing_met'],'Exact current twenty-module native timing is not met'
    records['native']=native;files[Path('verification/verify_rpc_http2_return.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-http2-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='actual_rpc_response_envelope_verified',verified_utc=datetime.now(timezone.utc).isoformat(),**records,
        exact_generators_and_harness_replayed=True,raw_network_request_and_reset_joined=False,sse_transport_joined=False,
        whole_rpc_gpu_image_lease_verified=False,physical_interfaces_verified=False,full_parser_native_timing_verified=False,
        full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/rpc-http2-return.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],native=native,evidence_folder=str(evidence)),indent=2))


if __name__=='__main__':main()
