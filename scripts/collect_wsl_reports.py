"""Archive WSL test logs/provenance in the primary Windows workspace."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from run_wsl_sv_tests import SUITES


def main():
    parser=argparse.ArgumentParser();parser.add_argument("suite",nargs="+",choices=SUITES)
    args=parser.parse_args();primary=Path(__file__).resolve().parents[1];wsl=Path.home()/"development/hardware/parser"
    for suite in args.suite:
        build_name,_,sources=SUITES[suite];source=wsl/"build"/build_name;target=primary/"build/wsl-reports"/suite
        target.mkdir(parents=True,exist_ok=True)
        for simulator in("verilator","iverilog"):
            for suffix in("build.log","simulation.log","report.json"):
                prefix=simulator+("-subsystem"if suite=="tokenizer_subsystem"else"")
                path=source/(prefix+"-"+suffix)
                if path.exists():shutil.copy2(path,target/path.name)
        provenance={"wsl_workspace":str(wsl),"source_sha256_at_archive":{name:hashlib.sha256((wsl/name).read_bytes()).hexdigest()for name in sources}}
        (target/"archive-provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
        print(f"Archived {suite} reports in {target}")


if __name__=="__main__":main()
