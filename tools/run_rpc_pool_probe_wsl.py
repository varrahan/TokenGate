"""Exercise the probe against the real pool guard/store and physical ACKs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from rtl_paths import source_path


def top_source(store,probe):
    from generate_hyperram_cdc_timing_harness import ports
    lines=['`timescale 1ns/1ps','`default_nettype none','module rpc_probe_top;',
        'localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;',
        'reg clk=0,rst=1,force_unlock=0;',
        'reg mem_ready=0,mem_rsp_valid=0;reg [71:0] mem_rsp_data=0;reg [7:0] mem_rsp_status=0;',
        'wire mem_valid,mem_write,mem_rsp_ready;wire [22:0] mem_addr;wire [3:0] mem_bytes;wire [71:0] mem_data;']
    store_links={
        'pool_lock_valid':'probe_lock_valid','pool_lock_base':'probe_lock_base','pool_lock_bytes':'probe_lock_bytes',
        'pool_lock_result_ready':'probe_lock_result_ready','pool_unlock_valid':'probe_unlock_valid||force_unlock'}
    probe_links={
        'lock_ready':'dir_pool_lock_ready','lock_result_valid':'dir_pool_lock_result_valid',
        'lock_status':'dir_pool_lock_status','lock_active':'dir_pool_lock_active','unlock_ready':'dir_pool_unlock_ready'}
    for module,prefix,source,links in(
        ('grpc_pool_locked_stream_store','dir',store,store_links),('rpc_pool_empty_probe','probe',probe,probe_links)):
        mapping=[]
        for direction,width,name in ports(source,module):
            if name in('clk','rst'):target=name
            elif name in links:target=links[name]
            elif direction=='input'and name.startswith('mem_'):
                owner='probe_memory_owner'if prefix=='probe'else'!probe_memory_owner'
                if name=='mem_ready':target='('+owner+')&&mem_ready'
                elif name=='mem_rsp_valid':target='('+owner+')&&mem_rsp_valid'
                else:target=name
            else:
                target=prefix+'_'+name
                lines.append(('reg 'if direction=='input'else'wire ')+width+' '+target+('=0'if direction=='input'else'')+';')
            mapping.append('.'+name+'('+target+')')
        params='#(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH))'if prefix=='dir'else'#(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH))'
        lines += [module+' '+params+' '+prefix+'_dut('+',\n'.join(mapping)+');']
    for name in('mem_valid','mem_write','mem_addr','mem_bytes','mem_data','mem_rsp_ready'):
        lines.append('assign '+name+'=probe_memory_owner?probe_'+name+':dir_'+name+';')
    lines+=['endmodule','`default_nettype wire','']
    return '\n'.join(lines)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name');ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9_]+',args.name)
        parent=root/'build/experiments/rpc-receive-payload-pipeline-v1'
        g=json.loads((parent/'generation.json').read_text())
        target=Path.home()/'development/hardware/parser/build/rpc-pool-probe'/args.name
        archive=root/'build/wsl-reports'/('rpc_pool_probe_'+args.name)
        launch=root/'build/validation'/(args.name+'-probe-launch.json')
        assert not archive.exists()and not launch.exists();target.mkdir(parents=True,exist_ok=False)
        for name in('grpc_pool_locked_stream_store','grpc_stream_store','memory_command_slot'):
            source=parent/'joint/rtl'/(name+'.v');assert sha(source)==g['non_mmio_parser_sha256'][name]
            path=target/'rtl'/source.name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,path)
        for name in('rtl/rpc_pool_empty_probe.v','sim/cocotb/test_rpc_pool_probe.py','tools/run_rpc_pool_probe_wsl.py','tools/generate_hyperram_cdc_timing_harness.py', 'tools/rtl_paths.py'):
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, name),path)
        (target/'sim/rpc_probe_top.sv').write_text(top_source((target/'rtl/grpc_pool_locked_stream_store.v').read_text(),(target/'rtl/rpc_pool_empty_probe.v').read_text()))
        inputs={p.relative_to(target).as_posix():sha(p)for p in target.rglob('*')if p.is_file()}
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        record=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),name=args.name,
            target=str(target),parent_generation_sha256=sha(parent/'generation.json'),inputs_sha256=inputs,
            actual_pool_guard_and_directory_and_memory_slot=True,component_only=True,
            complete_application_integrated=False,global_reload_authority_verified=False,full_system_complete=False)
        def save():launch.write_text(json.dumps(record,indent=2)+'\n')
        save()
        try:
            with(target/'driver.log').open('w')as log:
                process=subprocess.Popen([sys.executable,str(target/'tools/run_rpc_pool_probe_wsl.py'),'--execute'],cwd=target,stdout=log,stderr=subprocess.STDOUT)
                record['process_pid']=process.pid;save();code=process.wait()
            record.update(phase='completed'if code==0 else'failed',exit_code=code);assert code==0,('Actual pool probe test failed',code)
        except BaseException as error:record.update(phase='failed',error=str(error));raise
        finally:
            assert all(sha(target/n)==h for n,h in inputs.items())
            record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
            archive.mkdir(parents=True,exist_ok=False)
            for n in inputs:
                p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,p)
            for name in('inputs.json','driver.log'):shutil.copy2(target/name,archive/name)
            shutil.copy2(launch,archive/'launch.json')
            for p in(target/'build/test').iterdir():
                if p.is_file()and p.suffix in('.json','.log','.xml'):shutil.copy2(p,archive/p.name)
        print(json.dumps(dict(phase=record['phase'],exit_code=record['exit_code'])),flush=True)
        return
    from cocotb_tools.runner import get_runner
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(source_path(root, n))==h for n,h in inputs.items())
    build=root/'build/test';build.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(root/'sim/cocotb'))
    record=dict(phase='running',inputs_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner=get_runner('icarus')
        runner.build(sources=[source_path(root, n) for n in inputs if n.endswith(('.v','.sv'))],hdl_toplevel='rpc_probe_top',build_dir=build,always=True,log_file=build/'build.log')
        runner.test(hdl_toplevel='rpc_probe_top',test_module='test_rpc_pool_probe',test_dir=build,build_dir=build,results_xml=build/'results.xml',log_file=build/'simulation.log')
        xml=ET.parse(build/'results.xml');assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure')and not xml.findall('.//error')
        accepted=json.loads((build/'acceptance.json').read_text());assert accepted['phase']=='passed'
        record.update(phase='passed',tests=1,failures=0,acceptance_sha256=sha(build/'acceptance.json'))
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:
        record['finished_utc']=datetime.now(timezone.utc).isoformat();(build/'report.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':main()
