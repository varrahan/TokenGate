`timescale 1ns/1ps
`default_nettype none
// Protobuf field parser over a caller-managed 8-byte window. Data windows
// carry 1..8 bytes; packet end is a distinct count=0,last=1 record. The caller
// advances only by consumed. Selected length-delimited fields are emitted as
// bytes. The final keep=0,last=1 record carries packet_status; a transactional
// outer decoder must discard buffered text when packet_status is nonzero.
module protobuf_wire_fsm #(
    parameter integer USER_WIDTH=16,
    parameter integer MAX_FIELD_BYTES=16384,
    parameter integer MAX_GROUP_DEPTH=16
)(
    input wire clk,input wire rst,
    input wire [63:0] s_data,input wire [3:0] s_count,
    input wire s_valid,output wire s_ready,input wire s_last,
    input wire [USER_WIDTH-1:0] s_user,output reg [3:0] consumed,
    output wire [28:0] field_number,input wire field_selected,
    output wire [7:0] m_data,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user,
    output wire [7:0] packet_status,output wire idle
);
    localparam VREQ=0,VCHECK=1,PAYLOAD=2,SKIP=3,DRAIN=4,FINISH=5;
    localparam TAG=0,LENGTH=1,SKIP_VARINT=2;
    localparam integer GW=$clog2(MAX_GROUP_DEPTH+1);
    reg [2:0] state;
    reg [1:0] kind;
    reg [31:0] remaining;
    reg [28:0] field_reg;
    reg [28:0] group_stack[0:MAX_GROUP_DEPTH-1];
    reg [GW-1:0] group_depth;
    reg partial_varint,packet_open;
    reg [7:0] status;
    reg [USER_WIDTH-1:0] context_id;
    wire varint_ready,varint_valid,varint_error;
    wire [3:0] varint_consumed;
    wire [63:0] varint_value;
    wire utf8_error;
    utf8_byte_validator utf8_i (
        .clk(clk),.rst(rst),
        .clear(state==VCHECK && varint_valid && kind==LENGTH),
        .byte_valid(state==PAYLOAD && s_valid && s_ready && s_count!=0),
        .byte_data(s_data[7:0]),.byte_last(remaining==1),.byte_error(utf8_error));
    protobuf_varint_decoder varint_i (
        .clk(clk),.rst(rst || (state==FINISH && m_ready)),.s_data(s_data),.s_count(s_count),
        .s_valid(state==VREQ && s_valid && s_count!=0),.s_ready(varint_ready),
        .s_packet_last(1'b0),.consumed(varint_consumed),.m_value(varint_value),
        .m_error(varint_error),.m_valid(varint_valid),.m_ready(state==VCHECK));
    assign field_number=field_reg;
    assign m_data=state==PAYLOAD ? s_data[7:0] : 8'd0;
    assign m_keep=state==PAYLOAD && s_count!=0;
    assign m_valid=state==FINISH || (state==PAYLOAD && s_valid && s_count!=0);
    assign m_last=state==FINISH;
    assign m_user=context_id;
    assign packet_status=status;
    assign idle=state==VREQ && kind==TAG && !packet_open && !partial_varint;
    assign s_ready=!rst && ((state==VREQ && varint_ready) || state==SKIP || state==DRAIN ||
                            (state==PAYLOAD && (s_count==0 || m_ready)));
    always @* begin
        consumed=0;
        if(s_valid && s_ready)case(state)
            VREQ:consumed=varint_consumed;
            PAYLOAD:if(s_count!=0)consumed=1;
            SKIP:consumed=remaining<s_count ? remaining[3:0] : s_count;
            DRAIN:consumed=s_count;
            default:consumed=0;
        endcase
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=VREQ;kind<=TAG;remaining<=0;field_reg<=0;group_depth<=0;
            partial_varint<=0;packet_open<=0;status<=0;context_id<=0;
        end else begin
            if(s_valid && s_ready && !packet_open && (s_count!=0 || s_last))begin
                context_id<=s_user;packet_open<=1;
            end
            case(state)
                VREQ:if(s_valid && s_ready)begin
                    if(s_count==0 && s_last)begin
                        if(kind!=TAG || partial_varint)status<=1;
                        else if(group_depth!=0)status<=5;
                        state<=FINISH;
                    end else if(s_count!=0)state<=VCHECK;
                end
                VCHECK:begin
                    if(!varint_valid)begin partial_varint<=1;state<=VREQ;end
                    else begin
                        partial_varint<=0;
                        if(varint_error)begin status<=2;state<=DRAIN;end
                        else case(kind)
                            TAG:begin
                                field_reg<=varint_value[31:3];
                                if(varint_value>64'hffffffff || varint_value[31:3]==0 || varint_value[2:0]>5)begin
                                    status<=3;state<=DRAIN;
                                end else case(varint_value[2:0])
                                    0:begin kind<=SKIP_VARINT;state<=VREQ;end
                                    1:begin remaining<=8;state<=SKIP;end
                                    2:begin kind<=LENGTH;state<=VREQ;end
                                    3:if(group_depth==MAX_GROUP_DEPTH)begin status<=6;state<=DRAIN;end
                                      else begin group_stack[group_depth]<=varint_value[31:3];group_depth<=group_depth+1'b1;kind<=TAG;state<=VREQ;end
                                    4:if(group_depth==0)begin status<=5;state<=DRAIN;end
                                      else if(group_stack[group_depth-1'b1]!=varint_value[31:3])begin status<=5;state<=DRAIN;end
                                      else begin group_depth<=group_depth-1'b1;kind<=TAG;state<=VREQ;end
                                    5:begin remaining<=4;state<=SKIP;end
                                    default:begin status<=3;state<=DRAIN;end
                                endcase
                            end
                            LENGTH:if(varint_value>MAX_FIELD_BYTES)begin status<=4;state<=DRAIN;end
                                   else begin
                                       remaining<=varint_value[31:0];kind<=TAG;
                                       if(varint_value==0)state<=VREQ;
                                       else state<=field_selected && group_depth==0 ? PAYLOAD : SKIP;
                                   end
                            SKIP_VARINT:begin kind<=TAG;state<=VREQ;end
                            default:begin status<=3;state<=DRAIN;end
                        endcase
                    end
                end
                PAYLOAD:if(s_valid && s_ready)begin
                    if(s_count==0 && s_last)begin status<=1;state<=FINISH;end
                    else if(consumed!=0)begin
                        if(utf8_error)begin status<=7;state<=DRAIN;end
                        else begin
                            remaining<=remaining-1'b1;
                            if(remaining==1)begin kind<=TAG;state<=VREQ;end
                        end
                    end
                end
                SKIP:if(s_valid && s_ready)begin
                    if(s_count==0 && s_last)begin status<=1;state<=FINISH;end
                    else begin
                        remaining<=remaining-consumed;
                        if(remaining==consumed)begin kind<=TAG;state<=VREQ;end
                    end
                end
                DRAIN:if(s_valid && s_ready && s_count==0 && s_last)state<=FINISH;
                FINISH:if(m_ready)begin
                    state<=VREQ;kind<=TAG;remaining<=0;group_depth<=0;
                    partial_varint<=0;packet_open<=0;status<=0;
                end
                default:state<=VREQ;
            endcase
        end
    end
endmodule
`default_nettype wire
