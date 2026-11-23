`timescale 1ns/1ps
`default_nettype none
// JSON string-content escaping. UTF-8 payload bytes >= 0x20 pass unchanged;
// quote/backslash/control bytes expand into the required JSON escape sequence.
module json_escape_encoder #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output wire s_ready,
    input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output wire [7:0] m_data,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user
);
    reg [47:0] pending;
    reg [2:0] count;
    reg keep_reg,last_reg;
    reg [USER_WIDTH-1:0] context_id;
    function [7:0] hex_digit(input [3:0] nibble);
        begin hex_digit=nibble<10 ? 8'd48+nibble : 8'd87+nibble;end
    endfunction
    assign s_ready=!rst && count==0;
    assign m_valid=count!=0;
    assign m_data=pending[7:0];
    assign m_keep=keep_reg;
    assign m_last=last_reg && count==1;
    assign m_user=context_id;
    always @(posedge clk) begin
        if(rst) begin pending<=0;count<=0;keep_reg<=0;last_reg<=0;context_id<=0;end
        else begin
            if(m_valid && m_ready) begin pending<=pending>>8;count<=count-1'b1;end
            if(s_valid && s_ready) begin
                context_id<=s_user;keep_reg<=s_keep;last_reg<=s_last;
                if(!s_keep) begin pending<=0;count<=s_last ? 1 : 0;end
                else if(s_data==8'h22 || s_data==8'h5c)begin
                    pending<={32'd0,s_data,8'h5c};count<=2;
                end else case(s_data)
                    8'h08:begin pending<=48'h625c;count<=2;end
                    8'h09:begin pending<=48'h745c;count<=2;end
                    8'h0a:begin pending<=48'h6e5c;count<=2;end
                    8'h0c:begin pending<=48'h665c;count<=2;end
                    8'h0d:begin pending<=48'h725c;count<=2;end
                    default: if(s_data<8'h20)begin
                        pending<={hex_digit(s_data[3:0]),hex_digit(s_data[7:4]),8'h30,8'h30,8'h75,8'h5c};count<=6;
                    end else begin pending<={40'd0,s_data};count<=1;end
                endcase
            end
        end
    end
endmodule
`default_nettype wire
