"""gRPC message boundaries from struct-packed wire and independently sliced prefixes.

This unit corpus supplies saved stream progress, not HTTP/2 frame boundaries.
Full HTTP/2/stream-scheduler/application integration is a separate requirement.
"""
import argparse
from pathlib import Path
import random
import struct


def record(used=0, offset=0, length=0, received=0, ordinal=0, phase=0, ended=False, exhausted=False):
    return int.from_bytes(struct.pack('<8I', used, offset, length, received, ordinal,
                                     phase | (int(ended) << 3) | (int(exhausted) << 4), 0, 0), 'little')


def prefix_result(wire, base, cap, limit, encoding=False, eos=False, initial_ordinal=0):
    """Scan complete length-prefixed records; derive the incomplete suffix by slicing."""
    cursor=used=0;messages=[];phase=length=received=0;offset=0;status=detail=0
    while cursor < len(wire):
        if initial_ordinal+len(messages) > 0xffffffff:status,detail=8,9;break
        flag=wire[cursor]
        if flag > 1:status,detail=13,7;break
        if flag:status,detail=(12 if encoding else 13),6;break
        suffix=wire[cursor:];offset=used
        if len(suffix) < 5:
            phase=len(suffix);length=int.from_bytes(suffix[1:], 'big');received=0;break
        _,length=struct.unpack('!BI',suffix[:5]);phase=5
        if length > limit or used+length > cap:status,detail=8,3;break
        received=min(length,len(suffix)-5)
        if received < length:used+=received;break
        payload=suffix[5:5+length]
        messages.append((base+used if length else 0,length,initial_ordinal+len(messages),payload))
        used+=length;cursor+=5+length;offset=used;phase=length=received=0
    if not status and eos and phase:status,detail=13,4
    ordinal=min(0xffffffff,initial_ordinal+len(messages))
    final=0 if status else record(used,offset,length,received,ordinal,phase,eos,
                                  initial_ordinal+len(messages)>0xffffffff)
    return status,detail,final,messages


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261120);cases=[];segments=messages_total=0
    configs=[(5,1,100,0x100003,131072),(5,3,101,0x140007,131072),(6,1,102,0x180009,131072)]
    progress=[b'',b'',b''];states=[0,0,0];emitted=[0,0,0]
    def emit(slot,wire=b'',*,fresh=False,eos=False,limit=131072,encoding=0,cap=None,base=None,
             initial=None,status=None,detail=0,memstatus=0,fault=-1,events=None,expected_messages=None,
             final=None,initial_ordinal=0):
        nonlocal segments,messages_total
        user,stream,app,default_base,default_cap=configs[slot]
        base=default_base if base is None else base;cap=default_cap if cap is None else cap
        if fresh:progress[slot]=b'';states[slot]=0 if initial is None else initial;emitted[slot]=0
        before=states[slot];progress[slot]+=wire
        reference_status,reference_detail,reference_final,decoded=prefix_result(progress[slot],base,cap,limit,encoding,eos,initial_ordinal)
        new_messages=decoded[emitted[slot]:] if expected_messages is None else expected_messages
        if status is None:status,detail=reference_status,reference_detail
        if final is None:final=reference_final if status==0 else 0
        input_events=[(0,b,user,stream)for b in wire] if events is None else list(events)
        if eos:input_events.append((1,0,user,stream))
        fields=[slot,int(fresh),user,stream,app,base,cap,limit,encoding,len(input_events),status,detail,memstatus,fault,len(new_messages)]
        cases.append((fields,before,final,input_events,new_messages));segments+=1;messages_total+=len(new_messages)
        states[slot]=final;emitted[slot]=len(decoded)
    # Every possible division of a representative prefix/payload, including
    # finish while incomplete. The first byte of a message is not a frame tag.
    wire=struct.pack('!BI',0,9)+b'hello\x00RPC'
    for cut in range(len(wire)+1):
        emit(0,wire[:cut],fresh=True);emit(0,wire[cut:],eos=True)
    # Arbitrarily interleave three streams, including identical stream IDs on
    # different connections. Each contains empty and nonempty messages.
    streams=[]
    for slot in range(3):
        payloads=[b'',b'a',b'\x00\xff',bytes(range(256)),b'\xe2\x82\xac'*31]
        payloads += [rng.randbytes(rng.randrange(0,120))for _ in range(40)]
        streams.append(b''.join(struct.pack('!BI',0,len(p))+p for p in payloads))
        emit(slot,fresh=True)
    positions=[0,0,0]
    while any(positions[i]<len(streams[i])for i in range(3)):
        slot=rng.choice([i for i in range(3)if positions[i]<len(streams[i])]);begin=positions[slot]
        positions[slot]=min(len(streams[slot]),begin+rng.choice([1,2,3,4,5,7,31,64,257]))
        emit(slot,streams[slot][begin:positions[slot]],eos=positions[slot]==len(streams[slot]))
    # Large binary payload crosses 16-bit lengths and external cache lines.
    payload=rng.randbytes(65537);wire=struct.pack('!BI',0,len(payload))+payload
    emit(0,wire[:4],fresh=True);emit(0,wire[4:4093]);emit(0,wire[4093:32777]);emit(0,wire[32777:],eos=True)
    # Length and allocation edges are checked before payload writes.
    for size in [0,1,7,8,9,255,256,257]:
        payload=rng.randbytes(size);wire=struct.pack('!BI',0,size)+payload
        emit(1,wire,fresh=True,cap=size,limit=size,eos=True)
        if size:emit(1,struct.pack('!BI',0,size)+payload,fresh=True,cap=size-1,limit=size,eos=True)
        if size:emit(1,struct.pack('!BI',0,size)+payload,fresh=True,cap=size,limit=size-1,eos=True)
    for size in [0x10000,0x800000,0x7fffffff,0xffffffff]:
        emit(0,struct.pack('!BI',0,size)+b'bad',fresh=True,eos=True)
    # Append accounting must include earlier messages, never overwrite a lease.
    emit(1,b'\0\0\0\0\3abc\0\0\0\0\3def',fresh=True,cap=5,eos=True)
    # All prefix truncations and payload truncations, clean empty EOS, repeated
    # EOS and bytes after an already closed stream.
    for size in range(1,14):emit(2,(struct.pack('!BI',0,9)+b'123456789')[:size],fresh=True,eos=True)
    emit(2,fresh=True,eos=True)
    emit(2,events=[(1,0,6,1)],status=13,detail=8,final=0)
    emit(2,fresh=True,eos=True);emit(2,b'\0',status=13,detail=8,final=0)
    for flag in [1,2,3,127,255]:
        for encoding in [0,1]:emit(0,bytes([flag])+b'\0\0\0\3abc',fresh=True,encoding=encoding,eos=True)
    # Context, kind and corrupt saved-state/configuration rejection.
    emit(0,fresh=True,events=[(0,0,4,1)],status=13,detail=2)
    emit(0,fresh=True,events=[(0,0,5,3)],status=13,detail=2)
    emit(0,fresh=True,events=[(2,0,5,1)],status=13,detail=10)
    for initial in [1<<255,record(phase=6),record(used=131073),record(offset=1),
                    record(length=1),record(length=1,phase=5,received=1),record(phase=1,ended=True)]:
        emit(0,fresh=True,initial=initial,status=13,detail=1,expected_messages=[],final=0)
    emit(0,fresh=True,base=0x7fffff,cap=2,status=13,detail=1)
    # Ordinal rollover cannot alias message zero.
    emit(0,b'\0\0\0\0\0',fresh=True,initial=record(ordinal=0xffffffff),initial_ordinal=0xffffffff)
    emit(0,b'\0',status=8,detail=9,expected_messages=[],final=0)
    # Fault each payload write, including after a preceding successful lease.
    for target in range(12):
        before_payload=b'abc';second=b'123456789'
        wire=struct.pack('!BI',0,3)+before_payload+struct.pack('!BI',0,9)+second
        expected=[] if target<3 else [(configs[0][3],3,0,before_payload)]
        emit(0,wire,fresh=True,eos=True,status=13,detail=5,memstatus=0x51,fault=target,expected_messages=expected,final=0)
    # Fresh stream recovery after faults, without resetting shared hardware.
    emit(0,b'\0\0\0\0\3RPC',fresh=True,eos=True)
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        for fields,before,after,events,messages in cases:
            stream.write(' '.join(map(str,fields))+f' {before:064x} {after:064x}\n')
            for event in events:stream.write(' '.join(map(str,event))+'\n')
            for base,size,ordinal,payload in messages:
                stream.write(f'{base} {size} {ordinal}\n'+' '.join(f'{b:02x}'for b in payload)+'\n')
    print(f'Generated {segments} gRPC stream segments/{messages_total} complete-message leases')


if __name__=='__main__':main()
