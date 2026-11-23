"""Elaborate a frozen Windows syntax check with installed native XPM libraries."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.evidence)
    root=Path(__file__).resolve().parents[1];folder=root/'build/validation'/args.evidence
    syntax=json.loads((folder/'report.json').read_text());assert syntax['phase']=='syntax_compilation_passed'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,digest in syntax['inputs_sha256'].items():assert sha(folder/'sources'/name)==digest
    output=folder/'elaboration-report.json';assert not output.exists(),'Preserve prior elaboration evidence'
    glbl=Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v')
    target=folder/'sources/vendor/glbl.v';target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(glbl,target)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    report=dict(phase='compiling_global_module',started_utc=datetime.now(timezone.utc).isoformat(),
        glbl_sha256=sha(glbl),driver_sha256=sha(Path(__file__)),simulation_executed=False,
        elaboration_verified=False,full_system_complete=False,commands=[])
    commands=[['C:/AMDDesignTools/2025.2/Vivado/bin/xvlog.bat','--sv','--log','glbl-compile.log',str(target)],
        ['C:/AMDDesignTools/2025.2/Vivado/bin/xelab.bat','--debug','off','--snapshot','async_hyperram',
         '-L','xpm_source'if syntax.get('vendor_source_models')else'xpm','-L','unisims_ver','-L','unimacro_ver','--log','xelab.log','work.tb_axi_hyperram_async','work.glbl']]
    try:
        for index,command in enumerate(commands):
            report['commands'].append(command)
            with(folder/('elaboration-output-'+str(index)+'.log')).open('w')as log:
                result=subprocess.run(command,cwd=folder,check=False,stdout=log,stderr=subprocess.STDOUT)
            report['exit_code']=result.returncode
            if result.returncode:
                report['phase']='native_elaboration_failed';break
        else:
            report.update(phase='native_elaboration_passed',elaboration_verified=True)
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],exit_code=report['exit_code'],evidence_folder=str(folder))))
    raise SystemExit(report['exit_code'])


if __name__=='__main__':main()
