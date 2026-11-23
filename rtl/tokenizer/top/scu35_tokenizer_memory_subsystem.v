`timescale 1ns/1ps
`default_nettype none
// Bidirectional vocabulary clients sharing one small BRAM cache. The forward
// pretokenizer/trie/merge controller connects to the rank/class query ports.
// cfg_unlock is a WHOLE-DATAPATH epoch grant, including that external controller.
module scu35_tokenizer_memory_subsystem #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,
    parameter integer CACHE_LOG_LINES=6
)(
    input wire clk,input wire rst,
    input wire cfg_unlock,input wire cfg_valid,output wire cfg_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_addr,input wire [3:0] cfg_bytes,input wire [71:0] cfg_data,
    output wire cfg_rsp_valid,input wire cfg_rsp_ready,output wire [7:0] cfg_rsp_status,
    input wire cfg_invalidate_valid,output wire cfg_invalidate_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] directory_base,input wire [MEMORY_ADDR_WIDTH-1:0] pool_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] hash_base,input wire [MEMORY_ADDR_WIDTH-1:0] class_base,
    input wire strip_special_tokens,
    input wire [31:0] s_axis_tokens_tdata,input wire s_axis_tokens_tvalid,output wire s_axis_tokens_tready,
    input wire s_axis_tokens_tlast,input wire [USER_WIDTH-1:0] s_axis_tokens_tuser,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire error_valid,input wire error_ready,output wire [7:0] error_code,output wire [USER_WIDTH-1:0] error_user,
    input wire rank_req_valid,output wire rank_req_ready,input wire [16:0] rank_req_left,input wire [16:0] rank_req_right,
    output wire rank_rsp_valid,input wire rank_rsp_ready,output wire rank_rsp_found,
    output wire [16:0] rank_rsp_merged,output wire [16:0] rank_rsp_rank,output wire [7:0] rank_rsp_status,
    input wire class_req_valid,output wire class_req_ready,input wire [20:0] class_req_codepoint,
    output wire class_rsp_valid,input wire class_rsp_ready,output wire [1:0] class_rsp_class,output wire [7:0] class_rsp_status,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_araddr,output wire [7:0] m_axi_arlen,
    output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,output wire m_axi_arvalid,input wire m_axi_arready,
    input wire [63:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rlast,input wire m_axi_rvalid,output wire m_axi_rready,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,
    output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,output wire m_axi_awvalid,input wire m_axi_awready,
    output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
    input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
    output wire idle
);
    wire detok_idle,rank_idle,class_idle,fabric_idle;
    wire engines_idle=detok_idle&&rank_idle&&class_idle;
    reg cfg_pending;
    wire cfg_block=cfg_unlock||cfg_valid||cfg_invalidate_valid||cfg_pending;
    wire [3:0] cmd_valid,cmd_ready,response_valid,response_ready;
    wire [MEMORY_ADDR_WIDTH*4-1:0] command_address;
    wire [15:0] command_bytes;
    wire [287:0] response_data;
    wire [31:0] response_status;
    wire invalidate_ready;
    assign cmd_valid[3]=cfg_valid&&cfg_unlock&&engines_idle&&!cfg_pending;
    assign cfg_ready=cfg_unlock&&engines_idle&&!cfg_pending&&cmd_ready[3];
    assign cfg_rsp_valid=response_valid[3];assign cfg_rsp_status=response_status[31:24];
    assign response_ready[3]=cfg_rsp_ready;
    assign command_address[3*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=cfg_addr;
    assign command_bytes[15:12]=cfg_bytes;
    assign cfg_invalidate_ready=cfg_unlock&&engines_idle&&!cfg_pending&&invalidate_ready;
    assign idle=engines_idle&&fabric_idle&&!cfg_valid&&!cfg_invalidate_valid&&!cfg_pending;
    always @(posedge clk)begin
        if(rst)cfg_pending<=0;
        else begin
            if(cfg_valid&&cfg_ready)cfg_pending<=1;
            if(cfg_rsp_valid&&cfg_rsp_ready)cfg_pending<=0;
        end
    end
    detokenizer_engine #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.EXTERNAL_MEMORY(1)) inverse(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_block),.cfg_valid(1'b0),.cfg_ready(),.cfg_pool(1'b0),.cfg_addr(32'd0),.cfg_data(64'd0),.cfg_error(),
        .strip_special_tokens(strip_special_tokens),.s_axis_tokens_tdata(s_axis_tokens_tdata),.s_axis_tokens_tvalid(s_axis_tokens_tvalid),
        .s_axis_tokens_tready(s_axis_tokens_tready),.s_axis_tokens_tlast(s_axis_tokens_tlast),.s_axis_tokens_tuser(s_axis_tokens_tuser),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),.m_axis_text_tready(m_axis_text_tready),
        .m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),.error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_user(error_user),.idle(detok_idle),
        .directory_base(directory_base),.pool_base(pool_base),.mem_rd_valid(cmd_valid[0]),.mem_rd_ready(cmd_ready[0]),
        .mem_rd_addr(command_address[0+:MEMORY_ADDR_WIDTH]),.mem_rd_bytes(command_bytes[0+:4]),
        .mem_rsp_valid(response_valid[0]),.mem_rsp_ready(response_ready[0]),.mem_rsp_data(response_data[0+:72]),.mem_rsp_status(response_status[0+:8]));
    bpe_rank_lookup #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.EXTERNAL_MEMORY(1)) ranks(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_block),.cfg_valid(1'b0),.cfg_ready(),.cfg_addr(18'd0),.cfg_data(72'd0),
        .req_valid(rank_req_valid),.req_ready(rank_req_ready),.req_left(rank_req_left),.req_right(rank_req_right),
        .rsp_valid(rank_rsp_valid),.rsp_ready(rank_rsp_ready),.rsp_found(rank_rsp_found),.rsp_merged(rank_rsp_merged),.rsp_rank(rank_rsp_rank),.rsp_status(rank_rsp_status),.idle(rank_idle),
        .hash_base(hash_base),.mem_rd_valid(cmd_valid[1]),.mem_rd_ready(cmd_ready[1]),.mem_rd_addr(command_address[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_rd_bytes(command_bytes[4+:4]),
        .mem_rsp_valid(response_valid[1]),.mem_rsp_ready(response_ready[1]),.mem_rsp_data(response_data[72+:72]),.mem_rsp_status(response_status[8+:8]));
    unicode_external_lookup #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) classes(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_block),.class_base(class_base),.req_valid(class_req_valid),.req_ready(class_req_ready),.req_codepoint(class_req_codepoint),
        .rsp_valid(class_rsp_valid),.rsp_ready(class_rsp_ready),.rsp_class(class_rsp_class),.rsp_status(class_rsp_status),.idle(class_idle),
        .mem_rd_valid(cmd_valid[2]),.mem_rd_ready(cmd_ready[2]),.mem_rd_addr(command_address[2*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_rd_bytes(command_bytes[8+:4]),
        .mem_rsp_valid(response_valid[2]),.mem_rsp_ready(response_ready[2]),.mem_rsp_data(response_data[144+:72]),.mem_rsp_status(response_status[16+:8]));
    external_memory_fabric #(.ADDR_WIDTH(MEMORY_ADDR_WIDTH),.CACHE_LOG_LINES(CACHE_LOG_LINES)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(cfg_invalidate_valid&&cfg_unlock&&engines_idle&&!cfg_pending),.invalidate_ready(invalidate_ready),
        .s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(4'b1000),.s_addr(command_address),.s_bytes(command_bytes),.s_data({cfg_data,216'd0}),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),
        .m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),
        .m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.idle(fabric_idle));
endmodule
`default_nettype wire
