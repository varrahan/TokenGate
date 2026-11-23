"""Headroom-guarded native implementation of the exact simulated Tokenizer top."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--simulation',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    import re
    assert all(re.fullmatch(r'[A-Za-z0-9_-]+',v)for v in(args.name,args.simulation))
    tested=root/'build/validation'/args.simulation
    simulation=json.loads((tested/'report.json').read_text());assert simulation['phase']in('running','actual_tokenizer_hyperram_two_complete_images_passed','prepared_native_candidate')
    for name,digest in simulation['inputs_sha256'].items():assert sha(tested/'sources'/name)==digest,name
    report_path=root/'build/validation'/(args.name+'-launch.json');assert not report_path.exists()
    free=shutil.disk_usage(root).free;assert free>=3*1024**3,'Need 3 GiB for this isolated combined build'
    subprocess.run([sys.executable,str(root/'tools/generate_tokenizer_hyperram_timing_harness.py'),'--simulation',args.simulation],check=True,capture_output=True)
    command=['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace',
        '-source',str(root/'scripts/implement_tokenizer_hyperram.tcl'),'-log',str(root/'build'/(args.name+'.log')),
        '-journal',str(root/'build'/(args.name+'.jou')),'-tclargs',args.name,args.simulation]
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),command=command,simulation=args.simulation,
        input_sha256=simulation['inputs_sha256'],free_bytes_before=free,driver_sha256=sha(Path(__file__)),
        functional_completion_pending=simulation['phase']!='actual_tokenizer_hyperram_two_complete_images_passed',package_timing_verified=False,full_system_complete=False)
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    with(root/'build'/(args.name+'-stdout.log')).open('w')as log:
        process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
        report['launcher_pid']=process.pid;report_path.write_text(json.dumps(report,indent=2)+'\n');code=process.wait()
    report.update(phase='native_process_completed'if code==0 else'stopped_with_error',exit_code=code,
        finished_utc=datetime.now(timezone.utc).isoformat(),free_bytes_after=shutil.disk_usage(root).free)
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(phase=report['phase'],exit_code=code)))
    raise SystemExit(code)


if __name__=='__main__':main()
