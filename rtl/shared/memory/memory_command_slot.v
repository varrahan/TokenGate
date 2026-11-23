`timescale 1ns/1ps
`default_nettype none
// One transaction, including its response, owned independently of a caller's
// control state. A caller abandoning work must consume the result before reset.
module memory_command_slot #(parameter integer MEMORY_ADDR_WIDTH=23)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire req_write,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_addr,input wire [3:0] req_bytes,input wire [71:0] req_data,
    output wire result_valid,input wire result_ready,output reg [71:0] result_data,output reg [7:0] result_status,
    output wire mem_valid,input wire mem_ready,output reg mem_write,
    output reg [MEMORY_ADDR_WIDTH-1:0] mem_addr,output reg [3:0] mem_bytes,output reg [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam EMPTY=0,ISSUE=1,WAIT_DATA=2,RESULT=3;
    reg [1:0] state;
    assign req_ready=!rst&&state==EMPTY;
    assign mem_valid=!rst&&state==ISSUE;
    assign mem_rsp_ready=state==WAIT_DATA;
    assign result_valid=state==RESULT;
    assign idle=state==EMPTY;
    always @(posedge clk)begin
        if(rst)begin state<=EMPTY;mem_write<=0;mem_addr<=0;mem_bytes<=0;mem_data<=0;result_data<=0;result_status<=0;end
        else case(state)
            EMPTY:if(req_valid&&req_ready)begin
                mem_write<=req_write;mem_addr<=req_addr;mem_bytes<=req_bytes;mem_data<=req_data;state<=ISSUE;
            end
            ISSUE:if(mem_ready)state<=WAIT_DATA;
            WAIT_DATA:if(mem_rsp_valid)begin result_data<=mem_rsp_data;result_status<=mem_rsp_status;state<=RESULT;end
            RESULT:if(result_ready)state<=EMPTY;
            default:state<=EMPTY;
        endcase
    end
endmodule
`default_nettype wire
