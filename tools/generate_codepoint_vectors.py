"""Independent strict Python UTF-8 decoder cases for the RTL scalar reader."""
import argparse
import codecs
import random
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261104)
    texts=["", "ASCII\x00\n\r\t", "café 中🙂", "a\u0301", "\u007f\u0080\u07ff\u0800\ud7ff\ue000\uffff\U00010000\U0010ffff"]
    for _ in range(128):
        cps=[rng.randrange(0x110000)for _ in range(rng.randrange(1,64))]
        texts.append("".join(chr(cp)for cp in cps if not 0xd800<=cp<=0xdfff))
    cases=[text.encode()for text in texts]+[bytes([i])for i in range(256)]
    cases += [b"\xc0\x80",b"\xc1\xbf",b"\xe0\x80\x80",b"\xed\xa0\x80",b"\xf0\x80\x80\x80",b"\xf4\x90\x80\x80",b"\xf5\x80\x80\x80",b"\xffok"]
    for text in ("é","中","🙂"):
        raw=text.encode();cases += [b"prefix"+raw[:n]for n in range(1,len(raw))]
    cases += [rng.randbytes(rng.randrange(1,25))for _ in range(1000)]
    records=invalid=0
    with args.output.open("w",encoding="ascii")as stream:
        for raw in cases:
            for marker in (0,1):
                decoder=codecs.getincrementaldecoder("utf-8")("strict");scalars=[];pending=bytearray();error=0
                for b in raw:
                    pending.append(b)
                    try:decoded=decoder.decode(bytes([b]))
                    except UnicodeDecodeError:error=1;break
                    if decoded:
                        assert len(decoded)==1
                        scalars.append((ord(decoded),len(pending),int.from_bytes(pending,"little")))
                        pending.clear()
                if not error:
                    try:decoder.decode(b"",final=True)
                    except UnicodeDecodeError:error=2
                # A scalar ending on TLAST is terminal. Explicit EOF uses a
                # separate zero-keep record, including for empty packets.
                stream.write(f"{len(raw)} {len(scalars)} {error} {marker} {records+1}\n")
                stream.write(" ".join(map(str,raw))+"\n")
                for i,(cp,length,data)in enumerate(scalars):
                    last=int(not error and not marker and i+1==len(scalars))
                    stream.write(f"{cp} {length} {data:x} {last}\n")
                records+=1;invalid+=int(error!=0)
    print(f"Generated {records} UTF-8 packets, {invalid} malformed/truncated")


if __name__=="__main__":main()
