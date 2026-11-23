"""Freeze the real bidirectional raw Parser/Tokenizer/native-client regression."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def freeze_model_image(source,destination,approved):
    """Share verified, read-only fixture bytes on one build filesystem."""
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    approved=approved.resolve();cache=approved/'build/frozen-model-inputs'/digest/'memory.mem'
    assert cache.parent.resolve().is_relative_to(approved)
    cache.parent.mkdir(parents=True,exist_ok=True)
    if not cache.exists():
        descriptor,name=tempfile.mkstemp(prefix='model-',dir=cache.parent);os.close(descriptor)
        staging=Path(name)
        try:
            shutil.copyfile(source,staging)
            assert hashlib.sha256(staging.read_bytes()).hexdigest()==digest
            staging.chmod(0o444)
            try:os.link(staging,cache)
            except FileExistsError:pass
        finally:staging.unlink()
    assert not cache.is_symlink() and cache.is_file() and not(cache.stat().st_mode&0o222)
    assert hashlib.sha256(cache.read_bytes()).hexdigest()==digest
    assert not destination.exists()
    os.link(cache,destination)
    assert destination.stat().st_ino==cache.stat().st_ino
    assert hashlib.sha256(destination.read_bytes()).hexdigest()==digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--rtl-override',type=Path,help='An isolated existing RTL file or directory of replacements')
    parser.add_argument('--harness-override',type=Path,help='A passive replacement of the existing two-FPGA fixture')
    parser.add_argument('--test-override',type=Path,help='A replacement of an existing cocotb profile in the frozen snapshot')
    parser.add_argument('--profile',choices=('native','shutdown-faults','return-faults','workload','duplex','duplex-faults','receive-flow','receive-errors'),default='native');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        if shutil.disk_usage(root).free<512*1024*1024:
            print('Less than 512 MiB free on the workspace drive; preserve disk headroom before freezing another full-model run',file=sys.stderr,flush=True)
            raise SystemExit(75)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/raw-envelope-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        sources=[p for folder in('rtl','sim','tools','scripts')for p in(root/folder).rglob('*')
            if p.is_file()and not p.is_symlink()and '__pycache__'not in p.parts and p.suffix in('.py','.v','.sv')]
        sources +=[p for p in(root/'build/bidirectional-fixtures').iterdir()if p.is_file()]
        sources +=[root/'build/bidirectional-reference-validation.json'];inputs={};overrides={}
        if args.rtl_override:
            selected=args.rtl_override.resolve();paths=sorted(selected.glob('*.v'))if selected.is_dir()else[selected]
            assert paths
            for p in paths:
                assert p.is_file()and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.v',p.name)and(root/'rtl'/p.name).is_file()
                overrides['rtl/'+p.name]=p
        if args.harness_override:
            selected=args.harness_override.resolve()
            assert selected.is_file() and selected.name=='cocotb_two_fpga_enveloped_top.sv'
            overrides['sim/'+selected.name]=selected
        if args.test_override:
            selected=args.test_override.resolve()
            assert selected.is_file() and selected.suffix=='.py' and (root/'sim/cocotb'/selected.name).is_file()
            overrides['sim/cocotb/'+selected.name]=selected
        for source in sources:
            n=source.relative_to(root).as_posix();p=target/n;p.parent.mkdir(parents=True,exist_ok=True)
            selected=overrides.get(n,source)
            if n=='build/bidirectional-fixtures/memory.mem':freeze_model_image(selected,p,approved)
            else:shutil.copy2(selected,p)
            inputs[n]=sha(p)
        site=root/'.venv312/Lib/site-packages'
        for package in('h2','hpack','hyperframe'):
            package_sources=[p for p in(site/package).rglob('*')if p.is_file()and '__pycache__'not in p.parts]
            metadata=list(site.glob(package+'-*.dist-info'));assert len(metadata)==1
            package_sources +=[p for p in metadata[0].rglob('*')if p.is_file()and p.name!='RECORD']
            for source in package_sources:
                n='native-vendor/'+source.relative_to(site).as_posix();p=target/n;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,p);inputs[n]=sha(p)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');print('Frozen actual raw response envelopes: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_raw_envelope_tests.py'),'--execute','--profile',args.profile],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('raw_envelope_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in inputs:
            p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True)
            if n=='build/bidirectional-fixtures/memory.mem':freeze_model_image(target/n,p,root)
            else:shutil.copy2(target/n,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for n in('report.json','acceptance.json','simulation.log','build.log','results.xml','progress.json','failure.json','receive_trace.json','window_trace.json'):
            if(target/'build/test'/n).is_file():shutil.copy2(target/'build/test'/n,archive/n)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,profile=args.profile,exit_code=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat(),
            isolated_rtl_overrides={n:str(p)for n,p in overrides.items()},
            current_primary_changed_inputs=[n for n,h in inputs.items()if not n.startswith('native-vendor/')and(not(root/n).is_file()or sha(root/n)!=h)]),indent=2)+'\n')
        print('Archived actual raw envelopes: '+str(archive),flush=True);raise SystemExit(result.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/raw-envelope-tests'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(root/n)==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));build=root/'build/test';build.mkdir(parents=True,exist_ok=True);runner=get_runner('icarus')
    report=dict(phase='building',profile=args.profile,input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[root/n for n in inputs if n.startswith('rtl/')and n.endswith('.v')]+[root/'sim/cocotb_two_fpga_enveloped_top.sv'],
            hdl_toplevel='cocotb_two_fpga_enveloped_top',defines={'PARSER_PORTABLE_SIM':1},build_dir=build,always=True,log_file=build/'build.log')
        report['phase']='running'
        test_module={'native':'test_raw_grpc_enveloped','shutdown-faults':'test_raw_shutdown_faults',
            'return-faults':'test_raw_grpc_return_faults','workload':'test_raw_grpc_workload','duplex':'test_raw_grpc_duplex',
            'duplex-faults':'test_raw_grpc_duplex_faults','receive-flow':'test_raw_receive_flow','receive-errors':'test_raw_receive_errors'}[args.profile]
        runner.test(hdl_toplevel='cocotb_two_fpga_enveloped_top',test_module=test_module,test_dir=build,build_dir=build,
            results_xml=build/'results.xml',seed=20261121,extra_env={'PARSER_BIDIRECTIONAL_FIXTURES':str(root/'build/bidirectional-fixtures')},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        assert json.loads((build/'acceptance.json').read_text())['phase']=='passed'
        assert all(sha(root/n)==h for n,h in inputs.items())
        report.update(phase='passed',tests=1,failures=0,acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
