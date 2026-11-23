"""Audit exact capacity/packet-commit wiring before application execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4'),default='receive-capacity-v2');args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=read(root/'build/validation/open-rpc-reclaim-assembly.json');component=read(root/'build/validation/receive-capacity-store.json')
    faults=read(root/'build/validation/open-rpc-reclaim-faults.json')
    assert parent['key']=='ad1b6bc9beebcaf5' and component['key']=='76cbac586a7c94ac' and faults['key']=='954daaa0ea84129c'
    folder=root/'build/experiments'/args.candidate;generation=read(folder/'generation.json')
    assert generation['parent_assembly_audit_key']==parent['key'] and generation['capacity_component_audit_key']==component['key']
    assert generation['parent_actual_reclaim_fault_audit_key']==faults['key']
    assert sha(folder/'generate_receive_capacity_application.py')==generation['generator_sha256']
    parser={n:sha(p) for n,p in closure('http2_enveloped_parser_application',folder).items()}
    assert len(parser)==77 and parser=={Path(n).stem:h for n,h in generation['outputs_sha256'].items()}
    expected={'http2_receive_credit_store','http2_keyed_receive_credit_store','http2_receive_flow_controller','grpc_payload_reclaimer','http2_enveloped_parser_core'}
    assert set(generation['source_edit_certificate'])==set(generation['changed_from_reclaim_parent'])==expected
    for n,h in parent['executed_parser_sha256'].items():
        p=folder/'rtl'/(n+'.v')
        if n not in expected:assert sha(p)==h;continue
        text=p.read_text()
        for before,after in reversed(generation['source_edit_certificate'][n]):
            assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.replace('\n',generation['original_newlines'][n]).encode()).hexdigest()==h,n
    assert parser['http2_receive_credit_store']==component['actual_store_sha256']
    assert parser['memory_command_slot']==component['actual_memory_slot_sha256']
    core=(folder/'rtl/http2_enveloped_parser_core.v').read_text()
    old=(root/'build/experiments/open-rpc-reclaim/rtl/http2_enveloped_parser_core.v').read_text()
    assert ports(core,'http2_enveloped_parser_core')==ports(old,'http2_enveloped_parser_core')
    for fragment in ('wire rc_packet_ack=packet_result_valid&&packet_result_ready&&packet_committed;',
        'wire rc_dma_ack=completion_valid&&completion_ready&&completion_status==0&&reclaim_candidate;',
        'wire rc_fence=rc_pending||rc_busy||rc_ack;',
        'if(command_valid&&command_ready||control_valid&&control_ready||s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin\n            rc_live_payload_base<=cfg_payload_base;',
        '.cfg_payload_base(rc_credit_owner?rc_payload_base:rc_live_payload_base)',
        '.cfg_payload_bytes(rc_credit_owner?rc_payload_bytes:rc_live_payload_bytes)',
        '.cfg_payload_slot_bytes(rc_credit_owner?rc_slot_bytes:rc_live_slot_bytes)',
        'rx_admission_op==0?4\'d12:rx_admission_op',
        '!payload_lease_active&&!completion_valid&&f_idle&&!rx_active&&!rx_granted&&',
        '.req_authority(rc_credit_owner?rc_lock_active:rx_backend_authority)',
        '.m_lock_valid(receive_pool_lock_valid)', 'assign mem_valid[26]=rc_memory_owner?rc_mem_valid:rc_rx_mem_valid;'):
        assert core.count(fragment)==1,fragment
    keyed=(folder/'rtl/http2_keyed_receive_credit_store.v').read_text()
    if args.candidate in ('receive-capacity-v2','receive-capacity-v3','receive-capacity-v4'):
        assert 'rx_request_op==12&&service_window_rsp_op==0&&rx_admission_op==0&&rx_request_stream==0&&\n     rx_request_generation==0&&rx_request_address==0&&rx_request_amount==0' in core
    if args.candidate=='receive-capacity-v4':
        assert 'shutdown_control_offered||(!shutdown_command_offered&&!rc_fence&&!rx_format_pending&&' in core
        assert 'assign rc_start=rc_pending&&!rc_busy&&!shutdown_command_offered&&!f_command_valid&&!rsp_valid&&\n    !shutdown_control_offered&&!f_control_valid&&' in core
        assert '!f_control_result_valid&&!control_result_valid&&!rx_format_pending&&!rx_format_failed&&' in core
        assert 'wire command_admit=(allow_config||shutdown_command_offered)&&\n    (shutdown_command_offered||!shutdown_control_offered&&!control_valid);' in core
        assert 'else if(f_command_valid)shutdown_command_offered<=!f_command_ready;' in core
    elif args.candidate=='receive-capacity-v3':
        assert 'wire shutdown_control_admit=shutdown_control_offered||(!rc_fence&&!rx_format_pending&&' in core
        assert 'assign rc_start=rc_pending&&!rc_busy&&!shutdown_control_offered&&!f_control_valid&&\n    !f_control_result_valid&&!control_result_valid&&!rx_format_pending&&!rx_format_failed&&\n    queued_count==0&&pending_count==0&&!retirement_pending&&' in core
    else:
        assert 'assign rc_start=rc_pending&&!rc_busy&&queued_count==0&&pending_count==0&&!retirement_pending&&' in core
    for fragment in ('held_cfg_payload_base<=cfg_payload_base;held_cfg_payload_bytes<=cfg_payload_bytes;held_cfg_payload_slot_bytes<=cfg_payload_slot_bytes;',
        '.cfg_payload_base(held_cfg_payload_base)',
        '.ENABLE_CAPACITY(ENABLE_CAPACITY)', 'held_req_op==0||ENABLE_CAPACITY&&held_req_op==12'):
        assert fragment in keyed
    compactor=(folder/'rtl/grpc_payload_reclaimer.v').read_text()
    assert 'if(ENABLE_CAPACITY)begin credit_step<=1;state<=CREDIT_SEND;end' in compactor
    assert 'credit_op=credit_step==0?4\'d3:4\'d4;' in compactor
    assert 'record_data[453:421]<=completed_count;' in compactor
    assert 'else begin credit_step<=0;state<=CREDIT_SEND;end' in compactor
    result=dict(phase='receive_capacity_private_assembly_verified',candidate=args.candidate,verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_assembly_audit_key=parent['key'],capacity_component_audit_key=component['key'],
        parent_actual_reclaim_fault_audit_key=faults['key'],exact_parser_modules=77,executed_parser_sha256=parser,
        source_edit_inverse_verified=True,public_core_ports_unchanged=True,
        actual_packet_commit_and_dma_ack_hooks_verified=True,actual_pool_lock_and_memory_mux_preserved=True,
        live_partial_records_announce_pending_credit_without_release=True,
        actual_captured_backing_propagated_to_backend=True,keyed_recovery_scope_includes_backing=True,
        capacity_format_translation_tied_to_actual_initialization=args.candidate in ('receive-capacity-v2','receive-capacity-v3','receive-capacity-v4'),
        private_control_and_format_admission_serialized=args.candidate in ('receive-capacity-v3','receive-capacity-v4'),
        earlier_command_and_control_offers_preserved=args.candidate=='receive-capacity-v4',
        application_runtime_verified=False,large_message_deadlock_fixed=False,
        whole_system_retained_reset_verified=False,native_vendor_runtime_verified=False,native_timing_verified=False,
        full_protocol_fault_matrix_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        generation_sha256=sha(folder/'generation.json'),verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-capacity-assembly-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    label=args.candidate+'-assembly' if args.candidate in ('receive-capacity-v3','receive-capacity-v4') else 'receive-capacity-assembly'
    for p in (evidence/'audit.json',root/'build/validation'/(label+'.json')):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','large_message_deadlock_fixed')}))


if __name__=='__main__':main()
