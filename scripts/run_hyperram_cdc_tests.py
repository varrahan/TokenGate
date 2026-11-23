"""Test the real XPM FIFO models unchanged, with explicit simulator limitations."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and args.name.replace('_','').isalnum()
        if shutil.disk_usage(root).free<512*1024*1024:raise SystemExit(75)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/hyperram-cdc-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
        original={n:root/n for n in('rtl/cdc_packet_fifo.v','rtl/hyperram_clock_bridge.v','sim/tb_hyperram_clock_bridge.sv','scripts/run_hyperram_cdc_tests.py')}
        installed=Path('/mnt/c/AMDDesignTools/2025.2/Vivado/data/ip/xpm')
        for n in('cdc','memory','fifo'):original['vendor/xpm_'+n+'.sv']=installed/('xpm_'+n)/'hdl'/('xpm_'+n+'.sv')
        inputs={}
        for name,p in original.items():
            q=target/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[name]=sha(q)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen native-XPM HyperRAM CDC: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_hyperram_cdc_tests.py'),'--execute'],check=False)
        assert all(sha(target/n)==h==sha(original[n])for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('hyperram_cdc_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for name in inputs:
            q=archive/'execution-sources'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/name,q)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for p in(target/'build/test').iterdir():
            if p.is_file():shutil.copy2(p,archive/p.name)
        (archive/'snapshot.json').write_text(json.dumps(dict(name=args.name,exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived native-XPM HyperRAM CDC: '+str(archive),flush=True);raise SystemExit(result.returncode)
    inputs=json.loads((root/'inputs.json').read_text());assert len(inputs)==7
    assert all(sha(root/n)==h for n,h in inputs.items())
    folder=root/'build/test';folder.mkdir(parents=True,exist_ok=True)
    sources=[str(root/n)for n in inputs if n.endswith(('.v','.sv'))]
    common=['verilator','--timing','--assert','--bbox-unsup','-DOBSOLETE','-DONESPIN','-Wno-fatal',
        '--top-module','tb_hyperram_clock_bridge']
    report=dict(phase='building',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat(),
        simulator_version=subprocess.run(['verilator','--version'],check=True,capture_output=True,text=True).stdout.strip(),
        compiler_flags=common[1:],vendor_sources_unmodified=True,vendor_sva_enabled=False,
        independent_testbench_assertions_enabled=True,profiles={})
    try:
        with(folder/'build.log').open('w')as output:
            subprocess.run(common+['--binary','-j','2','--Mdir',str(folder/'obj')]+sources,
                check=True,stdout=output,stderr=subprocess.STDOUT)
        with(folder/'elaboration.log').open('w')as output:
            subprocess.run(common+['--xml-only','--flatten','--xml-output',str(folder/'elaboration.xml')]+sources,
                check=True,stdout=output,stderr=subprocess.STDOUT)
        xml=(folder/'elaboration.xml').read_text()
        assert 'ecc_behav_logic'not in xml,'Unsupported ECC branch reached the elaborated model'
        assert 'deassign'not in xml
        report['unsupported_ecc_branches_absent_from_elaborated_model']=True
        binary=folder/'obj/Vtb_hyperram_clock_bridge';report['binary_sha256']=sha(binary)
        report['phase']='running'
        for label,app,mem,phase in(('target_250_200',2000,2500,700),('slow_memory',2000,6500,1100),
            ('slow_application',3500,1500,350),('coincident_edges',2500,2500,0)):
            log=folder/(label+'.log')
            with log.open('w')as output:
                subprocess.run([str(binary),f'+APP_HALF={app}',f'+MEM_HALF={mem}',f'+MEM_PHASE={phase}'],
                    check=True,stdout=output,stderr=subprocess.STDOUT)
            text=log.read_text();line=next(line for line in text.splitlines()if line.startswith('CDC_TEST_PASS '))
            values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line)}
            assert values['epochs']==4 and values['completed']>=3000
            assert values['source_holds']>=50 and values['response_holds']>=50
            assert [values[n]for n in('app_half','mem_half','phase')]==[app,mem,phase]
            report['profiles'][label]=values
        accepted=dict(phase='passed',profiles=report['profiles'],command_bits=607,response_bits=521,
            actual_unmodified_amd_fifo_models_executed=True,reset_full_queues_and_active_traffic_verified=True,
            held_complete_packets_and_order_verified=True,unsupported_ecc_branches_absent_from_elaboration=True,
            vendor_sva_enabled=False,independent_testbench_assertions_enabled=True,
            analog_metastability_verified=False,native_cdc_constraints_verified=False,
            application_instantiation_verified=False,pin_level_rwds_cdc_verified=False,full_system_complete=False)
        (folder/'acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n')
        report.update(phase='passed',acceptance_sha256=sha(folder/'acceptance.json'))
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();(folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
