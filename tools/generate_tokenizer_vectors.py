"""Whole raw-text references; RTL supplies all pretokenization boundaries."""
import argparse
import os
import random
from pathlib import Path
import regex
import tiktoken
from vocabulary_image import compile_image,tiktoken_vocabulary
from unicode_profiles import export_unicode_image,LLAMA3_PATTERN,GPT2_PATTERN
from external_memory_image import build_external_image


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(out.parent/"tiktoken-cache"))
    model=tiktoken_vocabulary("cl100k_base");compile_image(model,out/"source");export_unicode_image(out/"unicode")
    manifest=build_external_image(out/"source",out/"unicode",out/"image")
    image=(out/"image"/"external_memory.bin").read_bytes()
    with(out/"memory.mem").open("w",encoding="ascii")as stream:
        for i in range(0,len(image),8):stream.write(f"{int.from_bytes(image[i:i+8],'little'):016x}\n")
    regions={item["name"]:item for item in manifest["regions"]}
    # Runtime allocation, not a maximum prompt size inferred from AXIS width.
    floor=manifest["workspace_base"];scalar=floor;merge=scalar+524288;commit=merge+524288
    def region(name):return regions[name]["base"]
    config=[region("unicode_classes"),region("merge_hash"),region("trie_nodes"),region("trie_edges"),0,0,
            floor,scalar,524288,merge,524288,commit,len(image)-commit]
    # Counts are derived from the emitted packed regions, including arbitrary
    # model versions; there is no fixture-only truncated vocabulary.
    config[4]=regions["trie_nodes"]["bytes"]//6
    config[5]=regions["trie_edges"]["bytes"]//4
    (out/"config.txt").write_text(" ".join(map(str,config))+"\n",encoding="ascii")
    enc=tiktoken.get_encoding("cl100k_base");rng=random.Random(20261104)
    special_id=enc._special_tokens["<|endoftext|>"]
    directory=int.from_bytes(image[special_id*8:special_id*8+8],"little")
    special_offset=(directory>>16)&0xffffffff;special_length=directory>>48
    replacement=b"<|reloaded!|>";assert len(replacement)==special_length
    special_tokens=dict(enc._special_tokens);del special_tokens["<|endoftext|>"];special_tokens[replacement.decode()]=special_id
    reloaded=tiktoken.Encoding(name="cl100k-runtime-special",pat_str=enc._pat_str,mergeable_ranks=enc._mergeable_ranks,special_tokens=special_tokens)
    assert reloaded.decode_bytes([special_id])==replacement
    (out/"reload.txt").write_text(f"{special_id} {region('string_pool')+special_offset} {special_length}\n"+
        " ".join(map(str,enc.decode_bytes([special_id])))+"\n"+" ".join(map(str,replacement))+"\n",encoding="ascii")
    texts=["", "hello world", "I'm we're THEY'LL I'VE DON'T", "  \n\t   end", "1234567890123456789",
           'JSON: "quote", \\,\n\t.', "café naïve Straße Ελληνικά Русский العربية 中文 日本語 한국어",
           "🙂🤖🦙 a\u0301 café\u00a0space", "a"*513,"\x00"*4097," "+"abc "*70]
    alphabet="abcXYZ0123456789 ,.!?\n\t'_é中🙂ΣЖا"
    texts += ["".join(rng.choices(alphabet,k=rng.randrange(1,110)))for _ in range(80)]
    count=ids=0
    with(out/"vectors.txt").open("w",encoding="ascii")as stream:
        for profile,pattern in enumerate([enc._pat_str,LLAMA3_PATTERN,GPT2_PATTERN]):
            for text in texts:
                raw=text.encode();expected=[token for piece in regex.findall(pattern,text)for token in enc._encode_single_piece(piece.encode())]
                if profile==0:assert expected==enc.encode_ordinary(text)
                count+=1;ids+=len(expected)
                stream.write(f"{len(raw)} {len(expected)} {profile} {count}\n")
                stream.write(" ".join(map(str,raw))+"\n"+" ".join(map(str,expected))+"\n")
    print(f"Generated {count} whole-text sequences/{ids} reference IDs, three profiles, full cl100k image, workspace={floor:#x}..{len(image):#x}")


if __name__=="__main__":main()
