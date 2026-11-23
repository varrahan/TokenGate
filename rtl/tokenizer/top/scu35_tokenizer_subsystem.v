`timescale 1ns/1ps
`default_nettype none
// Bidirectional tokenizer, one shared BRAM cache, ten external-memory clients.
// The external loader validates images and changes configuration while the
// epoch grant is asserted. cfg_* is a command/completion interface; an AXI-Lite
// register bridge and physical external-memory controller belong above it.
module scu35_tokenizer_subsystem #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,parameter integer CACHE_LOG_LINES=6
)(
    input wire clk,input wire rst,
    input wire update_req,input wire commit,input wire abort_update,input wire tables_valid,
    output wire cfg_unlock,output wire [31:0] epoch,output wire vocabulary_valid,output wire protocol_error,output wire draining,
    input wire cfg_valid,output wire cfg_ready,input wire [MEMORY_ADDR_WIDTH-1:0] cfg_addr,input wire [3:0] cfg_bytes,input wire [71:0] cfg_data,
    output wire cfg_rsp_valid,input wire cfg_rsp_ready,output wire [7:0] cfg_rsp_status,
    input wire cfg_invalidate_valid,output wire cfg_invalidate_ready,
    input wire [1:0] cfg_profile,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_class_base,cfg_hash_base,cfg_node_base,cfg_edge_base,
    input wire [31:0] cfg_node_count,cfg_edge_count,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,cfg_scalar_base,cfg_merge_base,cfg_commit_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_scalar_bytes,cfg_merge_bytes,cfg_commit_bytes,
    input wire [MEMORY_ADDR_WIDTH-1:0] directory_base,pool_base,input wire strip_special_tokens,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,input wire s_axis_text_tlast,input wire [USER_WIDTH-1:0] s_axis_text_tuser,
    output wire [511:0] m_axis_tokens_tdata,output wire [63:0] m_axis_tokens_tkeep,
    output wire m_axis_tokens_tvalid,input wire m_axis_tokens_tready,output wire m_axis_tokens_tlast,output wire [USER_WIDTH-1:0] m_axis_tokens_tuser,
    output wire completion_valid,input wire completion_ready,output wire completion_failed,output wire [31:0] completion_count,output wire [USER_WIDTH-1:0] completion_user,
    output wire forward_error_valid,input wire forward_error_ready,output wire [7:0] forward_error_stage,forward_error_detail,forward_error_status,output wire [USER_WIDTH-1:0] forward_error_user,
    input wire [31:0] s_axis_generated_tdata,input wire s_axis_generated_tvalid,output wire s_axis_generated_tready,input wire s_axis_generated_tlast,input wire [USER_WIDTH-1:0] s_axis_generated_tuser,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire reverse_error_valid,input wire reverse_error_ready,output wire [7:0] reverse_error_code,output wire [USER_WIDTH-1:0] reverse_error_user,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_araddr,output wire [7:0] m_axi_arlen,output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,output wire m_axi_arvalid,input wire m_axi_arready,
    input wire [63:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rlast,input wire m_axi_rvalid,output wire m_axi_rready,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,output wire m_axi_awvalid,input wire m_axi_awready,
    output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
    input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
    output wire idle
);
    wire admit,forward_idle,reverse_idle,pack_idle,fabric_idle,loader_idle;
    reg fabric_quiet;
    wire engines_idle=forward_idle&&reverse_idle&&pack_idle;
    wire loader_block=cfg_valid||cfg_invalidate_valid||!loader_idle;
    wire [9:0] command_valid,command_ready,command_write,response_valid,response_ready;
    wire [10*MEMORY_ADDR_WIDTH-1:0] command_address;wire [39:0] command_bytes;
    wire [719:0] command_data,response_data;wire [79:0] response_status;
    wire invalidate_ready;
    wire do_invalidate=cfg_invalidate_valid&&cfg_unlock&&engines_idle&&loader_idle;
    assign cfg_invalidate_ready=cfg_unlock&&engines_idle&&loader_idle&&invalidate_ready;
    // Separate client address/range calculation from the global configuration
    // permission path. Immediate engine/loader gates prevent stale admission;
    // once they are idle they cannot submit a new memory command. Waiting for
    // the registered fabric proof adds one conservative drain cycle.
    always @(posedge clk)if(rst)fabric_quiet<=0;else fabric_quiet<=fabric_idle;
    assign idle=engines_idle&&fabric_quiet&&loader_idle&&!cfg_valid&&!cfg_invalidate_valid;
`ifndef SYNTHESIS
    always @(posedge clk)if(!rst&&idle&&!fabric_idle)$error("Idle preceded actual fabric quiescence");
`endif
    vocabulary_epoch_control epoch_control(
        .clk(clk),.rst(rst),.update_req(update_req),.commit(commit),.abort_update(abort_update),.tables_valid(tables_valid),.datapath_idle(idle),
        .admit_sequences(admit),.cfg_unlock(cfg_unlock),.epoch(epoch),.vocabulary_valid(vocabulary_valid),.protocol_error(protocol_error),.draining(draining));
    wire [31:0] token_data;wire [3:0] token_keep;wire token_valid,token_ready,token_last;wire [USER_WIDTH-1:0] token_user;
    wire core_completion_valid;
    // Completion becomes visible only after the final 512-bit DMA word has
    // left the packager; its ACK also gates the next forward sequence.
    assign completion_valid=core_completion_valid&&pack_idle;
    bpe_tokenizer_engine #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) forward_engine(
        .clk(clk),.rst(rst),.admit_sequences(admit&&!loader_block),.cfg_profile(cfg_profile),.cfg_class_base(cfg_class_base),.cfg_hash_base(cfg_hash_base),.cfg_node_base(cfg_node_base),.cfg_edge_base(cfg_edge_base),
        .cfg_node_count(cfg_node_count),.cfg_edge_count(cfg_edge_count),.cfg_work_floor(cfg_work_floor),.cfg_scalar_base(cfg_scalar_base),.cfg_scalar_bytes(cfg_scalar_bytes),
        .cfg_merge_base(cfg_merge_base),.cfg_merge_bytes(cfg_merge_bytes),.cfg_commit_base(cfg_commit_base),.cfg_commit_bytes(cfg_commit_bytes),
        .s_axis_text_tdata(s_axis_text_tdata),.s_axis_text_tkeep(s_axis_text_tkeep),.s_axis_text_tvalid(s_axis_text_tvalid),.s_axis_text_tready(s_axis_text_tready),.s_axis_text_tlast(s_axis_text_tlast),.s_axis_text_tuser(s_axis_text_tuser),
        .m_axis_tokens_tdata(token_data),.m_axis_tokens_tkeep(token_keep),.m_axis_tokens_tvalid(token_valid),.m_axis_tokens_tready(token_ready),.m_axis_tokens_tlast(token_last),.m_axis_tokens_tuser(token_user),
        .completion_valid(core_completion_valid),.completion_ready(completion_ready&&pack_idle),.completion_failed(completion_failed),.completion_count(completion_count),.completion_user(completion_user),
        .error_valid(forward_error_valid),.error_ready(forward_error_ready),.error_stage(forward_error_stage),.error_detail(forward_error_detail),.error_status(forward_error_status),.error_user(forward_error_user),
        .mem_valid(command_valid[7:0]),.mem_ready(command_ready[7:0]),.mem_write(command_write[7:0]),.mem_addr(command_address[0+:8*MEMORY_ADDR_WIDTH]),.mem_bytes(command_bytes[31:0]),.mem_data(command_data[575:0]),
        .mem_rsp_valid(response_valid[7:0]),.mem_rsp_ready(response_ready[7:0]),.mem_rsp_data(response_data[575:0]),.mem_rsp_status(response_status[63:0]),.idle(forward_idle));
    token_packager #(.USER_WIDTH(USER_WIDTH)) packager(
        .clk(clk),.rst(rst),.s_token(token_data),.s_keep(token_keep==4'hf),.s_valid(token_valid),.s_ready(token_ready),.s_sequence_last(token_last),.s_user(token_user),
        .m_axis_tokens_tdata(m_axis_tokens_tdata),.m_axis_tokens_tkeep(m_axis_tokens_tkeep),.m_axis_tokens_tvalid(m_axis_tokens_tvalid),.m_axis_tokens_tready(m_axis_tokens_tready),.m_axis_tokens_tlast(m_axis_tokens_tlast),.m_axis_tokens_tuser(m_axis_tokens_tuser),.idle(pack_idle));
    // detokenizer_engine's configuration gate also stops continuation tokens.
    // Apply it only while idle, so an epoch update drains an admitted reverse
    // sequence through its final output instead of deadlocking between IDs.
    detokenizer_engine #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.EXTERNAL_MEMORY(1)) reverse_engine(
        .clk(clk),.rst(rst),.cfg_unlock((!admit||loader_block)&&reverse_idle),.cfg_valid(1'b0),.cfg_ready(),.cfg_pool(1'b0),.cfg_addr(32'd0),.cfg_data(64'd0),.cfg_error(),
        .strip_special_tokens(strip_special_tokens),.directory_base(directory_base),.pool_base(pool_base),
        .s_axis_tokens_tdata(s_axis_generated_tdata),.s_axis_tokens_tvalid(s_axis_generated_tvalid),.s_axis_tokens_tready(s_axis_generated_tready),.s_axis_tokens_tlast(s_axis_generated_tlast),.s_axis_tokens_tuser(s_axis_generated_tuser),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),.m_axis_text_tready(m_axis_text_tready),.m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),
        .error_valid(reverse_error_valid),.error_ready(reverse_error_ready),.error_code(reverse_error_code),.error_user(reverse_error_user),.idle(reverse_idle),
        .mem_rd_valid(command_valid[8]),.mem_rd_ready(command_ready[8]),.mem_rd_addr(command_address[8*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_rd_bytes(command_bytes[32+:4]),
        .mem_rsp_valid(response_valid[8]),.mem_rsp_ready(response_ready[8]),.mem_rsp_data(response_data[576+:72]),.mem_rsp_status(response_status[64+:8]));
    assign command_write[8]=0;assign command_data[576+:72]=0;
    wire loader_ready;
    assign cfg_ready=cfg_unlock&&engines_idle&&!cfg_invalidate_valid&&loader_ready;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) loader(
        .clk(clk),.rst(rst),.req_valid(cfg_valid&&cfg_unlock&&engines_idle&&!cfg_invalidate_valid),.req_ready(loader_ready),.req_write(1'b1),.req_addr(cfg_addr),.req_bytes(cfg_bytes),.req_data(cfg_data),
        .result_valid(cfg_rsp_valid),.result_ready(cfg_rsp_ready),.result_data(),.result_status(cfg_rsp_status),
        .mem_valid(command_valid[9]),.mem_ready(command_ready[9]),.mem_write(command_write[9]),.mem_addr(command_address[9*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(command_bytes[36+:4]),.mem_data(command_data[648+:72]),
        .mem_rsp_valid(response_valid[9]),.mem_rsp_ready(response_ready[9]),.mem_rsp_data(response_data[648+:72]),.mem_rsp_status(response_status[72+:8]),.idle(loader_idle));
    external_memory_fabric #(.CLIENTS(10),.ADDR_WIDTH(MEMORY_ADDR_WIDTH),.CACHE_LOG_LINES(CACHE_LOG_LINES)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(do_invalidate),.invalidate_ready(invalidate_ready),
        .s_valid(command_valid),.s_ready(command_ready),.s_write(command_write),.s_addr(command_address),.s_bytes(command_bytes),.s_data(command_data),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),
        .m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),
        .m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.idle(fabric_idle));
endmodule
`default_nettype wire
