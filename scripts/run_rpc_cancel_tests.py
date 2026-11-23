"""Freeze actual RPC/inverse/fabric cancellation executions in the approved WSL root."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path, source_relative


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--directed',action='store_true')
    parser.add_argument('--execute',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/rpc-cancel-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        sources=[p for folder in('rtl','sim','tools','scripts')for p in(source_path(root, folder)).rglob('*')
            if p.is_file()and not p.is_symlink()and '__pycache__'not in p.parts and p.suffix in('.py','.v','.sv')]
        sources +=[root/'build/rpc-grpc-fixtures'/n for n in('memory.bin','model_manifest.json','rpc_cases.json','frame_cases.json')]
        inputs={}
        for p in sources:
            n=source_relative(p, root);destination=target/n;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,destination);inputs[n.as_posix()]=sha(destination)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen actual RPC cancellation test: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_rpc_cancel_tests.py'),'--execute',*(['--directed']if args.directed else[])],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items()),'Frozen input changed'
        archive=root/'build/wsl-reports'/('rpc_cancel_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in inputs:
            destination=archive/'execution-sources'/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,destination)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for n in('report.json','results.xml','acceptance.json','simulation.log','build.log','progress.json'):
            if(target/'build/test'/n).is_file():shutil.copy2(target/'build/test'/n,archive/n)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat(),
            current_primary_changed_inputs=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h]),indent=2)+'\n')
        print('Archived actual RPC cancellation test: '+str(archive),flush=True);raise SystemExit(result.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/rpc-cancel-tests'
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));inputs=json.loads((root/'inputs.json').read_text())
    assert all(sha(source_path(root, n))==h for n,h in inputs.items())
    top='cocotb_rpc_cancel_top';test='test_rpc_cancel_directed'if args.directed else'test_rpc_cancel_matrix'
    build=root/'build/test';build.mkdir(parents=True,exist_ok=True);runner=get_runner('icarus')
    record=dict(phase='building',test_module=test,input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[source_path(root, n) for n in inputs if n.startswith('rtl/')and n.endswith('.v')]+[root/'sim/cocotb_rpc_cancel_top.sv'],
            hdl_toplevel=top,defines={'PARSER_PORTABLE_SIM':1},build_dir=build,always=True,log_file=build/'build.log')
        record['phase']='running'
        runner.test(hdl_toplevel=top,test_module=test,test_dir=build,build_dir=build,results_xml=build/'results.xml',
            extra_env={'PARSER_RPC_RESPONSE_FIXTURES':str(root/'build/rpc-grpc-fixtures')},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        accepted=json.loads((build/'acceptance.json').read_text());assert accepted['phase']=='passed'
        assert all(sha(source_path(root, n))==h for n,h in inputs.items())
        record.update(phase='passed',tests=1,failures=0,acceptance_sha256=sha(build/'acceptance.json'),finished_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        record.update(phase='failed',error=str(error),finished_utc=datetime.now(timezone.utc).isoformat());raise
    finally:(build/'report.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':main()
