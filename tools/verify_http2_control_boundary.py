"""Bind ordered controls, real raw/HPACK integration and native fork timing."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    isolated=root/'build/wsl-reports/http2_control_events_ordered_control_initial'
    integrated=root/'build/wsl-reports/http2_controlled_hpack_ordered_hpack_bench_width'
    files={};reports={}
    for label,archive in(('isolated',isolated),('raw_hpack',integrated)):
        inputs=json.loads((archive/'inputs.json').read_text())
        report=json.loads((archive/'report.json').read_text())
        snapshot=json.loads((archive/'snapshot.json').read_text())
        assert report['phase']=='passed' and snapshot['exit_code']==0 and report['input_sha256']==inputs
        for name,digest in inputs.items():
            assert sha(archive/'execution-sources'/name)==digest
            files[Path(label)/'execution'/name]=archive/'execution-sources'/name
        for name in('inputs.json','report.json','snapshot.json','simulation.log','build.log'):
            files[Path(label)/'reports'/name]=archive/name
        reports[label]=dict(inputs=inputs,record=report,current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h])
    accepted=json.loads((isolated/'acceptance.json').read_text())
    xml=ET.parse(isolated/'results.xml')
    assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure') and not xml.findall('.//error')
    assert xml.findall('.//testcase')[0].attrib['name']=='native_semantic_events_control_before_forward'
    assert reports['isolated']['record']['acceptance_sha256']==sha(isolated/'acceptance.json')
    assert accepted['phase']=='passed' and (accepted['sent'],accepted['forwarded'],accepted['controls'],accepted['native_wire_fragments'])==(123029,123029,1415,2209)
    assert accepted['all_metadata_preserved'] and accepted['control_before_dispatch_verified']
    assert accepted['settings_ack']==2 and accepted['ping_ack']==3
    assert all(accepted[n]>0 for n in('control_stalls','forward_stalls','input_stalls'))
    files[Path('isolated/reports/acceptance.json')]=isolated/'acceptance.json'
    files[Path('isolated/reports/results.xml')]=isolated/'results.xml'
    fixture=json.loads((isolated/'execution-sources/build/http2-control-fixtures/events.json').read_text())
    assert fixture['phase']=='native_wire_payload_references_passed'
    assert all(reports['isolated']['inputs'][n]==h for n,h in fixture['inputs_sha256'].items())
    hpack=reports['raw_hpack']['record'];log=(integrated/'simulation.log').read_text()
    assert hpack['simulation_log_sha256']==sha(integrated/'simulation.log')
    counts=re.search(r'PASS: raw 512-bit HTTP/2 -> external assembly -> HPACK: (\d+) packets/(\d+) semantic events/(\d+) exact header fields/(\d+) blocks/(\d+) protocol failures/(\d+) controls/(\d+) memory fault cases',log)
    assert counts and tuple(map(int,counts.groups()))==(2212,88482,139,29,87,616,108)
    assert (hpack['flow_actions'],hpack['settings_ack'],hpack['ping_ack'],hpack['data_frame_begins'])==(1429,1,2,282)
    assert hpack['flow_stall_cycles']>0
    executed=integrated/'execution-sources'
    dependencies=closure('http2_controlled_hpack_ingress',executed)
    assert len(dependencies)==16 and {'http2_control_event_fork','http2_frame_reader','http2_payload_decoder','http2_header_dispatch','hpack_header_decoder'}<=dependencies.keys()
    production=(executed/'rtl/http2_controlled_hpack_ingress.v').read_text()
    assert '.finish_valid(payload_result_valid&&control_fork_idle)' in production
    assert 'assign idle=base_idle&&payload_idle&&dispatch_idle&&control_fork_idle;' in production
    # Recompile the frozen native generators independently and compare the
    # complete wire/semantic/header corpus, rather than trusting its manifest.
    replay_key=hashlib.sha256(''.join(reports['raw_hpack']['inputs'][n]for n in
        ('tools/generate_http2_hpack_vectors.py','tools/generate_http2_transport_vectors.py','tools/generate_http2_frame_vectors.py', 'tools/rtl_paths.py')).encode()).hexdigest()[:16]
    replay=root/'build/validation/http2-control-reference-replay'/replay_key
    if not(replay/'vectors.txt').exists():
        subprocess.run([sys.executable,str(executed/'tools/generate_http2_hpack_vectors.py'),'--output',str(replay)],check=True)
    assert sha(replay/'vectors.txt')==reports['raw_hpack']['inputs']['build/http2-controlled-hpack/vectors.txt']
    native=root/'build/implementation/xcsu35p-sbvb625-2-e/http2_control_fork_scu35_initial'
    frozen=native/'sources';provenance=json.loads((native/'source-provenance.json').read_text())
    for name,record in provenance['files'].items():
        assert sha(frozen/name)==record['sha256'] and (frozen/name).stat().st_size==record['bytes']
    rtl=frozen/'rtl/http2_control_event_fork.v'
    assert sha(rtl)==reports['isolated']['inputs']['rtl/http2_control_event_fork.v']==reports['raw_hpack']['inputs']['rtl/http2_control_event_fork.v']
    assert len(closure('http2_control_event_fork',frozen))==1
    clocks=timing(native/'routed_timing.rpt');area=resources(native/'routed_utilization.rpt')
    assert clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
    assert area==dict(luts=6,registers=166,bram36=0,bram18=0,uram=0,dsps=0)
    assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(native/'route_status.rpt').read_text())
    assert 'Checks found: 0' in (native/'routed_drc.rpt').read_text()
    implementation=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
    assert [line.strip()for line in implementation.splitlines()if line.strip().startswith('set_false_path')]==[
        'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
    native_log=root/'build/http2_control_fork_scu35_initial-implementation.log'
    assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=http2_control_event_fork PART=xcsu35p-sbvb625-2-e' in native_log.read_text()
    assert '0 Critical Warnings and 0 Errors encountered.' in native_log.read_text()
    for name in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','routed_drc.rpt','route_status.rpt'):
        files[Path('native')/name]=native/name
    for name in provenance['files']:
        if not name.startswith('rtl/')or name=='rtl/http2_control_event_fork.v':files[Path('native/sources')/name]=frozen/name
    files[Path('native/implementation.log')]=native_log
    files[Path('verification/verify_http2_control_boundary.py')]=Path(__file__)
    key=hashlib.sha256(''.join(sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/http2-control-boundary-evidence'/key
    for name,source in files.items():
        target=evidence/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source)
        else:shutil.copy2(source,target)
    result=dict(phase='raw_hpack_control_functional_and_fork_timing_met',verified_utc=datetime.now(timezone.utc).isoformat(),
        isolated_acceptance=accepted,raw_hpack_counts=dict(zip(('packets','semantic_events','header_fields','blocks','protocol_failures','control_commands','memory_faults'),map(int,counts.groups()))),
        raw_hpack_control_actions=hpack['flow_actions'],raw_hpack_control_stalls=hpack['flow_stall_cycles'],active_hpack_rtl_modules=list(dependencies),
        native_fork_resources=area,native_fork_timing=clocks,native_fork_checkpoint_sha256=sha(native/'routed.dcp'),
        full_raw_hpack_native_timing_verified=False,full_parser_application_joined=False,
        credit_ledger_verified=False,settings_ack_bookkeeping_verified=False,headers_trailers_verified=False,
        full_system_complete=False,package_paths_excluded=True,
        native_reference_reproduced=True,native_reference_sha256=sha(replay/'vectors.txt'),
        native_reference_packages={p:importlib.metadata.version(p)for p in('h2','hpack','hyperframe')},
        current_primary_differences={label:r['current_primary_differences']for label,r in reports.items()},
        verifier_sha256=sha(Path(__file__)),evidence_folder=str(evidence))
    (root/'build/validation/http2-control-boundary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
