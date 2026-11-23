`timescale 1ns/1ps
`default_nettype none
// Full-packet CDC using the native AMD asynchronous FIFO. Both clocks must
// free-run. Hold reset_request through at least two edges of the slower clock.
// The reset outputs must reset the source/sink transaction owners as well.
module cdc_packet_fifo #(
    parameter WIDTH=607
)(
    input wire s_clk,m_clk,reset_request,
    input wire [WIDTH-1:0] s_data,
    input wire s_valid,
    output wire s_ready,
    output wire [WIDTH-1:0] m_data,
    output wire m_valid,
    input wire m_ready,
    output wire s_reset,m_reset,
    output wire overflow,underflow
);
    // Async assertion enters a vendor reset synchronizer. An extra register
    // makes the FIFO's reset assertion/release synchronous to its write clock.
    // Four release stages plus that register stretch even a short reset pulse.
    wire s_reset_async,m_reset_async;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) source_reset_sync(
        .src_arst(reset_request),.dest_clk(s_clk),.dest_arst(s_reset_async));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) destination_reset_sync(
        .src_arst(reset_request),.dest_clk(m_clk),.dest_arst(m_reset_async));
    reg s_fifo_reset=1'b1,m_fifo_reset=1'b1;
    always @(posedge s_clk)s_fifo_reset<=s_reset_async;
    always @(posedge m_clk)m_fifo_reset<=m_reset_async;
    wire wr_busy,rd_busy,full,empty;
    wire source_up=!s_fifo_reset&&!wr_busy;
    wire destination_up=!m_fifo_reset&&!rd_busy;
    wire source_up_m,destination_up_s;
    xpm_cdc_single #(.DEST_SYNC_FF(3),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) source_ready_sync(
        .src_clk(s_clk),.src_in(source_up),.dest_clk(m_clk),.dest_out(source_up_m));
    xpm_cdc_single #(.DEST_SYNC_FF(3),.INIT_SYNC_FF(1),.SIM_ASSERT_CHK(1),.SRC_INPUT_REG(0)) destination_ready_sync(
        .src_clk(m_clk),.src_in(destination_up),.dest_clk(s_clk),.dest_out(destination_up_s));
    assign s_reset=reset_request||!source_up||!destination_up_s;
    assign m_reset=reset_request||!destination_up||!source_up_m;
    assign s_ready=!s_reset&&!full;
    assign m_valid=!m_reset&&!empty;
    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("distributed"),.ECC_MODE("no_ecc"),.RELATED_CLOCKS(0),
        .FIFO_WRITE_DEPTH(16),.WRITE_DATA_WIDTH(WIDTH),.READ_DATA_WIDTH(WIDTH),
        .WR_DATA_COUNT_WIDTH(5),.RD_DATA_COUNT_WIDTH(5),.PROG_FULL_THRESH(10),.PROG_EMPTY_THRESH(10),
        .FULL_RESET_VALUE(1),.USE_ADV_FEATURES("0101"),.READ_MODE("fwft"),.FIFO_READ_LATENCY(0),
        .DOUT_RESET_VALUE("0"),.CDC_SYNC_STAGES(3),.WAKEUP_TIME(0),.SIM_ASSERT_CHK(1)
    ) storage(
        .sleep(1'b0),.rst(s_fifo_reset),.wr_clk(s_clk),.wr_en(s_valid&&s_ready),.din(s_data),
        .full(full),.prog_full(),.wr_data_count(),.overflow(overflow),.wr_rst_busy(wr_busy),.almost_full(),.wr_ack(),
        .rd_clk(m_clk),.rd_en(m_valid&&m_ready),.dout(m_data),.empty(empty),.prog_empty(),.rd_data_count(),
        .underflow(underflow),.rd_rst_busy(rd_busy),.almost_empty(),.data_valid(),
        .injectsbiterr(1'b0),.injectdbiterr(1'b0),.sbiterr(),.dbiterr());
endmodule
`default_nettype wire
