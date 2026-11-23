"""Native incremental response references for real RPC-directory integration."""
import argparse
import codecs
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import struct
import tiktoken


def varint(number):
    out=bytearray()
    while number>=128:out.append((number&127)|128);number>>=7
    out.append(number);return bytes(out)


def packet(raw,mode,field):
    if mode==2:return varint((field<<3)|2)+varint(len(raw))+raw
    body=json.dumps({'choices':[{'delta':{'content':raw.decode()}}]},ensure_ascii=False,separators=(',',':')).encode()
    return b'data: '+body+b'\n\n' if mode==1 else body


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];folder=args.output;folder.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(root/'build/tiktoken-cache'))
    source=root/'build/scu35/image';image=(source/'external_memory.bin').read_bytes();manifest=json.loads((source/'external_manifest.json').read_text())
    assert hashlib.sha256(image).hexdigest()==manifest['image_sha256']
    regions={r['name']:r for r in manifest['regions']};directory=regions['directory'];pool=regions['string_pool']
    enc=tiktoken.get_encoding('cl100k_base');byte_ids={};longest=(0,0)
    for token in range(100256):
        entry=struct.unpack_from('<Q',image,directory['base']+token*8)[0];raw=enc.decode_single_token_bytes(token)
        length=entry>>48;offset=(entry>>16)&0xffffffff
        assert entry&3==2 and entry&0xfffc==0 and length==len(raw) and image[pool['base']+offset:pool['base']+offset+length]==raw
        if len(raw)==1:byte_ids[raw[0]]=token
        if len(raw)>longest[0]:longest=(len(raw),token)
    streams=[]
    for mode in range(3):
        group=[]
        for index,text in enumerate(('hello world!','café 中文 🙂 한국어','\0\n\t"\\\r'+chr(0x10ffff),' '*128+'a'*80)):
            tokens=enc.encode_ordinary(text);decoder=codecs.getincrementaldecoder('utf8')('replace');chunks=[]
            for ordinal,token in enumerate(tokens):
                raw=enc.decode_single_token_bytes(token);eos=ordinal+1==len(tokens);decoded=decoder.decode(raw,final=eos).encode()
                carry=decoder.getstate()[0]
                chunks.append(dict(token=token,eos=int(eos),ordinal=ordinal,bow_hex=raw.hex(),packet_hex=packet(decoded,mode,17).hex(),
                    decoded_bytes=len(decoded),carry=int.from_bytes(carry,'little'),carry_count=len(carry)))
            group.append(dict(slot=index,user=index%3,stream=1+index*2,generation=1000*(mode+1)+index,application=100+mode,
                              format=mode,field=17,protobuf=int(mode==2),chunks=chunks))
        streams.append(group)
    floor=manifest['workspace_base'];layout=dict(stream_base=floor,stream_bytes=512,progress_base=floor+512,progress_bytes=128,
        payload_base=floor+1024,payload_bytes=4096,work_floor=floor,model_epoch=23,schema_epoch=9,
        directory_base=directory['base'],directory_bytes=directory['capacity'],pool_base=pool['base'],pool_bytes=pool['capacity'])
    a=byte_ids[65];raw=enc.decode_single_token_bytes(a)
    result=dict(layout=layout,groups=streams,ascii_token=a,ascii_packet_hex=packet(raw,1,17).hex(),
                invalid_token=byte_ids[255],long_token=longest[1],long_bow_hex=enc.decode_single_token_bytes(longest[1]).hex(),
                model_image_sha256=manifest['image_sha256'],ordinary_entries_verified=100256,tiktoken_version=importlib.metadata.version('tiktoken'),
                generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    shutil.copy2(source/'external_memory.bin',folder/'memory.bin');shutil.copy2(source/'external_manifest.json',folder/'model_manifest.json')
    (folder/'rpc_cases.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(groups=3,streams=12,commands=sum(len(s['chunks'])for g in streams for s in g),model_image_sha256=manifest['image_sha256']),indent=2))


if __name__=='__main__':main()
