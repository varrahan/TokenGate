"""Copy this project into the user-selected WSL workspace without clobbering edits.

Run with WSL Python against the mounted Windows source file. Only source/data
files are copied; Windows generated executables and signing controls are not.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--fixture",action="append",default=[])
    args=parser.parse_args();source=Path(__file__).resolve().parents[1]
    target=Path.home()/"development/hardware/parser"
    target.mkdir(parents=True,exist_ok=True)
    if target.resolve()!=target:raise ValueError("WSL target must not redirect through a symlink")
    manifest_file=target/".codex-parser-sync.json"
    old=json.loads(manifest_file.read_text())if manifest_file.exists()else{}
    files=[]
    for name in ("rtl","sim","tools","tests","scripts","constraints","docs"):
        files.extend(p for p in(source/name).rglob("*")if p.is_file()and not p.is_symlink()and "__pycache__"not in p.parts)
    for name in ("README.md","requirements-test.txt","create_parser.tcl",".gitignore"):
        if(source/name).exists():files.append(source/name)
    for fixture in args.fixture:
        if not re.fullmatch(r"[a-z0-9_-]+",fixture):raise ValueError("Invalid fixture name")
        files.extend(p for p in(source/"build"/fixture).iterdir()if p.is_file()and p.suffix in(".txt",".mem",".bin",".json"))
    plan=[];retired={};updated=dict(old)
    for path in files:
        relative=path.relative_to(source);key=relative.as_posix();destination=target/relative
        if not destination.resolve().is_relative_to(target):raise ValueError(f"Path leaves WSL workspace: {key}")
        source_hash=digest(path)
        if destination.exists():
            destination_hash=digest(destination)
            if destination_hash!=source_hash and destination_hash!=old.get(key):raise ValueError(f"Preserving modified WSL file: {key}")
        else:destination_hash=None
        if destination_hash!=source_hash:plan.append((path,destination))
        updated[key]=source_hash
        if len(relative.parts)>2 and relative.parts[0]=='rtl':
            flat_key='rtl/'+path.name;previous=target/flat_key
            if flat_key in old and not(source/flat_key).exists():
                if previous.exists():
                    if not previous.resolve().is_relative_to(target) or digest(previous)!=old[flat_key]:
                        raise ValueError(f"Preserving modified WSL file: {flat_key}")
                    retired[previous]=old[flat_key]
                updated.pop(flat_key,None)
    for path,destination in plan:
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
    for previous,expected in retired.items():
        if digest(previous)!=expected:raise ValueError(f"Preserving modified WSL file: {previous.relative_to(target)}")
        previous.unlink()
    manifest_file.write_text(json.dumps(updated,indent=2)+"\n")
    print(json.dumps({"source":str(source),"target":str(target),"copied":len(plan),"relocated":len(retired),"tracked":len(updated)},indent=2))


if __name__=="__main__":main()
