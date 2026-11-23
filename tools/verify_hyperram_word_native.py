"""Audit SCU35 area and internal 200 MHz timing for the tested word controller."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e/hyperram_word_controller_200_quoted'
    frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
    for name,record in provenance['files'].items():assert sha(frozen/name)==record['sha256']
    functional=json.loads((root/'build/validation/hyperram-startup.json').read_text())
    for name in ('axi_hyperram_bridge','hyperram_transaction_engine','hyperram_startup','axi_hyperram_controller'):
        path='rtl/'+name+'.v';digest=sha(root/path)
        assert digest==provenance['files'][path]['sha256']
        assert all(c['inputs_sha256'][path]==digest for c in functional['cases'].values())
    script=frozen/'scripts/implement_hyperram_word_controller.tcl'
    assert sha(script)==sha(root/'scripts/implement_hyperram_word_controller.tcl')
    assert script.read_text().count('set_false_path')==2
    assert 'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]'in script.read_text()
    assert 'set_false_path -to [all_outputs]'in script.read_text()
    assert (frozen/'timing.xdc').read_text().strip()=='create_clock -name memory_word_clk -period 5.000 [get_ports clk]'
    with tempfile.TemporaryDirectory(prefix='hyperram-native-harness-')as temp:
        output=Path(temp)/'harness.v'
        subprocess.run([sys.executable,str(root/'tools/generate_parser_timing_harness.py'),
            '--source',str(frozen/'rtl/axi_hyperram_controller.v'),'--top','axi_hyperram_controller',
            '--harness-top','axi_hyperram_controller_timing_harness','--output',str(output)],
            check=True,capture_output=True,text=True)
        assert sha(output)==sha(frozen/'timing_harness.v')
    log=root/'build/hyperram_word_controller_200_quoted.log';text=log.read_text()
    assert 'HYPERRAM_WORD_CONTROLLER_ROUTED CLOCK_PERIOD_NS=5.000 PHYSICAL_DDR_PHY_PRESENT=0 PACKAGE_TIMING_EXCLUDED=1'in text
    assert 'route_design completed successfully'in text and 'ERROR:'not in text
    assert '0 Critical Warnings and 0 Errors encountered.'in text
    assert 'Parameter MEMORY_CLOCK_HZ bound to: 200000000'in text
    assert 'Parameter CONFIG_LATENCY bound to: 7'in text and 'Parameter FIXED_LATENCY bound to: 1'in text
    with ZipFile(folder/'routed.dcp')as checkpoint:
        metadata=ET.fromstring(checkpoint.read('dcp.xml'))
    fields={node.tag:node.attrib.get('Name')for node in metadata}
    assert fields['Part']=='xcsu35p-sbvb625-2-e'and fields['Top']=='axi_hyperram_controller_timing_harness'
    timing=(folder/'routed_timing.rpt').read_text()
    row=re.search(r'^\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s*$',timing,re.M)
    assert row
    setup,hold,pulse=(float(row[i])for i in(1,5,9))
    assert setup>=0 and hold>=0 and pulse>=0 and all(int(row[i])==0 for i in(3,7,11))
    for name in('no_clock','constant_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops'):
        assert re.search(r'checking '+name+r' \(0\)',timing)
    assert re.search(r'^memory_word_clk\s+\{0.000 2.500\}\s+5.000\s+200.000',timing,re.M)
    assert 'All user specified timing constraints are met.'in timing
    assert 'There are 173 input ports with no input delay but user has a false path constraint.'in timing
    assert 'There are 164 ports with no output delay but user has a false path constraint'in timing
    route=(folder/'route_status.rpt').read_text()
    assert re.search(r'nets with routing errors\.+\s*:\s*0',route)
    routable=int(re.search(r'# of routable nets\.+\s*:\s*(\d+)',route)[1])
    fully_routed=int(re.search(r'# of fully routed nets\.+\s*:\s*(\d+)',route)[1])
    assert routable==fully_routed==3325
    assert 'Checks found: 0'in(folder/'routed_drc.rpt').read_text()
    area=(folder/'routed_utilization.rpt').read_text()
    def resources(instance):
        line=next(line for line in area.splitlines()if re.search(r'\|\s*'+re.escape(instance)+r'\s*\|',line))
        cols=[v.strip()for v in line.split('|')[1:-1]]
        return dict(luts=int(cols[2]),registers=int(cols[6]),bram36=int(cols[7]),bram18=int(cols[8]),uram=int(cols[9]),dsp=int(cols[10]))
    core=resources('core');total=resources('axi_hyperram_controller_timing_harness')
    assert core==dict(luts=1976,registers=2479,bram36=0,bram18=0,uram=0,dsp=0)
    assert total['registers']==2815 and total['registers']-core['registers']==336
    artifacts=[log,folder/'source-provenance.json',folder/'routed.dcp',folder/'routed_timing.rpt',
        folder/'routed_utilization.rpt',folder/'route_status.rpt',folder/'routed_drc.rpt',Path(__file__),
        root/'tools/generate_parser_timing_harness.py']
    result=dict(phase='hyperram_word_controller_scu35_internal_timing_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        part=fields['Part'],clock_period_ns=5,clock_frequency_mhz=200,core_resources=core,timing_neighbor_registers=336,
        setup_slack_ns=setup,hold_slack_ns=hold,pulse_width_slack_ns=pulse,failing_endpoints=0,
        route_errors=0,fully_routed_nets=fully_routed,reported_drc_violations=0,unconstrained_internal_endpoints=0,
        source_provenance=provenance,functional_audit_key=functional['key'],harness_replay_verified=True,
        package_input_false_paths=173,package_output_false_paths=164,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,package_timing_verified=False,
        application_instantiation_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in artifacts})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/hyperram-word-native-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in artifacts:
        if p.suffix!='.dcp':shutil.copy2(p,evidence/p.name)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/hyperram-word-native.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','key','core_resources','setup_slack_ns','hold_slack_ns')}))


if __name__=='__main__':main()
