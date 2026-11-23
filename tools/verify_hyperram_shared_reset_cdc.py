"""Classify all routed CDC warnings without suppressing or waiving them."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    native_path=root/'build/validation/hyperram-shared-reset-implementation.json'
    native=json.loads(native_path.read_text())
    functional_path=root/'build/validation/hyperram-shared-reset.json'
    functional=json.loads(functional_path.read_text())
    assert native['functional_audit_key']==functional['key']=='07002b9a4dd73fb7'
    for name,digest in native['artifacts_sha256'].items():assert sha(source_path(root, name))==digest,name
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/native['run']
    assert native['timing_met']and native['vendor_bus_skew_met']
    assert all(value==0 for value in native['unconstrained'].values())
    assert not native['critical_cdc_findings']
    assert all(value['severity']!='Critical'for value in native['cdc_counts'].values())
    fifo_widths={'clock_bridge/commands':607,'clock_bridge/responses':521,
                 'reload_request':1,'reload_completion':1}
    fifo_counts=Counter();io_counts=Counter();source=destination=None
    for line in(folder/'routed_cdc.rpt').read_text().splitlines():
        if line.startswith('Source Clock: '):source=line.split(': ',1)[1]
        if line.startswith('Destination Clock: '):destination=line.split(': ',1)[1]
        match=re.match(r'^\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+',line)
        if not match or match[2]=='Info':continue
        assert match[2]=='Warning'
        fields=line.split();launch,capture=fields[-2:]
        if match[1]=='CDC-15':
            assert source in('application_clk','memory_clk')and destination in('application_clk','memory_clk')and source!=destination
            owners=[name for name in fifo_widths if launch.startswith('core/'+name+'/storage/')and capture.startswith('core/'+name+'/storage/')]
            assert len(owners)==1,line
            assert 'xpm_fifo_base_inst/'in launch and 'xpm_fifo_base_inst/'in capture
            assert '/gen_sdpram.xpm_memory_base_inst/'in launch and '/gen_sdpram.xpm_memory_base_inst/'in capture
            assert '.doutb_reg_reg['in capture and 'Max Delay Datapath Only'in line
            fifo_counts[owners[0]]+=1
        elif match[1]=='CDC-26':
            assert source=='input port clock'and destination in('application_clk','memory_clk')
            assert not launch.startswith('core/')and capture.startswith('timing_')and capture.endswith('/D')
            io_counts[destination]+=1
        else:raise AssertionError('Unclassified CDC warning: '+line)
    assert dict(fifo_counts)==fifo_widths
    assert dict(io_counts)==dict(application_clk=153,memory_clk=21)
    assert len(native['vendor_bus_skew_summary'])==8
    assert len(native['vendor_gray_pointer_max_delays_ns'])==8
    assert len(native['vendor_fifo_data_max_delays_ns'])==4
    assert min(row['slack_ns']for row in native['vendor_bus_skew_summary'])==3.056
    script=(folder/'sources/scripts/implement_hyperram_shared_reset.tcl').read_text()
    assert script.count('set_false_path')==2 and 'set_clock_groups'not in script and 'create_waiver'not in script
    drc=(folder/'routed_drc.rpt').read_text()
    assert 'Checks found: 1'in drc and 'RTSTAT-10#1 Warning'in drc
    assert '178 net(s) have no routable loads.'in drc
    result=dict(phase='shared_reset_routed_cdc_warning_structure_reviewed',verified_utc=datetime.now(timezone.utc).isoformat(),
        native_audit_key=native['key'],functional_audit_key=functional['key'],critical_cdc_findings=0,
        all_1130_internal_warning_bits_inside_actual_vendor_fifo_ram=True,fifo_warning_bits=dict(fifo_counts),
        external_input_neighbor_warnings=dict(io_counts),vendor_gray_bus_skew_constraints=8,
        vendor_gray_pointer_max_delay_constraints=8,vendor_fifo_data_max_delay_constraints=4,
        minimum_gray_bus_skew_slack_ns=3.056,custom_waivers_added=0,custom_internal_false_paths_added=0,
        reported_drc_warnings=[dict(code='RTSTAT-10',description='No routable loads',nets=178,
                                   context='Isolated harness external outputs, including reset/status and PHY word controls')],
        native_timing_verified=True,cdc_structure_review_verified=True,
        analog_metastability_verified=False,formal_cdc_signoff_verified=False,package_timing_verified=False,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,tokenizer_instantiation_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in(native_path,functional_path,folder/'routed_cdc.rpt',
            folder/'routed_bus_skew.rpt',folder/'routed_exceptions.rpt',folder/'routed_drc.rpt',Path(__file__))})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    output=root/'build/validation/hyperram-shared-reset-cdc-review.json';output.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/hyperram-shared-reset-cdc-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(output,evidence/'verified.json');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    print(json.dumps({key:result[key]for key in('phase','key','critical_cdc_findings','fifo_warning_bits','external_input_neighbor_warnings')}))


if __name__=='__main__':main()
