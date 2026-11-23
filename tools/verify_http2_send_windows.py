"""Audit native-referenced outbound-window transactions and exact native RTL."""
import argparse
from datetime import datetime, timezone
import hashlib
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
    parser=argparse.ArgumentParser();parser.add_argument('--functional-only',action='store_true')
    parser.add_argument('--snapshot-name',default='durable_send_windows_reply_scope')
    parser.add_argument('--native-run',default='http2_send_windows_scu35_reply_scope')
    args=parser.parse_args();assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',x)for x in(args.snapshot_name,args.native_run))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports'/('http2_send_windows_'+args.snapshot_name);executed=archive/'execution-sources'
    inputs=json.loads((archive/'inputs.json').read_text());report=json.loads((archive/'report.json').read_text())
    snapshot=json.loads((archive/'snapshot.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    assert report['phase']==accepted['phase']=='passed' and snapshot['exit_code']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert report['tests']==1 and report['failures']==0
    for name,digest in inputs.items():assert sha(executed/name)==digest
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='native_signed_windows_and_every_memory_failure'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert (accepted['native_commands'],accepted['negative_commands'],accepted['injected_memory_faults'])==(28,11,72)
    assert accepted['memory_phase_counts']=={'0':8,'1':16,'5':15,'3':33}
    assert accepted['total_commands']==446 and accepted['total_memory_commands']==3911
    assert accepted['full_model_bytes']==8388608 and accepted['model_prefix_immutable']
    assert accepted['both_debits_before_grant_verified'] and accepted['signed_negative_windows_verified']and accepted['all_live_stream_settings_scan_verified']
    assert accepted['typed_authority_supplied_by_fixture'] and not accepted['actual_directory_admission_integrated'] and not accepted['actual_network_control_integrated']
    fixture=executed/'build/http2-send-window-fixtures';reference=json.loads((fixture/'cases.json').read_text())
    assert reference['phase']=='native_send_window_references_passed'
    assert reference['generator_sha256']==sha(executed/'tools/generate_http2_send_window_vectors.py')
    assert reference['original_image_sha256']==sha(fixture/'model.bin')==sha(root/'build/scu35/image/external_memory.bin')
    assert len(reference['cases'])==28 and reference['streams']==[1,3,5]
    assert any(c.get('stream_window',0)<0 for c in reference['cases']) and any(c['grant']==1 for c in reference['cases']if'grant'in c)
    assert reference['cases'][-1]['status']==4 and reference['cases'][-1]['http2_error']==3 and reference['cases'][-1]['affected']==2
    replay_key=hashlib.sha256((reference['generator_sha256']+reference['original_image_sha256']).encode()).hexdigest()[:16]
    replay=root/'build/validation/http2-send-window-reference-replay'/replay_key
    replay_script=replay/'tools/generate_http2_send_window_vectors.py';replay_image=replay/'build/scu35/image/external_memory.bin'
    for destination,source in((replay_script,executed/'tools/generate_http2_send_window_vectors.py'),(replay_image,fixture/'model.bin')):
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():assert sha(destination)==sha(source)
        else:shutil.copy2(source,destination)
    if not(replay/'build/http2-send-window-fixtures/cases.json').exists():subprocess.run([sys.executable,str(replay_script)],check=True)
    assert sha(replay/'build/http2-send-window-fixtures/cases.json')==sha(fixture/'cases.json')
    files={Path('execution')/name:executed/name for name in inputs}
    files.update({Path('reports')/name:archive/name for name in('report.json','inputs.json','snapshot.json','results.xml','acceptance.json','simulation.log','build.log')})
    files[Path('verification/verify_http2_send_windows.py')]=Path(__file__)
    result=dict(phase='functional_passed_native_pending',verified_utc=datetime.now(timezone.utc).isoformat(),acceptance=accepted,
        native_reference_reproduced=True,execution_inputs=len(inputs),current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h],
        actual_directory_authority_integrated=False,actual_control_and_framer_integrated=False,
        receive_windows_verified=False,send_closed_stream_lifecycle_verified=False,
        whole_rpc_image_leases_verified=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    if not args.functional_only:
        native=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run;frozen=native/'sources'
        provenance=json.loads((native/'source-provenance.json').read_text())
        for name,record in provenance['files'].items():assert sha(frozen/name)==record['sha256'] and(frozen/name).stat().st_size==record['bytes']
        dependencies=closure('http2_send_window_store',frozen);assert set(dependencies)=={'http2_send_window_store','memory_command_slot'}
        for path in set(dependencies.values()):
            relative=path.relative_to(frozen);assert sha(path)==inputs[relative.as_posix()]
            files[Path('native/sources')/relative]=path
        implementation=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in implementation.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        log=source_path(root, f'build/{args.native_run}-implementation.log')
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=http2_send_window_store PART=xcsu35p-sbvb625-2-e' in log.read_text()
        assert '0 Critical Warnings and 0 Errors encountered.' in log.read_text() and 'ERROR: [Synth' not in log.read_text()
        area=resources(native/'routed_utilization.rpt');clocks=timing(native/'routed_timing.rpt')
        assert area['luts']<=16320 and area['registers']<=32640 and area['bram36']==area['bram18']==area['uram']==area['dsps']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(native/'route_status.rpt').read_text())
        assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|',(native/'routed_drc.rpt').read_text())
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        result.update(phase='functional_passed_native_timing_met'if met else'functional_passed_native_timing_pending',
            native_run=args.native_run,native_exact_rtl_files=len(dependencies),resources=area,timing=clocks,
            routed_timing_met=met,package_paths_excluded=True,routed_checkpoint_sha256=sha(native/'routed.dcp'))
        files[Path('native/implementation.log')]=log
        for name in('source-provenance.json','routed_utilization.rpt','routed_timing.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/name]=native/name
        for name in provenance['files']:
            if not name.startswith('rtl/'):files[Path('native/sources')/name]=frozen/name
    key=hashlib.sha256(''.join(sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/http2-send-window-evidence'/key
    for name,source in files.items():
        target=evidence/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source)
        else:shutil.copy2(source,target)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/http2-send-windows.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
