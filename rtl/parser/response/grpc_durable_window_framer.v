`timescale 1ns/1ps
`default_nettype none
// DATA grants are supplied only by acknowledged actual window reservations.
// Actual cached LOAD authority is retained through the public frame result.
// Parent supplies ordered control commands; raw control and HEADERS remain external.
module grpc_durable_window_framer #(
parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_MESSAGE_BYTES=65535
 )(
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
    input wire [23:0] cfg_peer_max_frame_bytes,
    input wire [511:0] s_axis_message_tdata,
    input wire [63:0] s_axis_message_tkeep,
    input wire  s_axis_message_tvalid,
    output wire  s_axis_message_tready,
    input wire  s_axis_message_tlast,
    input wire [USER_WIDTH-1:0] s_axis_message_tuser,
    input wire  s_axis_message_abort,
    output wire [511:0] m_axis_tx_tdata,
    output wire [63:0] m_axis_tx_tkeep,
    output wire  m_axis_tx_tvalid,
    input wire  m_axis_tx_tready,
    output wire  m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire  result_valid,
    input wire  result_ready,
    output wire [7:0] result_status,
    output wire [USER_WIDTH-1:0] result_user,
    output wire [30:0] result_stream,
    output wire [31:0] result_message_bytes,
    output wire [31:0] result_wire_bytes,
    output wire [31:0] result_frames,
    output wire  result_tx_emitted,
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
    output wire [31:0] credit_error_http2_error
);
localparam IDLE=0,CONTROL=1,RESERVE=2;
reg [1:0] state;reg frame_active,parked;
reg [USER_WIDTH-1:0] frame_owner;reg [30:0] frame_stream;
reg [31:0] frame_generation;reg [MEMORY_ADDR_WIDTH-1:0] frame_address;
wire owned_idle,framer_idle,framer_start_ready,owned_request_ready,owned_result_valid,owned_result_ready;
wire frame_request_valid,frame_request_ready;wire [USER_WIDTH-1:0] frame_request_user;
wire [30:0] frame_request_stream;wire [23:0] frame_request_maximum,grant_bytes;
wire lease_matches=lease_rsp_valid&&lease_rsp_status==0&&lease_rsp_user==start_user&&lease_rsp_stream==start_stream;
wire reserve_pending=frame_active&&frame_request_valid&&!parked;
wire select_control=window_req_valid;
assign start_ready=!rst&&framer_start_ready&&!frame_active&&lease_matches;
assign window_req_ready=!rst&&state==IDLE&&owned_request_ready;
assign window_rsp_valid=state==CONTROL&&owned_result_valid;
assign credit_parked=parked;
assign credit_error_valid=state==RESERVE&&owned_result_valid&&owned_window_rsp_status>1;
assign frame_request_ready=state==RESERVE&&owned_result_valid&&
    (owned_window_rsp_status==0||(owned_window_rsp_status>1&&credit_error_ready));
assign grant_bytes=owned_window_rsp_status==0?owned_window_rsp_grant_bytes:24'd0;
assign owned_result_ready=state==CONTROL?window_rsp_ready:
    state==RESERVE&&(owned_window_rsp_status==1||frame_request_valid&&frame_request_ready);
assign idle=owned_idle&&framer_idle&&state==IDLE&&!frame_active&&!start_valid;
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
http2_owned_lifecycle_windows #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) owned(
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
    .lease_rsp_ready(lease_rsp_ready&&!frame_active&&!start_valid&&!window_busy&&state==IDLE),
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
    .window_req_valid(!rst&&state==IDLE&&(window_req_valid||reserve_pending)),
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
    .mem_rsp_status(mem_rsp_status)
);
grpc_http2_response_framer #(.USER_WIDTH(USER_WIDTH),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)) framer(
    .clk(clk),
    .rst(rst),
    .start_valid(start_valid&&!frame_active&&lease_matches),
    .start_ready(framer_start_ready),
    .start_user(start_user),
    .start_stream(start_stream),
    .cfg_peer_max_frame_bytes(cfg_peer_max_frame_bytes),
    .s_axis_message_tdata(s_axis_message_tdata),
    .s_axis_message_tkeep(s_axis_message_tkeep),
    .s_axis_message_tvalid(s_axis_message_tvalid),
    .s_axis_message_tready(s_axis_message_tready),
    .s_axis_message_tlast(s_axis_message_tlast),
    .s_axis_message_tuser(s_axis_message_tuser),
    .s_axis_message_abort(s_axis_message_abort),
    .frame_req_valid(frame_request_valid),
    .frame_req_ready(frame_request_ready),
    .frame_req_user(frame_request_user),
    .frame_req_stream(frame_request_stream),
    .frame_req_max_bytes(frame_request_maximum),
    .frame_grant_bytes(grant_bytes),
    .m_axis_tx_tdata(m_axis_tx_tdata),
    .m_axis_tx_tkeep(m_axis_tx_tkeep),
    .m_axis_tx_tvalid(m_axis_tx_tvalid),
    .m_axis_tx_tready(m_axis_tx_tready),
    .m_axis_tx_tlast(m_axis_tx_tlast),
    .m_axis_tx_tuser(m_axis_tx_tuser),
    .result_valid(result_valid),
    .result_ready(result_ready),
    .result_status(result_status),
    .result_user(result_user),
    .result_stream(result_stream),
    .result_message_bytes(result_message_bytes),
    .result_wire_bytes(result_wire_bytes),
    .result_frames(result_frames),
    .result_tx_emitted(result_tx_emitted),
    .idle(framer_idle)
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
        if(result_valid&&result_ready)begin frame_active<=0;parked<=0;end
        case(state)
            IDLE:if(owned_request_ready&&(window_req_valid||reserve_pending))state<=window_req_valid?CONTROL:RESERVE;
            CONTROL:if(owned_result_valid&&window_rsp_ready)begin
                state<=IDLE;
                if(owned_window_rsp_status==0&&owned_window_rsp_user==frame_owner&&
                   (owned_window_rsp_stream==0||owned_window_rsp_stream==frame_stream)&&
                   (owned_window_rsp_op==2||owned_window_rsp_op==3||owned_window_rsp_op==4||owned_window_rsp_op==8))parked<=0;
            end
            RESERVE:if(owned_result_valid&&owned_result_ready)begin state<=IDLE;parked<=owned_window_rsp_status==1;end
            default:state<=IDLE;
        endcase
    end
end
endmodule
`default_nettype wire
