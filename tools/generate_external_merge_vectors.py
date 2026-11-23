"""Full-model external merge fixtures, including pieces beyond 4096 bytes."""
import argparse
import os
import random
from pathlib import Path
import regex
import tiktoken
from vocabulary_image import compile_image,tiktoken_vocabulary
from unicode_profiles import export_unicode_image
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
    enc=tiktoken.get_encoding("cl100k_base");rng=random.Random(20261104)
    corpus=["hello world","I'm we're THEY'LL I'VE don't cannot","1234567890 3.141592653589793",
            'JSON: "quote", \\,\n\t.',"   many  spaces\t\tend \n\r\n","a"*513,"abababababababababab", "",
            "café naïve Straße Ελληνικά Русский العربية 中文 日本語 한국어","🙂🤖🦙 a\u0301 café\u00a0space"]
    alphabet=list("abcXYZ0123456789 ,.!?\n\t'_")+list("é中🙂ΣЖا")
    corpus += ["".join(rng.choices(alphabet,k=rng.randrange(1,50)))for _ in range(100)]
    records=[]
    for context,text in enumerate(corpus,1):
        pieces=regex.findall(enc._pat_str,text)or[""];whole=[]
        for i,piece in enumerate(pieces):
            raw=piece.encode();expected=enc._encode_single_piece(raw)if raw else[];whole.extend(expected)
            records.append((raw,expected,int(i+1==len(pieces)),context))
        assert whole==enc.encode_ordinary(text)
    pairs={(a,b)for a,b,_,_ in model.merges}
    byte=next(b for b in range(256)if(model.byte_ids[b],model.byte_ids[b])not in pairs)
    raw=bytes([byte])*4097
    records.append((raw,enc._encode_single_piece(raw),1,0xbeef))
    with(out/"pieces.txt").open("w",encoding="ascii")as stream:
        for raw,expected,last,context in records:
            ids=[model.byte_ids[b]for b in raw]
            stream.write(f"{len(ids)} {len(expected)} {last} {context}\n")
            stream.write(" ".join(map(str,ids))+"\n"+" ".join(map(str,expected))+"\n")
    (out/"config.txt").write_text(f'{manifest["workspace_base"]} 65536\n',encoding="ascii")
    print(f"Generated {len(records)} native-reference pieces including a {len(raw)}-byte unmergeable piece and a 513-byte repeated-letter piece")


if __name__=="__main__":main()
