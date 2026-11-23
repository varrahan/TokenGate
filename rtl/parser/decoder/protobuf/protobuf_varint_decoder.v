`timescale 1ns/1ps
`default_nettype none
// Parses up to LANES bytes per cycle from a caller-managed byte window.
// consumed reports only bytes belonging to this varint; the caller retains
// any remaining bytes in the window. Supports splits across arbitrary windows.
module protobuf_varint_decoder #(
    parameter integer LANES=8,
    parameter integer COUNT_WIDTH=$clog2(LANES+1)
)(
    input wire clk,input wire rst,
    input wire [LANES*8-1:0] s_data,input wire [COUNT_WIDTH-1:0] s_count,
    input wire s_valid,output wire s_ready,input wire s_packet_last,
    output wire [COUNT_WIDTH-1:0] consumed,
    output reg [63:0] m_value,output reg m_error,output reg m_valid,input wire m_ready
);
    reg [63:0] accumulator;
    reg [3:0] bytes_seen;
    reg [63:0] next_accumulator;
    reg [3:0] next_seen;
    reg [COUNT_WIDTH-1:0] used;
    reg done,error;
    reg [7:0] byte_value;
    integer lane;
    assign s_ready=!rst && (!m_valid || m_ready);
    assign consumed=(s_valid && s_ready) ? used : {COUNT_WIDTH{1'b0}};
    always @* begin
        next_accumulator=accumulator;next_seen=bytes_seen;
        used=0;done=0;error=0;byte_value=0;
        for(lane=0;lane<LANES;lane=lane+1)begin
            if(lane<s_count && !done)begin
                byte_value=s_data[lane*8+:8];used=used+1'b1;
                if(next_seen==9 && byte_value>1)begin done=1;error=1;end
                else begin
                    next_accumulator=next_accumulator | ({57'd0,byte_value[6:0]} << (next_seen*7));
                    next_seen=next_seen+1'b1;
                    if(!byte_value[7])done=1;
                end
            end
        end
        if(!done && s_packet_last)begin done=1;error=1;end
    end
    always @(posedge clk)begin
        if(rst)begin accumulator<=0;bytes_seen<=0;m_value<=0;m_error<=0;m_valid<=0;end
        else begin
            if(m_valid && m_ready)m_valid<=0;
            if(s_valid && s_ready)begin
                if(done)begin
                    m_value<=next_accumulator;m_error<=error;m_valid<=1;
                    accumulator<=0;bytes_seen<=0;
                end else begin accumulator<=next_accumulator;bytes_seen<=next_seen;end
            end
        end
    end
endmodule
`default_nettype wire
