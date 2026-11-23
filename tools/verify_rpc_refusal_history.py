"""Audit actual closed-history reads, rejection status and both final banks."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import H2Error
from hyperframe.frame import Frame
import tiktoken

from verify_joint_hyperram_grpc_native import varint
from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    candidate=root/'build/experiments/rpc-stream-refusal-v7';generation=read(candidate/'generation.json')
    directed=read(root/'build/validation/rpc-stream-refusal-v7-directed.json')
    assert directed['key']=='950ce3b65ccb9b0a'and directed['generation_sha256']==sha(candidate/'generation.json')
    run='rpc_stream_refusal_v7_history_20261122';folder=root/'build/wsl-reports'/('raw_envelope_'+run)
    source=folder/'execution-sources';launch=read(folder/'launch.json');report=read(folder/'report.json')
    inputs=read(folder/'inputs.json');accepted=read(folder/'acceptance.json')
    assert launch['phase']=='completed'and launch['exit_code']==0 and launch['scenario']=='history'
    assert launch['generation_sha256']==sha(candidate/'generation.json')==sha(folder/'fence-generation.json')
    assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0
    assert inputs==launch['inputs_sha256']==report['input_sha256']
    assert all(sha(source/n)==h for n,h in inputs.items())
    assert sha(folder/'acceptance.json')==report['acceptance_sha256']
    assert sha(folder/'run_rpc_admission_fence_wsl.py')==launch['driver_sha256']
    assert {n:sha(p)for n,p in closure('http2_enveloped_parser_application',source).items()}==generation['non_mmio_parser_sha256']==launch['parser_sha256']
    tokenizer={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
    parent=root/'build/wsl-reports/raw_envelope_receive_capacity_v4_native_owner_admission_20261122'
    assert len(tokenizer)==22 and tokenizer==launch['tokenizer_sha256']=={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',parent/'execution-sources').items()}
    assert launch['parent_inputs_sha256']==read(parent/'inputs.json')
    for n,edit in launch['fixture_edits'].items():
        text=(source/n).read_bytes().decode();assert sha(source/n)==edit['after_sha256']
        for before,after in reversed(edit['replacements']):assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.encode()).hexdigest()==edit['before_sha256']
        if n in launch['parent_inputs_sha256']:assert edit['before_sha256']==launch['parent_inputs_sha256'][n]
    assert inputs['build/bidirectional-fixtures/memory.mem']==launch['parent_inputs_sha256']['build/bidirectional-fixtures/memory.mem']
    test='sim/cocotb/test_rpc_refusal_history.py';assert sha(source/test)==sha(root/test)
    xml=ET.parse(folder/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='actual_directory_binding_precedes_validated_closed_history'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
    initial=b''.join(int(word,16).to_bytes(8,'little')for word in(source/'build/bidirectional-fixtures/memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==read(source/'build/bidirectional-fixtures/fixture_manifest.json')['loaded_image_sha256']
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    ids=encoding.encode('hello world');assert ids==[15339,1917]
    response=b''
    for token in ids:
        text=encoding.decode_single_token_bytes(token);payload=varint(17<<3|2)+varint(len(text))+text
        response+=b'\0'+len(payload).to_bytes(4,'big')+payload
    modes=['active-binding','bad-magic','reserved-bit','future-stream','even-stream']
    assert [c['mode']for c in accepted['cases']]==modes
    results={}
    for case in accepted['cases']:
        mode=case['mode'];assert case==read(folder/('history-'+mode+'.json'))
        address=layout[19]+160;good=0x48325731|(3<<32)
        changed=good^1 if mode in('active-binding','bad-magic')else good|(1<<63)if mode=='reserved-bit'else good
        assert case['history_address']==address and int(case['history_before_hex'],16)==good and int(case['history_probe_hex'],16)==changed
        trace=case['trace'];assert not trace['active']and not trace['drop_observed']
        cs=trace['commands'];rs=trace['responses'];assert len(cs)==len(rs)
        assert [c['index']for c in cs]==[r['index']for r in rs]==list(range(len(cs)))
        assert all(r['status']==0 for r in rs)and not any(r['discarded']for r in trace['results'])
        for c,r in zip(cs,rs):assert c['clock']<r['clock']and c['bytes']==8
        debits=[c for c in cs if c['flow_operation']==1 and not c['private_owner']]
        history=[c for c in debits if c['address']==address]
        result=case['result'];assert result['packet_memory_status']==result['receive_fault_memory_status']==0
        assert case['held_packet_result_cycles']==17
        if mode=='active-binding':
            assert result['packet_committed']==1 and result['receive_fault_valid']==result['receive_recovery_required']==0
            assert not history and trace['results']==[dict(clock=trace['results'][0]['clock'],discarded=0,status=0,detail=0,memory_status=0)]
            assert case['actual_captured_dma_ids_returned']==ids
            assert case['actual_generated_descriptors']==[[1,t,i,int(i==1)]for i,t in enumerate(ids)]
            assert case['response_records_hex']=={'1':response.hex()}
        else:
            assert result['packet_committed']==0 and result['receive_fault_valid']==1 and result['receive_fault_http2_error']==2
            assert (result['receive_fault_status'],result['receive_fault_detail'])==((5,23)if mode in('bad-magic','reserved-bit')else(3,10))
            assert result['receive_recovery_required']==int(mode in('bad-magic','reserved-bit'))
            assert len(history)==1 and history[0]['write']==0 and history[0]['backend_state']==11
            assert int(rs[history[0]['index']]['data_hex'],16)==changed
            assert not any(c['write']for c in debits)
            assert case['actual_captured_dma_ids_returned']==case['actual_generated_descriptors']==[]
            assert case['response_records_hex']=={}
        assert [(h['stream'],h['header_status'],h['header_http2_error'])for h in case['header_rejections']]==[(3,4,7)]
        packets=case['ingress_packets'];assert len(packets)==(6 if mode=='active-binding'else 5)
        server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'));server.initiate_connection()
        requests=[];body={};invalid_error=False
        for packet in packets:
            try:events=server.receive_data(bytes.fromhex(packet['raw_hex']))
            except H2Error:
                assert mode in('future-stream','even-stream')and packet['tag']==5;invalid_error=True;continue
            for e in events:
                if type(e).__name__=='RequestReceived':requests.append(e.stream_id)
                if type(e).__name__=='DataReceived':body[e.stream_id]=body.get(e.stream_id,b'')+e.data
        assert requests==[1,3]and invalid_error==(mode in('future-stream','even-stream'))
        probe=bytes.fromhex(case['actual_probe_packet_hex']);frame,size=Frame.parse_frame_header(memoryview(probe[:9]));frame.parse_body(memoryview(probe[9:]))
        assert frame.type==0 and frame.stream_id==({'active-binding':1,'future-stream':5,'even-stream':2}.get(mode,3))
        assert frame.data==(b'hello world'if mode=='active-binding'else b'\0\0\0\0\r\x0a\x0bhello world')
        assert len(probe)==9+size
        decoded=[]
        for raw_hex in case['wire_frames']:
            raw=bytes.fromhex(raw_hex);f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert len(raw)==9+size;decoded.append(f)
        assert [(f.stream_id,f.error_code)for f in decoded if f.type==3]==[(3,7)]
        if mode!='active-binding':
            reset=next(i for i,f in enumerate(decoded)if f.type==3)
            assert all(f.type!=8 for f in decoded[reset+1:])
            goaway=[f for f in decoded if f.type==7]
            assert len(goaway)==int(mode in('future-stream','even-stream'))
            assert all(f.last_stream_id==3 and f.error_code==2 for f in goaway)
        banks={}
        for side in('parser','tokenizer'):
            path=folder/('history-'+mode+'-'+side+'-final.bin');bank=path.read_bytes()
            assert len(bank)==8388608 and bank[:layout[6]]==initial[:layout[6]]
            banks[side]=dict(sha256=sha(path),protected_model_prefix_sha256=hashlib.sha256(bank[:layout[6]]).hexdigest())
            if side=='parser':
                assert int.from_bytes(bank[address:address+8],'little')==(good if mode=='active-binding'else changed)
                banks[side]['final_first_rpc_header_hex']=bank[layout[13]:layout[13]+8].hex()
        results[mode]=dict(status=result['receive_fault_status'],detail=result['receive_fault_detail'],
            recovery_required=result['receive_recovery_required'],actual_history_read_count=len(history),
            actual_memory_commands=len(cs),all_memory_response_statuses_zero=True,final_banks=banks)
    result=dict(phase='rpc_refusal_five_closed_history_policy_cases_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=run,generation_sha256=sha(candidate/'generation.json'),directed_audit_key=directed['key'],cases=results,
        exact_parser_modules=78,exact_tokenizer_modules=22,full_final_bank_bytes_each=8388608,
        active_binding_precedes_history_verified=True,malformed_history_quarantined=True,
        future_and_even_streams_never_discard_authorized=True,actual_read_data_and_statuses_verified=True,
        protected_model_bytes_in_both_final_banks_verified=True,invalid_peer_frames_independently_rejected=True,
        direct_test_memory_corruption_and_repair=True,production_retained_recovery_verified=False,
        native_vendor_runtime_verified=False,full_protocol_fault_matrix_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in folder.iterdir()if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-refusal-history-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in(evidence/'audit.json',root/'build/validation/rpc-refusal-history.json'):
        p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],actual_policy_cases=5)))


if __name__=='__main__':main()
