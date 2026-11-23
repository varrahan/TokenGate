`timescale 1ns/1ps
`default_nettype none
module external_memory_fabric #(
    parameter integer CLIENTS=4,parameter integer ADDR_WIDTH=23,
    parameter integer CACHE_LOG_LINES=6
)(
    input wire clk,input wire rst,
    input wire invalidate_valid,output wire invalidate_ready,
    input wire [CLIENTS-1:0] s_valid,output wire [CLIENTS-1:0] s_ready,input wire [CLIENTS-1:0] s_write,
    input wire [CLIENTS*ADDR_WIDTH-1:0] s_addr,input wire [CLIENTS*4-1:0] s_bytes,input wire [CLIENTS*72-1:0] s_data,
    output wire [CLIENTS-1:0] rsp_valid,input wire [CLIENTS-1:0] rsp_ready,
    output wire [CLIENTS*72-1:0] rsp_data,output wire [CLIENTS*8-1:0] rsp_status,
    output wire [ADDR_WIDTH-1:0] m_axi_araddr,output wire [7:0] m_axi_arlen,
    output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,output wire m_axi_arvalid,input wire m_axi_arready,
    input wire [63:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rlast,input wire m_axi_rvalid,output wire m_axi_rready,
    output wire [ADDR_WIDTH-1:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,
    output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,output wire m_axi_awvalid,input wire m_axi_awready,
    output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
    input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
    output wire idle
);
    wire rv,rr,rrv,rrr,wv,wr,wrv,wrr,arb_idle,arb_drained,cache_idle,cache_inv_ready;
    wire [ADDR_WIDTH-1:0] ra,wa;
    wire [3:0] rn,wn;
    wire [71:0] rd,wd;
    wire [7:0] rs,ws;
    assign invalidate_ready=arb_drained&&cache_inv_ready;
    assign idle=arb_idle&&cache_idle&&!invalidate_valid;
    external_memory_arbiter #(.CLIENTS(CLIENTS),.ADDR_WIDTH(ADDR_WIDTH)) arbiter(
        .clk(clk),.rst(rst),.pause(invalidate_valid),.s_valid(s_valid),.s_ready(s_ready),.s_write(s_write),
        .s_addr(s_addr),.s_bytes(s_bytes),.s_data(s_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_data(rsp_data),.rsp_status(rsp_status),
        .rd_valid(rv),.rd_ready(rr),.rd_addr(ra),.rd_bytes(rn),.rd_rsp_valid(rrv),.rd_rsp_ready(rrr),.rd_rsp_data(rd),.rd_rsp_status(rs),
        .wr_valid(wv),.wr_ready(wr),.wr_addr(wa),.wr_bytes(wn),.wr_data(wd),.wr_rsp_valid(wrv),.wr_rsp_ready(wrr),.wr_rsp_status(ws),
        .idle(arb_idle),.drained(arb_drained));
    external_memory_cache #(.ADDR_WIDTH(ADDR_WIDTH),.CACHE_LOG_LINES(CACHE_LOG_LINES)) cache(
        .clk(clk),.rst(rst),.invalidate_valid(invalidate_valid&&arb_drained),.invalidate_ready(cache_inv_ready),
        .rd_valid(rv),.rd_ready(rr),.rd_addr(ra),.rd_bytes(rn),.rd_rsp_valid(rrv),.rd_rsp_ready(rrr),.rd_rsp_data(rd),.rd_rsp_status(rs),
        .wr_valid(wv),.wr_ready(wr),.wr_addr(wa),.wr_bytes(wn),.wr_data(wd),.wr_rsp_valid(wrv),.wr_rsp_ready(wrr),.wr_rsp_status(ws),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),
        .m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),
        .m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.idle(cache_idle));
endmodule
`default_nettype wire
