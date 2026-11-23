"""Retain the full raw-prefill fixture and derive native reverse references."""
import argparse
import codecs
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tiktoken
from generate_rpc_response_vectors import packet


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];folder=args.output
    subprocess.run([sys.executable,str(root/'tools/generate_http2_prefill_vectors.py'),'--output',str(folder)],check=True)
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(root/'build/tiktoken-cache'))
    enc=tiktoken.get_encoding('cl100k_base');reference=json.loads((folder/'reference_cases.json').read_text())
    plan=json.loads((folder/'runtime_plan.json').read_text());regions={r['name']:r for r in json.loads((root/'build/scu35/image/external_manifest.json').read_text())['regions']}
    cases=[]
    for index,source in enumerate(reference['cases']):
        assert enc.encode_ordinary(bytes.fromhex(source['prompt_utf8_hex']).decode())==source['token_ids']
        mode=2 if source['application']==101 else 0 if index%4==0 else 1
        decoder=codecs.getincrementaldecoder('utf8')('replace');chunks=[];joined=bytearray()
        for ordinal,token in enumerate(source['token_ids']):
            raw=enc.decode_single_token_bytes(token);eos=ordinal+1==len(source['token_ids']);decoded=decoder.decode(raw,final=eos).encode()
            carry=decoder.getstate()[0];joined.extend(decoded)
            chunks.append(dict(token=token,ordinal=ordinal,eos=int(eos),bow_hex=raw.hex(),packet_hex=packet(decoded,mode,17).hex(),
                               decoded_bytes=len(decoded),carry=int.from_bytes(carry,'little'),carry_count=len(carry)))
        assert joined.hex()==source['prompt_utf8_hex']
        cases.append(dict(connection=source['connection'],stream=source['stream'],application=source['application'],format=mode,field=17,chunks=chunks))
    progress=plan['transport']['response_progress'];directory=regions['directory'];pool=regions['string_pool']
    result=dict(cases=cases,response_progress=progress,model_directory=directory,string_pool=pool,
        response_chunks=sum(len(c['chunks'])for c in cases),response_bytes=sum(len(bytes.fromhex(k['packet_hex']))for c in cases for k in c['chunks']),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        packet_reference_sha256=hashlib.sha256((root/'tools/generate_rpc_response_vectors.py').read_bytes()).hexdigest(),
        tiktoken_version=importlib.metadata.version('tiktoken'),full_transport_verified=False,full_system_verified=False)
    (folder/'response_reference.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f"Generated joint return references: {len(cases)} RPC responses, {result['response_chunks']} token chunks, {result['response_bytes']} bytes")


if __name__=='__main__':main()
