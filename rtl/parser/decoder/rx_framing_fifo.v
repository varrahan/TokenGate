`timescale 1ns/1ps
`default_nettype none
module rx_framing_fifo #(
    parameter integer DATA_WIDTH=512,
    parameter integer USER_WIDTH=16,
    parameter integer DEPTH=512
)(
    input wire clk,input wire rst,
    input wire [DATA_WIDTH-1:0] s_axis_tdata,
    input wire [DATA_WIDTH/8-1:0] s_axis_tkeep,
    input wire s_axis_tvalid,output wire s_axis_tready,
    input wire s_axis_tlast,input wire [USER_WIDTH-1:0] s_axis_tuser,
    output wire [DATA_WIDTH-1:0] m_axis_tdata,
    output wire [DATA_WIDTH/8-1:0] m_axis_tkeep,
    output wire m_axis_tvalid,input wire m_axis_tready,
    output wire m_axis_tlast,output wire [USER_WIDTH-1:0] m_axis_tuser
);
    localparam integer WIDTH=DATA_WIDTH+DATA_WIDTH/8+USER_WIDTH+1;
    localparam integer COUNT_WIDTH=$clog2(DEPTH)+1;
    wire full,empty,wr_busy,rd_busy;
    assign s_axis_tready=!rst && !full && !wr_busy;
    assign m_axis_tvalid=!rst && !empty && !rd_busy;
`ifdef PARSER_PORTABLE_SIM
    // No-ECC functional simulation backend. Native builds retain XPM below.
`ifdef SYNTHESIS
    initial $error("PARSER_PORTABLE_SIM is not a synthesis configuration");
`endif
    localparam integer PW=$clog2(DEPTH);
    reg [WIDTH-1:0] portable_memory[0:DEPTH-1];
    reg [PW-1:0] read_pointer,write_pointer;
    reg [COUNT_WIDTH-1:0] count;
    wire write_enable=s_axis_tvalid&&s_axis_tready;
    wire read_enable=m_axis_tvalid&&m_axis_tready;
    assign full=count==DEPTH;assign empty=count==0;assign wr_busy=1'b0;assign rd_busy=1'b0;
    assign {m_axis_tuser,m_axis_tlast,m_axis_tkeep,m_axis_tdata}=portable_memory[read_pointer];
    always @(posedge clk)begin
        if(rst)begin read_pointer<=0;write_pointer<=0;count<=0;end
        else begin
            if(write_enable)begin
                portable_memory[write_pointer]<={s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata};
                write_pointer<=write_pointer==DEPTH-1?{PW{1'b0}}:write_pointer+1'b1;
            end
            if(read_enable)read_pointer<=read_pointer==DEPTH-1?{PW{1'b0}}:read_pointer+1'b1;
            case({write_enable,read_enable})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:begin end endcase
        end
    end
`else
    xpm_fifo_sync #(
        .DOUT_RESET_VALUE("0"),.ECC_MODE("no_ecc"),.FIFO_MEMORY_TYPE("block"),
        .FIFO_READ_LATENCY(0),.FIFO_WRITE_DEPTH(DEPTH),.FULL_RESET_VALUE(1),
        .PROG_EMPTY_THRESH(10),.PROG_FULL_THRESH(10),
        .RD_DATA_COUNT_WIDTH(COUNT_WIDTH),.READ_DATA_WIDTH(WIDTH),.READ_MODE("fwft"),
        .SIM_ASSERT_CHK(1),.USE_ADV_FEATURES("0000"),.WAKEUP_TIME(0),
        .WR_DATA_COUNT_WIDTH(COUNT_WIDTH),.WRITE_DATA_WIDTH(WIDTH)
    ) memory (
        .wr_clk(clk),.rst(rst),.sleep(1'b0),
        .din({s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata}),
        .wr_en(s_axis_tvalid&&s_axis_tready),.full(full),.wr_rst_busy(wr_busy),
        .dout({m_axis_tuser,m_axis_tlast,m_axis_tkeep,m_axis_tdata}),
        .rd_en(m_axis_tvalid&&m_axis_tready),.empty(empty),.rd_rst_busy(rd_busy),
        .injectdbiterr(1'b0),.injectsbiterr(1'b0),
        .almost_empty(),.almost_full(),.data_valid(),.dbiterr(),.overflow(),
        .prog_empty(),.prog_full(),.rd_data_count(),.sbiterr(),.underflow(),
        .wr_ack(),.wr_data_count());
`endif
endmodule
`default_nettype wire
