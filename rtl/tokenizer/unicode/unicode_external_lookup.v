`timescale 1ns/1ps
`default_nettype none
// Packed programmable classes in external memory: four 2-bit scalar classes
// per byte. Variable-latency request/response; invalid scalars never reach AXI.
module unicode_external_lookup #(
    parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,input wire cfg_unlock,
    input wire [MEMORY_ADDR_WIDTH-1:0] class_base,
    input wire req_valid,output wire req_ready,input wire [20:0] req_codepoint,
    output wire rsp_valid,input wire rsp_ready,output reg [1:0] rsp_class,output reg [7:0] rsp_status,
    output wire mem_rd_valid,input wire mem_rd_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_rd_addr,output wire [3:0] mem_rd_bytes,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,ISSUE=1,WAIT_DATA=2,RESULT=3;
    reg [1:0] state,lane;
    reg [MEMORY_ADDR_WIDTH-1:0] address;
    wire [63:0] byte_address={43'd0,req_codepoint}/4+class_base;
    wire scalar_good=req_codepoint<=21'h10ffff && !(req_codepoint>=21'hd800&&req_codepoint<=21'hdfff);
    assign req_ready=!rst && !cfg_unlock && state==IDLE;
    assign rsp_valid=state==RESULT;
    assign mem_rd_valid=!rst && state==ISSUE;
    assign mem_rd_addr=address;
    assign mem_rd_bytes=1;
    assign mem_rsp_ready=state==WAIT_DATA;
    assign idle=state==IDLE;
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;lane<=0;address<=0;rsp_class<=0;rsp_status<=0;end
        else case(state)
            IDLE:if(req_valid&&req_ready)begin
                lane<=req_codepoint[1:0];address<=byte_address[MEMORY_ADDR_WIDTH-1:0];rsp_class<=0;rsp_status<=0;
                if(!scalar_good)begin rsp_status<=1;state<=RESULT;end
                else if(byte_address>=(64'd1<<MEMORY_ADDR_WIDTH))begin rsp_status<=2;state<=RESULT;end
                else state<=ISSUE;
            end
            ISSUE:if(mem_rd_ready)state<=WAIT_DATA;
            WAIT_DATA:if(mem_rsp_valid)begin
                if(mem_rsp_status!=0)rsp_status<=8'h10|mem_rsp_status;
                else rsp_class<=mem_rsp_data[lane*2+:2];
                state<=RESULT;
            end
            RESULT:if(rsp_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
