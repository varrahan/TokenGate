"""Audit real native-client calls and raw reset boundaries on the 68-module join."""
import argparse
import codecs
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import tiktoken
from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',default='actual_raw_registered_close_scope')
    parser.add_argument('--faults',help='Require all 41 shutdown fault phases on this exact 68-module join')
    parser.add_argument('--return-faults',help='Require all 20 raw-admitted response metadata ACK faults')
    parser.add_argument('--workload',help='Require the full native gRPC prompt/DMA-return corpus');args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',n)for n in(vars(args).values())if n)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={}
    archive=root/'build/wsl-reports'/('raw_envelope_'+args.snapshot);source=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    inputs=json.loads((archive/'inputs.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    for n,h in inputs.items():assert sha(source/n)==h,n;files[Path('execution')/n]=source/n
    xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='native_calls_return_actual_dma_ids_and_complete_grpc'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    parser_dag=closure('http2_enveloped_parser_application',source);tokenizer_dag=closure('tokenizer_fpga_memory_subsystem',source)
    assert(len(parser_dag),len(tokenizer_dag))==(68,22)
    assert {'rpc_grpc_http2_return','grpc_rpc_envelope','grpc_response_headers','http2_enveloped_shutdown'}<=parser_dag.keys()
    assert 'detokenizer_engine'not in parser_dag and 'detokenizer_engine'in tokenizer_dag
    for path in[*parser_dag.values(),*tokenizer_dag.values()]:
        n=path.relative_to(source).as_posix();assert inputs[n]==sha(source_path(root, n)),'Current active RTL differs: '+n
    names=('actual_raw_packets','actual_header_bindings','native_complete_grpc_calls','actual_forward_dma_ids',
        'actual_gpu_descriptors_accepted','actual_captured_dma_ids_returned','additional_generated_control_case_descriptors','native_wire_frames')
    assert tuple(accepted[n]for n in names)==(11,6,2,6,8,4,4,15)
    assert(accepted['parser_memory_clients'],accepted['tokenizer_memory_clients'])==(17,9)
    for n in('native_request_headers_and_data_generated_by_client','native_client_consumes_actual_rtl_responses',
        'normal_call_generated_input_is_captured_forward_dma','json_and_protobuf_response_fields_verified',
        'actual_response_headers_and_grpc_status_verified','actual_raw_mid_packet_reset_without_lookup',
        'actual_raw_rst_drains_offered_initial_header','actual_raw_rst_drains_offered_final_trailer',
        'actual_completed_eos_result_survives_raw_reset','ordinary_prompt_after_reset_without_global_reset',
        'actual_header_commit_failure_propagates_through_raw_reset','failed_header_commit_never_processes_reset',
        'complete_model_prefix_immutable'):assert accepted[n],n
    assert not any(accepted[n]for n in('whole_rpc_gpu_image_lease_verified','sse_transport_verified','receive_flow_control_verified',
        'physical_interfaces_verified','full_system_complete'))
    core=(source/'rtl/http2_enveloped_parser_core.v').read_text();controller=(source/'rtl/http2_enveloped_shutdown.v').read_text()
    for n in('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'):
        assert f'.freeze_cfg_{n}(shutdown_owned_{n})'in core
    assert 'fail(return_envelope_status,20,return_envelope_memory_status,1,2,1)'in controller
    assert 'window_req_valid&&!shutdown_recovery_required&&!response_recovery_required'in core
    assert 'wire allow_new_rx=!journal_recovery_required&&!response_recovery_required&&'in core
    harness=(source/'sim/cocotb_two_fpga_enveloped_top.sv').read_text()
    assert 'external_memory_fabric #(.CLIENTS(17)) p_fabric('in harness and 'tokenizer_fpga_memory_subsystem #'in harness
    # Bind this raw join to the independently audited full RPC envelope matrix.
    component_path=root/'build/validation/rpc-http2-return.json';component=json.loads(component_path.read_text())
    assert component['phase']=='actual_rpc_response_envelope_verified'and component['verifier_sha256']==sha(root/'tools/verify_rpc_http2_return.py')
    component_evidence=Path(component['evidence_folder']);component_inputs=json.loads((component_evidence/'rpc/reports/inputs.json').read_text())
    component_source=component_evidence/'rpc/execution'
    for path in closure('rpc_grpc_http2_return',source).values():
        n=path.relative_to(source).as_posix();assert sha(component_source/n)==component_inputs[n]==inputs[n]
    files[Path('component/rpc-http2-return.json')]=component_path
    fixture=source/'build/bidirectional-fixtures';layout=list(map(int,(fixture/'layout.txt').read_text().split()))
    loaded=b''.join(int(s,16).to_bytes(8,'little')for s in(fixture/'memory.mem').read_text().splitlines())
    manifest=json.loads((fixture/'fixture_manifest.json').read_text());original=root/'build/scu35/image/external_memory.bin'
    assert hashlib.sha256(loaded).hexdigest()==manifest['loaded_image_sha256']
    assert sha(original)=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    assert loaded[:layout[6]]==original.read_bytes()[:layout[6]]
    references=json.loads((fixture/'reference_cases.json').read_text());prompt=bytes.fromhex(references['cases'][0]['prompt_utf8_hex'])
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    ids=encoding.encode_ordinary(prompt.decode());assert ids==references['cases'][0]['token_ids']==[15339,1917]
    sys.path.insert(0,str(source/'tools'));from generate_rpc_response_vectors import packet
    for stream,mode in(('1',0),('3',2)):
        expected=[]
        for token in ids:
            raw=encoding.decode_single_token_bytes(token);body=packet(raw,mode,17);expected.append((b'\0'+len(body).to_bytes(4,'big')+body).hex())
        assert accepted['expected_response_records'][stream]==expected
    files[Path('model/original_complete_image.bin')]=original
    replay=root/'build/validation/raw-envelope-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in inputs:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,p)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(replay/'tools/generate_http2_enveloped_parser.py')],check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(replay/'tools/generate_two_fpga_harness.py'),'--enveloped-parser','--tokenizer-memory'],check=True,capture_output=True,text=True)
    for n in('rtl/http2_enveloped_shutdown.v','rtl/http2_enveloped_parser_core.v','rtl/http2_enveloped_parser_application.v','sim/cocotb_two_fpga_enveloped_top.sv'):
        assert sha(replay/n)==inputs[n]==sha(source_path(root, n)),n
    for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('reports')/n]=archive/n
    faults=None
    if args.faults:
        fault_archive=root/'build/wsl-reports'/('raw_envelope_'+args.faults);fault_source=fault_archive/'execution-sources'
        fault_report=json.loads((fault_archive/'report.json').read_text());fault_snapshot=json.loads((fault_archive/'snapshot.json').read_text())
        faults=json.loads((fault_archive/'acceptance.json').read_text());fault_inputs=json.loads((fault_archive/'inputs.json').read_text())
        assert fault_report['phase']==faults['phase']=='passed'and fault_report['tests']==1 and fault_report['failures']==0
        assert fault_snapshot['exit_code']==0 and fault_snapshot['profile']==fault_report['profile']=='shutdown-faults'
        assert fault_report['input_sha256']==fault_inputs and fault_report['acceptance_sha256']==sha(fault_archive/'acceptance.json')
        for n,h in fault_inputs.items():assert sha(fault_source/n)==h,n;files[Path('faults/execution')/n]=fault_source/n
        fault_xml=ET.parse(fault_archive/'results.xml');fault_cases=fault_xml.findall('.//testcase')
        assert len(fault_cases)==1 and fault_cases[0].attrib['name']=='raw_shutdown_memory_failures_preserve_quarantine_and_ownership'
        assert not fault_xml.findall('.//failure')and not fault_xml.findall('.//error')
        for path in[*parser_dag.values(),*tokenizer_dag.values()]:
            n=path.relative_to(source).as_posix();assert fault_inputs[n]==inputs[n]==sha(source_path(root, n)),n
        for n in('sim/cocotb_two_fpga_enveloped_top.sv','build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/layout.txt'):
            assert fault_inputs[n]==inputs[n],n
        assert(faults['window_close_faults'],faults['directory_close_faults'],faults['peer_goaway_faults'])==(14,9,18)
        expected=[(kind,phase)for kind,count in(('directory',9),('window',14),('peer',18))for phase in range(count)]
        assert[(c['service'],c['phase'])for c in faults['actual_raw_fault_cases']]==expected
        assert all(c['memory_commands']==c['phase']+1 and c['reset_processed']==(c['service']=='directory')for c in faults['actual_raw_fault_cases'])
        for n in('applied_write_errors','new_admission_fenced_until_global_reset','global_resets_only_after_actual_owners_drained',
            'successful_reset_after_explicit_root_reinitialization','fresh_disjoint_window_arena_per_global_reset','complete_model_prefix_immutable'):assert faults[n],n
        assert faults['actual_memory_error']==0x75 and not faults['retained_window_arena_warm_reset_verified']
        assert not any(faults[n]for n in('whole_rpc_gpu_image_lease_verified','physical_dma_packet_drain_verified','full_system_complete'))
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('faults/reports')/n]=fault_archive/n
    return_faults=None
    if args.return_faults:
        fault_archive=root/'build/wsl-reports'/('raw_envelope_'+args.return_faults);fault_source=fault_archive/'execution-sources'
        fault_report=json.loads((fault_archive/'report.json').read_text());fault_snapshot=json.loads((fault_archive/'snapshot.json').read_text())
        return_faults=json.loads((fault_archive/'acceptance.json').read_text());fault_inputs=json.loads((fault_archive/'inputs.json').read_text())
        assert fault_report['phase']==return_faults['phase']=='passed'and fault_report['tests']==1 and fault_report['failures']==0
        assert fault_snapshot['exit_code']==0 and fault_snapshot['profile']==fault_report['profile']=='return-faults'
        assert fault_report['input_sha256']==fault_inputs and fault_report['acceptance_sha256']==sha(fault_archive/'acceptance.json')
        for n,h in fault_inputs.items():assert sha(fault_source/n)==h,n;files[Path('return-faults/execution')/n]=fault_source/n
        fault_xml=ET.parse(fault_archive/'results.xml');fault_cases=fault_xml.findall('.//testcase')
        assert len(fault_cases)==1 and fault_cases[0].attrib['name']=='raw_admitted_return_metadata_faults_keep_real_ownership'
        assert not fault_xml.findall('.//failure')and not fault_xml.findall('.//error')
        for path in[*parser_dag.values(),*tokenizer_dag.values()]:
            n=path.relative_to(source).as_posix();assert fault_inputs[n]==inputs[n]==sha(source_path(root, n)),n
        for n in('sim/cocotb_two_fpga_enveloped_top.sv','build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/layout.txt'):
            assert fault_inputs[n]==inputs[n],n
        assert return_faults['actual_memory_error']==0x75 and return_faults['actual_gpu_descriptors_accepted']==21
        assert return_faults['actual_header_bindings']==21 and return_faults['actual_raw_packets']==42
        cases=return_faults['actual_return_metadata_faults'];assert len(cases)==20
        for index,case in enumerate(cases):
            types=[]if index<5 else[1]if index<10 else[1,0]if index<15 else[1,0,1]
            assert(case['phase'],case['memory_commands'],case['wire_types'],case['gpu_stage'])==(index,index+1,types,5 if index<5 else 20)
            assert(case['progress_base'],case['window_base'])==(0x7e8000+index*128,0x7f0000+index*64)
        for n in('real_raw_headers_and_native_response_client','applied_write_errors','held_gpu_results_retain_actual_load',
            'cached_load_retires_after_actual_gpu_ack','no_repeated_wire_after_uncertain_metadata','new_public_work_fenced',
            'global_reset_only_after_actual_owners_drained','fresh_window_and_progress_arenas_per_reset',
            'successful_gpu_return_after_explicit_root_reinitialization','fault_descriptors_are_explicit_generated_gpu_stimuli',
            'complete_model_prefix_immutable'):assert return_faults[n],n
        assert not any(return_faults[n]for n in('retained_arenas_warm_reset_verified','forward_dma_workload_verified',
            'raw_reset_concurrent_with_every_return_fault_verified','physical_interfaces_verified','whole_rpc_gpu_image_lease_verified','full_system_complete'))
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('return-faults/reports')/n]=fault_archive/n
    workload=None
    if args.workload:
        workload_archive=root/'build/wsl-reports'/('raw_envelope_'+args.workload);workload_source=workload_archive/'execution-sources'
        workload_report=json.loads((workload_archive/'report.json').read_text());workload_snapshot=json.loads((workload_archive/'snapshot.json').read_text())
        workload=json.loads((workload_archive/'acceptance.json').read_text());workload_inputs=json.loads((workload_archive/'inputs.json').read_text())
        assert workload_report['phase']==workload['phase']=='passed'and workload_report['tests']==1 and workload_report['failures']==0
        assert workload_snapshot['exit_code']==0 and workload_snapshot['profile']==workload_report['profile']=='workload'
        assert workload_report['input_sha256']==workload_inputs and workload_report['acceptance_sha256']==sha(workload_archive/'acceptance.json')
        for n,h in workload_inputs.items():assert sha(workload_source/n)==h,n;files[Path('workload/execution')/n]=workload_source/n
        workload_xml=ET.parse(workload_archive/'results.xml');workload_cases=workload_xml.findall('.//testcase')
        assert len(workload_cases)==1 and workload_cases[0].attrib['name']=='complete_prompt_corpus_uses_native_grpc_and_actual_dma'
        assert not workload_xml.findall('.//failure')and not workload_xml.findall('.//error')
        for path in[*parser_dag.values(),*tokenizer_dag.values()]:
            n=path.relative_to(source).as_posix();assert workload_inputs[n]==inputs[n]==sha(source_path(root, n)),n
        for n in('sim/cocotb_two_fpga_enveloped_top.sv','build/bidirectional-fixtures/memory.mem',
            'build/bidirectional-fixtures/reference_cases.json','build/bidirectional-fixtures/response_reference.json'):
            assert workload_inputs[n]==inputs[n],n
        assert tuple(workload[n]for n in('native_complete_grpc_calls','actual_forward_dma_ids','actual_captured_dma_ids_returned',
            'actual_gpu_descriptors_accepted','actual_header_bindings','parser_memory_clients','tokenizer_memory_clients'))==(16,2828,2828,2828,16,17,9)
        assert len(workload['native_grpc_calls'])==len(references['cases'])==16
        for index,(call,reference)in enumerate(zip(workload['native_grpc_calls'],references['cases'])):
            prompt=bytes.fromhex(reference['prompt_utf8_hex']);ids=encoding.encode_ordinary(prompt.decode())
            assert ids==reference['token_ids']
            mode=0 if index%2==0 else 2
            assert(call['reference_index'],call['stream'],call['format'],call['tokens'])==(index,2*index+1,mode,len(ids))
            decoder=codecs.getincrementaldecoder('utf8')('replace');records=bytearray()
            for ordinal,token in enumerate(ids):
                raw=encoding.decode_single_token_bytes(token)
                decoded=decoder.decode(raw,final=ordinal+1==len(ids)).encode();body=packet(decoded,mode,17)
                records.extend(b'\0'+len(body).to_bytes(4,'big')+body)
            assert len(records)==call['response_record_bytes']and hashlib.sha256(records).hexdigest()==call['response_sha256']
        for n in('native_request_and_response_endpoints','actual_peer_settings_and_window_updates','original_prompt_corpus_verified',
            'json_and_protobuf_response_fields_verified','complete_model_prefix_immutable','explicit_host_directory_retirement'):assert workload[n],n
        assert not any(workload[n]for n in('sse_transport_verified','receive_flow_control_verified','whole_rpc_gpu_image_lease_verified',
            'physical_interfaces_verified','full_system_complete'))
        for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('workload/reports')/n]=workload_archive/n
    files[Path('verification/verify_raw_enveloped_parser.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/raw-envelope-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='native_raw_grpc_response_envelope_verified',verified_utc=datetime.now(timezone.utc).isoformat(),acceptance=accepted,
        parser_modules=list(parser_dag),tokenizer_modules=list(tokenizer_dag),execution_inputs=len(inputs),current_active_rtl_matches=True,
        exact_raw_generation_and_harness_replayed=True,component_functional_matrix_bound=True,complete_original_model_prefix_verified=True,
        native_prompt_and_return_records_independently_reconstructed=True,
        current_primary_differences=[n for n,h in inputs.items()if not n.startswith('native-vendor/')and(not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h)],
        full_ordinary_workload_on_this_variant_verified=False,full_raw_memory_fault_matrix_verified=False,
        full_raw_shutdown_memory_fault_matrix_verified=faults is not None,
        raw_shutdown_fault_acceptance=faults,
        full_raw_return_metadata_fault_matrix_verified=return_faults is not None,raw_return_metadata_fault_acceptance=return_faults,
        full_native_grpc_prompt_corpus_verified=workload is not None,native_grpc_prompt_corpus_acceptance=workload,
        receive_flow_control_verified=False,sse_transport_verified=False,whole_rpc_gpu_image_lease_verified=False,
        physical_interfaces_verified=False,full_parser_native_timing_verified=False,full_system_complete=False,
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/raw-enveloped-parser.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','evidence_folder','full_system_complete')},indent=2))


if __name__=='__main__':main()
