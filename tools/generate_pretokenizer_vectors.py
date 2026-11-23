"""Independent byte-piece references and programmable Unicode memory image."""
import argparse
import os
import random
from pathlib import Path
import regex
import tiktoken
from unicode_profiles import LLAMA3_PATTERN,GPT2_PATTERN,packed_unicode_classes


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR",str(out.parent/"tiktoken-cache"))
    patterns=[tiktoken.get_encoding("cl100k_base")._pat_str,LLAMA3_PATTERN,GPT2_PATTERN]
    memory=bytearray(8388608);classes=packed_unicode_classes();memory[0x440000:0x440000+len(classes)]=classes
    with(out/"memory.mem").open("w",encoding="ascii")as stream:
        for i in range(0,len(memory),8):stream.write(f"{int.from_bytes(memory[i:i+8],'little'):016x}\n")
    rng=random.Random(20261104);alphabet="aBzZ09²Ⅸ\t\r\n \v\f\u0085\u00a0\u2028\u3000!?'\\-_.é中🙂\u0301ſ"
    texts=["", "I'm WE'RE THEY'LL I'VE DON'T", "'ſ'll've'RE", " \n\t  "," \n\t  x", "\n\r\n\tend",
           "!word !!word 123456789", "a"*4097," "*10000+"\n"+"\t"*10000+"word","🙂🤖 café 中"]
    texts += ["".join(rng.choice(alphabet)for _ in range(rng.randrange(0,65)))for _ in range(200)]
    sequence=0;pieces_total=bytes_total=0
    with(out/"vectors.txt").open("w",encoding="ascii")as stream:
        def write_case(raw,profile,expected,error=0,status=0,mode=0,capacity=0x37bc00):
            nonlocal sequence,pieces_total,bytes_total
            sequence+=1
            stream.write(f"{len(raw)} {profile} {sequence} {capacity} {error} {status} {mode} {len(expected)}\n")
            stream.write(" ".join(map(str,raw))+"\n")
            for record in expected:stream.write(" ".join(map(str,record))+"\n")
        for profile,pattern in enumerate(patterns):
            matcher=regex.compile(pattern)
            for text in texts:
                pieces=matcher.findall(text)or[""];records=[]
                for i,piece in enumerate(pieces):
                    raw=piece.encode();pieces_total+=1;bytes_total+=len(raw)
                    if raw:
                        records.extend((byte,1,int(j+1==len(raw)),int(i+1==len(pieces) and j+1==len(raw)))for j,byte in enumerate(raw))
                    else:records.append((0,0,1,1))
                write_case(text.encode(),profile,records)
        write_case(b"abc",3,[],1)
        write_case(b"abc",0,[],2,mode=1)
        write_case(b"abc",0,[],3,capacity=0)
        for raw,status in [(b"prefix\xfftail",1),(b"prefix\xe2\x82",2)]:write_case(raw,0,[],4,status)
        write_case(b"ABCD",0,[],4,3,mode=4)
        write_case(b"ABCD",0,[],5,2,mode=5)
        write_case(b"ABCD",0,[],5,0x12,mode=6)
        write_case(b"ABCD",0,[],6,4,mode=7)
        write_case(b"ABCD",0,[],7,2,mode=8)
        write_case(b"A",0,[],9,2,mode=9)
        write_case(b"A",0,[],10,0,mode=10)
        # A valid final record proves recovery after all negative paths.
        write_case(b"OK",0,[(79,1,0,0),(75,1,1,1)])
    print(f"Generated {sequence} frontend sequences, {pieces_total} reference pieces, {bytes_total} output bytes")


if __name__=="__main__":main()
