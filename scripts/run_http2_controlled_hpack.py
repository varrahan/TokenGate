"""Freeze the real raw/HPACK/control-fork integration and run its SV corpus."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from run_wsl_sv_tests import SUITES


SOURCES=tuple(dict.fromkeys([*SUITES['http2_hpack'][2],
    'rtl/http2_control_event_fork.v','rtl/http2_controlled_hpack_ingress.v',
    'sim/tb_http2_controlled_hpack.sv','tools/generate_controlled_hpack.py',
    'tools/generate_http2_hpack_vectors.py','tools/generate_http2_transport_vectors.py',
    'tools/generate_http2_frame_vectors.py','scripts/run_wsl_sv_tests.py',
    'scripts/run_http2_controlled_hpack.py','build/http2-controlled-hpack/vectors.txt']))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name')
    parser.add_argument('--execute',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--simulator',choices=('verilator','iverilog'),default='verilator')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser'
        assert approved.is_dir()and root!=approved
        target=approved/'build/http2-controlled-hpack-tests'/args.name
        target.mkdir(parents=True,exist_ok=False);inputs={}
        for name in SOURCES:
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/name,destination);inputs[name]=sha(destination)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen controlled-HPACK integration: '+str(target),flush=True)
        completed=subprocess.run([sys.executable,str(target/'scripts/run_http2_controlled_hpack.py'),
            '--execute','--simulator',args.simulator],check=False)
        assert all(sha(target/name)==digest for name,digest in inputs.items())
        archive=root/'build/wsl-reports'/('http2_controlled_hpack_'+args.name)
        archive.mkdir(parents=True,exist_ok=False)
        for name in SOURCES:
            destination=archive/'execution-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target/name,destination)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for name in('report.json','simulation.log','build.log'):
            if(target/'build/test'/name).is_file():shutil.copy2(target/'build/test'/name,archive/name)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=completed.returncode,
            current_primary_changed_inputs=[name for name,digest in inputs.items()if not(root/name).is_file()or sha(root/name)!=digest],
            finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived controlled-HPACK integration: '+str(archive),flush=True)
        raise SystemExit(completed.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/http2-controlled-hpack-tests'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(root/name)==digest for name,digest in inputs.items())
    build=root/'build/test';build.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'build/http2-controlled-hpack/vectors.txt',build/'vectors.txt')
    sources=[str(root/name)for name in SOURCES if name.endswith(('.v','.sv'))]
    top='tb_http2_controlled_hpack'
    if args.simulator=='verilator':
        command=['verilator','--binary','--timing','--assert','-Wno-fatal','-Werror-UNOPTFLAT',
            '--top-module',top,'-j','2','--Mdir',str(build/'verilator'),'-o',str(build/top),'-DPARSER_PORTABLE_SIM',*sources]
        execute=[str(build/top)]
    else:
        command=['iverilog','-g2012','-s',top,'-o',str(build/'sim.vvp'),'-DPARSER_PORTABLE_SIM',*sources]
        execute=['vvp',str(build/'sim.vvp')]
    record=dict(phase='building',simulator=args.simulator,input_sha256=inputs,compile_command=command,
        execute_command=execute,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        with(build/'build.log').open('w')as output:result=subprocess.run(command,cwd=build,stdout=output,stderr=subprocess.STDOUT)
        assert result.returncode==0,'Build failed: '+(build/'build.log').read_text()[-4000:]
        record['phase']='running';(build/'report.json').write_text(json.dumps(record,indent=2)+'\n')
        with(build/'simulation.log').open('w')as output:result=subprocess.run(execute,cwd=build,stdout=output,stderr=subprocess.STDOUT)
        log=(build/'simulation.log').read_text()
        assert result.returncode==0 and 'PASS: raw 512-bit HTTP/2' in log,log[-4000:]
        match=re.search(r'CONTROL_FORK: (\d+) exact-metadata actions/(\d+) stall cycles/(\d+) SETTINGS ACK/(\d+) PING ACK/(\d+) raw DATA begins',log)
        assert match and all(int(x)>0 for x in match.groups())
        assert all(sha(root/name)==digest for name,digest in inputs.items())
        assert sha(build/'vectors.txt')==inputs['build/http2-controlled-hpack/vectors.txt']
        record.update(phase='passed',flow_actions=int(match[1]),flow_stall_cycles=int(match[2]),settings_ack=int(match[3]),
            ping_ack=int(match[4]),data_frame_begins=int(match[5]),simulation_log_sha256=sha(build/'simulation.log'),
            credit_ledger_verified=False,full_system_complete=False,finished_utc=datetime.now(timezone.utc).isoformat())
        print(log[-3000:])
    except BaseException as error:
        record.update(phase='failed',error=str(error),finished_utc=datetime.now(timezone.utc).isoformat());raise
    finally:
        (build/'report.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    main()
