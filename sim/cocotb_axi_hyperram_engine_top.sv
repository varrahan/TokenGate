`timescale 1ns/1ps
`default_nettype none
// Passive same-clock test wiring; not a pin-level controller or initialization manager.
module cocotb_axi_hyperram_engine_top #(parameter MEMORY_CLOCK_HZ=200000000)(
    input wire  clk,
    input wire  rst,
    input wire [23-1:0] s_axi_araddr,
    input wire [7:0] s_axi_arlen,
    input wire [2:0] s_axi_arsize,
    input wire [1:0] s_axi_arburst,
    input wire  s_axi_arvalid,
    output wire  s_axi_arready,
    output wire [63:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire  s_axi_rlast,
    output wire  s_axi_rvalid,
    input wire  s_axi_rready,
    input wire [23-1:0] s_axi_awaddr,
    input wire [7:0] s_axi_awlen,
    input wire [2:0] s_axi_awsize,
    input wire [1:0] s_axi_awburst,
    input wire  s_axi_awvalid,
    output wire  s_axi_awready,
    input wire [63:0] s_axi_wdata,
    input wire [7:0] s_axi_wstrb,
    input wire  s_axi_wlast,
    input wire  s_axi_wvalid,
    output wire  s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output wire  s_axi_bvalid,
    input wire  s_axi_bready,
    input wire  enable,
    input wire [3:0] cfg_latency,
    input wire  cfg_fixed_latency,
    output wire  phy_cs_n,
    output wire  phy_clock_enable,
    output wire  phy_dq_oe,
    output wire [15:0] phy_tx_word,
    output wire  phy_rwds_oe,
    output wire [1:0] phy_tx_mask,
    input wire  phy_latency_extra,
    input wire  phy_rx_valid,
    input wire [15:0] phy_rx_word,
    input wire  phy_fault,
    output wire  phy_rx_enable,
    output wire  phy_rx_flush,
    output wire  idle,
    output wire [7:0] memory_detail
);
wire frontend_idle,engine_idle;
assign idle=frontend_idle&&engine_idle;
wire  hb_cmd_valid;
wire  hb_cmd_ready;
wire  hb_cmd_write;
wire [23-1:0] hb_cmd_address;
wire [6:0] hb_cmd_bytes;
wire [511:0] hb_cmd_data;
wire [63:0] hb_cmd_strobes;
wire  hb_rsp_valid;
wire  hb_rsp_ready;
wire [511:0] hb_rsp_data;
wire  hb_rsp_error;
axi_hyperram_bridge #(.ADDR_WIDTH(23)) frontend(
    .clk(clk),
    .rst(rst),
    .s_axi_araddr(s_axi_araddr),
    .s_axi_arlen(s_axi_arlen),
    .s_axi_arsize(s_axi_arsize),
    .s_axi_arburst(s_axi_arburst),
    .s_axi_arvalid(s_axi_arvalid),
    .s_axi_arready(s_axi_arready),
    .s_axi_rdata(s_axi_rdata),
    .s_axi_rresp(s_axi_rresp),
    .s_axi_rlast(s_axi_rlast),
    .s_axi_rvalid(s_axi_rvalid),
    .s_axi_rready(s_axi_rready),
    .s_axi_awaddr(s_axi_awaddr),
    .s_axi_awlen(s_axi_awlen),
    .s_axi_awsize(s_axi_awsize),
    .s_axi_awburst(s_axi_awburst),
    .s_axi_awvalid(s_axi_awvalid),
    .s_axi_awready(s_axi_awready),
    .s_axi_wdata(s_axi_wdata),
    .s_axi_wstrb(s_axi_wstrb),
    .s_axi_wlast(s_axi_wlast),
    .s_axi_wvalid(s_axi_wvalid),
    .s_axi_wready(s_axi_wready),
    .s_axi_bresp(s_axi_bresp),
    .s_axi_bvalid(s_axi_bvalid),
    .s_axi_bready(s_axi_bready),
    .hb_cmd_valid(hb_cmd_valid),
    .hb_cmd_ready(hb_cmd_ready),
    .hb_cmd_write(hb_cmd_write),
    .hb_cmd_address(hb_cmd_address),
    .hb_cmd_bytes(hb_cmd_bytes),
    .hb_cmd_data(hb_cmd_data),
    .hb_cmd_strobes(hb_cmd_strobes),
    .hb_rsp_valid(hb_rsp_valid),
    .hb_rsp_ready(hb_rsp_ready),
    .hb_rsp_data(hb_rsp_data),
    .hb_rsp_error(hb_rsp_error),
    .idle(frontend_idle)
);
hyperram_transaction_engine #(.MEMORY_CLOCK_HZ(MEMORY_CLOCK_HZ)) engine(
    .clk(clk),
    .rst(rst),
    .enable(enable),
    .cmd_valid(hb_cmd_valid),
    .cmd_ready(hb_cmd_ready),
    .cmd_write(hb_cmd_write),
    .cmd_register(1'b0),
    .cmd_address(hb_cmd_address),
    .cmd_bytes(hb_cmd_bytes),
    .cmd_data(hb_cmd_data),
    .cmd_strobes(hb_cmd_strobes),
    .cfg_latency(cfg_latency),
    .cfg_fixed_latency(cfg_fixed_latency),
    .rsp_valid(hb_rsp_valid),
    .rsp_ready(hb_rsp_ready),
    .rsp_data(hb_rsp_data),
    .rsp_error(hb_rsp_error),
    .rsp_detail(memory_detail),
    .phy_cs_n(phy_cs_n),
    .phy_clock_enable(phy_clock_enable),
    .phy_dq_oe(phy_dq_oe),
    .phy_tx_word(phy_tx_word),
    .phy_rwds_oe(phy_rwds_oe),
    .phy_tx_mask(phy_tx_mask),
    .phy_latency_extra(phy_latency_extra),
    .phy_rx_valid(phy_rx_valid),
    .phy_rx_word(phy_rx_word),
    .phy_fault(phy_fault),
    .phy_rx_enable(phy_rx_enable),
    .phy_rx_flush(phy_rx_flush),
    .idle(engine_idle)
);
endmodule
`default_nettype wire
