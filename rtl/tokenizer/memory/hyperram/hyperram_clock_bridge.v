`timescale 1ns/1ps
`default_nettype none
// Buffered memory commands cross app_clk -> mem_clk, complete results return.
// This preserves packet ordering; it is not the pin-level RWDS capture CDC.
// A shared reset aborts all outstanding transactions. Wire app_reset/mem_reset
// to both owners; an independent owner reset is unsupported.
module hyperram_clock_bridge(
    input wire app_clk,mem_clk,reset_request,
    output wire app_reset,mem_reset,
    input wire s_cmd_valid,
    output wire s_cmd_ready,
    input wire s_cmd_write,
    input wire [22:0] s_cmd_address,
    input wire [6:0] s_cmd_bytes,
    input wire [511:0] s_cmd_data,
    input wire [63:0] s_cmd_strobes,
    output wire m_cmd_valid,
    input wire m_cmd_ready,
    output wire m_cmd_write,
    output wire [22:0] m_cmd_address,
    output wire [6:0] m_cmd_bytes,
    output wire [511:0] m_cmd_data,
    output wire [63:0] m_cmd_strobes,
    input wire m_rsp_valid,
    output wire m_rsp_ready,
    input wire m_rsp_error,
    input wire [7:0] m_rsp_detail,
    input wire [511:0] m_rsp_data,
    output wire s_rsp_valid,
    input wire s_rsp_ready,
    output wire s_rsp_error,
    output wire [7:0] s_rsp_detail,
    output wire [511:0] s_rsp_data,
    output wire [3:0] fifo_errors
);
    wire cmd_app_reset,cmd_mem_reset,rsp_mem_reset,rsp_app_reset;
    wire cmd_s_ready,cmd_m_valid,rsp_s_ready,rsp_m_valid;
    assign app_reset=cmd_app_reset||rsp_app_reset;
    assign mem_reset=cmd_mem_reset||rsp_mem_reset;
    assign s_cmd_ready=cmd_s_ready&&!app_reset;
    assign m_cmd_valid=cmd_m_valid&&!mem_reset;
    assign m_rsp_ready=rsp_s_ready&&!mem_reset;
    assign s_rsp_valid=rsp_m_valid&&!app_reset;
    cdc_packet_fifo #(.WIDTH(607)) commands(
        .s_clk(app_clk),.m_clk(mem_clk),.reset_request(reset_request),
        .s_data({s_cmd_write,s_cmd_address,s_cmd_bytes,s_cmd_data,s_cmd_strobes}),
        .s_valid(s_cmd_valid&&!app_reset),.s_ready(cmd_s_ready),
        .m_data({m_cmd_write,m_cmd_address,m_cmd_bytes,m_cmd_data,m_cmd_strobes}),
        .m_valid(cmd_m_valid),.m_ready(m_cmd_ready&&!mem_reset),
        .s_reset(cmd_app_reset),.m_reset(cmd_mem_reset),.overflow(fifo_errors[0]),.underflow(fifo_errors[1]));
    cdc_packet_fifo #(.WIDTH(521)) responses(
        .s_clk(mem_clk),.m_clk(app_clk),.reset_request(reset_request),
        .s_data({m_rsp_error,m_rsp_detail,m_rsp_data}),.s_valid(m_rsp_valid&&!mem_reset),.s_ready(rsp_s_ready),
        .m_data({s_rsp_error,s_rsp_detail,s_rsp_data}),.m_valid(rsp_m_valid),.m_ready(s_rsp_ready&&!app_reset),
        .s_reset(rsp_mem_reset),.m_reset(rsp_app_reset),.overflow(fifo_errors[2]),.underflow(fifo_errors[3]));
endmodule
`default_nettype wire
