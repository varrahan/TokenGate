"""Bind the official board XML and actual Vivado selection to known pin scope."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    fetched=read(root/'build/validation/scu35-board-definition.json')
    assert fetched['key']=='8b040ee6fe1a7ec8' and fetched['upstream_commit']=='29bbdfd89b7048cac72bf971bcd4b18f6ca50c5a'
    folder=root/'FPGA/boards/scu35/1.0'
    for name,record in fetched['files'].items():
        p=folder/name;data=p.read_bytes();assert sha(p)==record['sha256']
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==record['git_blob_sha1']
    board=ET.parse(folder/'board.xml').getroot();fpga=board.find('./components/component[@name="part0"]')
    assert board.attrib['name']=='scu35' and fpga.attrib['part_name']==fetched['device']
    assert fpga.attrib['pin_map_file']=='part0_pins.xml' and board.attrib['preset_file']=='preset.xml'
    pins=ET.parse(folder/'part0_pins.xml').findall('.//pin')
    assert len(pins)==64 and len({p.attrib['name'] for p in pins})==64
    byname={p.attrib['name']:p.attrib for p in pins}
    clock=fpga.find('./interfaces/interface[@name="sys_diff_clock"]')
    assert clock.find('./parameters/parameter[@name="frequency"]').attrib['value']=='100000000'
    assert byname['SYSCLK_P']['loc']=='F23' and byname['SYSCLK_N']['loc']=='E23'
    assert byname['SYSCLK_P']['iostandard']==byname['SYSCLK_N']['iostandard']=='LVDS'
    interfaces=[i.attrib['name'] for i in fpga.findall('./interfaces/interface')]
    assert len(interfaces)==19 and not any('hyper' in n.lower() for n in interfaces)
    assert not any('hyper' in n.lower() for n in byname)
    assert [n for n in interfaces if 'hsio' in n.lower()]==['iic_hsio_main']
    log_path=root/'build/validation/scu35-board-vivado-validation.log';log=log_path.read_text()
    assert log.count('SCU35_BOARD_DEFINITION_VALIDATION_PASS board=xilinx.com:scu35:part0:1.0 part=xcsu35p-sbvb625-2-e')==1
    assert not re.search(r'^\s*(?:ERROR|CRITICAL WARNING):',log,re.M)
    warnings=re.findall(r'^WARNING: (.+)$',log,re.M)
    assert len(warnings)==1 and warnings[0].startswith('[Board 49-151]')
    tsv=root/'build/validation/scu35-board-vivado/board-validation.tsv'
    values=dict(line.split('\t',1) for line in tsv.read_text().splitlines())
    assert values['BOARD_PART']==fetched['board_part'] and values['PART']==fetched['device']
    assert Path(values['REPOSITORY']).resolve()==(root/'FPGA/boards').resolve()
    assert values['ORIGINAL_PROJECTS_MODIFIED']==values['PHYSICAL_HARDWARE_AVAILABLE']=='0'
    properties_path=root/'build/validation/scu35-board-vivado/board-properties.rpt'
    properties={}
    for line in properties_path.read_text().splitlines()[1:]:
        fields=line.split(None,3)
        if len(fields)==4:properties[fields[0]]=fields[3]
    assert Path(properties['FILE_NAME']).resolve()==(folder/'board.xml').resolve()
    assert properties['PART_NAME']==fetched['device'] and properties['NAME']==fetched['board_part']
    result=dict(phase='official_scu35_board_definition_vivado_selection_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        source_fetch_audit_key=fetched['key'],upstream_commit=fetched['upstream_commit'],board_part=fetched['board_part'],device=fetched['device'],
        system_clock_hz=100000000,system_clock_p=byname['SYSCLK_P'],system_clock_n=byname['SYSCLK_N'],
        declared_board_interfaces=interfaces,declared_board_pins=64,actual_vivado_board_assignment_verified=True,
        actual_vivado_pinned_file_path_verified=True,
        retained_vivado_warning=warnings[0],
        hyperram_data_pins_in_board_store_definition=False,hsio_data_pins_in_board_store_definition=False,
        complete_master_xdc_still_required=True,physical_hardware_available=False,
        target_validation_scope='Simulation, synthesis and implementation; physical board bring-up is unavailable per user',
        package_phy_timing_verified=False,physical_board_bringup_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p) for p in
            [log_path,tsv,root/'build/validation/scu35-board-vivado/board-properties.rpt',
             root/'scripts/validate_scu35_board_definition.tcl',root/'build/validation/scu35-board-definition.json']+
            [folder/n for n in fetched['files']]},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/scu35-board-verified-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in(evidence/'audit.json',root/'build/validation/scu35-board-verified.json'):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','key','system_clock_hz','complete_master_xdc_still_required')}))


if __name__=='__main__':main()
