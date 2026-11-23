`timescale 1ns/1ps
`default_nettype none
// Actual directory exclusion + actual durable send-window engine.
// Memory client zero: directory; client one: send-window records.
// Raw control/framer scheduling, closure scheduling and image leases remain required.
module http2_owned_pipelined_cancel_windows #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(
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
    output wire  idle,
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
    input wire [2*8-1:0] mem_rsp_status
,
    output wire  window_rsp_binding_valid,
    output wire [MEMORY_ADDR_WIDTH-1:0] window_rsp_record_address,
    output wire [31:0] window_rsp_generation,
    output wire  window_rsp_send_closed
);
localparam IDLE=0,LOCK_SEND=1,LOCK_WAIT=2,ISSUE=3,RESULT=4,LOCK_ERROR=5,UNLOCK=6;
reg [2:0] state;reg [7:0] owned_lock_status;
wire directory_idle,window_engine_idle,engine_req_ready,engine_rsp_valid;
wire lock_ready,lock_result_valid,unlock_ready;wire [7:0] lock_status;
reg [3:0] saved_req_op;
reg  saved_req_maintenance;
reg [USER_WIDTH-1:0] saved_req_user;
reg [30:0] saved_req_stream;
reg [31:0] saved_req_generation;
reg [MEMORY_ADDR_WIDTH-1:0] saved_req_record_address;
reg [31:0] saved_req_amount;
reg [MEMORY_ADDR_WIDTH-1:0] saved_cfg_context_base;
reg [MEMORY_ADDR_WIDTH-1:0] saved_cfg_stream_base;
reg [MEMORY_ADDR_WIDTH-1:0] saved_cfg_window_base;
reg [MEMORY_ADDR_WIDTH-1:0] saved_cfg_work_floor;
reg [MEMORY_ADDR_WIDTH:0] saved_cfg_context_bytes;
reg [MEMORY_ADDR_WIDTH:0] saved_cfg_stream_bytes;
reg [MEMORY_ADDR_WIDTH:0] saved_cfg_window_bytes;
wire [3:0] engine_rsp_op;
wire [USER_WIDTH-1:0] engine_rsp_user;
wire [30:0] engine_rsp_stream;
wire [7:0] engine_rsp_status;
wire [7:0] engine_rsp_detail;
wire [7:0] engine_rsp_memory_status;
wire  engine_rsp_connection_error;
wire [31:0] engine_rsp_http2_error;
wire [23:0] engine_rsp_grant_bytes;
wire [31:0] engine_rsp_connection_window;
wire [31:0] engine_rsp_initial_window;
wire [31:0] engine_rsp_stream_window;
wire [23:0] engine_rsp_max_frame_bytes;
wire [31:0] engine_rsp_affected_streams;
assign window_req_ready=!rst&&state==IDLE;
assign window_rsp_valid=!rst&&(state==LOCK_ERROR||state==RESULT&&engine_rsp_valid);
assign window_busy=state!=IDLE;
assign window_lock_status=owned_lock_status;
assign idle=state==IDLE&&directory_idle&&window_engine_idle&&!window_req_valid&&!window_recovery_required&&!recovery_required;
assign window_rsp_op=state==LOCK_ERROR?saved_req_op:engine_rsp_op;
assign window_rsp_user=state==LOCK_ERROR?saved_req_user:engine_rsp_user;
assign window_rsp_stream=state==LOCK_ERROR?saved_req_stream:engine_rsp_stream;
assign window_rsp_status=state==LOCK_ERROR?8'd7:engine_rsp_status;
assign window_rsp_detail=state==LOCK_ERROR?owned_lock_status:engine_rsp_detail;
assign window_rsp_memory_status=state==LOCK_ERROR?0:engine_rsp_memory_status;
assign window_rsp_connection_error=state==LOCK_ERROR?1'b1:engine_rsp_connection_error;
assign window_rsp_http2_error=state==LOCK_ERROR?32'd2:engine_rsp_http2_error;
assign window_rsp_grant_bytes=state==LOCK_ERROR?0:engine_rsp_grant_bytes;
assign window_rsp_connection_window=state==LOCK_ERROR?0:engine_rsp_connection_window;
assign window_rsp_initial_window=state==LOCK_ERROR?0:engine_rsp_initial_window;
assign window_rsp_stream_window=state==LOCK_ERROR?0:engine_rsp_stream_window;
assign window_rsp_max_frame_bytes=state==LOCK_ERROR?0:engine_rsp_max_frame_bytes;
assign window_rsp_affected_streams=state==LOCK_ERROR?0:engine_rsp_affected_streams;
grpc_pool_locked_stream_store #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) directory(
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
    .idle(directory_idle),
    .mem_valid(mem_valid[0*1+:1]),
    .mem_ready(mem_ready[0*1+:1]),
    .mem_write(mem_write[0*1+:1]),
    .mem_addr(mem_addr[0*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[0*4+:4]),
    .mem_data(mem_data[0*72+:72]),
    .mem_rsp_valid(mem_rsp_valid[0*1+:1]),
    .mem_rsp_ready(mem_rsp_ready[0*1+:1]),
    .mem_rsp_data(mem_rsp_data[0*72+:72]),
    .mem_rsp_status(mem_rsp_status[0*8+:8]),
    .lease_valid(lease_valid),
    .lease_ready(lease_ready),
    .lease_user(lease_user),
    .lease_stream(lease_stream),
    .lease_pool_base(lease_pool_base),
    .lease_pool_bytes(lease_pool_bytes),
    .lease_rsp_ready(lease_rsp_ready),
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
    .pool_lock_valid(state==LOCK_SEND),
    .pool_lock_ready(lock_ready),
    .pool_lock_base(saved_cfg_stream_base),
    .pool_lock_bytes(saved_cfg_stream_bytes),
    .pool_lock_result_valid(lock_result_valid),
    .pool_lock_result_ready(state==LOCK_WAIT),
    .pool_lock_status(lock_status),
    .pool_lock_active(directory_pool_lock_active),
    .pool_unlock_valid(state==UNLOCK),
    .pool_unlock_ready(unlock_ready)
);
wire  engine_rsp_binding_valid;
assign window_rsp_binding_valid=state==LOCK_ERROR?0:engine_rsp_binding_valid;
wire [MEMORY_ADDR_WIDTH-1:0] engine_rsp_record_address;
assign window_rsp_record_address=state==LOCK_ERROR?0:engine_rsp_record_address;
wire [31:0] engine_rsp_generation;
assign window_rsp_generation=state==LOCK_ERROR?0:engine_rsp_generation;
wire  engine_rsp_send_closed;
assign window_rsp_send_closed=state==LOCK_ERROR?0:engine_rsp_send_closed;
http2_pipelined_cancel_window_store #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) windows(
    .clk(clk),
    .rst(rst),
    .req_valid(state==ISSUE&&directory_pool_lock_active),
    .req_ready(engine_req_ready),
    .req_op(saved_req_op),
    .req_authority(directory_pool_lock_active),
    .req_maintenance(saved_req_maintenance),
    .req_user(saved_req_user),
    .req_stream(saved_req_stream),
    .req_generation(saved_req_generation),
    .req_record_address(saved_req_record_address),
    .req_amount(saved_req_amount),
    .cfg_context_base(saved_cfg_context_base),
    .cfg_stream_base(saved_cfg_stream_base),
    .cfg_window_base(saved_cfg_window_base),
    .cfg_work_floor(saved_cfg_work_floor),
    .cfg_context_bytes(saved_cfg_context_bytes),
    .cfg_stream_bytes(saved_cfg_stream_bytes),
    .cfg_window_bytes(saved_cfg_window_bytes),
    .rsp_valid(engine_rsp_valid),
    .rsp_ready(state==RESULT&&window_rsp_ready),
    .rsp_op(engine_rsp_op),
    .rsp_user(engine_rsp_user),
    .rsp_stream(engine_rsp_stream),
    .rsp_status(engine_rsp_status),
    .rsp_detail(engine_rsp_detail),
    .rsp_memory_status(engine_rsp_memory_status),
    .rsp_connection_error(engine_rsp_connection_error),
    .rsp_http2_error(engine_rsp_http2_error),
    .rsp_grant_bytes(engine_rsp_grant_bytes),
    .rsp_connection_window(engine_rsp_connection_window),
    .rsp_initial_window(engine_rsp_initial_window),
    .rsp_stream_window(engine_rsp_stream_window),
    .rsp_max_frame_bytes(engine_rsp_max_frame_bytes),
    .rsp_affected_streams(engine_rsp_affected_streams),
    .recovery_required(window_recovery_required),
    .recovery_address(window_recovery_address),
    .idle(window_engine_idle),
    .mem_valid(mem_valid[1*1+:1]),
    .mem_ready(mem_ready[1*1+:1]),
    .mem_write(mem_write[1*1+:1]),
    .mem_addr(mem_addr[1*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[1*4+:4]),
    .mem_data(mem_data[1*72+:72]),
    .mem_rsp_valid(mem_rsp_valid[1*1+:1]),
    .mem_rsp_ready(mem_rsp_ready[1*1+:1]),
    .mem_rsp_data(mem_rsp_data[1*72+:72]),
    .mem_rsp_status(mem_rsp_status[1*8+:8]),
    .rsp_binding_valid(engine_rsp_binding_valid),
    .rsp_record_address(engine_rsp_record_address),
    .rsp_generation(engine_rsp_generation),
    .rsp_send_closed(engine_rsp_send_closed)
);
always @(posedge clk)begin
    if(rst)begin state<=IDLE;owned_lock_status<=0;
        saved_req_op<=0;
        saved_req_maintenance<=0;
        saved_req_user<=0;
        saved_req_stream<=0;
        saved_req_generation<=0;
        saved_req_record_address<=0;
        saved_req_amount<=0;
        saved_cfg_context_base<=0;
        saved_cfg_stream_base<=0;
        saved_cfg_window_base<=0;
        saved_cfg_work_floor<=0;
        saved_cfg_context_bytes<=0;
        saved_cfg_stream_bytes<=0;
        saved_cfg_window_bytes<=0;
    end else case(state)
        IDLE:if(window_req_valid&&window_req_ready)begin
            owned_lock_status<=0;
            saved_req_op<=window_req_op;
            saved_req_maintenance<=window_req_maintenance;
            saved_req_user<=window_req_user;
            saved_req_stream<=window_req_stream;
            saved_req_generation<=window_req_generation;
            saved_req_record_address<=window_req_record_address;
            saved_req_amount<=window_req_amount;
            saved_cfg_context_base<=window_cfg_context_base;
            saved_cfg_stream_base<=window_cfg_stream_base;
            saved_cfg_window_base<=window_cfg_window_base;
            saved_cfg_work_floor<=window_cfg_work_floor;
            saved_cfg_context_bytes<=window_cfg_context_bytes;
            saved_cfg_stream_bytes<=window_cfg_stream_bytes;
            saved_cfg_window_bytes<=window_cfg_window_bytes;
            state<=LOCK_SEND;
        end
        LOCK_SEND:if(lock_ready)state<=LOCK_WAIT;
        LOCK_WAIT:if(lock_result_valid)begin owned_lock_status<=lock_status;state<=lock_status==0?ISSUE:LOCK_ERROR;end
        ISSUE:if(directory_pool_lock_active&&engine_req_ready)state<=RESULT;
        RESULT:if(engine_rsp_valid&&window_rsp_ready)state<=UNLOCK;
        LOCK_ERROR:if(window_rsp_ready)state<=IDLE;
        UNLOCK:if(unlock_ready)state<=IDLE;
        default:state<=IDLE;
    endcase
end
endmodule
`default_nettype wire
