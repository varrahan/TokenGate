`timescale 1ns/1ps
`default_nettype none
// SCU35 inverse-vocabulary path plus its BRAM cache and external AXI master.
// cfg_unlock must come from the drained epoch controller. Configuration is
// byte addressed; acceptance is distinct from the BRESP-backed completion.
module scu35_detokenizer_subsystem #(
    parameter integer USER_WIDTH=16,
    parameter integer MEMORY_ADDR_WIDTH=23,
    parameter integer CACHE_LOG_LINES=6
)(
    input wire clk,input wire rst,
    input wire cfg_unlock,input wire cfg_valid,output wire cfg_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_addr,input wire [3:0] cfg_bytes,input wire [71:0] cfg_data,
    output wire cfg_rsp_valid,input wire cfg_rsp_ready,output wire [7:0] cfg_rsp_status,
    input wire cfg_invalidate_valid,output wire cfg_invalidate_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] directory_base,input wire [MEMORY_ADDR_WIDTH-1:0] pool_base,
    input wire strip_special_tokens,
    input wire [31:0] s_axis_tokens_tdata,input wire s_axis_tokens_tvalid,output wire s_axis_tokens_tready,
    input wire s_axis_tokens_tlast,input wire [USER_WIDTH-1:0] s_axis_tokens_tuser,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,
    output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire error_valid,input wire error_ready,output wire [7:0] error_code,output wire [USER_WIDTH-1:0] error_user,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_araddr,output wire [7:0] m_axi_arlen,
    output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,output wire m_axi_arvalid,input wire m_axi_arready,
    input wire [63:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rlast,input wire m_axi_rvalid,output wire m_axi_rready,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,
    output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,output wire m_axi_awvalid,input wire m_axi_awready,
    output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
    input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
    output wire idle
);
    wire rd_valid,rd_ready,rsp_valid,rsp_ready,engine_idle,cache_idle,write_ready,invalidate_ready;
    reg cfg_pending;
    wire [MEMORY_ADDR_WIDTH-1:0] rd_addr;
    wire [3:0] rd_bytes;
    wire [71:0] rsp_data;
    wire [7:0] rsp_status;
    // Holding cfg_valid blocks the idle/commit indication even on its first
    // acceptance cycle. cache_idle remains false through the write response.
    assign idle=engine_idle && cache_idle && !cfg_valid && !cfg_invalidate_valid && !cfg_pending;
    assign cfg_ready=cfg_unlock && engine_idle && write_ready && !cfg_pending;
    assign cfg_invalidate_ready=cfg_unlock && engine_idle && invalidate_ready && !cfg_pending;
    always @(posedge clk)begin
        if(rst)cfg_pending<=0;
        else begin
            if(cfg_valid&&cfg_ready)cfg_pending<=1;
            if(cfg_rsp_valid&&cfg_rsp_ready)cfg_pending<=0;
        end
    end
    detokenizer_engine #(.USER_WIDTH(USER_WIDTH),.EXTERNAL_MEMORY(1),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) engine(
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock||cfg_valid||cfg_invalidate_valid||cfg_pending),
        .cfg_valid(1'b0),.cfg_ready(),.cfg_pool(1'b0),.cfg_addr(32'd0),.cfg_data(64'd0),.cfg_error(),
        .strip_special_tokens(strip_special_tokens),
        .s_axis_tokens_tdata(s_axis_tokens_tdata),.s_axis_tokens_tvalid(s_axis_tokens_tvalid),.s_axis_tokens_tready(s_axis_tokens_tready),
        .s_axis_tokens_tlast(s_axis_tokens_tlast),.s_axis_tokens_tuser(s_axis_tokens_tuser),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),
        .m_axis_text_tready(m_axis_text_tready),.m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_user(error_user),.idle(engine_idle),
        .directory_base(directory_base),.pool_base(pool_base),.mem_rd_valid(rd_valid),.mem_rd_ready(rd_ready),
        .mem_rd_addr(rd_addr),.mem_rd_bytes(rd_bytes),.mem_rsp_valid(rsp_valid),.mem_rsp_ready(rsp_ready),.mem_rsp_data(rsp_data),.mem_rsp_status(rsp_status));
    external_memory_cache #(.ADDR_WIDTH(MEMORY_ADDR_WIDTH),.CACHE_LOG_LINES(CACHE_LOG_LINES)) cache(
        .clk(clk),.rst(rst),.invalidate_valid(cfg_invalidate_valid&&cfg_unlock&&engine_idle&&!cfg_pending),.invalidate_ready(invalidate_ready),
        .rd_valid(rd_valid),.rd_ready(rd_ready),.rd_addr(rd_addr),.rd_bytes(rd_bytes),
        .rd_rsp_valid(rsp_valid),.rd_rsp_ready(rsp_ready),.rd_rsp_data(rsp_data),.rd_rsp_status(rsp_status),
        .wr_valid(cfg_valid&&cfg_unlock&&engine_idle&&!cfg_pending),.wr_ready(write_ready),.wr_addr(cfg_addr),.wr_bytes(cfg_bytes),.wr_data(cfg_data),
        .wr_rsp_valid(cfg_rsp_valid),.wr_rsp_ready(cfg_rsp_ready),.wr_rsp_status(cfg_rsp_status),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),
        .m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),
        .m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.idle(cache_idle));
endmodule
`default_nettype wire
