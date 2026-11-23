`timescale 1ns/1ps
`default_nettype none
// Two-entry registered FIFO. Ready depends only on registered occupancy.
// No combinational path crosses the input/output interface in either direction.
module axis_skid_buffer #(
    parameter integer DATA_WIDTH = 128,
    parameter integer KEEP_WIDTH = DATA_WIDTH/8,
    parameter integer USER_WIDTH = 16
)(
    input wire clk, input wire rst,
    input wire [DATA_WIDTH-1:0] s_axis_tdata,
    input wire [KEEP_WIDTH-1:0] s_axis_tkeep,
    input wire s_axis_tvalid, output wire s_axis_tready,
    input wire s_axis_tlast, input wire [USER_WIDTH-1:0] s_axis_tuser,
    output wire [DATA_WIDTH-1:0] m_axis_tdata,
    output wire [KEEP_WIDTH-1:0] m_axis_tkeep,
    output wire m_axis_tvalid, input wire m_axis_tready,
    output wire m_axis_tlast, output wire [USER_WIDTH-1:0] m_axis_tuser
);
    localparam integer WIDTH = DATA_WIDTH+KEEP_WIDTH+USER_WIDTH+1;
    // Explicit head/tail registers keep the payload off a LUT-RAM read-address
    // path. A two-entry array can otherwise infer an asynchronous RAM mux.
    reg [WIDTH-1:0] head_payload,tail_payload;
    reg [1:0] count;
    wire push = s_axis_tvalid && s_axis_tready;
    wire pop = m_axis_tvalid && m_axis_tready;
    assign s_axis_tready = count < 2;
    assign m_axis_tvalid = count != 0;
    assign {m_axis_tuser,m_axis_tlast,m_axis_tkeep,m_axis_tdata} = head_payload;
    always @(posedge clk) begin
        if (rst) begin
            count <= 0;
        end else begin
            if(pop)begin
                if(count==2)head_payload<=tail_payload;
                else if(push)head_payload<={s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata};
            end else if(push && count==0)begin
                head_payload<={s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata};
            end
            if(push && !pop && count!=0)
                tail_payload<={s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata};
            case ({push,pop})
                2'b10: count <= count+1'b1;
                2'b01: count <= count-1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
`default_nettype wire
