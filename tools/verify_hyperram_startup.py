"""Audit actual startup bus traces, fault fencing and common-reset recovery."""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    cases={}
    for label,hz,latency,fixed in (('200_fixed',200000000,7,1),('85_variable',85000000,3,0)):
        archive=root/'build/wsl-reports'/('hyperram_startup_startup_'+label+'_partial_read_reset')
        read=lambda n:json.loads((archive/n).read_text())
        inputs,report,state,accepted=(read(n)for n in('inputs.json','report.json','snapshot.json','acceptance.json'))
        assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
        assert report['input_sha256']==inputs and len(inputs)==9
        assert report['acceptance_sha256']==sha(archive/'acceptance.json')
        for name,digest in inputs.items():assert sha(archive/'execution-sources'/name)==sha(source_path(root, name))==digest,name
        xml=ET.parse(archive/'results.xml');assert len(xml.findall('.//testcase'))==1
        assert not xml.findall('.//failure')and not xml.findall('.//error')
        assert xml.find('.//testcase').attrib['name']=='startup_checks_device_before_releasing_axi'
        assert [accepted[n]for n in('clock_hz','latency','fixed_latency','startup_attempts','hardware_reset_epochs')]==[hz,latency,fixed,8,8]
        assert accepted['startup_fault_details']==[0x11,0x12,0x13,0x22,0x23]
        assert accepted['partial_read_words_before_supply_loss']==4
        assert accepted['queued_axi_reads']==accepted['queued_axi_writes']==1
        assert accepted['completed_host_reads']==3
        assert len(accepted['reset_timing'])==8
        for timing in accepted['reset_timing']:
            assert timing['reset_low_cycles']>=math.ceil(hz*200e-9)
            assert timing['first_cs_delay_cycles']>=math.ceil(hz*150e-6)
        assert accepted['full_image_sha256']==inputs['build/scu35/image/external_memory.bin']
        assert accepted['full_image_sha256']=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
        assert accepted['final_memory_sha256']==hashlib.sha256(bytes([8])*8388608).hexdigest()
        config=0x8f07|({3:14,4:15,5:0,6:1,7:2}[latency]<<4)|(fixed<<3)
        assert accepted['config_word']==config
        trace=read('hyperbus_trace.json');assert len(trace)==accepted['hyperbus_transactions']==27
        assert [(t['register'],t['write'],t['address'])for t in trace[:4]]==[
            (True,False,0),(True,False,2),(True,True,0x1000),(True,False,0x1000)]
        assert trace[2]['write_words']==[config]and trace[2]['clocks']==4
        assert trace[3]['data_clock']==2+latency*(2 if fixed else 1)
        aborted_ca=[t for t in trace if len(t['ca_words'])<3];assert len(aborted_ca)==1
        partial_reads=[t for t in trace if not t.get('register',True)and not t['write']and len(t['read_words'])==4]
        # Three complete one-beat reads and one aborted 64-byte read have four words.
        assert len(partial_reads)==4
        for flag in('register_sequence_and_config_latency_verified','powerup_reset_delays_verified',
            'startup_faults_fence_axi_verified','shared_reset_aborts_inflight_axi_verified',
            'reset_destroys_old_memory_image_in_device_model','contents_loss_ack_is_external_trust'):assert accepted[flag]
        for flag in('full_image_bootstrap_via_axi_verified','pin_level_ddr_phy_verified','rwds_cdc_verified',
            'application_instantiation_verified','native_timing_verified','full_system_complete'):assert accepted[flag]is False
        cases[label]=dict(acceptance=accepted,inputs_sha256=inputs,
            archive_sha256={p.name:sha(p)for p in archive.iterdir()if p.is_file()})
    generation=json.loads((root/'build/hyperram-startup/generation.json').read_text())
    assert generation['generator_sha256']==sha(root/'tools/generate_axi_hyperram_controller.py')
    assert generation['port_parser_sha256']==sha(root/'tools/generate_bidirectional_application.py')
    assert generation['output_sha256']==sha(source_path(root, 'rtl/axi_hyperram_controller.v'))
    assert all(sha(source_path(root, p))==h for p,h in generation['input_sha256'].items())
    with tempfile.TemporaryDirectory(prefix='hyperram-startup-replay-')as temp:
        replay=Path(temp)
        for name in list(generation['input_sha256'])+['tools/generate_axi_hyperram_controller.py','tools/generate_bidirectional_application.py', 'tools/rtl_paths.py']:
            p=replay/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, name),p)
        subprocess.run([sys.executable,str(replay/'tools/generate_axi_hyperram_controller.py')],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/hyperram-startup/generation.json').read_text())==generation
    log=root/'build/validation/hyperram-startup-structural.log'
    assert 'Found and reported 0 problems.'in log.read_text()and'ERROR:'not in log.read_text()
    result=dict(phase='hyperram_startup_and_axi_assembly_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        cases=cases,generation=generation,generator_replay_verified=True,structural_log_sha256=sha(log),
        qualified_synchronous_power_and_phy_inputs_required=True,shared_axi_master_reset_required=True,
        external_validated_reload_ack_required=True,full_image_bootstrap_via_axi_verified=False,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,application_instantiation_verified=False,
        native_timing_verified=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/hyperram-startup-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in(Path(__file__),log,source_path(root, 'rtl/hyperram_startup.v'),source_path(root, 'rtl/axi_hyperram_controller.v'),
        root/'sim/cocotb/test_hyperram_startup.py',root/'tools/generate_axi_hyperram_controller.py'):shutil.copy2(p,evidence/p.name)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/hyperram-startup.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],startup_attempts=16,startup_faults=10)))


if __name__=='__main__':main()
