`timescale 1ns/1ps
`default_nettype none
// Incremental UTF-8 -> transactional JSON/SSE/Protobuf application chunk.
// RPC binding, generation/model leases and transport framing belong upstream.
module utf8_serialized_chunk #(
    parameter integer USER_WIDTH=16,parameter integer MAX_TEXT_BYTES=16384
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire start_eos,start_replace,input wire [23:0] start_carry,input wire [1:0] start_carry_count,
    input wire [1:0] start_format,input wire [28:0] start_protobuf_field,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,input wire s_axis_text_tlast,
    input wire [USER_WIDTH-1:0] s_axis_text_tuser,input wire s_axis_text_abort,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire result_valid,input wire result_ready,output wire [7:0] result_stage,result_status,
    output wire [23:0] result_carry,output wire [1:0] result_carry_count,output wire [31:0] result_bytes,
    output wire [USER_WIDTH-1:0] result_user,output wire idle
);
    reg active,completion_pending;reg [1:0] format_mode;reg [28:0] protobuf_field;
    reg [23:0] original_carry;reg [1:0] original_count;reg [7:0] serializer_status;
    wire decoder_ready,decoder_result,decoder_idle,serializer_idle,serializer_error;
    wire [7:0] decoder_status,serializer_code;
    wire [23:0] decoder_carry;wire [1:0] decoder_count;wire [31:0] decoder_bytes;
    wire [127:0] text_data;wire [15:0] text_keep;wire [USER_WIDTH-1:0] text_user;
    wire text_valid,text_ready,text_last,text_abort;
    assign start_ready=!rst&&!active&&decoder_ready&&serializer_idle;
    assign result_valid=completion_pending;
    assign result_stage=decoder_status!=0?8'd1:serializer_status!=0?8'd2:8'd0;
    assign result_status=decoder_status!=0?decoder_status:serializer_status;
    assign result_carry=result_status!=0?original_carry:decoder_carry;
    assign result_carry_count=result_status!=0?original_count:decoder_count;
    assign result_bytes=result_status!=0?32'd0:decoder_bytes;
    assign idle=!active&&decoder_idle&&serializer_idle;
    always @(posedge clk)begin
        if(rst)begin active<=0;completion_pending<=0;format_mode<=0;protobuf_field<=0;original_carry<=0;original_count<=0;serializer_status<=0;end
        else begin
            if(start_valid&&start_ready)begin
                active<=1;completion_pending<=0;format_mode<=start_format;protobuf_field<=start_protobuf_field;
                original_carry<=start_carry;original_count<=start_carry_count;serializer_status<=0;
            end
            if(serializer_error&&serializer_status==0)serializer_status<=serializer_code;
            // Observe both completions at a clock edge. A combinational AND
            // can briefly see the decoder's new result with the serializer's
            // old idle value when the final input beat transfers.
            if(active&&decoder_result&&serializer_idle)completion_pending<=1;
            if(result_valid&&result_ready)begin active<=0;completion_pending<=0;end
        end
    end
    utf8_chunk_decoder #(.USER_WIDTH(USER_WIDTH)) decoder(
        .clk(clk),.rst(rst),.start_valid(start_valid&&start_ready),.start_ready(decoder_ready),.start_user(start_user),
        .start_eos(start_eos),.start_replace(start_replace),.start_carry(start_carry),.start_carry_count(start_carry_count),
        .s_axis_text_tdata(s_axis_text_tdata),.s_axis_text_tkeep(s_axis_text_tkeep),.s_axis_text_tvalid(s_axis_text_tvalid),
        .s_axis_text_tready(s_axis_text_tready),.s_axis_text_tlast(s_axis_text_tlast),.s_axis_text_tuser(s_axis_text_tuser),.s_axis_text_abort(s_axis_text_abort),
        .m_axis_text_tdata(text_data),.m_axis_text_tkeep(text_keep),.m_axis_text_tvalid(text_valid),.m_axis_text_tready(text_ready),
        .m_axis_text_tlast(text_last),.m_axis_text_tuser(text_user),.m_axis_text_abort(text_abort),
        .result_valid(decoder_result),.result_ready(result_valid&&result_ready),.result_status(decoder_status),
        .result_carry(decoder_carry),.result_carry_count(decoder_count),.result_bytes(decoder_bytes),.result_user(result_user),.idle(decoder_idle));
    proto_json_serializer #(.USER_WIDTH(USER_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.ABORT_SUPPORT(1)) serializer(
        .clk(clk),.rst(rst),.cfg_format(format_mode),.cfg_protobuf_field(protobuf_field),
        .s_axis_text_tdata(text_data),.s_axis_text_tkeep(text_keep),.s_axis_text_tvalid(text_valid),.s_axis_text_tready(text_ready),
        .s_axis_text_tlast(text_last),.s_axis_text_tuser(text_user),.s_axis_text_abort(text_abort),
        .m_axis_tx_tdata(m_axis_tx_tdata),.m_axis_tx_tkeep(m_axis_tx_tkeep),.m_axis_tx_tvalid(m_axis_tx_tvalid),
        .m_axis_tx_tready(m_axis_tx_tready),.m_axis_tx_tlast(m_axis_tx_tlast),.m_axis_tx_tuser(m_axis_tx_tuser),
        .error_valid(serializer_error),.error_ready(1'b1),.error_code(serializer_code),.error_user(),.idle(serializer_idle));
endmodule
`default_nettype wire
