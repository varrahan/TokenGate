"""Freeze and execute native-reference response header tests in WSL."""
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
from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--rtl-override',type=Path,help='Isolated replacement grpc_response_headers.v; production RTL stays unchanged');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/grpc-header-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        names=('rtl/grpc_response_headers.v','rtl/axis_cancellable_frame_arbiter.v','sim/cocotb_grpc_headers_top.sv',
            'sim/cocotb/test_grpc_response_headers.py','tools/generate_grpc_header_vectors.py',
            'scripts/run_grpc_header_tests.py','build/grpc-header-fixtures/cases.json', 'tools/rtl_paths.py')
        inputs={}
        for n in names:
            source=source_path(root, n)
            if n=='rtl/grpc_response_headers.v'and args.rtl_override:
                source=args.rtl_override.resolve();assert source.is_file()and source.name=='grpc_response_headers.v'
            p=target/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,p);inputs[n]=sha(p)
        # Freeze the actual pure-Python native oracle dependencies. WSL's
        # simulator venv need not share the Windows reference venv's packages,
        # and the execution must not import mutable primary-site packages.
        site=root/'.venv312/Lib/site-packages'
        for package in('h2','hpack','hyperframe'):
            sources=[p for p in(site/package).rglob('*')if p.is_file()and '__pycache__'not in p.parts]
            metadata=list(site.glob(package+'-*.dist-info'));assert len(metadata)==1
            sources +=[p for p in metadata[0].rglob('*')if p.is_file()and p.name!='RECORD']
            for source in sources:
                n='native-vendor/'+source.relative_to(site).as_posix();p=target/n;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,p);inputs[n]=sha(p)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen gRPC response headers: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_grpc_header_tests.py'),'--execute'],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('grpc_headers_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in inputs:
            p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for n in('report.json','acceptance.json','simulation.log','build.log','results.xml'):
            if(target/'build/test'/n).is_file():shutil.copy2(target/'build/test'/n,archive/n)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,
            isolated_rtl_override=str(args.rtl_override.resolve())if args.rtl_override else None,
            finished_utc=datetime.now(timezone.utc).isoformat(),current_primary_changed_inputs=[n for n,h in inputs.items()if not n.startswith('native-vendor/')and(not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h)]),indent=2)+'\n')
        print('Archived response headers: '+str(archive),flush=True);raise SystemExit(result.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/grpc-header-tests'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(source_path(root, n))==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));build=root/'build/test';build.mkdir(parents=True,exist_ok=True)
    runner=get_runner('icarus');report=dict(phase='building',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[source_path(root, n) for n in inputs if n.endswith(('.v','.sv'))],hdl_toplevel='cocotb_grpc_headers_top',
            build_dir=build,always=True,log_file=build/'build.log')
        report['phase']='running'
        runner.test(hdl_toplevel='cocotb_grpc_headers_top',test_module='test_grpc_response_headers',test_dir=build,build_dir=build,
            results_xml=build/'results.xml',extra_env={'PARSER_GRPC_HEADER_FIXTURES':str(root/'build/grpc-header-fixtures')},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        assert json.loads((build/'acceptance.json').read_text())['phase']=='passed'
        assert all(sha(source_path(root, n))==h for n,h in inputs.items())
        report.update(phase='passed',tests=1,failures=0,acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
