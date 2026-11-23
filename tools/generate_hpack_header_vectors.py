"""Stateful raw HPACK blocks/reference headers and connection dictionaries."""
import argparse
import copy
from pathlib import Path
import random
import struct
from hpack import Encoder,Decoder,NeverIndexedHeaderTuple
from hpack.hpack import encode_integer
from hpack.huffman import HuffmanEncoder
from hpack.huffman_constants import REQUEST_CODES,REQUEST_CODES_LENGTH


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261120);bases=[0x1003,0x8001,0x10005];capacities=[4096,512,1024]
    encoders=[];decoders=[];count=0;successes=0;errors=0
    huffman=HuffmanEncoder(REQUEST_CODES,REQUEST_CODES_LENGTH)
    def reset(ctx):
        encoder=Encoder();decoder=Decoder(max_header_list_size=262144)
        encoder.header_table_size=capacities[ctx];decoder.header_table_size=capacities[ctx];decoder.max_allowed_table_size=capacities[ctx]
        if ctx<len(encoders):encoders[ctx]=encoder;decoders[ctx]=decoder
        else:encoders.append(encoder);decoders.append(decoder)
    for ctx in range(3):reset(ctx)
    def integer(value,bits,flags=0):
        data=bytearray(encode_integer(value,bits));data[0]|=flags;return bytes(data)
    def string(raw,huff=False):
        data=huffman.encode(raw)if huff else raw;return integer(len(data),7,0x80 if huff else 0)+data
    def literal(name,value,kind=1,huff=False,index=0):
        prefix=integer(index,6 if kind==1 else 4,0x40 if kind==1 else 0x10 if kind==3 else 0)
        return prefix+(string(name,huff)if not index else b'')+string(value,huff)
    def scan(decoder,encoded):
        found=[];position=0
        while position<len(encoded):
            data=memoryview(encoded)[position:];first=data[0]
            if first&0x80:header,used=decoder._decode_indexed(data);kind=0
            elif first&0x40:header,used=decoder._decode_literal_index(data);kind=1
            elif first&0x20:used=decoder._update_encoding_context(data);header=None;kind=0
            else:header,used=decoder._decode_literal_no_index(data);kind=3 if first&0x10 else 2
            if header is not None:found.append((bytes(header[0]),bytes(header[1]),kind))
            position+=used
        return found
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        def emit(ctx,encoded,status=0,detail=0,aux=0,mode=0,allowed=None,required=0,required_max=0,scratch=32768,limit=262144,override=None,expect_reference_error=False):
            nonlocal count,successes,errors
            decoder=decoders[ctx];before=copy.deepcopy(decoder);count+=1
            if allowed is None:allowed=decoder.max_allowed_table_size
            table=before.header_table;used=sum(32+len(n)+len(v)for n,v in table.dynamic_entries)
            request=[len(encoded),bases[ctx],capacities[ctx],table.maxsize,allowed,used,len(table.dynamic_entries),required,required_max,0x700005,scratch,limit,count*37&65535]
            if override:
                for i,value in override.items():request[i]=value
            headers=[];image=b''
            if status==0:
                decoder.max_allowed_table_size=allowed;decoder.max_header_list_size=limit
                golden=list(decoder.decode(encoded,raw=True));headers=scan(before,encoded)
                assert [(n,v)for n,v,_ in headers]==golden
                image=b''.join(struct.pack('<II',len(n),len(v))+bytes(24)+n+v for n,v in decoder.header_table.dynamic_entries)
                result=[0,0,0,decoder.header_table.maxsize,len(image),len(decoder.header_table.dynamic_entries),len(headers),sum(32+len(n)+len(v)for n,v in golden)]
                successes+=1
            else:
                if expect_reference_error:
                    candidate=copy.deepcopy(decoder);candidate.max_allowed_table_size=allowed;candidate.max_header_list_size=limit
                    try:candidate.decode(encoded,raw=True)
                    except Exception:pass
                    else:raise AssertionError(f'Reference accepted negative block {encoded.hex()}')
                result=[status,detail,aux,0,0,0,0,0];errors+=1
            stream.write(' '.join(map(str,request+result+[mode,len(image),len(headers)]))+'\n')
            stream.write(' '.join(f'{b:02x}'for b in encoded)+'\n')
            for n,v,kind in headers:
                stream.write(f'{len(n)} {len(v)} {kind}\n'+' '.join(f'{b:02x}'for b in n+v)+'\n')
            stream.write(' '.join(f'{b:02x}'for b in image)+'\n')
        # Every static index, all representation classes and persistent tables.
        for index in range(1,62):emit(index%3,integer(index,7,0x80))
        # Force extended integer encodings for old dynamic indices and names.
        emit(0,b''.join(literal(f'x-{i}'.encode(),b'v',1)for i in range(80)))
        emit(0,integer(141,7,0x80)+literal(b'',b'extended-index-name',1,index=141))
        for ctx in range(3):
            emit(ctx,b'')
            for kind in(1,2,3):
                emit(ctx,literal(b'x-custom',bytes(range(32)),kind,False)+literal(b':path',b'/grpc.Generate',kind,True,index=4))
            emit(ctx,literal(b'',b'',1)+literal(b'long',b'z'*8193,2,True))
            emit(ctx,integer(257,5,0x20))
            emit(ctx,literal(b'leased-name',b'a'*200,1))
            emit(ctx,literal(b'',b'b'*200,1,index=62))
            emit(ctx,integer(62,7,0x80))
            # Actual settings shrink: previous maximum can exceed new allowed.
            emit(ctx,integer(64,5,0x20),allowed=64,required=1,required_max=64)
            emit(ctx,integer(0,5,0x20)+integer(64,5,0x20)+literal(b'x',b'y',1),allowed=64,required=1,required_max=0)
        names=[b':method',b':path',b'content-type',b'te',b'grpc-encoding',b'x-request-id',b'x-binary']
        values=[b'POST',b'/service.Generate',b'application/grpc',b'trailers',b'identity',b'123',bytes(range(256))]
        for ctx in range(3):reset(ctx)
        for number in range(300):
            ctx=rng.randrange(3);encoder=encoders[ctx]
            if number%19==0:
                # Fresh contexts are explicit requests, never a DUT reset.
                reset(ctx);encoder=encoders[ctx]
            if number%11==0:encoder.header_table_size=rng.choice([0,32,64,128,capacities[ctx]])
            decoders[ctx].max_allowed_table_size=capacities[ctx]
            fields=[]
            for _ in range(rng.randrange(1,9)):
                i=rng.randrange(len(names));value=values[i]if rng.randrange(3)else bytes(rng.randrange(256)for _ in range(rng.randrange(40)))
                fields.append(NeverIndexedHeaderTuple(names[i],value)if rng.randrange(4)==0 else(names[i],value))
            encoded=encoder.encode(fields,huffman=bool(number&1))
            emit(ctx,encoded)
        # Standalone negative blocks retire their compression context.
        def negative(data,status,detail=0,aux=0,reference=True,**kwargs):
            reset(0);emit(0,data,status,detail,aux,expect_reference_error=reference,**kwargs)
        negative(b'\x80',3)
        negative(integer(62,7,0x80),3,2)
        negative(b'\xff',2,2)
        negative(b'\xff'+b'\x80'*5+b'\x82\x83',2,5)
        negative(b'\x80'+b'\xff'*10,3)
        negative(b'\x40',4,0xfe)
        negative(literal(b'x',b'y',2)+integer(0,5,0x20),9,1)
        negative(integer(4097,5,0x20),9,3)
        negative(b'\x82',10,allowed=64)
        negative(b'',10,allowed=64)
        negative(integer(128,5,0x20)+integer(64,5,0x20),9,2,reference=False,required=1,required_max=64)
        negative(b'\x00\x01x\x81\xff',4,3,2)
        negative(b'\x82\x40\x01x\x04abc',4,2)
        negative(b'\x82',5,reference=False,scratch=0)
        negative(b'\x82',11,limit=31)
        negative(b'\x82\x83',8,mode=1,reference=False)
        negative(b'\x82',1,reference=False,override={1:0x7ffff0})
        negative(literal(b'x',b'value',2),7,0,0x52,mode=3,reference=False)
        negative(literal(b'x',b'value',1),12,5,0x64,mode=4,reference=False)
        for mode,status,detail,aux in((2,6,0,0x31),(5,3,4,0x63),(6,3,6,0)):
            reset(0);emit(0,literal(b'cached',b'value',1))
            emit(0,integer(62,7,0x80),status,detail,aux,mode=mode)
        reset(0);emit(0,literal(b'recovery',b'complete',1)+integer(62,7,0x80))
    print(f'Generated {count} stateful HPACK header blocks: {successes} valid/{errors} rejected, three external connection regions')


if __name__=='__main__':main()
