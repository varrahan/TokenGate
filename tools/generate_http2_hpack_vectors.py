"""Raw DMA packets -> native HPACK fields and passthrough semantic goldens."""
import argparse
import copy
from pathlib import Path
import subprocess
import sys
from hpack import Decoder
from generate_http2_frame_vectors import MAGIC,frame,Reference
from generate_http2_transport_vectors import Payload


def scan(decoder,data):
    result=[];position=0
    while position<len(data):
        view=memoryview(data)[position:];first=view[0]
        try:
            if first&128:header,used=decoder._decode_indexed(view);kind=0
            elif first&64:header,used=decoder._decode_literal_index(view);kind=1
            elif first&32:used=decoder._update_encoding_context(view);header=None;kind=0
            else:header,used=decoder._decode_literal_no_index(view);kind=3 if first&16 else 2
        except Exception:return result
        if header is not None:result.append((bytes(header[0]),bytes(header[1]),kind))
        position+=used
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    raw=args.output/'semantic';subprocess.run([sys.executable,str(Path(__file__).with_name('generate_http2_transport_vectors.py')),'--output',str(raw)],check=True)
    tokens=iter((raw/'vectors.txt').read_text().split());contexts={};records=[]
    def add(header,data,events):
        ctx=header[0]
        if header[1]:contexts[ctx]={'decoder':Decoder(max_header_list_size=262144),'body':bytearray(),'meta':None}
        current=contexts[ctx];forward=[];headers=[];blocks=[];failed=False
        for event in events:
            if failed:continue
            kind,byte,a,b,_,typ,flags,stream,_,_=event
            if kind==11:
                forward.append(event)
                if b==0:failed=True
                continue
            if typ not in(1,5,9):forward.append(event);continue
            if kind==0 and typ!=9:current['body']=bytearray();current['meta']=[stream,0,typ,flags]
            elif kind==1 and typ==5:current['meta'][1]=b
            elif kind==2:current['body'].append(byte)
            elif kind==3 and flags&4:
                encoded=bytes(current['body']);before=copy.deepcopy(current['decoder'])
                tentative=scan(copy.deepcopy(before),encoded)
                try:golden=list(current['decoder'].decode(encoded,raw=True))
                except Exception:
                    headers.extend(tentative);failed=True
                    if not header[8]:header[8]=1;header[9]=9;header[10]=0x83 if encoded==b'\x80' or encoded.endswith(b'\x80')else 0x84
                    continue
                assert [(n,v)for n,v,_ in tentative]==golden
                headers.extend(tentative);blocks.append([*current['meta'],len(golden),sum(32+len(n)+len(v)for n,v in golden)])
                current['body']=bytearray();current['meta']=None
        header[7]=len(forward);records.append((header,data,forward,headers,blocks))
    for first in tokens:
        header=[int(first)]+[int(next(tokens))for _ in range(11)]
        data=bytes(int(next(tokens),16)for _ in range(header[6]));events=[tuple(int(next(tokens))for _ in range(10))for _ in range(header[7])]
        add(header,data,events)
    for encoded in(b'\x80',b'\x82\x80',b'\x00\x01x\x81\xff'):
        wire=MAGIC+frame(4)+frame(1,1,encoded,4);reference=Reference();events,canonical=reference.feed(wire);semantic=Payload(True).feed(events)
        add([8,1,1,0,16384,0,len(wire),len(semantic),0,0,0,canonical],wire,semantic)
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        for header,data,events,headers,blocks in records:
            stream.write(' '.join(map(str,header+[len(headers),len(blocks)]))+'\n'+' '.join(f'{b:02x}'for b in data)+'\n')
            for event in events:stream.write(' '.join(map(str,event))+'\n')
            for name,value,kind in headers:
                stream.write(f'{len(name)} {len(value)} {kind}\n'+' '.join(f'{b:02x}'for b in name+value)+'\n')
            for block in blocks:stream.write(' '.join(map(str,block))+'\n')
    print(f'Generated {len(records)} raw HPACK ingress packets/{sum(len(h)for _,_,_,h,_ in records)} header fields/{sum(len(b)for _,_,_,_,b in records)} complete blocks')


if __name__=='__main__':main()
