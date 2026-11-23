`timescale 1ns/1ps
`default_nettype none
// Parallel lexical classes over an already compacted byte window. Quote and
// backslash masks are raw classes; the grammar retains escape/string state.
module json_simd_scanner #(
    parameter integer LANES=8,parameter integer COUNT_WIDTH=$clog2(LANES+1)
)(
    input wire [LANES*8-1:0] data,input wire [COUNT_WIDTH-1:0] count,
    output wire [LANES-1:0] quote,backslash,colon,comma,object_open,object_close,array_open,array_close,
    output wire [LANES-1:0] whitespace,control,non_ascii,structural,plain_ascii,
    output reg [COUNT_WIDTH-1:0] leading_whitespace,leading_plain_ascii
);
    wire [LANES-1:0] whitespace_prefix;
    wire [LANES-1:0] plain_prefix;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1)begin: classify
        wire [7:0] byte_value=data[lane*8+:8];
        wire present=lane<count;
        assign quote[lane]=present&&byte_value==8'h22;
        assign backslash[lane]=present&&byte_value==8'h5c;
        assign colon[lane]=present&&byte_value==8'h3a;
        assign comma[lane]=present&&byte_value==8'h2c;
        assign object_open[lane]=present&&byte_value==8'h7b;
        assign object_close[lane]=present&&byte_value==8'h7d;
        assign array_open[lane]=present&&byte_value==8'h5b;
        assign array_close[lane]=present&&byte_value==8'h5d;
        assign whitespace[lane]=present&&(byte_value==32||byte_value==9||byte_value==10||byte_value==13);
        assign control[lane]=present&&byte_value<32;
        assign non_ascii[lane]=present&&byte_value[7];
        assign structural[lane]=colon[lane]||comma[lane]||object_open[lane]||object_close[lane]||array_open[lane]||array_close[lane];
        assign plain_ascii[lane]=present&&!(quote[lane]||backslash[lane]||control[lane]||non_ascii[lane]||structural[lane]);
        assign whitespace_prefix[lane]=&whitespace[lane:0];
        assign plain_prefix[lane]=&plain_ascii[lane:0];
    end endgenerate
    integer index;
    always @*begin
        leading_whitespace=0;leading_plain_ascii=0;
        for(index=0;index<LANES;index=index+1)begin
            if(whitespace_prefix[index])leading_whitespace=index+1;
            if(plain_prefix[index])leading_plain_ascii=index+1;
        end
    end
endmodule
`default_nettype wire
