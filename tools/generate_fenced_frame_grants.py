"""Add a keyed reservation freeze and join it to the actual DATA wire path."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import add_ports, named_instance


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'rtl/http2_cancel_frame_grants.v'
    text = source.read_text().replace('http2_cancel_frame_grants', 'http2_fenced_frame_grants')
    extra = [('input', '', 'freeze_valid'), ('output', '', 'freeze_ready'),
        ('input', '[USER_WIDTH-1:0]', 'freeze_user'), ('input', '[30:0]', 'freeze_stream'),
        ('output', '', 'freeze_active'), ('output', '', 'freeze_drained'),
        ('output', '', 'freeze_binding_valid'), ('output', '[MEMORY_ADDR_WIDTH-1:0]', 'freeze_record_address'),
        ('output', '[31:0]', 'freeze_generation'), ('input', '', 'freeze_release_valid'),
        ('output', '', 'freeze_release_ready'), ('input', '', 'frame_tx_done'),
        ('output', '', 'frame_wire_pending'), ('output', '', 'frame_tracking_error')]
    text = add_ports(text, 'http2_fenced_frame_grants', extra)
    text = replace_once(text, 'localparam IDLE=0,CONTROL=1,RESERVE=2;', '''// frame_tx_done MUST be the real DATA-source wire TLAST handshake, never an enqueue.
// One positive reservation is owned until that handshake. No credit is refunded.
// External RESERVE (op 5) is withheld: only this scheduler may reserve DATA credit.
// A freeze accepts a wire key, blocks a same-edge new reservation/start, and
// preserves an already-dispatched reservation, all memory ACKs and its DATA frame.
// The parent must close the resolved stream after freeze_drained, then release
// this fence so a waiting framer receives the durable STREAM_CLOSED result.
// This is not a GPU/RPC cancellation controller. Reset requires a global fence.
localparam IDLE=0,CONTROL=1,RESERVE=2;
reg frozen,wire_pending,tracking_error;
reg [USER_WIDTH-1:0] frozen_user;
reg [30:0] frozen_stream;
wire freeze_take=freeze_valid&&freeze_ready;
wire saved_frame_match=frozen&&frame_owner==frozen_user&&frame_stream==frozen_stream;
wire incoming_frame_match=freeze_take&&frame_owner==freeze_user&&frame_stream==freeze_stream;
wire frame_frozen=saved_frame_match||incoming_frame_match;
wire start_frozen=(frozen&&start_user==frozen_user&&start_stream==frozen_stream)||
    (freeze_take&&start_user==freeze_user&&start_stream==freeze_stream);
wire control_matches_frame=frame_active&&window_req_user==frame_owner&&window_req_stream==frame_stream;
wire close_control=window_req_op==8||window_req_op==10;
wire control_allowed=window_req_op!=5&&(!close_control||!control_matches_frame||
    (saved_frame_match&&!wire_pending&&!tracking_error));
wire control_pending=window_req_valid&&control_allowed;
assign freeze_ready=!rst&&!frozen&&!tracking_error&&freeze_stream!=0;
assign freeze_active=frozen;
assign freeze_drained=!rst&&frozen&&!tracking_error&&
    (!saved_frame_match||(!wire_pending&&state!=RESERVE));
assign freeze_binding_valid=freeze_drained&&frame_active&&saved_frame_match;
assign freeze_record_address=freeze_binding_valid?frame_address:0;
assign freeze_generation=freeze_binding_valid?frame_generation:0;
assign freeze_release_ready=freeze_drained&&state==IDLE&&!window_busy;
assign frame_wire_pending=wire_pending;
assign frame_tracking_error=tracking_error;
always @(posedge clk)begin
    if(rst)begin frozen<=0;wire_pending<=0;tracking_error<=0;frozen_user<=0;frozen_stream<=0;end
    else begin
        if(freeze_take)begin frozen<=1;frozen_user<=freeze_user;frozen_stream<=freeze_stream;end
        if(freeze_release_valid&&freeze_release_ready)frozen<=0;
        if(frame_tx_done)begin
            if(!wire_pending)tracking_error<=1;
            else wire_pending<=0;
        end
        if(frame_request_valid&&frame_request_ready&&owned_window_rsp_status==0)begin
            if(wire_pending||frame_tx_done||owned_window_rsp_grant_bytes==0)tracking_error<=1;
            wire_pending<=1;
        end
    end
end''')
    substitutions = (
        ('assign credit_binding_active=frame_active;assign finish_ready=state==IDLE&&!window_busy;',
         'assign credit_binding_active=frame_active;assign finish_ready=state==IDLE&&!window_busy&&!wire_pending&&!tracking_error;'),
        ('wire reserve_pending=frame_active&&frame_request_valid&&!parked&&frame_req_user==frame_owner&&frame_req_stream==frame_stream;',
         'wire reserve_pending=frame_active&&frame_request_valid&&!parked&&!frame_frozen&&!wire_pending&&!tracking_error&&frame_req_user==frame_owner&&frame_req_stream==frame_stream;'),
        ('wire select_control=window_req_valid;', 'wire select_control=control_pending;'),
        ('assign start_ready=!rst&&!frame_active&&lease_matches;',
         'assign start_ready=!rst&&!frame_active&&!start_frozen&&!tracking_error&&lease_matches;'),
        ('assign window_req_ready=!rst&&state==IDLE&&owned_request_ready;',
         'assign window_req_ready=!rst&&state==IDLE&&owned_request_ready&&control_allowed;'),
        ('assign idle=owned_idle&&state==IDLE&&!frame_active&&!start_valid;',
         'assign idle=owned_idle&&state==IDLE&&!frame_active&&!start_valid&&!frozen&&!wire_pending&&!tracking_error;'),
        ('.window_req_valid(!rst&&state==IDLE&&(window_req_valid||reserve_pending))',
         '.window_req_valid(!rst&&state==IDLE&&(control_pending||reserve_pending))'),
        ('IDLE:if(owned_request_ready&&(window_req_valid||reserve_pending))state<=window_req_valid?CONTROL:RESERVE;',
         'IDLE:if(owned_request_ready&&(control_pending||reserve_pending))state<=control_pending?CONTROL:RESERVE;'),
    )
    for old,new in substitutions:text=replace_once(text,old,new)
    scheduler = root / 'rtl/http2_fenced_frame_grants.v';scheduler.write_text(text)

    sched_ports=ports(text,'http2_fenced_frame_grants')
    framer_path=root/'rtl/grpc_http2_response_framer.v';framer_ports=ports(framer_path.read_text(),'grpc_http2_response_framer')
    arb_path=root/'rtl/axis_cancellable_frame_arbiter.v';arb_ports=ports(arb_path.read_text(),'axis_cancellable_frame_arbiter')
    hidden={'start_valid','start_ready','start_user','start_stream','finish_valid','finish_ready','frame_tx_done','idle',
        'frame_req_valid','frame_req_ready','frame_req_user','frame_req_stream','frame_req_max_bytes','frame_grant_bytes'}
    public=[p for p in sched_ports if p[2]not in hidden]
    public += [p for p in framer_ports if p[2]not in {'clk','rst','idle','frame_req_valid','frame_req_ready','frame_req_user',
        'frame_req_stream','frame_req_max_bytes','frame_grant_bytes'}]
    public += [(d,w.replace('DATA_WIDTH','512').replace('KEEP_WIDTH','64'),n)
        for d,w,n in arb_ports if n.startswith('b_axis_')]
    public += [('output','','idle'),('output','','data_wire_paused')]
    assert len(public)==len({n for _,_,n in public})
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Actual owned directory, durable grants, DATA framer and direct wire arbiter.',
        '// freeze_drained includes every previously dispatched DATA reservation/wire frame.',
        '// The parent supplies key closure and complete GPU/RPC cancellation/lifetime handling.',
        'module grpc_cancellable_window_framer #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_MESSAGE_BYTES=65535',')(',
        ',\n'.join(f'    {d} wire {w} {n}'for d,w,n in public),');',
        'wire scheduler_start_ready,framer_start_ready,scheduler_finish_ready,scheduler_idle,framer_idle,arb_idle;',
        'wire framer_result_valid;wire frame_req_valid,frame_req_ready;wire [USER_WIDTH-1:0] frame_req_user;',
        'wire [30:0] frame_req_stream;wire [23:0] frame_req_max_bytes,frame_grant_bytes;',
        'wire [511:0] data_tdata;wire [63:0] data_tkeep;wire data_tvalid,data_tready,data_tlast;',
        'wire [USER_WIDTH-1:0] data_tuser;',
        'assign start_ready=scheduler_start_ready&&framer_start_ready;',
        'assign result_valid=framer_result_valid&&scheduler_finish_ready;',
        'assign idle=scheduler_idle&&framer_idle&&arb_idle;']
    sc={n:n for _,_,n in sched_ports};sc.update(start_valid='start_valid&&framer_start_ready',start_ready='scheduler_start_ready',
        finish_valid='framer_result_valid&&result_ready',finish_ready='scheduler_finish_ready',idle='scheduler_idle',
        frame_tx_done='data_tvalid&&data_tready&&data_tlast')
    lines += [named_instance('http2_fenced_frame_grants','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','credits',sc)]
    fc={n:n for _,_,n in framer_ports};fc.update(start_valid='start_valid&&scheduler_start_ready',start_ready='framer_start_ready',
        result_valid='framer_result_valid',result_ready='result_ready&&scheduler_finish_ready',idle='framer_idle')
    fc.update({f'm_axis_tx_{n}':f'data_{n}'for n in('tdata','tkeep','tvalid','tready','tlast','tuser')})
    lines += [named_instance('grpc_http2_response_framer','.USER_WIDTH(USER_WIDTH),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)','framer',fc)]
    ac={n:n for _,_,n in arb_ports};ac.update(idle='arb_idle',a_pause='freeze_binding_valid&&freeze_drained',a_paused='data_wire_paused')
    ac.update({f'a_axis_{n}':f'data_{n}'for n in('tdata','tkeep','tvalid','tready','tlast','tuser')})
    ac.update({f'm_axis_{n}':f'm_axis_tx_{n}'for n in('tdata','tkeep','tvalid','tready','tlast','tuser')})
    lines += [named_instance('axis_cancellable_frame_arbiter','.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)','wire_arbiter',ac),
        'endmodule','`default_nettype wire','']
    target=root/'rtl/grpc_cancellable_window_framer.v';target.write_text('\n'.join(lines))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='generated_keyed_freeze_and_actual_wire_framer',
        input_sha256={p.relative_to(root).as_posix():sha(p)for p in(source,framer_path,arb_path,Path(__file__))},
        generated_sha256={p.relative_to(root).as_posix():sha(p)for p in(scheduler,target)},
        positive_grant_owned_until_actual_wire_tlast=True,same_edge_freeze_blocks_dispatch=True,
        external_reserve_withheld=True,actual_rst_controller_integrated=False,full_system_complete=False)
    (root/'build/validation/fenced-frame-grants-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated reservation freeze and actual DATA-wire/framer join')


if __name__=='__main__':main()
