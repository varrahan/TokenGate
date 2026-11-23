"""Freeze and run the AXI frontend independently of the pending HyperBus PHY."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and args.name.replace('_','').isalnum()
        if shutil.disk_usage(root).free<512*1024*1024:raise SystemExit(75)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/axi-hyperram-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        names=('rtl/axi_hyperram_bridge.v','sim/cocotb/test_axi_hyperram_bridge.py',
            'scripts/run_axi_hyperram_tests.py','build/scu35/image/external_memory.bin', 'tools/rtl_paths.py')
        inputs={}
        for n in names:
            p=target/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, n),p);inputs[n]=sha(p)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen AXI/HyperRAM frontend: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_axi_hyperram_tests.py'),'--execute'],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('axi_hyperram_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in names:
            p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for p in (target/'build/test').iterdir():
            if p.name in ('report.json','acceptance.json','simulation.log','build.log','results.xml'):shutil.copy2(p,archive/p.name)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived AXI/HyperRAM frontend: '+str(archive),flush=True);raise SystemExit(result.returncode)
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(source_path(root, n))==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));build=root/'build/test';build.mkdir(parents=True,exist_ok=True)
    runner=get_runner('icarus');report=dict(phase='building',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[source_path(root, 'rtl/axi_hyperram_bridge.v')],hdl_toplevel='axi_hyperram_bridge',
            build_dir=build,always=True,log_file=build/'build.log')
        report['phase']='running'
        runner.test(hdl_toplevel='axi_hyperram_bridge',test_module='test_axi_hyperram_bridge',test_dir=build,
            build_dir=build,results_xml=build/'results.xml',seed=20261122,
            extra_env={'PARSER_HYPERRAM_IMAGE':str(root/'build/scu35/image/external_memory.bin')},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        assert json.loads((build/'acceptance.json').read_text())['phase']=='passed'
        report.update(phase='passed',acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
