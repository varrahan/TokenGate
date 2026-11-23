"""Protobuf wire fixtures, selecting top-level length-delimited fields 1/17."""
import argparse
from pathlib import Path
from generate_serializer_vectors import varint


def field(number,wire,payload):return bytes(varint(number<<3|wire))+payload
def string(number,data):return field(number,2,bytes(varint(len(data)))+data)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    unicode="café 中文 🙂 العربية".encode()
    vectors=[
        (b"",b"",0), (string(1,b"hello"),b"hello",0),
        (field(3,0,bytes(varint((1<<64)-1)))+string(17,unicode),unicode,0),
        (field(3,1,b"abcdefgh")+field(4,5,b"ABCD")+string(1,b"tail"),b"tail",0),
        (string(9,b"\x00\xff\x80")+string(1,b"")+string(17,b"ok"),b"ok",0),
        (field(4,3,string(1,b"hidden"))+field(4,4,b"")+string(1,b"visible"),b"visible",0),
        (string(1,b"a")+string(17,b"b")+string(1,b"c"),b"abc",0),
        (string((1<<29)-1,b"maximum field ID"),b"",0),
        (string(1,b"x"*256),b"x"*256,0),
        (b"\x00",b"",3),(b"\x0e",b"",3),(b"\x0f",b"",3),
        (b"\x80",b"",1),(b"\xff"*9+b"\x02",b"",2),
        (field(1,0,b"\xff"*9+b"\x02"),b"",2),
        (b"\x08",b"",1),(b"\x0a",b"",1),(b"\x0a\x05abc",b"",1),
        (field(2,1,b"short"),b"",1),(field(2,5,b"abc"),b"",1),
        (field(1,2,bytes(varint(257)))+b"x"*257,b"",4),
        (field(4,3,b"")+field(5,4,b""),b"",5),
        (field(4,4,b""),b"",5),(field(4,3,b""),b"",5),
        (field(1,3,b"")*5,b"",6),
        (field(1<<29,2,b"\x00"),b"",3),
    ]
    for invalid_utf8 in [b'\xc0\xaf',b'\xe0\x80\x80',b'\xed\xa0\x80',b'\xf4\x90\x80\x80',b'\x80',b'\xff',b'\xc2']:
        vectors.append((string(1,invalid_utf8),b"",7))
    vectors.append((string(1,b'\xc2')+string(1,b'\xa0'),b"",7))
    text="\x00\x7f\u0080\u07ff\u0800\ud7ff\ue000\uffff\U00010000\U0010ffff".encode()
    vectors.append((string(1,text),text,0))
    with args.output.open("w",encoding="ascii")as stream:
        for raw,text,error in vectors:
            stream.write(f"{len(raw)} {len(text)} {error}\n")
            stream.write(" ".join(map(str,raw))+"\n")
            stream.write(" ".join(map(str,text))+"\n")
    print(f"Generated {len(vectors)} Protobuf wire reference packets")


if __name__=="__main__":main()
