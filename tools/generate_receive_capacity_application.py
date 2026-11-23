"""Wire qualified backed budgets into actual packet commits and pool ownership."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',default='receive-capacity-v4');args=ap.parse_args()
    assert re.fullmatch(r'[a-z0-9-]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    parent=read(root/'build/validation/open-rpc-reclaim-assembly.json')
    component=read(root/'build/validation/receive-capacity-store.json')
    faults=read(root/'build/validation/open-rpc-reclaim-faults.json')
    assert parent['key']=='ad1b6bc9beebcaf5' and component['key']=='76cbac586a7c94ac' and faults['key']=='954daaa0ea84129c'
    original=root/'build/experiments/open-rpc-reclaim';folder=root/'build/experiments'/args.name;folder.mkdir(parents=True,exist_ok=False)
    source={};raws={};newlines={};certificates={}
    for n,h in parent['executed_parser_sha256'].items():
        p=original/'rtl'/(n+'.v');assert sha(p)==h
        raw=p.read_bytes().decode();raws[n]=raw;newlines[n]='\r\n' if '\r\n' in raw else '\n';source[n]=raw.replace('\r\n','\n')
    def edit(module,before,after):
        assert source[module].count(before)==1,(module,before)
        source[module]=source[module].replace(before,after);certificates.setdefault(module,[]).append([before,after])
    store_gen=read(root/'build/experiments/receive-capacity-store/generation.json')
    n='http2_receive_credit_store'
    for before,after in store_gen['source_edit_certificate']:edit(n,before,after)
    assert hashlib.sha256(source[n].replace('\n',newlines[n]).encode()).hexdigest()==component['actual_store_sha256']
    n='http2_keyed_receive_credit_store'
    edit(n,'parameter integer ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23',
        'parameter integer ENABLE_CAPACITY=0,ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23')
    marker='    input wire  context_write_busy,'
    edit(n,marker,'    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base,\n    input wire [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes,cfg_payload_slot_bytes,\n'+marker)
    marker='reg  held_req_keyed;'
    edit(n,marker,'reg [MEMORY_ADDR_WIDTH-1:0] held_cfg_payload_base;\nreg [MEMORY_ADDR_WIDTH:0] held_cfg_payload_bytes,held_cfg_payload_slot_bytes;\n'+marker)
    edit(n,'reg [USER_WIDTH+9*MEMORY_ADDR_WIDTH+4-1:0] scan_recovery_scope;',
        'localparam integer SCOPE_WIDTH=USER_WIDTH+9*MEMORY_ADDR_WIDTH+4+(ENABLE_CAPACITY?3*MEMORY_ADDR_WIDTH+2:0);\nreg [SCOPE_WIDTH-1:0] scan_recovery_scope;')
    before='''wire [USER_WIDTH+9*MEMORY_ADDR_WIDTH+4-1:0] current_scope={held_req_user,
    held_cfg_context_base,held_cfg_rpc_base,held_cfg_receive_connection_base,held_cfg_receive_stream_base,held_cfg_work_floor,
    held_cfg_context_bytes,held_cfg_rpc_bytes,held_cfg_receive_connection_bytes,held_cfg_receive_stream_bytes};'''
    old_tuple=before.split('current_scope=',1)[1].removesuffix(';')
    new_tuple=old_tuple[:-1]+',held_cfg_payload_base,held_cfg_payload_bytes,held_cfg_payload_slot_bytes}'
    edit(n,before,'wire [SCOPE_WIDTH-1:0] current_scope=ENABLE_CAPACITY?'+new_tuple+':'+old_tuple+';')
    edit(n,'state<=IDLE;resolved_address<=0;',
        'state<=IDLE;held_cfg_payload_base<=0;held_cfg_payload_bytes<=0;held_cfg_payload_slot_bytes<=0;resolved_address<=0;')
    edit(n,'held_req_op<=req_op;held_req_authority<=req_authority;',
        'held_cfg_payload_base<=cfg_payload_base;held_cfg_payload_bytes<=cfg_payload_bytes;held_cfg_payload_slot_bytes<=cfg_payload_slot_bytes;\n            held_req_op<=req_op;held_req_authority<=req_authority;')
    edit(n,'held_req_keyed||held_req_op!=0||!held_req_maintenance',
        'held_req_keyed||!(held_req_op==0||ENABLE_CAPACITY&&held_req_op==12)||!held_req_maintenance')
    edit(n,'if(held_req_op==0&&c_rsp_status==0)',
        'if((held_req_op==0||ENABLE_CAPACITY&&held_req_op==12)&&c_rsp_status==0)')
    edit(n,'http2_receive_credit_store #(.ENABLE_STREAM_FORMAT(ENABLE_STREAM_FORMAT),',
        'http2_receive_credit_store #(.ENABLE_CAPACITY(ENABLE_CAPACITY),.ENABLE_STREAM_FORMAT(ENABLE_STREAM_FORMAT),')
    marker='    .cfg_context_base(held_cfg_context_base),'
    edit(n,marker,'    .cfg_payload_base(held_cfg_payload_base),.cfg_payload_bytes(held_cfg_payload_bytes),.cfg_payload_slot_bytes(held_cfg_payload_slot_bytes),\n'+marker)
    n='http2_receive_flow_controller'
    edit(n,'parameter integer ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23',
        'parameter integer ENABLE_CAPACITY=0,ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23')
    edit(n,'if(request_op==0||ENABLE_STREAM_FORMAT&&request_op==11)',
        'if(request_op==0||ENABLE_CAPACITY&&request_op==12||ENABLE_STREAM_FORMAT&&request_op==11)')
    n='grpc_payload_reclaimer'
    edit(n,'parameter integer MEMORY_ADDR_WIDTH=23,USER_WIDTH=16',
        'parameter integer ENABLE_CAPACITY=0,MEMORY_ADDR_WIDTH=23,USER_WIDTH=16')
    edit(n,'wire refund_good=refund_value<=65535&&',
        "wire refund_good=refund_value<=(ENABLE_CAPACITY?{32'd0,record_data[191:160]}+64'd5:64'd65535)&&")
    edit(n,'else if(refund_value==0)state<=NEXT_RECORD;',
        '''else if(refund_value==0)begin
                        // This packet admitted a committed live slot. Announce
                        // only durable pending capacity, without RELEASE or
                        // mutation of the live partial prefix/body.
                        if(ENABLE_CAPACITY)begin credit_step<=1;state<=CREDIT_SEND;end
                        else state<=NEXT_RECORD;
                    end''')
    n='http2_enveloped_parser_core'
    edit(n,'wire rc_ack=completion_valid&&completion_ready&&completion_status==0&&reclaim_candidate;',
        '''wire rc_packet_ack=packet_result_valid&&packet_result_ready&&packet_committed;
wire rc_dma_ack=completion_valid&&completion_ready&&completion_status==0&&reclaim_candidate;
wire rc_ack=rc_packet_ack||rc_dma_ack;''')
    edit(n,'if(s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin\n            rc_live_payload_base<=cfg_payload_base;',
        'if(command_valid&&command_ready||control_valid&&control_ready||s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin\n            rc_live_payload_base<=cfg_payload_base;')
    edit(n,'http2_keyed_receive_credit_store #(.ENABLE_STREAM_FORMAT(1),',
        'http2_keyed_receive_credit_store #(.ENABLE_CAPACITY(1),.ENABLE_STREAM_FORMAT(1),')
    marker='    .req_valid(rc_credit_owner?rc_credit_valid:rx_backend_valid),'
    edit(n,marker,'''    .cfg_payload_base(rc_credit_owner?rc_payload_base:rc_live_payload_base),
    .cfg_payload_bytes(rc_credit_owner?rc_payload_bytes:rc_live_payload_bytes),
    .cfg_payload_slot_bytes(rc_credit_owner?rc_slot_bytes:rc_live_slot_bytes),
'''+marker)
    edit(n,'http2_receive_flow_controller #(.ENABLE_STREAM_FORMAT(1),',
        'http2_receive_flow_controller #(.ENABLE_CAPACITY(1),.ENABLE_STREAM_FORMAT(1),')
    edit(n,"assign rx_init_op=rx_select_format?4'd11:rx_select_close?(rx_close_connection_fatal?4'd10:4'd9):rx_admission_op;",
        "assign rx_init_op=rx_select_format?4'd11:rx_select_close?(rx_close_connection_fatal?4'd10:4'd9):rx_admission_op==0?4'd12:rx_admission_op;")
    edit(n,'rx_request_op==service_window_rsp_op&&rx_request_user==service_window_rsp_user&&rx_request_stream==service_window_rsp_stream&&',
        '''(rx_request_op==service_window_rsp_op||
     rx_request_op==12&&service_window_rsp_op==0&&rx_admission_op==0&&rx_request_stream==0&&
     rx_request_generation==0&&rx_request_address==0&&rx_request_amount==0)&&
    rx_request_user==service_window_rsp_user&&rx_request_stream==service_window_rsp_stream&&''')
    edit(n,'grpc_payload_reclaimer #(.USER_WIDTH(USER_WIDTH),',
        'grpc_payload_reclaimer #(.ENABLE_CAPACITY(1),.USER_WIDTH(USER_WIDTH),')
    if args.name in ('receive-capacity-v3','receive-capacity-v4'):
        edit(n,'wire shutdown_control_admit=shutdown_control_offered||(!rx_format_pending&&',
            'wire shutdown_control_admit=shutdown_control_offered||(!rc_fence&&!rx_format_pending&&')
        edit(n,'assign rc_start=rc_pending&&!rc_busy&&queued_count==0&&pending_count==0&&!retirement_pending&&',
            '''assign rc_start=rc_pending&&!rc_busy&&!shutdown_control_offered&&!f_control_valid&&
    !f_control_result_valid&&!control_result_valid&&!rx_format_pending&&!rx_format_failed&&
    queued_count==0&&pending_count==0&&!retirement_pending&&''')
    if args.name=='receive-capacity-v4':
        edit(n,'reg shutdown_control_offered;', 'reg shutdown_control_offered;\nreg shutdown_command_offered;')
        edit(n,'shutdown_control_offered||(!rc_fence&&!rx_format_pending&&',
            'shutdown_control_offered||(!shutdown_command_offered&&!rc_fence&&!rx_format_pending&&')
        marker='assign f_command_valid=command_valid&&allow_config;\nassign command_ready=f_command_ready&&allow_config;'
        edit(n,marker,'''wire command_admit=(allow_config||shutdown_command_offered)&&
    (shutdown_command_offered||!shutdown_control_offered&&!control_valid);
assign f_command_valid=command_valid&&command_admit;
assign command_ready=f_command_ready&&command_admit;
always @(posedge clk)begin
    if(rst)shutdown_command_offered<=0;
    else if(f_command_valid)shutdown_command_offered<=!f_command_ready;
end''')
        edit(n,'assign rc_start=rc_pending&&!rc_busy&&!shutdown_control_offered&&!f_control_valid&&',
            'assign rc_start=rc_pending&&!rc_busy&&!shutdown_command_offered&&!f_command_valid&&!rsp_valid&&\n    !shutdown_control_offered&&!f_control_valid&&')
    for n,text in source.items():
        restored=text
        for before,after in reversed(certificates.get(n,[])):
            assert restored.count(after)==1;restored=restored.replace(after,before)
        assert restored.replace('\n',newlines[n])==raws[n],n
        p=folder/'rtl'/(n+'.v');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.replace('\n',newlines[n]).encode())
    assert ports(source['http2_enveloped_parser_core'],'http2_enveloped_parser_core')==ports(raws['http2_enveloped_parser_core'],'http2_enveloped_parser_core')
    parser={n:sha(p) for n,p in closure('http2_enveloped_parser_application',folder).items()};assert len(parser)==77
    changed={n for n in parser if parser[n]!=parent['executed_parser_sha256'][n]}
    assert changed==set(certificates)=={'http2_receive_credit_store','http2_keyed_receive_credit_store','http2_receive_flow_controller','grpc_payload_reclaimer','http2_enveloped_parser_core'}
    quiet=read(root/'build/validation/frame-owned-quiet-corpus.json')
    result=dict(phase='receive_capacity_application_generated',candidate=args.name,parent_assembly_audit_key=parent['key'],
        capacity_component_audit_key=component['key'],parent_actual_reclaim_fault_audit_key=faults['key'],
        exact_parser_modules=77,changed_from_reclaim_parent=sorted(changed),
        changed_existing_modules=sorted(n for n in quiet['executed_parser_sha256'] if parser[n]!=quiet['executed_parser_sha256'][n]),
        added_module='grpc_payload_reclaimer',source_edit_certificate=certificates,original_newlines=newlines,
        exact_source_inverse_verified=True,public_core_ports_unchanged=True,
        packet_commit_ack_uses_real_private_owner=True,existing_pool_lock_and_memory_client_preserved=True,
        private_control_and_format_admission_serialized=args.name in ('receive-capacity-v3','receive-capacity-v4'),
        earlier_command_and_control_offers_preserved=args.name=='receive-capacity-v4',
        outputs_sha256={'rtl/'+n+'.v':h for n,h in parser.items()},generator_sha256=sha(Path(__file__)),
        application_runtime_verified=False,large_message_deadlock_fixed=False,native_timing_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');shutil.copy2(Path(__file__),folder/Path(__file__).name)
    print(json.dumps(dict(phase=result['phase'],exact_parser_modules=77,changed_modules=sorted(changed))))


if __name__=='__main__':main()
