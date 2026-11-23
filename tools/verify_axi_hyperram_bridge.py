"""Bind the buffered AXI contract checks to executed RTL and full image bytes."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports/axi_hyperram_buffered_axi_frontend_duplex';source=archive/'execution-sources'
    read=lambda n:json.loads((archive/n).read_text())
    inputs,report,state,accepted=(read(n)for n in('inputs.json','report.json','snapshot.json','acceptance.json'))
    assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert len(inputs)==4
    for n,h in inputs.items():assert sha(source/n)==sha(root/n)==h,n
    xml=ET.parse(archive/'results.xml');assert len(xml.findall('.//testcase'))==1
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert xml.find('.//testcase').attrib['name']=='buffered_axi_transactions_preserve_data_and_errors'
    assert [accepted[n]for n in('axi_reads','axi_writes','actual_backend_commands','rejected_write_cases','backend_errors','simultaneous_read_write_rounds')]==[203,121,309,7,2,33]
    assert accepted['axi_reads']+accepted['axi_writes']-len(accepted['rejected_read_cases'])-accepted['rejected_write_cases']==accepted['actual_backend_commands']
    assert len(accepted['rejected_read_cases'])==8 and accepted['held_command_cycles']>=37
    assert accepted['initial_image_sha256']=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    assert accepted['initial_image_sha256']==inputs['build/scu35/image/external_memory.bin']
    for n in ('independently_stalled_channels','write_data_before_address_verified','held_read_and_write_results_verified',
        'full_8mib_image_loaded','partial_strobes_and_zero_strobes_verified','malformed_bursts_never_reach_backend'):
        assert accepted[n]
    for n in('physical_hyperbus_phy_verified','axi_cdc_verified','native_timing_verified','full_system_complete'):assert accepted[n]is False
    log=root/'build/validation/axi-hyperram-structural.log';text=log.read_text()
    assert 'Found and reported 0 problems.' in text and 'ERROR:'not in text
    assert 'read_verilog rtl/axi_hyperram_bridge.v; hierarchy -top axi_hyperram_bridge; proc; check -assert; stat' in text
    result=dict(phase='buffered_axi_hyperram_frontend_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,inputs_sha256=inputs,archive_files_sha256={p.name:sha(p)for p in archive.iterdir()if p.is_file()},
        structural_check_log_sha256=sha(log),actual_full_image_byte_scoreboard_verified=True,
        same_clock_axi_frontend_only=True,physical_hyperbus_phy_verified=False,axi_cdc_verified=False,
        native_timing_verified=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/axi-hyperram-frontend-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in(Path(__file__),log,source/'rtl/axi_hyperram_bridge.v',source/'sim/cocotb/test_axi_hyperram_bridge.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/axi-hyperram-frontend.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,axi_transactions=324,backend_commands=309)))


if __name__=='__main__':main()
