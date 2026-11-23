`timescale 1ns/1ps
`default_nettype none
// Byte stream -> Unicode scalar plus its original 1..4 UTF-8 bytes. A zero-
// keep/TLAST input is an explicit EOF and produces a zero-keep terminal record.
// Completed scalars before a later error are tentative; the owning packet
// controller must discard the packet on error. Malformed packets drain fully.
module utf8_codepoint_reader #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output wire s_ready,
    input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output reg [20:0] m_codepoint,output reg [31:0] m_bytes,output reg [2:0] m_length,
    output reg m_keep,output reg m_valid,input wire m_ready,output reg m_last,output reg [USER_WIDTH-1:0] m_user,
    output wire error_valid,input wire error_ready,output reg [7:0] error_code,output wire [USER_WIDTH-1:0] error_user,
    output wire idle
);
    localparam READ=0,DRAIN=1,ERROR_STATE=2;
    reg [1:0] state,remaining,next_remaining;
    reg [7:0] minimum,maximum,next_minimum,next_maximum;
    reg [20:0] accumulated,next_accumulated;
    reg [31:0] raw;
    reg [2:0] count;
    reg active,invalid;
    reg [USER_WIDTH-1:0] context_id;
    wire [31:0] next_raw=remaining==0?{24'd0,s_data}:raw|({24'd0,s_data}<<(count*8));
    assign s_ready=!rst && state!=ERROR_STATE && !(m_valid&&m_last) && (!m_valid||m_ready);
    assign error_valid=state==ERROR_STATE;
    assign error_user=context_id;
    assign idle=state==READ && !active && !m_valid && remaining==0 && !s_valid;
    always @*begin
        invalid=0;next_remaining=0;next_minimum=8'h80;next_maximum=8'hbf;next_accumulated=0;
        if(remaining!=0)begin
            invalid=s_data<minimum||s_data>maximum;
            next_remaining=remaining-1'b1;next_accumulated={accumulated[14:0],s_data[5:0]};
        end else if(s_data<128)next_accumulated={14'd0,s_data[6:0]};
        else if(s_data>=8'hc2&&s_data<=8'hdf)begin next_remaining=1;next_accumulated={16'd0,s_data[4:0]};end
        else if(s_data>=8'he0&&s_data<=8'hef)begin
            next_remaining=2;next_accumulated={17'd0,s_data[3:0]};
            if(s_data==8'he0)next_minimum=8'ha0;
            if(s_data==8'hed)next_maximum=8'h9f;
        end else if(s_data>=8'hf0&&s_data<=8'hf4)begin
            next_remaining=3;next_accumulated={18'd0,s_data[2:0]};
            if(s_data==8'hf0)next_minimum=8'h90;
            if(s_data==8'hf4)next_maximum=8'h8f;
        end else invalid=1;
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=READ;remaining<=0;minimum<=8'h80;maximum<=8'hbf;accumulated<=0;raw<=0;count<=0;
            active<=0;context_id<=0;m_codepoint<=0;m_bytes<=0;m_length<=0;m_keep<=0;m_valid<=0;m_last<=0;m_user<=0;error_code<=0;
        end else begin
            if(m_valid&&m_ready)begin m_valid<=0;if(m_last)active<=0;end
            case(state)
                READ:if(s_valid&&s_ready)begin
                    if(s_keep||s_last)begin
                        if(!active)begin active<=1;context_id<=s_user;end
                        if(active&&s_user!=context_id)begin
                            error_code<=3;state<=s_last?ERROR_STATE:DRAIN;
                        end else if(!s_keep)begin
                            if(remaining!=0)begin error_code<=2;state<=ERROR_STATE;end
                            else begin m_codepoint<=0;m_bytes<=0;m_length<=0;m_keep<=0;m_valid<=1;m_last<=1;m_user<=active?context_id:s_user;end
                        end else if(invalid)begin error_code<=1;state<=s_last?ERROR_STATE:DRAIN;end
                        else if(s_last&&next_remaining!=0)begin error_code<=2;state<=ERROR_STATE;end
                        else begin
                            remaining<=next_remaining;minimum<=next_minimum;maximum<=next_maximum;
                            accumulated<=next_accumulated;raw<=next_raw;count<=remaining==0?1:count+1'b1;
                            if(next_remaining==0)begin
                                m_codepoint<=next_accumulated;m_bytes<=next_raw;m_length<=remaining==0?1:count+1'b1;
                                m_keep<=1;m_valid<=1;m_last<=s_last;m_user<=active?context_id:s_user;
                            end
                        end
                    end
                end
                DRAIN:if(s_valid&&s_ready&&s_last)state<=ERROR_STATE;
                ERROR_STATE:if(error_ready)begin
                    state<=READ;remaining<=0;minimum<=8'h80;maximum<=8'hbf;accumulated<=0;raw<=0;count<=0;active<=0;
                end
                default:state<=READ;
            endcase
        end
    end
endmodule
`default_nettype wire
