"""Freeze the actual RPC/inverse/progress/envelope regression in WSL."""
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--rtl-override',type=Path,help='An isolated existing RTL file or directory of replacements');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/rpc-http2-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        sources=[p for folder in('rtl','sim','tools','scripts')for p in(root/folder).rglob('*')
            if p.is_file()and not p.is_symlink()and '__pycache__'not in p.parts and p.suffix in('.py','.v','.sv')]
        sources +=[root/'build/rpc-grpc-fixtures'/n for n in('memory.bin','model_manifest.json','rpc_cases.json','frame_cases.json')]
        sources +=[root/'build/grpc-header-fixtures/cases.json'];inputs={};overrides={}
        if args.rtl_override:
            selected=args.rtl_override.resolve();paths=sorted(selected.glob('*.v'))if selected.is_dir()else[selected]
            assert paths
            for p in paths:
                assert p.is_file()and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.v',p.name)and(root/'rtl'/p.name).is_file()
                overrides['rtl/'+p.name]=p
        for source in sources:
            n=source.relative_to(root).as_posix();p=target/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(overrides.get(n,source),p);inputs[n]=sha(p)
        site=root/'.venv312/Lib/site-packages'
        for package in('h2','hpack','hyperframe'):
            package_sources=[p for p in(site/package).rglob('*')if p.is_file()and '__pycache__'not in p.parts]
            metadata=list(site.glob(package+'-*.dist-info'));assert len(metadata)==1
            package_sources +=[p for p in metadata[0].rglob('*')if p.is_file()and p.name!='RECORD']
            for source in package_sources:
                n='native-vendor/'+source.relative_to(site).as_posix();p=target/n;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,p);inputs[n]=sha(p)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen actual gRPC RPC envelope: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_rpc_http2_tests.py'),'--execute'],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('rpc_http2_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in inputs:
            p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for n in('report.json','acceptance.json','simulation.log','build.log','results.xml','progress.json'):
            if(target/'build/test'/n).is_file():shutil.copy2(target/'build/test'/n,archive/n)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat(),
            isolated_rtl_overrides={n:str(p)for n,p in overrides.items()},
            current_primary_changed_inputs=[n for n,h in inputs.items()if not n.startswith('native-vendor/')and(not(root/n).is_file()or sha(root/n)!=h)]),indent=2)+'\n')
        print('Archived actual RPC envelope: '+str(archive),flush=True);raise SystemExit(result.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/rpc-http2-tests'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(root/n)==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));build=root/'build/test';build.mkdir(parents=True,exist_ok=True);runner=get_runner('icarus')
    report=dict(phase='building',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[root/n for n in inputs if n.startswith('rtl/')and n.endswith('.v')]+[root/'sim/cocotb_rpc_http2_top.sv'],
            hdl_toplevel='cocotb_rpc_http2_top',defines={'PARSER_PORTABLE_SIM':1},build_dir=build,always=True,log_file=build/'build.log')
        report['phase']='running'
        runner.test(hdl_toplevel='cocotb_rpc_http2_top',test_module='test_rpc_http2_return',test_dir=build,build_dir=build,
            results_xml=build/'results.xml',extra_env={'PARSER_RPC_RESPONSE_FIXTURES':str(root/'build/rpc-grpc-fixtures')},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        assert json.loads((build/'acceptance.json').read_text())['phase']=='passed'
        assert all(sha(root/n)==h for n,h in inputs.items())
        report.update(phase='passed',tests=1,failures=0,acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
