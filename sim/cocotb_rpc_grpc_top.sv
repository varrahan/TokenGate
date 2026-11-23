`timescale 1ns/1ps
`default_nettype none
module cocotb_rpc_grpc_top;
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
wire [1:0] mem_valid;
wire [1:0] mem_ready;
wire [1:0] mem_write;
wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr;
wire [7:0] mem_bytes;
wire [143:0] mem_data;
wire [1:0] mem_rsp_valid;
wire [1:0] mem_rsp_ready;
wire [143:0] mem_rsp_data;
wire [15:0] mem_rsp_status;
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
reg  frame_req_ready=0;
wire [USER_WIDTH-1:0] frame_req_user;
wire [30:0] frame_req_stream;
wire [23:0] frame_req_max_bytes;
reg [23:0] frame_grant_bytes=0;
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
wire [3:0] all_valid,all_ready,all_write,all_rsp_valid,all_rsp_ready;
wire [91:0] all_addr;wire [15:0] all_bytes;wire [287:0] all_data,normal_rsp_data;
wire [31:0] normal_rsp_status;
wire [287:0] fault_rsp_data=normal_rsp_data;
reg fault_arm=0,fault_enable=0;reg [1:0] fault_client=0;
integer fault_target=0,response_index=0;reg fault_injected=0;
wire injecting=fault_enable&&!fault_injected&&response_index==fault_target;
wire [31:0] fault_rsp_status=injecting?
    (normal_rsp_status&~(32'hff<<(fault_client*8)))|(32'h75<<(fault_client*8)):normal_rsp_status;
reg program_valid=0,program_write=0;wire program_ready;
reg [22:0] program_address=0;reg [3:0] program_bytes=8;reg [71:0] program_data=0;
wire program_result_valid;reg program_result_ready=0;wire [71:0] program_result_data;wire [7:0] program_status;
wire fabric_idle;
wire inverse_valid,inverse_rsp_ready;wire [22:0] inverse_addr;wire [3:0] inverse_bytes;
rpc_grpc_parser_response dut(.*);
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
assign all_valid[1:0]={inverse_valid,mem_valid[0]};assign mem_ready=all_ready[1:0];assign all_write[1:0]={1'b0,mem_write[0]};
assign all_addr[45:0]={inverse_addr,mem_addr[22:0]};assign all_bytes[7:0]={inverse_bytes,mem_bytes[3:0]};assign all_data[143:0]={72'd0,mem_data[71:0]};
assign mem_rsp_valid=all_rsp_valid[1:0];assign all_rsp_ready[1:0]={inverse_rsp_ready,mem_rsp_ready[0]};
assign mem_rsp_data=fault_rsp_data[143:0];assign mem_rsp_status=fault_rsp_status[15:0];
assign directory_ready=store_ready;
assign directory_result_valid=store_valid&&!host_selected;
assign directory_status=store_status;assign directory_memory_status=store_memory;
assign directory_address=store_address;assign directory_application=store_application;
assign directory_generation=store_generation;assign directory_protobuf=store_protobuf;
assign directory_unsupported_encoding=store_encoding;
assign host_ready=store_ready&&!directory_valid&&idle;
assign host_result_valid=store_valid&&host_selected;assign host_status=store_status;
assign host_result_address=store_address;
grpc_stream_store registry(
    .clk(clk),.rst(rst),.req_valid(directory_valid||host_valid&&idle),.req_ready(store_ready),
    .req_op(directory_valid?3'd1:host_op),
    .cfg_pool_base(directory_valid?directory_pool_base:host_pool_base),.cfg_pool_bytes(directory_valid?directory_pool_bytes:host_pool_bytes),
    .req_user(directory_valid?directory_user:host_user),.req_application(host_application),
    .req_stream(directory_valid?directory_stream:host_stream),.req_generation(host_generation),
    .req_address(host_address),.req_buffer_base(host_buffer_base),.req_buffer_bytes(host_buffer_bytes),
    .req_message_limit(host_message_limit),.req_protobuf(host_protobuf),.req_unsupported_encoding(host_encoding),.req_maintenance(host_maintenance),.req_state(256'd0),
    .rsp_valid(store_valid),.rsp_ready(host_selected?host_result_ready:directory_result_ready),
    .rsp_status(store_status),.rsp_detail(),.rsp_memory_status(store_memory),.rsp_op(),.rsp_address(store_address),
    .rsp_buffer_base(),.rsp_buffer_bytes(),.rsp_user(),.rsp_application(store_application),.rsp_stream(),
    .rsp_generation(store_generation),.rsp_message_limit(),.rsp_protobuf(store_protobuf),.rsp_unsupported_encoding(store_encoding),.rsp_state(),
    .recovery_required(store_recovery),.recovery_address(),.idle(store_idle),
    .mem_valid(all_valid[2]),.mem_ready(all_ready[2]),.mem_write(all_write[2]),.mem_addr(all_addr[46+:23]),.mem_bytes(all_bytes[8+:4]),.mem_data(all_data[144+:72]),
    .mem_rsp_valid(all_rsp_valid[2]),.mem_rsp_ready(all_rsp_ready[2]),.mem_rsp_data(fault_rsp_data[144+:72]),.mem_rsp_status(fault_rsp_status[16+:8]));
assign all_valid[3]=program_valid;assign program_ready=all_ready[3];assign all_write[3]=program_write;
assign all_addr[69+:23]=program_address;assign all_bytes[12+:4]=program_bytes;assign all_data[216+:72]=program_data;
assign program_result_valid=all_rsp_valid[3];assign all_rsp_ready[3]=program_result_ready;
assign program_result_data=fault_rsp_data[216+:72];assign program_status=fault_rsp_status[24+:8];
external_memory_fabric #(.CLIENTS(4)) fabric(
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
    if(rst)host_selected<=0;
    else if((directory_valid||host_valid&&idle)&&store_ready)host_selected<=!directory_valid;
    if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end
    else if(all_rsp_valid[fault_client]&&all_rsp_ready[fault_client])begin
        if(injecting)fault_injected<=1;
        response_index<=response_index+1;
    end
end
endmodule
`default_nettype wire
