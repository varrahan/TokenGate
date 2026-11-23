"""Complete-image tiktoken -> incremental codecs -> response byte references."""
import argparse
import codecs
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import shutil
import struct
import tiktoken


def varint(number):
    out=bytearray()
    while number>=128:out.append((number&127)|128);number>>=7
    out.append(number);return bytes(out)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];folder=args.output;folder.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(folder.parent/'tiktoken-cache'))
    source=root/'build/scu35/image';manifest=json.loads((source/'external_manifest.json').read_text())
    image=(source/'external_memory.bin').read_bytes();assert hashlib.sha256(image).hexdigest()==manifest['image_sha256']
    regions={region['name']:region for region in manifest['regions']};directory=regions['directory'];pool=regions['string_pool']
    enc=tiktoken.get_encoding('cl100k_base');byte_ids={};longest=(0,0)
    def entry(token):return struct.unpack_from('<Q',image,directory['base']+8*token)[0]
    def table_bytes(token):
        word=entry(token);length=word>>48;offset=(word>>16)&0xffffffff
        assert word&2 and word&0xfffc==0 and offset+length<=pool['capacity']
        return image[pool['base']+offset:pool['base']+offset+length],offset,bool(word&1)
    for token in range(manifest['trie']['terminals']):
        raw,offset,special=table_bytes(token);assert not special and raw==enc.decode_single_token_bytes(token)
        if len(raw)==1:byte_ids[raw[0]]=token
        if len(raw)>longest[0]:longest=(len(raw),token)
    specials=sorted(enc.encode(text,allowed_special={text})[0]for text in enc.special_tokens_set)
    for token in specials:
        raw,_,special=table_bytes(token);assert special and raw==enc.decode_single_token_bytes(token)
    assert len(byte_ids)==256
    cases=[];rng=random.Random(20261120)
    def add(token,carry=b'',eos=True,replace=True,strip=True,mode=1,key=None,reset=True,patch=None,
            fault=0,target=0,error=None,reads=None):
        index=len(cases);user=index%3;stream=1+2*(index%31);generation=1+index
        command=dict(user=user,axis_user=user,application=100+mode,stream=stream,generation=generation,model_epoch=23,schema_epoch=9,
            active_epoch=23,lease_valid=1,token=token,keep=15,eos=int(eos),replace=int(replace),strip=int(strip),format=mode,
            field=rng.choice((1,17,16384,(1<<29)-1)),directory_base=directory['base'],directory_bytes=directory['capacity'],
            pool_base=pool['base'],pool_bytes=pool['capacity'],carry=int.from_bytes(carry,'little'),carry_count=len(carry))
        if patch:command.update(patch)
        raw=None;offset=0
        if command['keep']==0:raw=b''
        elif token<directory['capacity']//8 and entry(token)&2:
            raw,offset,special=table_bytes(token)
            if strip and special:raw=b''
        if fault==2 or fault==3 or fault==4:raw=b'';reads=1
        elif fault==5:raw=image[pool['base']:pool['base']+65535];offset=0;reads=8193
        elif fault==6:raw=image[pool['base']+70001:pool['base']+70041];offset=70001;reads=7
        if reads is None:reads=0 if command['keep']==0 else 1+(len(raw)+offset%8+7)//8 if raw else 1
        bow_raw=raw
        if fault==1:
            good=target-1
            prefix=min(len(raw),8-offset%8+8*(good-1))if good>0 else 0
            bow_raw=raw[:prefix];reads=target+1
        if error is not None and error[0]==1:bow_raw=None
        if raw is None and bow_raw is None and error is not None and error[0]!=1:bow_raw=b''
        decoded=b'';next_carry=carry;stage=status=memory_status=0
        if error is not None:stage,status,memory_status=error
        else:
            decoder=codecs.getincrementaldecoder('utf8')('replace'if replace else'strict');decoder.setstate((carry,0))
            try:decoded=decoder.decode(raw,final=eos).encode();next_carry=decoder.getstate()[0]
            except UnicodeDecodeError as exc:stage,status=4,4 if exc.reason=='unexpected end of data'else 1
            if status==0:
                if command['format']==3 or command['format']==2 and command['field']==0:stage,status=5,2
                elif len(decoded)>16384:stage,status=5,1
        packet=b''
        if status==0:
            if command['format']==2:packet=varint((command['field']<<3)|2)+varint(len(decoded))+decoded
            else:
                body=json.dumps({'choices':[{'delta':{'content':decoded.decode()}}]},ensure_ascii=False,separators=(',',':')).encode()
                packet=b'data: '+body+b'\n\n'if command['format']==1 else body
        expected=dict(stage=stage,status=status,memory_status=memory_status,carry=command['carry']if status else int.from_bytes(next_carry,'little'),
            carry_count=command['carry_count']if status else len(next_carry),decoded_bytes=0 if status else len(decoded),
            packet_hex=packet.hex(),bow_hex=None if bow_raw is None else bow_raw.hex(),logical_reads=reads)
        cases.append(dict(key=key or f'case-{index}',reset=reset,command=command,fault_mode=fault,fault_target=target,expected=expected))
        return next_carry if not status else carry
    sequences=[('plain','hello world!'),('unicode','café 中文 🙂 Καλημέρα 한국어'),('controls','\0\n\t"\\\r'+chr(0x10ffff)),('long',' '*128+'a'*80)]
    # Three response formats, real native tokenization, carried state per caller.
    for mode in range(3):
        streams=[(name,enc.encode_ordinary(text))for name,text in sequences];positions=[0]*len(streams);carries=[b'']*len(streams)
        while any(positions[i]<len(ids)for i,(_,ids)in enumerate(streams)):
            for index,(name,ids)in enumerate(streams):
                pos=positions[index]
                if pos<len(ids):
                    carries[index]=add(ids[pos],carries[index],eos=pos+1==len(ids),mode=mode,key=f'{mode}-{name}',reset=pos==0,
                        patch=dict(user=index%3,axis_user=index%3,application=100+mode,stream=1+2*index,generation=100+index))
                    positions[index]+=1
    for byte in range(256):
        for replace in(False,True):add(byte_ids[byte],replace=replace,mode=byte%3)
    for token in specials:
        for strip in(False,True):
            for mode in range(3):add(token,strip=strip,mode=mode)
    for token in rng.sample(range(100256),80):add(token,mode=rng.randrange(3),replace=True)
    for replace in(False,True):
        for mode in range(3):add(0,carry=b'\xf0\x9f',replace=replace,mode=mode,patch=dict(keep=0))
    a=byte_ids[65]
    for patch,error in((dict(lease_valid=0),(1,1,0)),(dict(active_epoch=24),(1,2,0)),(dict(generation=0),(1,3,0)),
        (dict(keep=3),(1,4,0)),(dict(keep=0,eos=0),(1,4,0)),(dict(pool_bytes=1),(1,5,0)),
        (dict(pool_base=0),(1,5,0)),(dict(directory_base=0x7ffff8),(1,5,0)),(dict(directory_bytes=8),(1,6,0)),
        (dict(axis_user=0xfffe),(1,7,0))):add(a,carry=b'\xf0\x9f',patch=patch,error=error,reads=0)
    add(0xffffffff,error=(1,6,0),reads=0)
    assert entry(100256)&2==0
    add(100256,error=(3,2,0),reads=1)
    for target in(0,1,4):add(longest[1],fault=1,target=target,error=(3,4 if target==0 else 5,0x75))
    for fault,error in((2,(2,2,0)),(3,(3,2,0)),(4,(2,2,0))):add(a,fault=fault,error=error)
    add(a,fault=5,mode=1);add(a,fault=6,mode=2)
    add(a,patch=dict(format=3));add(a,mode=2,patch=dict(field=0))
    add(a,carry=b'A',error=(4,2,0))
    shutil.copy2(source/'external_memory.bin',folder/'memory.bin')
    shutil.copy2(source/'external_manifest.json',folder/'model_manifest.json')
    (folder/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    result=dict(cases=len(cases),successes=sum(c['expected']['status']==0 for c in cases),
        rejections=sum(c['expected']['status']!=0 for c in cases),response_bytes=sum(len(bytes.fromhex(c['expected']['packet_hex']))for c in cases),
        ordinary_entries_verified=100256,special_entries_verified=len(specials),model_image_sha256=manifest['image_sha256'],
        longest_native_token_bytes=longest[0],generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        tiktoken_version=importlib.metadata.version('tiktoken'),full_transport_verified=False,whole_rpc_lease_verified=False)
    (folder/'fixture_manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
