"""Two complete vocabularies and independent bidirectional native references."""
import codecs
from dataclasses import replace
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import struct
import tiktoken
from external_memory_image import build_external_image
from vocabulary_image import compile_image,tiktoken_vocabulary,decode_image
from generate_rpc_response_vectors import packet


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    os.environ.setdefault('TIKTOKEN_CACHE_DIR',str(root/'build/tiktoken-cache'))
    folder=root/'build/experiments/tokenizer-hyperram/fixtures';folder.mkdir(parents=True,exist_ok=True)
    old=tiktoken.get_encoding('cl100k_base');vocab=tiktoken_vocabulary('cl100k_base')
    permutation=bytearray(range(256));permutation[ord('e')]=ord('E');permutation[ord('E')]=ord('e')
    table=bytes(permutation)
    tokens={token:raw if token in vocab.special else raw.translate(table)for token,raw in vocab.tokens.items()}
    swapped=replace(vocab,name='cl100k_ascii_case_swap',tokens=tokens,
        byte_ids=tuple(vocab.byte_ids[permutation[b]]for b in range(256)))
    compiled=compile_image(swapped,folder/'swapped-vocabulary')
    manifest1=build_external_image(folder/'swapped-vocabulary',root/'build/unicode',folder/'swapped-image')
    manifest0=json.loads((root/'build/scu35/image/external_manifest.json').read_text())
    assert compiled['vocabulary_entries']==len(vocab.tokens)==100261
    original=(root/'build/scu35/image/external_memory.bin').read_bytes()
    assert hashlib.sha256(original).hexdigest()==manifest0['image_sha256']
    initial_regions={r['name']:r for r in manifest0['regions']}
    directory=initial_regions['directory'];pool=initial_regions['string_pool']
    index=original[directory['base']:directory['base']+directory['capacity']]
    strings=original[pool['base']:pool['base']+pool['capacity']]
    assert sum(bool(word[0]&2)for word in struct.iter_unpack('<Q',index))==100261
    for token,raw in vocab.tokens.items():assert decode_image(index,strings,token)==raw
    assert manifest0['trie']['nodes']==manifest1['trie']['nodes']==216750
    assert manifest0['trie']['edges']==manifest1['trie']['edges']==216749
    assert manifest0['capacity_bytes']==manifest1['capacity_bytes']==8388608
    assert [(r['name'],r['base'],r['bytes'],r['capacity'])for r in manifest0['regions']]==[(r['name'],r['base'],r['bytes'],r['capacity'])for r in manifest1['regions']]
    custom=tiktoken.Encoding(name='cl100k_ascii_case_swap',pat_str=old._pat_str,
        mergeable_ranks={raw.translate(table):rank for raw,rank in old._mergeable_ranks.items()},special_tokens=old._special_tokens)
    reference=json.loads((root/'build/bidirectional-fixtures/reference_cases.json').read_text())
    all_cases=[]
    for epoch,encoding in enumerate((old,custom)):
        cases=[]
        for index,source in enumerate(reference['cases']):
            raw=bytes.fromhex(source['prompt_utf8_hex']);text=raw.decode();ids=encoding.encode_ordinary(text)
            if epoch==0:assert ids==source['token_ids']
            else:assert ids==old.encode_ordinary(raw.translate(table).decode())
            mode=2 if source['application']==101 else 0 if index%4==0 else 1
            decoder=codecs.getincrementaldecoder('utf8')('replace');chunks=[];joined=bytearray()
            for ordinal,token in enumerate(ids or [0]):
                keep=15 if ids else 0;eos=ordinal+1==max(1,len(ids))
                piece=encoding.decode_single_token_bytes(token)if ids else b''
                decoded=decoder.decode(piece,final=eos).encode();joined.extend(decoded);carry=decoder.getstate()[0]
                chunks.append(dict(token=token,keep=keep,eos=int(eos),raw_hex=piece.hex(),packet_hex=packet(decoded,mode,17).hex(),
                    decoded_bytes=len(decoded),carry=int.from_bytes(carry,'little'),carry_count=len(carry)))
            assert joined==raw
            cases.append(dict(user=index+1,application=source['application'],format=mode,prompt_hex=raw.hex(),token_ids=ids,chunks=chunks))
        all_cases.append(cases)
        with(folder/f'epoch{epoch}.vectors').open('w')as output:
            output.write(str(len(cases))+'\n')
            def values(items):output.write(' '.join(str(i)for i in items)+'\n')
            for case in cases:
                raw=bytes.fromhex(case['prompt_hex']);ids=case['token_ids']
                values((len(raw),len(ids),case['user'],case['application'],case['format'],len(case['chunks'])))
                values(raw);values(ids)
                for chunk in case['chunks']:
                    raw=bytes.fromhex(chunk['raw_hex']);serialized=bytes.fromhex(chunk['packet_hex'])
                    values((chunk['token'],chunk['keep'],chunk['eos'],len(raw),len(serialized),chunk['decoded_bytes'],chunk['carry'],chunk['carry_count']))
                    values(raw);values(serialized)
    assert all_cases[0][0]['token_ids']!=all_cases[1][0]['token_ids']
    plan=json.loads((root/'build/bidirectional-fixtures/runtime_plan.json').read_text())
    regions={region['name']:region for region in manifest0['regions']}
    working={region['name']:region for region in plan['regions']if region['owner']=='tokenizer'}
    config=dict(link_f_bpe_cfg_profile=0,link_f_bpe_cfg_class_base=regions['unicode_classes']['base'],
        link_f_bpe_cfg_hash_base=regions['merge_hash']['base'],link_f_bpe_cfg_node_base=regions['trie_nodes']['base'],
        link_f_bpe_cfg_edge_base=regions['trie_edges']['base'],link_f_bpe_cfg_node_count=216750,link_f_bpe_cfg_edge_count=216749,
        link_f_bpe_cfg_work_floor=manifest0['workspace_base'],link_r_cfg_directory_base=regions['directory']['base'],
        link_r_cfg_pool_base=regions['string_pool']['base'],link_r_cfg_directory_bytes=regions['directory']['capacity'],
        link_r_cfg_pool_bytes=regions['string_pool']['capacity'])
    for field,region in(('scalar','scalar_workspace'),('merge','merge_workspace'),('commit','token_commit')):
        config['link_f_bpe_cfg_'+field+'_base']=working[region]['base']
        config['link_f_bpe_cfg_'+field+'_bytes']=working[region]['bytes']
    (folder/'tokenizer_config.svh').write_text('\n'.join(f'{key}={value};'for key,value in config.items())+'\n')
    record=dict(phase='two_complete_vocabulary_epoch_fixtures_generated',generator_sha256=sha(Path(__file__)),
        vocabulary_entries_each=100261,ordinary_tokens_each=100256,special_tokens_each=5,
        image_sha256=[manifest0['image_sha256'],manifest1['image_sha256']],image_bytes_each=8388608,
        base_image_path=str(root/'build/scu35/image/external_memory.bin'),swapped_image_path=str(folder/'swapped-image/external_memory.bin'),
        tiktoken_version=importlib.metadata.version('tiktoken'),cases=all_cases,
        forward_sequences=sum(len(cases)for cases in all_cases),
        tokens_per_epoch=[sum(len(case['token_ids'])for case in cases)for cases in all_cases],
        fixture_sha256={p.relative_to(folder).as_posix():sha(p)for p in folder.rglob('*')if p.is_file()and p.name!='reference.json'},
        bidirectional_reference_sha256=sha(root/'build/bidirectional-fixtures/reference_cases.json'),
        custom_model_is_bijective_ascii_case_permutation=True,no_vocabulary_reduction=True,full_system_complete=False)
    (folder/'reference.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({key:record[key]for key in('phase','forward_sequences','tokens_per_epoch','image_sha256')}))


if __name__=='__main__':main()
