"""Semantic gRPC packets through the real directory, commit queue and Parser.

Expected text is derived with Python JSON decoding or independently packed
Protobuf fields. Closed/reused RPCs are tested before any payload may be read.
"""
import argparse
import json
from pathlib import Path
import random
import struct
from generate_serializer_vectors import varint


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261123);definitions=[];commands=[];tag=0xc2000000
    def define(mode=0,user=5,sid=1,base=0x6a0003,capacity=131072):
        i=len(definitions);definitions.append((user,sid,1000+i,0x62000000+i,base,capacity,65536,mode,0));return i
    def control(op,i=0,status=0):commands.append(('C',op,i,status))
    def frame(body):return struct.pack('!BI',0,len(body))+body
    def events(i,wire,eos=False):
        result=[(0,definitions[i][1],b)for b in wire]
        if eos:result.append((1,definitions[i][1],0))
        return result
    def packet(user,data,commit=True,errors=()):
        nonlocal tag
        current=tag;tag+=1;commands.append(('P',user,current,int(commit),list(data),list(errors)));return current
    def completion(i,t,ordinal=0,status=0,detail=0,memory=0,text=b'',application=None,generation=None):
        return(i,t,ordinal,status,detail,memory,text,definitions[i][2]if application is None else application,definitions[i][3]if generation is None else generation)
    def drain(items,client=-1,target=-1,probe=-1):commands.append(('A',client,target,probe,items))
    def body_for(mode,text):
        if mode:
            data=text.encode();return b'\x48\x01\x0a'+bytes(varint(len(data)))+data,data
        body=json.dumps({'ignored':[1,True,None],'prompt':text,'text':' tail'},ensure_ascii=rng.choice([True,False]),separators=(',',':')).encode()
        obj=json.loads(body);return body,(obj['prompt']+obj['text']).encode()
    samples=['','hello','café 中文 🙂 العربية','quote " slash \\ line\n tab\t nul\0','e\u0301','x'*257]
    for mode in[0,1]:
        for text in samples+[''.join(rng.choice(' abCD09é中🙂\n\\"')for _ in range(rng.randrange(90)))for _ in range(12)]:
            i=define(mode);control(4,i);control(0,i);body,text_bytes=body_for(mode,text)
            # Both incomplete prefix and body persist across real packets.
            wire=frame(body);p=0
            for cut in[1,2,7,len(wire)]:
                end=min(len(wire),p+cut)
                if end==p:break
                t=packet(5,events(i,wire[p:end],eos=end==len(wire)));p=end
            drain([completion(i,t,text=text_bytes)])
    # Empty extraction and a zero-byte Protobuf message still retire a lease
    # with one empty text packet; no payload read is required for the latter.
    for mode,body in[(0,b'{}'),(1,b'')]:
        control(4);i=define(mode);control(0,i);t=packet(5,events(i,frame(body),True));drain([completion(i,t)])
    # Interleaved same-connection streams, and equal IDs on different connections.
    control(4);a=define(0,5,1);b=define(1,5,3,0x6c0003);c=define(0,6,1,0x6e0003)
    for i in[a,b,c]:control(0,i)
    ab,at=body_for(0,'first');bb,bt=body_for(1,'second');cb,ct=body_for(0,'other connection')
    packet(5,events(a,frame(ab)[:3])+events(b,frame(bb)[:2]))
    tc=packet(6,events(c,frame(cb),True));drain([completion(c,tc,text=ct)])
    t=packet(5,events(b,frame(bb)[2:],True)+events(a,frame(ab)[3:],True))
    drain([completion(b,t,text=bt),completion(a,t,text=at)])
    # Multiple complete application messages in one committed packet.
    for mode in[0,1]:
        control(4);i=define(mode);control(0,i);items=[body_for(mode,f'message {j}')for j in range(7)]
        t=packet(5,events(i,b''.join(frame(body)for body,_ in items),True))
        drain([completion(i,t,j,text=text)for j,(_,text)in enumerate(items)])
    # A later malformed/compressed message closes the RPC. Its earlier valid
    # descriptor must be retired without reading a byte of the closed payload.
    for suffix,status,detail in[(b'\x02',13,7),(b'\x01\0\0\0\3zip',13,6)]:
        control(4);i=define();control(0,i)
        t=packet(5,events(i,frame(b'{"prompt":"must not escape"}')+suffix),errors=[(i,status,detail,0)])
        drain([completion(i,t,status=4,detail=1)])
    # Explicit CLOSE, followed by immediate physical allocation/slot reuse.
    control(4);old=define();new=define();control(0,old)
    t=packet(5,events(old,frame(b'{"prompt":"stale generation"}'),True))
    control(3,old);control(0,new)
    drain([completion(old,t,status=4,detail=2)])
    body,text=body_for(0,'new allocation');t=packet(5,events(new,frame(body),True));drain([completion(new,t,text=text)])
    # A successful Parser replay pins its payload through stalled text AND a
    # stalled completion. Concurrent CLOSE is accepted only after lease release.
    control(4);i=define();control(0,i);body,text=body_for(0,'lease '+('x'*257))
    t=packet(5,events(i,frame(body),True));drain([completion(i,t,text=text)],probe=i)
    control(1,i,3)
    # Packet abort produces no application completion and retires only its user.
    control(4);i=define();c=define(1,6,1,0x6c0003);control(0,i);control(0,c)
    packet(5,events(i,frame(b'{"prompt":"aborted"}'),True),commit=False)
    control(1,i,3);body,text=body_for(1,'surviving connection');t=packet(6,events(c,frame(body),True));drain([completion(c,t,text=text)])
    # Complete gRPC framing with invalid application syntax must yield no text.
    for mode,body in[(0,b'{"prompt":"x"}garbage'),(0,b'{"prompt":"\\ud800"}'),(1,b'\x0a\x05abc'),(1,b'\x0a\x01\xff')]:
        control(4);i=define(mode);control(0,i);t=packet(5,events(i,frame(body),True))
        drain([completion(i,t,status=3,detail=255)])
    # Read failures after syntactically valid first beats must still abort.
    json_prefix=b'{"prompt":"must not escape"}';json_body=json_prefix+b' '*(128-len(json_prefix))
    proto_prefix=b'\x0a\x0fmust not escape\x10\x80\x01';proto_body=proto_prefix+b'\x10\x00'*((128-len(proto_prefix))//2)
    assert len(proto_body)==128
    for mode,body in[(0,json_body),(1,proto_body)]:
        for target in[0,1,7,8,15]:
            control(4);i=define(mode);control(0,i);t=packet(5,events(i,frame(body),True))
            drain([completion(i,t,status=2,detail=0x81,memory=0x74)],client=4,target=target)
    # The directory lookup itself can fail before Parser admission. Exact-slot
    # maintenance then removes the uncertain RPC and later work recovers.
    control(4);i=define();control(0,i);t=packet(5,events(i,frame(b'{"prompt":"unread"}'),True))
    drain([completion(i,t,status=6,detail=2,memory=0x73)],client=0,target=0)
    control(5,i);control(1,i,3)
    # Corrupt acknowledged queue words through the actual memory command path.
    # Magic remains valid; live admission must reject each bounded-looking lie.
    for word,mask,value,status,detail in[
        (0,0xffff0000,0x77770000,5,2), # application identity
        (0,1<<63,1<<63,5,2),        # format
        (1,0xffffffff,65537,5,3),   # length limit / committed extent
        (1,0xffffffff00000000,9<<32,5,4), # future ordinal
        (2,0xffffffff,0x69ffff,5,3), # before allocation
        (2,0xffffffff00000000,0x11111111<<32,4,2), # generation
    ]:
        control(4);i=define();control(0,i);commands.append(('W',word,mask,value))
        t=packet(5,events(i,frame(b'{"prompt":"metadata must reject"}'),True))
        drain([completion(i,t,status=status,detail=detail,ordinal=9 if word==1 and mask>>32 else 0,
                          application=0x7777 if word==0 and mask==0xffff0000 else None,
                          generation=0x11111111 if word==2 and mask>>32 else None)])
    # Long ignored fields force replay beyond a single FIFO burst.
    control(4);i=define(1);control(0,i);commands.append(('W',2,0xffffffff,0x6a0003))
    t=packet(5,events(i,frame(b''),True));drain([completion(i,t,status=5,detail=3)])
    for mode in[0,1]:
        control(4);i=define(mode);control(0,i);text=b'large replay'
        if mode:body=b'\x4a'+bytes(varint(20000))+b'\xff'*20000+b'\x0a'+bytes(varint(len(text)))+text
        else:body=json.dumps({'ignored':'z'*20000,'prompt':text.decode()}).encode()
        t=packet(5,events(i,frame(body),True));drain([completion(i,t,text=text)])
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        stream.write(f'{len(definitions)}\n')
        for d in definitions:stream.write(' '.join(map(str,d))+'\n')
        for command in commands:
            if command[0]=='C':_,op,i,status=command;stream.write(f'0 {op} {i} {status}\n')
            elif command[0]=='P':
                _,user,t,commit,data,errors=command;stream.write(f'1 {user} {t} {commit} {len(data)} {len(errors)}\n')
                for event in data:stream.write(' '.join(map(str,event))+'\n')
                for error in errors:stream.write(' '.join(map(str,error))+'\n')
            elif command[0]=='A':
                _,client,target,probe,items=command;stream.write(f'2 {client} {target} {probe} {len(items)}\n')
                for i,t,ordinal,status,detail,memory,text,application,generation in items:
                    stream.write(f'{i} {t} {ordinal} {status} {detail} {memory} {len(text)} {application} {generation}\n'+' '.join(f'{b:02x}'for b in text)+'\n')
            else:_,word,mask,value=command;stream.write(f'3 {word} {mask:016x} {value:016x}\n')
    print(f'Generated {len(commands)} operations/{tag-0xc2000000} packets/{len(definitions)} admissions')


if __name__=='__main__':main()
