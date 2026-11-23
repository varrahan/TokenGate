"""Audit both actual GPU/refusal wire orders, native bodies and all credit."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import Frame
import tiktoken

from verify_joint_hyperram_grpc_native import varint
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('rpc-stream-refusal-v7','rpc-registered-frame-select-v1'),default='rpc-stream-refusal-v7');args=ap.parse_args()
    registered=args.candidate=='rpc-registered-frame-select-v1'
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    candidate=root/'build/experiments'/args.candidate;generation=read(candidate/'generation.json')
    directed=read(root/'build/validation/rpc-stream-refusal-v7-directed.json')
    assert directed['key']=='950ce3b65ccb9b0a'
    if registered:
        from verify_registered_frame_select import require_unit_audit
        selection_audit=require_unit_audit(root)
        assert directed['generation_sha256']==generation['parent_generation_sha256']
    else:assert directed['generation_sha256']==sha(candidate/'generation.json')
    assert directed['four_directed_application_runs_verified']
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    encoding=tiktoken.get_encoding('cl100k_base');ids=encoding.encode('hello world');assert ids==[15339,1917]
    expected=b''
    for token in ids:
        text=encoding.decode_single_token_bytes(token);payload=varint(17<<3|2)+varint(len(text))+text
        expected+=b'\0'+len(payload).to_bytes(4,'big')+payload
    test_name='sim/cocotb/test_rpc_refusal_gpu.py';current=(root/test_name).read_bytes().decode()
    delay='        await cycles(d,2)\n';assert current.count(delay)==1
    runs={'gpu-first':'rpc_stream_refusal_v7_gpu_first_20261122','reset-first':'rpc_stream_refusal_v7_reset_first_v2_20261122'}
    if registered:runs={'gpu-first':'rpc_registered_select_v1_gpu_first_20261122','reset-first':'rpc_registered_select_v1_reset_first_20261122'}
    executions={};artifacts={Path(__file__)}
    parent=root/'build/wsl-reports/raw_envelope_receive_capacity_v4_native_owner_admission_20261122'
    parent_inputs=read(parent/'inputs.json')
    for order,run in runs.items():
        folder=root/'build/wsl-reports'/('raw_envelope_'+run);source=folder/'execution-sources'
        launch=read(folder/'launch.json');report=read(folder/'report.json');inputs=read(folder/'inputs.json');accepted=read(folder/'acceptance.json')
        assert launch['phase']=='completed'and launch['exit_code']==0 and launch['scenario']==order
        if registered:assert launch['registered_selection_unit_audit_key']==selection_audit['key']
        assert launch['generation_sha256']==sha(candidate/'generation.json')==sha(folder/'fence-generation.json')
        assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0
        assert inputs==report['input_sha256']==launch['inputs_sha256']
        assert sha(folder/'acceptance.json')==report['acceptance_sha256']
        assert all(sha(source/n)==h for n,h in inputs.items())
        assert sha(folder/'run_rpc_admission_fence_wsl.py')==launch['driver_sha256']
        assert {n:sha(p)for n,p in closure('http2_enveloped_parser_application',source).items()}==generation['non_mmio_parser_sha256']==launch['parser_sha256']
        tokenizer={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
        assert len(tokenizer)==22 and tokenizer==launch['tokenizer_sha256']=={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',parent/'execution-sources').items()}
        assert launch['parent_inputs_sha256']==parent_inputs
        for n,edit in launch['fixture_edits'].items():
            text=(source/n).read_bytes().decode();assert sha(source/n)==edit['after_sha256']
            for before,after in reversed(edit['replacements']):
                assert text.count(after)==1;text=text.replace(after,before)
            assert hashlib.sha256(text.encode()).hexdigest()==edit['before_sha256']
            if n in parent_inputs:assert edit['before_sha256']==parent_inputs[n]
        assert inputs['build/bidirectional-fixtures/memory.mem']==parent_inputs['build/bidirectional-fixtures/memory.mem']
        actual_test=(source/test_name).read_bytes().decode()
        expected_test=current.replace(delay,'')if order=='gpu-first'and not registered else current if order=='gpu-first'else current.replace("ORDER='gpu-first'","ORDER='reset-first'")
        assert actual_test==expected_test
        xml=ET.parse(folder/'results.xml');tests=xml.findall('.//testcase')
        assert len(tests)==1 and tests[0].attrib['name']=='real_gpu_and_refused_data_preserve_wire_ownership'
        assert not xml.findall('.//failure')and not xml.findall('.//error')
        assert accepted['order']==order and accepted['held_wire_cycles']==37
        assert accepted['actual_captured_dma_ids_returned']=={'1':ids,'5':ids}
        assert accepted['actual_generated_descriptors']==[[s,t,i,int(i==1)]for s in(1,5)for i,t in enumerate(ids)]
        assert accepted['native_complete_grpc_calls']==2 and bytes.fromhex(accepted['byte_exact_response_hex'])==expected
        overlap=accepted['overlap'];assert len(overlap)==37
        assert [e['clock']for e in overlap]==list(range(overlap[0]['clock'],overlap[0]['clock']+37))
        if order=='gpu-first':
            assert all(e['return_pending']==e['gpu_accepted']==e['directory_lease']==1 for e in overlap)
            assert any(e['raw_valid']for e in overlap)
        else:assert all(e['gpu_valid']or e['return_pending']for e in overlap)
        counts=accepted['axis_promise_counts'];assert counts['wire_held_cycles']>=37 and counts['gpu_handshakes']==4
        assert counts['raw_held_cycles']>0
        assert [(r['stream'],r['header_status'],r['header_detail'],r['header_http2_error'])for r in accepted['header_rejections']]==[(3,4,1,7)]
        packets=read(folder/'ingress_packets.json');raw_frames=read(folder/'wire_frames.json')
        assert len(packets)==4 and all(p['user']==0 and p['expected_commit']==1 for p in packets)
        server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'));server.initiate_connection()
        headers={};bodies={};flow={}
        for packet in packets:
            for event in server.receive_data(bytes.fromhex(packet['raw_hex'])):
                kind=type(event).__name__
                if kind=='RequestReceived':headers[event.stream_id]=event.headers
                if kind=='DataReceived':
                    bodies[event.stream_id]=bodies.get(event.stream_id,b'')+event.data
                    flow[event.stream_id]=flow.get(event.stream_id,0)+event.flow_controlled_length
        assert sorted(headers)==[1,3,5]
        assert all(dict(h)[':path']=='/parser.Tokenize/Proto'for h in headers.values())
        assert dict(headers[3])['x-refusal-shared']==dict(headers[5])['x-refusal-shared']=='dynamic-entry-from-refused-request'
        record=b'\0\0\0\0\r\x0a\x0bhello world'
        assert bodies=={s:record for s in(1,3,5)}and flow=={1:18,3:26,5:18}
        client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'));client.initiate_connection()
        for stream,h in headers.items():client.send_headers(stream,h);client.send_data(stream,record,end_stream=True)
        response={};ended=[];resets=[];window=[];decoded=[]
        for raw_hex in raw_frames:
            raw=bytes.fromhex(raw_hex);frame,size=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
            assert len(raw)==9+size;decoded.append(frame)
            if frame.type==8:window.append((frame.stream_id,frame.window_increment))
            if frame.type==3:resets.append((frame.stream_id,frame.error_code))
            for event in client.receive_data(raw):
                kind=type(event).__name__
                if kind=='ResponseReceived':assert event.headers==[(':status','200'),('content-type','application/grpc+proto')]
                if kind=='TrailersReceived':assert event.headers==[('grpc-status','0')]
                if kind=='DataReceived':response[event.stream_id]=response.get(event.stream_id,b'')+event.data
                if kind=='StreamEnded':ended.append(event.stream_id)
                assert kind!='ConnectionTerminated'
        assert response=={1:expected,5:expected}and ended==[1,5]and resets==[(3,7)]
        first=next(f for f in decoded if f.type in(1,3))
        assert (first.type,first.stream_id)==((1,1)if order=='gpu-first'else(3,3))
        assert accepted['held_wire_hex']==next(raw for raw in raw_frames if bytes.fromhex(raw)[3]in(1,3))
        assert all(stream==0 for stream,amount in window)
        layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
        capacity=layout[14]//128*(layout[18]+5)
        assert accepted['final_connection_credit']==capacity
        assert sum(amount for stream,amount in window)==capacity-65535+sum(flow.values())
        assert accepted['refused_data_flow_controlled_bytes']==26
        executions[order]=dict(run=run,actual_dma_ids=4,actual_generated_descriptors=4,
            first_held_frame_type=first.type,first_held_frame_stream=first.stream_id,
            held_wire_cycles=37,axis_promise_counts=counts,actual_connection_refund_and_grant_bytes=sum(a for s,a in window),
            native_requests_and_responses_rebuilt=True,complete_model_fixture_preserved=True)
        artifacts.update(p for p in folder.iterdir()if p.is_file())
    failed=root/'build/wsl-reports/raw_envelope_rpc_stream_refusal_v7_reset_first_20261122'
    assert read(failed/'launch.json')['exit_code']==1
    failed_test=(failed/'execution-sources'/test_name).read_bytes().decode()
    assert failed_test==current.replace(delay,'').replace("ORDER='gpu-first'","ORDER='reset-first'")
    failure_xml=ET.parse(failed/'results.xml');failures=failure_xml.findall('.//failure')
    assert len(failures)==1 and 'assert (0 or 0)'in(failures[0].text or'')
    artifacts.update((failed/'launch.json',failed/'inputs.json',failed/'results.xml',failed/'execution-sources'/test_name))
    result=dict(phase='rpc_refusal_gpu_both_actual_wire_orders_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(candidate/'generation.json'),directed_audit_key=directed['key'],executions=executions,
        exact_parser_modules=78,exact_tokenizer_modules=22,portable_memory_backend=True,
        held_actual_wire_offer_preserved=True,old_rpc_actual_dma_to_gpu_roundtrips_verified=True,
        actual_refused_padded_data_accounting_verified=True,shared_hpack_state_verified=True,
        corrected_test_observation_delay_cycles=2,original_premature_probe_failure_preserved=True,
        refusal_memory_faults_with_gpu_ownership_verified=False,retained_reset_verified=False,
        native_vendor_runtime_verified=False,full_protocol_fault_matrix_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in sorted(artifacts)},verifier_sha256=sha(Path(__file__)))
    if registered:result.update(candidate=args.candidate,registered_selection_unit_audit_key=selection_audit['key'],
        phase='registered_selection_gpu_both_actual_wire_orders_verified')
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-refusal-gpu-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    pointer='rpc-registered-select-gpu.json'if registered else'rpc-refusal-gpu.json'
    for p in(evidence/'audit.json',root/'build/validation'/pointer):
        p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],actual_wire_orders=len(executions))))


if __name__=='__main__':main()
