"""Hash an implementation's frozen source snapshot, independently of live edits."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);parser.add_argument("--tool-version",required=True)
    args=parser.parse_args();files={}
    for path in sorted(args.root.rglob("*")):
        if path.is_file():files[path.relative_to(args.root).as_posix()]={"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    if not files:raise ValueError("No frozen implementation sources")
    args.output.write_text(json.dumps({"tool_version":args.tool_version,"source_root":str(args.root.resolve()),"files":files},indent=2)+"\n")


if __name__=="__main__":main()
