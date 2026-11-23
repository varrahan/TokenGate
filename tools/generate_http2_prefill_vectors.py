"""Raw HTTP/2/gRPC -> complete cl100k DMA references and disjoint policy/work."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import struct

import hpack
from hyperframe.frame import DataFrame,HeadersFrame,SettingsFrame,ContinuationFrame
import tiktoken
from runtime_memory_plan import Limits,runtime_plan


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image-directory',type=Path,default=Path(__file__).resolve().parents[1]/'build/scu35/image')
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(out.parent/'tiktoken-cache'))
    manifest=json.loads((args.image_directory/'external_manifest.json').read_text())
    image=(args.image_directory/'external_memory.bin').read_bytes()
    plan=runtime_plan(manifest,image,Limits(3,3,131072,16384,16384,32768,4096,16,2,1024))
    transport=plan['transport'];policy=transport['route_table'];keys=transport['route_strings'];loaded=bytearray(image)
    paths=[b'/parser.Tokenize/Json',b'/parser.Tokenize/Proto'];cursor=keys['base']
    for i,path in enumerate(paths):
        # Header ABI: format bit 0 Protobuf, bit 1 JSON.
        struct.pack_into('<8I',loaded,policy['base']+32*i,cursor,len(path),100+i|((1<<(1-i))<<16),65536,9,23,0,0)
        loaded[cursor:cursor+len(path)]=path;cursor+=len(path)
    config=plan['tokenizer_config'];pool=transport['stream_pool'];queue=transport['descriptor_queue'];payload=transport['rpc_payloads']
    layout=config+[pool['base'],pool['bytes'],queue['base'],queue['bytes'],payload[0]['base'],payload[0]['bytes'],
                   transport['context_pool']['base'],transport['context_pool']['bytes'],policy['base'],policy['bytes'],keys['base'],keys['bytes'],2,23,9]
    for connection in transport['connections']:
        for name in['header_buffer','hpack_table','header_scratch']:layout.extend([connection[name]['base'],connection[name]['bytes']])
    (out/'layout.txt').write_text(' '.join(map(str,layout))+'\n')
    (out/'runtime_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    with(out/'memory.mem').open('w')as stream:
        for offset in range(0,len(loaded),8):stream.write(f"{int.from_bytes(loaded[offset:offset+8],'little'):016x}\n")
    enc=tiktoken.get_encoding('cl100k_base');encoders=[hpack.Encoder()for _ in range(3)]
    commands=[];references=[];expected_ids=0;messages=0;packet_count=0;header_count=0;tag=0x12340000
    def opening(user):
        encoders[user]=hpack.Encoder();commands.append((0,[user],[]))
        packet(user,b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'+SettingsFrame().serialize())
    def packet(user,wire,commit=1):
        nonlocal tag,packet_count
        commands.append((1,[user,tag,len(wire),commit],wire));tag+=1;packet_count+=1
    def headers(user,sid,mode,wire_length,end=False,trailer=False,path=None,split=False):
        nonlocal header_count
        fields=[(b'x-finish',b'yes')]if trailer else[(b':method',b'POST'),(b':scheme',b'https'),(b':path',path or paths[mode]),
                 (b':authority',b'parser.test'),(b'content-type',b'application/grpc+json'if mode==0 else b'application/grpc+proto'),
                 (b'te',b'trailers'),(b'content-length',str(wire_length).encode()),(b'grpc-timeout',b'100m')]
        encoded=encoders[user].encode(fields,huffman=bool(header_count%2));h=HeadersFrame(sid);h.data=encoded
        if end:h.flags.add('END_STREAM')
        header_count+=1
        if split:
            h.data=encoded[:len(encoded)//2];c=ContinuationFrame(sid);c.data=encoded[len(encoded)//2:];c.flags.add('END_HEADERS')
            return h.serialize()+c.serialize()
        h.flags.add('END_HEADERS');return h.serialize()
    def data(sid,body,end=True,padded=False):
        frame=DataFrame(sid);frame.data=body
        if end:frame.flags.add('END_STREAM')
        if padded:frame.flags.add('PADDED');frame.pad_length=7
        return frame.serialize()
    def body(text,mode):
        raw=text.encode();payload=json.dumps({'prompt':text},ensure_ascii=False,separators=(',',':')).encode()if mode==0 else b'\x0a'+varint(len(raw))+raw
        return struct.pack('!BI',0,len(payload))+payload
    def expected(user,sid,text,mode):
        nonlocal expected_ids,messages
        ids=enc.encode_ordinary(text);expected_ids+=len(ids);messages+=1
        commands.append((2,[user,sid,100+mode,len(ids)],ids))
        references.append({'connection':user,'stream':sid,'application':100+mode,
                           'prompt_utf8_hex':text.encode().hex(),'token_ids':ids})
    def close(user,sid):commands.append((3,[user,sid],[]))
    for user in range(3):opening(user)
    for index,text in enumerate(['hello world','café 中文 🙂','one\n"two"\t\\three','a'*140,'Καλημέρα κόσμε','한국어 日本語','\0'*40,'space  \r\n  end']):
        user=index%3;sid=1+2*(index//3);mode=index%2;wire=body(text,mode)
        raw=headers(user,sid,mode,len(wire),split=index%3==1)+data(sid,wire,padded=index%2==0)
        # DMA fragments split frame headers, HPACK and gRPC prefixes, with
        # persistent connection/HPACK state and sparse AXI lanes in the bench.
        if index%2:
            for left,right in zip([0,1,8,25],[1,8,25,len(raw)]):packet(user,raw[left:right])
        else:packet(user,raw)
        expected(user,sid,text,mode);close(user,sid)
    # Two RPCs opened and interleaved in one actual DMA packet. The later
    # stream starts DATA first but its message completes second.
    u=0;a=21;b=23;ta='first interleaved';tb='second stream 🙂';wa=body(ta,0);wb=body(tb,1)
    packet(u,headers(u,a,0,len(wa))+headers(u,b,1,len(wb))+data(b,wb[:7],False)+data(a,wa)+data(b,wb[7:]))
    expected(u,a,ta,0);expected(u,b,tb,1);close(u,a);close(u,b)
    # Trailers END_STREAM inject EOS only after their live binding is restored.
    u=1;sid=21;text='trailing metadata';wire=body(text,0)
    packet(u,headers(u,sid,0,len(wire))+data(sid,wire,False)+headers(u,sid,0,0,True,True))
    expected(u,sid,text,0);close(u,sid)
    # A valid tentative message followed by an invalid PING must publish no
    # descriptor/token. Packet abort retires every RPC for this connection.
    u=2;sid=21;wire=body('must never reach DMA',0)
    packet(u,headers(u,sid,0,len(wire))+data(sid,wire)+b'\x00\x00\x07\x06\x00\x00\x00\x00\x00'+b'1234567',0)
    opening(u)
    wire=body('after raw protocol abort',1);packet(u,headers(u,1,1,len(wire))+data(1,wire));expected(u,1,'after raw protocol abort',1);close(u,1)
    # Unknown route cannot authorize following DATA. This first integrated
    # controller conservatively aborts/retire the connection on header errors.
    packet(0,headers(0,25,0,0,path=b'/unknown.Service/Method'),0);opening(0)
    wire=body('after rejected path',0);packet(0,headers(0,1,0,len(wire))+data(1,wire));expected(0,1,'after rejected path',0);close(0,1)
    # Exercise failures through the joined memory fabric, then recover via
    # real connection reset/empty-directory checks and a new successful RPC.
    for number,(client,target)in enumerate([(19,4),(17,0)]):
        user=2;sid=3;wire=body('discard failed admission',0)
        commands.append((4,[client,target],[]))
        packet(user,headers(user,sid,0,len(wire))+data(sid,wire),0)
        opening(user);text=f'after shared memory fault {number}';wire=body(text,number%2)
        packet(user,headers(user,1,number%2,len(wire))+data(1,wire));expected(user,1,text,number%2);close(user,1)
    # Use production Parser capacities, not the earlier 1 KiB bench variant.
    # Many independently pretokenized words exercise the complete 16 KiB text
    # staging path without hiding a quadratic single-piece BPE workload.
    user=1;sid=23;text='hello '*2700;wire=body(text,0)
    packet(user,headers(user,sid,0,len(wire))+data(sid,wire));expected(user,sid,text,0);close(user,sid)
    with(out/'vectors.txt').open('w')as stream:
        for op,fields,values in commands:
            stream.write(str(op)+' '+' '.join(map(str,fields))+'\n')
            if values:stream.write(' '.join(map(str,values))+'\n')
    metadata={'raw_http2':True,'image_sha256':hashlib.sha256(image).hexdigest(),'loaded_image_sha256':hashlib.sha256(loaded).hexdigest(),
              'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'packets':packet_count,'headers':header_count,'messages':messages,'exact_token_ids':expected_ids,'memory_faults':2,
              'parser_max_text_bytes':16384,'parser_max_field_bytes':16384,'largest_prompt_utf8_bytes':len(text.encode()),
              'packages':{p:importlib.metadata.version(p)for p in['tiktoken','hpack','hyperframe']},
              'full_transport_verified':False,'full_system_verified':False}
    (out/'fixture_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'reference_cases.json').write_text(json.dumps({'encoding':'cl100k_base','method':'encode_ordinary',
        'tiktoken_version':importlib.metadata.version('tiktoken'),'cases':references},indent=2)+'\n')
    print(f'Generated raw HTTP/2 full-model prefill: {packet_count} packets/{header_count} headers/{messages} messages/{expected_ids} exact token IDs')


def varint(value):
    result=bytearray()
    while value>=128:result.append((value&127)|128);value>>=7
    result.append(value);return bytes(result)


if __name__=='__main__':main()
