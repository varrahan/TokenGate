"""Audit actual combined Tokenizer timing/area, preserving failures and CDC warnings."""
import argparse
from collections import Counter,defaultdict
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
from verify_two_fpga_application import closure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.run)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text());artifacts=set()
    launch_path=root/'build/validation'/(args.run+'-launch.json');launch=read(launch_path)
    assert launch['phase']=='native_process_completed'and launch['exit_code']==0
    tested=root/'build/validation'/launch['simulation'];simulation=read(tested/'report.json')
    assert simulation['inputs_sha256']==launch['input_sha256']
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.run
    frozen=folder/'sources';provenance=read(folder/'source-provenance.json')
    for name,record in provenance['files'].items():
        assert sha(frozen/name)==record['sha256'];artifacts.add(frozen/name)
        if name.startswith('rtl/'):assert simulation['inputs_sha256'][name]==record['sha256']
    dependencies=closure('tokenizer_hyperram_subsystem',frozen)
    assert {'tokenizer_fpga_memory_subsystem','tokenizer_fpga_application','bpe_tokenizer_engine',
        'detokenizer_engine','inverse_tokenizer_partition','external_memory_fabric','external_memory_arbiter',
        'external_memory_cache','programmable_table_ram','axi_hyperram_async_controller','axi_hyperram_bridge',
        'hyperram_clock_bridge','hyperram_word_backend','hyperram_transaction_engine','hyperram_startup',
        'cdc_packet_fifo','hyperram_shared_domain_reset'}<=dependencies.keys()
    assert not {'utf8_serialized_chunk','proto_json_serializer','http2_frame_reader'}&dependencies.keys()
    assert len(dependencies)==31 and len(set(dependencies.values()))==30
    with tempfile.TemporaryDirectory(prefix='th-',dir=root/'build')as temporary:
        replay=Path(temporary)
        assert replay.resolve().is_relative_to((root/'build').resolve())
        for name in('generate_tokenizer_hyperram_timing_harness','generate_hyperram_cdc_timing_harness'):
            source=root/'tools'/(name+'.py');target=replay/'tools'/source.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);artifacts.add(source)
        target=replay/'build/validation'/launch['simulation']/'sources/rtl/tokenizer_hyperram_subsystem.v'
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((frozen/'rtl/tokenizer_hyperram_subsystem.v').read_bytes())
        subprocess.run([sys.executable,str(replay/'tools/generate_tokenizer_hyperram_timing_harness.py'),
            '--simulation',launch['simulation']],check=True,capture_output=True)
        assert sha(replay/'build/tokenizer-hyperram/timing_harness.v')==sha(frozen/'timing_harness.v')
        replayed_harness_metadata=read(replay/'build/tokenizer-hyperram/generation.json')
        assert replayed_harness_metadata['source_sha256']==sha(frozen/'rtl/tokenizer_hyperram_subsystem.v')
    log=root/'build'/(args.run+'.log');text=log.read_text();artifacts.add(log)
    assert 'TOKENIZER_HYPERRAM_ROUTED APP_PERIOD_NS=4.000 MEM_PERIOD_NS=5.000 PACKAGE_TIMING_EXCLUDED=1 PHYSICAL_DDR_PHY_PRESENT=0'in text
    assert 'route_design completed successfully'in text and 'ERROR:'not in text and 'Found timing loop'not in text
    with ZipFile(folder/'routed.dcp')as archive:xml=ET.fromstring(archive.read('dcp.xml'))
    fields={node.tag:node.attrib.get('Name')for node in xml}
    assert fields['Part']=='xcsu35p-sbvb625-2-e'and fields['Top']=='tokenizer_hyperram_timing_harness'
    timing=(folder/'routed_timing.rpt').read_text()
    row=re.search(r'^\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s*$',timing,re.M);assert row
    measured=dict(setup_slack_ns=float(row[1]),hold_slack_ns=float(row[5]),pulse_width_slack_ns=float(row[9]),
        setup_failing_endpoints=int(row[3]),hold_failing_endpoints=int(row[7]),pulse_failing_endpoints=int(row[11]))
    timing_met=all(measured[key]>=0 for key in('setup_slack_ns','hold_slack_ns','pulse_width_slack_ns'))
    assert timing_met==('All user specified timing constraints are met.'in timing)
    unconstrained={key:int(re.search(r'checking '+key+r' \((\d+)\)',timing)[1])for key in
        ('no_clock','constant_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops')}
    area=(folder/'routed_utilization.rpt').read_text()
    def resources(instance):
        line=next(line for line in area.splitlines()if re.search(r'\|\s*'+re.escape(instance)+r'\s*\|',line))
        cells=[cell.strip()for cell in line.split('|')[1:-1]]
        return dict(luts=int(cells[2]),lutram=int(cells[4]),registers=int(cells[6]),bram36=int(cells[7]),bram18=int(cells[8]),uram=int(cells[9]),dsp=int(cells[10]))
    core=resources('core');total=resources(fields['Top'])
    assert core['bram36']+core['bram18']/2>=1 and core['uram']==0
    fit=core['luts']<=16320 and core['registers']<=32640 and core['bram36']+core['bram18']/2<=48 and core['dsp']<=48
    counts={};groups=defaultdict(Counter);critical=[];source=destination=None
    for line in(folder/'routed_cdc.rpt').read_text().splitlines():
        match=re.fullmatch(r'(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+(.+)',line.strip())
        if match:counts[match[1]]=dict(severity=match[2],count=int(match[3]),description=match[4])
        if line.startswith('Source Clock: '):source=line.split(': ',1)[1]
        if line.startswith('Destination Clock: '):destination=line.split(': ',1)[1]
        row_cdc=re.match(r'^\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+',line)
        if row_cdc:
            groups[source+' -> '+destination][row_cdc[1]]+=1
            if row_cdc[2]=='Critical':critical.append(dict(code=row_cdc[1],source_clock=source,destination_clock=destination,source=line.split()[-2],destination=line.split()[-1]))
    script=(frozen/'scripts/implement_tokenizer_hyperram.tcl').read_text()
    assert script.count('set_false_path')==2 and 'set_clock_groups'not in script and 'create_waiver'not in script
    exceptions=(folder/'routed_exceptions.rpt').read_text()
    pointer_delays=[float(match[1])for line in exceptions.splitlines()if 'src_gray_ff_reg*'in line and(match:=re.search(r'max_dpo=([\d.]+)',line))]
    data_delays=[float(match[1])for line in exceptions.splitlines()if 'all_fanout'in line and(match:=re.search(r'max_dpo=([\d.]+)',line))]
    skew_rows=re.findall(r'^\s*(?:Slow|Fast)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s*$',(folder/'routed_bus_skew.rpt').read_text(),re.M)
    skew=[dict(requirement_ns=float(a),actual_ns=float(b),slack_ns=float(c))for a,b,c in skew_rows]
    assert len(pointer_delays)==len(skew)==8 and len(data_delays)==4
    route=(folder/'route_status.rpt').read_text()
    errors=int(re.search(r'nets with routing errors\.+\s*:\s*(\d+)',route)[1])
    routable=int(re.search(r'# of routable nets\.+\s*:\s*(\d+)',route)[1]);routed=int(re.search(r'# of fully routed nets\.+\s*:\s*(\d+)',route)[1])
    assert errors==0 and routable==routed
    drc=(folder/'routed_drc.rpt').read_text()
    drc_rows=re.findall(r'^\|\s*([\w-]+)\s*\|\s*(Warning|Error|Critical Warning|Advisory)\s*\|[^\n]*?\|\s*(\d+)\s*\|',drc,re.M)
    checks=[dict(rule=rule,severity=severity,checks=int(number))for rule,severity,number in drc_rows]
    assert sum(check['checks']for check in checks)==int(re.search(r'Checks found:\s*(\d+)',drc)[1])
    for path in folder.iterdir():
        if path.is_file()and path.suffix in('.json','.rpt','.dcp'):artifacts.add(path)
    artifacts.update((launch_path,Path(__file__)))
    result=dict(phase='combined_tokenizer_hyperram_native_findings_recorded',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.run,simulation=launch['simulation'],simulation_state_at_native_audit=simulation['phase'],
        functional_simulation_passed=simulation.get('passed',False),part=fields['Part'],core_resources=core,resource_fit=fit,
        timing_neighbor_registers=total['registers']-core['registers'],timing_met=timing_met,**measured,unconstrained=unconstrained,
        exact_modules=list(dependencies),exact_rtl_files=30,source_provenance=provenance,harness_replay_verified=True,
        replayed_harness_metadata=replayed_harness_metadata,
        cdc_counts=counts,clock_pair_counts={key:dict(value)for key,value in groups.items()},critical_cdc_findings=critical,
        vendor_gray_pointer_max_delays_ns=pointer_delays,vendor_fifo_data_max_delays_ns=data_delays,
        vendor_bus_skew_summary=skew,vendor_bus_skew_met=all(row['slack_ns']>=0 for row in skew),
        fully_routed_nets=routed,routing_errors=0,reported_drc_checks=checks,
        actual_tokenizer_cache_controller_instantiated=True,external_whole_rpc_image_grant_implementation_verified=False,
        package_timing_verified=False,pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,
        pcie_verified=False,physical_link_verified=False,formal_cdc_signoff_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    output=root/'build/validation/tokenizer-hyperram-native.json';output.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/tokenizer-hyperram-native-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    for name,digest in result['artifacts_sha256'].items():
        if name.startswith('tools/')or name=='build/tokenizer-hyperram/generation.json':
            target=evidence/name;assert target.resolve().is_relative_to(evidence.resolve())
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():assert sha(target)==digest
            else:target.write_bytes((root/name).read_bytes())
    shutil.copy2(output,evidence/'verified.json');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    print(json.dumps({key:result[key]for key in('phase','key','core_resources','resource_fit','setup_slack_ns','hold_slack_ns','cdc_counts')}))


if __name__=='__main__':main()
