`timescale 1ns/1ps
`default_nettype none
// Incremental Unicode scalar decoding. State is an incomplete 1..3-byte
// prefix owned by the caller's RPC record, not a fixed on-chip context table.
// Text is tentative until TLAST with abort=0. Result ACK releases the chunk.
module utf8_chunk_decoder #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire start_eos,start_replace,input wire [23:0] start_carry,input wire [1:0] start_carry_count,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,input wire s_axis_text_tlast,
    input wire [USER_WIDTH-1:0] s_axis_text_tuser,input wire s_axis_text_abort,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,
    output wire [USER_WIDTH-1:0] m_axis_text_tuser,output wire m_axis_text_abort,
    output wire result_valid,input wire result_ready,output reg [7:0] result_status,
    output reg [23:0] result_carry,output reg [1:0] result_carry_count,
    output wire [31:0] result_bytes,output wire [USER_WIDTH-1:0] result_user,output wire idle
);
    localparam IDLE=0,SCAN=1,SEND=2,RETRY=3,END_MARKER=4,WAIT_OUTPUT=5,RESULT=6;
    reg [2:0] state,resume_state;
    reg [USER_WIDTH-1:0] context_id;
    reg eos,replace_invalid,dropping,input_closed;
    reg [23:0] original_carry;
    reg [1:0] original_count,remaining;
    reg [7:0] minimum,maximum,retry_octet;
    reg [31:0] pending,output_word,byte_count;
    reg [2:0] pending_count,output_count;
    wire [7:0] byte_data;
    wire byte_keep,byte_valid,byte_last,unpack_idle,unpack_ready;
    wire [USER_WIDTH:0] byte_user;
    wire byte_ready=state==SCAN;
    wire accept_input=state!=IDLE&&state!=RESULT&&!input_closed;
    assign s_axis_text_tready=unpack_ready&&accept_input;
    axis_byte_unpacker #(.DATA_WIDTH(128),.USER_WIDTH(USER_WIDTH+1)) input_bytes(
        .clk(clk),.rst(rst),.s_data(s_axis_text_tdata),.s_keep(s_axis_text_tkeep),
        .s_valid(s_axis_text_tvalid&&accept_input),.s_ready(unpack_ready),
        .s_last(s_axis_text_tlast),.s_user({s_axis_text_abort,s_axis_text_tuser}),
        .m_data(byte_data),.m_keep(byte_keep),.m_valid(byte_valid),.m_ready(byte_ready),
        .m_last(byte_last),.m_user(byte_user),.idle(unpack_idle));
    wire pack_ready;
    axis_byte_packer #(.DATA_WIDTH(128),.USER_WIDTH(USER_WIDTH)) output_bytes(
        .clk(clk),.rst(rst),.s_data(output_word[7:0]),.s_keep(state==SEND),
        .s_valid(state==SEND||state==END_MARKER),.s_ready(pack_ready),
        .s_last(state==END_MARKER),.s_user(context_id),
        .m_data(m_axis_text_tdata),.m_keep(m_axis_text_tkeep),.m_valid(m_axis_text_tvalid),
        .m_ready(m_axis_text_tready),.m_last(m_axis_text_tlast),.m_user(m_axis_text_tuser));
    assign m_axis_text_abort=m_axis_text_tlast&&result_status!=0;
    assign result_valid=state==RESULT;
    assign result_user=context_id;
    assign result_bytes=result_status==0?byte_count:32'd0;
    assign idle=state==IDLE&&unpack_idle&&!m_axis_text_tvalid;
    assign start_ready=!rst&&idle;
    wire [7:0] seed0=start_carry[7:0],seed1=start_carry[15:8],seed2=start_carry[23:16];
    wire seed_lead2=seed0>=8'hc2&&seed0<=8'hdf;
    wire seed_lead3=seed0>=8'he0&&seed0<=8'hef;
    wire seed_lead4=seed0>=8'hf0&&seed0<=8'hf4;
    wire [7:0] seed_min=seed0==8'he0 ? 8'ha0:seed0==8'hf0 ? 8'h90:8'h80;
    wire [7:0] seed_max=seed0==8'hed ? 8'h9f:seed0==8'hf4 ? 8'h8f:8'hbf;
    wire seed_second=seed1>=seed_min&&seed1<=seed_max;
    wire seed_good=start_carry_count==0?start_carry==0:
        start_carry_count==1?start_carry[23:8]==0&&(seed_lead2||seed_lead3||seed_lead4):
        start_carry_count==2?seed2==0&&(seed_lead3||seed_lead4)&&seed_second:
        seed_lead4&&seed_second&&seed2>=8'h80&&seed2<=8'hbf;
    wire [2:0] seed_total=seed_lead2?3'd2:seed_lead3?3'd3:3'd4;
    task emit_bytes;
        input [31:0] data;input [2:0] count;input [2:0] following;
        begin output_word<=data;output_count<=count;resume_state<=following;state<=SEND;end
    endtask
    task fail_chunk;
        input [7:0] status;
        begin
            if(result_status==0)result_status<=status;
            dropping<=1;pending<=0;pending_count<=0;remaining<=0;
        end
    endtask
    task consume_octet;
        input [7:0] octet;
        begin
            if(remaining==0)begin
                if(octet<128)emit_bytes({24'd0,octet},1,SCAN);
                else if(octet>=8'hc2&&octet<=8'hf4)begin
                    pending<={24'd0,octet};pending_count<=1;minimum<=8'h80;maximum<=8'hbf;
                    if(octet<=8'hdf)remaining<=1;
                    else if(octet<=8'hef)begin remaining<=2;if(octet==8'he0)minimum<=8'ha0;if(octet==8'hed)maximum<=8'h9f;end
                    else begin remaining<=3;if(octet==8'hf0)minimum<=8'h90;if(octet==8'hf4)maximum<=8'h8f;end
                end else if(replace_invalid)emit_bytes(32'h00bdbfef,3,SCAN);
                else fail_chunk(1);
            end else if(octet>=minimum&&octet<=maximum)begin
                minimum<=8'h80;maximum<=8'hbf;remaining<=remaining-1'b1;
                if(remaining==1)begin
                    emit_bytes(pending|({24'd0,octet}<<(pending_count*8)),pending_count+1'b1,SCAN);
                    pending<=0;pending_count<=0;
                end else begin pending[pending_count*8+:8]<=octet;pending_count<=pending_count+1'b1;end
            end else begin
                remaining<=0;pending<=0;pending_count<=0;minimum<=8'h80;maximum<=8'hbf;
                if(replace_invalid)begin retry_octet<=octet;emit_bytes(32'h00bdbfef,3,RETRY);end
                else fail_chunk(1);
            end
        end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;resume_state<=SCAN;context_id<=0;eos<=0;replace_invalid<=0;dropping<=0;input_closed<=1;
            original_carry<=0;original_count<=0;remaining<=0;minimum<=8'h80;maximum<=8'hbf;
            retry_octet<=0;pending<=0;pending_count<=0;output_word<=0;output_count<=0;byte_count<=0;
            result_status<=0;result_carry<=0;result_carry_count<=0;
        end else begin
        if(s_axis_text_tvalid&&s_axis_text_tready&&s_axis_text_tlast)input_closed<=1;
        case(state)
            IDLE:if(start_valid&&start_ready)begin
                context_id<=start_user;eos<=start_eos;replace_invalid<=start_replace;input_closed<=0;
                original_carry<=start_carry;original_count<=start_carry_count;result_carry<=0;result_carry_count<=0;
                result_status<=seed_good?0:2;dropping<=!seed_good;pending<={8'd0,start_carry};
                pending_count<={1'b0,start_carry_count};byte_count<=0;
                remaining<=start_carry_count==0?2'd0:seed_total-start_carry_count;
                minimum<=start_carry_count==1?seed_min:8'h80;
                maximum<=start_carry_count==1?seed_max:8'hbf;state<=SCAN;
            end
            SCAN:if(byte_valid&&byte_ready)begin
                if(byte_last)begin
                    if(byte_user[USER_WIDTH]||dropping||byte_user[USER_WIDTH-1:0]!=context_id)begin
                        if(byte_user[USER_WIDTH])result_status<=5;
                        else if(result_status==0)result_status<=3;
                        result_carry<=original_carry;result_carry_count<=original_count;state<=END_MARKER;
                    end else if(remaining==0)begin result_carry<=0;result_carry_count<=0;state<=END_MARKER;end
                    else if(!eos)begin result_carry<=pending[23:0];result_carry_count<=pending_count[1:0];state<=END_MARKER;end
                    else begin
                        remaining<=0;pending<=0;pending_count<=0;
                        if(replace_invalid)begin result_carry<=0;result_carry_count<=0;emit_bytes(32'h00bdbfef,3,END_MARKER);end
                        else begin result_status<=4;result_carry<=original_carry;result_carry_count<=original_count;state<=END_MARKER;end
                    end
                end else if(byte_user[USER_WIDTH-1:0]!=context_id)fail_chunk(3);
                else if(byte_keep&&!dropping)consume_octet(byte_data);
            end
            SEND:if(pack_ready)begin
                output_word<=output_word>>8;output_count<=output_count-1'b1;
                if(byte_count==32'hffffffff)fail_chunk(6);else byte_count<=byte_count+1'b1;
                if(output_count==1)state<=resume_state;
            end
            RETRY:begin state<=SCAN;if(!dropping)consume_octet(retry_octet);end
            END_MARKER:if(pack_ready)state<=WAIT_OUTPUT;
            WAIT_OUTPUT:if(m_axis_text_tvalid&&m_axis_text_tready&&m_axis_text_tlast)state<=RESULT;
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
        end
    end
endmodule
`default_nettype wire
