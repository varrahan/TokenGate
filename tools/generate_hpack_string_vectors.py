"""Complete HPACK string prefixes/payloads, with independent library decoding."""
import argparse
from pathlib import Path
import random
from hpack.hpack import encode_integer,Decoder
from hpack.huffman import HuffmanEncoder
from hpack.huffman_constants import REQUEST_CODES,REQUEST_CODES_LENGTH


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261119);encoder=HuffmanEncoder(REQUEST_CODES,REQUEST_CODES_LENGTH);count=0
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        def emit(encoded,raw=b'',status=0,detail=0,last=1,mode=0,payload_bytes=None):
            nonlocal count
            count+=1
            stream.write(f'{len(encoded)} {len(raw)} {status} {detail} {last} {mode} {payload_bytes if payload_bytes is not None else len(encoded)-1}\n')
            for data in(encoded,raw):stream.write(' '.join(f'{b:02x}'for b in data)+'\n')
        def valid(raw,huffman,last):
            data=encoder.encode(raw)if huffman else raw
            encoded=bytes(encode_integer(len(data),7));encoded=bytes([encoded[0]|(0x80 if huffman else 0)])+encoded[1:]+data
            # Decode a literal header with a fresh name and this exact value.
            reference=Decoder().decode(b'\x00\x01x'+encoded,raw=True)
            assert reference==[(b'x',raw)]
            emit(encoded,raw,last=last,payload_bytes=len(data))
        values=[b'',b'www.example.com',bytes(range(256)),b'a'*8193]
        values += [bytes([b])for b in range(256)]
        values += [bytes(rng.randrange(256)for _ in range(rng.choice([0,1,2,3,7,8,31,126,127,128,255,512])))for _ in range(500)]
        for raw in values:
            for huffman in(False,True):valid(raw,huffman,rng.randrange(2))
        emit(b'\x04abc',status=2,payload_bytes=3)
        emit(b'\x01',status=2,payload_bytes=0)
        emit(b'\x7f',status=1,detail=2,payload_bytes=0)
        emit(b'\x7f'+b'\x80'*5,status=1,detail=5,last=0,payload_bytes=0)
        emit(bytes(encode_integer(1<<32,7)),status=1,detail=1,payload_bytes=0)
        emit(b'\x84'+b'\xff'*4,status=3,detail=1,payload_bytes=4)
        emit(b'\x81\xff',status=3,detail=2,payload_bytes=1)
        emit(b'\x04abcd',status=4,mode=1,payload_bytes=4)
        data=encoder.encode(b'hello world')
        emit(bytes([0x80|len(data)])+data,status=4,mode=1,payload_bytes=len(data))
        emit(bytes([0x80|len(data)+1])+data,status=2,payload_bytes=len(data))
        valid(b'recovery',True,1)
    print(f'Generated {count} complete HPACK strings, raw/Huffman lengths, block boundaries and errors')


if __name__=='__main__':main()
