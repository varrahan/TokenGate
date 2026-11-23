`timescale 1ns/1ps
`default_nettype none
// HPACK prefix integer, with explicit 32-bit value and encoded-length limits.
// Continuation chunks occupy disjoint bit slices; a separate sum stage adds
// the captured prefix mask, avoiding a barrel shift plus carry chain per byte.
// s_block_last marks END_HEADERS, not an arbitrary DATA/CONTINUATION boundary.
module hpack_integer_decoder #(
    parameter integer USER_WIDTH=16,parameter integer MAX_CONTINUATION_BYTES=5
)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire [3:0] s_prefix_bits,input wire s_valid,output wire s_ready,
    input wire s_block_last,input wire [USER_WIDTH-1:0] s_user,
    output wire rsp_valid,input wire rsp_ready,output reg [31:0] rsp_value,output reg [7:0] rsp_status,
    output reg rsp_block_last,output wire [USER_WIDTH-1:0] rsp_user,output wire idle
);
    localparam IDLE=0,CONTINUATION=1,SUM=2,RESULT=3;
    reg [1:0] state;
    reg [3:0] continuation_count;
    reg [31:0] payload;
    reg [7:0] prefix_mask;
    reg saved_last;
    reg [USER_WIDTH-1:0] context_id;
    wire [8:0] first_mask=(9'd1<<s_prefix_bits)-1'b1;
    wire [8:0] first_value={1'b0,s_data}&first_mask;
    wire payload_overflow=(continuation_count==4&&s_data[6:4]!=0)||(continuation_count>4&&s_data[6:0]!=0);
    wire [32:0] sum_value={1'b0,payload}+{25'd0,prefix_mask};
    assign s_ready=!rst&&(state==IDLE||state==CONTINUATION);
    assign rsp_valid=state==RESULT;
    assign rsp_user=context_id;
    assign idle=state==IDLE&&!(s_valid&&s_ready);
    task finish(input [31:0] value,input [7:0] status,input last);
        begin rsp_value<=status==0?value:32'd0;rsp_status<=status;rsp_block_last<=last;state<=RESULT;end
    endtask
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;continuation_count<=0;payload<=0;prefix_mask<=0;saved_last<=0;context_id<=0;rsp_value<=0;rsp_status<=0;rsp_block_last<=0;end
        else case(state)
            IDLE:if(s_valid&&s_ready)begin
                context_id<=s_user;
                if(s_prefix_bits<1||s_prefix_bits>8)finish(0,3,s_block_last);
                else if(first_value<first_mask)finish({23'd0,first_value},0,s_block_last);
                else if(s_block_last)finish(0,2,1'b1);
                else begin prefix_mask<=first_mask[7:0];payload<=0;continuation_count<=0;state<=CONTINUATION;end
            end
            CONTINUATION:if(s_valid&&s_ready)begin
                if(s_user!=context_id)finish(0,4,s_block_last);
                else if(payload_overflow)finish(0,1,s_block_last);
                else begin
                    case(continuation_count)
                        0:payload[6:0]<=s_data[6:0];
                        1:payload[13:7]<=s_data[6:0];
                        2:payload[20:14]<=s_data[6:0];
                        3:payload[27:21]<=s_data[6:0];
                        4:payload[31:28]<=s_data[3:0];
                        default:begin end
                    endcase
                    continuation_count<=continuation_count+1'b1;
                    if(!s_data[7])begin saved_last<=s_block_last;state<=SUM;end
                    else if(s_block_last)finish(0,2,1'b1);
                    else if(continuation_count+1>=MAX_CONTINUATION_BYTES)finish(0,5,1'b0);
                end
            end
            SUM:finish(sum_value[31:0],sum_value[32]?8'd1:8'd0,saved_last);
            RESULT:if(rsp_ready)state<=IDLE;
        endcase
    end
    initial if(MAX_CONTINUATION_BYTES<1||MAX_CONTINUATION_BYTES>9)$error("Unsupported HPACK integer length limit");
endmodule
`default_nettype wire
