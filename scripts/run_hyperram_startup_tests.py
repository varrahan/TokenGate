"""Freeze the startup/AXI assembly with a full image in the approved WSL tree."""
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
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--clock-hz',type=int,choices=(85000000,104000000,133000000,166000000,200000000),default=200000000)
    parser.add_argument('--latency',type=int,choices=range(3,8),default=7)
    parser.add_argument('--fixed',type=int,choices=(0,1),default=1);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and args.name.replace('_','').isalnum()
        if shutil.disk_usage(root).free<512*1024*1024:raise SystemExit(75)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/hyperram-startup-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        names=['rtl/'+n+'.v'for n in('axi_hyperram_bridge','hyperram_transaction_engine','hyperram_startup','axi_hyperram_controller')]
        names+=['sim/cocotb/'+n+'.py'for n in('hyperram_word_model','test_axi_hyperram_bridge','test_hyperram_startup')]
        names+=['scripts/run_hyperram_startup_tests.py','build/scu35/image/external_memory.bin', 'tools/rtl_paths.py']
        inputs={}
        for name in names:
            p=target/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, name),p);inputs[name]=sha(p)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen HyperRAM startup: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_hyperram_startup_tests.py'),'--execute',
            '--clock-hz',str(args.clock_hz),'--latency',str(args.latency),'--fixed',str(args.fixed)],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('hyperram_startup_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for name in names:
            p=archive/'execution-sources'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/name,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for p in (target/'build/test').iterdir():
            if p.name in('report.json','acceptance.json','simulation.log','build.log','results.xml','hyperbus_trace.json'):shutil.copy2(p,archive/p.name)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived HyperRAM startup: '+str(archive),flush=True);raise SystemExit(result.returncode)
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(source_path(root, n))==h for n,h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0,str(root/'sim/cocotb'));build=root/'build/test';build.mkdir(parents=True,exist_ok=True)
    runner=get_runner('icarus');report=dict(phase='building',input_sha256=inputs,
        clock_hz=args.clock_hz,latency=args.latency,fixed=args.fixed,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[source_path(root, n) for n in inputs if n.endswith('.v')],hdl_toplevel='axi_hyperram_controller',
            parameters={'MEMORY_CLOCK_HZ':args.clock_hz,'CONFIG_LATENCY':args.latency,'FIXED_LATENCY':args.fixed},
            build_dir=build,always=True,log_file=build/'build.log')
        report['phase']='running'
        runner.test(hdl_toplevel='axi_hyperram_controller',test_module='test_hyperram_startup',
            test_dir=build,build_dir=build,results_xml=build/'results.xml',seed=20261127,
            extra_env={'PARSER_HYPERRAM_IMAGE':str(root/'build/scu35/image/external_memory.bin'),
                'PARSER_HYPERRAM_CLOCK_HZ':str(args.clock_hz),'PARSER_HYPERRAM_LATENCY':str(args.latency),
                'PARSER_HYPERRAM_FIXED':str(args.fixed)},log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        assert json.loads((build/'acceptance.json').read_text())['phase']=='passed'
        report.update(phase='passed',acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
