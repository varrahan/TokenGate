`timescale 1ns/1ps
`default_nettype none
module cocotb_rpc_durable_top;
localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
reg  clk=0;
reg  rst=0;
reg [31:0] s_axis_tokens_tdata=0;
reg [3:0] s_axis_tokens_tkeep=0;
reg  s_axis_tokens_tvalid=0;
wire  s_axis_tokens_tready;
reg  s_axis_tokens_tlast=0;
reg [USER_WIDTH-1:0] s_axis_tokens_tuser=0;
reg [30:0] s_stream=0;
reg [31:0] s_generation=0;
reg [31:0] s_model_epoch=0;
reg [31:0] s_schema_epoch=0;
reg [31:0] s_ordinal=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_progress_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_progress_bytes=0;
reg [31:0] cfg_model_epoch=0;
reg [31:0] cfg_schema_epoch=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_directory_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_directory_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes=0;
reg  cfg_strip_special=0;
reg  cfg_replace_invalid=0;
reg [1:0] cfg_format=0;
reg [28:0] cfg_protobuf_field=0;
wire  directory_valid;
wire  directory_ready;
wire [USER_WIDTH-1:0] directory_user;
wire [30:0] directory_stream;
wire [MEMORY_ADDR_WIDTH-1:0] directory_pool_base;
wire [MEMORY_ADDR_WIDTH:0] directory_pool_bytes;
wire  directory_result_valid;
wire  directory_result_ready;
wire [7:0] directory_status;
wire [7:0] directory_memory_status;
wire [MEMORY_ADDR_WIDTH-1:0] directory_address;
wire [USER_WIDTH-1:0] directory_application;
wire [31:0] directory_generation;
wire  directory_protobuf;
wire  directory_unsupported_encoding;
wire [511:0] m_axis_tx_tdata;
wire [63:0] m_axis_tx_tkeep;
wire  m_axis_tx_tvalid;
reg  m_axis_tx_tready=0;
wire  m_axis_tx_tlast;
wire [USER_WIDTH-1:0] m_axis_tx_tuser;
wire  result_valid;
reg  result_ready=0;
wire [7:0] result_stage;
wire [7:0] result_status;
wire [7:0] result_memory_status;
wire [USER_WIDTH-1:0] result_user;
wire [USER_WIDTH-1:0] result_application;
wire [30:0] result_stream;
wire [31:0] result_generation;
wire [31:0] result_model_epoch;
wire [31:0] result_schema_epoch;
wire [31:0] result_ordinal;
wire [31:0] result_bytes;
wire  result_eos;
wire  result_tx_emitted;
wire  recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] recovery_address;
wire  directory_lease_active;
wire  idle;
wire [3*1-1:0] mem_valid;
wire [3*1-1:0] mem_ready;
wire [3*1-1:0] mem_write;
wire [3*MEMORY_ADDR_WIDTH-1:0] mem_addr;
wire [3*4-1:0] mem_bytes;
wire [3*72-1:0] mem_data;
wire [3*1-1:0] mem_rsp_valid;
wire [3*1-1:0] mem_rsp_ready;
wire [3*72-1:0] mem_rsp_data;
wire [3*8-1:0] mem_rsp_status;
wire [31:0] link_r_s_axis_tokens_tdata;
wire [3:0] link_r_s_axis_tokens_tkeep;
wire  link_r_s_axis_tokens_tvalid;
wire  link_r_s_axis_tokens_tready;
wire  link_r_s_axis_tokens_tlast;
wire [USER_WIDTH-1:0] link_r_s_axis_tokens_tuser;
wire  link_r_lease_valid;
wire [USER_WIDTH-1:0] link_r_lease_user;
wire [USER_WIDTH-1:0] link_r_lease_application;
wire [30:0] link_r_lease_stream;
wire [31:0] link_r_lease_generation;
wire [31:0] link_r_lease_model_epoch;
wire [31:0] link_r_lease_schema_epoch;
wire [31:0] link_r_cfg_active_model_epoch;
wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_directory_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_pool_base;
wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_directory_bytes;
wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_pool_bytes;
wire  link_r_cfg_strip_special;
wire  link_r_cfg_replace_invalid;
wire [1:0] link_r_cfg_format;
wire [28:0] link_r_cfg_protobuf_field;
wire [23:0] link_r_carry_in;
wire [1:0] link_r_carry_in_count;
wire  link_r_result_valid;
wire  link_r_result_ready;
wire [7:0] link_r_result_stage;
wire [7:0] link_r_result_status;
wire [7:0] link_r_result_memory_status;
wire [23:0] link_r_carry_out;
wire [1:0] link_r_carry_out_count;
wire [31:0] link_r_result_bytes;
wire  link_r_idle;
wire  link_s_start_valid;
wire  link_s_start_ready;
wire [USER_WIDTH-1:0] link_s_start_user;
wire  link_s_start_eos;
wire  link_s_start_replace;
wire [23:0] link_s_start_carry;
wire [1:0] link_s_start_carry_count;
wire [1:0] link_s_start_format;
wire [28:0] link_s_start_protobuf_field;
wire [127:0] link_s_s_axis_text_tdata;
wire [15:0] link_s_s_axis_text_tkeep;
wire  link_s_s_axis_text_tvalid;
wire  link_s_s_axis_text_tready;
wire  link_s_s_axis_text_tlast;
wire [USER_WIDTH-1:0] link_s_s_axis_text_tuser;
wire  link_s_s_axis_text_abort;
wire  link_s_result_valid;
wire  link_s_result_ready;
wire [7:0] link_s_result_stage;
wire [7:0] link_s_result_status;
wire [23:0] link_s_result_carry;
wire [1:0] link_s_result_carry_count;
wire [31:0] link_s_result_bytes;
wire  link_s_idle;
reg [23:0] cfg_peer_max_frame_bytes=0;
wire  frame_req_valid;
wire frame_req_ready;
wire [USER_WIDTH-1:0] frame_req_user;
wire [30:0] frame_req_stream;
wire [23:0] frame_req_max_bytes;
wire [23:0] frame_grant_bytes;
wire [31:0] result_serialized_bytes;
wire [31:0] result_wire_bytes;
wire [31:0] result_frames;
wire  result_progress_committed;
reg  m_axi_arready=0;
reg [63:0] m_axi_rdata=0;
reg [1:0] m_axi_rresp=0;
reg  m_axi_rlast=0;
reg  m_axi_rvalid=0;
reg  m_axi_awready=0;
reg  m_axi_wready=0;
reg [1:0] m_axi_bresp=0;
reg  m_axi_bvalid=0;
wire [22:0] m_axi_araddr;
wire [7:0] m_axi_arlen;
wire [2:0] m_axi_arsize;
wire [1:0] m_axi_arburst;
wire  m_axi_arvalid;
wire  m_axi_rready;
wire [22:0] m_axi_awaddr;
wire [7:0] m_axi_awlen;
wire [2:0] m_axi_awsize;
wire [1:0] m_axi_awburst;
wire  m_axi_awvalid;
wire [63:0] m_axi_wdata;
wire [7:0] m_axi_wstrb;
wire  m_axi_wlast;
wire  m_axi_wvalid;
wire  m_axi_bready;
reg host_valid=0;wire host_ready;reg [2:0] host_op=0;
reg [22:0] host_pool_base=0,host_address=0,host_buffer_base=0;
reg [23:0] host_pool_bytes=0,host_buffer_bytes=0;
reg [15:0] host_user=0,host_application=0;reg [30:0] host_stream=0;
reg [31:0] host_generation=0,host_message_limit=0;
reg host_protobuf=0,host_encoding=0,host_maintenance=0;
wire host_result_valid;reg host_result_ready=0;wire [7:0] host_status;
wire [22:0] host_result_address;wire store_recovery,store_idle;
reg host_selected=0;
wire store_ready,store_valid;wire [7:0] store_status,store_memory;
wire [22:0] store_address;wire [15:0] store_application;wire [31:0] store_generation;
wire store_protobuf,store_encoding;
wire [4:0] all_valid,all_ready,all_write,all_rsp_valid,all_rsp_ready;
wire [114:0] all_addr;wire [19:0] all_bytes;wire [359:0] all_data,normal_rsp_data;
wire [39:0] normal_rsp_status;
wire [359:0] fault_rsp_data=normal_rsp_data;
reg fault_arm=0,fault_enable=0;reg [2:0] fault_client=0;
integer fault_target=0,response_index=0;reg fault_injected=0;
wire injecting=fault_enable&&!fault_injected&&response_index==fault_target;
wire [39:0] fault_rsp_status=injecting?
    (normal_rsp_status&~(40'hff<<(fault_client*8)))|(40'h75<<(fault_client*8)):normal_rsp_status;
reg program_valid=0,program_write=0;wire program_ready;
reg [22:0] program_address=0;reg [3:0] program_bytes=8;reg [71:0] program_data=0;
wire program_result_valid;reg program_result_ready=0;wire [71:0] program_result_data;wire [7:0] program_status;
wire fabric_idle;
wire inverse_valid,inverse_rsp_ready;wire [22:0] inverse_addr;wire [3:0] inverse_bytes;
reg [255:0] host_state=0;
wire [7:0] host_detail;
wire [7:0] host_memory_status;
wire [2:0] host_result_op;
wire [MEMORY_ADDR_WIDTH-1:0] host_result_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] host_result_buffer_bytes;
wire [USER_WIDTH-1:0] host_result_user;
wire [USER_WIDTH-1:0] host_result_application;
wire [30:0] host_result_stream;
wire [31:0] host_result_generation;
wire [31:0] host_result_message_limit;
wire  host_result_protobuf;
wire  host_result_encoding;
wire [255:0] host_result_state;
wire  record_lease_active;
wire  directory_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] directory_recovery_address;
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
wire [USER_WIDTH-1:0] window_rsp_user;
wire [30:0] window_rsp_stream;
wire [7:0] window_rsp_status;
wire [7:0] window_rsp_detail;
wire [7:0] window_rsp_memory_status;
wire  window_rsp_connection_error;
wire [31:0] window_rsp_http2_error;
wire [23:0] window_rsp_grant_bytes;
wire [31:0] window_rsp_connection_window;
wire [31:0] window_rsp_initial_window;
wire [31:0] window_rsp_stream_window;
wire [23:0] window_rsp_max_frame_bytes;
wire [31:0] window_rsp_affected_streams;
wire  window_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] window_recovery_address;
wire  window_busy;
wire [7:0] window_lock_status;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_window_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_window_bytes=0;
wire  credit_parked;
wire  directory_pool_lock_active;
wire [7:0] result_credit_status;
wire [7:0] result_credit_detail;
wire [31:0] result_credit_http2_error;
wire  result_credit_connection_error;
`ifdef PARSER_RPC_KEYED
rpc_grpc_keyed_return
`else
rpc_grpc_durable_return
`endif
#(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) dut(
    .clk(clk),
    .rst(rst),
    .s_axis_tokens_tdata(s_axis_tokens_tdata),
    .s_axis_tokens_tkeep(s_axis_tokens_tkeep),
    .s_axis_tokens_tvalid(s_axis_tokens_tvalid),
    .s_axis_tokens_tready(s_axis_tokens_tready),
    .s_axis_tokens_tlast(s_axis_tokens_tlast),
    .s_axis_tokens_tuser(s_axis_tokens_tuser),
    .s_stream(s_stream),
    .s_generation(s_generation),
    .s_model_epoch(s_model_epoch),
    .s_schema_epoch(s_schema_epoch),
    .s_ordinal(s_ordinal),
    .cfg_stream_base(cfg_stream_base),
    .cfg_progress_base(cfg_progress_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_stream_bytes(cfg_stream_bytes),
    .cfg_progress_bytes(cfg_progress_bytes),
    .cfg_model_epoch(cfg_model_epoch),
    .cfg_schema_epoch(cfg_schema_epoch),
    .cfg_directory_base(cfg_directory_base),
    .cfg_pool_base(cfg_pool_base),
    .cfg_directory_bytes(cfg_directory_bytes),
    .cfg_pool_bytes(cfg_pool_bytes),
    .cfg_strip_special(cfg_strip_special),
    .cfg_replace_invalid(cfg_replace_invalid),
    .cfg_format(cfg_format),
    .cfg_protobuf_field(cfg_protobuf_field),
    .m_axis_tx_tdata(m_axis_tx_tdata),
    .m_axis_tx_tkeep(m_axis_tx_tkeep),
    .m_axis_tx_tvalid(m_axis_tx_tvalid),
    .m_axis_tx_tready(m_axis_tx_tready),
    .m_axis_tx_tlast(m_axis_tx_tlast),
    .m_axis_tx_tuser(m_axis_tx_tuser),
    .result_valid(result_valid),
    .result_ready(result_ready),
    .result_stage(result_stage),
    .result_status(result_status),
    .result_memory_status(result_memory_status),
    .result_user(result_user),
    .result_application(result_application),
    .result_stream(result_stream),
    .result_generation(result_generation),
    .result_model_epoch(result_model_epoch),
    .result_schema_epoch(result_schema_epoch),
    .result_ordinal(result_ordinal),
    .result_bytes(result_bytes),
    .result_eos(result_eos),
    .result_tx_emitted(result_tx_emitted),
    .recovery_required(recovery_required),
    .recovery_address(recovery_address),
    .directory_lease_active(directory_lease_active),
    .idle(idle),
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
    .link_r_s_axis_tokens_tdata(link_r_s_axis_tokens_tdata),
    .link_r_s_axis_tokens_tkeep(link_r_s_axis_tokens_tkeep),
    .link_r_s_axis_tokens_tvalid(link_r_s_axis_tokens_tvalid),
    .link_r_s_axis_tokens_tready(link_r_s_axis_tokens_tready),
    .link_r_s_axis_tokens_tlast(link_r_s_axis_tokens_tlast),
    .link_r_s_axis_tokens_tuser(link_r_s_axis_tokens_tuser),
    .link_r_lease_valid(link_r_lease_valid),
    .link_r_lease_user(link_r_lease_user),
    .link_r_lease_application(link_r_lease_application),
    .link_r_lease_stream(link_r_lease_stream),
    .link_r_lease_generation(link_r_lease_generation),
    .link_r_lease_model_epoch(link_r_lease_model_epoch),
    .link_r_lease_schema_epoch(link_r_lease_schema_epoch),
    .link_r_cfg_active_model_epoch(link_r_cfg_active_model_epoch),
    .link_r_cfg_directory_base(link_r_cfg_directory_base),
    .link_r_cfg_pool_base(link_r_cfg_pool_base),
    .link_r_cfg_directory_bytes(link_r_cfg_directory_bytes),
    .link_r_cfg_pool_bytes(link_r_cfg_pool_bytes),
    .link_r_cfg_strip_special(link_r_cfg_strip_special),
    .link_r_cfg_replace_invalid(link_r_cfg_replace_invalid),
    .link_r_cfg_format(link_r_cfg_format),
    .link_r_cfg_protobuf_field(link_r_cfg_protobuf_field),
    .link_r_carry_in(link_r_carry_in),
    .link_r_carry_in_count(link_r_carry_in_count),
    .link_r_result_valid(link_r_result_valid),
    .link_r_result_ready(link_r_result_ready),
    .link_r_result_stage(link_r_result_stage),
    .link_r_result_status(link_r_result_status),
    .link_r_result_memory_status(link_r_result_memory_status),
    .link_r_carry_out(link_r_carry_out),
    .link_r_carry_out_count(link_r_carry_out_count),
    .link_r_result_bytes(link_r_result_bytes),
    .link_r_idle(link_r_idle),
    .link_s_start_valid(link_s_start_valid),
    .link_s_start_ready(link_s_start_ready),
    .link_s_start_user(link_s_start_user),
    .link_s_start_eos(link_s_start_eos),
    .link_s_start_replace(link_s_start_replace),
    .link_s_start_carry(link_s_start_carry),
    .link_s_start_carry_count(link_s_start_carry_count),
    .link_s_start_format(link_s_start_format),
    .link_s_start_protobuf_field(link_s_start_protobuf_field),
    .link_s_s_axis_text_tdata(link_s_s_axis_text_tdata),
    .link_s_s_axis_text_tkeep(link_s_s_axis_text_tkeep),
    .link_s_s_axis_text_tvalid(link_s_s_axis_text_tvalid),
    .link_s_s_axis_text_tready(link_s_s_axis_text_tready),
    .link_s_s_axis_text_tlast(link_s_s_axis_text_tlast),
    .link_s_s_axis_text_tuser(link_s_s_axis_text_tuser),
    .link_s_s_axis_text_abort(link_s_s_axis_text_abort),
    .link_s_result_valid(link_s_result_valid),
    .link_s_result_ready(link_s_result_ready),
    .link_s_result_stage(link_s_result_stage),
    .link_s_result_status(link_s_result_status),
    .link_s_result_carry(link_s_result_carry),
    .link_s_result_carry_count(link_s_result_carry_count),
    .link_s_result_bytes(link_s_result_bytes),
    .link_s_idle(link_s_idle),
    .cfg_peer_max_frame_bytes(cfg_peer_max_frame_bytes),
    .result_serialized_bytes(result_serialized_bytes),
    .result_wire_bytes(result_wire_bytes),
    .result_frames(result_frames),
    .result_progress_committed(result_progress_committed),
    .control_req_valid(host_valid),
    .control_req_ready(host_ready),
    .control_req_op(host_op),
    .control_pool_base(host_pool_base),
    .control_pool_bytes(host_pool_bytes),
    .control_req_user(host_user),
    .control_req_application(host_application),
    .control_req_stream(host_stream),
    .control_req_generation(host_generation),
    .control_req_address(host_address),
    .control_req_buffer_base(host_buffer_base),
    .control_req_buffer_bytes(host_buffer_bytes),
    .control_req_message_limit(host_message_limit),
    .control_req_protobuf(host_protobuf),
    .control_req_unsupported_encoding(host_encoding),
    .control_req_maintenance(host_maintenance),
    .control_req_state(host_state),
    .control_rsp_valid(host_result_valid),
    .control_rsp_ready(host_result_ready),
    .control_rsp_status(host_status),
    .control_rsp_detail(host_detail),
    .control_rsp_memory_status(host_memory_status),
    .control_rsp_op(host_result_op),
    .control_rsp_address(host_result_address),
    .control_rsp_buffer_base(host_result_buffer_base),
    .control_rsp_buffer_bytes(host_result_buffer_bytes),
    .control_rsp_user(host_result_user),
    .control_rsp_application(host_result_application),
    .control_rsp_stream(host_result_stream),
    .control_rsp_generation(host_result_generation),
    .control_rsp_message_limit(host_result_message_limit),
    .control_rsp_protobuf(host_result_protobuf),
    .control_rsp_unsupported_encoding(host_result_encoding),
    .control_rsp_state(host_result_state),
    .record_lease_active(record_lease_active),
    .directory_recovery_required(directory_recovery_required),
    .directory_recovery_address(directory_recovery_address),
    .window_req_valid(window_req_valid),
    .window_req_ready(window_req_ready),
    .window_req_op(window_req_op),
    .window_req_maintenance(window_req_maintenance),
    .window_req_user(window_req_user),
    .window_req_stream(window_req_stream),
    .window_req_generation(window_req_generation),
    .window_req_record_address(window_req_record_address),
    .window_req_amount(window_req_amount),
    .window_cfg_context_base(window_cfg_context_base),
    .window_cfg_stream_base(window_cfg_stream_base),
    .window_cfg_window_base(window_cfg_window_base),
    .window_cfg_work_floor(window_cfg_work_floor),
    .window_cfg_context_bytes(window_cfg_context_bytes),
    .window_cfg_stream_bytes(window_cfg_stream_bytes),
    .window_cfg_window_bytes(window_cfg_window_bytes),
    .window_rsp_valid(window_rsp_valid),
    .window_rsp_ready(window_rsp_ready),
    .window_rsp_op(window_rsp_op),
    .window_rsp_user(window_rsp_user),
    .window_rsp_stream(window_rsp_stream),
    .window_rsp_status(window_rsp_status),
    .window_rsp_detail(window_rsp_detail),
    .window_rsp_memory_status(window_rsp_memory_status),
    .window_rsp_connection_error(window_rsp_connection_error),
    .window_rsp_http2_error(window_rsp_http2_error),
    .window_rsp_grant_bytes(window_rsp_grant_bytes),
    .window_rsp_connection_window(window_rsp_connection_window),
    .window_rsp_initial_window(window_rsp_initial_window),
    .window_rsp_stream_window(window_rsp_stream_window),
    .window_rsp_max_frame_bytes(window_rsp_max_frame_bytes),
    .window_rsp_affected_streams(window_rsp_affected_streams),
    .window_recovery_required(window_recovery_required),
    .window_recovery_address(window_recovery_address),
    .window_busy(window_busy),
    .window_lock_status(window_lock_status),
    .cfg_context_base(cfg_context_base),
    .cfg_context_bytes(cfg_context_bytes),
    .cfg_window_base(cfg_window_base),
    .cfg_window_bytes(cfg_window_bytes),
    .credit_parked(credit_parked),
    .directory_pool_lock_active(directory_pool_lock_active),
    .result_credit_status(result_credit_status),
    .result_credit_detail(result_credit_detail),
    .result_credit_http2_error(result_credit_http2_error),
    .result_credit_connection_error(result_credit_connection_error)
);
inverse_tokenizer_partition #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) inverse(
    .clk(clk),
    .rst(rst),
    .s_axis_tokens_tdata(link_r_s_axis_tokens_tdata),
    .s_axis_tokens_tkeep(link_r_s_axis_tokens_tkeep),
    .s_axis_tokens_tvalid(link_r_s_axis_tokens_tvalid),
    .s_axis_tokens_tready(link_r_s_axis_tokens_tready),
    .s_axis_tokens_tlast(link_r_s_axis_tokens_tlast),
    .s_axis_tokens_tuser(link_r_s_axis_tokens_tuser),
    .lease_valid(link_r_lease_valid),
    .lease_user(link_r_lease_user),
    .lease_application(link_r_lease_application),
    .lease_stream(link_r_lease_stream),
    .lease_generation(link_r_lease_generation),
    .lease_model_epoch(link_r_lease_model_epoch),
    .lease_schema_epoch(link_r_lease_schema_epoch),
    .cfg_active_model_epoch(link_r_cfg_active_model_epoch),
    .cfg_directory_base(link_r_cfg_directory_base),
    .cfg_pool_base(link_r_cfg_pool_base),
    .cfg_directory_bytes(link_r_cfg_directory_bytes),
    .cfg_pool_bytes(link_r_cfg_pool_bytes),
    .cfg_strip_special(link_r_cfg_strip_special),
    .cfg_replace_invalid(link_r_cfg_replace_invalid),
    .cfg_format(link_r_cfg_format),
    .cfg_protobuf_field(link_r_cfg_protobuf_field),
    .carry_in(link_r_carry_in),
    .carry_in_count(link_r_carry_in_count),
    .result_valid(link_r_result_valid),
    .result_ready(link_r_result_ready),
    .result_stage(link_r_result_stage),
    .result_status(link_r_result_status),
    .result_memory_status(link_r_result_memory_status),
    .carry_out(link_r_carry_out),
    .carry_out_count(link_r_carry_out_count),
    .result_bytes(link_r_result_bytes),
    .result_user(),
    .result_application(),
    .result_stream(),
    .result_generation(),
    .result_model_epoch(),
    .result_schema_epoch(),
    .result_eos(),
    .mem_rd_valid(inverse_valid),
    .mem_rd_ready(all_ready[1]),
    .mem_rd_addr(inverse_addr),
    .mem_rd_bytes(inverse_bytes),
    .mem_rsp_valid(all_rsp_valid[1]),
    .mem_rsp_ready(inverse_rsp_ready),
    .mem_rsp_data(fault_rsp_data[72+:72]),
    .mem_rsp_status(fault_rsp_status[8+:8]),
    .idle(link_r_idle),
    .link_s_start_valid(link_s_start_valid),
    .link_s_start_ready(link_s_start_ready),
    .link_s_start_user(link_s_start_user),
    .link_s_start_eos(link_s_start_eos),
    .link_s_start_replace(link_s_start_replace),
    .link_s_start_carry(link_s_start_carry),
    .link_s_start_carry_count(link_s_start_carry_count),
    .link_s_start_format(link_s_start_format),
    .link_s_start_protobuf_field(link_s_start_protobuf_field),
    .link_s_s_axis_text_tdata(link_s_s_axis_text_tdata),
    .link_s_s_axis_text_tkeep(link_s_s_axis_text_tkeep),
    .link_s_s_axis_text_tvalid(link_s_s_axis_text_tvalid),
    .link_s_s_axis_text_tready(link_s_s_axis_text_tready),
    .link_s_s_axis_text_tlast(link_s_s_axis_text_tlast),
    .link_s_s_axis_text_tuser(link_s_s_axis_text_tuser),
    .link_s_s_axis_text_abort(link_s_s_axis_text_abort),
    .link_s_result_valid(link_s_result_valid),
    .link_s_result_ready(link_s_result_ready),
    .link_s_result_stage(link_s_result_stage),
    .link_s_result_status(link_s_result_status),
    .link_s_result_carry(link_s_result_carry),
    .link_s_result_carry_count(link_s_result_carry_count),
    .link_s_result_bytes(link_s_result_bytes),
    .link_s_idle(link_s_idle)
);
assign all_valid[1:0]={inverse_valid,mem_valid[0]};assign mem_ready={all_ready[4],all_ready[2],all_ready[0]};assign all_write[1:0]={1'b0,mem_write[0]};
assign all_addr[45:0]={inverse_addr,mem_addr[22:0]};assign all_bytes[7:0]={inverse_bytes,mem_bytes[3:0]};assign all_data[143:0]={72'd0,mem_data[71:0]};
assign mem_rsp_valid={all_rsp_valid[4],all_rsp_valid[2],all_rsp_valid[0]};assign all_rsp_ready[1:0]={inverse_rsp_ready,mem_rsp_ready[0]};
assign mem_rsp_data={fault_rsp_data[288+:72],fault_rsp_data[144+:72],fault_rsp_data[0+:72]};assign mem_rsp_status={fault_rsp_status[32+:8],fault_rsp_status[16+:8],fault_rsp_status[0+:8]};
assign frame_req_valid=dut.frame_req_valid;
assign frame_req_ready=dut.frame_req_ready;
assign frame_req_user=dut.frame_req_user;
assign frame_req_stream=dut.frame_req_stream;
assign frame_req_max_bytes=dut.frame_req_max_bytes;
assign frame_grant_bytes=dut.frame_grant_bytes;
assign directory_valid=dut.directory_valid;
assign directory_ready=dut.directory_ready;
assign directory_user=dut.directory_user;
assign directory_stream=dut.directory_stream;
assign directory_pool_base=dut.directory_pool_base;
assign directory_pool_bytes=dut.directory_pool_bytes;
assign directory_result_valid=dut.directory_result_valid;
assign directory_result_ready=dut.directory_result_ready;
assign directory_status=dut.directory_status;
assign directory_memory_status=dut.directory_memory_status;
assign directory_address=dut.directory_address;
assign directory_application=dut.directory_application;
assign directory_generation=dut.directory_generation;
assign directory_protobuf=dut.directory_protobuf;
assign directory_unsupported_encoding=dut.directory_unsupported_encoding;
assign all_valid[2]=mem_valid[1];assign all_write[2]=mem_write[1];
assign all_addr[46+:23]=mem_addr[23+:23];assign all_bytes[8+:4]=mem_bytes[4+:4];
assign all_data[144+:72]=mem_data[72+:72];assign all_rsp_ready[2]=mem_rsp_ready[1];
assign store_recovery=directory_recovery_required;
assign store_ready=host_ready;assign store_idle=dut.directory_service.owned.directory.backend_idle;
assign all_valid[4]=mem_valid[2];assign all_write[4]=mem_write[2];
assign all_addr[92+:23]=mem_addr[46+:23];assign all_bytes[16+:4]=mem_bytes[8+:4];
assign all_data[288+:72]=mem_data[144+:72];assign all_rsp_ready[4]=mem_rsp_ready[2];
assign all_valid[3]=program_valid;assign program_ready=all_ready[3];assign all_write[3]=program_write;
assign all_addr[69+:23]=program_address;assign all_bytes[12+:4]=program_bytes;assign all_data[216+:72]=program_data;
assign program_result_valid=all_rsp_valid[3];assign all_rsp_ready[3]=program_result_ready;
assign program_result_data=fault_rsp_data[216+:72];assign program_status=fault_rsp_status[24+:8];
external_memory_fabric #(.CLIENTS(5)) fabric(
    .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),
    .s_valid(all_valid),.s_ready(all_ready),.s_write(all_write),.s_addr(all_addr),.s_bytes(all_bytes),.s_data(all_data),
    .rsp_valid(all_rsp_valid),.rsp_ready(all_rsp_ready),.rsp_data(normal_rsp_data),.rsp_status(normal_rsp_status),
.m_axi_araddr(m_axi_araddr),
.m_axi_arlen(m_axi_arlen),
.m_axi_arsize(m_axi_arsize),
.m_axi_arburst(m_axi_arburst),
.m_axi_arvalid(m_axi_arvalid),
.m_axi_rready(m_axi_rready),
.m_axi_awaddr(m_axi_awaddr),
.m_axi_awlen(m_axi_awlen),
.m_axi_awsize(m_axi_awsize),
.m_axi_awburst(m_axi_awburst),
.m_axi_awvalid(m_axi_awvalid),
.m_axi_wdata(m_axi_wdata),
.m_axi_wstrb(m_axi_wstrb),
.m_axi_wlast(m_axi_wlast),
.m_axi_wvalid(m_axi_wvalid),
.m_axi_bready(m_axi_bready),
.m_axi_arready(m_axi_arready),
.m_axi_rdata(m_axi_rdata),
.m_axi_rresp(m_axi_rresp),
.m_axi_rlast(m_axi_rlast),
.m_axi_rvalid(m_axi_rvalid),
.m_axi_awready(m_axi_awready),
.m_axi_wready(m_axi_wready),
.m_axi_bresp(m_axi_bresp),
.m_axi_bvalid(m_axi_bvalid),
.idle(fabric_idle));
always @(posedge clk)begin
    if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end
    else if(all_rsp_valid[fault_client]&&all_rsp_ready[fault_client])begin
        if(injecting)fault_injected<=1;
        response_index<=response_index+1;
    end
end
endmodule
`default_nettype wire
