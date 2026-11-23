"""Native four-state clock-bridge tests against unchanged AMD source models."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--fifo-override',type=Path,required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();installed=Path('C:/AMDDesignTools/2025.2/Vivado')
    original={'rtl/cdc_packet_fifo.v':args.fifo_override.resolve(),'rtl/hyperram_clock_bridge.v':root/'rtl/hyperram_clock_bridge.v',
        'sim/tb_hyperram_clock_bridge.sv':root/'sim/tb_hyperram_clock_bridge.sv','vendor/glbl.v':installed/'data/verilog/src/glbl.v'}
    for macro in('cdc','memory','fifo'):original['vendor/xpm_'+macro+'.sv']=installed/'data/ip/xpm'/('xpm_'+macro)/'hdl'/('xpm_'+macro+'.sv')
    inputs={}
    for name,p in original.items():
        q=folder/'sources'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[name]=sha(q)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        driver_sha256=sha(Path(__file__)),vendor_sources_unmodified=True,vendor_sva_enabled=False,
        compatibility_defines=['OBSOLETE'],independent_assertions_enabled=True,profiles={},
        native_cdc_signoff_verified=False,full_system_complete=False,commands=[])
    output=folder/'report.json'
    def run(command,label):
        report['commands'].append(command);output.write_text(json.dumps(report,indent=2)+'\n')
        with(folder/(label+'.log')).open('w')as log:
            code=subprocess.run(command,cwd=folder,check=False,stdout=log,stderr=subprocess.STDOUT).returncode
        if code:raise RuntimeError(label+' returned '+str(code))
    try:
        run([str(installed/'bin/xvlog.bat'),'--sv','--define','OBSOLETE','--work','xpm_source','--log','xpm-compile.log']+
            [str(folder/'sources'/n)for n in inputs if n.startswith('vendor/xpm_')],'vendor_compiler')
        run([str(installed/'bin/xvlog.bat'),'--sv','--log','design-compile.log']+
            [str(folder/'sources'/n)for n in inputs if not n.startswith('vendor/xpm_')],'design_compiler')
        run([str(installed/'bin/xelab.bat'),'--debug','off','--snapshot','cdc_bridge','-L','xpm_source',
            '-L','unisims_ver','-L','unimacro_ver','--log','xelab.log','work.tb_hyperram_clock_bridge','work.glbl'],'elaborator')
        report['phase']='running'
        for label,app,mem,phase in(('target_250_200',2000,2500,700),('slow_memory',2000,6500,1100),
            ('slow_application',3500,1500,350),('coincident_edges',2500,2500,0)):
            command='"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" cdc_bridge --runall --onerror quit --onfinish quit --maxlogsize 8 --log xsim-'+label+'.log'
            command+=f' --testplusarg "APP_HALF={app}" --testplusarg "MEM_HALF={mem}" --testplusarg "MEM_PHASE={phase}"'
            run(command,label)
            text=(folder/(label+'.log')).read_text(errors='replace')
            line=next((s for s in text.splitlines()if s.startswith('CDC_TEST_PASS ')),None)
            assert line,'Native clock test did not reach its completion assertions'
            assert not re.search(r'^(?:Fatal|Error):',text,re.M)
            values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line)}
            assert values['epochs']==4 and values['completed']>=3000
            assert values['source_holds']>=50 and values['response_holds']>=50
            assert [values[k]for k in('app_half','mem_half','phase')]==[app,mem,phase]
            report['profiles'][label]=values
        assert all(sha(folder/'sources'/name)==digest for name,digest in inputs.items())
        report.update(phase='native_four_state_clock_profiles_passed',passed=True)
    except BaseException as error:
        report.update(phase='native_clock_profile_failed',passed=False,error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],clock_profiles=len(report['profiles']),
        completed_responses=sum(p['completed']for p in report['profiles'].values()))))


if __name__=='__main__':main()
