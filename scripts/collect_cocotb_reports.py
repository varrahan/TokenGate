"""Archive the WSL cocotb result and verify it against the primary sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser();parser.add_argument('suite',choices=('mmio','mmio_system','http2_prefill','generated_response','rpc_response','bidirectional','two_fpga'))
    args=parser.parse_args();primary=Path(__file__).resolve().parents[1]
    wsl=Path.home()/'development/hardware/parser';source=wsl/'build'/('cocotb-'+args.suite)
    report=json.loads((source/'report.json').read_text())
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    for name,digest in {**report['source_sha256'],**report.get('fixture_sha256',{})}.items():
        assert sha(wsl/name)==digest,('WSL input changed',name)
        assert sha(primary/name)==digest,('Primary input changed',name)
    target=primary/'build/wsl-reports'/('cocotb_'+args.suite);target.mkdir(parents=True,exist_ok=True)
    for name in('build.log','simulation.log','report.json','results.xml','acceptance.json','progress.json'):
        if(source/name).is_file():shutil.copy2(source/name,target/name)
    print(f"Archived cocotb {args.suite}: {report['phase']} in {target}")


if __name__=='__main__':main()
