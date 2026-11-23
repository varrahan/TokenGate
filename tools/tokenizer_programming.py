"""Validated host programming plans for tokenizer_mmio.

Plans retain the entire model, including empty hash/directory slots. Each
doorbell is a completed AXI-Lite write before the next operation executes.
An adapter implementing read32/write32 can use execute_plan on real hardware;
the binary stream is also consumed by the compiled full-load RTL regression.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import time
from unicode_profiles import GPT2_PATTERN,GPT2_COMPACT_PATTERN,CL100K_COMPACT_PATTERN,LLAMA3_PATTERN
from external_memory_image import validate_vocabulary_data
from trie_image import ordinary_tokens,validate_trie

WRITE=1;POLL=2;ASSERT=3
RECORD=struct.Struct(">HHI")


@dataclass(frozen=True)
class Operation:
    kind:int
    address:int
    value:int


def profile_for(manifest):
    metadata=manifest["pretokenizer"]
    if metadata["kind"]=="regex":
        pattern=metadata["pattern"]
        if pattern==CL100K_COMPACT_PATTERN:return 0
        if pattern==LLAMA3_PATTERN:return 1
        if pattern==GPT2_COMPACT_PATTERN:return 2
        def canonical(pattern):return pattern.replace(r"[\p{L}]",r"\p{L}").replace(r"[\p{N}]",r"\p{N}")
        if canonical(pattern)==canonical(GPT2_PATTERN):return 2
    elif metadata["kind"]=="huggingface":
        pre=metadata.get("pre_tokenizer")or{}
        if pre.get("type")=="ByteLevel"and not pre.get("add_prefix_space",False)and pre.get("use_regex",True)and metadata.get("post_processor")is None:return 2
    raise ValueError("Model requires an unsupported normalization/pretokenization profile")


def validate_external_payload(directory):
    directory=Path(directory);manifest=json.loads((directory/"external_manifest.json").read_text())
    image=(directory/"external_memory.bin").read_bytes()
    if manifest.get("abi")!=1 or len(image)!=8388608 or manifest.get("image_bytes")!=len(image):raise ValueError("Unsupported external image ABI/capacity")
    if hashlib.sha256(image).hexdigest()!=manifest["image_sha256"]:raise ValueError("External image checksum mismatch")
    if [manifest[k]for k in("id_bits","rank_bits","hash_addr_bits","vocab_addr_bits","pool_word_addr_bits")]!=[17,17,18,17,17]:raise ValueError("Image widths do not match the current SCU35 hardware")
    regions={};previous_end=0
    for region in manifest["regions"]:
        base,size,capacity=(region[key]for key in("base","bytes","capacity"))
        if region["name"]in regions or not 0<=previous_end<=base or not 0<=size<=capacity or base+capacity>manifest["workspace_base"]:raise ValueError("Invalid or overlapping image regions")
        if hashlib.sha256(image[base:base+size]).hexdigest()!=region["sha256"]:raise ValueError("Region checksum mismatch")
        regions[region["name"]]=region;previous_end=base+capacity
    required={"directory","string_pool","merge_hash","unicode_classes","byte_vocabulary","trie_nodes","trie_edges"}
    if set(regions)!=required or not previous_end<=manifest["workspace_base"]<=len(image):raise ValueError("Incomplete external image")
    if "vocabulary_entries"not in manifest or"merge_pairs"not in manifest:raise ValueError("Regenerate the external manifest with source entry/pair counts")
    def payload(name):
        region=regions[name];return image[region["base"]:region["base"]+region["bytes"]]
    files={filename:payload(name)for name,filename in(("directory","directory.bin"),("string_pool","string_pool.bin"),("byte_vocabulary","byte_tokens.bin"),("merge_hash","merge_hash.bin"))}
    validate_vocabulary_data(manifest,files)
    if len(payload("unicode_classes"))!=278528:raise ValueError("Incomplete Unicode classes")
    validate_trie(payload("trie_nodes"),payload("trie_edges"),ordinary_tokens(files["directory.bin"],files["string_pool.bin"]),id_bits=17,node_bits=18)
    return manifest,image,regions


def programming_plan(directory,*,epoch,scalar_bytes=524288,merge_bytes=524288,commit_bytes=None):
    manifest,image,regions=validate_external_payload(directory);profile=profile_for(manifest)
    floor=manifest["workspace_base"];scalar=floor;merge=(scalar+scalar_bytes+63)&~63;commit=(merge+merge_bytes+63)&~63
    if commit_bytes is None:commit_bytes=len(image)-commit
    if min(scalar_bytes,merge_bytes,commit_bytes)<0 or commit+commit_bytes>len(image):raise ValueError("Working allocation exceeds external capacity")
    values=[profile,regions["unicode_classes"]["base"],regions["merge_hash"]["base"],regions["trie_nodes"]["base"],regions["trie_edges"]["base"],
            regions["trie_nodes"]["bytes"]//6,regions["trie_edges"]["bytes"]//4,floor,scalar,scalar_bytes,merge,merge_bytes,commit,commit_bytes,
            regions["directory"]["base"],regions["string_pool"]["base"],0]
    if epoch<1 or epoch>0xffffffff:raise ValueError("Invalid expected epoch")
    # Validation above precedes the first emitted hardware operation.
    yield Operation(WRITE,8,1);yield Operation(POLL,4,0x00010001)
    for address,value in zip(range(0x30,0x74,4),values):yield Operation(WRITE,address,value)
    yield Operation(WRITE,0x1c,9)
    for offset in range(0,floor,9):
        payload=image[offset:min(offset+9,floor)];word=int.from_bytes(payload,"little")
        if len(payload)!=9:yield Operation(WRITE,0x1c,len(payload))
        for address,value in((0x18,offset),(0x20,word&0xffffffff),(0x24,word>>32&0xffffffff),(0x28,word>>64),(0x2c,1)):
            yield Operation(WRITE,address,value)
    yield Operation(WRITE,0x10,1);yield Operation(WRITE,8,8);yield Operation(WRITE,8,2)
    yield Operation(POLL,4,0x00050004);yield Operation(ASSERT,0xc,epoch);yield Operation(ASSERT,0x14,0)


def write_plan(operations,path):
    path=Path(path);count=0;digest=hashlib.sha256()
    with path.open("wb")as stream:
        for op in operations:
            record=RECORD.pack(op.kind,op.address,op.value);stream.write(record);digest.update(record);count+=1
    return {"abi":1,"record_bytes":8,"record_endian":"big","operations":count,"bytes":path.stat().st_size,"sha256":digest.hexdigest()}


def read_plan(path,metadata=None):
    path=Path(path)
    if metadata is not None:
        if metadata.get("abi")!=1 or path.stat().st_size!=metadata["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest()!=metadata["sha256"]:raise ValueError("Programming plan integrity failure")
    with path.open("rb")as stream:
        while record:=stream.read(RECORD.size):
            if len(record)!=RECORD.size:raise ValueError("Truncated programming plan")
            op=Operation(*RECORD.unpack(record))
            if op.kind not in(WRITE,POLL,ASSERT)or op.address%4:raise ValueError("Invalid programming operation")
            yield op


def execute_plan(operations,*,read32,write32,poll_timeout=30.0):
    """write32 must wait for AXI-Lite B and raise on bus/transport failures.

    An exception stops the plan before any subsequent commit. Recovery must
    explicitly reacquire the epoch grant and load a complete validated image.
    """
    for op in operations:
        if op.kind==WRITE:write32(op.address,op.value)
        elif op.kind==ASSERT:
            actual=read32(op.address)
            if actual!=op.value:raise RuntimeError(f"MMIO assertion {op.address:#x}: {actual:#x} != {op.value:#x}")
        elif op.kind==POLL:
            mask,wanted=op.value>>16,op.value&0xffff;deadline=time.monotonic()+poll_timeout
            while read32(op.address)&mask!=wanted:
                if time.monotonic()>=deadline:raise TimeoutError(f"MMIO status timeout at {op.address:#x}")
        else:raise ValueError("Invalid programming operation")


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("image",type=Path);parser.add_argument("--epoch",type=int,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();metadata=write_plan(programming_plan(args.image,epoch=args.epoch),args.output)
    args.output.with_suffix(args.output.suffix+".json").write_text(json.dumps(metadata,indent=2)+"\n")
    print(json.dumps(metadata,indent=2))


if __name__=="__main__":main()
