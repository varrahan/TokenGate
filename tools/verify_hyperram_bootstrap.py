"""Audit every byte programmed/read through actual AXI and HyperBus word RTL."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports/hyperram_bootstrap_full_8mib_axi_bootstrap_readback'
    read=lambda n:json.loads((archive/n).read_text())
    inputs,report,state,accepted=(read(n)for n in('inputs.json','report.json','snapshot.json','acceptance.json'))
    assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
    assert len(inputs)==10 and report['input_sha256']==inputs
    for name,digest in inputs.items():assert sha(archive/'execution-sources'/name)==sha(source_path(root, name))==digest,name
    assert report['acceptance_sha256']==sha(archive/'acceptance.json')
    xml=ET.parse(archive/'results.xml');assert len(xml.findall('.//testcase'))==1
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert xml.find('.//testcase').attrib['name']=='complete_image_is_programmed_and_read_back_through_axi'
    assert accepted['image_bytes']==8388608 and accepted['axi_writes']==accepted['axi_reads']==131072
    assert accepted['hyperbus_register_transactions']==4
    digest=inputs['build/scu35/image/external_memory.bin']
    assert digest=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    for field in('image_sha256','wire_write_sha256','wire_read_sha256','axi_read_sha256'):assert accepted[field]==digest
    wire=read('wire-summary.json');assert wire['writes']==wire['reads']==131072
    assert wire['write_sha256']==wire['read_sha256']==digest
    last_address=8388608-64
    last_ca=(1<<47)|(1<<45)|((last_address>>4)<<16)|((last_address>>1)&7)
    assert wire['last']==dict(ca_hex=f'{last_ca:012x}',address=last_address,write=False,bytes=64)
    registers=wire['registers'];assert len(registers)==4
    assert [(t['register'],t['write'],t['address'])for t in registers]==[
        (True,False,0),(True,False,2),(True,True,4096),(True,False,4096)]
    assert registers[0]['read_words']==[0x0c81]and registers[1]['read_words']==[1]
    assert registers[2]['write_words']==[0x8f2f]and registers[3]['read_words']==[0x8f2f]
    assert accepted['write_cycles']>=131072*32 and accepted['read_cycles']>=131072*32
    for flag in('reset_destroyed_previous_image_verified','every_byte_programmed_and_read_back',
        'no_vocabulary_or_address_range_reduction','contents_loss_ack_after_complete_readback'):assert accepted[flag]
    for flag in('pin_level_ddr_phy_verified','rwds_cdc_verified','application_instantiation_verified',
        'native_timing_verified','full_system_complete'):assert accepted[flag]is False
    assert read('progress.json')==dict(phase='passed',completed_bytes=8388608,total_bytes=8388608)
    startup=json.loads((root/'build/validation/hyperram-startup.json').read_text())
    for name in('axi_hyperram_bridge','hyperram_transaction_engine','hyperram_startup','axi_hyperram_controller'):
        path='rtl/'+name+'.v'
        assert all(c['inputs_sha256'][path]==inputs[path]for c in startup['cases'].values())
    result=dict(phase='complete_hyperram_image_axi_bootstrap_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,wire_summary=wire,input_sha256=inputs,
        archive_sha256={p.name:sha(p)for p in archive.iterdir()if p.is_file()},
        functional_startup_audit_key=startup['key'],complete_8mib_image_and_address_sweep_verified=True,
        application_clock_bridge_instantiated=False,pin_level_ddr_phy_verified=False,
        rwds_cdc_verified=False,application_instantiation_verified=False,full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/hyperram-bootstrap-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in(Path(__file__),root/'sim/cocotb/test_hyperram_bootstrap.py',archive/'wire-summary.json'):
        shutil.copy2(p,evidence/p.name)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/hyperram-bootstrap.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],image_bytes=8388608,axi_transactions=262144)))


if __name__=='__main__':main()
