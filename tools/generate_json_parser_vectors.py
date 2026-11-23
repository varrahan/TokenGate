"""Independent strict UTF-8 JSON/schema reference vectors for the RTL parser."""
import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ObjectPairs:
    pairs:list


SCHEMAS={0:{"prompt","text"},1:{"content","x"*32}}


def reference(raw,profile,max_depth=8):
    def reject_constant(value):raise ValueError(value)
    value=json.loads(raw.decode("utf-8"),object_pairs_hook=ObjectPairs,parse_constant=reject_constant)
    result=bytearray()
    def visit(item,depth):
        if isinstance(item,ObjectPairs):
            if depth>=max_depth:raise ValueError("nesting capacity")
            for key,value in item.pairs:
                key.encode("utf-8",errors="strict")
                if key in SCHEMAS[profile]:
                    if not isinstance(value,str):raise ValueError("selected field must be a string")
                    result.extend(value.encode("utf-8",errors="strict"))
                visit(value,depth+1)
        elif isinstance(item,list):
            if depth>=max_depth:raise ValueError("nesting capacity")
            for element in item:visit(element,depth+1)
        elif isinstance(item,str):item.encode("utf-8",errors="strict")
    visit(value,0)
    return bytes(result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    rng=random.Random(20261104)
    vectors=[]
    def add(raw,profile=0):
        if isinstance(raw,str):raw=raw.encode("utf-8")
        try:text=reference(raw,profile);bad=0
        except (ValueError,UnicodeError,RecursionError):text=b"";bad=1
        vectors.append((profile,raw,text,bad))
    valid=[{},[],True,False,None,0,-1,1.23e-17,"root string",{"prompt":"hello"},
           {"text":"café 中文 🙂 العربية"},{"ignored":{"prompt":"nested"},"text":" tail"},
           {"prompt":"", "prefixPrompt":"no", "promptExtra":"no", "text":"yes"},
           {"ignored":[True,False,None,-2.5e+3,[],{}, {"text":"inside array"}]},
           {"prompt":"".join(chr(i)for i in range(128))},
           {"p"*40:"unknown long key","text":"ok"}]
    for value in valid:
        for ensure_ascii in [False,True]:add(json.dumps(value,ensure_ascii=ensure_ascii,separators=(',',':')))
    for cp in [0,0x7f,0x80,0x7ff,0x800,0xd7ff,0xe000,0xffff,0x10000,0x10ffff]:
        for ensure_ascii in [False,True]:add(json.dumps({"prompt":chr(cp)},ensure_ascii=ensure_ascii))
    add(br'{"pr\u006fmpt":"escaped key","text":"a\"b\\c\/d\b\f\n\r\t"}')
    add(br'{"prompt":"first","prompt":"second"}')
    add("["*8+"]"*8)
    bad=["", " ","{", "[",'"unclosed',"[1,]",'{"x":1,}',"{x:1}",
         '{"x" 1}','{"x":}','{"x":true false}',"[1 2]","{}{}","[] trailing",
         "00","01","-","-.1","1.","1e","1e+","+1","1e2.3","NaN","Infinity",
         "truefalse","True","nul","[}","{]",'{"prompt":1}','{"text":null}',
         '{"prompt":{}}','{"text":[]}',"["*9+"]"*9,
         r'{"prompt":"\uD800"}',r'{"prompt":"\uDC00"}',r'{"prompt":"\uD800\u0041"}',
         r'{"ignored":"\uDC00"}',r'{"prompt":"\q"}',r'{"prompt":"\u12g4"}',
         '{"prompt":"raw\nnewline"}']
    for raw in bad:add(raw)
    for malformed in [b'\xc0\xaf',b'\xc1\xbf',b'\xe0\x80\x80',b'\xed\xa0\x80',b'\xed\xbf\xbf',
                      b'\xf0\x80\x80\x80',b'\xf4\x90\x80\x80',b'\xf5\x80\x80\x80',b'\x80',b'\xff',b'\xc2']:
        add(b'{"prompt":"'+malformed+b'"}')
    for fragment in [b'{"prompt":"\\',b'{"prompt":"\\u1',b'{"prompt":"\\u12',b'{"prompt":"\\u123',
                     b'{"prompt":"\\uD800\\',b'{"prompt":"\\uD800\\uDC0']:
        add(fragment)
    alphabet="abcXYZ012 \t\n\\\"é中🙂\u0301"
    def text():return "".join(rng.choice(alphabet)for _ in range(rng.randrange(0,35)))
    def value(depth=0):
        if depth>2:return rng.choice([None,True,False,rng.randrange(-1000,1000),text()])
        kind=rng.randrange(6)
        if kind==0:return [value(depth+1)for _ in range(rng.randrange(0,4))]
        if kind<4:
            return {key:(text()if key in SCHEMAS[0] else value(depth+1))for key in rng.sample(["prompt","text","ignored","array","nested"],rng.randrange(1,5))}
        return rng.choice([None,True,False,rng.randrange(-1000,1000),text()])
    for _ in range(120):add(json.dumps(value(),ensure_ascii=bool(rng.randrange(2)),indent=(2 if rng.randrange(4)==0 else None)))
    # Reloaded schema must replace, rather than supplement, the default keys.
    for payload in [{"content":"new schema","prompt":"not selected","text":"not selected"},
                    {"x"*32:"exact length", "x"*33:"not a prefix match"},
                    {"nested":[{"content":"one"},{"content":"two"}]},
                    {"content":False},{"text":"old schema ignored"}]:
        add(json.dumps(payload,ensure_ascii=False),1)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",encoding="ascii")as stream:
        for profile,raw,text,bad in vectors:
            stream.write(f"{profile} {len(raw)} {len(text)} {bad}\n")
            stream.write(" ".join(map(str,raw))+"\n")
            stream.write(" ".join(map(str,text))+"\n")
    print(f"Generated {len(vectors)} JSON grammar/Unicode/schema packets ({sum(v[3]for v in vectors)} invalid)")


if __name__=="__main__":main()
