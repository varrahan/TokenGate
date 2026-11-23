"""Exhaustive trie transitions, independent terminal expectations and misses."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from external_memory_image import validate_vocabulary,build_external_image
from trie_image import ordinary_tokens,validate_trie
from unicode_profiles import export_unicode_image
from vocabulary_image import compile_image,tiktoken_vocabulary


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--image",type=Path)
    parser.add_argument("--vocabulary",type=Path);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    if (args.image is None)!=(args.vocabulary is None):raise ValueError("Supply both image and vocabulary, or neither")
    if args.image is None:
        os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(out.parent/"tiktoken-cache"))
        args.vocabulary=out/"source";args.image=out/"image"
        compile_image(tiktoken_vocabulary("cl100k_base"),args.vocabulary)
        export_unicode_image(out/"unicode")
        build_external_image(args.vocabulary,out/"unicode",args.image)
    manifest=json.loads((args.image/"external_manifest.json").read_text());image=(args.image/"external_memory.bin").read_bytes()
    if hashlib.sha256(image).hexdigest()!=manifest["image_sha256"]:raise ValueError("Combined image integrity failure")
    _,source=validate_vocabulary(args.vocabulary);ordinary=ordinary_tokens(source["directory.bin"],source["string_pool.bin"])
    regions={entry["name"]:entry for entry in manifest["regions"]}
    def region(name):
        entry=regions[name];return image[entry["base"]:entry["base"]+entry["bytes"]]
    nodes,edges=region("trie_nodes"),region("trie_edges");validate_trie(nodes,edges,ordinary)
    with(out/"memory.mem").open("w",encoding="ascii")as stream:
        for i in range(0,len(image),8):stream.write(f"{int.from_bytes(image[i:i+8],'little'):016x}\n")
    reverse={data:token for token,data in ordinary.items()};prefixes=[None]*(len(nodes)//6);prefixes[0]=b""
    queries=0;leaf=None;zero_child=None
    with(out/"queries.txt").open("w",encoding="ascii")as stream:
        def query(parent,label,found,terminal,child,token):
            nonlocal queries
            stream.write(f"{parent} {label} {found} {terminal} {child} {token} {queries&1} {queries&65535}\n");queries+=1
        for parent in range(len(nodes)//6):
            record=int.from_bytes(nodes[parent*6:parent*6+6],"little");base=record&0x3ffff;count=(record>>18)&511;labels=set()
            for location in range(base,base+count):
                word=int.from_bytes(edges[location*4:location*4+4],"little");label=word&255;child=(word>>8)&0x3ffff
                labels.add(label);prefixes[child]=prefixes[parent]+bytes([label]);expected=reverse.get(prefixes[child])
                query(parent,label,1,int(expected is not None),child,expected if expected is not None else 0)
                if parent==0 and label==0:zero_child=child
                child_record=int.from_bytes(nodes[child*6:child*6+6],"little")
                if leaf is None and ((child_record>>18)&511)==0:leaf=(parent,label,child)
            missing=next((label for label in range(256)if label not in labels),None)
            if missing is not None:query(parent,missing,0,0,0,0)
    if zero_child is None or leaf is None:raise ValueError("Full-byte vocabulary/leaf fixture is missing")
    config=(regions["trie_nodes"]["base"],regions["trie_edges"]["base"],len(nodes)//6,len(edges)//4,zero_child,*leaf)
    (out/"config.txt").write_text(" ".join(map(str,config))+"\n",encoding="ascii")
    print(f"Generated {queries} transitions/misses covering all {len(nodes)//6} trie nodes and {len(edges)//4} edges")


if __name__=="__main__":main()
