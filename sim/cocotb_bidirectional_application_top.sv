`timescale 1ns/1ps
`default_nettype none
module cocotb_bidirectional_application_top;
localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
reg  clk=0;
reg  rst=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
reg  queue_cfg_valid=0;
wire  queue_cfg_ready;
reg  queue_cfg_clear=0;
reg  maintenance_grant=0;
reg [MEMORY_ADDR_WIDTH-1:0] queue_cfg_base=0;
reg [MEMORY_ADDR_WIDTH:0] queue_cfg_bytes=0;
wire  queue_cfg_result_valid;
reg  queue_cfg_result_ready=0;
wire [7:0] queue_cfg_status;
reg  control_valid=0;
wire  control_ready;
reg [2:0] control_op=0;
reg [USER_WIDTH-1:0] control_user=0;
reg [USER_WIDTH-1:0] control_application=0;
reg [30:0] control_stream=0;
reg [31:0] control_generation=0;
reg [MEMORY_ADDR_WIDTH-1:0] control_address=0;
reg [MEMORY_ADDR_WIDTH-1:0] control_buffer_base=0;
reg [MEMORY_ADDR_WIDTH:0] control_buffer_bytes=0;
reg [31:0] control_message_limit=0;
reg  control_protobuf=0;
reg  control_unsupported_encoding=0;
reg  control_maintenance=0;
wire  control_result_valid;
reg  control_result_ready=0;
wire [7:0] control_status;
wire [7:0] control_detail;
wire [7:0] control_memory_status;
wire [2:0] control_result_op;
wire [MEMORY_ADDR_WIDTH-1:0] control_result_address;
wire [MEMORY_ADDR_WIDTH-1:0] control_result_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes;
wire [USER_WIDTH-1:0] control_result_user;
wire [USER_WIDTH-1:0] control_result_application;
wire [30:0] control_result_stream;
wire [31:0] control_result_generation;
wire [31:0] control_result_message_limit;
wire  control_result_protobuf;
wire  control_result_unsupported_encoding;
wire [255:0] control_result_state;
wire  packet_result_valid;
reg  packet_result_ready=0;
wire  packet_committed;
wire [7:0] packet_status;
wire [7:0] packet_detail;
wire [7:0] packet_memory_status;
wire [USER_WIDTH-1:0] packet_user;
wire [31:0] packet_tag;
wire  rpc_error_valid;
reg  rpc_error_ready=0;
wire [7:0] rpc_error_status;
wire [7:0] rpc_error_detail;
wire [7:0] rpc_error_memory_status;
wire [USER_WIDTH-1:0] rpc_error_user;
wire [USER_WIDTH-1:0] rpc_error_application;
wire [30:0] rpc_error_stream;
wire [31:0] rpc_error_generation;
wire [31:0] rpc_error_packet_tag;
wire  stream_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] stream_recovery_address;
wire  queue_recovery_required;
wire [7:0] queue_recovery_detail;
wire [7:0] queue_recovery_memory_status;
wire  retirement_pending;
wire [31:0] queued_count;
wire [31:0] pending_count;
reg  admit_messages=0;
reg  stream_cfg_valid=0;
wire  stream_cfg_ready;
wire  stream_cfg_result_valid;
reg  stream_cfg_result_ready=0;
wire [7:0] stream_cfg_status;
reg  cfg_unlock=0;
reg  cfg_schema_valid=0;
wire  cfg_schema_ready;
wire  cfg_quiescent;
reg [3:0] cfg_schema_index=0;
reg [255:0] cfg_schema_key=0;
reg [5:0] cfg_schema_key_length=0;
reg  cfg_schema_json_enable=0;
reg [28:0] cfg_schema_field=0;
reg  cfg_schema_proto_enable=0;
wire  completion_valid;
reg  completion_ready=0;
wire [7:0] completion_status;
wire [7:0] completion_detail;
wire [7:0] completion_memory_status;
wire [USER_WIDTH-1:0] completion_user;
wire [USER_WIDTH-1:0] completion_application;
wire [30:0] completion_stream;
wire [31:0] completion_generation;
wire [31:0] completion_ordinal;
wire [31:0] completion_packet_tag;
wire  payload_lease_active;
reg [1:0] cfg_token_profile=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_class_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_hash_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_node_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_edge_base=0;
reg [31:0] cfg_token_node_count=0;
reg [31:0] cfg_token_edge_count=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_work_floor=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_scalar_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_merge_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_commit_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_token_scalar_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_token_merge_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_token_commit_bytes=0;
wire [511:0] m_axis_tokens_tdata;
wire [63:0] m_axis_tokens_tkeep;
wire  m_axis_tokens_tvalid;
reg  m_axis_tokens_tready=0;
wire  m_axis_tokens_tlast;
wire [USER_WIDTH-1:0] m_axis_tokens_tuser;
wire [USER_WIDTH-1:0] dma_connection;
wire [30:0] dma_stream;
wire [31:0] dma_generation;
wire [31:0] dma_ordinal;
wire [31:0] dma_packet_tag;
wire [31:0] completion_count;
wire [7:0] completion_token_stage;
wire [7:0] completion_token_detail;
wire [7:0] completion_token_status;
reg  admit_packets=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
reg  command_valid=0;
wire  command_ready;
reg [1:0] command_op=0;
reg [USER_WIDTH-1:0] command_user=0;
reg  command_server_role=0;
reg  command_allow_push=0;
reg [23:0] command_max_frame_bytes=0;
reg [MEMORY_ADDR_WIDTH-1:0] command_buffer_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] command_table_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] command_scratch_base=0;
reg [MEMORY_ADDR_WIDTH:0] command_buffer_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] command_table_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] command_scratch_bytes=0;
reg [31:0] command_hpack_maximum=0;
reg [31:0] command_hpack_allowed=0;
reg [31:0] command_header_list_limit=0;
reg [31:0] command_required_maximum=0;
reg  command_required_update=0;
reg [511:0] s_axis_rx_tdata=0;
reg [63:0] s_axis_rx_tkeep=0;
reg  s_axis_rx_tvalid=0;
wire  s_axis_rx_tready;
reg  s_axis_rx_tlast=0;
reg [USER_WIDTH-1:0] s_axis_rx_tuser=0;
wire  rsp_valid;
reg  rsp_ready=0;
wire  rsp_is_command;
wire [1:0] rsp_command_op;
wire [7:0] rsp_status;
wire [7:0] rsp_detail;
wire [7:0] rsp_memory_status;
wire [31:0] rsp_http2_error;
wire [USER_WIDTH-1:0] rsp_user;
reg [31:0] s_axis_rx_tag=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_route_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_route_strings_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_payload_slot_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_route_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_route_strings_bytes=0;
reg [31:0] cfg_routes=0;
reg [31:0] cfg_model_epoch=0;
reg [31:0] cfg_schema_epoch=0;
wire  header_valid;
reg  header_ready=0;
wire [3:0] header_status;
wire [7:0] header_detail;
wire [7:0] header_memory_status;
wire [7:0] header_control_status;
wire [7:0] header_cleanup_status;
wire  header_connection_error;
wire [31:0] header_http2_error;
wire [9:0] header_http_status;
wire [7:0] header_grpc_status;
wire [USER_WIDTH-1:0] header_user;
wire [30:0] header_stream;
wire [31:0] header_generation;
wire [MEMORY_ADDR_WIDTH-1:0] header_address;
wire [15:0] header_application;
wire [31:0] header_model_epoch;
wire [31:0] header_schema_epoch;
wire  header_trailers;
wire  header_end_stream;
wire  admission_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] admission_recovery_address;
wire [USER_WIDTH-1:0] admission_recovery_user;
wire  transport_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] transport_recovery_address;
wire  control_event_valid;
reg  control_event_ready=0;
wire [3:0] control_event_kind;
wire [31:0] control_event_arg0;
wire [31:0] control_event_arg1;
wire [30:0] control_event_stream;
wire [USER_WIDTH-1:0] control_event_user;
wire [7:0] transport_packet_status;
wire [7:0] transport_packet_detail;
wire [7:0] transport_packet_memory_status;
wire [31:0] transport_packet_http2_error;
wire  idle;
wire [21:0] mem_valid;
wire [21:0] mem_ready;
wire [21:0] mem_write;
wire [22*MEMORY_ADDR_WIDTH-1:0] mem_addr;
wire [87:0] mem_bytes;
wire [1583:0] mem_data;
wire [21:0] mem_rsp_valid;
wire [21:0] mem_rsp_ready;
wire [1583:0] mem_rsp_data;
wire [175:0] mem_rsp_status;
reg [31:0] s_axis_generated_tdata=0;
reg [3:0] s_axis_generated_tkeep=0;
reg  s_axis_generated_tvalid=0;
wire  s_axis_generated_tready;
reg  s_axis_generated_tlast=0;
reg [USER_WIDTH-1:0] s_axis_generated_tuser=0;
reg [30:0] generated_stream=0;
reg [31:0] generated_generation=0;
reg [31:0] generated_model_epoch=0;
reg [31:0] generated_schema_epoch=0;
reg [31:0] generated_ordinal=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_response_progress_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_response_progress_bytes=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_response_directory_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_response_pool_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_response_directory_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_response_pool_bytes=0;
reg  cfg_response_strip_special=0;
reg  cfg_response_replace_invalid=0;
reg [1:0] cfg_response_format=0;
reg [28:0] cfg_response_protobuf_field=0;
wire [511:0] m_axis_tx_tdata;
wire [63:0] m_axis_tx_tkeep;
wire  m_axis_tx_tvalid;
reg  m_axis_tx_tready=0;
wire  m_axis_tx_tlast;
wire [USER_WIDTH-1:0] m_axis_tx_tuser;
wire  response_result_valid;
reg  response_result_ready=0;
wire [7:0] response_result_stage;
wire [7:0] response_result_status;
wire [7:0] response_result_memory_status;
wire [USER_WIDTH-1:0] response_result_user;
wire [USER_WIDTH-1:0] response_result_application;
wire [30:0] response_result_stream;
wire [31:0] response_result_generation;
wire [31:0] response_result_model_epoch;
wire [31:0] response_result_schema_epoch;
wire [31:0] response_result_ordinal;
wire [31:0] response_result_bytes;
wire  response_result_eos;
wire  response_result_tx_emitted;
wire  response_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] response_recovery_address;
wire  response_directory_lease_active;
wire  response_idle;
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
wire fabric_idle;wire [175:0] fabric_status;
integer fault_client=-1,fault_target=-1,response_index=0;reg fault_arm=0,fault_injected=0;
http2_bidirectional_application dut(.*);
external_memory_fabric #(.CLIENTS(22)) fabric(
.clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),
.s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(mem_data),
.rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(mem_rsp_data),.rsp_status(fabric_status),
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
generate for(genvar client=0;client<22;client=client+1)begin: fault_ports
assign mem_rsp_status[client*8+:8]=(fault_client==client&&!fault_injected&&response_index==fault_target)?8'h75:fabric_status[client*8+:8];
end endgenerate
always @(posedge clk)begin
if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end
else if(fault_client>=0&&fault_client<22&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin
if(!fault_injected&&response_index==fault_target)fault_injected<=1;response_index<=response_index+1;
end
end
endmodule
`default_nettype wire
