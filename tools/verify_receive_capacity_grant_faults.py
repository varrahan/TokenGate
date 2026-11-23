"""Audit all actual initial-grant failures and replay the real small RPC."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import Frame
import tiktoken
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True)
    ap.add_argument('--candidate',choices=('receive-capacity-v2','receive-capacity-v4'),default='receive-capacity-v2');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    label='receive-capacity-v4' if args.candidate=='receive-capacity-v4' else 'receive-capacity'
    assembly=read(root/'build/validation'/(label+'-assembly.json'))
    assert assembly['key']==('69a29b3c155b339f' if args.candidate=='receive-capacity-v4' else 'c4cf022229153691')
    original=read(root/'build/validation/json-simd-corpus.json');assert original['key']=='2509134d2630b47e'
    launch_path=root/'build/validation'/(args.name+'-launch.json');launch=read(launch_path)
    assert launch['phase']=='completed' and launch['exit_code']==0 and launch['profile']=='capacity-grant-faults'
    assert launch['candidate']==args.candidate and launch['generation_sha256']==assembly['generation_sha256']
    archive=root/'build/wsl-reports'/('raw_envelope_'+args.name);source=archive/'execution-sources'
    accepted=read(archive/'acceptance.json');report=read(archive/'report.json');inputs=read(archive/'inputs.json')
    assert report['phase']==accepted['phase']=='passed' and report['tests']==1 and report['failures']==0
    assert read(archive/'snapshot.json')['exit_code']==0 and inputs==launch['inputs_sha256']==report['input_sha256']
    assert sha(archive/'acceptance.json')==report['acceptance_sha256']
    for n,h in inputs.items():assert sha(source/n)==h,n
    assert {n:sha(p)for n,p in closure('http2_enveloped_parser_application',source).items()}==assembly['executed_parser_sha256']
    assert {n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}==original['executed_tokenizer_sha256']
    assert sha(source/'tools/run_open_rpc_credit_wsl.py')==launch['driver_sha256']
    edits={e['path']:e for e in launch['fixture_edits']};assert set(edits)=={'sim/cocotb/test_http2_prefill.py','scripts/run_raw_envelope_tests.py'}
    for n,edit in edits.items():
        text=(source/n).read_bytes().decode()
        for before,after in reversed(edit['replacements']):assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.encode()).hexdigest()==edit['old_sha256']==original['inputs_sha256'][n]
    assert {n for n in original['inputs_sha256'] if inputs[n]!=original['inputs_sha256'][n]}==set(launch['changed_rtl'])|set(edits)
    assert set(inputs)-set(original['inputs_sha256'])=={'rtl/grpc_payload_reclaimer.v','tools/run_open_rpc_credit_wsl.py',
        'sim/cocotb/test_raw_open_rpc_credit.py','sim/cocotb/test_raw_reclaim_faults.py','sim/cocotb/test_raw_capacity_grant_faults.py'}
    for n,h in original['inputs_sha256'].items():
        if not n.startswith('rtl/') and n not in edits:assert inputs[n]==h,n
    test=(source/'sim/cocotb/test_raw_capacity_grant_faults.py').read_text()
    assert 'memory.parser.run(),memory.tokenizer.run()' in test and 'memory.run()' not in test
    xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='actual_initial_capacity_grant_ack_faults_retain_pool'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    assert accepted['complete_model_bytes']==8388608 and accepted['actual_committed_packet_and_shared_pool_authority']
    assert accepted['initial_grants_without_dma_or_release'] and accepted['complete_model_prefixes_immutable']
    layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
    rpc=layout[13];assert layout[14]==384 and layout[18]==131072
    stream_capacity=layout[18]+5;connection_capacity=3*stream_capacity
    success=accepted['success'];commands=success['actual_grant_commands'];responses=success['actual_grant_responses'];ops=success['actual_credit_commands']
    assert len(commands)==len(responses)==42 and responses==[dict(command=i,status=0)for i in range(42)]
    assert len(ops)==2 and ops[0][3]!=0
    assert ops==[[4,0,1,ops[0][3],rpc,0],[4,0,0,0,0,0]]
    preface=success['actual_preface_scan']
    assert preface['starts']==1 and preface['credit_commands']==[] and preface['successful_result']==[0,0,0]
    assert [(c['owner'],c['write'],c['address'],c['bytes'])for c in preface['commands']]==[('compactor',0,rpc+128*i,8)for i in range(3)]
    assert preface['responses']==[dict(command=i,status=0)for i in range(3)]
    assert [(c['owner'],c['write'],c['address'],c['bytes'])for c in commands[:8]]==[('compactor',0,rpc+8*i,8)for i in range(8)]
    assert [(c['owner'],c['write'],c['address'],c['bytes'])for c in commands[-2:]]==[('compactor',0,rpc+128*i,8)for i in (1,2)]
    assert all(c['owner']=='credit'for c in commands[8:40])
    writes=[(i,c['address'],c['bytes'],c['data'])for i,c in enumerate(commands)if c['write']]
    assert writes==[(25,0x7e6010,8,(stream_capacity-65535)<<32),
        (26,0x7e6008,8,(1<<32)|stream_capacity),(27,0x7e6010,8,0),
        (37,0x7e5010,8,(connection_capacity-65535)<<32),
        (38,0x7e5008,8,(stream_capacity<<32)|connection_capacity),(39,0x7e5010,8,0)]
    wire=[bytes.fromhex(h)for h in success['actual_wire_frames']];packets=success['actual_ingress_packets']
    assert len(packets)==3 and [p['tag']for p in packets]==[1,2,3] and all(p['user']==0 and p['expected_commit']==1 for p in packets)
    assert wire[:2]==[bytes.fromhex('000000040000000000'),bytes.fromhex('000000040100000000')]
    frames=[]
    for raw in wire:
        f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw;frames.append(f)
    assert [(f.stream_id,f.window_increment)for f in frames if f.type==8]==[(1,stream_capacity-65535),(0,connection_capacity-65535),(0,18)]
    assert success['actual_initial_window_updates']==[wire[2].hex(),wire[3].hex()]
    client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'));server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'))
    client.initiate_connection();server.initiate_connection();server.data_to_send();client.receive_data(wire[0])
    assert client.data_to_send().hex()==packets[0]['raw_hex'];server.receive_data(bytes.fromhex(packets[0]['raw_hex']))
    assert server.data_to_send()==wire[1];client.receive_data(wire[1])
    client.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    assert client.data_to_send().hex()==packets[1]['raw_hex'];server.receive_data(bytes.fromhex(packets[1]['raw_hex']))
    for i,s,amount in [(2,1,stream_capacity-65535),(3,0,connection_capacity-65535)]:
        server.increment_flow_control_window(amount,stream_id=s or None);assert server.data_to_send()==wire[i];client.receive_data(wire[i])
    data=b'\0\0\0\0\x0d\x0a\x0bhello world';assert len(data)==18
    client.send_data(1,data,end_stream=True);assert client.data_to_send().hex()==packets[2]['raw_hex']
    assert b''.join(e.data for e in server.receive_data(bytes.fromhex(packets[2]['raw_hex']))if type(e).__name__=='DataReceived')==data
    events=[]
    for raw,f in zip(wire[4:],frames[4:]):
        if f.type==8:server.increment_flow_control_window(18);assert server.data_to_send()==raw
        events.extend(client.receive_data(raw))
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    ids=encoding.encode_ordinary('hello world');assert ids==success['actual_captured_dma_ids_returned']==[15339,1917]
    response=b''.join(b'\0'+(len(raw)+3).to_bytes(4,'big')+b'\x8a\x01'+bytes([len(raw)])+raw for t in ids for raw in[encoding.decode_single_token_bytes(t)])
    assert b''.join(e.data for e in events if type(e).__name__=='DataReceived')==response
    assert response.hex()==success['byte_exact_response_hex'] and sum(type(e).__name__=='StreamEnded'for e in events)==1
    assert sum(type(e).__name__=='ResponseReceived'for e in events)==sum(type(e).__name__=='TrailersReceived'for e in events)==1
    assert not any(type(e).__name__ in('StreamReset','ConnectionTerminated')for e in events)
    assert client.outbound_flow_control_window==success['final_connection_credit']==connection_capacity and success['explicit_host_close']
    faults=accepted['every_actual_capacity_grant_ack_fault'];assert [f['phase']for f in faults]==list(range(42))
    for phase,fault in enumerate(faults):
        assert fault['actual_commands']==commands[:phase+1]
        assert fault['actual_responses']==[dict(command=i,status=0 if i<phase else 0x75)for i in range(phase+1)]
        assert fault['actual_error'][2]==0x75 and fault['actual_preface_scan']==preface
        assert fault['actual_pool_retained'] and fault['new_work_denied'] and fault['model_prefixes_immutable']
        updates=0 if phase<26 else 1 if phase<38 else 2
        assert fault['actual_window_updates']==success['actual_initial_window_updates'][:updates]
        assert fault['actual_credit_commands']==ops[:0 if phase<8 else 1 if phase<28 else 2]
    result=dict(phase='actual_receive_capacity_initial_grant_faults_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,assembly_audit_key=assembly['key'],exact_parser_modules=77,exact_tokenizer_modules=22,
        actual_initial_capacity_ack_faults=42,actual_pending_intent_wire_and_retirement_writes_verified=True,
        actual_preface_free_pool_scan_verified=True,no_dma_completion_or_release_used_for_initial_grants=True,
        actual_committed_stream_and_shared_pool_authority_verified=True,
        all_faults_retain_actual_pool_and_deny_new_work=True,actual_captured_dma_ids_returned=2,
        full_actual_ingress_and_wire_independently_replayed=True,explicit_host_close_refund_verified=True,
        large_message_deadlock_fixed=False,native_vendor_runtime_verified=False,whole_system_retained_reset_verified=False,
        full_protocol_fault_matrix_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in[launch_path,*[p for p in archive.iterdir()if p.is_file()]]},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-capacity-grant-faults-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in(evidence/'audit.json',root/'build/validation'/(label+'-grant-faults.json')):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','key','actual_initial_capacity_ack_faults')}))


if __name__=='__main__':main()
