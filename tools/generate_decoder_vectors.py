"""Combine JSON and Protobuf references for the transactional AXI decoder."""
import argparse
import subprocess
import sys
from pathlib import Path


def load(path,width):
    numbers=iter(map(int,path.read_text(encoding="ascii").split()))
    result=[]
    while True:
        try:first=next(numbers)
        except StopIteration:break
        header=[first]+[next(numbers)for _ in range(width-1)]
        nraw,ntext=header[1:3]if width==4 else header[:2]
        raw=bytes(next(numbers)for _ in range(nraw))
        text=bytes(next(numbers)for _ in range(ntext))
        result.append((header,raw,text))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    directory=args.output.parent
    directory.mkdir(parents=True,exist_ok=True)
    here=Path(__file__).resolve().parent
    json_path=directory/"json-source.txt"
    proto_path=directory/"proto-source.txt"
    subprocess.run([sys.executable,str(here/"generate_json_parser_vectors.py"),"--output",str(json_path)],check=True)
    subprocess.run([sys.executable,str(here/"generate_protobuf_vectors.py"),"--output",str(proto_path)],check=True)
    json_vectors=load(json_path,4)
    proto_vectors=load(proto_path,3)
    records=[]
    for i,(header,raw,text)in enumerate(json_vectors):
        profile,_,_,bad=header
        code=255 if bad else 128 if len(text)>128 else 0
        records.append((0,profile,raw,text if code==0 else b"",code))
        if i<len(proto_vectors):
            pheader,praw,ptext=proto_vectors[i]
            pcode=(0x40|pheader[2])if pheader[2] else 128 if len(ptext)>128 else 0
            records.append((1,0,praw,ptext if pcode==0 else b"",pcode))
    with args.output.open("w",encoding="ascii")as stream:
        stream.write(f"{len(records)}\n")
        for mode,profile,raw,text,code in records:
            stream.write(f"{mode} {profile} {len(raw)} {len(text)} {code}\n")
            stream.write(" ".join(map(str,raw))+"\n")
            stream.write(" ".join(map(str,text))+"\n")
    print(f"Generated {len(records)} mixed-format queued AXI packets")


if __name__=="__main__":main()
