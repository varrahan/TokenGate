"""Implement the exact full-default SIMD decoder tested by native XSim."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from verify_two_fpga_application import closure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    tested=root/'build/validation/json_simd_decoder_full_native';functional=json.loads((tested/'report.json').read_text())
    assert functional['passed']and functional['full_default_decoder_parameters']
    assert functional['expected']['committed']==32 and functional['expected']['maximum_text_bytes']==16200
    original=tested/'candidate/sources';state=functional['revisions']['candidate']
    dependencies=closure('proto_json_decoder',original);assert len(dependencies)==11
    for module,path in dependencies.items():assert sha(path)==state['inputs_sha256']['rtl/'+path.name],module
    free=shutil.disk_usage(root).free;assert free>=3*1024**3,'Need 3 GiB for the isolated decoder'
    part='xcau15p-ffvb676-2-e';top='proto_json_decoder'
    folder=root/'build/validation'/(args.name+'-inputs');launch=root/'build/validation'/(args.name+'-launch.json')
    assert not launch.exists()and not(root/'build/implementation'/part/args.name).exists()
    folder.mkdir(parents=True,exist_ok=False);inputs={}
    for path in dependencies.values():
        target=folder/'rtl'/path.name;target.parent.mkdir(exist_ok=True);shutil.copy2(path,target);inputs['rtl/'+path.name]=sha(target)
    for name in('scripts/implement_registered_subsystem.tcl','tools/generate_parser_timing_harness.py','constraints/parser.xdc'):
        path=root/name;target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);inputs[name]=sha(target)
    shutil.copy2(tested/'report.json',folder/'functional-report.json');shutil.copy2(Path(__file__),folder/Path(__file__).name)
    harness=root/'build'/(args.name+'-timing-harness.v')
    subprocess.run([sys.executable,str(folder/'tools/generate_parser_timing_harness.py'),'--source',str(folder/'rtl'/(top+'.v')),
        '--top',top,'--harness-top',top+'_timing_harness','--output',str(harness)],check=True,capture_output=True)
    command=['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace','-source',
        str(root/'scripts/implement_registered_subsystem.tcl'),'-log',str(root/'build'/(args.name+'-implementation.log')),
        '-journal',str(root/'build'/(args.name+'-implementation.jou')),'-tclargs',top,args.name,'implementation','Default',part,str(folder/'rtl'),'1']
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),run=args.name,top=top,part=part,
        exact_core_modules=11,functional_report_sha256=sha(tested/'report.json'),inputs_sha256=inputs,
        harness_sha256=sha(harness),driver_sha256=sha(Path(__file__)),command=command,max_threads=1,
        free_bytes_before=free,minimum_free_bytes=3*1024**3,clock_period_ns=4.0,
        full_parser_transport_implementation=False,package_timing_verified=False,primary_parser_rtl_modified=False,full_system_complete=False)
    def save():launch.write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        for name,digest in inputs.items():assert sha(folder/name)==digest
        with(root/'build'/(args.name+'-stdout.log')).open('w')as output:
            process=subprocess.Popen(command,cwd=root,stdout=output,stderr=subprocess.STDOUT)
            report['launcher_pid']=process.pid;save();code=process.wait()
        report['exit_code']=code;assert code==0,code
        text=(root/'build'/(args.name+'-stdout.log')).read_text(errors='replace')
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP='+top in text and 'ERROR:'not in text
        report['phase']='native_process_completed'
    except BaseException as error:report.update(phase='stopped_with_error',error=str(error));raise
    finally:
        report.update(finished_utc=datetime.now(timezone.utc).isoformat(),free_bytes_after=shutil.disk_usage(root).free);save()
    print(json.dumps({key:report[key]for key in('phase','run','exit_code','exact_core_modules')}))


if __name__=='__main__':main()
