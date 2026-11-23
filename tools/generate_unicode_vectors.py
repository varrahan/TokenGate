"""Runtime Unicode-class BRAM contents and independent scalar test queries."""
import argparse
import random
from pathlib import Path
import regex
from unicode_profiles import unicode_classes,export_unicode_image


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    export_unicode_image(args.output)
    data=(args.output/"unicode_classes.bin").read_bytes()
    (args.output/"unicode_classes.mem").write_text("".join(f"{b:02x}\n"for b in data),encoding="ascii")
    classes=unicode_classes()
    points=set(range(256))|{0xd7ff,0xd800,0xdfff,0xe000,0x10ffff,0x110000,0x1fffff}
    for cp in range(1,len(classes)):
        if classes[cp]!=classes[cp-1]:points.update((cp-1,cp,min(cp+1,0x10ffff)))
    rng=random.Random(20261104)
    points.update(rng.randrange(0x110000)for _ in range(1000))
    expected={}
    patterns=[(regex.compile(r"\p{L}"),1),(regex.compile(r"\p{N}"),2),(regex.compile(r"\s"),3)]
    for cp in sorted(points):
        invalid=cp>0x10ffff or 0xd800<=cp<=0xdfff
        value=0
        if not invalid:
            for pattern,classification in patterns:
                if pattern.fullmatch(chr(cp)):value=classification;break
        expected[cp]=(value,int(invalid))
    with(args.output/"unicode_queries.txt").open("w",encoding="ascii")as stream:
        stream.write(f"{len(expected)}\n")
        for cp,(value,error)in expected.items():stream.write(f"{cp} {value} {error}\n")
    print(f"Generated full Unicode class image and {len(expected)} boundary/random queries")


if __name__=="__main__":main()
