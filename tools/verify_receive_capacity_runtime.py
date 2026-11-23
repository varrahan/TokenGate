"""Independent full-wire, actual-DMA oracle for capacity-backed large RPCs."""
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


def verify(root,name,assembly):
    read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    launch=read(root/'build/validation'/(name+'-launch.json'))
    assert launch['phase']=='completed' and launch['exit_code']==0 and launch['candidate']==assembly['candidate']
    assert launch['generation_sha256']==assembly['generation_sha256']
    archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
    report=read(archive/'report.json');inputs=read(archive/'inputs.json');accepted=read(archive/'acceptance.json')
    assert report['phase']==accepted['phase']=='passed' and report['tests']==1 and report['failures']==0
    assert read(archive/'snapshot.json')['exit_code']==0
    assert inputs==launch['inputs_sha256']==report['input_sha256']
    assert sha(archive/'acceptance.json')==report['acceptance_sha256']
    for n,h in inputs.items():assert sha(source/n)==h,n
    assert {n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}==assembly['executed_parser_sha256']
    original=read(root/'build/validation/json-simd-corpus.json');assert original['key']=='2509134d2630b47e'
    assert {n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}==original['executed_tokenizer_sha256']
    assert sha(source/'tools/run_open_rpc_credit_wsl.py')==launch['driver_sha256']
    edits={e['path']:e for e in launch['fixture_edits']}
    assert set(edits)=={'sim/cocotb/test_http2_prefill.py','scripts/run_raw_envelope_tests.py'}
    for n,edit in edits.items():
        text=(source/n).read_bytes().decode()
        for before,after in reversed(edit['replacements']):
            assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.encode()).hexdigest()==edit['old_sha256']==original['inputs_sha256'][n]
    assert {n for n in original['inputs_sha256'] if inputs[n]!=original['inputs_sha256'][n]}==set(launch['changed_rtl'])|set(edits)
    for n,h in original['inputs_sha256'].items():
        if not n.startswith('rtl/') and n not in edits:assert inputs[n]==h,n
    multi=launch['profile']=='capacity-streams'
    reuse=launch['profile']=='capacity-large-reuse'
    assert launch['profile'] in ('capacity-streams','large-message-credit','capacity-large-reuse')
    module='test_raw_capacity_streams' if multi else 'test_raw_capacity_large_reuse' if reuse else 'test_raw_large_message_credit'
    assert set(inputs)-set(original['inputs_sha256'])=={'rtl/grpc_payload_reclaimer.v',
        'sim/cocotb/test_raw_open_rpc_credit.py','tools/run_open_rpc_credit_wsl.py','sim/cocotb/'+module+'.py'}
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['classname']==module and not xml.findall('.//failure') and not xml.findall('.//error')
    layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
    assert layout[18]==131072 and layout[14]//128==3
    stream_capacity=layout[18]+5;connection_capacity=3*stream_capacity
    body=(b'\x9a\x06\xc0\x3e'+b'U'*8000)*8+b'\x9a\x06\xcf\x0b'+b'U'*1487+b'\x0a\x0bhello world'
    record=b'\0'+len(body).to_bytes(4,'big')+body;assert len(body)==65536 and len(record)==65541
    streams=(1,3,5) if multi else (1,)
    requests=read(archive/'requests.json');packets=read(archive/'ingress_packets.json');wire=[bytes.fromhex(h) for h in read(archive/'wire_frames.json')]
    assert len(packets)==len(requests)+2 and [p['tag'] for p in packets]==list(range(1,len(packets)+1))
    assert all(p['user']==0 and p['expected_commit']==1 for p in packets)
    assert [p['raw_hex'] for p in packets[2:]]==[r['raw_hex'] for r in requests]
    expected_requests=([(s,o,8192,False) for o in range(0,65536,8192) for s in streams]+[(s,65536,5,True) for s in streams]) if multi else [(1,o,min(8192,len(record)-o),o+8192>=len(record)) for o in range(0,len(record),8192)]
    if reuse:
        expected_requests=[(1,o,min(8192,len(record)-o),m==2 and o+8192>=len(record)) for m in range(3) for o in range(0,len(record),8192)]
        assert [r['message'] for r in requests]==[m for m in range(3) for o in range(0,len(record),8192)]
    assert [(r.get('stream',1),r['offset'],r['data_bytes'],r['end_stream']) for r in requests]==expected_requests
    assert wire[:2]==[bytes.fromhex('000000040000000000'),bytes.fromhex('000000040100000000')]
    parsed=[]
    for raw in wire:
        f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw;parsed.append(f)
    initial_updates=[(1,stream_capacity-65535),(0,connection_capacity-65535)]+([(3,stream_capacity-65535),(5,stream_capacity-65535)] if multi else [])
    expected_updates=initial_updates+([(1,len(record)),(0,len(record))]*2 if reuse else [])+[(0,len(record)) for s in streams]
    assert [(f.stream_id,f.window_increment) for f in parsed if f.type==8]==expected_updates
    client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'));server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'))
    client.initiate_connection();server.initiate_connection();server.data_to_send()
    client.receive_data(wire[0]);assert client.data_to_send().hex()==packets[0]['raw_hex']
    server.receive_data(bytes.fromhex(packets[0]['raw_hex']));assert server.data_to_send()==wire[1];client.receive_data(wire[1])
    for s in streams:client.send_headers(s,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    assert client.data_to_send().hex()==packets[1]['raw_hex'];server.receive_data(bytes.fromhex(packets[1]['raw_hex']))
    index=2
    for s,amount in initial_updates:
        assert (parsed[index].type,parsed[index].stream_id,parsed[index].window_increment)==(8,s,amount)
        server.increment_flow_control_window(amount,stream_id=s or None);assert server.data_to_send()==wire[index]
        client.receive_data(wire[index]);index+=1
    sent={s:bytearray() for s in streams}
    reuse_flow=[]
    for request in requests:
        s=request.get('stream',1);offset=request['offset'];data=record[offset:offset+request['data_bytes']]
        client.send_data(s,data,end_stream=request['end_stream']);assert client.data_to_send().hex()==request['raw_hex']
        events=server.receive_data(bytes.fromhex(request['raw_hex']))
        assert b''.join(e.data for e in events if type(e).__name__=='DataReceived')==data
        sent[s].extend(data)
        if reuse and offset+len(data)==len(record):
            message=request['message']
            if message<2:
                for sid in (1,0):
                    assert (parsed[index].type,parsed[index].stream_id,parsed[index].window_increment)==(8,sid,len(record))
                    server.increment_flow_control_window(len(record),stream_id=sid or None)
                    assert server.data_to_send()==wire[index]
                    client.receive_data(wire[index]);index+=1
            reuse_flow.append(dict(connection_credit=client.outbound_flow_control_window,
                stream_credit=client.local_flow_control_window(1),wire_frame_count=index))
    assert all(bytes(data)==record*(3 if reuse else 1) for data in sent.values())
    events=[];refunds=0
    for raw,f in zip(wire[index:],parsed[index:]):
        if f.type==8:
            assert f.stream_id==0 and f.window_increment==len(record)
            server.increment_flow_control_window(len(record));assert server.data_to_send()==raw;refunds+=1
        events.extend(client.receive_data(raw))
    assert refunds==len(streams) and client.outbound_flow_control_window==server.inbound_flow_control_window==connection_capacity
    assert not any(type(e).__name__ in ('StreamReset','ConnectionTerminated') for e in events)
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    ids=encoding.encode_ordinary('hello world');assert ids==[15339,1917]
    returned_ids=ids*(3 if reuse else 1)
    expected_response=b''.join(b'\0'+(len(raw)+3).to_bytes(4,'big')+b'\x8a\x01'+bytes([len(raw)])+raw for token in returned_ids for raw in [encoding.decode_single_token_bytes(token)])
    for s in streams:
        assert sum(type(e).__name__=='ResponseReceived' and e.stream_id==s for e in events)==1
        assert sum(type(e).__name__=='TrailersReceived' and e.stream_id==s for e in events)==1
        assert sum(type(e).__name__=='StreamEnded' and e.stream_id==s for e in events)==1
        assert next(e.headers for e in events if type(e).__name__=='ResponseReceived' and e.stream_id==s)==[(':status','200'),('content-type','application/grpc+proto')]
        assert next(e.headers for e in events if type(e).__name__=='TrailersReceived' and e.stream_id==s)==[('grpc-status','0')]
        assert b''.join(e.data for e in events if type(e).__name__=='DataReceived' and e.stream_id==s)==expected_response
    if multi:
        assert accepted['actual_captured_dma_ids_returned']=={str(s):ids for s in streams}
        assert accepted['actual_generated_descriptors']==[[s,ids[o],o,int(o==1)] for o in range(2) for s in streams]
        partials=accepted['concurrent_partial_streams'];assert len(partials)==3
        assert len({p['record_address'] for p in partials})==len({p['payload_base'] for p in partials})==3
        for p,s in zip(partials,streams):
            assert p['stream']==s and p['generation']!=0 and p['message_length']==65536 and p['received_body_bytes']==65531
            slot=(p['record_address']-layout[13])//128
            assert slot in (0,1,2) and p['record_address']==layout[13]+128*slot
            assert p['payload_base']==layout[17]+layout[18]*slot
            assert p['partial_body_sha256']==hashlib.sha256(body[:65531]).hexdigest()
        assert accepted['byte_exact_response_hex']==expected_response.hex() and accepted['complete_model_prefixes_immutable']
        assert accepted['actual_application_data_bytes']==3*len(record) and accepted['explicit_host_directory_closes']==3
    elif reuse:
        assert accepted['actual_captured_dma_ids_returned']==returned_ids
        assert accepted['actual_generated_descriptors']==[[1,t,o,int(o==5)] for o,t in enumerate(returned_ids)]
        assert accepted['byte_exact_response_hex']==expected_response.hex() and accepted['complete_model_prefixes_immutable']
        assert accepted['complete_messages_acknowledged']==3 and accepted['actual_body_bytes']==3*len(body)>layout[18]
        assert accepted['actual_application_data_bytes']==3*len(record) and accepted['explicit_host_directory_closes']==1
        snapshots=accepted['reuse_snapshots'];assert len(snapshots)==3
        assert snapshots==read(archive/'reuse_progress.json')
        for m,(snapshot,flow) in enumerate(zip(snapshots,reuse_flow)):
            assert snapshot['message']==m and snapshot['record_address']==layout[13] and snapshot['payload_base']==layout[17]
            assert snapshot['payload_sha256']==hashlib.sha256(body).hexdigest()
            p=int.from_bytes(bytes.fromhex(snapshot['progress_hex']),'little')
            assert (p&0xffffffff,p>>32&0xffffffff,p>>64&0xffffffff,p>>96&0xffffffff,
                p>>128&0xffffffff,p>>160&7,p>>163&1,p>>164&1,p>>165&((1<<33)-1),p>>198)==(
                (0,0,0,0,m+1,0,0,0,m+1,0) if m<2 else (65536,65536,0,0,3,0,1,0,2,0))
            assert all(snapshot[k]==v for k,v in flow.items())
            assert snapshot['actual_messages']==m+1 and snapshot['actual_dma_ids']==2*(m+1) and snapshot['actual_generated_descriptors']==0
            assert snapshot['connection_credit']==connection_capacity-(len(record) if m==2 else 0)
    else:
        assert accepted['configured_message_limit']==len(body) and accepted['actual_message_body_bytes']==len(body)
        assert accepted['actual_captured_dma_ids_returned']==ids
        assert accepted['actual_gpu_descriptors']==[[1,t,o,int(o==1)] for o,t in enumerate(ids)]
        assert accepted['response_hex']==expected_response.hex() and accepted['response_sha256']==hashlib.sha256(expected_response).hexdigest()
        assert accepted['actual_data_bytes_sent']==len(record) and accepted['full_model_prefixes_immutable']
        assert accepted['explicit_host_close'] and accepted['configured_connection_capacity']==connection_capacity
    assert accepted['native_complete_grpc_calls']==len(streams) and accepted['final_connection_credit']==connection_capacity
    trace=read(archive/'receive_trace.json')
    assert any(e['event']=='rx_request' and e['op']==12 for e in trace)
    assert not any(e['event']=='rx_result' and (e['status'] or e['memory_status']) for e in trace)
    if reuse:
        # This observer records the ordinary receive controller, not the
        # private rc_credit mux input. Establish refund causality from actual
        # DATA debits, durable reclaimed ordinals and the exact wire prefix;
        # do not claim unrecorded private RELEASE handshakes.
        assert [(e['op'],e['stream'],e['amount']) for e in trace if e['event']=='rx_request']==[
            (11,0,0),(12,0,0),(1,1,0)]+[(2,1,r['data_bytes']) for r in requests]+[(9,1,0),(4,0,0)]
        assert sum(e['event']=='service_control_req' and e['op']==3 for e in trace)==1
        for snapshot in snapshots:
            prefix=trace[:snapshot['receive_trace_count']]
            assert sum(e['event']=='rx_request' and e['op']==2 for e in prefix)==9*(snapshot['message']+1)
            assert sum(e['amount'] for e in prefix if e['event']=='rx_request' and e['op']==2)==65541*(snapshot['message']+1)
            assert not any(e['event']=='service_control_req' and e['op']==3 for e in prefix)
            assert sum(e['event']=='service_control_req' and e['op']==4 for e in prefix)==1
    private_path=archive/'private_credit_trace.json'
    if launch['candidate']=='receive-capacity-v4':
        private=read(private_path);pending=None
        for i,e in enumerate(private):
            if e['event']=='request':
                assert pending is None and e['actual_private_and_shared_pool_locks'] and e['op'] in (3,4)
                pending=i
            else:
                assert e['event']=='result' and pending is not None and e['request']==pending
                assert e['status']==e['detail']==e['memory_status']==0 and e['clock']>=private[pending]['clock']
                pending=None
        assert pending is None
        releases=[e for e in private if e['event']=='request' and e['op']==3]
        if reuse:
            assert len(releases)==2 and all((e['user'],e['stream'],e['address'],e['amount'])==(0,1,layout[13],65541) for e in releases)
            assert len({e['generation'] for e in releases})==1 and releases[0]['generation']!=0
            for snapshot in snapshots:
                prefix=private[:snapshot['private_credit_trace_count']]
                assert sum(e['event']=='request' and e['op']==3 for e in prefix)==min(snapshot['message']+1,2)
        else:assert not releases
    count=3 if reuse else len(streams)
    return dict(run=name,native_complete_grpc_calls=len(streams),actual_application_bytes=count*len(record),
        actual_dma_ids_returned=2*count,concurrent_large_partial_streams=len(streams) if multi else 0,
        large_open_rpc_slot_reuse_verified=reuse,completed_messages=count,
        actual_window_update_frames=len(expected_updates),final_connection_credit=connection_capacity,
        full_actual_ingress_and_wire_replayed=True,independent_tiktoken_response_verified=True,
        actual_explicit_close_refunds_verified=True,actual_capacity_format_requests_verified=True,
        private_credit_handshakes_captured=private_path.exists(),
        input_manifest_sha256=sha(archive/'inputs.json'),acceptance_sha256=sha(archive/'acceptance.json'),
        wire_sha256=sha(archive/'wire_frames.json'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--names',nargs='+',required=True)
    ap.add_argument('--candidate',choices=('receive-capacity-v2','receive-capacity-v4'),default='receive-capacity-v2');args=ap.parse_args()
    assert len(set(args.names))==len(args.names) and all(re.fullmatch(r'[A-Za-z0-9_]+',n)for n in args.names)
    root=Path(__file__).resolve().parents[1]
    label='receive-capacity-v4' if args.candidate=='receive-capacity-v4' else 'receive-capacity'
    assembly=json.loads((root/'build/validation'/(label+'-assembly.json')).read_text())
    assert assembly['key']==('69a29b3c155b339f' if args.candidate=='receive-capacity-v4' else 'c4cf022229153691') and assembly['capacity_format_translation_tied_to_actual_initialization']
    result=dict(phase='receive_capacity_selected_application_workloads_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        assembly_audit_key=assembly['key'],executions={n:verify(root,n,assembly)for n in args.names},
        actual_parser_and_tokenizer_executed=True,typed_component_authority_replaced_by_actual_ownership=True,
        native_vendor_runtime_verified=False,whole_system_retained_reset_verified=False,
        full_protocol_fault_matrix_verified=False,native_timing_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result['original_64k_message_counterexample_resolved']=any(e['native_complete_grpc_calls']==1 for e in result['executions'].values())
    result['concurrent_large_partial_streams_verified']=any(e['concurrent_large_partial_streams']==3 for e in result['executions'].values())
    result['large_open_rpc_slot_reuse_verified']=any(e['large_open_rpc_slot_reuse_verified'] for e in result['executions'].values())
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-capacity-runtime-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in(evidence/'audit.json',root/'build/validation'/(label+'-runtime.json')):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','key','original_64k_message_counterexample_resolved','concurrent_large_partial_streams_verified')}))


if __name__=='__main__':main()
