"""Byte-exact Python JSON/SSE/Protobuf serializer reference vectors."""
import argparse
import json
from pathlib import Path


def varint(value):
    result=bytearray()
    while value>=128:
        result.append((value&127)|128)
        value>>=7
    result.append(value)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    texts=["",'Hello "world" \\ newline\n tab\t',"café 中文 🙂 العربية", "".join(chr(i)for i in range(128))]
    vectors=[]
    for mode in range(3):
        for i,text in enumerate(texts):
            raw=text.encode()
            field=[1,17,16384,(1<<29)-1][i]
            json_body=json.dumps({"choices":[{"delta":{"content":text}}]},ensure_ascii=False,separators=(',',':')).encode()
            if mode==0:expected=json_body
            elif mode==1:expected=b"data: "+json_body+b"\n\n"
            else:expected=varint((field<<3)|2)+varint(len(raw))+raw
            vectors.append((mode,field,raw,expected,0))
    for n in [1,15,16,17,32,64,128,255,256]:
        raw=b"x"*n
        vectors.append((2,1,raw,varint(10)+varint(n)+raw,0))
    vectors.extend([(0,1,b"x"*257,b"",1),(3,1,b"invalid format",b"",2),(2,0,b"invalid field",b"",2)])
    vectors.extend([(1,1,b'context '*5,b'',3),(0,1,b'cancelled partial response',b'',4),(2,1,b'',b'',4)])
    with args.output.open("w",encoding="ascii") as stream:
        for mode,field,raw,expected,error in vectors:
            stream.write(f"{mode} {field} {len(raw)} {len(expected)} {error}\n")
            stream.write(" ".join(map(str,raw))+"\n")
            stream.write(" ".join(map(str,expected))+"\n")
    print(f"Generated {len(vectors)} serializer reference packets")


if __name__=="__main__":main()
