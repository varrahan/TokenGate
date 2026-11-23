`timescale 1ns/1ps
`default_nettype none
// Exact, case-sensitive :path lookup. The caller retains the HPACK scratch
// lease through result ACK. Tables and strings are runtime external memory.
module http2_route_lookup #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,input wire start_valid,output wire start_ready,
    input wire [USER_WIDTH-1:0] start_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] query_base,input wire [31:0] query_bytes,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_scratch_base,cfg_table_base,cfg_strings_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_scratch_bytes,cfg_table_bytes,cfg_strings_bytes,
    input wire [31:0] cfg_entries,
    output wire result_valid,input wire result_ready,
    output reg [2:0] result_status,output reg [7:0] result_detail,result_memory_status,
    output reg [USER_WIDTH-1:0] result_user,output reg [15:0] result_application,
    output reg [1:0] result_formats,output reg [31:0] result_message_limit,result_schema_epoch,result_model_epoch,result_entry,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,CHECK=1,META_REQ=2,META_WAIT=3,META_CHECK=4,QUERY_REQ=5,QUERY_WAIT=6,KEY_REQ=7,KEY_WAIT=8,COMPARE=9,NEXT=10,RESULT=11;
    reg [3:0] state;reg [1:0] word_index;
    reg [MEMORY_ADDR_WIDTH-1:0] scratch_base,table_base,strings_base,path_base;
    reg [MEMORY_ADDR_WIDTH:0] scratch_bytes,table_bytes,strings_bytes;
    reg [31:0] entries,path_bytes,entry_index,position;
    reg [255:0] record_data;reg found;
    reg [71:0] query_data,key_data;reg [3:0] chunk;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire [63:0] scratch_end={1'b0,scratch_base}+{1'b0,scratch_bytes};
    wire [63:0] table_end={1'b0,table_base}+{1'b0,table_bytes};
    wire [63:0] strings_end={1'b0,strings_base}+{1'b0,strings_bytes};
    wire [63:0] query_end={1'b0,path_base}+{32'd0,path_bytes};
    wire [63:0] key_end={32'd0,record_data[31:0]}+{32'd0,record_data[63:32]};
    wire config_good=scratch_bytes!=0&&scratch_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        path_bytes!=0&&path_base>=scratch_base&&query_end<=scratch_end&&
        table_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&strings_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&entries<=({8'd0,table_bytes}>>5)&&
        (table_bytes==0||strings_bytes==0||table_end<={1'b0,strings_base}||strings_end<={1'b0,table_base});
    wire record_good=record_data[63:32]!=0&&{32'd0,record_data[31:0]}>={1'b0,strings_base}&&key_end<=strings_end&&
        record_data[95:82]==0&&record_data[81:80]!=0&&record_data[127:96]!=0&&record_data[255:192]==0;
    wire [31:0] remaining=path_bytes-position;
    wire [3:0] next_chunk=remaining>9?4'd9:remaining[3:0];
    wire slot_request=state==META_REQ||state==QUERY_REQ||state==KEY_REQ;
    wire [31:0] metadata_address=table_base+(entry_index<<5)+{27'd0,word_index,3'd0};
    wire [31:0] key_address=record_data[31:0]+position;
    wire [MEMORY_ADDR_WIDTH-1:0] request_address=state==META_REQ?metadata_address[MEMORY_ADDR_WIDTH-1:0]:
        state==QUERY_REQ?path_base+position[MEMORY_ADDR_WIDTH-1:0]:key_address[MEMORY_ADDR_WIDTH-1:0];
    wire [71:0] compare_mask=72'hffffffffffffffffff>>((9-chunk)*8);
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) reader(
        .clk(clk),.rst(rst),.req_valid(slot_request),.req_ready(slot_ready),.req_write(1'b0),.req_addr(request_address),
        .req_bytes(state==META_REQ?4'd8:state==QUERY_REQ?next_chunk:chunk),.req_data(72'd0),
        .result_valid(slot_valid),.result_ready(state==META_WAIT||state==QUERY_WAIT||state==KEY_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign start_ready=!rst&&state==IDLE;
    assign result_valid=!rst&&state==RESULT;
    assign idle=state==IDLE&&slot_idle&&!(start_valid&&start_ready);
    task reject;
        input [2:0] status;input [7:0] detail;input [7:0] memory_status;
        begin
            result_status<=status;result_detail<=detail;result_memory_status<=memory_status;
            result_application<=0;result_formats<=0;result_message_limit<=0;result_schema_epoch<=0;result_model_epoch<=0;result_entry<=0;state<=RESULT;
        end
    endtask
    initial begin if(MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>31||USER_WIDTH<1)$error("Unsupported route lookup widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;word_index<=0;scratch_base<=0;table_base<=0;strings_base<=0;path_base<=0;
            scratch_bytes<=0;table_bytes<=0;strings_bytes<=0;entries<=0;path_bytes<=0;entry_index<=0;position<=0;
            record_data<=0;found<=0;query_data<=0;key_data<=0;chunk<=0;
            result_status<=0;result_detail<=0;result_memory_status<=0;result_user<=0;result_application<=0;result_formats<=0;
            result_message_limit<=0;result_schema_epoch<=0;result_model_epoch<=0;result_entry<=0;
        end else case(state)
            IDLE:if(start_valid&&start_ready)begin
                scratch_base<=cfg_scratch_base;scratch_bytes<=cfg_scratch_bytes;table_base<=cfg_table_base;table_bytes<=cfg_table_bytes;
                strings_base<=cfg_strings_base;strings_bytes<=cfg_strings_bytes;entries<=cfg_entries;path_base<=query_base;path_bytes<=query_bytes;
                result_user<=start_user;result_status<=0;result_detail<=0;result_memory_status<=0;result_application<=0;result_formats<=0;
                result_message_limit<=0;result_schema_epoch<=0;result_model_epoch<=0;result_entry<=0;
                entry_index<=0;position<=0;found<=0;word_index<=0;state<=CHECK;
            end
            CHECK:if(!config_good)reject(2,1,0);else if(entries==0)reject(1,0,0);else state<=META_REQ;
            META_REQ:if(slot_ready)state<=META_WAIT;
            META_WAIT:if(slot_valid)begin
                if(slot_status!=0)reject(3,1,slot_status);
                else begin
                    case(word_index)
                        0:record_data[63:0]<=slot_data[63:0];
                        1:record_data[127:64]<=slot_data[63:0];
                        2:record_data[191:128]<=slot_data[63:0];
                        3:record_data[255:192]<=slot_data[63:0];
                    endcase
                    word_index<=word_index+1'b1;state<=word_index==3?META_CHECK:META_REQ;
                end
            end
            META_CHECK:if(!record_good)reject(2,2,0);
                else if(record_data[63:32]!=path_bytes)state<=NEXT;
                else begin position<=0;state<=QUERY_REQ;end
            QUERY_REQ:if(slot_ready)begin chunk<=next_chunk;state<=QUERY_WAIT;end
            QUERY_WAIT:if(slot_valid)begin
                if(slot_status!=0)reject(3,2,slot_status);
                else begin query_data<=slot_data;state<=KEY_REQ;end
            end
            KEY_REQ:if(slot_ready)state<=KEY_WAIT;
            KEY_WAIT:if(slot_valid)begin
                if(slot_status!=0)reject(3,3,slot_status);
                else begin key_data<=slot_data;state<=COMPARE;end
            end
            COMPARE:if(((key_data^query_data)&compare_mask)!=0)state<=NEXT;
                else if(position+chunk==path_bytes)begin
                    if(found)reject(4,0,0);
                    else begin
                        found<=1;result_application<=record_data[79:64];result_formats<=record_data[81:80];result_message_limit<=record_data[127:96];
                        result_schema_epoch<=record_data[159:128];result_model_epoch<=record_data[191:160];result_entry<=entry_index;state<=NEXT;
                    end
                end else begin position<=position+chunk;state<=QUERY_REQ;end
            NEXT:if(entry_index+1==entries)begin
                if(!found)reject(1,0,0);else state<=RESULT;
            end else begin entry_index<=entry_index+1'b1;word_index<=0;state<=META_REQ;end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
