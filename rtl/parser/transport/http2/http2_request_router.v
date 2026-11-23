`timescale 1ns/1ps
`default_nettype none
// Field validation plus exact runtime service-path lookup. This returns a
// tentative admission candidate; the stream controller owns OPEN/packet commit.
module http2_request_router #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire [30:0] start_stream,input wire start_trailers,input wire start_end_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_scratch_base,cfg_route_base,cfg_route_strings_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_scratch_bytes,cfg_route_bytes,cfg_route_strings_bytes,input wire [31:0] cfg_routes,
    input wire header_valid,output wire header_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] header_name_base,header_value_base,
    input wire [31:0] header_name_bytes,header_value_bytes,input wire [1:0] header_representation,input wire [USER_WIDTH-1:0] header_user,
    output wire field_valid,input wire field_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] field_name_base,field_value_base,
    output wire [31:0] field_name_bytes,field_value_bytes,output wire [1:0] field_representation,
    output wire [3:0] field_kind,output wire [USER_WIDTH-1:0] field_user,
    input wire finish_valid,output wire finish_ready,input wire finish_failed,
    output wire result_valid,input wire result_ready,output wire result_admissible,
    output wire [2:0] result_status,output wire [7:0] result_detail,result_memory_status,
    output wire [9:0] result_http_status,output wire [1:0] result_format,
    output wire result_identity_encoding,result_content_length_valid,output wire [63:0] result_content_length,
    output wire result_timeout_valid,output wire [26:0] result_timeout_value,output wire [2:0] result_timeout_unit,
    output wire [31:0] result_headers,output wire [USER_WIDTH-1:0] result_user,
    output wire [30:0] result_stream,output wire result_trailers,result_end_stream,
    output reg [2:0] result_route_status,output reg [7:0] result_route_detail,result_route_memory_status,
    output reg [15:0] result_application,output reg [1:0] result_formats,
    output reg [31:0] result_message_limit,result_schema_epoch,result_model_epoch,result_route_entry,
    output wire [1:0] mem_valid,input wire [1:0] mem_ready,output wire [1:0] mem_write,
    output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [7:0] mem_bytes,output wire [143:0] mem_data,
    input wire [1:0] mem_rsp_valid,output wire [1:0] mem_rsp_ready,input wire [143:0] mem_rsp_data,input wire [15:0] mem_rsp_status,
    output wire idle
);
    reg [MEMORY_ADDR_WIDTH-1:0] scratch_base,route_base,strings_base;
    reg [MEMORY_ADDR_WIDTH:0] scratch_bytes,route_bytes,strings_bytes;
    reg [31:0] routes;
    wire checked_field_valid,checked_field_ready,checker_idle,lookup_idle;
    reg handling_field,field_consumed,lookup_started,lookup_done,path_field;
    wire lookup_start_valid=handling_field&&path_field&&!lookup_started;
    wire lookup_start_ready,lookup_result_valid;
    wire lookup_result_ready=handling_field&&path_field&&!lookup_done;
    wire [2:0] lookup_status;wire [7:0] lookup_detail,lookup_memory_status;
    wire [15:0] lookup_application;wire [1:0] lookup_formats;
    wire [31:0] lookup_limit,lookup_schema,lookup_model,lookup_entry;
    assign field_valid=checked_field_valid&&handling_field&&!field_consumed;
    assign checked_field_ready=handling_field&&field_consumed&&lookup_done;
    assign idle=checker_idle&&lookup_idle&&!handling_field;
    assign result_admissible=result_status==0&&(result_trailers||
        result_route_status==0&&result_format<2&&result_formats[result_format]);
    http2_request_headers #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.USER_WIDTH(USER_WIDTH)) validator(
        .clk(clk),.rst(rst),.start_valid(start_valid),.start_ready(start_ready),.start_user(start_user),.start_stream(start_stream),
        .start_trailers(start_trailers),.start_end_stream(start_end_stream),.cfg_scratch_base(cfg_scratch_base),.cfg_scratch_bytes(cfg_scratch_bytes),
        .header_valid(header_valid),.header_ready(header_ready),.header_name_base(header_name_base),.header_value_base(header_value_base),
        .header_name_bytes(header_name_bytes),.header_value_bytes(header_value_bytes),.header_representation(header_representation),.header_user(header_user),
        .field_valid(checked_field_valid),.field_ready(checked_field_ready),.field_name_base(field_name_base),.field_value_base(field_value_base),
        .field_name_bytes(field_name_bytes),.field_value_bytes(field_value_bytes),.field_representation(field_representation),.field_kind(field_kind),.field_user(field_user),
        .finish_valid(finish_valid),.finish_ready(finish_ready),.finish_failed(finish_failed),
        .result_valid(result_valid),.result_ready(result_ready),.result_status(result_status),.result_detail(result_detail),.result_memory_status(result_memory_status),
        .result_http_status(result_http_status),.result_format(result_format),.result_identity_encoding(result_identity_encoding),
        .result_content_length_valid(result_content_length_valid),.result_content_length(result_content_length),.result_timeout_valid(result_timeout_valid),
        .result_timeout_value(result_timeout_value),.result_timeout_unit(result_timeout_unit),.result_headers(result_headers),.result_user(result_user),
        .result_stream(result_stream),.result_trailers(result_trailers),.result_end_stream(result_end_stream),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),
        .mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(checker_idle));
    http2_route_lookup #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.USER_WIDTH(USER_WIDTH)) lookup(
        .clk(clk),.rst(rst),.start_valid(lookup_start_valid),.start_ready(lookup_start_ready),.start_user(field_user),
        .query_base(field_value_base),.query_bytes(field_value_bytes),.cfg_scratch_base(scratch_base),.cfg_scratch_bytes(scratch_bytes),
        .cfg_table_base(route_base),.cfg_table_bytes(route_bytes),.cfg_strings_base(strings_base),.cfg_strings_bytes(strings_bytes),.cfg_entries(routes),
        .result_valid(lookup_result_valid),.result_ready(lookup_result_ready),.result_status(lookup_status),.result_detail(lookup_detail),.result_memory_status(lookup_memory_status),
        .result_user(),.result_application(lookup_application),.result_formats(lookup_formats),.result_message_limit(lookup_limit),.result_schema_epoch(lookup_schema),.result_model_epoch(lookup_model),.result_entry(lookup_entry),
        .mem_valid(mem_valid[1]),.mem_ready(mem_ready[1]),.mem_write(mem_write[1]),.mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[4+:4]),.mem_data(mem_data[72+:72]),
        .mem_rsp_valid(mem_rsp_valid[1]),.mem_rsp_ready(mem_rsp_ready[1]),.mem_rsp_data(mem_rsp_data[72+:72]),.mem_rsp_status(mem_rsp_status[8+:8]),.idle(lookup_idle));
    always @(posedge clk)begin
        if(rst)begin
            scratch_base<=0;route_base<=0;strings_base<=0;scratch_bytes<=0;route_bytes<=0;strings_bytes<=0;routes<=0;
            handling_field<=0;field_consumed<=0;lookup_started<=0;lookup_done<=0;path_field<=0;
            result_route_status<=1;result_route_detail<=0;result_route_memory_status<=0;result_application<=0;result_formats<=0;
            result_message_limit<=0;result_schema_epoch<=0;result_model_epoch<=0;result_route_entry<=0;
        end else begin
            if(start_valid&&start_ready)begin
                scratch_base<=cfg_scratch_base;scratch_bytes<=cfg_scratch_bytes;route_base<=cfg_route_base;route_bytes<=cfg_route_bytes;
                strings_base<=cfg_route_strings_base;strings_bytes<=cfg_route_strings_bytes;routes<=cfg_routes;
                result_route_status<=1;result_route_detail<=0;result_route_memory_status<=0;result_application<=0;result_formats<=0;
                result_message_limit<=0;result_schema_epoch<=0;result_model_epoch<=0;result_route_entry<=0;
            end
            if(!handling_field&&checked_field_valid)begin
                handling_field<=1;field_consumed<=0;lookup_started<=0;path_field<=field_kind==3;lookup_done<=field_kind!=3;
            end
            if(field_valid&&field_ready)field_consumed<=1;
            if(lookup_start_valid&&lookup_start_ready)lookup_started<=1;
            if(lookup_result_valid&&lookup_result_ready)begin
                lookup_done<=1;result_route_status<=lookup_status;result_route_detail<=lookup_detail;result_route_memory_status<=lookup_memory_status;
                result_application<=lookup_application;result_formats<=lookup_formats;result_message_limit<=lookup_limit;
                result_schema_epoch<=lookup_schema;result_model_epoch<=lookup_model;result_route_entry<=lookup_entry;
            end
            if(checked_field_valid&&checked_field_ready)handling_field<=0;
        end
    end
endmodule
`default_nettype wire
