"""Record actual assembly routing/timing/CDC, retaining every open finding."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse
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

from rtl_paths import source_path, source_relative


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shared-reset',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    name='hyperram_async_250_200_'+('shared_reset'if args.shared_reset else'qualified_reset')
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/name
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    launch=read(root/'build/validation'/(name+'-launch.json'))
    assert launch['phase']=='native_process_completed'and launch['exit_code']==0
    functional=read(root/'build/validation'/('hyperram-shared-reset.json'if args.shared_reset else'hyperram-async-native.json'))
    if args.shared_reset:
        assert functional['parent_audit_key']==launch['parent_functional_audit_key']
        assert functional['inputs_sha256']==launch['inputs_sha256']
    else:assert functional['key']==launch['functional_audit_key']
    provenance=read(folder/'source-provenance.json');artifacts=set()
    for path,record in provenance['files'].items():
        frozen=folder/'sources'/path;assert sha(frozen)==record['sha256'];artifacts.add(frozen)
        if path.startswith('rtl/'):
            assert record['sha256']==functional['inputs_sha256'][path]
    with tempfile.TemporaryDirectory(prefix='async-timing-harness-replay-')as temp:
        replay=Path(temp)
        for relative in ('tools/generate_hyperram_async_timing_harness.py','tools/generate_hyperram_cdc_timing_harness.py',
                         'rtl/axi_hyperram_async_controller.v', 'tools/rtl_paths.py'):
            target=replay/relative;target.parent.mkdir(parents=True,exist_ok=True)
            source=folder/'sources'/relative if relative.startswith('rtl/')else source_path(root, relative)
            shutil.copy2(source,target);artifacts.add(source)
        subprocess.run([sys.executable,str(replay/'tools/generate_hyperram_async_timing_harness.py')],check=True,capture_output=True)
        assert sha(replay/'build/hyperram-async/timing_harness.v')==sha(folder/'sources/timing_harness.v')
    with ZipFile(folder/'routed.dcp')as archive:
        xml=ET.fromstring(archive.read('dcp.xml'))
    fields={node.tag:node.attrib.get('Name')for node in xml}
    assert fields['Part']=='xcsu35p-sbvb625-2-e'
    assert fields['Top']=='axi_hyperram_async_controller_timing_harness'
    log=root/'build'/(name+'.log');text=log.read_text();artifacts.add(log)
    assert 'HYPERRAM_ASYNC_ASSEMBLY_ROUTED APP_PERIOD_NS=4.000 MEM_PERIOD_NS=5.000 PACKAGE_TIMING_EXCLUDED=1 PHYSICAL_DDR_PHY_PRESENT=0'in text
    assert 'route_design completed successfully'in text and 'ERROR:'not in text
    timing=(folder/'routed_timing.rpt').read_text()
    row=re.search(r'^\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s*$',timing,re.M)
    assert row
    values=dict(setup_slack_ns=float(row[1]),hold_slack_ns=float(row[5]),pulse_width_slack_ns=float(row[9]),
                setup_failing_endpoints=int(row[3]),hold_failing_endpoints=int(row[7]),pulse_failing_endpoints=int(row[11]))
    timing_met=all(values[key]>=0 for key in('setup_slack_ns','hold_slack_ns','pulse_width_slack_ns'))
    assert timing_met==('All user specified timing constraints are met.'in timing)
    unconstrained={key:int(re.search(r'checking '+key+r' \((\d+)\)',timing)[1])for key in
        ('no_clock','constant_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops')}
    counts={};groups=defaultdict(Counter);critical=[];source=destination=None
    cdc=(folder/'routed_cdc.rpt').read_text()
    for line in cdc.splitlines():
        match=re.fullmatch(r'(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+(.+)',line.strip())
        if match:counts[match[1]]=dict(severity=match[2],count=int(match[3]),description=match[4])
        if line.startswith('Source Clock: '):source=line.split(': ',1)[1]
        if line.startswith('Destination Clock: '):destination=line.split(': ',1)[1]
        row_cdc=re.match(r'^\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+',line)
        if row_cdc:
            groups[source+' -> '+destination][row_cdc[1]]+=1
            if row_cdc[2]=='Critical':
                parts=line.split();critical.append(dict(code=row_cdc[1],source_clock=source,destination_clock=destination,
                    source=parts[-2],destination=parts[-1]))
    area=(folder/'routed_utilization.rpt').read_text()
    def resources(instance):
        line=next(line for line in area.splitlines()if re.search(r'\|\s*'+re.escape(instance)+r'\s*\|',line))
        columns=[v.strip()for v in line.split('|')[1:-1]]
        return dict(luts=int(columns[2]),lutram=int(columns[4]),registers=int(columns[6]),
                    bram36=int(columns[7]),bram18=int(columns[8]),uram=int(columns[9]),dsp=int(columns[10]))
    core=resources('core');total=resources(fields['Top'])
    route=(folder/'route_status.rpt').read_text()
    routing_errors=int(re.search(r'nets with routing errors\.+\s*:\s*(\d+)',route)[1])
    routable=int(re.search(r'# of routable nets\.+\s*:\s*(\d+)',route)[1])
    routed=int(re.search(r'# of fully routed nets\.+\s*:\s*(\d+)',route)[1])
    assert routing_errors==0 and routable==routed
    script=(folder/'sources/scripts'/('implement_hyperram_shared_reset.tcl'if args.shared_reset else'implement_hyperram_async_controller.tcl')).read_text()
    assert script.count('set_false_path')==2 and 'set_clock_groups'not in script and 'create_waiver'not in script
    exceptions=(folder/'routed_exceptions.rpt').read_text()
    pointer_limits=[float(match[1])for line in exceptions.splitlines()
        if 'src_gray_ff_reg*'in line and(match:=re.search(r'max_dpo=([\d.]+)',line))]
    data_limits=[float(match[1])for line in exceptions.splitlines()
        if 'all_fanout'in line and(match:=re.search(r'max_dpo=([\d.]+)',line))]
    skew=(folder/'routed_bus_skew.rpt').read_text()
    # Only the report-summary table contains a Slow/Fast row with three numbers.
    skew_rows=re.findall(r'^\s*(?:Slow|Fast)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s*$',skew,re.M)
    skew_summary=[dict(requirement_ns=float(a),actual_ns=float(b),slack_ns=float(c))for a,b,c in skew_rows]
    assert len(pointer_limits)==8 and len(data_limits)==4 and len(skew_summary)==8,'Missing vendor FIFO timing constraints'
    for path in folder.iterdir():
        if path.is_file()and path.suffix in('.rpt','.dcp','.json'):artifacts.add(path)
    artifacts.update((root/'build/validation'/('hyperram-shared-reset.json'if args.shared_reset else'hyperram-async-native.json'),
        root/'build/validation'/(name+'-launch.json'),
        (root/'build/experiments/hyperram-shared-reset'if args.shared_reset else root)/'build/hyperram-async/timing-harness-generation.json',Path(__file__)))
    result=dict(phase='hyperram_async_assembly_native_findings_recorded',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=name,part=fields['Part'],functional_audit_key=functional['key'],source_provenance=provenance,
        generator_replay_verified=True,core_resources=core,timing_neighbor_registers=total['registers']-core['registers'],
        timing_met=timing_met,**values,unconstrained=unconstrained,cdc_counts=counts,
        clock_pair_counts={key:dict(value)for key,value in groups.items()},critical_cdc_findings=critical,
        vendor_gray_pointer_max_delays_ns=pointer_limits,vendor_fifo_data_max_delays_ns=data_limits,vendor_bus_skew_summary=skew_summary,
        vendor_bus_skew_met=all(row['slack_ns']>=0 for row in skew_summary),fully_routed_nets=routed,routing_errors=0,
        cdc_signoff_verified=False,primary_fifo_modified=False,package_timing_verified=False,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,tokenizer_instantiation_verified=False,
        full_system_complete=False,artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation'/('hyperram-shared-reset-implementation.json'if args.shared_reset else'hyperram-async-implementation.json');target.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/hyperram-async-implementation-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(target,evidence/'verified.json');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    print(json.dumps({key:result[key]for key in('phase','key','core_resources','setup_slack_ns','hold_slack_ns','cdc_counts','vendor_bus_skew_met')}))


if __name__=='__main__':main()
