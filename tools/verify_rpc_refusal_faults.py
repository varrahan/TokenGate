"""Audit every physical refused-DATA ACK position and actual captured frames."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import Frame

from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('rpc-stream-refusal-v7','rpc-registered-frame-select-v1'),default='rpc-stream-refusal-v7');args=ap.parse_args()
    registered=args.candidate=='rpc-registered-frame-select-v1'
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    candidate=root/'build/experiments'/args.candidate;generation=read(candidate/'generation.json')
    directed=read(root/'build/validation/rpc-stream-refusal-v7-directed.json')
    assert directed['key']=='950ce3b65ccb9b0a'
    if registered:
        from verify_registered_frame_select import require_unit_audit
        selection_audit=require_unit_audit(root)
        assert directed['generation_sha256']==generation['parent_generation_sha256']
        actual_directed=read(root/'build/validation/rpc-registered-frame-select-v1-directed.json')
        assert actual_directed['key']=='381fe48f058bf0b1'and actual_directed['generation_sha256']==sha(candidate/'generation.json')
    else:assert directed['generation_sha256']==sha(candidate/'generation.json')
    assert directed['four_directed_application_runs_verified']
    run='rpc_registered_select_v1_faults_20261122'if registered else'rpc_stream_refusal_v7_faults_20261122'
    folder=root/'build/wsl-reports'/('raw_envelope_'+run)
    source=folder/'execution-sources';launch=read(folder/'launch.json');report=read(folder/'report.json')
    inputs=read(folder/'inputs.json');accepted=read(folder/'acceptance.json')
    assert launch['phase']=='completed' and launch['exit_code']==0 and launch['scenario']=='faults'
    if registered:assert launch['registered_selection_unit_audit_key']==selection_audit['key']
    assert launch['generation_sha256']==sha(candidate/'generation.json')==sha(folder/'fence-generation.json')
    assert report['phase']==accepted['phase']=='passed' and report['tests']==1 and report['failures']==0
    assert launch['inputs_sha256']==report['input_sha256']==inputs
    assert all(sha(source/n)==h for n,h in inputs.items())
    assert sha(folder/'acceptance.json')==report['acceptance_sha256']
    assert sha(folder/'run_rpc_admission_fence_wsl.py')==launch['driver_sha256']
    assert {n:sha(p)for n,p in closure('http2_enveloped_parser_application',source).items()}==generation['non_mmio_parser_sha256']==launch['parser_sha256']
    tokenizer={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
    parent=root/'build/wsl-reports/raw_envelope_receive_capacity_v4_native_owner_admission_20261122'
    assert len(tokenizer)==22 and tokenizer==launch['tokenizer_sha256']=={n:sha(p)for n,p in closure('tokenizer_fpga_memory_subsystem',parent/'execution-sources').items()}
    assert launch['parent_inputs_sha256']==read(parent/'inputs.json')
    for n,edit in launch['fixture_edits'].items():
        text=(source/n).read_bytes().decode();assert sha(source/n)==edit['after_sha256']
        for before,after in reversed(edit['replacements']):
            assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.encode()).hexdigest()==edit['before_sha256']
        if n in launch['parent_inputs_sha256']:assert edit['before_sha256']==launch['parent_inputs_sha256'][n]
    assert inputs['build/bidirectional-fixtures/memory.mem']==launch['parent_inputs_sha256']['build/bidirectional-fixtures/memory.mem']
    test='sim/cocotb/test_rpc_refusal_faults.py'
    assert sha(source/test)==sha(root/test)
    xml=ET.parse(folder/'results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='every_refused_data_ack_fault_preserves_wire_and_quarantine'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    baseline=accepted['baseline'];final=accepted['successful_fresh_root_recovery']
    commands=baseline['memory_commands'];responses=baseline['memory_responses'];assert len(commands)==len(responses)==46
    assert [c['index']for c in commands]==list(range(46))==[r['index']for r in responses]
    assert {c['flow_operation']for c in commands}=={1,6,7}
    assert len(baseline['actual_wire_updates'])==1 and baseline['actual_wire_updates'][0]['ack_count']==44
    assert responses[43]['clock']<baseline['actual_wire_updates'][0]['clock']<commands[44]['clock']
    if not registered:assert baseline['actual_wire_updates']==[{'clock':19592,'ack_count':44}]
    assert [c['index']for c in commands if c['write']]==[23,33,43,44,45]
    assert commands[13]['backend_state']==11 and responses[13]['data_hex']=='000000000348325731'
    shape=lambda entry:{k:v for k,v in entry.items()if k!='clock'}
    def frames(raws):
        decoded=[]
        for raw in raws:
            data=bytes.fromhex(raw);f,size=Frame.parse_frame_header(memoryview(data[:9]));f.parse_body(memoryview(data[9:]))
            assert len(data)==9+size;decoded.append(f)
        return decoded
    def check_wire(case,has_update):
        fs=frames(case['wire_frames']);assert len(fs)==1+int(has_update)
        assert fs[0].type==3 and fs[0].stream_id==3 and fs[0].error_code==7
        if has_update:assert fs[1].type==8 and fs[1].stream_id==0 and fs[1].window_increment==26
        assert len(case['actual_wire_updates'])==int(has_update)
        assert case['held_reset_cycles']>=37
    for successful in (baseline,final):
        assert successful['phase']is None and successful['packet_result']==[1,0,0,0,0,0]
        assert all(r['status']==0 for r in successful['memory_responses'])
        assert list(map(shape,successful['memory_commands']))==list(map(shape,commands))
        assert list(map(shape,successful['memory_responses']))==list(map(shape,responses))
        check_wire(successful,True)
    assert [c['phase']for c in accepted['cases']]==[45]+list(range(45))
    details=[]
    for case in accepted['cases']:
        phase=case['phase'];cs=case['memory_commands'];rs=case['memory_responses']
        assert len(cs)==len(rs)==phase+1
        assert list(map(shape,cs))==list(map(shape,commands[:phase+1]))
        assert [r['index']for r in rs if r['status']]==[phase]and rs[-1]['status']==0x75
        for index,(cmd,rsp)in enumerate(zip(cs,rs)):
            assert cmd['clock']<rsp['clock']
            assert rsp['data_hex']==responses[index]['data_hex']
            if index:assert rs[index-1]['clock']<cmd['clock']
        assert case==read(folder/('refusal-fault-'+str(phase)+'.json'))
        assert case['packet_result'][0:2]==[0,12]and case['packet_result'][3:]==[117,117,0]
        check_wire(case,phase>=44)
        state=read(folder/('fault-state-completed-'+str(phase)+'.json'))
        assert state['fault_injected']==1
        assert state['core']['receive_fault_valid']==state['core']['receive_recovery_required']==1
        assert state['core']['rx_active']==state['core']['rx_granted']==state['core']['rx_drop_valid']==0
        assert state['backend_state']==state['credit_store_state']==state['receive_state']==0
        assert state['trace']['commands']==cs and state['trace']['responses']==rs
        packets=state['ingress_packets'];assert len(packets)==4
        server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'));server.initiate_connection()
        requests=[];bodies={};credit={}
        for packet in packets:
            assert packet['user']==0
            for event in server.receive_data(bytes.fromhex(packet['raw_hex'])):
                kind=type(event).__name__
                if kind=='RequestReceived':requests.append(event.stream_id)
                if kind=='DataReceived':
                    bodies[event.stream_id]=bodies.get(event.stream_id,b'')+event.data
                    credit[event.stream_id]=credit.get(event.stream_id,0)+event.flow_controlled_length
        assert requests==[1,3]and bodies=={1:b'\0\0\0\0\r\x0a\x0b',3:b'\0\0\0\0\r\x0a\x0bhello world'}
        assert credit=={1:7,3:26}
        details.append(dict(index=phase,address=cs[-1]['address'],write=cs[-1]['write'],
            flow_operation=cs[-1]['flow_operation'],wire_update_preceded_error=phase>=44,
            actual_memory_status=117,physical_commands_after_error=0))
    # Preserve the actual predecessor failure: all memory ACKs drained and the
    # wire already accepted credit, but discarded DATA waited for journal replay.
    negative=root/'build/wsl-reports/raw_envelope_rpc_stream_refusal_v6_faults_20261122'
    assert read(negative/'launch.json')['exit_code']==1
    failed=read(negative/'fault-state-timeout-packet_result_valid.json')
    assert failed['receive_state']==5 and failed['receive_operation']==7
    assert failed['core']['rx_drop_valid']==1 and failed['core']['receive_fault_valid']==1
    assert len(failed['trace']['commands'])==len(failed['trace']['responses'])==46
    assert failed['trace']['responses'][-1]['status']==117
    result=dict(phase='refused_data_all_46_physical_ack_faults_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=run,generation_sha256=sha(candidate/'generation.json'),directed_audit_key=directed['key'],
        executed_parser_sha256=generation['non_mmio_parser_sha256'],executed_tokenizer_sha256=tokenizer,
        actual_memory_response_positions=46,actual_applied_write_ack_error_positions=5,
        actual_post_wire_retirement_error_positions=2,baseline_and_final_success_verified=True,
        no_memory_retry_or_duplicate_wire_credit=True,held_reset_and_packet_result_assertions_passed=True,
        exact_full_model_fixture_preserved=True,model_immutability_checked_by_simulation_assertions=True,
        no_per_fault_final_memory_dump_available=True,old_rpc_left_incomplete_no_gpu_descriptors_accepted=True,
        resets_are_explicit_test_root_resets_after_drain=True,production_retained_reset_recovery_verified=False,
        native_vendor_runtime_verified=False,full_protocol_fault_matrix_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,native_timing_verified=False,full_system_complete=False,
        injections=details,predecessor_failure_state_sha256=sha(negative/'fault-state-timeout-packet_result_valid.json'),
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in folder.iterdir()if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    if registered:result.update(candidate=args.candidate,registered_selection_unit_audit_key=selection_audit['key'],
        registered_selection_directed_audit_key=actual_directed['key'],phase='registered_selection_all_46_physical_ack_faults_verified')
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-refusal-ack-faults-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    pointer='rpc-registered-select-ack-faults.json'if registered else'rpc-refusal-ack-faults.json'
    for p in (evidence/'audit.json',root/'build/validation'/pointer):
        p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ('phase','key','actual_memory_response_positions')}))


if __name__=='__main__':main()
