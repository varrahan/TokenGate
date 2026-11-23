`timescale 1ns/1ps
`default_nettype none
// Validates Unicode scalar UTF-8, rejecting overlong forms, surrogates,
// values above U+10FFFF and incomplete sequences at a field boundary.
module utf8_byte_validator (
    input wire clk,input wire rst,input wire clear,
    input wire byte_valid,input wire [7:0] byte_data,input wire byte_last,
    output wire byte_error
);
    reg [1:0] remaining,next_remaining;
    reg [7:0] minimum,maximum,next_minimum,next_maximum;
    reg invalid;
    always @* begin
        invalid=0;next_remaining=remaining;next_minimum=8'h80;next_maximum=8'hbf;
        if(remaining!=0)begin
            if(byte_data<minimum || byte_data>maximum)invalid=1;
            next_remaining=remaining-1'b1;
        end else if(byte_data<128)next_remaining=0;
        else if(byte_data>=8'hc2 && byte_data<=8'hdf)next_remaining=1;
        else if(byte_data>=8'he0 && byte_data<=8'hef)begin
            next_remaining=2;
            if(byte_data==8'he0)next_minimum=8'ha0;
            if(byte_data==8'hed)next_maximum=8'h9f;
        end else if(byte_data>=8'hf0 && byte_data<=8'hf4)begin
            next_remaining=3;
            if(byte_data==8'hf0)next_minimum=8'h90;
            if(byte_data==8'hf4)next_maximum=8'h8f;
        end else invalid=1;
    end
    assign byte_error=byte_valid && (invalid || (byte_last && next_remaining!=0));
    always @(posedge clk)begin
        if(rst || clear)begin remaining<=0;minimum<=8'h80;maximum<=8'hbf;end
        else if(byte_valid)begin remaining<=next_remaining;minimum<=next_minimum;maximum<=next_maximum;end
    end
endmodule
`default_nettype wire
