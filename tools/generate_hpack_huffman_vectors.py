"""Independent HPACK Huffman references, exhaustive short encoded strings."""
import argparse
from pathlib import Path
import random
from hpack.huffman import HuffmanEncoder
from hpack.huffman_constants import REQUEST_CODES,REQUEST_CODES_LENGTH
from hpack.huffman_table import decode_huffman
from hpack.exceptions import HPACKDecodingError


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    encoder=HuffmanEncoder(REQUEST_CODES,REQUEST_CODES_LENGTH);rng=random.Random(20261104)
    assert encoder.encode(b"www.example.com")==bytes.fromhex("f1e3c2e5f23a6ba0ab90f4ff")
    count=valid=invalid=decoded_bytes=0
    with(args.output/"vectors.txt").open("w",encoding="ascii")as stream:
        def write(encoded,*,mode=0,code=0):
            nonlocal count,valid,invalid,decoded_bytes
            try:decoded=decode_huffman(encoded);bad=0
            except HPACKDecodingError:decoded=b"";bad=1
            if mode&4:decoded=b"";bad=1;code=3
            count+=1;valid+=not bad;invalid+=bad;decoded_bytes+=len(decoded)
            context=count*37&0xffff
            stream.write(f"{len(encoded)} {len(decoded)} {bad} {code} {context} {mode}\n"+" ".join(map(str,encoded))+"\n"+" ".join(map(str,decoded))+"\n")
        originals=[b"",b"www.example.com",b"no-cache",b"custom-key",b"custom-value",bytes(range(256))]
        originals += [bytes([byte])for byte in range(256)]
        originals += [rng.randbytes(rng.randrange(0,513))for _ in range(500)]
        originals += [rng.randbytes(8193)]
        for i,original in enumerate(originals):
            encoded=encoder.encode(original);assert decode_huffman(encoded)==original
            write(encoded,mode=i%4)
        for value in range(256):write(bytes([value]),mode=value%4)
        for value in range(65536):write(value.to_bytes(2,"big"),mode=value%4)
        write(b"\xff"*4,code=1);write(b"\xff"*4+b"tail",code=1)
        write(encoder.encode(b"context changes while a string is active"),mode=4)
        write(encoder.encode(b"after-errors"),mode=3)
    print(f"Generated {count} strings: {valid} valid/{invalid} invalid, {decoded_bytes} committed reference bytes; every 1/2-byte encoding, all symbols, EOF/padding/EOS, context and long strings")


if __name__=="__main__":main()
