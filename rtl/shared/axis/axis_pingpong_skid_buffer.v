`timescale 1ns/1ps
`default_nettype none
// Two registered slots with independent write/read pointers. Input ready is
// registered occupancy only. A pop changes the read pointer; downstream ready
// never selects or enables either wide payload register's next value.
module axis_pingpong_skid_buffer #(
    parameter integer DATA_WIDTH=128,
    parameter integer KEEP_WIDTH=DATA_WIDTH/8,
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [DATA_WIDTH-1:0] s_axis_tdata,
    input wire [KEEP_WIDTH-1:0] s_axis_tkeep,
    input wire s_axis_tvalid,output wire s_axis_tready,
    input wire s_axis_tlast,input wire [USER_WIDTH-1:0] s_axis_tuser,
    output wire [DATA_WIDTH-1:0] m_axis_tdata,
    output wire [KEEP_WIDTH-1:0] m_axis_tkeep,
    output wire m_axis_tvalid,input wire m_axis_tready,
    output wire m_axis_tlast,output wire [USER_WIDTH-1:0] m_axis_tuser
);
    localparam integer WIDTH=DATA_WIDTH+KEEP_WIDTH+USER_WIDTH+1;
    reg [WIDTH-1:0] slot0_payload,slot1_payload;
    reg [1:0] count;
    reg read_slot,write_slot;
    wire push=s_axis_tvalid&&s_axis_tready;
    wire pop=m_axis_tvalid&&m_axis_tready;
    assign s_axis_tready=count<2;
    assign m_axis_tvalid=count!=0;
    assign {m_axis_tuser,m_axis_tlast,m_axis_tkeep,m_axis_tdata}=
        read_slot ? slot1_payload : slot0_payload;
    always @(posedge clk)begin
        if(rst)begin count<=0;read_slot<=0;write_slot<=0;end
        else begin
            if(push)begin
                if(write_slot)slot1_payload<={s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata};
                else slot0_payload<={s_axis_tuser,s_axis_tlast,s_axis_tkeep,s_axis_tdata};
                write_slot<=!write_slot;
            end
            if(pop)read_slot<=!read_slot;
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:count<=count;
            endcase
        end
    end
endmodule
`default_nettype wire
