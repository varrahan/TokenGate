"""Complete-model gRPC/Parser/BoW/BPE/DMA references and joint allocations."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import regex
import tiktoken
from runtime_memory_plan import Limits,runtime_plan
from unicode_profiles import LLAMA3_PATTERN,GPT2_PATTERN


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image-directory',type=Path,default=Path(__file__).resolve().parents[1]/'build/scu35/image')
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(out.parent/'tiktoken-cache'))
    image=(args.image_directory/'external_memory.bin').read_bytes()
    manifest=json.loads((args.image_directory/'external_manifest.json').read_text())
    limits=Limits(3,3,131072,16384,16384,32768,4096,16)
    plan=runtime_plan(manifest,image,limits)
    plan['planner_sha256']=hashlib.sha256(Path(__file__).with_name('runtime_memory_plan.py').read_bytes()).hexdigest()
    (out/'runtime_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    subprocess.run([sys.executable,str(Path(__file__).with_name('generate_grpc_parser_vectors.py')),'--output',str(out/'parser')],check=True)
    tokens=iter((out/'parser/vectors.txt').read_text().split())
    def integer():return int(next(tokens))
    definitions=[[integer()for _ in range(9)]for _ in range(integer())]
    old_bases=sorted({d[4]for d in definitions});assert len(old_bases)==3
    bases={old:region['base']for old,region in zip(old_bases,plan['transport']['rpc_payloads'])}
    for d in definitions:d[4]=bases[d[4]];assert d[5]<=limits.rpc_payload_bytes
    enc=tiktoken.get_encoding('cl100k_base');patterns=[enc._pat_str,LLAMA3_PATTERN,GPT2_PATTERN]
    def encode(raw,profile):
        text=raw.decode('utf-8');ids=[i for piece in regex.findall(patterns[profile],text)for i in enc._encode_single_piece(piece.encode())]
        if profile==0:assert ids==enc.encode_ordinary(text)
        return ids
    commands=[];drains=0;expected_ids=0;successes=0
    while True:
        try:opcode=integer()
        except StopIteration:break
        if opcode==0:commands.append((0,[integer()for _ in range(3)]))
        elif opcode==1:
            fields=[integer()for _ in range(5)];events=[[integer()for _ in range(3)]for _ in range(fields[3])];errors=[[integer()for _ in range(4)]for _ in range(fields[4])]
            commands.append((1,fields,events,errors))
        elif opcode==3:commands.append((3,integer(),next(tokens),next(tokens)))
        elif opcode==2:
            client,target,probe,count=[integer()for _ in range(4)];profile=drains%3;drains+=1;items=[]
            for _ in range(count):
                fields=[integer()for _ in range(9)];raw=bytes(int(next(tokens),16)for _ in range(fields[6]))
                ids=encode(raw,profile)if fields[3]==0 else[]
                expected_ids+=len(ids);successes+=fields[3]==0
                fields[6]=len(ids);fields.extend([0,1 if fields[3]==0 else 0])
                items.append((fields,ids))
            commands.append((2,[client,target,0 if client>=0 else -1,probe,count,profile,0],items))
        else:raise ValueError('Unknown source fixture opcode')
    # All source error cases still traverse the real Parser path. Additional
    # tokenizer faults exercise every shared client and a failed DMA prefix.
    faults=[(5,0,0,2,5,0),(6,0,1,2,6,0),(7,0,0,3,0,0),(10,0,0,4,3,0),
            (11,0,1,4,2,0),(12,0,1,6,0,0),(12,0,0,7,0,0),(12,17,0,7,0,0),
            (-1,-1,-1,1,0,1),(-1,-1,-1,5,0,2)]
    for number,(client,target,write,stage,detail,config_mode)in enumerate(faults):
        i=len(definitions);d=[5,1,1000+i,0x63000000+i,plan['transport']['rpc_payloads'][0]['base'],131072,65536,0,0];definitions.append(d)
        commands.extend([(0,[4,i,0]),(0,[0,i,0])])
        text='\0'*80;body=json.dumps({'prompt':text}).encode();wire=struct.pack('!BI',0,len(body))+body;tag=0xc3000000+number
        commands.append((1,[5,tag,1,len(wire)+1,0],[[0,1,b]for b in wire]+[[1,1,0]],[]))
        ids=encode(text.encode(),0)[:17]if stage==7 and target==17 else[]
        fields=[i,tag,0,7,detail,0x74 if client>=0 else 0,len(ids),d[2],d[3],stage,1 if ids else 0]
        expected_ids+=len(ids);commands.append((2,[client,target,write,-1,1,0,config_mode],[(fields,ids)]))
        # Retire the failed RPC, reuse its buffer under a fresh generation and
        # prove a successful token DMA immediately after each failure phase.
        recovered=len(definitions);r=d.copy();r[2]=1000+recovered;r[3]=0x64000000+recovered;definitions.append(r)
        commands.extend([(0,[3,i,0]),(0,[0,recovered,0])])
        profile=number%3;text=f'recovered {number}: café 中文 🙂';body=json.dumps({'prompt':text},ensure_ascii=bool(number%2)).encode()
        wire=struct.pack('!BI',0,len(body))+body;tag=0xc4000000+number
        commands.append((1,[5,tag,1,len(wire)+1,0],[[0,1,b]for b in wire]+[[1,1,0]],[]))
        ids=encode(text.encode(),profile);expected_ids+=len(ids);successes+=1
        fields=[recovered,tag,0,0,0,0,len(ids),r[2],r[3],0,1]
        commands.append((2,[-1,-1,-1,-1,1,profile,0],[(fields,ids)]))
    with(out/'vectors.txt').open('w',encoding='ascii')as stream:
        stream.write(f'{len(definitions)}\n')
        for d in definitions:stream.write(' '.join(map(str,d))+'\n')
        for command in commands:
            opcode=command[0]
            if opcode==0:stream.write('0 '+' '.join(map(str,command[1]))+'\n')
            elif opcode==1:
                _,fields,events,errors=command;stream.write('1 '+' '.join(map(str,fields))+'\n')
                for row in events+errors:stream.write(' '.join(map(str,row))+'\n')
            elif opcode==2:
                _,fields,items=command;stream.write('2 '+' '.join(map(str,fields))+'\n')
                for item,ids in items:stream.write(' '.join(map(str,item))+'\n'+' '.join(map(str,ids))+'\n')
            else:stream.write(f'3 {command[1]} {command[2]} {command[3]}\n')
    config=plan['tokenizer_config'];transport=plan['transport']
    layout=config+[transport['stream_pool']['base'],transport['stream_pool']['bytes'],transport['descriptor_queue']['base'],transport['descriptor_queue']['bytes']]
    layout.extend(value for region in transport['rpc_payloads']for value in[region['base'],region['bytes']])
    (out/'layout.txt').write_text(' '.join(map(str,layout))+'\n')
    with(out/'memory.mem').open('w',encoding='ascii')as stream:
        for offset in range(0,len(image),8):stream.write(f"{int.from_bytes(image[offset:offset+8],'little'):016x}\n")
    metadata={'image_sha256':hashlib.sha256(image).hexdigest(),'model':manifest['model'],'model_bytes':len(image),'successes':successes,'expected_dma_ids_including_failed_prefix':expected_ids,
              'parser_faults':11,'tokenizer_faults':len(faults),'profiles':3,'runtime_plan_static_only':True,
              'packages':{name:importlib.metadata.version(name)for name in['tiktoken','regex']}}
    (out/'fixture_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(f'Generated full-model semantic gRPC prefill: {len(commands)} operations/{successes} successful messages/{expected_ids} checked DMA IDs; joint workspace and three profiles')


if __name__=='__main__':main()
