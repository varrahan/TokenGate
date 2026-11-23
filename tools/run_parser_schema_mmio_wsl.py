"""Functional schema test in approved WSL; not native vendor-RAM evidence."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--source',required=True);args=ap.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9_]+',n) for n in (args.name,args.source))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original=root/'build/validation'/args.source
    native=json.loads((original/'report.json').read_text())
    assert native['expected_packets']==65 and native['expected_durable_applies']==2
    assert 'Built simulation snapshot parser_schema_mmio' in (original/'elaborate-stdout.log').read_text()
    approved=Path('/home/varrahan/development/hardware/parser')
    assert approved.is_dir() and Path.home()==approved.parents[2]
    folder=approved/'build/parser-schema-mmio'/args.name
    folder.mkdir(parents=True,exist_ok=False)
    archive=root/'build/wsl-reports'/args.name;assert not archive.exists()
    for name,digest in native['inputs_sha256'].items():
        path=original/'sources'/name;assert sha(path)==digest,name
        target=folder/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    shutil.copy2(original/'schema-vectors.txt',folder/'schema-vectors.txt')
    assert sha(folder/'schema-vectors.txt')==native['vectors_sha256']
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    result=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),native_source=args.source,
        native_report_sha256=sha(original/'report.json'),inputs_sha256=native['inputs_sha256'],vectors_sha256=native['vectors_sha256'],
        driver_sha256=sha(Path(__file__)),commands=[],passed=False,portable_memory_backend=True,
        native_vendor_runtime_verified=False,paired_transport_integration_verified=False,native_timing_verified=False,full_system_complete=False)
    def save(): (folder/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(command,name):
        result['commands'].append(command);save()
        with (folder/(name+'.log')).open('w') as output:
            code=subprocess.call(command,cwd=folder,stdout=output,stderr=subprocess.STDOUT)
        text=(folder/(name+'.log')).read_text(errors='replace')
        assert code==0 and not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),(name,code)
        return text
    save()
    try:
        files=sorted((folder/'sources/rtl').glob('*.v'))+[folder/'sources/vendor/glbl.v',folder/'sources/sim/tb_parser_schema_mmio.sv']
        run(['iverilog','-g2012','-DPARSER_PORTABLE_SIM','-s','tb_parser_schema_mmio','-o','simulation.vvp']+[str(p) for p in files],'compile')
        result['phase']='simulating';save()
        text=run(['vvp','simulation.vvp'],'simulate')
        assert text.count('PARSER_SCHEMA_MMIO_TEST_PASS')==1
        assert all(sha(folder/'sources'/n)==h for n,h in native['inputs_sha256'].items())
        result.update(phase='functional_parser_schema_mmio_verified',passed=True,
            result=re.search(r'^PARSER_SCHEMA_MMIO_TEST_PASS.*$',text,re.M)[0],log_sha256=sha(folder/'simulate.log'))
    except BaseException as error:result.update(phase='failed',error=str(error));raise
    finally:
        result['finished_utc']=datetime.now(timezone.utc).isoformat();save()
        archive.mkdir(parents=True,exist_ok=False)
        for name in ['report.json','schema-vectors.txt',Path(__file__).name,'compile.log','simulate.log']:
            if (folder/name).exists():shutil.copy2(folder/name,archive/name)
        shutil.copytree(folder/'sources',archive/'sources')
    print(json.dumps({k:result[k] for k in ('phase','passed','portable_memory_backend','native_vendor_runtime_verified','result')}))


if __name__=='__main__':main()
