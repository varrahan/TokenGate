"""Exercise actual power/PHY qualification loss during in-flight reads."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


FAULT_BODY='''
    // Supply qualification is synchronous to mem_clk, independent of app_clk.
    send_read_address(0,8);
    wait(active&&!register_mode&&!write_mode&&read_words>=4);
    @(negedge mem_clk);power_good_mem=0;
    wait(app_reset&&mem_reset);
    assert(!reload_done_valid)else $fatal(1,"Supply loss retained reload completion");
    #150000;@(negedge mem_clk);power_good_mem=1;
    wait(!app_reset);
    while(!memory_ready_app)begin @(negedge app_clk);assert(!s_axi_rvalid&&!s_axi_bvalid)else $fatal(1,"Supply loss left stale AXI response");end
    assert(reset_epochs==2&&contents_lost_app&&!startup_fault_app)else $fatal(1,"Supply loss recovery state");
    read_burst(0,8,0,0,13);
    assert(contents_lost_app&&!reload_done_valid)else $fatal(1,"Supply loss cleared image invalidation");
    $display("QUALIFICATION_SUPPLY_RECOVERED reset_epochs=%0d",reset_epochs);
    // A two-memory-edge PHY-ready loss must be captured and stretched, even
    // though it is much shorter than device RESET# hold and power-up waiting.
    send_read_address(0,8);
    wait(active&&!register_mode&&!write_mode&&read_words>=4);
    @(negedge mem_clk);phy_ready_mem=0;
    repeat(2)@(posedge mem_clk);
    @(negedge mem_clk);phy_ready_mem=1;
    wait(app_reset&&mem_reset);
    wait(!app_reset);
    while(!memory_ready_app)begin @(negedge app_clk);assert(!s_axi_rvalid&&!s_axi_bvalid)else $fatal(1,"PHY loss left stale AXI response");end
    assert(reset_epochs==3&&contents_lost_app&&!startup_fault_app)else $fatal(1,"PHY loss recovery state");
    read_burst(0,8,0,0,17);
    assert(contents_lost_app&&!reload_done_valid&&fifo_errors==0)else $fatal(1,"PHY loss cleared image invalidation");
    $display("QUALIFICATION_LOSS_PASS reset_epochs=3 completed_reads=%0d supply_losses=1 phy_losses=1",axi_reads);
    $finish;
end
initial begin #(64'd2000000000);$fatal(1,"Qualification loss test timeout");end
'''


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'build/experiments/hyperram-shared-reset'
    experiment=root/'build/experiments/hyperram-shared-reset-faults';experiment.mkdir(parents=True,exist_ok=False)
    generation=json.loads((source/'generation.json').read_text())
    for name,digest in generation['outputs_sha256'].items():
        original=source/name;assert sha(original)==digest,name
        target=experiment/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
    body=experiment/'sim/hyperram_async_test_body.svh';text=body.read_text()
    assert text.count('    full_phase=1;')==1
    body.write_text(text[:text.index('    full_phase=1;')]+FAULT_BODY)
    image_sha='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    image=root/'build/frozen-hyperram-images'/image_sha/'external_memory.bin'
    target=experiment/'build/frozen-hyperram-images'/image_sha/'external_memory.bin'
    target.parent.mkdir(parents=True,exist_ok=True);os.link(image,target)
    record=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),
        generator_and_driver_sha256=sha(Path(__file__)),parent_generation_sha256=sha(source/'generation.json'),
        test_body_sha256=sha(body),primary_rtl_modified=False,full_image_regression=False,
        targeted_supply_and_phy_loss=True,full_system_complete=False)
    report=experiment/'report.json';report.write_text(json.dumps(record,indent=2)+'\n')
    for tool,args in (('check_async_hyperram_windows',['--name','qualification_loss','--vendor-source-models']),
                      ('elaborate_async_hyperram_windows',['--evidence','qualification_loss'])):
        subprocess.run([sys.executable,str(experiment/'tools'/(tool+'.py'))]+args,check=True,capture_output=True)
    folder=experiment/'build/validation/qualification_loss';os.link(image,folder/'image.bin')
    command='"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" async_hyperram --runall --onerror quit --onfinish quit --maxlogsize 16 --log xsim-qualification.log --testplusarg "IMAGE=image.bin"'
    record.update(phase='running',windows_command_line=command);report.write_text(json.dumps(record,indent=2)+'\n')
    with(folder/'qualification-output.log').open('w')as output:
        run=subprocess.run(command,cwd=folder,stdout=output,stderr=subprocess.STDOUT)
    text=(folder/'qualification-output.log').read_text(errors='replace')
    markers=re.findall(r'^QUALIFICATION_LOSS_PASS (.+)$',text,re.M)
    passed=run.returncode==0 and len(markers)==1 and not re.search(r'^(?:Fatal|Error|ERROR):',text,re.M)
    values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',markers[0])}if markers else{}
    passed=passed and values==dict(reset_epochs=3,completed_reads=3,supply_losses=1,phy_losses=1)
    record.update(phase='qualification_loss_passed'if passed else'qualification_loss_failed',
        passed=passed,exit_code=run.returncode,acceptance=values,finished_utc=datetime.now(timezone.utc).isoformat(),
        rtl_sha256={path.name:sha(path)for path in(folder/'sources/rtl').glob('*.v')},
        artifact_sha256={path.relative_to(experiment).as_posix():sha(path)for path in folder.glob('*.log')})
    report.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(phase=record['phase'],acceptance=values)))
    raise SystemExit(0 if passed else 1)


if __name__=='__main__':main()
