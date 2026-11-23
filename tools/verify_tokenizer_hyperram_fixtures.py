"""Independently validate both full model images and every native reference byte."""
import argparse
import codecs
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tiktoken
from trie_image import validate_trie
from vocabulary_image import decode_image,pair_hash
from generate_rpc_response_vectors import packet


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/validation'/args.run;report=json.loads((folder/'report.json').read_text())
    reference=json.loads((folder/'reference.json').read_text())
    assert sha(folder/'reference.json')==report['reference_sha256']
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(root/'build/tiktoken-cache'))
    original=tiktoken.get_encoding('cl100k_base')
    table=bytearray(range(256));table[ord('e')]=ord('E');table[ord('E')]=ord('e');table=bytes(table)
    swapped=tiktoken.Encoding(name='verified_cl100k_case_swap',pat_str=original._pat_str,
        mergeable_ranks={raw.translate(table):rank for raw,rank in original._mergeable_ranks.items()},special_tokens=original._special_tokens)
    manifest=json.loads((root/'build/scu35/image/external_manifest.json').read_text())
    regions={r['name']:r for r in manifest['regions']}
    artifacts={folder/'reference.json',root/'build/scu35/image/external_manifest.json',Path(__file__),
        root/'tools/trie_image.py',root/'tools/vocabulary_image.py',root/'tools/generate_rpc_response_vectors.py'}
    def region(image,name):
        entry=regions[name];return image[entry['base']:entry['base']+entry['bytes']]
    images=[];entries=[]
    for epoch,encoding in enumerate((original,swapped)):
        path=folder/f'image{epoch}.bin';assert path.stat().st_size==8388608
        assert sha(path)==reference['image_sha256'][epoch]==report['image_sha256'][epoch]
        image=path.read_bytes();images.append(image);artifacts.add(path)
        index=region(image,'directory');pool=region(image,'string_pool')
        ordinary={rank:raw for raw,rank in encoding._mergeable_ranks.items()}
        special={rank:raw.encode()for raw,rank in encoding._special_tokens.items()}
        assert len(ordinary)==100256 and len(special)==5
        expected=ordinary|special
        observed={token:word for token,(word,)in enumerate(struct.iter_unpack('<Q',index))if word&2}
        assert set(observed)==set(expected)and len(observed)==100261
        for token,word in observed.items():
            assert word&0xfffc==0 and bool(word&1)==(token in special)
            assert decode_image(index,pool,token)==expected[token]
        assert all(word==0 or word&2 for(word,)in struct.iter_unpack('<Q',index))
        assert validate_trie(region(image,'trie_nodes'),region(image,'trie_edges'),ordinary)==ordinary
        assert len(region(image,'trie_nodes'))//6==216750 and len(region(image,'trie_edges'))//4==216749
        byte_ids=struct.unpack('<256I',region(image,'byte_vocabulary'))
        assert all(ordinary[token]==bytes([byte])for byte,token in enumerate(byte_ids))
        entries.append(ordinary)
    assert images[0]!=images[1]
    assert region(images[0],'merge_hash')==region(images[1],'merge_hash')
    assert region(images[0],'unicode_classes')==region(images[1],'unicode_classes')
    # The hash ABI is checked against all native token pairs and priorities.
    actual_pairs={};mask=(1<<17)-1
    data=region(images[0],'merge_hash')
    for offset in range(0,len(data),9):
        word=int.from_bytes(data[offset:offset+9],'little')
        if not word:continue
        assert word>>69==0 and(word>>68)&1
        left=word&mask;right=(word>>17)&mask;merged=(word>>34)&mask;rank=(word>>51)&mask
        assert (left,right)not in actual_pairs
        assert entries[0][left]+entries[0][right]==entries[0][merged]and rank==merged
        address=pair_hash(left,right,18)
        while address!=offset//9:
            assert any(data[address*9:address*9+9]),'Merge entry unreachable through linear probing'
            address=(address+1)&((1<<18)-1)
        actual_pairs[left,right]=(merged,rank)
    expected_pairs={}
    ranks=original._mergeable_ranks
    for raw,merged in ranks.items():
        for split in range(1,len(raw)):
            left=ranks.get(raw[:split]);right=ranks.get(raw[split:])
            if left is not None and right is not None:expected_pairs[left,right]=(merged,merged)
    assert actual_pairs==expected_pairs and len(actual_pairs)==233378
    sequences=tokens=chunks=serialized=0
    for epoch,encoding in enumerate((original,swapped)):
        path=folder/f'epoch{epoch}.vectors';artifacts.add(path)
        words=iter(int(word)for word in path.read_text().split())
        def take(count):return [next(words)for _ in range(count)]
        assert next(words)==len(reference['cases'][epoch])==16
        for case in reference['cases'][epoch]:
            raw=bytes.fromhex(case['prompt_hex']);ids=encoding.encode_ordinary(raw.decode())
            assert ids==case['token_ids']
            assert take(6)==[len(raw),len(ids),case['user'],case['application'],case['format'],len(case['chunks'])]
            assert bytes(take(len(raw)))==raw and take(len(ids))==ids
            decoder=codecs.getincrementaldecoder('utf8')('replace');joined=bytearray()
            assert len(case['chunks'])==max(1,len(ids))
            for ordinal,chunk in enumerate(case['chunks']):
                token=ids[ordinal]if ids else 0;keep=15 if ids else 0;eos=int(ordinal+1==max(1,len(ids)))
                bow=encoding.decode_single_token_bytes(token)if ids else b''
                decoded=decoder.decode(bow,final=bool(eos)).encode();joined.extend(decoded)
                carry=decoder.getstate()[0];framed=packet(decoded,case['format'],17)
                metadata=[token,keep,eos,len(bow),len(framed),len(decoded),int.from_bytes(carry,'little'),len(carry)]
                assert take(8)==metadata and bytes(take(len(bow)))==bow and bytes(take(len(framed)))==framed
                assert bow.hex()==chunk['raw_hex']and framed.hex()==chunk['packet_hex']
                assert chunk['carry']==int.from_bytes(carry,'little')and chunk['carry_count']==len(carry)
                chunks+=1;serialized+=len(framed)
            assert joined==raw;sequences+=1;tokens+=len(ids)
        assert next(words,None)is None,'Extra unverified vector data'
    assert sequences==32 and tokens==chunks==11091
    # Preserve the exact generator used for these references. A later change
    # only excluded reference.json from subsequent metadata scans; reconstruct
    # its one-line predecessor and require the original SHA before archiving.
    evidence=folder/'fixture-audit';evidence.mkdir(parents=True,exist_ok=True)
    archived=evidence/'vector-generator-used.py'
    if not archived.exists():
        generator=root/'tools/generate_tokenizer_hyperram_vectors.py';original_source=generator.read_text()
        if hashlib.sha256(original_source.encode()).hexdigest()!=reference['generator_sha256']:
            original_source=original_source.replace("if p.is_file()and p.name!='reference.json'","if p.is_file()")
        assert hashlib.sha256(original_source.encode()).hexdigest()==reference['generator_sha256']
        archived.write_bytes(original_source.encode())
    assert sha(archived)==reference['generator_sha256'];artifacts.add(archived)
    result=dict(phase='two_complete_tokenizer_images_and_native_vectors_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        simulation=args.run,image_sha256=reference['image_sha256'],image_bytes_each=8388608,
        vocabulary_entries_each=100261,ordinary_tokens_each=100256,special_tokens_each=5,
        trie_nodes_each=216750,trie_edges_each=216749,merge_pairs_each=233378,all_image_entries_and_trie_paths_verified=True,
        every_merge_pair_rank_and_hash_probe_reachability_verified=True,
        bijective_ascii_case_model_permutation_verified=True,forward_sequences=sequences,token_ids=tokens,inverse_chunks=chunks,
        serialized_response_bytes=serialized,first_sequence_token_ids=[reference['cases'][epoch][0]['token_ids']for epoch in range(2)],
        image_reload_hardware_verified=False,functional_hardware_simulation_verified=False,full_system_complete=False,
        artifacts_sha256={path.relative_to(root).as_posix():sha(path)for path in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    output=root/'build/validation/tokenizer-hyperram-fixtures.json';output.write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(output,evidence/'verified.json');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    print(json.dumps({key:result[key]for key in('phase','key','forward_sequences','token_ids','first_sequence_token_ids')}))


if __name__=='__main__':main()
