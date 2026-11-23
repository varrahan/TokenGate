"""Runtime trie image ABI, exhaustive structural validation and reference lookup.

Node (6 LE bytes): edge base [node_bits-1:0], count [node_bits+8:node_bits],
token ID [node_bits+9+id_bits-1:node_bits+9], terminal flag above ID.
Edge (4 LE bytes): byte [7:0], child [node_bits+7:8]. Reserved bits are zero.
This is a trie over ordinary token bytes; special tokens use inverse filtering.
"""
import argparse
import hashlib
import json
from pathlib import Path
from vocabulary_image import decode_image


def check_widths(id_bits,node_bits):
    if not(1<=id_bits<=32 and 1<=node_bits<=24 and node_bits+10+id_bits<=48):
        raise ValueError("Trie fields exceed the six-byte node/four-byte edge ABI")


def ordinary_tokens(index,pool):
    result={}
    for token_id in range(len(index)//8):
        word=int.from_bytes(index[token_id*8:token_id*8+8],"little")
        if word&2 and not word&1:result[token_id]=decode_image(index,pool,token_id)
    return result


def compile_trie(tokens,*,id_bits=17,node_bits=18):
    check_widths(id_bits,node_bits)
    children=[{}];terminals=[None];spellings={}
    for token_id,data in tokens.items():
        if type(token_id)is not int or not 0<=token_id<1<<id_bits:
            raise ValueError("Trie token ID exceeds capacity")
        if not isinstance(data,bytes):raise ValueError("Trie vocabulary must contain byte strings")
        if data in spellings:raise ValueError("Duplicate ordinary token bytes")
        spellings[data]=token_id
    for token_id,data in sorted(tokens.items()):
        node=0
        for byte in data:
            child=children[node].get(byte)
            if child is None:
                if len(children)>=1<<node_bits:raise ValueError("Trie node capacity exceeded")
                child=len(children);children[node][byte]=child;children.append({});terminals.append(None)
            node=child
        terminals[node]=token_id
    nodes=bytearray();edges=bytearray();cursor=0
    for branches,token_id in zip(children,terminals):
        if cursor>=1<<node_bits:raise ValueError("Trie edge capacity exceeded")
        word=cursor|(len(branches)<<node_bits)
        if token_id is not None:word|=(token_id<<(node_bits+9))|(1<<(node_bits+9+id_bits))
        nodes.extend(word.to_bytes(6,"little"))
        for byte,child in sorted(branches.items()):edges.extend((byte|(child<<8)).to_bytes(4,"little"))
        cursor+=len(branches)
    nodes=bytes(nodes);edges=bytes(edges)
    validate_trie(nodes,edges,tokens,id_bits=id_bits,node_bits=node_bits)
    files={"trie_nodes.bin":nodes,"trie_edges.bin":edges}
    manifest={"abi":1,"id_bits":id_bits,"node_bits":node_bits,"root":0,
              "nodes":len(children),"edges":cursor,"terminals":len(tokens),
              "node_bytes":6,"edge_bytes":4,"max_token_bytes":max(map(len,tokens.values()),default=0),
              "files":{name:{"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}for name,data in files.items()}}
    return manifest,files


def validate_trie(nodes,edges,expected=None,*,id_bits=17,node_bits=18):
    check_widths(id_bits,node_bits)
    if len(nodes)%6 or not nodes or len(edges)%4:raise ValueError("Invalid trie image sizes")
    node_count=len(nodes)//6;edge_count=len(edges)//4
    if node_count>1<<node_bits or edge_count>=1<<node_bits:raise ValueError("Trie image capacity exceeded")
    pointer_mask=(1<<node_bits)-1;token_mask=(1<<id_bits)-1;flag=node_bits+9+id_bits
    records=[];in_degree=[0]*node_count;cursor=0
    for node_id in range(node_count):
        word=int.from_bytes(nodes[node_id*6:node_id*6+6],"little")
        base=word&pointer_mask;count=(word>>node_bits)&511;token=(word>>(node_bits+9))&token_mask;terminal=bool(word>>flag&1)
        if word>>(flag+1) or not terminal and token:raise ValueError("Invalid trie node flags")
        if count>256 or base!=cursor or base+count>edge_count:raise ValueError("Invalid trie edge range")
        if not count and not terminal and node_count>1:raise ValueError("Nonterminal trie leaf")
        previous=-1
        for location in range(base,base+count):
            edge=int.from_bytes(edges[location*4:location*4+4],"little")
            byte=edge&255;child=(edge>>8)&pointer_mask
            if edge>>(node_bits+8):raise ValueError("Invalid trie edge flags")
            if byte<=previous:raise ValueError("Trie edge labels must be unique and sorted")
            if not node_id<child<node_count:raise ValueError("Invalid/cyclic trie child pointer")
            in_degree[child]+=1;previous=byte
        records.append((base,count,token if terminal else None));cursor+=count
    if cursor!=edge_count or any(degree!=1 for degree in in_degree[1:])or in_degree[0]:
        raise ValueError("Unreachable/shared trie node or unowned edge")
    # Iterative DFS avoids recursion-depth and quadratic prefix construction
    # for long tokens. Copy bytes only at terminal nodes.
    decoded={};path=bytearray();stack=[(0,0)]
    while stack:
        node,position=stack[-1];base,count,token=records[node]
        if position==0 and token is not None:
            if token in decoded:raise ValueError("Duplicate trie terminal ID")
            decoded[token]=bytes(path)
        if position==count:
            stack.pop()
            if stack:path.pop()
        else:
            stack[-1]=(node,position+1)
            edge=int.from_bytes(edges[(base+position)*4:(base+position)*4+4],"little")
            path.append(edge&255);stack.append(((edge>>8)&pointer_mask,0))
    if expected is not None and decoded!=expected:raise ValueError("Trie terminals do not match the complete ordinary vocabulary")
    return decoded


def lookup_step(nodes,edges,node_id,byte,*,id_bits=17,node_bits=18):
    """Reference binary search for a single byte, with child terminal metadata."""
    if not 0<=node_id<len(nodes)//6 or not 0<=byte<=255:raise ValueError("Invalid trie query")
    mask=(1<<node_bits)-1;word=int.from_bytes(nodes[node_id*6:node_id*6+6],"little")
    base=word&mask;low=0;high=(word>>node_bits)&511
    while low<high:
        middle=(low+high)//2;edge=int.from_bytes(edges[(base+middle)*4:(base+middle)*4+4],"little")
        if edge&255<byte:low=middle+1
        elif edge&255>byte:high=middle
        else:
            child=(edge>>8)&mask;record=int.from_bytes(nodes[child*6:child*6+6],"little")
            terminal=bool(record>>(node_bits+9+id_bits)&1)
            return child,terminal,(record>>(node_bits+9))&((1<<id_bits)-1)if terminal else 0
    return None


def lookup_token(nodes,edges,data,*,id_bits=17,node_bits=18):
    node=0
    for byte in data:
        result=lookup_step(nodes,edges,node,byte,id_bits=id_bits,node_bits=node_bits)
        if result is None:return None
        node=result[0]
    record=int.from_bytes(nodes[node*6:node*6+6],"little")
    return (record>>(node_bits+9))&((1<<id_bits)-1)if record>>(node_bits+9+id_bits)&1 else None


def build_from_vocabulary(vocabulary_directory,output_directory,*,node_bits=18):
    from external_memory_image import validate_vocabulary
    source,files=validate_vocabulary(vocabulary_directory)
    manifest,payloads=compile_trie(ordinary_tokens(files["directory.bin"],files["string_pool.bin"]),id_bits=source["id_bits"],node_bits=node_bits)
    manifest["model"]=source["name"]
    output_directory.mkdir(parents=True,exist_ok=True)
    for name,data in payloads.items():(output_directory/name).write_bytes(data)
    (output_directory/"trie_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--vocabulary",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--node-bits",type=int,default=18)
    args=parser.parse_args();print(json.dumps(build_from_vocabulary(args.vocabulary,args.output,node_bits=args.node_bits),indent=2))


if __name__=="__main__":main()
