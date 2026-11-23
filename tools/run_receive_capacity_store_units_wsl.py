"""Freeze and run the full original legacy suite and new capacity-store tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name');ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    approved=Path('/home/varrahan/development/hardware/parser')
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9_]+',args.name)
        original=root/'build/wsl-reports/http2_receive_credits_receive_credit_actual_retired_binding'
        baseline=json.loads((original/'inputs.json').read_text())
        generation=json.loads((root/'build/experiments/receive-capacity-store/generation.json').read_text())
        target=approved/'build/receive-capacity-store-units'/args.name
        archive=root/'build/wsl-reports'/args.name
        assert not archive.exists();target.mkdir(parents=True,exist_ok=False)
        inputs={}
        for name,digest in baseline.items():
            source=original/'execution-sources'/name;assert sha(source)==digest,name
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,destination);inputs[name]=digest
        for name,digest in generation['outputs_sha256'].items():
            source=root/'build/experiments/receive-capacity-store'/name;assert sha(source)==digest
            shutil.copy2(source,target/name);inputs[name]=digest
        for name in ('sim/cocotb/test_receive_capacity_store.py','tools/run_receive_capacity_store_units_wsl.py'):
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/name,destination);inputs[name]=sha(destination)
        assert {n for n in baseline if inputs[n]!=baseline[n]}=={'rtl/http2_receive_credit_store.v'}
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        shutil.copy2(root/'build/experiments/receive-capacity-store/generation.json',target/'generation.json')
        with (target/'driver.log').open('w') as stream:
            code=subprocess.call([sys.executable,str(target/'tools/run_receive_capacity_store_units_wsl.py'),'--execute'],cwd=target,stdout=stream,stderr=subprocess.STDOUT)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive.mkdir(parents=True,exist_ok=False)
        for name in inputs:
            destination=archive/'execution-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/name,destination)
        for name in ('inputs.json','generation.json','driver.log'):shutil.copy2(target/name,archive/name)
        shutil.copytree(target/'build/capacity-tests',archive/'results')
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=code,finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print(json.dumps(dict(name=args.name,exit_code=code)),flush=True);raise SystemExit(code)
    assert root.parent==approved/'build/receive-capacity-store-units'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(root/n)==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'))
    folder=root/'build/capacity-tests';folder.mkdir(parents=True,exist_ok=False)
    report=dict(phase='running',inputs_sha256=inputs,passed=False,executions=[],started_utc=datetime.now(timezone.utc).isoformat())
    try:
        for label,module,enabled in [('legacy','test_receive_credit_store',0),('capacity','test_receive_capacity_store',1)]:
            build=folder/label;build.mkdir()
            runner=get_runner('icarus')
            runner.build(sources=[root/'rtl/http2_receive_credit_store.v',root/'rtl/memory_command_slot.v'],
                hdl_toplevel='http2_receive_credit_store',parameters={'ENABLE_CAPACITY':enabled},
                build_dir=build,always=True,log_file=build/'build.log')
            runner.test(hdl_toplevel='http2_receive_credit_store',test_module=module,build_dir=build,test_dir=build,
                results_xml=build/'results.xml',seed=20261122,
                extra_env={'PARSER_HTTP2_SEND_WINDOW_FIXTURES':str(root/'build/http2-send-window-fixtures')},log_file=build/'simulation.log')
            xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure') and not xml.findall('.//error')
            accepted=json.loads((build/'acceptance.json').read_text());assert accepted['phase']=='passed'
            report['executions'].append(dict(mode=label,enabled=enabled,test_module=module,acceptance_sha256=sha(build/'acceptance.json')))
        report.update(phase='passed',passed=True)
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
