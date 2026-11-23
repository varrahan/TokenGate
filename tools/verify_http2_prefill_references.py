"""Independently decode actual fixture wire bytes with hyper-h2 and tiktoken.

Run in the native reference environment. This verifies the oracle inputs,
not RTL execution, complete transport behavior or physical throughput.
"""
import argparse
from collections import deque
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived,DataReceived
from h2.exceptions import ProtocolError
import tiktoken


def protobuf_text(payload):
    assert payload and payload[0]==10,'Expected independent field-one string'
    length=shift=0;position=1
    while True:
        assert position<len(payload)and shift<70
        octet=payload[position];position+=1;length|=(octet&127)<<shift
        if octet<128:break
        shift+=7
    assert position+length==len(payload)
    return payload[position:].decode('utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];folder=args.fixtures
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(folder.parent/'tiktoken-cache'))
    metadata=json.loads((folder/'fixture_manifest.json').read_text())
    references=json.loads((folder/'reference_cases.json').read_text())['cases']
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    assert metadata['generator_sha256']==sha(root/'tools/generate_http2_prefill_vectors.py')
    model_folder=root/'build/scu35/image'
    model_manifest=json.loads((model_folder/'external_manifest.json').read_text())
    model=(model_folder/'external_memory.bin').read_bytes()
    loaded=b''.join(int(line,16).to_bytes(8,'little')for line in(folder/'memory.mem').read_text().splitlines())
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    assert len(model)==len(loaded)==model_manifest['image_bytes']==8388608
    assert sha(model_folder/'external_memory.bin')==metadata['image_sha256']==model_manifest['image_sha256']
    assert hashlib.sha256(loaded).hexdigest()==metadata['loaded_image_sha256']
    assert layout[6]==model_manifest['workspace_base']and loaded[:layout[6]]==model[:layout[6]]
    assert(layout[4],layout[5])==(model_manifest['trie']['nodes'],model_manifest['trie']['edges'])
    for region in model_manifest['regions']:
        assert hashlib.sha256(loaded[region['base']:region['base']+region['bytes']]).hexdigest()==region['sha256'],region['name']
    encoding=tiktoken.get_encoding('cl100k_base')
    native={};streams={};completed=deque();armed=False
    packets=messages=tokens=protocol_errors=route_errors=memory_errors=opens=0
    words=iter(map(int,(folder/'vectors.txt').read_text().split()))
    while (op:=next(words,None)) is not None:
        if op==0:
            user=next(words);connection=H2Connection(config=H2Configuration(client_side=False,header_encoding='utf-8'))
            connection.initiate_connection();native[user]=connection;opens+=1
            streams={key:state for key,state in streams.items()if key[0]!=user}
        elif op==1:
            user,tag,length,commit=(next(words)for _ in range(4));wire=bytes(next(words)for _ in range(length));packets+=1
            assert native.get(user)is not None,('Wire without OPEN',user,tag)
            protocol_failed=False
            try:events=native[user].receive_data(wire)
            except ProtocolError:
                protocol_failed=True;protocol_errors+=1;events=[]
            unknown=any(isinstance(event,RequestReceived)and dict(event.headers)[':path']not in
                        ('/parser.Tokenize/Json','/parser.Tokenize/Proto')for event in events)
            if unknown:route_errors+=1
            if not commit:
                assert protocol_failed or unknown or armed,('Unexplained failed packet',user,tag)
                if armed:memory_errors+=1;armed=False
                native[user]=None
                streams={key:state for key,state in streams.items()if key[0]!=user}
                completed=deque(item for item in completed if item[0]!=user)
                continue
            assert not protocol_failed and not unknown and not armed,('Unexpected accepted packet',user,tag)
            for event in events:
                if isinstance(event,RequestReceived):
                    headers=dict(event.headers);mode=0 if headers[':path'].endswith('/Json')else 1
                    assert headers['content-type']==('application/grpc+json'if mode==0 else'application/grpc+proto')
                    streams[user,event.stream_id]=[mode,bytearray()]
                elif isinstance(event,DataReceived):
                    mode,data=streams[user,event.stream_id];data.extend(event.data)
                    while len(data)>=5 and len(data)>=5+int.from_bytes(data[1:5],'big'):
                        assert data[0]==0,'Unexpected compressed reference message'
                        size=int.from_bytes(data[1:5],'big');payload=bytes(data[5:5+size]);del data[:5+size]
                        text=json.loads(payload)['prompt']if mode==0 else protobuf_text(payload)
                        assert isinstance(text,str)
                        completed.append((user,event.stream_id,100+mode,text))
        elif op==2:
            user,stream,application,count=(next(words)for _ in range(4))
            expected=[next(words)for _ in range(count)]
            assert completed,('Expected DMA result without a native gRPC message',user,stream)
            nu,ns,na,text=completed.popleft();assert(nu,ns,na)==(user,stream,application)
            actual=encoding.encode_ordinary(text);reference=references[messages]
            assert actual==expected==reference['token_ids'],('Native token mismatch',messages)
            assert text.encode().hex()==reference['prompt_utf8_hex']
            assert(user,stream,application)==(reference['connection'],reference['stream'],reference['application'])
            messages+=1;tokens+=len(actual)
        elif op==3:
            user,stream=next(words),next(words)
            assert not streams[user,stream][1],'Unconsumed gRPC bytes at directory CLOSE'
        elif op==4:
            client,target=next(words),next(words);assert not armed and 0<=client<20 and target>=0;armed=True
        else:raise AssertionError(('Unknown fixture operation',op))
    assert not completed and not armed and messages==len(references)
    assert(packets,messages,tokens,protocol_errors,route_errors,memory_errors,opens)==(38,16,2828,1,1,2,7)
    result=dict(phase='passed',finished_utc=datetime.now(timezone.utc).isoformat(),wire_packets=packets,
                grpc_messages=messages,native_token_ids=tokens,protocol_error_packets=protocol_errors,
                unknown_route_packets=route_errors,memory_fault_packets=memory_errors,
                independent_wire_decoder='hyper-h2',independent_application_decoders=['json','Protobuf field-one varint'],
                native_tokenizer='tiktoken cl100k_base encode_ordinary',
                complete_model_prefix_matches_image=True,model_prefix_bytes=layout[6],
                model_image_sha256=model_manifest['image_sha256'],
                model_manifest_sha256=sha(model_folder/'external_manifest.json'),
                model_regions_verified=len(model_manifest['regions']),
                model_trie_nodes=model_manifest['trie']['nodes'],model_trie_edges=model_manifest['trie']['edges'],
                model_ordinary_tokens=model_manifest['trie']['terminals'],
                packages={name:importlib.metadata.version(name)for name in('h2','hpack','hyperframe','tiktoken')},
                fixture_sha256={path.name:sha(path)for path in folder.iterdir()if path.is_file()and path.suffix in('.json','.txt','.mem')},
                verifier_sha256=sha(Path(__file__)),rtl_execution_verified=False,full_transport_verified=False)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'PASS: native hyper-h2 -> JSON/Protobuf -> tiktoken: {packets} wire packets/{messages} messages/{tokens} exact token IDs, four explained rejected packets')


if __name__=='__main__':main()
