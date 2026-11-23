`timescale 1ns/1ps
`default_nettype none
// Actual cached LOAD/pool grant + durable credit scheduler; frame_req is already authorized.
module http2_fenced_pipelined_grants #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(
    input wire  clk,
    input wire  rst,
    input wire  req_valid,
    output wire  req_ready,
    input wire [2:0] req_op,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes,
    input wire [USER_WIDTH-1:0] req_user,
    input wire [USER_WIDTH-1:0] req_application,
    input wire [30:0] req_stream,
    input wire [31:0] req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_address,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_buffer_base,
    input wire [MEMORY_ADDR_WIDTH:0] req_buffer_bytes,
    input wire [31:0] req_message_limit,
    input wire  req_protobuf,
    input wire  req_unsupported_encoding,
    input wire  req_maintenance,
    input wire [255:0] req_state,
    output wire  rsp_valid,
    input wire  rsp_ready,
    output wire [7:0] rsp_status,
    output wire [7:0] rsp_detail,
    output wire [7:0] rsp_memory_status,
    output wire [2:0] rsp_op,
    output wire [MEMORY_ADDR_WIDTH-1:0] rsp_address,
    output wire [MEMORY_ADDR_WIDTH-1:0] rsp_buffer_base,
    output wire [MEMORY_ADDR_WIDTH:0] rsp_buffer_bytes,
    output wire [USER_WIDTH-1:0] rsp_user,
    output wire [USER_WIDTH-1:0] rsp_application,
    output wire [30:0] rsp_stream,
    output wire [31:0] rsp_generation,
    output wire [31:0] rsp_message_limit,
    output wire  rsp_protobuf,
    output wire  rsp_unsupported_encoding,
    output wire [255:0] rsp_state,
    output wire  recovery_required,
    output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    input wire  lease_valid,
    output wire  lease_ready,
    input wire [USER_WIDTH-1:0] lease_user,
    input wire [30:0] lease_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] lease_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] lease_pool_bytes,
    input wire  lease_rsp_ready,
    output wire  lease_active,
    output wire  lease_rsp_valid,
    output wire [7:0] lease_rsp_status,
    output wire [7:0] lease_rsp_detail,
    output wire [7:0] lease_rsp_memory_status,
    output wire [2:0] lease_rsp_op,
    output wire [MEMORY_ADDR_WIDTH-1:0] lease_rsp_address,
    output wire [MEMORY_ADDR_WIDTH-1:0] lease_rsp_buffer_base,
    output wire [MEMORY_ADDR_WIDTH:0] lease_rsp_buffer_bytes,
    output wire [USER_WIDTH-1:0] lease_rsp_user,
    output wire [USER_WIDTH-1:0] lease_rsp_application,
    output wire [30:0] lease_rsp_stream,
    output wire [31:0] lease_rsp_generation,
    output wire [31:0] lease_rsp_message_limit,
    output wire  lease_rsp_protobuf,
    output wire  lease_rsp_unsupported_encoding,
    output wire [255:0] lease_rsp_state,
    input wire  window_req_valid,
    output wire  window_req_ready,
    input wire [3:0] window_req_op,
    input wire  window_req_maintenance,
    input wire [USER_WIDTH-1:0] window_req_user,
    input wire [30:0] window_req_stream,
    input wire [31:0] window_req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] window_req_record_address,
    input wire [31:0] window_req_amount,
    input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_context_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_stream_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_window_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] window_cfg_context_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] window_cfg_stream_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] window_cfg_window_bytes,
    output wire  window_rsp_valid,
    input wire  window_rsp_ready,
    output wire [3:0] window_rsp_op,
    output wire [USER_WIDTH-1:0] window_rsp_user,
    output wire [30:0] window_rsp_stream,
    output wire [7:0] window_rsp_status,
    output wire [7:0] window_rsp_detail,
    output wire [7:0] window_rsp_memory_status,
    output wire  window_rsp_connection_error,
    output wire [31:0] window_rsp_http2_error,
    output wire [23:0] window_rsp_grant_bytes,
    output wire [31:0] window_rsp_connection_window,
    output wire [31:0] window_rsp_initial_window,
    output wire [31:0] window_rsp_stream_window,
    output wire [23:0] window_rsp_max_frame_bytes,
    output wire [31:0] window_rsp_affected_streams,
    output wire  window_recovery_required,
    output wire [MEMORY_ADDR_WIDTH-1:0] window_recovery_address,
    output wire  window_busy,
    output wire [7:0] window_lock_status,
    output wire  directory_pool_lock_active,
    output wire [2*1-1:0] mem_valid,
    input wire [2*1-1:0] mem_ready,
    output wire [2*1-1:0] mem_write,
    output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [2*4-1:0] mem_bytes,
    output wire [2*72-1:0] mem_data,
    input wire [2*1-1:0] mem_rsp_valid,
    output wire [2*1-1:0] mem_rsp_ready,
    input wire [2*72-1:0] mem_rsp_data,
    input wire [2*8-1:0] mem_rsp_status,
    input wire  start_valid,
    output wire  start_ready,
    input wire [USER_WIDTH-1:0] start_user,
    input wire [30:0] start_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] frame_cfg_context_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] frame_cfg_stream_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] frame_cfg_window_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] frame_cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] frame_cfg_context_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] frame_cfg_stream_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] frame_cfg_window_bytes,
    output wire  idle,
    output wire  credit_parked,
    output wire  credit_error_valid,
    input wire  credit_error_ready,
    output wire [USER_WIDTH-1:0] credit_error_user,
    output wire [30:0] credit_error_stream,
    output wire [7:0] credit_error_status,
    output wire [7:0] credit_error_detail,
    output wire [7:0] credit_error_memory_status,
    output wire  credit_error_connection_error,
    output wire [31:0] credit_error_http2_error,
    input wire  frame_req_valid,
    output wire  frame_req_ready,
    input wire [USER_WIDTH-1:0] frame_req_user,
    input wire [30:0] frame_req_stream,
    input wire [23:0] frame_req_max_bytes,
    output wire [23:0] frame_grant_bytes,
    input wire  finish_valid,
    output wire  finish_ready,
    output wire  credit_binding_active
,
    output wire  window_rsp_binding_valid,
    output wire [MEMORY_ADDR_WIDTH-1:0] window_rsp_record_address,
    output wire [31:0] window_rsp_generation,
    output wire  window_rsp_send_closed
,
    input wire  freeze_valid,
    output wire  freeze_ready,
    input wire [USER_WIDTH-1:0] freeze_user,
    input wire [30:0] freeze_stream,
    output wire  freeze_active,
    output wire  freeze_drained,
    output wire  freeze_binding_valid,
    output wire [MEMORY_ADDR_WIDTH-1:0] freeze_record_address,
    output wire [31:0] freeze_generation,
    input wire  freeze_release_valid,
    output wire  freeze_release_ready,
    input wire  frame_tx_done,
    output wire  frame_wire_pending,
    output wire  frame_tracking_error
);

// frame_tx_done MUST be the real DATA-source wire TLAST handshake, never an enqueue.
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
end
reg [1:0] state;reg frame_active,parked;
reg [USER_WIDTH-1:0] frame_owner;reg [30:0] frame_stream;
reg [31:0] frame_generation;reg [MEMORY_ADDR_WIDTH-1:0] frame_address;
wire owned_idle,owned_request_ready,owned_result_valid,owned_result_ready;
wire frame_request_valid=frame_req_valid;wire frame_request_ready;
wire [23:0] frame_request_maximum=frame_req_max_bytes;wire [23:0] grant_bytes;
assign frame_req_ready=frame_request_ready;assign frame_grant_bytes=grant_bytes;
assign credit_binding_active=frame_active;assign finish_ready=state==IDLE&&!window_busy&&!wire_pending&&!tracking_error;
wire lease_matches=lease_rsp_valid&&lease_rsp_status==0&&lease_rsp_user==start_user&&lease_rsp_stream==start_stream;
wire reserve_pending=frame_active&&frame_request_valid&&!parked&&!frame_frozen&&!wire_pending&&!tracking_error&&frame_req_user==frame_owner&&frame_req_stream==frame_stream;
wire select_control=control_pending;
assign start_ready=!rst&&!frame_active&&!start_frozen&&!tracking_error&&lease_matches;
assign window_req_ready=!rst&&state==IDLE&&owned_request_ready&&control_allowed;
assign window_rsp_valid=state==CONTROL&&owned_result_valid;
assign credit_parked=parked;
assign credit_error_valid=state==RESERVE&&owned_result_valid&&owned_window_rsp_status>1;
assign frame_request_ready=state==RESERVE&&owned_result_valid&&
    (owned_window_rsp_status==0||(owned_window_rsp_status>1&&credit_error_ready));
assign grant_bytes=owned_window_rsp_status==0?owned_window_rsp_grant_bytes:24'd0;
assign owned_result_ready=state==CONTROL?window_rsp_ready:
    state==RESERVE&&(owned_window_rsp_status==1||frame_request_valid&&frame_request_ready);
assign idle=owned_idle&&state==IDLE&&!frame_active&&!start_valid&&!frozen&&!wire_pending&&!tracking_error;
wire [3:0] owned_window_rsp_op;
assign window_rsp_op=owned_window_rsp_op;
wire [USER_WIDTH-1:0] owned_window_rsp_user;
assign window_rsp_user=owned_window_rsp_user;
wire [30:0] owned_window_rsp_stream;
assign window_rsp_stream=owned_window_rsp_stream;
wire [7:0] owned_window_rsp_status;
assign window_rsp_status=owned_window_rsp_status;
wire [7:0] owned_window_rsp_detail;
assign window_rsp_detail=owned_window_rsp_detail;
wire [7:0] owned_window_rsp_memory_status;
assign window_rsp_memory_status=owned_window_rsp_memory_status;
wire  owned_window_rsp_connection_error;
assign window_rsp_connection_error=owned_window_rsp_connection_error;
wire [31:0] owned_window_rsp_http2_error;
assign window_rsp_http2_error=owned_window_rsp_http2_error;
wire [23:0] owned_window_rsp_grant_bytes;
assign window_rsp_grant_bytes=owned_window_rsp_grant_bytes;
wire [31:0] owned_window_rsp_connection_window;
assign window_rsp_connection_window=owned_window_rsp_connection_window;
wire [31:0] owned_window_rsp_initial_window;
assign window_rsp_initial_window=owned_window_rsp_initial_window;
wire [31:0] owned_window_rsp_stream_window;
assign window_rsp_stream_window=owned_window_rsp_stream_window;
wire [23:0] owned_window_rsp_max_frame_bytes;
assign window_rsp_max_frame_bytes=owned_window_rsp_max_frame_bytes;
wire [31:0] owned_window_rsp_affected_streams;
assign window_rsp_affected_streams=owned_window_rsp_affected_streams;
assign credit_error_user=owned_window_rsp_user;
assign credit_error_stream=owned_window_rsp_stream;
assign credit_error_status=owned_window_rsp_status;
assign credit_error_detail=owned_window_rsp_detail;
assign credit_error_memory_status=owned_window_rsp_memory_status;
assign credit_error_connection_error=owned_window_rsp_connection_error;
assign credit_error_http2_error=owned_window_rsp_http2_error;
reg [MEMORY_ADDR_WIDTH-1:0] saved_frame_cfg_context_base;
reg [MEMORY_ADDR_WIDTH-1:0] saved_frame_cfg_stream_base;
reg [MEMORY_ADDR_WIDTH-1:0] saved_frame_cfg_window_base;
reg [MEMORY_ADDR_WIDTH-1:0] saved_frame_cfg_work_floor;
reg [MEMORY_ADDR_WIDTH:0] saved_frame_cfg_context_bytes;
reg [MEMORY_ADDR_WIDTH:0] saved_frame_cfg_stream_bytes;
reg [MEMORY_ADDR_WIDTH:0] saved_frame_cfg_window_bytes;
http2_owned_pipelined_cancel_windows #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) owned(
    .clk(clk),
    .rst(rst),
    .req_valid(req_valid),
    .req_ready(req_ready),
    .req_op(req_op),
    .cfg_pool_base(cfg_pool_base),
    .cfg_pool_bytes(cfg_pool_bytes),
    .req_user(req_user),
    .req_application(req_application),
    .req_stream(req_stream),
    .req_generation(req_generation),
    .req_address(req_address),
    .req_buffer_base(req_buffer_base),
    .req_buffer_bytes(req_buffer_bytes),
    .req_message_limit(req_message_limit),
    .req_protobuf(req_protobuf),
    .req_unsupported_encoding(req_unsupported_encoding),
    .req_maintenance(req_maintenance),
    .req_state(req_state),
    .rsp_valid(rsp_valid),
    .rsp_ready(rsp_ready),
    .rsp_status(rsp_status),
    .rsp_detail(rsp_detail),
    .rsp_memory_status(rsp_memory_status),
    .rsp_op(rsp_op),
    .rsp_address(rsp_address),
    .rsp_buffer_base(rsp_buffer_base),
    .rsp_buffer_bytes(rsp_buffer_bytes),
    .rsp_user(rsp_user),
    .rsp_application(rsp_application),
    .rsp_stream(rsp_stream),
    .rsp_generation(rsp_generation),
    .rsp_message_limit(rsp_message_limit),
    .rsp_protobuf(rsp_protobuf),
    .rsp_unsupported_encoding(rsp_unsupported_encoding),
    .rsp_state(rsp_state),
    .recovery_required(recovery_required),
    .recovery_address(recovery_address),
    .lease_valid(lease_valid),
    .lease_ready(lease_ready),
    .lease_user(lease_user),
    .lease_stream(lease_stream),
    .lease_pool_base(lease_pool_base),
    .lease_pool_bytes(lease_pool_bytes),
    .lease_rsp_ready(lease_rsp_ready&&(!frame_active||finish_valid)&&!start_valid&&finish_ready),
    .lease_active(lease_active),
    .lease_rsp_valid(lease_rsp_valid),
    .lease_rsp_status(lease_rsp_status),
    .lease_rsp_detail(lease_rsp_detail),
    .lease_rsp_memory_status(lease_rsp_memory_status),
    .lease_rsp_op(lease_rsp_op),
    .lease_rsp_address(lease_rsp_address),
    .lease_rsp_buffer_base(lease_rsp_buffer_base),
    .lease_rsp_buffer_bytes(lease_rsp_buffer_bytes),
    .lease_rsp_user(lease_rsp_user),
    .lease_rsp_application(lease_rsp_application),
    .lease_rsp_stream(lease_rsp_stream),
    .lease_rsp_generation(lease_rsp_generation),
    .lease_rsp_message_limit(lease_rsp_message_limit),
    .lease_rsp_protobuf(lease_rsp_protobuf),
    .lease_rsp_unsupported_encoding(lease_rsp_unsupported_encoding),
    .lease_rsp_state(lease_rsp_state),
    .window_req_valid(!rst&&state==IDLE&&(control_pending||reserve_pending)),
    .window_req_ready(owned_request_ready),
    .window_req_op(select_control?window_req_op:4'd5),
    .window_req_maintenance(select_control?window_req_maintenance:1'b0),
    .window_req_user(select_control?window_req_user:frame_owner),
    .window_req_stream(select_control?window_req_stream:frame_stream),
    .window_req_generation(select_control?window_req_generation:frame_generation),
    .window_req_record_address(select_control?window_req_record_address:frame_address),
    .window_req_amount(select_control?window_req_amount:{8'd0,frame_request_maximum}),
    .window_cfg_context_base(select_control?window_cfg_context_base:saved_frame_cfg_context_base),
    .window_cfg_stream_base(select_control?window_cfg_stream_base:saved_frame_cfg_stream_base),
    .window_cfg_window_base(select_control?window_cfg_window_base:saved_frame_cfg_window_base),
    .window_cfg_work_floor(select_control?window_cfg_work_floor:saved_frame_cfg_work_floor),
    .window_cfg_context_bytes(select_control?window_cfg_context_bytes:saved_frame_cfg_context_bytes),
    .window_cfg_stream_bytes(select_control?window_cfg_stream_bytes:saved_frame_cfg_stream_bytes),
    .window_cfg_window_bytes(select_control?window_cfg_window_bytes:saved_frame_cfg_window_bytes),
    .window_rsp_valid(owned_result_valid),
    .window_rsp_ready(owned_result_ready),
    .window_rsp_op(owned_window_rsp_op),
    .window_rsp_user(owned_window_rsp_user),
    .window_rsp_stream(owned_window_rsp_stream),
    .window_rsp_status(owned_window_rsp_status),
    .window_rsp_detail(owned_window_rsp_detail),
    .window_rsp_memory_status(owned_window_rsp_memory_status),
    .window_rsp_connection_error(owned_window_rsp_connection_error),
    .window_rsp_http2_error(owned_window_rsp_http2_error),
    .window_rsp_grant_bytes(owned_window_rsp_grant_bytes),
    .window_rsp_connection_window(owned_window_rsp_connection_window),
    .window_rsp_initial_window(owned_window_rsp_initial_window),
    .window_rsp_stream_window(owned_window_rsp_stream_window),
    .window_rsp_max_frame_bytes(owned_window_rsp_max_frame_bytes),
    .window_rsp_affected_streams(owned_window_rsp_affected_streams),
    .window_recovery_required(window_recovery_required),
    .window_recovery_address(window_recovery_address),
    .idle(owned_idle),
    .window_busy(window_busy),
    .window_lock_status(window_lock_status),
    .directory_pool_lock_active(directory_pool_lock_active),
    .mem_valid(mem_valid),
    .mem_ready(mem_ready),
    .mem_write(mem_write),
    .mem_addr(mem_addr),
    .mem_bytes(mem_bytes),
    .mem_data(mem_data),
    .mem_rsp_valid(mem_rsp_valid),
    .mem_rsp_ready(mem_rsp_ready),
    .mem_rsp_data(mem_rsp_data),
    .mem_rsp_status(mem_rsp_status),
    .window_rsp_binding_valid(window_rsp_binding_valid),
    .window_rsp_record_address(window_rsp_record_address),
    .window_rsp_generation(window_rsp_generation),
    .window_rsp_send_closed(window_rsp_send_closed)
);

always @(posedge clk)begin
    if(rst)begin
        state<=IDLE;frame_active<=0;parked<=0;frame_owner<=0;frame_stream<=0;frame_generation<=0;frame_address<=0;
        saved_frame_cfg_context_base<=0;
        saved_frame_cfg_stream_base<=0;
        saved_frame_cfg_window_base<=0;
        saved_frame_cfg_work_floor<=0;
        saved_frame_cfg_context_bytes<=0;
        saved_frame_cfg_stream_bytes<=0;
        saved_frame_cfg_window_bytes<=0;
    end else begin
        if(start_valid&&start_ready)begin
            frame_active<=1;parked<=0;frame_owner<=lease_rsp_user;frame_stream<=lease_rsp_stream;
            frame_generation<=lease_rsp_generation;frame_address<=lease_rsp_address;
            saved_frame_cfg_context_base<=frame_cfg_context_base;
            saved_frame_cfg_stream_base<=frame_cfg_stream_base;
            saved_frame_cfg_window_base<=frame_cfg_window_base;
            saved_frame_cfg_work_floor<=frame_cfg_work_floor;
            saved_frame_cfg_context_bytes<=frame_cfg_context_bytes;
            saved_frame_cfg_stream_bytes<=frame_cfg_stream_bytes;
            saved_frame_cfg_window_bytes<=frame_cfg_window_bytes;
        end
        if(finish_valid&&finish_ready)begin frame_active<=0;parked<=0;end
        case(state)
            IDLE:if(owned_request_ready&&(control_pending||reserve_pending))state<=control_pending?CONTROL:RESERVE;
            CONTROL:if(owned_result_valid&&window_rsp_ready)begin
                state<=IDLE;
                if(owned_window_rsp_status==0&&owned_window_rsp_user==frame_owner&&
                   (owned_window_rsp_stream==0||owned_window_rsp_stream==frame_stream)&&
                   (owned_window_rsp_op==2||owned_window_rsp_op==3||owned_window_rsp_op==4||owned_window_rsp_op==8||owned_window_rsp_op==9||owned_window_rsp_op==10))parked<=0;
            end
            RESERVE:if(owned_result_valid&&owned_result_ready)begin state<=IDLE;parked<=owned_window_rsp_status==1;end
            default:state<=IDLE;
        endcase
    end
end
endmodule
`default_nettype wire
