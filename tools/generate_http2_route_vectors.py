"""Runtime service tables and exact-path expectations for the raw wire corpus."""
import argparse
import json
from pathlib import Path
import struct


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.output
    keys=[b'/example.Generate/Call',b'/example.Generate/Cal',b'/EXAMPLE.Generate/Call',
          b'/service0/Method0',b'/service1/Method1',b'/valid%23path?query=yes',b'/'+b'x'*6000]
    blob=b'';records=[]
    for index,key in enumerate(keys):
        records.append([0x210005+len(blob),len(key),(17+index)|((2 if index==4 else 1 if index==3 else 3)<<16),
                        65537+index,9+index,23+index,0,0])
        blob+=key
    variants={0:records}
    labels={b'empty':1,b'bad-config':2,b'bad-record':3,b'duplicate':4,b'reload':5,
            b'bad-pointer':6,b'bad-formats':7,b'bad-reserved':8,b'zero-limit':9}
    for variant in range(3,10):
        changed=[r.copy() for r in records]
        if variant==3:changed[-1][7]=1
        if variant==4:changed.append(records[0].copy());changed[-1][2]=471|(3<<16)
        if variant==5:
            for r in changed:r[2]=(r[2]&0xffff0000)|90;r[4]=99;r[5]=100
        if variant==6:changed[-1][0]=0x7fffff
        if variant==7:changed[-1][2]&=0xffff
        if variant==8:changed[-1][6]=1
        if variant==9:changed[-1][3]=0
        variants[variant]=changed
    image={}
    for variant,rows in variants.items():
        data=b''.join(struct.pack('<8I',*row) for row in rows)
        image.update({0x200003+variant*512+i:b for i,b in enumerate(data)})
    image.update({0x210005+i:b for i,b in enumerate(blob)})
    with(root/'route_init.txt').open('w')as stream:
        ordered=sorted(image);position=0
        while position<len(ordered):
            address=ordered[position];values=[image[address]];position+=1
            while position<len(ordered)and len(values)<8 and ordered[position]==address+len(values):
                values.append(image[ordered[position]]);position+=1
            stream.write(f'{address} {len(values)} {int.from_bytes(bytes(values),"little"):016x}\n')

    tokens=iter((root/'vectors.txt').read_text().split());total=0;queries=0;matches=0;unknown=0;faults=0;duplicates=0;admitted=0
    with(root/'routes.txt').open('w')as stream:
        while True:
            try:first=next(tokens)
            except StopIteration:break
            f=[int(first)]+[int(next(tokens)) for _ in range(18)]
            for _ in range(f[18]):next(tokens)
            headers=[]
            for _ in range(f[17]):
                n,v,k=(int(next(tokens)) for _ in range(3));raw=bytes(int(next(tokens),16)for _ in range(n+v));headers.append((raw[:n],raw[n:]))
            label=dict(headers).get(b'x-route-case',b'')
            variant=labels.get(label,0);fault=int(label[6:])if label.startswith(b'fault-')else -1
            query=[v for n,v in headers[:f[16]] if n==b':path']
            queries+=len(query)
            status=1;detail=0;metadata=[0]*6
            if query:
                query=query[-1]
                if not query or variant==2:status=2;detail=1
                elif fault>=0:status=3
                elif variant in(3,6,7,8,9):status=2;detail=2
                elif variant!=1:
                    rows=variants[variant];hits=[(i,row)for i,row in enumerate(rows)if keys[i if i<len(keys)else 0]==query]
                    if len(hits)>1:status=4
                    elif hits:
                        i,row=hits[0];status=0;metadata=[row[2]&65535,row[2]>>16,row[3],row[4],row[5],i]
            formats=metadata[1]
            admissible=int(f[7]==0 and (f[2] or status==0 and f[9]<2 and bool(formats&(1<<f[9]))))
            count=0 if variant==1 else len(variants.get(variant,records));capacity=32 if variant==2 else count*32
            stream.write(' '.join(map(str,[variant,count,capacity,fault,status,detail,*metadata,admissible]))+'\n')
            total+=1;matches+=status==0;unknown+=status==1;faults+=status in(2,3);duplicates+=status==4;admitted+=admissible
    manifest=json.loads((root/'fixture_manifest.json').read_text())
    manifest.update(route_packet_candidates=total,route_queries=queries,route_matches=matches,unknown_routes=unknown,route_failures=faults,ambiguous_routes=duplicates,
                    header_admissible=admitted,route_programmed_bytes=len(image),scope='raw HTTP/2/HPACK/header checks/exact runtime path routing; trailer state is fixture supplied; no RPC OPEN')
    (root/'fixture_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))


if __name__=='__main__':main()
