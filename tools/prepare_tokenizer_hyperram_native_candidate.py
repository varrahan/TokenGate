"""Freeze a timing candidate honestly, without inventing a simulation result."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    subprocess.run([sys.executable,str(root/'tools/generate_tokenizer_hyperram_experiment.py')],check=True,capture_output=True)
    experiment=root/'build/experiments/tokenizer-hyperram';generation=json.loads((experiment/'generation.json').read_text())
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    inputs={}
    for name,digest in generation['outputs_sha256'].items():
        source=experiment/name;assert sha(source)==digest
        target=folder/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());inputs[name]=sha(target)
    (folder/'generation.json').write_bytes((experiment/'generation.json').read_bytes())
    (folder/'integration-generator-used.py').write_bytes((root/'tools/generate_tokenizer_hyperram_experiment.py').read_bytes())
    report=dict(phase='prepared_native_candidate',prepared_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        generation_sha256=sha(folder/'generation.json'),driver_sha256=sha(Path(__file__)),
        simulation_executed=False,functional_verification_complete=False,full_system_complete=False)
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],rtl_files=len(inputs),candidate=args.name)))


if __name__=='__main__':main()
