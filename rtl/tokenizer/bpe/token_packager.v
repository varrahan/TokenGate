`timescale 1ns/1ps
`default_nettype none
// Packs complete 32-bit token IDs into the 512-bit C2H contract. TKEEP always
// marks all four bytes of each valid ID. Zero-keep/TLAST represents an empty
// sequence or an explicit EOF following a previously emitted full beat.
module token_packager #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire [31:0] s_token,input wire s_keep,input wire s_valid,output wire s_ready,
    input wire s_sequence_last,input wire [USER_WIDTH-1:0] s_user,
    output reg [511:0] m_axis_tokens_tdata,output reg [63:0] m_axis_tokens_tkeep,
    output reg m_axis_tokens_tvalid,input wire m_axis_tokens_tready,
    output reg m_axis_tokens_tlast,output reg [USER_WIDTH-1:0] m_axis_tokens_tuser,
    output wire idle
);
    reg [511:0] partial_data;
    reg [4:0] count;
    reg sequence_active,final_pending,emit_pending,emit_last;
    reg [USER_WIDTH-1:0] context_id;
    reg [USER_WIDTH-1:0] emit_user;
    reg [4:0] emit_count;
    wire [5:0] next_count={1'b0,count}+s_keep;
    wire output_room=!m_axis_tokens_tvalid||m_axis_tokens_tready;
    wire emit_fire=emit_pending&&output_room;
    wire capture=s_valid&&s_ready&&(s_keep||s_sequence_last);
    assign s_ready=!rst&&!final_pending&&(!m_axis_tokens_tvalid||m_axis_tokens_tready);
    assign idle=!sequence_active&&!final_pending&&!emit_pending&&count==0&&!m_axis_tokens_tvalid&&!(s_valid&&s_ready);
    // A fixed bank per token avoids a 512-bit variable insert on the output
    // register. Emission and the first token of the next group can share a
    // clock, preserving one accepted token per cycle with an available sink.
    genvar bank;
    generate for(bank=0;bank<16;bank=bank+1)begin:token_bank
        wire bank_write=capture&&s_keep&&count==bank;
        always @(posedge clk)begin
            if(rst||emit_fire&&!bank_write)partial_data[bank*32+:32]<=0;
            else if(bank_write)partial_data[bank*32+:32]<=s_token;
        end
    end endgenerate
    always @(posedge clk)begin
        if(rst)begin
            count<=0;sequence_active<=0;final_pending<=0;context_id<=0;
            emit_pending<=0;emit_last<=0;emit_count<=0;emit_user<=0;
            m_axis_tokens_tdata<=0;m_axis_tokens_tkeep<=0;m_axis_tokens_tvalid<=0;m_axis_tokens_tlast<=0;m_axis_tokens_tuser<=0;
        end else begin
            if(m_axis_tokens_tvalid&&m_axis_tokens_tready)begin
                m_axis_tokens_tvalid<=0;
                if(m_axis_tokens_tlast)begin sequence_active<=0;final_pending<=0;end
            end
            if(emit_fire)begin
                m_axis_tokens_tdata<=partial_data;
                m_axis_tokens_tkeep<=64'hffffffffffffffff>>(64-emit_count*4);
                m_axis_tokens_tvalid<=1;m_axis_tokens_tlast<=emit_last;m_axis_tokens_tuser<=emit_user;
                emit_pending<=0;
            end
            if(capture)begin
                if(!sequence_active)begin sequence_active<=1;context_id<=s_user;end
                if((s_keep&&count==15)||s_sequence_last)begin
                    emit_pending<=1;emit_last<=s_sequence_last;emit_count<=next_count[4:0];
                    emit_user<=sequence_active?context_id:s_user;count<=0;
                    if(s_sequence_last)final_pending<=1;
                end else count<=next_count[4:0];
            end
        end
    end
endmodule
`default_nettype wire
