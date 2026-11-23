`timescale 1ns/1ps
`default_nettype none
// Host register adapter joined to the actual transactional application decoder.
// The system owner fences ingress and drains queued/remote schema users before
// schema_maintenance_grant. Keep that grant through the final apply response.
module parser_schema_mmio_decoder #(
    parameter integer USER_WIDTH=16,FIFO_DEPTH=512,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384,
    parameter integer MAX_JSON_DEPTH=32,MAX_PROTO_GROUP_DEPTH=16,SCHEMA_ENTRIES=16,
    parameter integer SCHEMA_INDEX_WIDTH=(SCHEMA_ENTRIES>1?$clog2(SCHEMA_ENTRIES):1)
)(
    input wire clk,input wire rst,input wire cfg_protobuf,input wire schema_maintenance_grant,
    input wire [15:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,output wire s_axi_bvalid,input wire s_axi_bready,
    input wire [15:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire [1:0] s_axi_rresp,output wire s_axi_rvalid,input wire s_axi_rready,
    input wire [511:0] s_axis_rx_tdata,input wire [63:0] s_axis_rx_tkeep,
    input wire s_axis_rx_tvalid,output wire s_axis_rx_tready,input wire s_axis_rx_tlast,
    input wire [USER_WIDTH-1:0] s_axis_rx_tuser,input wire s_axis_rx_abort,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,
    output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire error_valid,input wire error_ready,output wire [7:0] error_code,
    output wire [USER_WIDTH-1:0] error_user,output wire idle,
    output wire [31:0] schema_epoch,output wire schema_committed,output wire schema_cfg_busy
);
    wire cfg_schema_valid,cfg_schema_ready,cfg_schema_json_enable,cfg_schema_proto_enable;
    wire [SCHEMA_INDEX_WIDTH-1:0] cfg_schema_index;
    wire [255:0] cfg_schema_key;
    wire [5:0] cfg_schema_key_length;
    wire [28:0] cfg_schema_field;
    parser_schema_mmio #(.ENTRIES(SCHEMA_ENTRIES),.INDEX_WIDTH(SCHEMA_INDEX_WIDTH)) mmio(
        .clk(clk),.rst(rst),.s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp),.s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),.s_axi_rresp(s_axi_rresp),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),
        .cfg_unlock(schema_maintenance_grant),.cfg_quiescent(idle),
        .cfg_schema_valid(cfg_schema_valid),.cfg_schema_ready(cfg_schema_ready),.cfg_schema_index(cfg_schema_index),
        .cfg_schema_key(cfg_schema_key),.cfg_schema_key_length(cfg_schema_key_length),
        .cfg_schema_json_enable(cfg_schema_json_enable),.cfg_schema_field(cfg_schema_field),.cfg_schema_proto_enable(cfg_schema_proto_enable),
        .schema_epoch(schema_epoch),.schema_committed(schema_committed),.busy(schema_cfg_busy));
    proto_json_decoder #(.USER_WIDTH(USER_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),
        .MAX_FIELD_BYTES(MAX_FIELD_BYTES),.MAX_JSON_DEPTH(MAX_JSON_DEPTH),.MAX_PROTO_GROUP_DEPTH(MAX_PROTO_GROUP_DEPTH),
        .SCHEMA_ENTRIES(SCHEMA_ENTRIES),.KEY_BYTES(32),.SCHEMA_INDEX_WIDTH(SCHEMA_INDEX_WIDTH),.KEY_LENGTH_WIDTH(6)) decoder(
        .clk(clk),.rst(rst),.cfg_protobuf(cfg_protobuf),.cfg_unlock(schema_maintenance_grant),
        .cfg_schema_valid(cfg_schema_valid),.cfg_schema_ready(cfg_schema_ready),.cfg_schema_index(cfg_schema_index),
        .cfg_schema_key(cfg_schema_key),.cfg_schema_key_length(cfg_schema_key_length),
        .cfg_schema_json_enable(cfg_schema_json_enable),.cfg_schema_field(cfg_schema_field),.cfg_schema_proto_enable(cfg_schema_proto_enable),
        .s_axis_rx_tdata(s_axis_rx_tdata),.s_axis_rx_tkeep(s_axis_rx_tkeep),.s_axis_rx_tvalid(s_axis_rx_tvalid),.s_axis_rx_tready(s_axis_rx_tready),
        .s_axis_rx_tlast(s_axis_rx_tlast),.s_axis_rx_tuser(s_axis_rx_tuser),.s_axis_rx_abort(s_axis_rx_abort),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),.m_axis_text_tready(m_axis_text_tready),
        .m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_user(error_user),.idle(idle));
endmodule
`default_nettype wire
