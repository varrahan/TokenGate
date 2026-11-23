"""Compose stream-local fence refusal and durable closed-stream DATA discard."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure
from generate_dual_fpga_hyperram_integration import order_declarations
from verify_dual_fpga_hyperram_integration import verify_order


def transport_edits():
    declarations = '''reg refusal_at_begin,refusal_reserved,refusal_pending,refusal_seen;
reg [511:0] refusal_frame;
reg [USER_WIDTH-1:0] refusal_owner;
wire fence_refusal=refusal_at_begin&&a_result_valid&&!a_result_is_reset&&
    a_result_status==4&&a_result_detail==1&&!a_result_connection_error&&a_result_http2_error==7&&
    a_result_memory_status==0&&a_result_control_status==0&&a_result_cleanup_status==0&&!a_result_trailers;
wire dropped_data=discard_frame_valid&&r_event_type==0&&r_event_user==discard_frame_user&&r_event_stream==discard_frame_stream;
assign discard_frame_done=dropped_data&&r_event_valid&&r_event_ready&&r_event_kind==3;
assign refusal_history=refusal_seen;
assign refusal_tdata=refusal_frame;assign refusal_tkeep=64'h1fff;
assign refusal_tvalid=!rst&&refusal_pending;assign refusal_tlast=1;
assign refusal_tuser=refusal_owner;
always @(posedge clk)begin
    if(rst)begin refusal_at_begin<=0;refusal_reserved<=0;refusal_pending<=0;refusal_seen<=0;refusal_frame<=0;refusal_owner<=0;end
    else begin
        if(a_begin_valid&&a_begin_ready)refusal_at_begin<=!admit_new_rpcs&&admit_messages&&!packet_fatal;
        if(refusal_pending&&refusal_tready)refusal_pending<=0;
        if(header_valid&&header_ready)refusal_reserved<=0;
        // Reserve a registered wire offer before publishing the rejected
        // header. Public VALID never depends on a changing wire READY.
        if(fence_refusal&&!refusal_reserved&&!refusal_pending)begin
            refusal_reserved<=1;refusal_pending<=1;refusal_seen<=1;refusal_owner<=a_result_user;
            refusal_frame<=0;refusal_frame[23:16]<=8'd4;refusal_frame[31:24]<=8'd3;
            refusal_frame[47:40]<={1'b0,a_result_stream[30:24]};
            refusal_frame[55:48]<=a_result_stream[23:16];refusal_frame[63:56]<=a_result_stream[15:8];
            refusal_frame[71:64]<=a_result_stream[7:0];refusal_frame[103:96]<=8'd7;
        end
    end
end
'''
    return [
        ('output wire payload_reclaimable\n);', '''output wire payload_reclaimable,
    output wire [511:0] refusal_tdata,output wire [63:0] refusal_tkeep,
    output wire refusal_tvalid,input wire refusal_tready,output wire refusal_tlast,
    output wire [USER_WIDTH-1:0] refusal_tuser,output wire refusal_history,
    input wire discard_frame_valid,input wire [30:0] discard_frame_stream,
    input wire [USER_WIDTH-1:0] discard_frame_user,output wire discard_frame_done
);'''),
        ('localparam IDLE=', declarations+'\nlocalparam IDLE='),
        ('assign header_valid=a_result_valid&&!a_result_is_reset;',
         'assign header_valid=a_result_valid&&!a_result_is_reset&&(!fence_refusal||refusal_reserved);'),
        (':header_ready;\n    assign header_status=', ':header_ready&&(!fence_refusal||refusal_reserved);\n    assign header_status='),
        ('if(header_status!=0)begin packet_fatal<=1;header_pending<=0;end',
         'if(header_status!=0)begin if(!fence_refusal)packet_fatal<=1;header_pending<=0;end'),
        ('assign p_s_valid=state==RUN&&!packet_fatal&&!receive_fault_valid&&(eos_pending||!header_pending',
         'assign p_s_valid=state==RUN&&!packet_fatal&&!receive_fault_valid&&(eos_pending||!dropped_data&&!header_pending'),
        ('control_event?control_event_ready:packet_fatal||!(data_byte||data_eos)||p_s_ready',
         'control_event?control_event_ready:packet_fatal||dropped_data||!(data_byte||data_eos)||p_s_ready'),
        ('assign idle=state==IDLE&&control_owner==0&&a_idle&&h_idle&&r_idle&&p_idle&&!header_pending;',
         'assign idle=state==IDLE&&control_owner==0&&a_idle&&h_idle&&r_idle&&p_idle&&!header_pending&&!refusal_pending&&!refusal_reserved;'),
    ]


def keyed_edits():
    return [
        ('output wire [31:0] rsp_generation\n);',
         'output wire [31:0] rsp_generation,\n    input wire allow_closed_discard,output wire rsp_discarded\n);'),
        ('localparam IDLE=0,PREPARE=1,PRECHECK_SEND=2,PRECHECK_WAIT=3,SCAN_REQ=4,SCAN_WAIT=5,\n    SCAN_CHECK=6,COMMAND_SEND=7,COMMAND_WAIT=8,LOCAL_RESULT=9;',
         'localparam IDLE=0,PREPARE=1,PRECHECK_SEND=2,PRECHECK_WAIT=3,SCAN_REQ=4,SCAN_WAIT=5,\n    SCAN_CHECK=6,COMMAND_SEND=7,COMMAND_WAIT=8,LOCAL_RESULT=9,HISTORY_REQ=10,HISTORY_WAIT=11;\nreg held_allow_discard,discarded_binding;'),
        ('assign selected_scan=state==SCAN_REQ||state==SCAN_WAIT||state==SCAN_CHECK;',
         'assign selected_scan=state==SCAN_REQ||state==SCAN_WAIT||state==SCAN_CHECK||state==HISTORY_REQ||state==HISTORY_WAIT;'),
        ('assign scan_word_address=scan_address+word_index*8;',
         'assign scan_word_address=(state==HISTORY_REQ||state==HISTORY_WAIT)?held_cfg_context_base+(held_req_user<<8)+160:scan_address+word_index*8;'),
        ('.req_valid(state==SCAN_REQ)', '.req_valid(state==SCAN_REQ||state==HISTORY_REQ)'),
        ('.result_ready(state==SCAN_WAIT)', '.result_ready(state==SCAN_WAIT||state==HISTORY_WAIT)'),
        ('assign rsp_binding_valid=rsp_valid&&rsp_status==0&&held_req_stream!=0&&resolved_generation!=0;',
         'assign rsp_binding_valid=rsp_valid&&rsp_status==0&&held_req_stream!=0&&resolved_generation!=0;\nassign rsp_discarded=state==COMMAND_WAIT&&c_rsp_valid&&c_rsp_status==0&&discarded_binding;'),
        ('else local_fail(3,10,0,0);', 'else if(held_allow_discard&&held_req_op==2)state<=HISTORY_REQ;\n        else local_fail(3,10,0,0);'),
        ('state<=IDLE;held_cfg_payload_base<=0;', 'state<=IDLE;held_allow_discard<=0;discarded_binding<=0;held_cfg_payload_base<=0;'),
        ('held_cfg_payload_base<=cfg_payload_base;', 'held_allow_discard<=allow_closed_discard;discarded_binding<=0;held_cfg_payload_base<=cfg_payload_base;'),
        ('        SCAN_CHECK:if(record_data', '''        HISTORY_REQ:if(scan_slot_ready)state<=HISTORY_WAIT;
        HISTORY_WAIT:if(scan_slot_valid)begin
            if(scan_slot_status!=0)local_fail(5,22,scan_slot_status,1);
            else if(scan_slot_data[31:0]!=32'h48325731||scan_slot_data[63])local_fail(5,23,0,1);
            else if(!held_req_stream[0]||held_req_stream>scan_slot_data[62:32])local_fail(3,10,0,0);
            else begin discarded_binding<=1;resolved_address<=0;resolved_generation<=0;state<=COMMAND_SEND;end
        end
        SCAN_CHECK:if(record_data'''),
        ('.req_op(state==PRECHECK_SEND?4\'d8:held_req_op)', '.req_op(state==PRECHECK_SEND?4\'d8:discarded_binding?4\'d6:held_req_op)'),
        ('.req_stream(state==PRECHECK_SEND?31\'d0:held_req_stream)', '.req_stream(state==PRECHECK_SEND||discarded_binding?31\'d0:held_req_stream)'),
    ]


def flow_edits():
    return [
        ('input wire [31:0] result_http2_error,input wire result_debit_authorized,', '''input wire [31:0] result_http2_error,input wire result_debit_authorized,
    input wire result_discarded,input wire discard_frame_done,output wire discard_frame_valid,
    output reg [30:0] discard_frame_stream,output reg [USER_WIDTH-1:0] discard_frame_user,
    output wire packet_gap_quiescent,'''),
        ('localparam IDLE=0,SEND=1,WAIT=2,FLOW=3,INIT_RESULT=4,REPLAY_RESULT=5;',
         'localparam IDLE=0,SEND=1,WAIT=2,FLOW=3,INIT_RESULT=4,REPLAY_RESULT=5,DROP_START_ACK=6,DROP_END_ACK=7;'),
        ('localparam INITIALIZE=0,DEBIT=1,RELEASE=2,UPDATE_STREAM=3,UPDATE_CONNECTION=4,RETIRE_UPDATE=5;',
         'localparam INITIALIZE=0,DEBIT=1,RELEASE=2,UPDATE_STREAM=3,UPDATE_CONNECTION=4,RETIRE_UPDATE=5,DROP_RELEASE=6,DROP_UPDATE=7;\nreg discard_active,discard_meta_seen;reg [23:0] discard_length;reg [7:0] discard_flags;\nassign discard_frame_valid=discard_active;\n// Private memory maintenance can run between packets while a DATA frame\n// persists. This is not reload/epoch authority and never asserts public idle.\nassign packet_gap_quiescent=state==IDLE&&!init_valid&&!s_valid&&!replay_valid&&(frame_active||discard_active);'),
        ('assign s_ready=!rst&&state==FLOW&&m_ready;',
         'assign s_ready=!rst&&(state==FLOW&&m_ready||state==DROP_START_ACK||state==DROP_END_ACK);'),
        ('&&!frame_active;', '&&!frame_active&&!discard_active;'),
        ('state<=IDLE;operation<=0;status<=0;',
         'state<=IDLE;operation<=0;discard_active<=0;discard_meta_seen<=0;discard_length<=0;discard_flags<=0;discard_frame_stream<=0;discard_frame_user<=0;status<=0;'),
        ('        end else case(state)', '        end else begin\n        if(discard_frame_done)discard_active<=0;\n        case(state)'),
        ('                end else if(s_valid&&(s_type!=0||s_kind!=0||admit_data))begin', '''                end else if(discard_active&&s_valid&&s_type==0&&s_kind==3)begin
                    if(!discard_meta_seen||s_stream!=discard_frame_stream||s_user!=discard_frame_user||s_length!=discard_length||s_flags!=discard_flags)begin
                        remember_fault(8,35,0,2);state<=FLOW;
                    end else begin
                        request_is_init<=0;request_is_close<=0;request_keyed<=0;request_maintenance<=0;
                        request_user<=discard_frame_user;request_stream<=0;request_generation<=0;request_address<=0;
                        operation<=DROP_RELEASE;command(7,{8'd0,discard_length});
                    end
                end else if(discard_active&&s_valid&&s_type==0&&s_kind==1)begin
                    if(discard_meta_seen||s_stream!=discard_frame_stream||s_user!=discard_frame_user||s_length!=discard_length||
                        s_flags!=discard_flags||s_arg1!=0||s_arg0>{8'd0,discard_length}||
                        (discard_flags[3]?({8'd0,discard_length}-s_arg0<1||{8'd0,discard_length}-s_arg0>256):s_arg0!={8'd0,discard_length}))
                        remember_fault(8,36,0,2);
                    discard_meta_seen<=1;state<=DROP_START_ACK;
                end else if(s_valid&&(s_type!=0||s_kind!=0||admit_data))begin'''),
        ('                    DEBIT:state<=FLOW;', '''                    DEBIT:if(result_discarded)begin
                        discard_active<=1;discard_meta_seen<=0;discard_frame_stream<=m_stream;discard_frame_user<=m_user;
                        discard_length<=m_length;discard_flags<=m_flags;state<=DROP_START_ACK;
                    end else state<=FLOW;
                    DROP_RELEASE:begin operation<=DROP_UPDATE;command(4,0);end
                    DROP_UPDATE:state<=DROP_END_ACK;'''),
        ('state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:REPLAY_RESULT;',
         'state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:(operation==DROP_RELEASE||operation==DROP_UPDATE)?DROP_END_ACK:REPLAY_RESULT;'),
        ('            INIT_RESULT:if(init_result_ready)', '''            DROP_START_ACK:if(s_valid)state<=IDLE;
            DROP_END_ACK:if(s_valid)state<=IDLE;
            INIT_RESULT:if(init_result_ready)'''),
        ('        endcase\n    end\nendmodule', '''        endcase
        // An explicit connection abort may abandon semantic events only once
        // accepted memory commands and their responses have drained.
        if(abort_flow&&discard_active&&state!=SEND&&state!=WAIT)begin discard_active<=0;state<=IDLE;end
        end
    end
endmodule'''),
    ]


def core_edits():
    decl = '''wire [511:0] refusal_tdata,refusal_base_tdata;
wire [63:0] refusal_tkeep,refusal_base_tkeep;
wire refusal_tvalid,refusal_tready,refusal_tlast,refusal_history;
wire refusal_base_tvalid,refusal_base_tready,refusal_base_tlast,refusal_wire_idle;
wire [USER_WIDTH-1:0] refusal_tuser,refusal_base_tuser;
wire rx_discarded,rx_drop_valid,rx_drop_done,rx_packet_gap_quiescent;
wire [30:0] rx_drop_stream;wire [USER_WIDTH-1:0] rx_drop_user;
'''
    result = [
        (');\n', ');\n'+decl),
        ('.receive_data_admit(receive_data_admit)', '''.receive_data_admit(receive_data_admit),
    .refusal_tdata(refusal_tdata),.refusal_tkeep(refusal_tkeep),.refusal_tvalid(refusal_tvalid),
    .refusal_tready(refusal_tready),.refusal_tlast(refusal_tlast),.refusal_tuser(refusal_tuser),
    .refusal_history(refusal_history),.discard_frame_valid(rx_drop_valid),
    .discard_frame_stream(rx_drop_stream),.discard_frame_user(rx_drop_user),.discard_frame_done(rx_drop_done)'''),
        ('.rsp_generation()\n);', '.rsp_generation(),.allow_closed_discard(refusal_history),.rsp_discarded(rx_discarded)\n);'),
        ('.admit_data(receive_data_admit)', '.admit_data(receive_data_admit&&!rx_drop_valid)'),
        ('.result_debit_authorized(rx_result_debit_authorized),\n    .fault_valid(rc_flow_fault_valid)', '''.result_debit_authorized(rx_result_debit_authorized),
    .result_discarded(rx_discarded),.discard_frame_done(rx_drop_done),.discard_frame_valid(rx_drop_valid),
    .discard_frame_stream(rx_drop_stream),.discard_frame_user(rx_drop_user),.packet_gap_quiescent(rx_packet_gap_quiescent),
    .fault_valid(rc_flow_fault_valid)'''),
        ('assign idle=!rc_fence&&', 'assign idle=refusal_wire_idle&&!rc_fence&&'),
        ('assign cfg_quiescent=f_cfg_quiescent&&allow_config;',
         'assign cfg_quiescent=f_cfg_quiescent&&allow_config&&receive_controller_idle&&refusal_wire_idle;'),
        ('    receive_controller_idle&&receive_pool_gate_idle&&rc_backend_idle&&',
         '    (receive_controller_idle||rx_packet_gap_quiescent)&&receive_pool_gate_idle&&rc_backend_idle&&'),
    ]
    # Only the final existing arbiter drives these public wire ports. The new
    # arbiter adds no queue: a source ACK remains the actual wire handshake.
    for field in ('tdata','tkeep','tvalid','tready','tlast','tuser'):
        result.append(('.m_axis_'+field+'(m_axis_tx_'+field+')', '.m_axis_'+field+'(refusal_base_'+field+')'))
    result.append(('endmodule', '''axis_frame_arbiter #(.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)) refusal_wire(
    .clk(clk),.rst(rst),.idle(refusal_wire_idle),
    .a_axis_tdata(refusal_base_tdata),.a_axis_tkeep(refusal_base_tkeep),.a_axis_tvalid(refusal_base_tvalid),
    .a_axis_tready(refusal_base_tready),.a_axis_tlast(refusal_base_tlast),.a_axis_tuser(refusal_base_tuser),
    .b_axis_tdata(refusal_tdata),.b_axis_tkeep(refusal_tkeep),.b_axis_tvalid(refusal_tvalid),
    .b_axis_tready(refusal_tready),.b_axis_tlast(refusal_tlast),.b_axis_tuser(refusal_tuser),
    .m_axis_tdata(m_axis_tx_tdata),.m_axis_tkeep(m_axis_tx_tkeep),.m_axis_tvalid(m_axis_tx_tvalid),
    .m_axis_tready(m_axis_tx_tready),.m_axis_tlast(m_axis_tx_tlast),.m_axis_tuser(m_axis_tx_tuser));
endmodule'''))
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',default='rpc-stream-refusal-v1');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];parent=root/'build/experiments/rpc-admission-fence-v1'
    target=root/'build/experiments'/args.name
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    manifest=read(parent/'generation.json');audit=read(root/'build/validation/rpc-admission-fence.json')
    failure=read(root/'build/validation/rpc-admission-fence-failure.json')
    assert audit['key']=='1e606bcd79f8f20a' and failure['key']=='d246ef849f723296'
    assert sha(parent/'generation.json')==audit['generation_sha256']
    target.mkdir(parents=True,exist_ok=False)
    for name,digest in manifest['outputs_sha256'].items():
        assert sha(parent/name)==digest,name
        p=target/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/name,p)
    certificates={}
    for module,edits in {'http2_classified_parser_transport':transport_edits(),
        'http2_keyed_receive_credit_store':keyed_edits(),'http2_receive_flow_controller':flow_edits(),
        'http2_enveloped_parser_core':core_edits()}.items():
        name='joint/rtl/'+module+'.v';p=target/name;original=p.read_bytes().decode();updated=original
        applied=[]
        for before,after in edits:
            if '\r\n' in original:before=before.replace('\n','\r\n');after=after.replace('\n','\r\n')
            count=updated.count(before)
            if module=='http2_enveloped_parser_core' and before==');\n':
                assert count>1;updated=updated.replace(before,after,1);count=1
            else:
                assert count==1,(module,before,count)
                updated=updated.replace(before,after)
            applied.append([before,after])
        inverse=updated
        for before,after in reversed(applied):
            assert inverse.count(after)==1,(module,after)
            inverse=inverse.replace(after,before)
        assert inverse==original
        old_ports=ports(original,module);new_ports=ports(updated,module)
        if module=='http2_enveloped_parser_core':assert new_ports==old_ports
        else:assert all(port in new_ports for port in old_ports)
        ordered,order_certificate=order_declarations(updated)
        verify_order(updated,ordered,order_certificate)
        assert ports(ordered,module)==new_ports
        p.write_bytes(ordered.encode());certificates[name]=dict(before_sha256=sha(parent/name),after_sha256=sha(p),replacements=applied,
            edited_preorder_sha256=hashlib.sha256(updated.encode()).hexdigest(),declaration_order_certificate=order_certificate)
    parser=closure('http2_schema_mmio_application',target/'joint');plain=closure('http2_enveloped_parser_application',target/'joint')
    tokenizer=closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',target/'joint')
    assert len(parser)==79 and len(plain)==78 and len(tokenizer)==31
    assert {n:sha(p)for n,p in tokenizer.items()}==manifest['canonical_tokenizer_sha256']
    changed={n for n,h in manifest['outputs_sha256'].items()if sha(target/n)!=h}
    assert changed==set(certificates)
    fault_parent=None
    if args.name=='rpc-stream-refusal-v7':
        v6=root/'build/experiments/rpc-stream-refusal-v6';v6_generation=read(v6/'generation.json')
        assert {n for n,p in plain.items() if sha(p)!=v6_generation['non_mmio_parser_sha256'][n]}=={'http2_receive_flow_controller'}
        before=(v6/'joint/rtl/http2_receive_flow_controller.v').read_text()
        after=(target/'joint/rtl/http2_receive_flow_controller.v').read_text()
        old_line='state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:REPLAY_RESULT;'
        new_line='state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:(operation==DROP_RELEASE||operation==DROP_UPDATE)?DROP_END_ACK:REPLAY_RESULT;'
        assert before.count(old_line)==1 and before.replace(old_line,new_line)==after
        fault_parent=dict(generation_sha256=sha(v6/'generation.json'),
            fault_run='rpc_stream_refusal_v6_faults_20261122',actual_failed_ack=45,
            original_line=old_line,replacement_line=new_line,
            changed_module='http2_receive_flow_controller',default_open_equivalence_verified=False)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    result=dict(phase='stream_local_refusal_generated_runtime_unverified',parent_generation_sha256=sha(parent/'generation.json'),
        parent_assembly_audit_key=audit['key'],counterexample_audit_key=failure['key'],source_edit_certificates=certificates,
        canonical_parser_sha256={n:sha(p)for n,p in parser.items()},non_mmio_parser_sha256={n:sha(p)for n,p in plain.items()},
        canonical_tokenizer_sha256={n:sha(p)for n,p in tokenizer.items()},parser_modules=79,non_mmio_parser_modules=78,tokenizer_modules=31,
        functional_runtime_verified=False,native_timing_verified=False,whole_rpc_gpu_maintenance_authority_verified=False,full_system_complete=False,
        receive_fault_fix_parent=fault_parent,
        generator_sha256=sha(Path(__file__)))
    result['outputs_sha256']={p.relative_to(target).as_posix():sha(p)for p in target.rglob('*')if p.is_file()}
    (target/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ('phase','parser_modules','non_mmio_parser_modules','tokenizer_modules')}))


if __name__=='__main__':main()
