"""Run the frozen native full-image integration test using normal XSim options."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',required=True)
    parser.add_argument('--attempt',default='quoted_plusarg');parser.add_argument('--startup-diagnostic',action='store_true');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.evidence)
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.attempt)
    root=Path(__file__).resolve().parents[1];folder=root/'build/validation'/args.evidence
    syntax=json.loads((folder/'report.json').read_text())
    elaboration=json.loads((folder/'elaboration-report.json').read_text());assert elaboration['elaboration_verified']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,digest in syntax['inputs_sha256'].items():assert sha(folder/'sources'/name)==digest
    output=folder/('simulation-'+args.attempt+'-report.json');assert not output.exists(),'Preserve existing simulation evidence'
    digest='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    image=root/'build/frozen-hyperram-images'/digest/'external_memory.bin';assert sha(image)==digest
    local=folder/'image.bin'
    if local.exists():assert os.path.samefile(image,local)and sha(local)==digest
    else:os.link(image,local)
    shutil.copy2(Path(__file__),folder/('run_async_hyperram_windows-'+args.attempt+'.py'))
    command=['C:/AMDDesignTools/2025.2/Vivado/bin/xsim.bat','async_hyperram','--runall',
        '--onerror','quit','--onfinish','quit','--maxlogsize','32','--log','xsim-'+args.attempt+'.log','--testplusarg','IMAGE=image.bin']
    # cmd.exe treats an unquoted '=' as a batch-argument separator. Preserve
    # quotes around this fixed plusarg rather than passing list2cmdline output.
    windows_command_line='"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" async_hyperram --runall --onerror quit --onfinish quit --maxlogsize 32 --log xsim-'+args.attempt+'.log --testplusarg "IMAGE=image.bin"'
    if args.startup_diagnostic:
        command+=['--testplusarg','STARTUP_DIAGNOSTIC']
        windows_command_line+=' --testplusarg STARTUP_DIAGNOSTIC'
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),command=command,
        image_sha256=digest,input_sha256=syntax['inputs_sha256'],driver_sha256=sha(Path(__file__)),
        vendor_source_models=syntax.get('vendor_source_models',False),vendor_sva_enabled=syntax.get('vendor_sva_enabled',True),
        independent_testbench_assertions_enabled=True,
        runtime_options_changed_for_security=False,simulation_passed=False,full_system_complete=False)
    report['windows_command_line']=windows_command_line
    with(folder/('simulator-output-'+args.attempt+'.log')).open('w')as log:
        process=subprocess.Popen(windows_command_line,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
        report['launcher_pid']=process.pid;output.write_text(json.dumps(report,indent=2)+'\n')
        while True:
            try:code=process.wait(timeout=1);break
            except subprocess.TimeoutExpired:
                if log.tell()>64*1024*1024 or (folder/('simulator-output-'+args.attempt+'.log')).stat().st_size>64*1024*1024:
                    subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/taskkill.exe'),'/PID',str(process.pid),'/T','/F'],
                        check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    code=process.wait();report['owned_test_stopped_for_log_limit']=True;break
    text=(folder/('simulator-output-'+args.attempt+'.log')).read_text(errors='replace')
    report.update(exit_code=code,phase='native_simulation_failed',finished_utc=datetime.now(timezone.utc).isoformat())
    line=next((line for line in text.splitlines()if line.startswith('ASYNC_HYPERRAM_PASS ')),None)
    if code==0 and line:
        values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line)}
        assert values['image_bytes']==8388608 and values['full_writes']==values['full_reads']==131072
        assert values['reset_epochs']==2 and values['timeout_status']==2 and values['partial_write_words']==4
        report.update(phase='native_full_image_async_memory_passed',simulation_passed=True,acceptance=values)
    if args.startup_diagnostic and code==0 and 'ASYNC_STARTUP_DIAGNOSTIC_PASS'in text:
        report.update(phase='native_startup_diagnostic_passed',startup_diagnostic_passed=True)
    assert sha(local)==digest
    report['snapshot_files_sha256']={p.relative_to(folder).as_posix():sha(p)for p in(folder/'xsim.dir/async_hyperram').rglob('*')if p.is_file()}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],exit_code=code,acceptance=report.get('acceptance'))))
    raise SystemExit(0 if report['simulation_passed']or report.get('startup_diagnostic_passed')else code or 1)


if __name__=='__main__':main()
