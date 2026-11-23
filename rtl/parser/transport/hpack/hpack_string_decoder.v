`timescale 1ns/1ps
`default_nettype none
// One HPACK string: H/length prefix followed by exactly the declared octets.
// Decoded bytes are tentative until the separate keep=0/last=1 marker.
// A failed string emits no marker and returns decoded_bytes=0. The parent
// retires its header block; malformed lengths can leave block bytes unread.
module hpack_string_decoder #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_valid,output wire s_ready,
    input wire s_block_last,input wire [USER_WIDTH-1:0] s_user,
    output wire [7:0] m_data,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user,
    output wire rsp_valid,input wire rsp_ready,output reg [7:0] rsp_status,rsp_detail,
    output wire rsp_block_last,output wire [31:0] rsp_encoded_bytes,rsp_decoded_bytes,
    output wire [USER_WIDTH-1:0] rsp_user,output wire idle
);
    localparam IDLE=0,LENGTH=1,RAW=2,RAW_EOF=3,RAW_FINISH=4,HUFFMAN=5,HUFFMAN_FINISH=6,
               DRAIN=7,WAIT_ERROR=8,RESULT=9;
    reg [3:0] state;
    reg huffman,last_seen,payload_failed;
    reg [31:0] remaining,encoded_count,decoded_count;
    reg [USER_WIDTH-1:0] context_id;
    reg raw_valid,raw_keep,raw_last;
    reg [7:0] raw_data;
    wire integer_ready,integer_valid,integer_last;wire [31:0] integer_value;wire [7:0] integer_status;
    wire length_input=state==IDLE||state==LENGTH;
    hpack_integer_decoder #(.USER_WIDTH(USER_WIDTH)) length_decoder(
        .clk(clk),.rst(rst),.s_data(s_data),.s_prefix_bits(4'd7),.s_valid(s_valid&&length_input),.s_ready(integer_ready),
        .s_block_last(s_block_last),.s_user(s_user),.rsp_valid(integer_valid),.rsp_ready(state==LENGTH),
        .rsp_value(integer_value),.rsp_status(integer_status),.rsp_block_last(integer_last),.rsp_user(),.idle());
    wire h_ready,h_valid,h_keep,h_last,h_error;wire [7:0] h_data,h_error_code;
    wire h_output_ready=h_keep?m_ready:(payload_failed?1'b1:m_ready);
    hpack_huffman_decoder #(.USER_WIDTH(USER_WIDTH)) huffman_decoder(
        .clk(clk),.rst(rst),.s_data(s_data),.s_keep(1'b1),.s_valid(s_valid&&state==HUFFMAN),.s_ready(h_ready),
        .s_last(remaining==1||s_block_last),.s_user(s_user),.m_data(h_data),.m_keep(h_keep),.m_valid(h_valid),
        .m_ready(h_output_ready),.m_last(h_last),.m_user(),.error_valid(h_error),.error_ready(state==HUFFMAN||state==HUFFMAN_FINISH),.error_code(h_error_code),.error_user(),.idle());
    assign s_ready=!rst&&(length_input?integer_ready:state==RAW?(!raw_valid||m_ready):state==HUFFMAN?h_ready:state==DRAIN);
    assign m_valid=raw_valid||(h_valid&&(h_keep||!payload_failed));
    assign m_data=raw_valid?raw_data:h_data;
    assign m_keep=raw_valid?raw_keep:h_keep;
    assign m_last=raw_valid?raw_last:h_last;
    assign m_user=context_id;
    assign rsp_valid=state==RESULT;
    assign rsp_block_last=last_seen;
    assign rsp_encoded_bytes=encoded_count;
    assign rsp_decoded_bytes=rsp_status==0?decoded_count:32'd0;
    assign rsp_user=context_id;
    assign idle=state==IDLE&&!raw_valid&&!(s_valid&&s_ready);
    task fail(input [7:0] status,input [7:0] detail);
        begin rsp_status<=status;rsp_detail<=detail;state<=WAIT_ERROR;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;huffman<=0;last_seen<=0;payload_failed<=0;remaining<=0;encoded_count<=0;decoded_count<=0;context_id<=0;
            raw_valid<=0;raw_keep<=0;raw_last<=0;raw_data<=0;rsp_status<=0;rsp_detail<=0;
        end else begin
            if(raw_valid&&m_ready)raw_valid<=0;
            if(m_valid&&m_ready&&m_keep)begin
                decoded_count<=decoded_count+1'b1;
                if(decoded_count==32'hffffffff&&!payload_failed)begin payload_failed<=1;rsp_status<=5;rsp_detail<=0;end
            end
            case(state)
                IDLE:if(s_valid&&s_ready)begin
                    huffman<=s_data[7];context_id<=s_user;last_seen<=s_block_last;payload_failed<=0;
                    encoded_count<=0;decoded_count<=0;rsp_status<=0;rsp_detail<=0;state<=LENGTH;
                end
                LENGTH:if(integer_valid)begin
                    last_seen<=integer_last;remaining<=integer_value;
                    if(integer_status!=0)fail(1,integer_status);
                    else if(integer_value==0)state<=RAW_EOF;
                    else if(integer_last)fail(2,0);
                    else state<=huffman?HUFFMAN:RAW;
                end
                RAW:if(s_valid&&s_ready)begin
                    encoded_count<=encoded_count+1'b1;remaining<=remaining-1'b1;last_seen<=s_block_last;
                    if(s_user!=context_id)begin
                        rsp_status<=4;rsp_detail<=0;state<=s_block_last||remaining==1?WAIT_ERROR:DRAIN;
                    end else begin
                        raw_data<=s_data;raw_keep<=1;raw_last<=0;raw_valid<=1;
                        if(s_block_last&&remaining!=1)fail(2,0);
                        else if(remaining==1)state<=RAW_EOF;
                    end
                end
                RAW_EOF:if(!raw_valid||m_ready)begin raw_data<=0;raw_keep<=0;raw_last<=1;raw_valid<=1;state<=RAW_FINISH;end
                RAW_FINISH:if(raw_valid&&m_ready)state<=RESULT;
                HUFFMAN:if(s_valid&&s_ready)begin
                    encoded_count<=encoded_count+1'b1;remaining<=remaining-1'b1;last_seen<=s_block_last;
                    if(s_user!=context_id)begin payload_failed<=1;rsp_status<=4;rsp_detail<=0;end
                    else if(s_block_last&&remaining!=1&&!payload_failed)begin payload_failed<=1;rsp_status<=2;rsp_detail<=0;end
                    if(remaining==1||s_block_last)state<=HUFFMAN_FINISH;
                end
                DRAIN:if(s_valid&&s_ready)begin
                    encoded_count<=encoded_count+1'b1;remaining<=remaining-1'b1;last_seen<=s_block_last;
                    if(remaining==1||s_block_last)state<=WAIT_ERROR;
                end
                WAIT_ERROR:if(!raw_valid)state<=RESULT;
                RESULT:if(rsp_ready)state<=IDLE;
                default:begin end
            endcase
            if(state==HUFFMAN||state==HUFFMAN_FINISH)begin
                if(h_error)begin if(payload_failed)state<=RESULT;else begin rsp_status<=3;rsp_detail<=h_error_code;state<=RESULT;end end
                else if(h_valid&&h_output_ready&&h_last)state<=RESULT;
            end
        end
    end
endmodule
`default_nettype wire
