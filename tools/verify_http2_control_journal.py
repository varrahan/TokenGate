"""Bind transactional control-log execution and exact native implementation."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import struct
import xml.etree.ElementTree as ET

from hyperframe.frame import Frame, PingFrame
from verify_two_fpga_application import closure, resources, timing


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-name',default='committed_control_log_full_metadata')
    parser.add_argument('--native-run',default='http2_control_journal_scu35_initial')
    parser.add_argument('--functional-only',action='store_true');args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',s)for s in(args.snapshot_name,args.native_run))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports'/('http2_control_journal_'+args.snapshot_name);executed=archive/'execution-sources'
    inputs=json.loads((archive/'inputs.json').read_text());report=json.loads((archive/'report.json').read_text())
    accepted=json.loads((archive/'acceptance.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and snapshot['exit_code']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert report['tests']==1 and report['failures']==0
    for name,digest in inputs.items():assert sha(executed/name)==digest,name
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='partial_control_frames_packet_abort_wrap_and_every_memory_fault'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert accepted['native_settings_parameters']==5 and accepted['memory_phases']==accepted['injected_memory_faults']==54
    assert accepted['negative_configuration_and_authority_commands']==7 and accepted['held_output_cycles']>0
    assert accepted['native_extra_control_frames']==5 and accepted['stream_id_and_ack_flags_preserved']
    assert all(accepted[k]for k in('duplicate_settings_preserved','unknown_settings_preserved',
        'partial_frame_across_packets_verified','independent_connections_verified','aborted_packet_preserves_committed_root',
        'complete_frame_before_consumer_verified','ring_wrap_verified','explicit_capacity_failure_verified',
        'applied_write_errors_quarantined','no_retry_after_uncertain_effect','consumer_error_quarantined',
        'poisoned_config_verified','complete_model_prefix_immutable','actual_connection_ownership_supplied_by_fixture'))
    assert not accepted['window_consumer_integrated']and not accepted['raw_parser_integrated']and not accepted['full_system_complete']
    dependencies=closure('http2_control_journal',executed);assert set(dependencies)=={'http2_control_journal','memory_command_slot'}
    source=(executed/'rtl/http2_control_journal.v').read_text()
    assert 'assign m_valid=!rst&&state==EMIT;'in source and 'if(!finish_commit)state<=RESULT;'in source
    assert 'frame_end<=next_cursor;cursor<=head;load(RREPLAY,slot_address+head,3);'in source
    assert 'if(next_tail==head)quarantine(4,2,context_address+216);'in source
    assert 'if(consume_status!=0)quarantine(8,consume_status,slot_address+cursor);'in source
    assert 'root_record[95:64]<=frame_end;save_root(1);'in source
    assert "state==WRITE_REQ?{8'd0,write_word}:72'd0"in source
    fixture=executed/'build/http2-send-window-fixtures'
    reference=json.loads((fixture/'cases.json').read_text())
    assert reference['original_image_sha256']==sha(fixture/'model.bin')==sha(root/'build/scu35/image/external_memory.bin')
    assert accepted['hyperframe_version']==importlib.metadata.version('hyperframe')=='6.1.0'
    settings=[(1,4096),(4,0),(5,16384),(4,65535),(65000,0xdeadbeef)]
    payload=b''.join(struct.pack('>HI',*p)for p in settings)
    wire=len(payload).to_bytes(3,'big')+b'\x04\0'+bytes(4)+payload
    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
    assert size==30 and frame.settings==dict(settings)
    ping=PingFrame(0);ping.opaque_data=b'journal!'
    native=dict(settings_wire_hex=wire.hex(),ordered_settings=settings,ping_wire_hex=ping.serialize().hex(),
        duplicate_parameter_order_retained=True,settings_ack=False,hyperframe_version='6.1.0')
    replay=root/'build/validation/control-journal-native-reference.json';replay.write_text(json.dumps(native,indent=2)+'\n')
    files={Path('execution')/name:executed/name for name in inputs}
    files.update({Path('reports')/name:archive/name for name in('inputs.json','report.json','snapshot.json','results.xml','acceptance.json','simulation.log','build.log')})
    files[Path('verification/native-reference.json')]=replay
    files[Path('verification/verify_http2_control_journal.py')]=Path(__file__)
    result=dict(phase='journal_functional_passed_native_pending',verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted,execution_inputs=len(inputs),active_rtl_modules=list(dependencies),
        independent_native_frame_replay_verified=True,current_primary_differences=[n for n,h in inputs.items()if not(root/n).is_file()or sha(root/n)!=h],
        actual_connection_owner_supplied_by_fixture=True,raw_parser_joined=False,window_consumer_joined=False,
        ack_transmitter_joined=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    if not args.functional_only:
        folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run;frozen=folder/'sources'
        provenance=json.loads((folder/'source-provenance.json').read_text())
        for name,record in provenance['files'].items():assert sha(frozen/name)==record['sha256']
        measured_dependencies=closure('http2_control_journal',frozen);assert set(measured_dependencies)==set(dependencies)
        for path in measured_dependencies.values():
            relative=path.relative_to(frozen);assert sha(path)==inputs[relative.as_posix()]
            files[Path('native/sources')/relative]=path
        implementation=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
        assert[line.strip()for line in implementation.splitlines()if line.strip().startswith('set_false_path')]==[
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        log=root/f'build/{args.native_run}-implementation.log';text=log.read_text()
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=http2_control_journal PART=xcsu35p-sbvb625-2-e'in text
        assert '0 Critical Warnings and 0 Errors encountered.'in text and 'ERROR: [Synth'not in text
        area=resources(folder/'routed_utilization.rpt');clocks=timing(folder/'routed_timing.rpt')
        assert area['luts']<=16320 and area['registers']<=32640 and area['bram36']==area['bram18']==area['uram']==0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        result.update(phase='journal_functional_and_native_timing_met'if met else'journal_functional_passed_timing_pending',
            native_run=args.native_run,timing=clocks,resources=area,routed_timing_met=met,native_exact_rtl_files=2,
            package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        files[Path('native/implementation.log')]=log
        for name in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','route_status.rpt','routed_drc.rpt'):files[Path('native')/name]=folder/name
        for name in provenance['files']:
            if not name.startswith('rtl/'):files[Path('native/sources')/name]=frozen/name
    key=hashlib.sha256(''.join(str(p)+sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/http2-control-journal-evidence'/key
    for relative,path in files.items():
        target=evidence/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(path)
        else:shutil.copy2(path,target)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/http2-control-journal.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
