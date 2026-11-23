"""Independent Python JSON reference bytes for the RTL escape encoder."""
import argparse
import json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--output",type=Path,required=True)
args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
texts=["", "".join(chr(i) for i in range(128)), "UTF-8 café 中文 🙂 العربية", 'quote " slash / backslash \\ tab\t newline\n', "x"*128]
with args.output.open("w",encoding="ascii") as stream:
    for text in texts:
        raw=text.encode("utf-8")
        escaped=json.dumps(text,ensure_ascii=False)[1:-1].encode("utf-8")
        stream.write(f"{len(raw)} {len(escaped)}\n")
        stream.write(" ".join(str(b) for b in raw)+"\n")
        stream.write(" ".join(str(b) for b in escaped)+"\n")
