"""Review every combined-design CDC/DRC warning without adding waivers."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from generate_hyperram_cdc_timing_harness import ports


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    audits=list((root/'build/validation/tokenizer-hyperram-native-evidence').glob('*/verified.json'))
    candidates=[(path,json.loads(path.read_text()))for path in audits]
    candidates=[(path,record)for path,record in candidates if record['run']==args.run]
    assert candidates,'Native findings must be audited first'
    native_path,native=max(candidates,key=lambda item:item[1]['verified_utc'])
    for name,digest in native['artifacts_sha256'].items():
        path=root/name
        if not path.exists()or sha(path)!=digest:path=native_path.parent/name
        assert sha(path)==digest,name
    assert native['vendor_bus_skew_met']and not native['critical_cdc_findings']
    assert all(value==0 for value in native['unconstrained'].values())
    assert all(value['severity']!='Critical'for value in native['cdc_counts'].values())
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.run
    interface=ports((folder/'sources/rtl/tokenizer_hyperram_subsystem.v').read_text(),'tokenizer_hyperram_subsystem')
    input_domains={name:('memory_clk'if name.startswith('phy_')or name.endswith('_mem')else'application_clk')
                   for direction,_,name in interface if direction=='input'and name not in('app_clk','mem_clk')}
    fifo_widths={'clock_bridge/commands':607,'clock_bridge/responses':521,'reload_request':1,'reload_completion':1}
    fifo_directions={'clock_bridge/commands':('application_clk','memory_clk'),
        'clock_bridge/responses':('memory_clk','application_clk'),
        'reload_request':('application_clk','memory_clk'),'reload_completion':('memory_clk','application_clk')}
    fifo_counts=Counter();io_counts=Counter();source=destination=None;io_bits=set()
    for line in(folder/'routed_cdc.rpt').read_text().splitlines():
        if line.startswith('Source Clock: '):source=line.split(': ',1)[1]
        if line.startswith('Destination Clock: '):destination=line.split(': ',1)[1]
        match=re.match(r'^\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+',line)
        if not match or match[2]=='Info':continue
        assert match[2]=='Warning';launch,capture=line.split()[-2:]
        if match[1]=='CDC-15':
            owners=[name for name in fifo_widths if launch.startswith('core/memory/'+name+'/storage/')
                    and capture.startswith('core/memory/'+name+'/storage/')]
            assert len(owners)==1,line
            assert (source,destination)==fifo_directions[owners[0]]
            assert 'xpm_fifo_base_inst/'in launch and'xpm_fifo_base_inst/'in capture
            assert '/gen_sdpram.xpm_memory_base_inst/'in launch and'/gen_sdpram.xpm_memory_base_inst/'in capture
            assert '.doutb_reg_reg['in capture and'Max Delay Datapath Only'in line
            fifo_counts[owners[0]]+=1
        elif match[1]=='CDC-26':
            assert source=='input port clock'
            port=re.fullmatch(r'(\w+)(\[\d+\])?',launch);assert port,line
            assert input_domains[port[1]]==destination,line
            assert capture=='timing_'+port[1]+'_reg'+(port[2]or'')+'/D',line
            assert launch not in io_bits;io_bits.add(launch);io_counts[destination]+=1
        else:raise AssertionError('Unclassified CDC warning: '+line)
    assert dict(fifo_counts)==fifo_widths
    assert sum(fifo_counts.values())==native['cdc_counts']['CDC-15']['count']==1130
    assert sum(io_counts.values())==native['cdc_counts']['CDC-26']['count']
    assert len(native['vendor_bus_skew_summary'])==len(native['vendor_gray_pointer_max_delays_ns'])==8
    assert len(native['vendor_fifo_data_max_delays_ns'])==4
    script=(folder/'sources/scripts/implement_tokenizer_hyperram.tcl').read_text()
    assert script.count('set_false_path')==2 and 'set_clock_groups'not in script and 'create_waiver'not in script
    drc=(folder/'routed_drc.rpt').read_text()
    checks=native['reported_drc_checks'];assert {row['rule']for row in checks}<={'DPOP-3','DPOP-4','RTSTAT-10'}
    assert all(row['severity']=='Warning'for row in checks)
    for block in re.split(r'\n(?=[A-Z][A-Z0-9-]+#\d+ Warning\n)',drc)[1:]:
        if block.startswith(('DPOP-3#','DPOP-4#')):
            assert 'DSP core/application/application/tokenizer/ranks/hash_pair_return'in block
        else:assert block.startswith('RTSTAT-10#')
    no_load=int(re.search(r'(\d+) net\(s\) have no routable loads\.',drc)[1])
    result=dict(phase='combined_tokenizer_hyperram_cdc_warning_structure_reviewed',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.run,native_audit_key=native['key'],critical_cdc_findings=0,all_remaining_warnings_classified=True,
        actual_vendor_fifo_warning_bits=dict(fifo_counts),external_input_neighbor_warnings=dict(io_counts),
        external_input_bits_individually_matched_to_registered_ports=True,
        minimum_gray_bus_skew_slack_ns=min(row['slack_ns']for row in native['vendor_bus_skew_summary']),
        reported_drc_checks=checks,unloaded_external_output_nets=no_load,
        dsp_pipeline_advisories_scope='existing rank hash-pair multipliers',
        custom_waivers_added=0,custom_internal_false_paths_added=0,native_timing_verified=native['timing_met'],
        analog_metastability_verified=False,formal_cdc_signoff_verified=False,package_timing_verified=False,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in(native_path,folder/'routed_cdc.rpt',
            folder/'routed_bus_skew.rpt',folder/'routed_exceptions.rpt',folder/'routed_drc.rpt',
            folder/'sources/timing_harness.v',folder/'sources/rtl/tokenizer_hyperram_subsystem.v',Path(__file__))})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/tokenizer-hyperram-cdc-review.json';target.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/tokenizer-hyperram-cdc-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(target,evidence/'verified.json')
    archive=evidence/'tools'/Path(__file__).name;archive.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(Path(__file__),archive)
    print(json.dumps({key:result[key]for key in('phase','key','native_timing_verified','actual_vendor_fifo_warning_bits','external_input_neighbor_warnings')}))


if __name__=='__main__':main()
