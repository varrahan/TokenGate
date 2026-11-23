"""Freeze the audited 75-module Parser and implement it on the AU15P candidate."""
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

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    part='xcau15p-ffvb676-2-e';top='http2_enveloped_parser_application'
    audit_path=root/'build/validation/progress-format-corpus.json';audit=json.loads(audit_path.read_text())
    assert audit['key']=='6dd529d376e06926'and audit['full_native_corpus_verified']
    assert audit['exact_parser_modules']==75 and len(audit['executed_parser_sha256'])==75
    archive=root/'build/wsl-reports/raw_envelope_progress_format_full_native_corpus'
    for name,digest in audit['archive_files_sha256'].items():assert sha(archive/name)==digest,name
    free=shutil.disk_usage(root).free
    assert free>=10*1024**3,'Need at least 10 GiB free for the full Parser implementation'
    folder=root/'build/validation'/(args.name+'-inputs')
    launch_path=root/'build/validation'/(args.name+'-launch.json')
    assert not launch_path.exists()and not(root/'build/implementation'/part/args.name).exists()
    folder.mkdir(parents=True,exist_ok=False);inputs={}
    for module,digest in audit['executed_parser_sha256'].items():
        source=archive/'execution-sources/rtl'/(module+'.v');assert sha(source)==digest,module
        assert(source_path(root, Path('rtl') / (source.name))).is_file(),'Generic implementation override must replace an existing filename'
        target=folder/'rtl'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target);inputs['rtl/'+source.name]=digest
    dependencies=closure(top,folder)
    assert len(dependencies)==75 and set(dependencies)==set(audit['executed_parser_sha256'])
    assert all(sha(path)==audit['executed_parser_sha256'][module]for module,path in dependencies.items())
    for name in('scripts/implement_registered_subsystem.tcl','scripts/run_registered_subsystem_implementation.ps1',
                 'tools/generate_parser_timing_harness.py','tools/capture_source_provenance.py','constraints/parser.xdc', 'tools/rtl_paths.py', 'scripts/rtl_sources.tcl'):
        source=source_path(root, name);target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);inputs[name]=sha(target)
    shutil.copy2(audit_path,folder/'functional-corpus-audit.json');shutil.copy2(Path(__file__),folder/Path(__file__).name)
    harness=root/'build'/(args.name+'-timing-harness.v')
    subprocess.run([sys.executable,str(folder/'tools/generate_parser_timing_harness.py'),
        '--source',str(folder/'rtl'/(top+'.v')),'--top',top,'--harness-top',top+'_timing_harness',
        '--output',str(harness)],check=True,capture_output=True)
    command=['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace','-source',
        str(root/'scripts/implement_registered_subsystem.tcl'),'-log',str(root/'build'/(args.name+'-implementation.log')),
        '-journal',str(root/'build'/(args.name+'-implementation.jou')),'-tclargs',top,args.name,'implementation','Default',part,str(folder/'rtl'),'1']
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),run=args.name,top=top,part=part,
        functional_corpus_audit_key=audit['key'],functional_corpus_audit_sha256=sha(audit_path),
        exact_parser_modules=75,inputs_sha256=inputs,harness_sha256=sha(harness),driver_sha256=sha(Path(__file__)),
        command=command,max_threads=1,free_bytes_before=free,minimum_free_bytes=10*1024**3,
        clock_period_ns=4.0,package_timing_verified=False,primary_rtl_modified=False,full_system_complete=False)
    def save():launch_path.write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        for name,digest in inputs.items():assert sha(source_path(root, name))==digest if not name.startswith('rtl/')else sha(folder/name)==digest
        with(root/'build'/(args.name+'-stdout.log')).open('w')as output:
            process=subprocess.Popen(command,cwd=root,stdout=output,stderr=subprocess.STDOUT)
            report['launcher_pid']=process.pid;save();code=process.wait()
        report['exit_code']=code
        assert code==0,('Vivado returned failure',code)
        text=(root/'build'/(args.name+'-stdout.log')).read_text(errors='replace')
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP='+top in text and 'ERROR:'not in text
        assert all(sha(folder/name)==digest for name,digest in inputs.items())
        report['phase']='native_process_completed'
    except BaseException as error:
        report.update(phase='stopped_with_error',error=str(error));raise
    finally:
        report.update(finished_utc=datetime.now(timezone.utc).isoformat(),free_bytes_after=shutil.disk_usage(root).free);save()
    print(json.dumps({key:report[key]for key in('phase','run','exit_code','functional_corpus_audit_key')}))


if __name__=='__main__':main()
