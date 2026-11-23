"""Audit the real private/FORMAT race and replay its actual DMA/inverse call."""
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
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--negative',required=True);args=ap.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9_]+',n) for n in (args.name,args.negative))
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original=read(root/'build/validation/json-simd-corpus.json');assert original['key']=='2509134d2630b47e'
    assemblies=[read(root/'build/validation'/n) for n in ('receive-capacity-v4-assembly.json','receive-capacity-assembly.json')]
    assert [a['key'] for a in assemblies]==['69a29b3c155b339f','c4cf022229153691']
    loaded=[]
    for name,assembly,passed in zip((args.name,args.negative),assemblies,(True,False)):
        launch=read(root/'build/validation'/(name+'-launch.json'))
        assert launch['profile']=='capacity-format-owner' and launch['candidate']==assembly['candidate']
        assert launch['exit_code']==(0 if passed else 1) and launch['phase']==('completed' if passed else 'failed')
        assert launch['generation_sha256']==assembly['generation_sha256']
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
        inputs=read(archive/'inputs.json');report=read(archive/'report.json')
        assert inputs==launch['inputs_sha256']==report['input_sha256'] and read(archive/'snapshot.json')['exit_code']==launch['exit_code']
        for n,h in inputs.items():assert sha(source/n)==h,n
        assert {n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}==assembly['executed_parser_sha256']
        assert {n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}==original['executed_tokenizer_sha256']
        for edit in launch['fixture_edits']:
            text=(source/edit['path']).read_bytes().decode()
            for before,after in reversed(edit['replacements']):
                assert text.count(after)==1;text=text.replace(after,before)
            assert hashlib.sha256(text.encode()).hexdigest()==edit['old_sha256']==original['inputs_sha256'][edit['path']]
        assert {n for n,h in original['inputs_sha256'].items() if inputs[n]!=h}==set(launch['changed_rtl'])|{e['path'] for e in launch['fixture_edits']}
        assert set(inputs)-set(original['inputs_sha256'])=={'rtl/grpc_payload_reclaimer.v','sim/cocotb/test_raw_open_rpc_credit.py',
            'sim/cocotb/test_raw_capacity_format_owner.py','tools/run_open_rpc_credit_wsl.py'}
        xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
        assert len(tests)==1 and tests[0].attrib['name']=='actual_format_serializes_with_private_owner_and_preserves_load_offer'
        if passed:
            assert report['phase']=='passed' and report['tests']==1 and report['failures']==0
            assert not xml.findall('.//failure') and not xml.findall('.//error')
        else:
            failures=xml.findall('.//failure');assert len(failures)==1 and report['phase']=='failed'
            assert 'assert sample==dict(control_valid=1,control_ready=0,forward_control_valid=0,private_lock=1,pool_lock=1,private_busy=1)' in failures[0].text
            assert "'control_valid': 0" in failures[0].text
        loaded.append((archive,source,inputs,report))
    archive,source,inputs,report=loaded[0];negative,negative_source,negative_inputs,_=loaded[1]
    assert {n for n,h in assemblies[0]['executed_parser_sha256'].items() if h!=assemblies[1]['executed_parser_sha256'][n]}=={'http2_enveloped_parser_core'}
    # The positive fixture adds only a read-only progress recorder after the
    # maintenance-authorized negative fixture. Reconstruct every original
    # stimulus and assertion, rather than allowing an arbitrary changed test.
    p='sim/cocotb/test_raw_capacity_format_owner.py';text=(source/p).read_text()
    start=text.index('    async def inspect_arbitration():');end=text.index('    await b.drain(',start)
    restored=(text[:start]+text[end:]).replace('    watching.cancel()\n','')
    assert restored==(negative_source/p).read_text()
    assert 'b.set(maintenance_grant=1)\n    formatting=cocotb.start_soon(b.directory(4))' in text
    for n,h in inputs.items():
        if n not in ('rtl/http2_enveloped_parser_core.v',p,'tools/run_open_rpc_credit_wsl.py'):assert h==negative_inputs[n],n
    accepted=read(archive/'acceptance.json');assert accepted['phase']=='passed' and sha(archive/'acceptance.json')==report['acceptance_sha256']
    expected_sample=dict(control_valid=1,control_ready=0,forward_control_valid=0,private_lock=1,pool_lock=1,private_busy=1)
    assert accepted['blocked_format_samples']==[expected_sample]*23
    layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
    assert layout[14]==384 and layout[18]==131072
    stream_capacity=layout[18]+5;capacity=layout[14]//128*stream_capacity
    wire=[bytes.fromhex(x) for x in read(archive/'wire_frames.json')]
    packets=read(archive/'ingress_packets.json');assert len(packets)==4
    assert [(p['user'],p['tag'],p['expected_commit']) for p in packets]==[(0,i,1) for i in range(1,5)]
    frames=[]
    for raw in wire:
        f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw;frames.append(f)
    assert len(wire)==10 and [(f.stream_id,f.window_increment) for f in frames if f.type==8]==[(1,65542),(0,327696),(3,65560),(0,18)]
    held=accepted['held_wire_snapshot'];assert held[0].to_bytes(64,'little')[:13]==wire[2] and held[1:]==[8191,1,0]
    assert accepted['held_memory_counters']['wire']==2
    after=accepted['after_actual_format'];assert after['wire']==[raw.hex() for raw in wire[:4]] and after['rpc_markers']==['0000000000000000']*3
    client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'));server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'))
    client.initiate_connection();server.initiate_connection();server.data_to_send()
    client.receive_data(wire[0]);assert client.data_to_send().hex()==packets[0]['raw_hex']
    server.receive_data(bytes.fromhex(packets[0]['raw_hex']));assert server.data_to_send()==wire[1];client.receive_data(wire[1])
    def headers(stream):
        client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    def receive_request(index):
        raw=client.data_to_send();assert raw.hex()==packets[index]['raw_hex'];return server.receive_data(raw)
    def credit(index,stream,amount):
        server.increment_flow_control_window(amount,stream_id=stream or None);assert server.data_to_send()==wire[index];client.receive_data(wire[index])
    headers(1);receive_request(1);credit(2,1,65542);credit(3,0,327696)
    record=b'\0\0\0\0\x0d\x0a\x0bhello world'
    headers(3);client.send_data(3,record)
    assert b''.join(e.data for e in receive_request(2) if type(e).__name__=='DataReceived')==record
    credit(4,3,65560);credit(5,0,18)
    assert client.outbound_flow_control_window==capacity and client.local_flow_control_window(3)==stream_capacity
    client.send_data(3,b'',end_stream=True);receive_request(3)
    events=[e for raw in wire[6:] for e in client.receive_data(raw)]
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    ids=encoding.encode_ordinary('hello world');assert ids==[15339,1917]
    expected=b''.join(b'\0'+(len(raw)+3).to_bytes(4,'big')+b'\x8a\x01'+bytes([len(raw)])+raw for token in ids for raw in [encoding.decode_single_token_bytes(token)])
    assert b''.join(e.data for e in events if type(e).__name__=='DataReceived')==expected
    assert sum(type(e).__name__=='StreamEnded' and e.stream_id==3 for e in events)==1
    assert next(e.headers for e in events if type(e).__name__=='TrailersReceived')==[('grpc-status','0')]
    assert accepted['actual_captured_dma_ids_returned']==ids and accepted['actual_generated_descriptors']==[[3,t,o,int(o==1)] for o,t in enumerate(ids)]
    assert accepted['byte_exact_response_hex']==expected.hex() and accepted['final_connection_credit']==capacity
    assert accepted['actual_existing_load_offer_retired'] and accepted['actual_dma_ack_reclaimed_record'] and accepted['model_prefixes_immutable']
    trace=read(archive/'receive_trace.json');assert not any(e['event']=='rx_result' and e['status'] for e in trace)
    assert sum(e['event']=='rx_request' and e['op']==11 for e in trace)==2
    result=dict(phase='actual_private_format_and_offered_control_serialization_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,negative_run=args.negative,assembly_audit_key=assemblies[0]['key'],negative_assembly_audit_key=assemblies[1]['key'],
        actual_private_lock_blocks_new_format=True,held_wire_and_memory_unchanged_cycles=23,
        earlier_control_and_command_complete_after_dma_ack=True,actual_dma_ack_reclaims_record=True,
        actual_dma_ids_returned=2,native_complete_grpc_calls=1,full_actual_ingress_and_wire_independently_replayed=True,
        complete_model_and_native_packages_preserved=True,negative_early_format_acceptance_preserved=True,
        whole_system_retained_reset_verified=False,full_protocol_fault_matrix_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p) for a in (archive,negative) for p in a.iterdir() if p.is_file()},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-capacity-format-owner-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in (evidence/'audit.json',root/'build/validation/receive-capacity-format-owner.json'):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','held_wire_and_memory_unchanged_cycles')}))


if __name__=='__main__':main()
