"""Freeze a native Vivado syntax/elaboration check without claiming simulation."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True)
    parser.add_argument('--fifo-override',type=Path)
    parser.add_argument('--vendor-source-models',action='store_true');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    names=['rtl/'+n+'.v'for n in('axi_hyperram_bridge','cdc_packet_fifo','hyperram_clock_bridge','hyperram_startup',
        'hyperram_transaction_engine','hyperram_word_backend','axi_hyperram_async_controller')]
    names+=['sim/tb_axi_hyperram_async.sv','sim/hyperram_async_test_body.svh'];design_names=list(names)
    vendor={}
    if args.vendor_source_models:
        for macro in('cdc','memory','fifo'):
            name='vendor/xpm_'+macro+'.sv'
            vendor[name]=Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+macro)/'hdl'/('xpm_'+macro+'.sv')
        names+=list(vendor)
    inputs={}
    for name in names:
        source=vendor.get(name,args.fifo_override.resolve()if args.fifo_override and name=='rtl/cdc_packet_fifo.v'else root/name)
        assert source.is_file()
        target=folder/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        inputs[name]=sha(target)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        fifo_override=str(args.fifo_override)if args.fifo_override else None,
        compiler='C:/AMDDesignTools/2025.2/Vivado/bin/xvlog.bat',
        simulation_executed=False,elaboration_verified=False,full_system_complete=False,
        vendor_source_models=args.vendor_source_models,vendor_sva_enabled=not args.vendor_source_models,
        vendor_compatibility_defines=['OBSOLETE']if args.vendor_source_models else[],
        independent_testbench_assertions_enabled=True,
        driver_sha256=sha(Path(__file__)))
    command=[report['compiler'],'--sv','--include',str(folder/'sources/sim'),'--log','xvlog.log']
    command +=[str(folder/'sources'/name)for name in design_names if name.endswith(('.v','.sv'))]
    report['command']=command
    commands=[]
    if vendor:commands.append([report['compiler'],'--sv','--define','OBSOLETE','--work','xpm_source','--log','xpm-source-compile.log']+
        [str(folder/'sources'/name)for name in vendor])
    commands.append(command);report['commands']=commands
    for index,command in enumerate(commands):
        with(folder/('compiler-output-'+str(index)+'.log')).open('w')as output:
            result=subprocess.run(command,cwd=folder,check=False,stdout=output,stderr=subprocess.STDOUT)
        if result.returncode:break
    assert all(sha(folder/'sources'/name)==digest for name,digest in inputs.items())
    report.update(phase='syntax_compilation_passed'if result.returncode==0 else'syntax_compilation_failed',
        exit_code=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat())
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],exit_code=result.returncode,evidence_folder=str(folder))))
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
