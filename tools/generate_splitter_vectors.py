"""RTL span references from independent tokenizer regex engines."""
import argparse
import os
import random
from pathlib import Path

import regex
import tiktoken
from unicode_profiles import LLAMA3_PATTERN,GPT2_PATTERN,unicode_classes


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(args.output.parent.parent/"tiktoken-cache"))
    patterns=[tiktoken.get_encoding("cl100k_base")._pat_str,LLAMA3_PATTERN,GPT2_PATTERN]
    rng=random.Random(20261104)
    alphabet="aBzZ09²Ⅸ\t\r\n \v\f\u0085\u00a0\u2028\u3000!?'\\-_.é中🙂\u0301ſ"
    texts=["", "I'm WE'RE THEY'LL I'VE DON'T", "'ſ'll've'RE", " \n\t  "," \n\t  x", "\n\r\n\tend",
           "!word !!word 123456789", "a"*65536," "*100000+"\n"+"\t"*100000+"word",
           " "*100000+"\n"+"\t"*100000," "*100+"word","'S 'T 'RE 'VE 'M 'LL 'D 'ſ"]
    texts += ["".join(rng.choice(alphabet)for _ in range(rng.randrange(0,100)))for _ in range(10000)]
    categories=unicode_classes();records=pieces=0;max_count=0
    with args.output.open("w",encoding="ascii")as stream:
        for profile,pattern in enumerate(patterns):
            matcher=regex.compile(pattern)
            for text in texts:
                spans=[(m.start(),m.end()-m.start())for m in matcher.finditer(text)]or[(0,0)]
                assert "".join(text[start:start+count]for start,count in spans)==text
                records+=1;pieces+=len(spans);max_count=max(max_count,len(text))
                stream.write(f"{len(text)} {profile} {records} {len(spans)}\n")
                for char in text:
                    cp=ord(char);raw=char.encode()
                    word=int.from_bytes(raw,"little")|(cp<<32)|(categories[cp]<<53)|(len(raw)<<55)
                    stream.write(f"{word:016x}\n")
                for i,(start,count)in enumerate(spans):stream.write(f"{start} {count} {int(i+1==len(spans))}\n")
    print(f"Generated {records} three-profile sequences / {pieces} spans, maximum {max_count} scalars")


if __name__=="__main__":main()
