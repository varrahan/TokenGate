`timescale 1ns/1ps
`default_nettype none
// Complete staged gRPC message -> actual transactional JSON/Protobuf Parser.
// Admission/HTTP validation and transport commit precede descriptor submission.
module grpc_application_decoder #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,
    parameter integer FIFO_DEPTH=16,parameter integer MAX_TEXT_BYTES=16384,parameter integer MAX_FIELD_BYTES=16384
)(
    input wire clk,input wire rst,input wire message_valid,output wire message_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] message_base,input wire [31:0] message_bytes,message_ordinal,
    input wire [USER_WIDTH-1:0] message_user,message_application,input wire [30:0] message_stream,input wire message_protobuf,
    input wire cfg_unlock,input wire cfg_schema_valid,output wire cfg_schema_ready,input wire [3:0] cfg_schema_index,
    input wire [255:0] cfg_schema_key,input wire [5:0] cfg_schema_key_length,input wire cfg_schema_json_enable,
    input wire [28:0] cfg_schema_field,input wire cfg_schema_proto_enable,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire completion_valid,input wire completion_ready,output wire [7:0] completion_status,completion_detail,completion_memory_status,
    output wire [USER_WIDTH-1:0] completion_user,completion_application,output wire [30:0] completion_stream,output wire [31:0] completion_ordinal,
    output wire mem_valid,input wire mem_ready,output wire mem_write,output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,output wire idle
);
    localparam IDLE=0,WAIT=1,RESULT=2;
    reg [1:0] state;reg protobuf_mode,replay_done,parser_done;reg [7:0] replay_status,replay_memory_status,parser_status;
    reg [USER_WIDTH-1:0] context_id,application_id;reg [30:0] stream_id;reg [31:0] ordinal;
    wire replay_start_ready,replay_idle,parser_idle,replay_result_valid;wire [7:0] replay_result_status,replay_result_memory;
    wire [511:0] replay_data;wire [63:0] replay_keep;wire replay_valid,replay_ready,replay_last,replay_abort;wire [USER_WIDTH-1:0] replay_user;
    wire parser_error;wire [7:0] parser_code;wire [USER_WIDTH-1:0] parser_user;
    assign message_ready=!rst&&state==IDLE&&replay_start_ready&&parser_idle&&!cfg_unlock;
    transport_message_replay #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) replay(
        .clk(clk),.rst(rst),.start_valid(message_valid&&message_ready),.start_ready(replay_start_ready),.start_base(message_base),.start_bytes(message_bytes),.start_user(message_application),
        .m_axis_tdata(replay_data),.m_axis_tkeep(replay_keep),.m_axis_tvalid(replay_valid),.m_axis_tready(replay_ready),.m_axis_tlast(replay_last),.m_axis_tuser(replay_user),.m_axis_abort(replay_abort),
        .result_valid(replay_result_valid),.result_ready(state==WAIT&&!replay_done),.result_status(replay_result_status),.result_memory_status(replay_result_memory),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(replay_idle));
    proto_json_decoder #(.USER_WIDTH(USER_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)) parser(
        .clk(clk),.rst(rst),.cfg_protobuf(protobuf_mode),.cfg_unlock(cfg_unlock&&state==IDLE),.cfg_schema_valid(cfg_schema_valid),.cfg_schema_ready(cfg_schema_ready),
        .cfg_schema_index(cfg_schema_index),.cfg_schema_key(cfg_schema_key),.cfg_schema_key_length(cfg_schema_key_length),.cfg_schema_json_enable(cfg_schema_json_enable),.cfg_schema_field(cfg_schema_field),.cfg_schema_proto_enable(cfg_schema_proto_enable),
        .s_axis_rx_tdata(replay_data),.s_axis_rx_tkeep(replay_keep),.s_axis_rx_tvalid(replay_valid),.s_axis_rx_tready(replay_ready),.s_axis_rx_tlast(replay_last),.s_axis_rx_tuser(replay_user),.s_axis_rx_abort(replay_abort),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),.m_axis_text_tready(m_axis_text_tready),.m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),
        .error_valid(parser_error),.error_ready(state==WAIT&&!parser_done),.error_code(parser_code),.error_user(parser_user),.idle(parser_idle));
    assign completion_valid=state==RESULT;
    assign completion_status=replay_status!=0?replay_status:parser_status!=0?8'd3:8'd0;
    assign completion_detail=parser_status;assign completion_memory_status=replay_memory_status;
    assign completion_user=context_id;assign completion_application=application_id;assign completion_stream=stream_id;assign completion_ordinal=ordinal;
    assign idle=state==IDLE&&replay_idle&&parser_idle&&!(message_valid&&message_ready);
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;protobuf_mode<=0;replay_done<=0;parser_done<=0;replay_status<=0;replay_memory_status<=0;parser_status<=0;context_id<=0;application_id<=0;stream_id<=0;ordinal<=0;end
        else case(state)
            IDLE:if(message_valid&&message_ready)begin
                context_id<=message_user;application_id<=message_application;stream_id<=message_stream;ordinal<=message_ordinal;protobuf_mode<=message_protobuf;
                replay_done<=0;parser_done<=0;replay_status<=0;replay_memory_status<=0;parser_status<=0;state<=WAIT;
            end
            WAIT:begin
                if(replay_result_valid&&!replay_done)begin replay_done<=1;replay_status<=replay_result_status;replay_memory_status<=replay_result_memory;end
                if(parser_error&&!parser_done)begin parser_done<=1;parser_status<=parser_code;end
                if(m_axis_text_tvalid&&m_axis_text_tready&&m_axis_text_tlast)parser_done<=1;
                if(replay_done&&parser_done)state<=RESULT;
            end
            RESULT:if(completion_ready)state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
