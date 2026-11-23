`timescale 1ns/1ps
`default_nettype none
module cocotb_grpc_headers_top;
    reg clk=0,rst=1,req_valid=0;wire req_ready;
    reg [1:0] req_kind=0,req_encoding=0;reg [31:0] req_grpc_status=0;
    reg [15:0] req_user=0;reg [30:0] req_stream=1;
    reg abort_valid=0,pause=0;wire abort_ready,wire_fenced;
    wire [511:0] header_data;wire [63:0] header_keep;wire header_valid,header_ready,header_last;
    wire [15:0] header_user;
    wire result_valid;reg result_ready=0;wire [7:0] result_status;wire result_tx_emitted;
    wire [1:0] result_kind;wire [15:0] result_user;wire [30:0] result_stream;wire [6:0] result_wire_bytes;
    wire header_idle,arb_idle;
    reg [511:0] b_axis_tdata=0;reg [63:0] b_axis_tkeep=0;reg b_axis_tvalid=0,b_axis_tlast=1;
    reg [15:0] b_axis_tuser=0;wire b_axis_tready;
    wire [511:0] m_axis_tx_tdata;wire [63:0] m_axis_tx_tkeep;
    wire m_axis_tx_tvalid,m_axis_tx_tlast;wire [15:0] m_axis_tx_tuser;reg m_axis_tx_tready=0;
    grpc_response_headers dut(
        .clk(clk),.rst(rst),.req_valid(req_valid),.req_ready(req_ready),.req_kind(req_kind),.req_encoding(req_encoding),
        .req_grpc_status(req_grpc_status),.req_user(req_user),.req_stream(req_stream),
        .abort_valid(abort_valid),.abort_ready(abort_ready),.wire_fenced(wire_fenced),
        .m_axis_tx_tdata(header_data),.m_axis_tx_tkeep(header_keep),.m_axis_tx_tvalid(header_valid),
        .m_axis_tx_tready(header_ready),.m_axis_tx_tlast(header_last),.m_axis_tx_tuser(header_user),
        .result_valid(result_valid),.result_ready(result_ready),.result_status(result_status),.result_tx_emitted(result_tx_emitted),
        .result_kind(result_kind),.result_user(result_user),.result_stream(result_stream),.result_wire_bytes(result_wire_bytes),.idle(header_idle));
    axis_cancellable_frame_arbiter arb(
        .clk(clk),.rst(rst),.a_axis_tdata(header_data),.a_axis_tkeep(header_keep),.a_axis_tvalid(header_valid),
        .a_axis_tready(header_ready),.a_axis_tlast(header_last),.a_axis_tuser(header_user),
        .b_axis_tdata(b_axis_tdata),.b_axis_tkeep(b_axis_tkeep),.b_axis_tvalid(b_axis_tvalid),.b_axis_tready(b_axis_tready),
        .b_axis_tlast(b_axis_tlast),.b_axis_tuser(b_axis_tuser),.m_axis_tdata(m_axis_tx_tdata),.m_axis_tkeep(m_axis_tx_tkeep),
        .m_axis_tvalid(m_axis_tx_tvalid),.m_axis_tready(m_axis_tx_tready),.m_axis_tlast(m_axis_tx_tlast),.m_axis_tuser(m_axis_tx_tuser),
        .idle(arb_idle),.a_pause(pause),.a_paused(wire_fenced));
endmodule
`default_nettype wire
