`timescale 1ns/1ps
`default_nettype none
module cocotb_peer_controls_top;
localparam integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
wire [63:0] peer_cmd_rsp_ping_payload;
wire [31:0] peer_cmd_rsp_ping_acks;
wire [31:0] peer_cmd_rsp_settings_acks;
wire [31:0] peer_cmd_rsp_settings_pending;
wire  peer_cmd_rsp_ping_pending;
wire  peer_cmd_rsp_enable_push;
wire [31:0] peer_cmd_rsp_max_header_list_size;
wire [31:0] peer_cmd_rsp_max_concurrent_streams;
wire [31:0] peer_cmd_rsp_header_table_size;
wire  peer_cmd_rsp_ack_matched;
wire  peer_cmd_rsp_wire_retired;
wire [USER_WIDTH-1:0] peer_cmd_rsp_user;
wire [3:0] peer_cmd_rsp_op;
wire [31:0] peer_cmd_rsp_http2_error;
wire  peer_cmd_rsp_connection_error;
wire [7:0] peer_cmd_rsp_memory_status;
wire [7:0] peer_cmd_rsp_detail;
wire [7:0] peer_cmd_rsp_status;
reg  peer_cmd_rsp_ready=0;
wire  peer_cmd_rsp_valid;
reg [63:0] peer_cmd_req_payload=0;
reg [USER_WIDTH-1:0] peer_cmd_req_user=0;
reg  peer_cmd_req_maintenance=0;
reg  peer_cmd_req_authority=0;
reg [3:0] peer_cmd_req_op=0;
wire  peer_cmd_req_ready;
reg  peer_cmd_req_valid=0;
wire [7:0] peer_format_memory_status;
wire [7:0] peer_format_status;
reg [MEMORY_ADDR_WIDTH:0] cfg_peer_bytes=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_peer_base=0;
reg  clk=0;
reg  rst=0;
reg  start_valid=0;
wire  start_ready;
reg  start_format=0;
reg  start_maintenance=0;
reg  start_authority=0;
reg [USER_WIDTH-1:0] start_user=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_journal_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_journal_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_slot_bytes=0;
reg  s_valid=0;
wire  s_ready;
reg [3:0] s_kind=0;
reg [7:0] s_data=0;
reg [31:0] s_arg0=0;
reg [31:0] s_arg1=0;
reg [23:0] s_length=0;
reg [7:0] s_type=0;
reg [7:0] s_flags=0;
reg [30:0] s_stream=0;
reg [USER_WIDTH-1:0] s_user=0;
reg  finish_valid=0;
wire  finish_ready;
reg  finish_commit=0;
wire  result_valid;
reg  result_ready=0;
wire [7:0] result_status;
wire [7:0] result_detail;
wire [7:0] result_memory_status;
wire [USER_WIDTH-1:0] result_user;
wire  result_committed;
wire [31:0] result_records;
wire [31:0] result_frames;
wire  recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] recovery_address;
wire  idle;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_window_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_window_bytes=0;
wire [7:0] control_status;
wire [7:0] control_detail;
wire [7:0] control_memory_status;
wire  control_connection_error;
wire [31:0] control_http2_error;
wire [31:0] control_frames;
wire [31:0] control_ack_frames;
wire [31:0] control_window_updates;
wire  exec_window_req_valid;
wire  exec_window_req_ready;
wire [3:0] exec_window_req_op;
wire  exec_window_req_maintenance;
wire [USER_WIDTH-1:0] exec_window_req_user;
wire [30:0] exec_window_req_stream;
wire [31:0] exec_window_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] exec_window_req_record_address;
wire [31:0] exec_window_req_amount;
wire [MEMORY_ADDR_WIDTH-1:0] exec_window_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] exec_window_cfg_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] exec_window_cfg_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] exec_window_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] exec_window_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] exec_window_cfg_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] exec_window_cfg_window_bytes;
wire  exec_window_rsp_valid;
wire  exec_window_rsp_ready;
wire [3:0] exec_window_rsp_op;
wire [USER_WIDTH-1:0] exec_window_rsp_user;
wire [30:0] exec_window_rsp_stream;
wire [7:0] exec_window_rsp_status;
wire [7:0] exec_window_rsp_detail;
wire [7:0] exec_window_rsp_memory_status;
wire  exec_window_rsp_connection_error;
wire [31:0] exec_window_rsp_http2_error;
wire  cancel_valid;
reg  cancel_ready=0;
wire [USER_WIDTH-1:0] cancel_user;
wire  cancel_goaway;
wire [30:0] cancel_stream;
wire [31:0] cancel_arg0;
wire [31:0] cancel_arg1;
reg  cancel_result_valid=0;
wire  cancel_result_ready;
reg [7:0] cancel_status=0;
wire  classify_valid;
reg  classify_ready=0;
wire [USER_WIDTH-1:0] classify_user;
wire [30:0] classify_stream;
reg  classify_result_valid=0;
wire  classify_result_ready;
reg [7:0] classify_status=0;
reg  classify_closed=0;
wire [511:0] m_axis_tx_tdata;
wire [63:0] m_axis_tx_tkeep;
wire  m_axis_tx_tvalid;
reg  m_axis_tx_tready=0;
wire  m_axis_tx_tlast;
wire [USER_WIDTH-1:0] m_axis_tx_tuser;
reg  req_valid=0;
wire  req_ready;
reg [2:0] req_op=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes=0;
reg [USER_WIDTH-1:0] req_user=0;
reg [USER_WIDTH-1:0] req_application=0;
reg [30:0] req_stream=0;
reg [31:0] req_generation=0;
reg [MEMORY_ADDR_WIDTH-1:0] req_address=0;
reg [MEMORY_ADDR_WIDTH-1:0] req_buffer_base=0;
reg [MEMORY_ADDR_WIDTH:0] req_buffer_bytes=0;
reg [31:0] req_message_limit=0;
reg  req_protobuf=0;
reg  req_unsupported_encoding=0;
reg  req_maintenance=0;
reg [255:0] req_state=0;
wire  rsp_valid;
reg  rsp_ready=0;
wire [7:0] rsp_status;
wire [7:0] rsp_detail;
wire [7:0] rsp_memory_status;
wire [2:0] rsp_op;
wire [MEMORY_ADDR_WIDTH-1:0] rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] rsp_buffer_bytes;
wire [USER_WIDTH-1:0] rsp_user;
wire [USER_WIDTH-1:0] rsp_application;
wire [30:0] rsp_stream;
wire [31:0] rsp_generation;
wire [31:0] rsp_message_limit;
wire  rsp_protobuf;
wire  rsp_unsupported_encoding;
wire [255:0] rsp_state;
wire  directory_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] directory_recovery_address;
reg  lease_valid=0;
wire  lease_ready;
reg [USER_WIDTH-1:0] lease_user=0;
reg [30:0] lease_stream=0;
reg [MEMORY_ADDR_WIDTH-1:0] lease_pool_base=0;
reg [MEMORY_ADDR_WIDTH:0] lease_pool_bytes=0;
reg  lease_rsp_ready=0;
wire  lease_active;
wire  lease_rsp_valid;
wire [7:0] lease_rsp_status;
wire [7:0] lease_rsp_detail;
wire [7:0] lease_rsp_memory_status;
wire [2:0] lease_rsp_op;
wire [MEMORY_ADDR_WIDTH-1:0] lease_rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] lease_rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] lease_rsp_buffer_bytes;
wire [USER_WIDTH-1:0] lease_rsp_user;
wire [USER_WIDTH-1:0] lease_rsp_application;
wire [30:0] lease_rsp_stream;
wire [31:0] lease_rsp_generation;
wire [31:0] lease_rsp_message_limit;
wire  lease_rsp_protobuf;
wire  lease_rsp_unsupported_encoding;
wire [255:0] lease_rsp_state;
reg  window_req_valid=0;
wire  window_req_ready;
reg [3:0] window_req_op=0;
reg  window_req_maintenance=0;
reg [USER_WIDTH-1:0] window_req_user=0;
reg [30:0] window_req_stream=0;
reg [31:0] window_req_generation=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_req_record_address=0;
reg [31:0] window_req_amount=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_window_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH:0] window_cfg_context_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] window_cfg_stream_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] window_cfg_window_bytes=0;
wire  window_rsp_valid;
reg  window_rsp_ready=0;
wire [3:0] window_rsp_op;
wire [3:0] service_window_rsp_op;
assign window_rsp_op=service_window_rsp_op;
wire [USER_WIDTH-1:0] window_rsp_user;
wire [USER_WIDTH-1:0] service_window_rsp_user;
assign window_rsp_user=service_window_rsp_user;
wire [30:0] window_rsp_stream;
wire [30:0] service_window_rsp_stream;
assign window_rsp_stream=service_window_rsp_stream;
wire [7:0] window_rsp_status;
wire [7:0] service_window_rsp_status;
assign window_rsp_status=service_window_rsp_status;
wire [7:0] window_rsp_detail;
wire [7:0] service_window_rsp_detail;
assign window_rsp_detail=service_window_rsp_detail;
wire [7:0] window_rsp_memory_status;
wire [7:0] service_window_rsp_memory_status;
assign window_rsp_memory_status=service_window_rsp_memory_status;
wire  window_rsp_connection_error;
wire  service_window_rsp_connection_error;
assign window_rsp_connection_error=service_window_rsp_connection_error;
wire [31:0] window_rsp_http2_error;
wire [31:0] service_window_rsp_http2_error;
assign window_rsp_http2_error=service_window_rsp_http2_error;
wire [23:0] window_rsp_grant_bytes;
wire [23:0] service_window_rsp_grant_bytes;
assign window_rsp_grant_bytes=service_window_rsp_grant_bytes;
wire [31:0] window_rsp_connection_window;
wire [31:0] service_window_rsp_connection_window;
assign window_rsp_connection_window=service_window_rsp_connection_window;
wire [31:0] window_rsp_initial_window;
wire [31:0] service_window_rsp_initial_window;
assign window_rsp_initial_window=service_window_rsp_initial_window;
wire [31:0] window_rsp_stream_window;
wire [31:0] service_window_rsp_stream_window;
assign window_rsp_stream_window=service_window_rsp_stream_window;
wire [23:0] window_rsp_max_frame_bytes;
wire [23:0] service_window_rsp_max_frame_bytes;
assign window_rsp_max_frame_bytes=service_window_rsp_max_frame_bytes;
wire [31:0] window_rsp_affected_streams;
wire [31:0] service_window_rsp_affected_streams;
assign window_rsp_affected_streams=service_window_rsp_affected_streams;
wire  window_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] window_recovery_address;
wire  window_busy;
wire [7:0] window_lock_status;
wire  directory_pool_lock_active;
wire [4*1-1:0] mem_valid;
wire [2*1-1:0] journal_mem_valid;
wire [2*1-1:0] service_mem_valid;
assign mem_valid={service_mem_valid,journal_mem_valid};
reg [4*1-1:0] mem_ready=0;
wire [2*1-1:0] journal_mem_ready;
wire [2*1-1:0] service_mem_ready;
assign journal_mem_ready=mem_ready[0+:2*1];
assign service_mem_ready=mem_ready[2*1+:2*1];
wire [4*1-1:0] mem_write;
wire [2*1-1:0] journal_mem_write;
wire [2*1-1:0] service_mem_write;
assign mem_write={service_mem_write,journal_mem_write};
wire [4*MEMORY_ADDR_WIDTH-1:0] mem_addr;
wire [2*MEMORY_ADDR_WIDTH-1:0] journal_mem_addr;
wire [2*MEMORY_ADDR_WIDTH-1:0] service_mem_addr;
assign mem_addr={service_mem_addr,journal_mem_addr};
wire [4*4-1:0] mem_bytes;
wire [2*4-1:0] journal_mem_bytes;
wire [2*4-1:0] service_mem_bytes;
assign mem_bytes={service_mem_bytes,journal_mem_bytes};
wire [4*72-1:0] mem_data;
wire [2*72-1:0] journal_mem_data;
wire [2*72-1:0] service_mem_data;
assign mem_data={service_mem_data,journal_mem_data};
reg [4*1-1:0] mem_rsp_valid=0;
wire [2*1-1:0] journal_mem_rsp_valid;
wire [2*1-1:0] service_mem_rsp_valid;
assign journal_mem_rsp_valid=mem_rsp_valid[0+:2*1];
assign service_mem_rsp_valid=mem_rsp_valid[2*1+:2*1];
wire [4*1-1:0] mem_rsp_ready;
wire [2*1-1:0] journal_mem_rsp_ready;
wire [2*1-1:0] service_mem_rsp_ready;
assign mem_rsp_ready={service_mem_rsp_ready,journal_mem_rsp_ready};
reg [4*72-1:0] mem_rsp_data=0;
wire [2*72-1:0] journal_mem_rsp_data;
wire [2*72-1:0] service_mem_rsp_data;
assign journal_mem_rsp_data=mem_rsp_data[0+:2*72];
assign service_mem_rsp_data=mem_rsp_data[2*72+:2*72];
reg [4*8-1:0] mem_rsp_status=0;
wire [2*8-1:0] journal_mem_rsp_status;
wire [2*8-1:0] service_mem_rsp_status;
assign journal_mem_rsp_status=mem_rsp_status[0+:2*8];
assign service_mem_rsp_status=mem_rsp_status[2*8+:2*8];
reg [2:0] window_owner=0;
wire service_window_req_ready,service_window_rsp_valid;
assign exec_window_req_ready=window_owner==1&&service_window_req_ready;
assign window_req_ready=window_owner==3&&service_window_req_ready;
assign exec_window_rsp_valid=window_owner==2&&service_window_rsp_valid;
assign window_rsp_valid=window_owner==4&&service_window_rsp_valid;
always @(posedge clk)begin if(rst)window_owner<=0;else case(window_owner)
0:if(exec_window_req_valid)window_owner<=1;else if(window_req_valid)window_owner<=3;
1:if(exec_window_req_valid&&service_window_req_ready)window_owner<=2;
2:if(service_window_rsp_valid&&exec_window_rsp_ready)window_owner<=0;
3:if(window_req_valid&&service_window_req_ready)window_owner<=4;
4:if(service_window_rsp_valid&&window_rsp_ready)window_owner<=0;
default:window_owner<=0;endcase end
assign exec_window_rsp_op=service_window_rsp_op;
assign exec_window_rsp_user=service_window_rsp_user;
assign exec_window_rsp_stream=service_window_rsp_stream;
assign exec_window_rsp_status=service_window_rsp_status;
assign exec_window_rsp_detail=service_window_rsp_detail;
assign exec_window_rsp_memory_status=service_window_rsp_memory_status;
assign exec_window_rsp_connection_error=service_window_rsp_connection_error;
assign exec_window_rsp_http2_error=service_window_rsp_http2_error;
wire service_idle;
http2_peer_controls #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) dut(
    .clk(clk),
    .rst(rst),
    .start_valid(start_valid),
    .start_ready(start_ready),
    .start_format(start_format),
    .start_maintenance(start_maintenance),
    .start_authority(start_authority),
    .start_user(start_user),
    .cfg_context_base(cfg_context_base),
    .cfg_journal_base(cfg_journal_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_context_bytes(cfg_context_bytes),
    .cfg_journal_bytes(cfg_journal_bytes),
    .cfg_slot_bytes(cfg_slot_bytes),
    .s_valid(s_valid),
    .s_ready(s_ready),
    .s_kind(s_kind),
    .s_data(s_data),
    .s_arg0(s_arg0),
    .s_arg1(s_arg1),
    .s_length(s_length),
    .s_type(s_type),
    .s_flags(s_flags),
    .s_stream(s_stream),
    .s_user(s_user),
    .finish_valid(finish_valid),
    .finish_ready(finish_ready),
    .finish_commit(finish_commit),
    .result_valid(result_valid),
    .result_ready(result_ready),
    .result_status(result_status),
    .result_detail(result_detail),
    .result_memory_status(result_memory_status),
    .result_user(result_user),
    .result_committed(result_committed),
    .result_records(result_records),
    .result_frames(result_frames),
    .recovery_required(recovery_required),
    .recovery_address(recovery_address),
    .idle(idle),
    .mem_valid(journal_mem_valid),
    .mem_ready(journal_mem_ready),
    .mem_write(journal_mem_write),
    .mem_addr(journal_mem_addr),
    .mem_bytes(journal_mem_bytes),
    .mem_data(journal_mem_data),
    .mem_rsp_valid(journal_mem_rsp_valid),
    .mem_rsp_ready(journal_mem_rsp_ready),
    .mem_rsp_data(journal_mem_rsp_data),
    .mem_rsp_status(journal_mem_rsp_status),
    .cfg_stream_base(cfg_stream_base),
    .cfg_window_base(cfg_window_base),
    .cfg_stream_bytes(cfg_stream_bytes),
    .cfg_window_bytes(cfg_window_bytes),
    .control_status(control_status),
    .control_detail(control_detail),
    .control_memory_status(control_memory_status),
    .control_connection_error(control_connection_error),
    .control_http2_error(control_http2_error),
    .control_frames(control_frames),
    .control_ack_frames(control_ack_frames),
    .control_window_updates(control_window_updates),
    .window_req_valid(exec_window_req_valid),
    .window_req_ready(exec_window_req_ready),
    .window_req_op(exec_window_req_op),
    .window_req_maintenance(exec_window_req_maintenance),
    .window_req_user(exec_window_req_user),
    .window_req_stream(exec_window_req_stream),
    .window_req_generation(exec_window_req_generation),
    .window_req_record_address(exec_window_req_record_address),
    .window_req_amount(exec_window_req_amount),
    .window_cfg_context_base(exec_window_cfg_context_base),
    .window_cfg_stream_base(exec_window_cfg_stream_base),
    .window_cfg_window_base(exec_window_cfg_window_base),
    .window_cfg_work_floor(exec_window_cfg_work_floor),
    .window_cfg_context_bytes(exec_window_cfg_context_bytes),
    .window_cfg_stream_bytes(exec_window_cfg_stream_bytes),
    .window_cfg_window_bytes(exec_window_cfg_window_bytes),
    .window_rsp_valid(exec_window_rsp_valid),
    .window_rsp_ready(exec_window_rsp_ready),
    .window_rsp_op(exec_window_rsp_op),
    .window_rsp_user(exec_window_rsp_user),
    .window_rsp_stream(exec_window_rsp_stream),
    .window_rsp_status(exec_window_rsp_status),
    .window_rsp_detail(exec_window_rsp_detail),
    .window_rsp_memory_status(exec_window_rsp_memory_status),
    .window_rsp_connection_error(exec_window_rsp_connection_error),
    .window_rsp_http2_error(exec_window_rsp_http2_error),
    .cancel_valid(cancel_valid),
    .cancel_ready(cancel_ready),
    .cancel_user(cancel_user),
    .cancel_goaway(cancel_goaway),
    .cancel_stream(cancel_stream),
    .cancel_arg0(cancel_arg0),
    .cancel_arg1(cancel_arg1),
    .cancel_result_valid(cancel_result_valid),
    .cancel_result_ready(cancel_result_ready),
    .cancel_status(cancel_status),
    .classify_valid(classify_valid),
    .classify_ready(classify_ready),
    .classify_user(classify_user),
    .classify_stream(classify_stream),
    .classify_result_valid(classify_result_valid),
    .classify_result_ready(classify_result_ready),
    .classify_status(classify_status),
    .classify_closed(classify_closed),
    .m_axis_tx_tdata(m_axis_tx_tdata),
    .m_axis_tx_tkeep(m_axis_tx_tkeep),
    .m_axis_tx_tvalid(m_axis_tx_tvalid),
    .m_axis_tx_tready(m_axis_tx_tready),
    .m_axis_tx_tlast(m_axis_tx_tlast),
    .m_axis_tx_tuser(m_axis_tx_tuser),
    .cfg_peer_base(cfg_peer_base),
    .cfg_peer_bytes(cfg_peer_bytes),
    .peer_format_status(peer_format_status),
    .peer_format_memory_status(peer_format_memory_status),
    .peer_cmd_req_valid(peer_cmd_req_valid),
    .peer_cmd_req_ready(peer_cmd_req_ready),
    .peer_cmd_req_op(peer_cmd_req_op),
    .peer_cmd_req_authority(peer_cmd_req_authority),
    .peer_cmd_req_maintenance(peer_cmd_req_maintenance),
    .peer_cmd_req_user(peer_cmd_req_user),
    .peer_cmd_req_payload(peer_cmd_req_payload),
    .peer_cmd_rsp_valid(peer_cmd_rsp_valid),
    .peer_cmd_rsp_ready(peer_cmd_rsp_ready),
    .peer_cmd_rsp_status(peer_cmd_rsp_status),
    .peer_cmd_rsp_detail(peer_cmd_rsp_detail),
    .peer_cmd_rsp_memory_status(peer_cmd_rsp_memory_status),
    .peer_cmd_rsp_connection_error(peer_cmd_rsp_connection_error),
    .peer_cmd_rsp_http2_error(peer_cmd_rsp_http2_error),
    .peer_cmd_rsp_op(peer_cmd_rsp_op),
    .peer_cmd_rsp_user(peer_cmd_rsp_user),
    .peer_cmd_rsp_wire_retired(peer_cmd_rsp_wire_retired),
    .peer_cmd_rsp_ack_matched(peer_cmd_rsp_ack_matched),
    .peer_cmd_rsp_header_table_size(peer_cmd_rsp_header_table_size),
    .peer_cmd_rsp_max_concurrent_streams(peer_cmd_rsp_max_concurrent_streams),
    .peer_cmd_rsp_max_header_list_size(peer_cmd_rsp_max_header_list_size),
    .peer_cmd_rsp_enable_push(peer_cmd_rsp_enable_push),
    .peer_cmd_rsp_ping_pending(peer_cmd_rsp_ping_pending),
    .peer_cmd_rsp_settings_pending(peer_cmd_rsp_settings_pending),
    .peer_cmd_rsp_settings_acks(peer_cmd_rsp_settings_acks),
    .peer_cmd_rsp_ping_acks(peer_cmd_rsp_ping_acks),
    .peer_cmd_rsp_ping_payload(peer_cmd_rsp_ping_payload)
);
http2_owned_keyed_windows #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) service(
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
    .recovery_required(directory_recovery_required),
    .recovery_address(directory_recovery_address),
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
    .window_req_valid(window_owner==1?exec_window_req_valid:window_owner==3&&window_req_valid),
    .window_req_ready(service_window_req_ready),
    .window_req_op(window_owner==1?exec_window_req_op:window_req_op),
    .window_req_maintenance(window_owner==1?exec_window_req_maintenance:window_req_maintenance),
    .window_req_user(window_owner==1?exec_window_req_user:window_req_user),
    .window_req_stream(window_owner==1?exec_window_req_stream:window_req_stream),
    .window_req_generation(window_owner==1?exec_window_req_generation:window_req_generation),
    .window_req_record_address(window_owner==1?exec_window_req_record_address:window_req_record_address),
    .window_req_amount(window_owner==1?exec_window_req_amount:window_req_amount),
    .window_cfg_context_base(window_owner==1?exec_window_cfg_context_base:window_cfg_context_base),
    .window_cfg_stream_base(window_owner==1?exec_window_cfg_stream_base:window_cfg_stream_base),
    .window_cfg_window_base(window_owner==1?exec_window_cfg_window_base:window_cfg_window_base),
    .window_cfg_work_floor(window_owner==1?exec_window_cfg_work_floor:window_cfg_work_floor),
    .window_cfg_context_bytes(window_owner==1?exec_window_cfg_context_bytes:window_cfg_context_bytes),
    .window_cfg_stream_bytes(window_owner==1?exec_window_cfg_stream_bytes:window_cfg_stream_bytes),
    .window_cfg_window_bytes(window_owner==1?exec_window_cfg_window_bytes:window_cfg_window_bytes),
    .window_rsp_valid(service_window_rsp_valid),
    .window_rsp_ready(window_owner==2?exec_window_rsp_ready:window_owner==4&&window_rsp_ready),
    .window_rsp_op(service_window_rsp_op),
    .window_rsp_user(service_window_rsp_user),
    .window_rsp_stream(service_window_rsp_stream),
    .window_rsp_status(service_window_rsp_status),
    .window_rsp_detail(service_window_rsp_detail),
    .window_rsp_memory_status(service_window_rsp_memory_status),
    .window_rsp_connection_error(service_window_rsp_connection_error),
    .window_rsp_http2_error(service_window_rsp_http2_error),
    .window_rsp_grant_bytes(service_window_rsp_grant_bytes),
    .window_rsp_connection_window(service_window_rsp_connection_window),
    .window_rsp_initial_window(service_window_rsp_initial_window),
    .window_rsp_stream_window(service_window_rsp_stream_window),
    .window_rsp_max_frame_bytes(service_window_rsp_max_frame_bytes),
    .window_rsp_affected_streams(service_window_rsp_affected_streams),
    .window_recovery_required(window_recovery_required),
    .window_recovery_address(window_recovery_address),
    .idle(service_idle),
    .window_busy(window_busy),
    .window_lock_status(window_lock_status),
    .directory_pool_lock_active(directory_pool_lock_active),
    .mem_valid(service_mem_valid),
    .mem_ready(service_mem_ready),
    .mem_write(service_mem_write),
    .mem_addr(service_mem_addr),
    .mem_bytes(service_mem_bytes),
    .mem_data(service_mem_data),
    .mem_rsp_valid(service_mem_rsp_valid),
    .mem_rsp_ready(service_mem_rsp_ready),
    .mem_rsp_data(service_mem_rsp_data),
    .mem_rsp_status(service_mem_rsp_status)
);
endmodule
`default_nettype wire
