"""Freeze a full-image word-level HyperBus engine simulation in approved WSL."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--profile',choices=('engine','axi'),default='engine')
    parser.add_argument('--clock-hz',type=int,choices=(85000000,104000000,133000000,166000000,200000000),default=200000000)
    args=parser.parse_args()
    if args.profile=='axi'and args.clock_hz!=200000000:parser.error('The current integrated AXI fixture uses 200 MHz')
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and args.name.replace('_','').isalnum()
        if shutil.disk_usage(root).free<512*1024*1024:raise SystemExit(75)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/hyperram-engine-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        names=['rtl/hyperram_transaction_engine.v','sim/cocotb/hyperram_word_model.py',
            'scripts/run_hyperram_engine_tests.py','build/scu35/image/external_memory.bin']
        names+=['sim/cocotb/test_hyperram_transaction_engine.py']if args.profile=='engine'else[
            'rtl/axi_hyperram_bridge.v','sim/cocotb_axi_hyperram_engine_top.sv',
            'sim/cocotb/test_axi_hyperram_engine.py','sim/cocotb/test_axi_hyperram_bridge.py']
        inputs={}
        for n in names:
            p=target/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,p);inputs[n]=sha(p)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen HyperBus word engine: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_hyperram_engine_tests.py'),'--execute','--profile',args.profile,
            '--clock-hz',str(args.clock_hz)],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('hyperram_engine_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in names:
            p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for p in (target/'build/test').iterdir():
            if p.name in('report.json','acceptance.json','simulation.log','build.log','results.xml','hyperbus_trace.json'):shutil.copy2(p,archive/p.name)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived HyperBus word engine: '+str(archive),flush=True);raise SystemExit(result.returncode)
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(root/n)==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));build=root/'build/test';build.mkdir(parents=True,exist_ok=True)
    runner=get_runner('icarus');report=dict(phase='building',profile=args.profile,clock_hz=args.clock_hz,input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    top='hyperram_transaction_engine'if args.profile=='engine'else'cocotb_axi_hyperram_engine_top'
    test='test_hyperram_transaction_engine'if args.profile=='engine'else'test_axi_hyperram_engine'
    sources=[root/n for n in inputs if n.endswith(('.v','.sv'))]
    try:
        runner.build(sources=sources,hdl_toplevel=top,parameters={'MEMORY_CLOCK_HZ':args.clock_hz},
            build_dir=build,always=True,log_file=build/'build.log')
        report['phase']='running'
        runner.test(hdl_toplevel=top,test_module=test,
            test_dir=build,build_dir=build,results_xml=build/'results.xml',seed=20261122,
            extra_env={'PARSER_HYPERRAM_IMAGE':str(root/'build/scu35/image/external_memory.bin'),
                'PARSER_HYPERRAM_CLOCK_HZ':str(args.clock_hz)},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        assert json.loads((build/'acceptance.json').read_text())['phase']=='passed'
        report.update(phase='passed',acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
