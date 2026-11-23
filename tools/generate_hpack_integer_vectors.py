"""Independent python-hpack prefix integer vectors and bounded error cases."""
import argparse
from pathlib import Path
import random
from hpack.hpack import encode_integer,decode_integer
from hpack.exceptions import HPACKDecodingError


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261104);count=0
    with(args.output/"vectors.txt").open("w",encoding="ascii")as stream:
        def write(encoded,bits,value,status=0,last=1,mode=0):
            nonlocal count
            count+=1;context=count*37&65535
            if status==0:
                reference,used=decode_integer(encoded,bits);assert reference==value and used==len(encoded)and value<=0xffffffff
            stream.write(f"{len(encoded)} {bits} {value if status==0 else 0} {status} {last} {context} {mode}\n"+" ".join(map(str,encoded))+"\n")
        for bits in range(1,9):
            mask=(1<<bits)-1
            values=list(range(mask+1))+[mask+1,127,128,1337,(1<<14)-1,(1<<21)-1,(1<<28)-1,(1<<32)-1]
            values += [rng.randrange(1<<32)for _ in range(1000)]
            for value in values:
                encoded=bytearray(encode_integer(value,bits));encoded[0]|=rng.randrange(256)&~mask
                write(encoded,bits,value,last=rng.randrange(2))
            for value in((1<<32),(1<<35)-1):write(encode_integer(value,bits),bits,0,status=1)
            for value in(mask,1337,0xffffffff):
                truncated=bytes(encode_integer(value,bits))[:-1]
                try:decode_integer(truncated,bits)
                except HPACKDecodingError:pass
                else:raise AssertionError("Reference accepted truncated integer")
                write(truncated,bits,0,status=2)
            write(bytes([mask])+b"\x80\x00",bits,mask,last=0)
            write(bytes([mask])+b"\x80"*4+b"\x00",bits,mask,last=1)
            write(bytes([mask])+b"\x80"*5,bits,0,status=5,last=0)
        write(b"\0",0,0,status=3);write(b"\0",9,0,status=3)
        write(encode_integer(32,5),5,0,status=4,mode=1)
        write(encode_integer(42,8),8,42)
    print(f"Generated {count} HPACK integer values/errors across all prefix widths, complete first-byte domain, 32-bit limits, truncation, length limits and context")


if __name__=="__main__":main()
