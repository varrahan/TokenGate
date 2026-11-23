`timescale 1ns/1ps
`default_nettype none
module bow_axi_bridge #(
    parameter integer DATA_WIDTH=128,
    parameter integer KEEP_WIDTH=DATA_WIDTH/8,
    parameter integer USER_WIDTH=16
)(
    input wire clk, input wire rst,
    input wire [DATA_WIDTH-1:0] s_ingress_tdata,
    input wire [KEEP_WIDTH-1:0] s_ingress_tkeep,
    input wire s_ingress_tvalid, output wire s_ingress_tready,
    input wire s_ingress_tlast, input wire [USER_WIDTH-1:0] s_ingress_tuser,
    output wire [DATA_WIDTH-1:0] m_ingress_tdata,
    output wire [KEEP_WIDTH-1:0] m_ingress_tkeep,
    output wire m_ingress_tvalid, input wire m_ingress_tready,
    output wire m_ingress_tlast, output wire [USER_WIDTH-1:0] m_ingress_tuser,
    input wire [DATA_WIDTH-1:0] s_egress_tdata,
    input wire [KEEP_WIDTH-1:0] s_egress_tkeep,
    input wire s_egress_tvalid, output wire s_egress_tready,
    input wire s_egress_tlast, input wire [USER_WIDTH-1:0] s_egress_tuser,
    output wire [DATA_WIDTH-1:0] m_egress_tdata,
    output wire [KEEP_WIDTH-1:0] m_egress_tkeep,
    output wire m_egress_tvalid, input wire m_egress_tready,
    output wire m_egress_tlast, output wire [USER_WIDTH-1:0] m_egress_tuser
);
    axis_skid_buffer #(.DATA_WIDTH(DATA_WIDTH),.KEEP_WIDTH(KEEP_WIDTH),.USER_WIDTH(USER_WIDTH)) ingress (
        .clk(clk),.rst(rst),.s_axis_tdata(s_ingress_tdata),.s_axis_tkeep(s_ingress_tkeep),
        .s_axis_tvalid(s_ingress_tvalid),.s_axis_tready(s_ingress_tready),
        .s_axis_tlast(s_ingress_tlast),.s_axis_tuser(s_ingress_tuser),
        .m_axis_tdata(m_ingress_tdata),.m_axis_tkeep(m_ingress_tkeep),
        .m_axis_tvalid(m_ingress_tvalid),.m_axis_tready(m_ingress_tready),
        .m_axis_tlast(m_ingress_tlast),.m_axis_tuser(m_ingress_tuser));
    axis_skid_buffer #(.DATA_WIDTH(DATA_WIDTH),.KEEP_WIDTH(KEEP_WIDTH),.USER_WIDTH(USER_WIDTH)) egress (
        .clk(clk),.rst(rst),.s_axis_tdata(s_egress_tdata),.s_axis_tkeep(s_egress_tkeep),
        .s_axis_tvalid(s_egress_tvalid),.s_axis_tready(s_egress_tready),
        .s_axis_tlast(s_egress_tlast),.s_axis_tuser(s_egress_tuser),
        .m_axis_tdata(m_egress_tdata),.m_axis_tkeep(m_egress_tkeep),
        .m_axis_tvalid(m_egress_tvalid),.m_axis_tready(m_egress_tready),
        .m_axis_tlast(m_egress_tlast),.m_axis_tuser(m_egress_tuser));
endmodule
`default_nettype wire
