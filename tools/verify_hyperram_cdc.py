"""Audit full-width packet CDC simulation without claiming physical signoff."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports/hyperram_cdc_native_xpm_synchronized_reset'
    read=lambda n:json.loads((archive/n).read_text())
    inputs,report,state,accepted=(read(n)for n in('inputs.json','report.json','snapshot.json','acceptance.json'))
    assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
    assert report['input_sha256']==inputs and len(inputs)==7
    assert report['acceptance_sha256']==sha(archive/'acceptance.json')
    for name,digest in inputs.items():
        assert sha(archive/'execution-sources'/name)==digest
        if name.startswith('vendor/'):
            macro=Path(name).stem
            installed=Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/macro/'hdl'/(macro+'.sv')
            assert sha(installed)==digest
        else:assert sha(source_path(root, name))==digest
    flags=report['compiler_flags']
    assert all(flag in flags for flag in('--assert','--bbox-unsup','-DOBSOLETE','-DONESPIN'))
    xml_text=(archive/'elaboration.xml').read_text();xml=ET.fromstring(xml_text)
    assert 'ecc_behav_logic'not in xml_text and 'deassign'not in xml_text
    parameters=[node for node in xml.findall('.//var')if node.attrib.get('origName')=='ECC_MODE']
    assert parameters
    for node in parameters:
        value=node.find('const').attrib['name']
        # String "no_ecc" at wrapper level, integer zero in the elaborated memory.
        assert value=="48'h6e6f5f656363"or re.fullmatch(r"32's?h0",value),value
    assert report['unsupported_ecc_branches_absent_from_elaborated_model']
    assert report['vendor_sva_enabled']is False and accepted['vendor_sva_enabled']is False
    profiles={'target_250_200':(2000,2500,700),'slow_memory':(2000,6500,1100),
        'slow_application':(3500,1500,350),'coincident_edges':(2500,2500,0)}
    assert set(profiles)==set(accepted['profiles'])==set(report['profiles'])
    for label,clocks in profiles.items():
        text=(archive/(label+'.log')).read_text();line=next(line for line in text.splitlines()if line.startswith('CDC_TEST_PASS '))
        values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line)}
        assert values==accepted['profiles'][label]==report['profiles'][label]
        assert tuple(values[n]for n in('app_half','mem_half','phase'))==clocks
        assert values['epochs']==4 and values['completed']>=3000
        assert values['source_holds']>=50 and values['response_holds']>=50
        assert '%Fatal:'not in text and '%Error:'not in text
    assert accepted['command_bits']==607 and accepted['response_bits']==521
    code=json.loads((root/'build/validation/hyperram-cdc-generated-code.json').read_text())
    for label,count in(('failing_fixture',0),('corrected_fixture',1)):
        record=code['records'][label];source=source_path(root, record['cpp_file'])
        assert sha(source)==record['cpp_sha256']
        assert source.read_text().count('pending_responses.pop_front()')==count==record['pending_response_pop_calls']
    assert code['records']['corrected_fixture']['binary_sha256']==report['binary_sha256']
    for flag in('analog_metastability_verified','native_cdc_constraints_verified','application_instantiation_verified',
        'pin_level_rwds_cdc_verified','full_system_complete'):assert accepted[flag]is False
    result=dict(phase='hyperram_packet_cdc_functional_simulation_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,inputs_sha256=inputs,archive_sha256={p.name:sha(p)for p in archive.iterdir()if p.is_file()},
        testbench_fixture_bug=code,verilator_version=report['simulator_version'],compiler_flags=flags,
        vendor_sources_unmodified=True,vendor_sva_enabled=False,independent_assertions_enabled=True,
        native_cdc_constraints_verified=False,native_timing_verified=False,application_instantiation_verified=False,
        pin_level_rwds_cdc_verified=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/hyperram-cdc-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in(Path(__file__),source_path(root, 'rtl/cdc_packet_fifo.v'),source_path(root, 'rtl/hyperram_clock_bridge.v'),
        root/'sim/tb_hyperram_clock_bridge.sv',root/'tools/collect_hyperram_cdc_generated_code.py'):shutil.copy2(p,evidence/p.name)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/hyperram-cdc.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],clock_profiles=4,
        completed_responses=sum(p['completed']for p in accepted['profiles'].values()))))


if __name__=='__main__':main()
