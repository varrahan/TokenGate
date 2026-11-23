"""HTTP/2 wire fragments, native hyper-h2 sessions and hyperframe headers."""
import argparse
from pathlib import Path
import random
from hyperframe.frame import Frame
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived,DataReceived

MAGIC=b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'


def frame(kind,stream=0,payload=b'',flags=0,length=None):
    return (len(payload)if length is None else length).to_bytes(3,'big')+bytes([kind,flags])+stream.to_bytes(4,'big')+payload


class Reference:
    def __init__(self,server=True,allow=False,maximum=16384):
        self.magic=0 if server else 24;self.server=server;self.allow=allow;self.maximum=maximum
        self.header=bytearray();self.current=None;self.left=0;self.skip=False;self.first=True;self.cont=0;self.error=0;self.detail=0

    def feed(self,data):
        events=[]
        def emit(kind,byte=0,last=0,error=0):events.append((kind,byte,*self.current,last,error))
        for byte in data:
            if self.error:continue
            if self.magic<24:
                if byte!=MAGIC[self.magic]:self.error=1;self.detail=2
                else:self.magic+=1
                continue
            if self.left:
                self.left-=1
                if not self.skip:emit(1,byte,int(self.left==0))
                if self.left==0:
                    if not self.skip:emit(2)
                    self.current=None
                continue
            self.header.append(byte)
            if len(self.header)!=9:continue
            raw=bytes(self.header);self.header.clear()
            n=int.from_bytes(raw[:3],'big');kind=raw[3];flags=raw[4];stream=int.from_bytes(raw[5:],'big')&0x7fffffff
            self.current=(n,kind,flags,stream)
            error=detail=0
            if n>self.maximum:error,detail=6,3
            elif self.cont and(kind!=9 or stream!=self.cont)or kind==9 and not self.cont:error,detail=1,4
            elif self.first and(kind!=4 or flags&1):error,detail=1,5
            elif kind in(0,1,2,3,5,9)and not stream or kind in(4,6,7)and stream:error,detail=1,6
            elif kind==5 and(self.server or not self.allow):error,detail=1,7
            bad_length=(kind==2 and n!=5 or kind==3 and n!=4 or kind==4 and(n%6 or flags&1 and n)or
                kind==5 and n<(5 if flags&8 else 4)or kind==6 and n!=8 or kind==7 and n<8 or kind==8 and n!=4 or kind==1 and flags&32 and n<(6 if flags&8 else 5))
            if not error and bad_length and kind!=2:error,detail=6,8
            if error:self.error=error;self.detail=detail;continue
            # Native header parsing checks the complete format and masks the
            # reserved stream bit independently of our byte-at-a-time buffering.
            parsed,parsed_length=Frame.parse_frame_header(memoryview(raw));assert parsed_length==n and parsed.stream_id==stream
            self.left=n;self.skip=kind>9 or bool(bad_length)
            if bad_length:emit(3,error=6)
            else:
                self.first=False
                if kind in(1,5)and not flags&4:self.cont=stream
                elif kind==9 and flags&4:self.cont=0
                if not self.skip:emit(0)
            if not n:
                if not self.skip:emit(2)
                self.current=None
        canonical=self.magic==24 and not self.first and not self.header and not self.left and not self.cont and not self.error
        return events,int(canonical)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261120);records=[];references={};total_events=0
    def emit(ctx,data,fresh=False,server=True,allow=False,maximum=16384,mode=0):
        nonlocal total_events
        if fresh:references[ctx]=Reference(server,allow,maximum)
        reference=references[ctx];events,canonical=reference.feed(data)
        failed=int(bool(reference.error));error=reference.error;detail=reference.detail
        if mode in(2,3,4):events=[];canonical=0;failed=1;error=2;detail=10 if mode==2 else 1
        records.append(([ctx,int(fresh),int(server),int(allow),maximum,mode,len(data),len(events),failed,error,detail,canonical],data,events));total_events+=len(events)
    def fragments(ctx,wire,server=True,allow=False,maximum=16384,bytewise=False):
        position=0;fresh=True
        while position<len(wire):
            n=1 if bytewise else rng.choice([1,2,7,9,63,64,65,257,1024,4096])
            data=wire[position:position+n];position+=len(data)
            emit(ctx,data,fresh,server,allow,maximum);fresh=False
            if rng.randrange(13)==0:emit(ctx,b'',False,server,allow,maximum)
    client=H2Connection(config=H2Configuration(client_side=True));server=H2Connection(config=H2Configuration(client_side=False))
    client.initiate_connection();server.initiate_connection();server_wire=server.data_to_send()
    client_wire=client.data_to_send()
    for stream in range(1,42,2):
        fields=[(':method','POST'),(':scheme','https'),(':authority','parser.local'),(':path','/parser.Generate'),('content-type','application/grpc'),('te','trailers')]
        if stream==1:fields.append(('x-large','X'+''.join(chr(rng.randrange(33,127))for _ in range(35000))+'X'))
        client.send_headers(stream,fields)
        message=f'prompt-{stream}'.encode();body=b'\0'+len(message).to_bytes(4,'big')+message
        client.send_data(stream,body,end_stream=True)
    client.ping(b'01234567');client.increment_flow_control_window(1024);client_wire+=client.data_to_send()
    native_events=server.receive_data(client_wire)
    assert sum(isinstance(e,RequestReceived)for e in native_events)==21 and sum(isinstance(e,DataReceived)for e in native_events)==21
    server.send_headers(1,[(':status','200'),('content-type','application/grpc')]);server.send_data(1,b'\0\0\0\0\2ok',end_stream=True)
    server_wire+=server.data_to_send();client.receive_data(server_wire)
    # Interleave packet fragments from two real, independent HTTP/2 directions.
    packet_lists=[]
    for ctx,wire,role in((0,client_wire,True),(1,server_wire,False)):
        start=len(records);fragments(ctx,wire,role);packet_lists.append(records[start:]);del records[start:]
    while any(packet_lists):
        available=[i for i,p in enumerate(packet_lists)if p];records.append(packet_lists[rng.choice(available)].pop(0))
    custom=MAGIC+frame(4)+frame(1,1,b'\x82',4)+frame(0,0x80000001,b'\x02abc\0\0',9)+frame(2,1,b'\0\0\0\0\x10')+frame(3,3,(8).to_bytes(4,'big'))
    custom+=frame(6,0,b'abcdefgh',0x81)+frame(8,0,(0x80000080).to_bytes(4,'big'))+frame(0xfd,0,b'ignored extension'*5,0xff)
    custom+=frame(1,5,b'\x82',0)+frame(9,5,b'\x84',4)+frame(7,0,b'\0'*8+b'debug')
    fragments(2,custom)
    fragments(3,MAGIC+frame(4)+frame(2,1,b'bad')+frame(6,0,b'recovery'),bytewise=True)
    fragments(4,frame(4)+frame(5,1,b'\0\0\0\2\x82')+frame(9,1,b'\x84',4),server=False,allow=True)
    fragments(4,frame(4)+frame(5,1,b'\0\0\0\0\2',12),server=False,allow=True)
    emit(4,frame(5,1,b'\0\0\0\2',12),server=False,allow=True)
    fragments(5,MAGIC+frame(4)+frame(0,1,bytes(rng.randrange(256)for _ in range(20000))),maximum=65535)
    fragments(5,MAGIC+frame(4)+frame(0,1,bytes(range(256))*256+b'x'),maximum=65537)
    negatives=[b'X'+MAGIC[1:],MAGIC+frame(6,0,b'12345678'),MAGIC+frame(4,0,b'',1),MAGIC+frame(4,1),
        MAGIC+frame(4)+frame(0,0),MAGIC+frame(4)+frame(9,1),MAGIC+frame(4)+frame(1,1,b'',0)+frame(6,0,b'12345678'),
        MAGIC+frame(4)+frame(1,1,b'',0)+frame(9,3,b'',4),MAGIC+frame(4)+frame(5,1,b'\0'*4,4),
        MAGIC+frame(4,0,b'123'),MAGIC+frame(4)+frame(6,0,b'bad'),MAGIC+frame(4)+frame(8,1,b'bad'),
        MAGIC+frame(4)+frame(3,1,b'bad'),MAGIC+frame(4)+frame(7,0,b'bad'),MAGIC+frame(4)+frame(1,1,b'abcd',32),
        MAGIC+frame(4)+frame(0,1,length=16385)]
    for data in negatives:emit(6,data,True)
    for position in range(24):
        bad=bytearray(MAGIC);bad[position]^=1;emit(6,bytes(bad)+frame(4),True)
    for length in range(1,38):
        emit(6,MAGIC+frame(4)+frame(4,0,bytes(length)),True)
    emit(6,MAGIC+frame(4)+frame(4,0,bytes(6),1),True)
    emit(6,MAGIC+frame(4),True,mode=2)
    emit(7,b'config drain',True,mode=4,maximum=100)
    references[7]=Reference();emit(7,b'invalid saved state',False,mode=3)
    emit(6,MAGIC+frame(4)+frame(6,0,b'final-ok'),True)
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        for header,data,events in records:
            stream.write(' '.join(map(str,header))+'\n'+' '.join(f'{b:02x}'for b in data)+'\n')
            for event in events:stream.write(' '.join(map(str,event))+'\n')
    print(f'Generated {len(records)} HTTP/2 DMA fragments/{total_events} events; real hyper-h2 client/server sessions and protocol negatives')


if __name__=='__main__':main()
