"""Semantic DATA packets for automatic stream load/save and packet publication.

Only admissions, bytes/EOS and transport decisions enter RTL. Progress goldens
are derived by scanning struct-packed wire prefixes, never supplied to the DUT.
"""
import argparse
from pathlib import Path
import random
import struct
from generate_grpc_message_vectors import prefix_result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);rng=random.Random(20261122)
    definitions=[];records={};commands=[];pending_retire=None;packet_number=0;buffer_cursor=0x6a0003
    def define(user,sid,encoding=0,capacity=2048):
        nonlocal buffer_cursor
        i=len(definitions);definitions.append((user,sid,100+i,0x51000000+i,buffer_cursor,capacity,capacity,i&1,encoding))
        buffer_cursor+=((capacity+4095)//4096)*4096
        assert buffer_cursor<0x780003, 'Fixture payload buffers overlap the stream directory'
        return i
    def control(op,i=0,status=0,detail=0):
        nonlocal pending_retire
        d=definitions[i];key=d[:2];slot=-1;value=0
        if status==0:
            if op==4:records.clear()
            elif op==0:
                slot=next(n for n in range(16)if all(r['slot']!=n for r in records.values()))
                records[key]={'id':i,'slot':slot,'wire':b'','state':0,'emitted':0,'ended':False,'failed':None}
            elif op in(1,3):
                r=records[key];slot=r['slot'];value=r['state']
                if op==3:del records[key]
            elif op==5:
                records_copy=list(records)
                for k in records_copy:
                    if k[0]==pending_retire:del records[k]
                pending_retire=None
        commands.append(('C',op,i,status,detail,slot,value))
    def packet(user,events,commit=True,fault_client=-1,fault_target=-1,expected_status=None):
        nonlocal packet_number,pending_retire
        tag=0xc1000000+packet_number;packet_number+=1;descriptors=[];errors=[];current=None;payload_writes=0;queue_failed=False;prepared_failed=False
        def flush():
            nonlocal current
            if current in records and records[current]['failed']:
                r=records.pop(current);errors.append((r['id'],*r['failed']))
            current=None
        normalized=[]
        for kind,sid,data in events:
            if kind==2:
                flush();i=sid;d=definitions[i];key=d[:2]
                slot=next(n for n in range(16)if all(r['slot']!=n for r in records.values()))
                records[key]={'id':i,'slot':slot,'wire':b'','state':0,'emitted':0,'ended':False,'failed':None}
                normalized.append((kind,i,slot));continue
            normalized.append((kind,sid,data));key=(user,sid)
            if queue_failed or fault_client==0:continue
            if key!=current:flush();current=key
            if key not in records:raise ValueError(f'Fixture used an unadmitted stream {key}')
            r=records[key];d=definitions[r['id']]
            if r['failed']:continue
            if r['ended']:r['failed']=(13,8,0);continue
            old_used=r['state']&0xffffffff
            if kind==1:r['ended']=True
            else:r['wire']+=bytes([data])
            status,detail,state,complete=prefix_result(r['wire'],d[4],d[5],d[6],d[8],r['ended'])
            if state and(state&0xffffffff)>old_used:
                if fault_client==1 and payload_writes==fault_target:r['failed']=(13,5,0x51);payload_writes+=1;continue
                payload_writes+=1
            for base,size,ordinal,payload in complete[r['emitted']:]:
                descriptors.append((r['id'],base,size,ordinal,payload))
                if len(descriptors)>16 or fault_client==2:queue_failed=True;prepared_failed=True;break
            r['emitted']=len(complete)
            if status:r['failed']=(status,detail,0)
            else:r['state']=state
        flush()
        if fault_client==0:
            expected_status=13;prepared_failed=fault_target in(0,8);pending_retire=user;descriptors=[];errors=[]
        elif queue_failed:
            expected_status=13 if fault_client==2 else 8;commit=False;descriptors=[]
        elif expected_status is None:expected_status=0
        if not commit or queue_failed:
            descriptors=[]
            if fault_client!=0:
                for key in list(records):
                    if key[0]==user:del records[key]
        published=commit and not prepared_failed and expected_status==0
        commands.append(('P',user,tag,int(commit),expected_status,int(prepared_failed),fault_client,fault_target,int(published),int(fault_client==0),normalized,descriptors,errors))
    def byte_events(sid,wire):return[(0,sid,b)for b in wire]
    def framed(payload):return struct.pack('!BI',0,len(payload))+payload
    a=define(5,1);b=define(5,3);c=define(6,1);bad=define(5,7,1)
    control(4)
    for i in(a,b,c):control(0,i)
    # Switch streams repeatedly inside packets and persist incomplete prefixes
    # across packets. Same stream ID on another connection is independent.
    def random_messages():return[bytes(rng.randrange(256)for _ in range(rng.randrange(71)))for _ in range(15)]
    streams={a:b''.join(framed(p)for p in[b'',b'alpha',bytes(range(63)),b'last']+random_messages()),
             b:b''.join(framed(p)for p in[b'bravo',b'',b'\0\xff'*17]+random_messages()),
             c:b''.join(framed(p)for p in[b'other connection']+random_messages())}
    positions={i:0 for i in streams}
    while any(positions[i]<len(streams[i])for i in streams):
        user=rng.choice([u for u in[5,6]if any(definitions[i][0]==u and positions[i]<len(streams[i])for i in streams)])
        events=[]
        for _ in range(rng.randrange(1,5)):
            available=[i for i in streams if definitions[i][0]==user and positions[i]<len(streams[i])]
            if not available:break
            i=rng.choice(available);begin=positions[i];positions[i]=min(len(streams[i]),begin+rng.randrange(1,13))
            events+=byte_events(definitions[i][1],streams[i][begin:positions[i]])
            if positions[i]==len(streams[i]):events.append((1,definitions[i][1],0))
        packet(user,events)
    for i in(a,b,c):control(1,i)
    control(2,a,7,32) # External progress SAVE is deliberately unavailable.
    # A tentative admission and DATA can share a packet.
    control(0,bad);packet(5,byte_events(7,framed(b'prefix')+b'\x01\0\0\0\3zip')+byte_events(3,b'\0'))
    # Stream b was already at EOS: its later byte is a separate stream error.
    control(1,bad,3);control(1,b,3)
    fresh=define(5,9);packet(5,[(2,fresh,0)]+byte_events(9,framed(b'inline admission'))+[(1,9,0)])
    # Abort retires all streams of only its connection. Connection 6 remains.
    packet(5,[],commit=False);control(1,a,3);control(1,fresh,3);control(1,c)
    # Restore partial connection-6 progress across an unrelated raw abort.
    control(4);a=define(5,1);b=define(5,3);c=define(6,1)
    for i in(a,b,c):control(0,i)
    packet(6,byte_events(1,framed(b'kept')[:3]))
    packet(5,byte_events(1,framed(b'aborted')[:6]),commit=False)
    control(1,c);packet(6,byte_events(1,framed(b'kept')[3:])+[(1,1,0)])
    # Cross the 16-bit boundary with real payload writes and restored progress.
    # Short prefix cuts and large body cuts exercise both persistence counters;
    # the sibling forces LOAD/SAVE inside each packet as well as between them.
    control(4);large=define(5,11,capacity=131072);sibling=define(5,13)
    control(0,large);control(0,sibling)
    wire=framed(bytes((i*37+i//251)&255 for i in range(65537)));position=0
    for cut in[1,3,7,13,61,4091,16384,8193,16384,16384,16384]:
        end=min(len(wire),position+cut)
        if end==position:break
        packet(5,byte_events(11,wire[position:end])+byte_events(13,framed(bytes([position&255]))))
        position=end
    assert position==len(wire)
    packet(5,[(1,11,0),(1,13,0)])
    control(1,large);control(1,sibling)
    # Payload write failure is RPC-scoped; the sibling stream still completes.
    control(4);a=define(5,1);b=define(5,3)
    for i in(a,b):control(0,i)
    packet(5,byte_events(1,framed(b'bad'))+byte_events(3,framed(b'good'))+[(1,3,0)],fault_client=1,fault_target=0)
    control(1,a,3);control(1,b)
    # Pending-descriptor exhaustion and a write error cannot deadlock input.
    for fault_client in[-1,2]:
        control(4);a=define(5,1);c=define(6,1);control(0,a);control(0,c)
        payload=b''.join(framed(b'')for _ in range(18)) if fault_client<0 else framed(b'queue error')
        packet(5,byte_events(1,payload),fault_client=fault_client,fault_target=0 if fault_client==2 else -1)
        control(1,a,3);control(1,c)
    # Immediate load, prepare-save and abort-cleanup read failures. Recovery
    # clears the uncertain slot, then the engine retires the rest of that user.
    for target in[0,8,22]:
        control(4);a=define(5,1);b=define(5,3);c=define(6,1)
        for i in(a,b,c):control(0,i)
        packet(5,byte_events(1,framed(b'partial')[:1]),commit=target!=22,fault_client=0,fault_target=target)
        control(5,a);control(1,a,3);control(1,b,3);control(1,c)
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        stream.write(f'{len(definitions)}\n')
        for d in definitions:stream.write(' '.join(map(str,d))+'\n')
        for command in commands:
            if command[0]=='C':
                _,op,i,status,detail,slot,value=command;stream.write(f'0 {op} {i} {status} {detail} {slot} {value:064x}\n')
            else:
                _,user,tag,commit,status,failed,client,target,published,retiring,events,descriptors,errors=command
                stream.write(f'1 {user} {tag} {commit} {status} {failed} {client} {target} {published} {retiring} {len(events)} {len(descriptors)} {len(errors)}\n')
                for event in events:stream.write(' '.join(map(str,event))+'\n')
                for i,base,size,ordinal,payload in descriptors:stream.write(f'{i} {base} {size} {ordinal}\n'+' '.join(f'{b:02x}'for b in payload)+'\n')
                for error in errors:stream.write(' '.join(map(str,error))+'\n')
    print(f'Generated {len(commands)} ingress operations/{packet_number} DATA packets/{len(definitions)} admissions')


if __name__=='__main__':main()
