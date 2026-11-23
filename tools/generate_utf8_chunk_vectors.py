"""Independent Python incremental-codec and JSON/Protobuf chunk references."""
import argparse
import codecs
import hashlib
import json
from pathlib import Path
import random


def varint(number):
    result=bytearray()
    while number>=128:result.append((number&127)|128);number>>=7
    result.append(number);return bytes(result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261120);cases=[]
    def add(raw,carry=b'',eos=True,replace=True,mode=None,field=1,upstream=False,mismatch=False,bad_state=None):
        mode=rng.randrange(3)if mode is None else mode
        seed=int.from_bytes(carry,'little');seed_count=len(carry);stage=status=0;decoded=b'';next_carry=carry
        if bad_state is not None:seed,seed_count=bad_state;stage,status=1,2
        else:
            decoder=codecs.getincrementaldecoder('utf-8')('replace'if replace else'strict');decoder.setstate((carry,0))
            try:decoded=decoder.decode(raw,final=eos).encode('utf-8');next_carry=decoder.getstate()[0]
            except UnicodeDecodeError as error:stage,status=1,4 if error.reason=='unexpected end of data'else 1
        if mismatch and status==0:stage,status=1,3
        if upstream:stage,status=1,5
        if status==0:
            if mode==3 or mode==2 and field==0:stage,status=2,2
            elif len(decoded)>16384:stage,status=2,1
        expected=b''
        if status==0:
            if mode==2:expected=varint((field<<3)|2)+varint(len(decoded))+decoded
            else:
                body=json.dumps({'choices':[{'delta':{'content':decoded.decode('utf-8')}}]},ensure_ascii=False,separators=(',',':')).encode()
                expected=(b'data: '+body+b'\n\n')if mode==1 else body
        out_seed=seed if status else int.from_bytes(next_carry,'little')
        out_count=seed_count if status else len(next_carry)
        header=[0x5100+len(cases)%16,int(eos),int(replace),seed,seed_count,mode,field,len(raw),int(upstream),int(mismatch),
                stage,status,len(expected),out_seed,out_count,0 if status else len(decoded)]
        cases.append((header,raw,expected));return next_carry if not status else carry
    scalars=[0x80,0x7ff,0x800,0xd7ff,0xe000,0xffff,0x10000,0x10ffff,0x20ac,0x1f642]
    prefixes=[b'']
    for point in scalars:
        encoded=chr(point).encode();prefixes.extend(encoded[:n]for n in range(1,len(encoded)))
        for cut in range(1,len(encoded)):
            for replace in(False,True):
                carry=add(encoded[:cut],eos=False,replace=replace)
                add(encoded[cut:],carry,eos=True,replace=replace)
    for byte in range(256):
        for replace in(False,True):add(bytes([byte]),replace=replace)
    for raw in(b'\xe0\x80\x80',b'\xed\xa0\x80',b'\xf0\x80\x80\x80',b'\xf4\x90\x80\x80',
               b'\xe2\x82A',b'\xe2\x82\xf0',b'\xc2\xc2\xa9',b'\xf0\x90\x80A',b'\xff\0"\\\n'):
        for replace in(False,True):add(raw,replace=replace)
    # Interleaved callers retain their carry outside the RTL between chunks.
    sequences=[text.encode()for text in('A café 中文 🙂\n"\\end','Καλημέρα 한국어 日本語',chr(0x10ffff)*3)]
    offsets=[0]*3;carries=[b'']*3
    while any(offset<len(raw)for offset,raw in zip(offsets,sequences)):
        for index,raw in enumerate(sequences):
            if offsets[index]<len(raw):
                end=min(len(raw),offsets[index]+rng.randrange(1,4))
                carries[index]=add(raw[offsets[index]:end],carries[index],eos=end==len(raw),mode=index)
                offsets[index]=end
    for _ in range(300):
        carry=rng.choice(prefixes);raw=bytes(rng.randrange(256)for _ in range(rng.randrange(0,65)))
        add(raw,carry,eos=bool(rng.randrange(2)),replace=bool(rng.randrange(2)),field=rng.choice((1,17,16384,(1<<29)-1)))
    for carry in prefixes:
        for replace in(False,True):add(b'',carry,eos=True,replace=replace);add(b'',carry,eos=False,replace=replace)
    for seed in((1,0),(0x41,1),(0x80,1),(0x01c2,1),(0xa9c2,2),(0x80e0,2),(0x8080e0,3)):
        add(b'valid bytes',bad_state=seed)
    for mode in range(3):
        add(b'prefix '*6,upstream=True,mode=mode)
        add(b'prefix '*6,mismatch=True,mode=mode)
        add(b'\xf0\x9f',upstream=True,mode=mode,replace=False)
    add(b'format',mode=3);add(b'field',mode=2,field=0)
    for mode in range(3):
        add(b'x'*16384,mode=mode);add(b'x'*16385,mode=mode)
    add(b'\xff'*5461,mode=1);add(b'\xff'*5462,mode=1)
    add(b'\0'*16384,mode=1)
    with(args.output/'vectors.txt').open('w')as stream:
        for header,raw,expected in cases:
            stream.write(' '.join(map(str,header))+'\n')
            stream.write(' '.join(map(str,raw))+'\n');stream.write(' '.join(map(str,expected))+'\n')
    metadata=dict(cases=len(cases),successful=sum(h[11]==0 for h,_,_ in cases),
                  errors=sum(h[11]!=0 for h,_,_ in cases),raw_bytes=sum(len(raw)for _,raw,_ in cases),
                  serialized_bytes=sum(len(out)for _,_,out in cases),max_text_bytes=16384,
                  oracle='Python codecs incremental UTF-8, json and independent Protobuf varints',
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'fixture_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()
