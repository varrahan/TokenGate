`timescale 1ns/1ps
`default_nettype none
// JSON string contents, excluding quote delimiters. Input EOF is a distinct
// keep=0,last=1 record. Produces UTF-8 scalar values and a final status marker.
// Status: 1 truncated escape, 2 illegal escape/control, 3 invalid UTF-8,
// 4 unpaired surrogate. Tentative bytes require transactional packet commit.
module json_string_normalizer #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output wire s_ready,
    input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output wire [7:0] m_data,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user,
    output wire [7:0] packet_status
);
    localparam NORMAL=0,ESCAPE=1,HEX=2,HIGH_SLASH=3,HIGH_U=4,LOW_HEX=5,DRAIN=6,FINISH=7;
    reg [2:0] state;
    reg [31:0] pending;
    reg [2:0] pending_count;
    reg [15:0] unicode_value,high_surrogate;
    reg [1:0] hex_index,utf8_remaining;
    reg [7:0] next_min,next_max,status;
    reg [USER_WIDTH-1:0] context_id;
    reg packet_open;
    function is_hex(input [7:0] value);
        begin is_hex=(value>=48&&value<=57)||(value>=65&&value<=70)||(value>=97&&value<=102);end
    endfunction
    function [3:0] hex_value(input [7:0] value);
        begin hex_value=value<=57 ? value-48 : value<=70 ? value-55 : value-87;end
    endfunction
    function [34:0] encode_utf8(input [20:0] cp);
        begin
            if(cp<128)encode_utf8={3'd1,24'd0,cp[7:0]};
            else if(cp<2048)encode_utf8={3'd2,16'd0,{2'b10,cp[5:0]},{3'b110,cp[10:6]}};
            else if(cp<65536)encode_utf8={3'd3,8'd0,{2'b10,cp[5:0]},{2'b10,cp[11:6]},{4'b1110,cp[15:12]}};
            else encode_utf8={3'd4,{2'b10,cp[5:0]},{2'b10,cp[11:6]},{2'b10,cp[17:12]},{5'b11110,cp[20:18]}};
        end
    endfunction
    wire [15:0] codeunit={unicode_value[11:0],hex_value(s_data)};
    wire [20:0] paired_cp=21'h10000+(({5'd0,high_surrogate}-21'hd800)<<10)+({5'd0,codeunit}-21'hdc00);
    assign s_ready=!rst && pending_count==0 && state!=FINISH;
    assign m_valid=pending_count!=0 || state==FINISH;
    assign m_keep=pending_count!=0;
    assign m_data=pending_count!=0 ? pending[7:0] : 8'd0;
    assign m_last=state==FINISH;
    assign m_user=context_id;
    assign packet_status=status;
    always @(posedge clk)begin
        if(rst)begin
            state<=NORMAL;pending<=0;pending_count<=0;unicode_value<=0;high_surrogate<=0;
            hex_index<=0;utf8_remaining<=0;next_min<=8'h80;next_max<=8'hbf;
            status<=0;context_id<=0;packet_open<=0;
        end else begin
            if(m_valid && m_ready)begin
                if(pending_count!=0)begin pending<=pending>>8;pending_count<=pending_count-1'b1;end
                else begin state<=NORMAL;status<=0;packet_open<=0;utf8_remaining<=0;end
            end
            if(s_valid && s_ready)begin
                if(!packet_open && (s_keep || s_last))begin context_id<=s_user;packet_open<=1;end
                if(!s_keep && s_last)begin
                    if(state!=DRAIN)begin
                        if(state==HIGH_SLASH || state==HIGH_U || state==LOW_HEX)status<=4;
                        else if(state!=NORMAL)status<=1;
                        else if(utf8_remaining!=0)status<=3;
                    end
                    state<=FINISH;
                end else if(s_keep)case(state)
                    NORMAL:begin
                        if(utf8_remaining!=0)begin
                            if(s_data<next_min || s_data>next_max)begin status<=3;state<=DRAIN;end
                            else begin
                                pending<={24'd0,s_data};pending_count<=1;
                                utf8_remaining<=utf8_remaining-1'b1;next_min<=8'h80;next_max<=8'hbf;
                            end
                        end else if(s_data==8'h5c)state<=ESCAPE;
                        else if(s_data<32 || s_data==8'h22)begin status<=2;state<=DRAIN;end
                        else if(s_data<128)begin pending<={24'd0,s_data};pending_count<=1;end
                        else begin
                            next_min<=8'h80;next_max<=8'hbf;
                            if(s_data>=8'hc2 && s_data<=8'hdf)begin
                                utf8_remaining<=1;pending<={24'd0,s_data};pending_count<=1;
                            end else if(s_data>=8'he0 && s_data<=8'hef)begin
                                utf8_remaining<=2;pending<={24'd0,s_data};pending_count<=1;
                                if(s_data==8'he0)next_min<=8'ha0;
                                if(s_data==8'hed)next_max<=8'h9f;
                            end else if(s_data>=8'hf0 && s_data<=8'hf4)begin
                                utf8_remaining<=3;pending<={24'd0,s_data};pending_count<=1;
                                if(s_data==8'hf0)next_min<=8'h90;
                                if(s_data==8'hf4)next_max<=8'h8f;
                            end else begin status<=3;state<=DRAIN;end
                        end
                    end
                    ESCAPE:begin
                        state<=NORMAL;
                        case(s_data)
                            8'h22,8'h5c,8'h2f:begin pending<={24'd0,s_data};pending_count<=1;end
                            8'h62:begin pending<=8'h08;pending_count<=1;end
                            8'h66:begin pending<=8'h0c;pending_count<=1;end
                            8'h6e:begin pending<=8'h0a;pending_count<=1;end
                            8'h72:begin pending<=8'h0d;pending_count<=1;end
                            8'h74:begin pending<=8'h09;pending_count<=1;end
                            8'h75:begin unicode_value<=0;hex_index<=0;state<=HEX;end
                            default:begin status<=2;state<=DRAIN;end
                        endcase
                    end
                    HEX,LOW_HEX:begin
                        if(!is_hex(s_data))begin status<=2;state<=DRAIN;end
                        else if(hex_index==3)begin
                            if(state==LOW_HEX)begin
                                if(codeunit<16'hdc00 || codeunit>16'hdfff)begin status<=4;state<=DRAIN;end
                                else begin {pending_count,pending}<=encode_utf8(paired_cp);state<=NORMAL;end
                            end else if(codeunit>=16'hd800 && codeunit<=16'hdbff)begin high_surrogate<=codeunit;state<=HIGH_SLASH;end
                            else if(codeunit>=16'hdc00 && codeunit<=16'hdfff)begin status<=4;state<=DRAIN;end
                            else begin {pending_count,pending}<=encode_utf8({5'd0,codeunit});state<=NORMAL;end
                        end else begin unicode_value<=codeunit;hex_index<=hex_index+1'b1;end
                    end
                    HIGH_SLASH:if(s_data==8'h5c)state<=HIGH_U;else begin status<=4;state<=DRAIN;end
                    HIGH_U:if(s_data==8'h75)begin unicode_value<=0;hex_index<=0;state<=LOW_HEX;end
                           else begin status<=4;state<=DRAIN;end
                    DRAIN:begin end
                    default:begin end
                endcase
            end
        end
    end
endmodule
`default_nettype wire
