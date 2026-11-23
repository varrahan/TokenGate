"""Semantic payload goldens; native hyperframe checks complete frame bodies."""
import argparse
from pathlib import Path
import random
import subprocess
import sys
import struct
from hyperframe.frame import Frame
from generate_http2_frame_vectors import Reference,MAGIC,frame


class Payload:
    def __init__(self,role):
        self.role=role;self.meta=(0,0,0,0);self.body=bytearray();self.failed=False;self.error=0;self.detail=0;self.skip_native=False

    def feed(self,events):
        out=[]
        def emit(kind,data=0,a=0,b=0):
            length,typ,flags,stream=self.meta;out.append((kind,data,a,b,length,typ,flags,stream,0,0))
        def fail(error,detail):
            self.failed=True;self.error=error;self.detail=detail;emit(11,a=error)
        def body_begin():
            length,typ,flags,_=self.meta;pad=self.body[0]if padded else 0
            promised=int.from_bytes(self.body[(1 if padded else 0):prefix_end],'big')&0x7fffffff if typ==5 else 0
            if typ==5 and not promised:fail(1,8)
            else:emit(1,a=length-prefix_end-pad,b=promised)
        for kind,data,length,typ,flags,stream,last,error in events:
            if self.failed:continue
            if kind in(0,3):
                self.meta=(length,typ,flags,stream);self.body=bytearray();self.skip_native=False
                if kind==3:emit(11,a=error,b=stream);continue
                padded=typ in(0,1,5)and bool(flags&8);prefix=5 if typ==1 and flags&32 else 4 if typ==5 else 0
                if padded and not length:fail(6,4);continue
                emit(0)
                if typ in(0,1,9)and not padded and not prefix:
                    prefix_end=0;body_begin()
                continue
            length,typ,flags,stream=self.meta
            padded=typ in(0,1,5)and bool(flags&8);prefix=5 if typ==1 and flags&32 else 4 if typ==5 else 0
            prefix_end=(1 if padded else 0)+prefix
            if kind==1:
                self.body.append(data);n=len(self.body)
                if typ in(0,1,5,9):
                    pad=self.body[0]if padded else 0
                    if padded and n==1:
                        if pad+prefix_end>length:fail(1,7)
                        elif not prefix:body_begin()
                    elif prefix and n==prefix_end:
                        if typ==1:emit(9,a=int.from_bytes(self.body[prefix_end-5:prefix_end-1],'big'),b=self.body[-1]+1)
                        body_begin()
                    elif n>prefix_end and n<=length-pad:emit(2,data)
                elif typ==4 and n%6==0:
                    setting,value=struct.unpack('>HI',self.body[-6:])
                    if setting==2 and(value>1 or not self.role and value==1)or setting==5 and not 16384<=value<=0xffffff:fail(1,10)
                    elif setting==4 and value>0x7fffffff:fail(3,10)
                    else:emit(4,a=setting,b=value)
                elif typ in(6,7)and n==8:
                    a,b=struct.unpack('>II',self.body);emit(5 if typ==6 else 6,a=a if typ==6 else a&0x7fffffff,b=b)
                elif typ in(3,8)and n==4:
                    value=int.from_bytes(self.body,'big')
                    if typ==3:emit(8,a=value)
                    elif value&0x7fffffff:emit(7,a=value&0x7fffffff)
                    elif stream:emit(11,a=1,b=stream);self.skip_native=True
                    else:fail(1,11)
                elif typ==2 and n==5:emit(9,a=int.from_bytes(self.body[:4],'big'),b=self.body[-1]+1)
            elif kind==2:
                if not self.skip_native:
                    header=frame(typ,stream,bytes(self.body),flags)[:9]
                    native,n=Frame.parse_frame_header(memoryview(header));assert n==length
                    # hyperframe 6.1 rejects the WINDOW_UPDATE reserved bit;
                    # RFC 9113 requires ignoring it. Normalize only that bit
                    # for the native syntax oracle; wire/goldens retain it.
                    native_body=bytes(self.body)
                    if typ==8:native_body=bytes([native_body[0]&127])+native_body[1:]
                    native.parse_body(memoryview(native_body))
                emit(3)
        return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    raw=args.output/'raw';subprocess.run([sys.executable,str(Path(__file__).with_name('generate_http2_frame_vectors.py')),'--output',str(raw)],check=True)
    tokens=iter((raw/'vectors.txt').read_text().split());records=[];payloads={}
    def append(header,data,events):
        ctx,fresh,role=header[:3]
        if fresh:payloads[ctx]=Payload(bool(role))
        payload=payloads[ctx];semantic=payload.feed(events)
        result=list(header);result[7]=len(semantic)
        if not result[8]and payload.failed:result[8]=1;result[9]=payload.error;result[10]=payload.detail
        records.append((result,data,semantic))
    for first in tokens:
        header=[int(first)]+[int(next(tokens))for _ in range(11)]
        data=bytes(int(next(tokens),16)for _ in range(header[6]));events=[tuple(int(next(tokens))for _ in range(8))for _ in range(header[7])]
        if header[5]==0:append(header,data,events)
    rng=random.Random(20261121)
    def wire(data,role=True,allow=False,bytewise=False):
        reference=Reference(role,allow);fresh=1;position=0
        while position<len(data):
            count=1 if bytewise else rng.choice([1,2,7,64,255]);chunk=data[position:position+count];position+=len(chunk)
            events,canonical=reference.feed(chunk)
            append([8,fresh,int(role),int(allow),16384,0,len(chunk),len(events),int(bool(reference.error)),reference.error,reference.detail,canonical],chunk,events)
            # A failed connection has no subsequent packets to resume.
            if payloads[8].failed or reference.error:break
            fresh=0
    for pad in range(256):wire(MAGIC+frame(4)+frame(0,1,bytes([pad])+b'data'+bytes([0xff])*pad,8))
    wire(MAGIC+frame(4)+frame(1,1,b'\x02\x80\0\0\3\xff\x82\x84\0\0',44),bytewise=True)
    wire(frame(4)+frame(5,1,b'\x01\x80\0\0\2\x82\0',12),role=False,allow=True,bytewise=True)
    wire(MAGIC+frame(4)+frame(8,3,bytes(4))+frame(6,0,b'still-ok'),bytewise=True)
    wire(MAGIC+frame(4,0,struct.pack('>HIHIHI',4,0x7fffffff,5,0xffffff,2,1)),bytewise=True)
    negatives=[frame(0,1,b'',8),frame(0,1,b'\x04abc',8),frame(1,1,b'\x01'+bytes(5),40),
        frame(4,0,struct.pack('>HI',2,2)),frame(4,0,struct.pack('>HI',4,0x80000000)),
        frame(4,0,struct.pack('>HI',5,16383)),frame(4,0,struct.pack('>HI',5,0x1000000)),frame(8,0,bytes(4))]
    for bad in negatives:wire(MAGIC+frame(4)+bad,bytewise=True)
    wire(frame(4)+frame(4,0,struct.pack('>HI',2,1)),role=False,bytewise=True)
    wire(frame(4)+frame(5,1,bytes(4),4),role=False,allow=True,bytewise=True)
    wire(frame(4)+frame(5,1,b'\x01'+bytes(4),12),role=False,allow=True,bytewise=True)
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        for header,data,events in records:
            stream.write(' '.join(map(str,header))+'\n'+' '.join(f'{b:02x}'for b in data)+'\n')
            for event in events:stream.write(' '.join(map(str,event))+'\n')
    print(f'Generated {len(records)} transport packets/{sum(len(e)for _,_,e in records)} semantic events; native frame-body checks, all padding lengths, controls and payload negatives')


if __name__=='__main__':main()
