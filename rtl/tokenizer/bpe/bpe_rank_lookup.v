`timescale 1ns/1ps
`default_nettype none
// Open-addressed, runtime-programmable merge table. Linear probing always
// compares both complete token IDs; a hash collision never becomes a merge.
module bpe_rank_lookup #(
    parameter integer ID_WIDTH=17,
    parameter integer RANK_WIDTH=17,
    parameter integer HASH_ADDR_WIDTH=18,
    parameter integer EXTERNAL_MEMORY=1,
    parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire cfg_unlock,input wire cfg_valid,output wire cfg_ready,
    input wire [HASH_ADDR_WIDTH-1:0] cfg_addr,input wire [71:0] cfg_data,
    input wire req_valid,output wire req_ready,
    input wire [ID_WIDTH-1:0] req_left,input wire [ID_WIDTH-1:0] req_right,
    output wire rsp_valid,input wire rsp_ready,output reg rsp_found,
    output reg [ID_WIDTH-1:0] rsp_merged,output reg [RANK_WIDTH-1:0] rsp_rank,
    output wire idle,
    output reg [7:0] rsp_status,
    input wire [MEMORY_ADDR_WIDTH-1:0] hash_base,
    output wire mem_rd_valid,input wire mem_rd_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_rd_addr,output wire [3:0] mem_rd_bytes,
    input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status
);
    localparam IDLE=0,ISSUE=1,WAIT_DATA=2,RESULT=3,PREPARE_ADDRESS=4,CHECK_ADDRESS=5;
    reg [2:0] state;
    reg [ID_WIDTH-1:0] left_id,right_id;
    reg [HASH_ADDR_WIDTH-1:0] address,probes;
    reg [MEMORY_ADDR_WIDTH-1:0] base_latched;
    reg [63:0] resolved_address;
    reg resolved_good;
    wire ram_ready,ram_valid;
    wire [71:0] ram_data;
    function [31:0] hash_pair(input [ID_WIDTH-1:0] left,input [ID_WIDTH-1:0] right);
        reg [31:0] x;
        begin x=(left*32'h9e3779b1)^(right*32'h85ebca6b); hash_pair=x^(x>>16); end
    endfunction
    wire [63:0] byte_address=64'd9*address+base_latched;
    wire address_good=resolved_address+9<=(64'd1<<MEMORY_ADDR_WIDTH);
    generate if(EXTERNAL_MEMORY)begin: external_hash
        assign cfg_ready=0;
        assign ram_ready=mem_rd_ready && resolved_good;
        assign ram_valid=mem_rsp_valid && state==WAIT_DATA;
        assign ram_data=mem_rsp_data;
        assign mem_rd_valid=!rst && state==ISSUE && resolved_good;
        assign mem_rd_addr=resolved_address[MEMORY_ADDR_WIDTH-1:0];
        assign mem_rd_bytes=9;
        assign mem_rsp_ready=state==WAIT_DATA;
    end else begin: native_hash
    assign mem_rd_valid=0;assign mem_rd_addr=0;assign mem_rd_bytes=0;assign mem_rsp_ready=0;
    programmable_table_ram #(.DATA_WIDTH(72),.ADDR_WIDTH(HASH_ADDR_WIDTH)) merge_hash (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),.cfg_valid(cfg_valid),
        .cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_data(cfg_data),
        .rd_valid(state==ISSUE),.rd_ready(ram_ready),.rd_addr(address),
        .rsp_valid(ram_valid),.rsp_data(ram_data));
    end endgenerate
    assign req_ready=!rst && !cfg_unlock && state==IDLE;
    assign rsp_valid=state==RESULT;
    assign idle=state==IDLE;
    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE;left_id<=0;right_id<=0;address<=0;probes<=0;
            rsp_found<=0;rsp_merged<=0;rsp_rank<=0;rsp_status<=0;base_latched<=0;
            resolved_address<=0;resolved_good<=0;
        end else case(state)
            IDLE: if(req_valid && req_ready) begin
                left_id<=req_left;right_id<=req_right;address<=hash_pair(req_left,req_right);
                probes<=0;rsp_found<=0;rsp_rank<=0;rsp_merged<=0;rsp_status<=0;
                base_latched<=hash_base;state<=EXTERNAL_MEMORY?PREPARE_ADDRESS:ISSUE;
            end
            // Resolve the nine-byte slot, then check its complete extent in a
            // separate clock. No address arithmetic feeds the issue/response CE.
            PREPARE_ADDRESS:begin resolved_address<=byte_address;state<=CHECK_ADDRESS;end
            CHECK_ADDRESS:begin
                resolved_good<=address_good;
                if(!address_good)begin rsp_status<=1;state<=RESULT;end
                else state<=ISSUE;
            end
            ISSUE: if(EXTERNAL_MEMORY && !resolved_good)begin rsp_status<=1;state<=RESULT;end
                   else if(ram_ready) state<=WAIT_DATA;
            WAIT_DATA: if(ram_valid) begin
                if(EXTERNAL_MEMORY && mem_rsp_status!=0)begin rsp_status<=8'h10|mem_rsp_status;state<=RESULT;end
                else if(!ram_data[3*ID_WIDTH+RANK_WIDTH]) state<=RESULT;
                else if(ram_data[0+:ID_WIDTH]==left_id && ram_data[ID_WIDTH+:ID_WIDTH]==right_id) begin
                    rsp_found<=1;rsp_merged<=ram_data[2*ID_WIDTH+:ID_WIDTH];
                    rsp_rank<=ram_data[3*ID_WIDTH+:RANK_WIDTH];state<=RESULT;
                end else if(&probes) state<=RESULT;
                else begin address<=address+1'b1;probes<=probes+1'b1;state<=EXTERNAL_MEMORY?PREPARE_ADDRESS:ISSUE;end
            end
            RESULT: if(rsp_ready) state<=IDLE;
            default: state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
