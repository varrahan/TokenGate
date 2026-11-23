`timescale 1ns/1ps
`default_nettype none
// Framing and semantic payload state are committed under one record marker.
// Owns bytes 0..63 of the connection record. Stream lifecycle/flow-control
// application, HPACK buffering and gRPC assembly are downstream responsibilities.
module http2_transport_ingress #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,parameter integer RECORD_SHIFT=8
)(
    input wire clk,input wire rst,input wire admit_packets,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
    input wire command_valid,output wire command_ready,input wire [1:0] command_op,input wire [USER_WIDTH-1:0] command_user,
    input wire command_server_role,command_allow_push,input wire [23:0] command_max_frame_bytes,
    input wire [511:0] s_axis_rx_tdata,input wire [63:0] s_axis_rx_tkeep,input wire s_axis_rx_tvalid,output wire s_axis_rx_tready,
    input wire s_axis_rx_tlast,input wire [USER_WIDTH-1:0] s_axis_rx_tuser,
    output wire event_valid,input wire event_ready,output wire [3:0] event_kind,output wire [7:0] event_data,
    output wire [31:0] event_arg0,event_arg1,output wire [23:0] event_length,output wire [7:0] event_type,event_flags,
    output wire [30:0] event_stream,output wire [USER_WIDTH-1:0] event_user,
    output wire rsp_valid,input wire rsp_ready,output wire rsp_is_command,output wire [1:0] rsp_command_op,
    output wire [7:0] rsp_status,rsp_detail,rsp_memory_status,output wire [31:0] rsp_http2_error,output wire [USER_WIDTH-1:0] rsp_user,
    output wire recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire mem_valid,input wire mem_ready,output wire mem_write,output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,output wire [71:0] mem_data,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,output wire idle
);
    wire raw_valid,raw_ready,raw_last;wire [1:0] raw_kind;wire [7:0] raw_data,raw_type,raw_flags;wire [23:0] raw_length;
    wire [30:0] raw_stream;wire [31:0] raw_error;wire [USER_WIDTH-1:0] raw_user;
    wire aux_start_valid,aux_start_ready,aux_server_role,aux_finish_valid,aux_result_valid,aux_result_ready,aux_failed,base_idle,payload_idle;
    wire [255:0] aux_restore,aux_save;wire [USER_WIDTH-1:0] aux_user;wire [31:0] aux_error;wire [7:0] aux_detail;
    http2_connection_ingress #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.RECORD_SHIFT(RECORD_SHIFT),.AUX_STATE(1)) scheduler(
        .clk(clk),.rst(rst),.admit_packets(admit_packets),.cfg_context_base(cfg_context_base),.cfg_context_bytes(cfg_context_bytes),
        .command_valid(command_valid),.command_ready(command_ready),.command_op(command_op),.command_user(command_user),.command_server_role(command_server_role),.command_allow_push(command_allow_push),.command_max_frame_bytes(command_max_frame_bytes),
        .command_aux_initial(256'd0),
        .s_axis_rx_tdata(s_axis_rx_tdata),.s_axis_rx_tkeep(s_axis_rx_tkeep),.s_axis_rx_tvalid(s_axis_rx_tvalid),.s_axis_rx_tready(s_axis_rx_tready),.s_axis_rx_tlast(s_axis_rx_tlast),.s_axis_rx_tuser(s_axis_rx_tuser),
        .event_valid(raw_valid),.event_ready(raw_ready),.event_kind(raw_kind),.event_data(raw_data),.event_length(raw_length),.event_type(raw_type),.event_flags(raw_flags),.event_stream(raw_stream),.event_payload_last(raw_last),.event_error(raw_error),.event_user(raw_user),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_is_command(rsp_is_command),.rsp_command_op(rsp_command_op),.rsp_status(rsp_status),.rsp_detail(rsp_detail),.rsp_memory_status(rsp_memory_status),.rsp_http2_error(rsp_http2_error),.rsp_user(rsp_user),
        .recovery_required(recovery_required),.recovery_address(recovery_address),.mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),.mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(base_idle),
        .aux_start_valid(aux_start_valid),.aux_start_ready(aux_start_ready),.aux_restore(aux_restore),.aux_user(aux_user),.aux_server_role(aux_server_role),.aux_finish_valid(aux_finish_valid),
        .aux_result_valid(aux_result_valid),.aux_result_ready(aux_result_ready),.aux_save(aux_save),.aux_failed(aux_failed),.aux_error(aux_error),.aux_detail(aux_detail));
    http2_payload_decoder #(.USER_WIDTH(USER_WIDTH)) payload(
        .clk(clk),.rst(rst),.start_valid(aux_start_valid),.start_ready(aux_start_ready),.start_user(aux_user),.cfg_server_role(aux_server_role),.cfg_state(aux_restore),
        .s_valid(raw_valid),.s_ready(raw_ready),.s_kind(raw_kind),.s_data(raw_data),.s_length(raw_length),.s_type(raw_type),.s_flags(raw_flags),.s_stream(raw_stream),.s_payload_last(raw_last),.s_error(raw_error),.s_user(raw_user),
        .m_valid(event_valid),.m_ready(event_ready),.m_kind(event_kind),.m_data(event_data),.m_arg0(event_arg0),.m_arg1(event_arg1),.m_length(event_length),.m_type(event_type),.m_flags(event_flags),.m_stream(event_stream),.m_user(event_user),
        .finish_valid(aux_finish_valid),.result_valid(aux_result_valid),.result_ready(aux_result_ready),.result_state(aux_save),.result_failed(aux_failed),.result_error(aux_error),.result_detail(aux_detail),.idle(payload_idle));
    assign idle=base_idle&&payload_idle;
endmodule
`default_nettype wire
