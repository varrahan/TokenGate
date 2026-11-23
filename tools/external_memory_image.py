"""Validated SCU35 external-memory images, retaining the complete vocabulary.

The external cache/master and physical controller are separate implementation
work. This tool defines and verifies their byte-addressed image contract.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from vocabulary_image import decode_image,pair_hash
from trie_image import compile_trie,ordinary_tokens


def verified_bytes(path,metadata):
    data=path.read_bytes()
    if len(data)!=metadata["bytes"] or hashlib.sha256(data).hexdigest()!=metadata["sha256"]:
        raise ValueError(f"Image integrity failure: {path.name}")
    return data


def validate_vocabulary(directory):
    manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    names=("directory.bin","string_pool.bin","byte_tokens.bin","merge_hash.bin")
    files={name:verified_bytes(directory/name,manifest["files"][name])for name in names}
    return validate_vocabulary_data(manifest,files)


def validate_vocabulary_data(manifest,files):
    """Semantic validation shared by the compiler and host MMIO loader."""
    if manifest.get("abi")!=1:raise ValueError("Unsupported vocabulary ABI")
    widths=[manifest[k]for k in ("id_bits","rank_bits","hash_addr_bits","vocab_addr_bits","pool_word_addr_bits")]
    id_bits,rank_bits,hash_bits,vocab_bits,pool_bits=widths
    if not all(isinstance(w,int)and 1<=w<=20 for w in widths):raise ValueError("Invalid hardware capacity widths")
    valid_bit=3*id_bits+rank_bits
    if valid_bit>=72:raise ValueError("Merge entry exceeds the 72-bit ABI")
    names=("directory.bin","string_pool.bin","byte_tokens.bin","merge_hash.bin")
    index,pool,byte_ids,raw_hash=(files[name]for name in names)
    if len(index)!=8*(1<<vocab_bits) or len(raw_hash)!=9*(1<<hash_bits) or len(byte_ids)!=1024:
        raise ValueError("Image sizes do not match declared hardware capacities")
    if len(pool)>8*(1<<pool_bits):raise ValueError("String pool exceeds capacity")
    tokens={};special=set()
    for token_id in range(1<<vocab_bits):
        word,=struct.unpack_from("<Q",index,8*token_id)
        if not word&2:
            if word:raise ValueError("Nonzero invalid directory entry")
            continue
        if word&0xfffc:raise ValueError("Reserved directory flags are nonzero")
        tokens[token_id]=decode_image(index,pool,token_id)
        if word&1:special.add(token_id)
    if len(tokens)!=manifest["vocabulary_entries"]:raise ValueError("Vocabulary entry count mismatch")
    for byte,token_id in enumerate(struct.unpack("<256I",byte_ids)):
        if token_id in special or tokens.get(token_id)!=bytes([byte]):raise ValueError("Invalid base-byte vocabulary")
    slots=[int.from_bytes(raw_hash[i:i+9],"little")for i in range(0,len(raw_hash),9)]
    mask=(1<<id_bits)-1
    seen=set();pair_count=0
    for location,word in enumerate(slots):
        if word==0:continue
        if word>>(valid_bit+1) or not(word>>valid_bit&1):raise ValueError("Invalid hash flags")
        left=word&mask;right=word>>id_bits&mask;result=word>>(2*id_bits)&mask
        key=(left,right)
        if key in seen:raise ValueError("Duplicate merge key")
        seen.add(key)
        if any(token not in tokens or token in special for token in (left,right,result)):
            raise ValueError("Merge refers to an invalid/control token")
        if tokens[left]+tokens[right]!=tokens[result]:raise ValueError("Merged token bytes do not match inputs")
        address=pair_hash(left,right,hash_bits)
        while address!=location:
            if slots[address]==0:raise ValueError("Unreachable merge hash entry")
            address=(address+1)&(len(slots)-1)
        pair_count+=1
    if pair_count!=manifest["merge_pairs"]:raise ValueError("Merge entry count mismatch")
    return manifest,files


def build_external_image(vocabulary_directory,unicode_directory,output_directory,capacity=8*1024*1024,*,trie_node_bits=18):
    manifest,files=validate_vocabulary(vocabulary_directory)
    unicode_manifest=json.loads((unicode_directory/"unicode_manifest.json").read_text(encoding="utf-8"))
    if unicode_manifest.get("abi")!=1 or unicode_manifest.get("codepoints")!=0x110000 or unicode_manifest.get("class_bits")!=2:
        raise ValueError("Unsupported Unicode image ABI")
    unicode_data=verified_bytes(unicode_directory/"unicode_classes.bin",unicode_manifest)
    if len(unicode_data)!=278528:raise ValueError("Incomplete Unicode class table")
    trie,trie_files=compile_trie(ordinary_tokens(files["directory.bin"],files["string_pool.bin"]),
                                id_bits=manifest["id_bits"],node_bits=trie_node_bits)
    specifications=[
        ("directory","directory.bin",files["directory.bin"],len(files["directory.bin"])),
        ("string_pool","string_pool.bin",files["string_pool.bin"],8*(1<<manifest["pool_word_addr_bits"])),
        ("merge_hash","merge_hash.bin",files["merge_hash.bin"],len(files["merge_hash.bin"])),
        ("unicode_classes","unicode_classes.bin",unicode_data,len(unicode_data)),
        ("byte_vocabulary","byte_tokens.bin",files["byte_tokens.bin"],1024),
        ("trie_nodes","trie_nodes.bin",trie_files["trie_nodes.bin"],len(trie_files["trie_nodes.bin"])),
        ("trie_edges","trie_edges.bin",trie_files["trie_edges.bin"],len(trie_files["trie_edges.bin"])),
    ]
    regions=[];offset=0
    for name,filename,data,reserved in specifications:
        offset=(offset+63)&~63
        regions.append({"name":name,"source":filename,"base":offset,"bytes":len(data),
                        "capacity":reserved,"sha256":hashlib.sha256(data).hexdigest()})
        offset+=reserved
    offset=(offset+63)&~63
    if offset>capacity:raise ValueError(f"Complete vocabulary needs {offset} bytes; external capacity is {capacity}")
    image=bytearray(capacity)
    for region,(_,_,data,_)in zip(regions,specifications):image[region["base"]:region["base"]+len(data)]=data
    result={"abi":1,"target":"xcsu35p-sbvb625-2-e","model":manifest["name"],
            "capacity_bytes":capacity,"regions":regions,"workspace_base":offset,
            "workspace_capacity":capacity-offset,"workspace_plan_verified":False,
            "vocabulary_entries":manifest["vocabulary_entries"],"merge_pairs":manifest["merge_pairs"],
            "id_bits":manifest["id_bits"],"rank_bits":manifest["rank_bits"],
            "hash_addr_bits":manifest["hash_addr_bits"],"vocab_addr_bits":manifest["vocab_addr_bits"],
            "pool_word_addr_bits":manifest["pool_word_addr_bits"],"pretokenizer":manifest["pretokenizer"],
            "unicode_source":unicode_manifest["regex_package_version"],
            "trie":{key:value for key,value in trie.items()if key!="files"},
            "image_bytes":len(image),"image_sha256":hashlib.sha256(image).hexdigest(),
            "required_cache_contract":{"data_bits":72,"max_request_bytes":9,"cache_line_bytes":64}}
    output_directory.mkdir(parents=True,exist_ok=True)
    (output_directory/"external_memory.bin").write_bytes(image)
    (output_directory/"external_manifest.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--vocabulary",type=Path,required=True)
    parser.add_argument("--unicode",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--capacity-bytes",type=int,default=8*1024*1024)
    parser.add_argument("--trie-node-bits",type=int,default=18)
    args=parser.parse_args()
    result=build_external_image(args.vocabulary,args.unicode,args.output,args.capacity_bytes,trie_node_bits=args.trie_node_bits)
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
