`timescale 1ns/1ps
`default_nettype none
// Compacted lookahead for the parallel Protobuf varint parser. The consumer
// advances by m_consumed, retaining unconsumed bytes. EOF is its own zero-count
// record, including when a packet ends exactly at the eight-byte boundary.
module axis_byte_window #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output wire s_ready,
    input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output wire [63:0] m_data,output wire [3:0] m_count,
    output wire m_valid,input wire m_ready,input wire [3:0] m_consumed,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user,output wire idle
);
    reg [63:0] buffer_data;
    reg [3:0] count;
    reg eof,packet_open;
    reg [USER_WIDTH-1:0] context_id;
    assign s_ready=!rst && !eof && count<8;
    assign m_valid=count==8 || eof;
    assign m_data=buffer_data;
    assign m_count=count;
    assign m_last=eof && count==0;
    assign m_user=context_id;
    assign idle=count==0 && !eof && !packet_open;
    always @(posedge clk)begin
        if(rst)begin buffer_data<=0;count<=0;eof<=0;packet_open<=0;context_id<=0;end
        else begin
            if(m_valid && m_ready)begin
                if(m_last)begin buffer_data<=0;count<=0;eof<=0;packet_open<=0;end
                else begin buffer_data<=buffer_data>>(m_consumed*8);count<=count-m_consumed;end
            end
            if(s_valid && s_ready)begin
                if(!packet_open && (s_keep||s_last))begin context_id<=s_user;packet_open<=1;end
                if(s_keep)begin buffer_data[count*8+:8]<=s_data;count<=count+1'b1;end
                if(s_last)eof<=1;
            end
        end
    end
endmodule
`default_nettype wire
