"""gRPC wire -> staged messages -> actual JSON/Protobuf extraction references."""
import argparse
import json
from pathlib import Path
import random
import struct
from generate_serializer_vectors import varint


def proto_text(data):
    return b'\x0a'+bytes(varint(len(data)))+data


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);rng=random.Random(20261121)
    cases=[]
    def add(mode,messages,fault=-1):
        # Each item is (actual wire body, expected clean text, parse status).
        wire=b''.join(struct.pack('!BI',0,len(body))+body for body,_,_ in messages)
        expected=[]
        for ordinal,(body,text,status)in enumerate(messages):
            expected.append((ordinal,2 if fault>=0 else 3 if status else 0,0x81 if fault>=0 else status,0x62 if fault>=0 else 0,b'' if fault>=0 or status else text))
        cases.append((mode,wire,fault,expected))
    samples=['','hello','café 中文 🙂 العربية','quote " slash \\ line\n tab\t nul\0',
             '\u00e9 is literal text','e\u0301', 'x'*257]
    for mode in [0,1]:
        for text in samples:
            data=text.encode()
            if mode:body=proto_text(data);expected=data
            else:
                obj={'ignored':123,'prompt':text,'text':' tail'};body=json.dumps(obj,ensure_ascii=bool(len(text)%2),separators=(',',':')).encode()
                decoded=json.loads(body);expected=(decoded['prompt']+decoded['text']).encode()
            add(mode,[(body,expected,0)])
        add(mode,[(b'' if mode else b'{}',b'',0)])
        # Multiple messages per input sequence, with distinct append ranges.
        for _ in range(20):
            items=[]
            for _ in range(rng.randrange(2,6)):
                text=''.join(rng.choice(' abCD09é中🙂\n\\"')for _ in range(rng.randrange(0,100)))
                data=text.encode()
                if mode:body=proto_text(data)+b'\x48\x01';expected=data
                else:body=json.dumps({'prompt':text},ensure_ascii=rng.choice([0,1])).encode();expected=json.loads(body)['prompt'].encode()
                items.append((body,expected,0))
            add(mode,items)
    # Complete gRPC framing does not make malformed application syntax valid.
    for body in [b'',b'{',b'{"prompt":"x"}garbage',b'{"prompt":"\\ud800"}',b'{"prompt":"\xff"}']:
        add(0,[(body,b'',255)])
    for body in [b'\x0a',b'\x0a\x05abc',b'\x00',b'\x0a\x01\xff',b'\x80']:
        add(1,[(body,b'',255)])
    add(0,[(json.dumps({'prompt':'x'*1025}).encode(),b'',0x80)])
    add(1,[(proto_text(b'x'*1025),b'',0x80)])
    obj={'ignored':'z'*3000,'prompt':'replay stalls'}
    add(0,[(json.dumps(obj).encode(),json.loads(json.dumps(obj))['prompt'].encode(),0)])
    ignored=bytes(range(256))*11+b'\xff'*184
    add(1,[(b'\x4a'+bytes(varint(len(ignored)))+ignored+proto_text(b'replay stalls'),b'replay stalls',0)])
    # Both first 64-byte prefixes are syntactically complete. A later memory
    # error must still abort; inferring failure from syntax would miss these.
    json_prefix=b'{"prompt":"must not escape"}'
    json_body=json_prefix+b' '*(128-len(json_prefix))
    proto_prefix=proto_text(b'must not escape')+b'\x10\x80\x01'
    proto_body=proto_prefix+b'\x10\x00'*((128-len(proto_prefix))//2)
    assert len(proto_body)==128
    for mode,body in [(0,json_body),(1,proto_body)]:
        for target in range((len(body)+7)//8):add(mode,[(body,b'',0)],fault=target)
    # Recovery after errors uses the same cores and memory fabric, no reset.
    add(0,[(b'{"prompt":"recovered"}',b'recovered',0)])
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        for index,(mode,wire,fault,messages)in enumerate(cases):
            user=0x21+index%3;sid=1+2*(index%5);app=1000+index
            stream.write(f'{mode} {len(wire)} {fault} {len(messages)} {user} {sid} {app}\n')
            stream.write(' '.join(f'{b:02x}'for b in wire)+'\n')
            for ordinal,status,detail,memory,text in messages:
                stream.write(f'{ordinal} {status} {detail} {memory} {len(text)}\n'+' '.join(f'{b:02x}'for b in text)+'\n')
    print(f'Generated {len(cases)} gRPC/application sequences/{sum(len(m)for _,_,_,m in cases)} messages')


if __name__=='__main__':main()
