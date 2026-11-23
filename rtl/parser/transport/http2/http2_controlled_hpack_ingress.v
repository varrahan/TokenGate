`timescale 1ns/1ps
`default_nettype none
// Packet -> semantic DATA/control and decoded HPACK fields. Owns connection
// record bytes 0..159; all progress/dictionary counters share one commit.
module http2_controlled_hpack_ingress #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,parameter integer RECORD_SHIFT=8,parameter integer BLOCK_START_PORT=0
)(
    input wire clk,input wire rst,input wire admit_packets,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
    input wire command_valid,output wire command_ready,input wire [1:0] command_op,input wire [USER_WIDTH-1:0] command_user,
    input wire command_server_role,command_allow_push,input wire [23:0] command_max_frame_bytes,
    input wire [MEMORY_ADDR_WIDTH-1:0] command_buffer_base,command_table_base,command_scratch_base,
    input wire [MEMORY_ADDR_WIDTH:0] command_buffer_bytes,command_table_bytes,command_scratch_bytes,
    input wire [31:0] command_hpack_maximum,command_hpack_allowed,command_header_list_limit,command_required_maximum,input wire command_required_update,
    input wire [511:0] s_axis_rx_tdata,input wire [63:0] s_axis_rx_tkeep,input wire s_axis_rx_tvalid,output wire s_axis_rx_tready,
    input wire s_axis_rx_tlast,input wire [USER_WIDTH-1:0] s_axis_rx_tuser,
    output wire event_valid,input wire event_ready,output wire [3:0] event_kind,output wire [7:0] event_data,output wire [31:0] event_arg0,event_arg1,
    output wire [23:0] event_length,output wire [7:0] event_type,event_flags,output wire [30:0] event_stream,output wire [USER_WIDTH-1:0] event_user,
    output wire header_valid,input wire header_ready,output wire [MEMORY_ADDR_WIDTH-1:0] header_name_base,header_value_base,
    output wire [31:0] header_name_bytes,header_value_bytes,output wire [1:0] header_representation,output wire [USER_WIDTH-1:0] header_user,
    output wire block_start_valid,input wire block_start_ready,output wire [30:0] block_start_stream,block_start_promised_stream,
    output wire [7:0] block_start_type,block_start_flags,output wire [USER_WIDTH-1:0] block_start_user,
    output wire block_valid,input wire block_ready,output wire [30:0] block_stream,block_promised_stream,output wire [7:0] block_type,block_flags,
    output wire [31:0] block_headers,block_list_bytes,output wire [USER_WIDTH-1:0] block_user,
    output wire rsp_valid,input wire rsp_ready,output wire rsp_is_command,output wire [1:0] rsp_command_op,
    output wire [7:0] rsp_status,rsp_detail,rsp_memory_status,output wire [31:0] rsp_http2_error,output wire [USER_WIDTH-1:0] rsp_user,
    output wire recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire [3:0] mem_valid,input wire [3:0] mem_ready,output wire [3:0] mem_write,output wire [4*MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [15:0] mem_bytes,output wire [287:0] mem_data,input wire [3:0] mem_rsp_valid,output wire [3:0] mem_rsp_ready,
    input wire [287:0] mem_rsp_data,input wire [31:0] mem_rsp_status,output wire idle
,
    output wire  flow_event_valid,
    input wire  flow_event_ready,
    output wire [3:0] flow_event_kind,
    output wire [7:0] flow_event_data,
    output wire [31:0] flow_event_arg0,
    output wire [31:0] flow_event_arg1,
    output wire [23:0] flow_event_length,
    output wire [7:0] flow_event_type,
    output wire [7:0] flow_event_flags,
    output wire [30:0] flow_event_stream,
    output wire [USER_WIDTH-1:0] flow_event_user
);
    localparam [1023:0] UPDATE_MASK=(1024'hffffffff<<480)|(1024'hffffffff<<576)|(1024'hffffffff<<608)|(1024'd1<<640);
    wire [31:0] c_buffer_base=command_buffer_base,c_buffer_bytes=command_buffer_bytes,c_table_base=command_table_base,c_table_bytes=command_table_bytes,c_scratch_base=command_scratch_base,c_scratch_bytes=command_scratch_bytes;
    wire [767:0] initial_header_state={352'd0,31'd0,command_required_update,command_required_maximum,command_header_list_limit,32'd0,32'd0,command_hpack_allowed,command_hpack_maximum,c_scratch_bytes,c_scratch_base,c_table_bytes,c_table_base,c_buffer_bytes,c_buffer_base};
    wire raw_valid,raw_ready,raw_last;wire [1:0] raw_kind;wire [7:0] raw_data,raw_type,raw_flags;wire [23:0] raw_length;wire [30:0] raw_stream;wire [31:0] raw_error;wire [USER_WIDTH-1:0] raw_user;
    wire sem_valid,sem_ready;wire [3:0] sem_kind;wire [7:0] sem_data,sem_type,sem_flags;wire [31:0] sem_arg0,sem_arg1;wire [23:0] sem_length;wire [30:0] sem_stream;wire [USER_WIDTH-1:0] sem_user;
    wire aux_start_valid,aux_start_ready,aux_server_role,aux_finish_valid,aux_result_valid,aux_result_ready,base_idle,payload_idle,dispatch_idle;
    wire payload_start_ready,dispatch_start_ready,payload_result_valid,dispatch_result_valid,payload_failed,dispatch_failed;
    wire [1023:0] aux_restore,aux_save;wire [255:0] payload_save;wire [767:0] dispatch_save;wire [USER_WIDTH-1:0] aux_user;wire [31:0] payload_error,dispatch_error;wire [7:0] payload_detail,dispatch_detail;
    assign aux_start_ready=payload_start_ready&&dispatch_start_ready;
    assign aux_result_valid=payload_result_valid&&dispatch_result_valid;
    assign aux_save={dispatch_save,payload_save};
    http2_connection_ingress #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.RECORD_SHIFT(RECORD_SHIFT),.AUX_STATE(1),.AUX_BITS(1024),.AUX_UPDATE(1),.AUX_UPDATE_MASK(UPDATE_MASK)) scheduler(
        .clk(clk),.rst(rst),.admit_packets(admit_packets),.cfg_context_base(cfg_context_base),.cfg_context_bytes(cfg_context_bytes),
        .command_valid(command_valid),.command_ready(command_ready),.command_op(command_op),.command_user(command_user),.command_server_role(command_server_role),.command_allow_push(command_allow_push),.command_max_frame_bytes(command_max_frame_bytes),.command_aux_initial({initial_header_state,256'd0}),
        .s_axis_rx_tdata(s_axis_rx_tdata),.s_axis_rx_tkeep(s_axis_rx_tkeep),.s_axis_rx_tvalid(s_axis_rx_tvalid),.s_axis_rx_tready(s_axis_rx_tready),.s_axis_rx_tlast(s_axis_rx_tlast),.s_axis_rx_tuser(s_axis_rx_tuser),
        .event_valid(raw_valid),.event_ready(raw_ready),.event_kind(raw_kind),.event_data(raw_data),.event_length(raw_length),.event_type(raw_type),.event_flags(raw_flags),.event_stream(raw_stream),.event_payload_last(raw_last),.event_error(raw_error),.event_user(raw_user),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_is_command(rsp_is_command),.rsp_command_op(rsp_command_op),.rsp_status(rsp_status),.rsp_detail(rsp_detail),.rsp_memory_status(rsp_memory_status),.rsp_http2_error(rsp_http2_error),.rsp_user(rsp_user),
        .recovery_required(recovery_required),.recovery_address(recovery_address),.mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),.mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(base_idle),
        .aux_start_valid(aux_start_valid),.aux_start_ready(aux_start_ready),.aux_restore(aux_restore),.aux_user(aux_user),.aux_server_role(aux_server_role),.aux_finish_valid(aux_finish_valid),
        .aux_result_valid(aux_result_valid),.aux_result_ready(aux_result_ready),.aux_save(aux_save),.aux_failed(payload_failed||dispatch_failed),.aux_error(payload_failed?payload_error:dispatch_error),.aux_detail(payload_failed?payload_detail:dispatch_detail));
    http2_payload_decoder #(.USER_WIDTH(USER_WIDTH)) payload(
        .clk(clk),.rst(rst),.start_valid(aux_start_valid&&dispatch_start_ready),.start_ready(payload_start_ready),.start_user(aux_user),.cfg_server_role(aux_server_role),.cfg_state(aux_restore[255:0]),
        .s_valid(raw_valid),.s_ready(raw_ready),.s_kind(raw_kind),.s_data(raw_data),.s_length(raw_length),.s_type(raw_type),.s_flags(raw_flags),.s_stream(raw_stream),.s_payload_last(raw_last),.s_error(raw_error),.s_user(raw_user),
        .m_valid(sem_valid),.m_ready(sem_ready),.m_kind(sem_kind),.m_data(sem_data),.m_arg0(sem_arg0),.m_arg1(sem_arg1),.m_length(sem_length),.m_type(sem_type),.m_flags(sem_flags),.m_stream(sem_stream),.m_user(sem_user),
        .finish_valid(aux_finish_valid),.result_valid(payload_result_valid),.result_ready(aux_result_ready&&dispatch_result_valid),.result_state(payload_save),.result_failed(payload_failed),.result_error(payload_error),.result_detail(payload_detail),.idle(payload_idle));
    http2_header_dispatch #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.USER_WIDTH(USER_WIDTH),.BLOCK_START_PORT(BLOCK_START_PORT)) dispatcher(
    .clk(clk),
    .rst(rst),
    .start_valid(aux_start_valid&&payload_start_ready),
    .start_ready(dispatch_start_ready),
    .start_user(aux_user),
    .cfg_state(aux_restore[1023:256]),
    .s_valid(dispatch_event_valid),
    .s_ready(dispatch_event_ready),
    .s_kind(dispatch_event_kind),
    .s_data(dispatch_event_data),
    .s_arg0(dispatch_event_arg0),
    .s_arg1(dispatch_event_arg1),
    .s_length(dispatch_event_length),
    .s_type(dispatch_event_type),
    .s_flags(dispatch_event_flags),
    .s_stream(dispatch_event_stream),
    .s_user(dispatch_event_user),
    .m_valid(event_valid),
    .m_ready(event_ready),
    .m_kind(event_kind),
    .m_data(event_data),
    .m_arg0(event_arg0),
    .m_arg1(event_arg1),
    .m_length(event_length),
    .m_type(event_type),
    .m_flags(event_flags),
    .m_stream(event_stream),
    .m_user(event_user),
    .header_valid(header_valid),
    .header_ready(header_ready),
    .header_name_base(header_name_base),
    .header_value_base(header_value_base),
    .header_name_bytes(header_name_bytes),
    .header_value_bytes(header_value_bytes),
    .header_representation(header_representation),
    .header_user(header_user),
    .block_start_valid(block_start_valid),
    .block_start_ready(block_start_ready),
    .block_start_stream(block_start_stream),
    .block_start_promised_stream(block_start_promised_stream),
    .block_start_type(block_start_type),
    .block_start_flags(block_start_flags),
    .block_start_user(block_start_user),
    .block_valid(block_valid),
    .block_ready(block_ready),
    .block_stream(block_stream),
    .block_promised_stream(block_promised_stream),
    .block_type(block_type),
    .block_flags(block_flags),
    .block_headers(block_headers),
    .block_list_bytes(block_list_bytes),
    .block_user(block_user),
    .finish_valid(payload_result_valid&&control_fork_idle),
    .result_valid(dispatch_result_valid),
    .result_ready(aux_result_ready&&payload_result_valid),
    .result_state(dispatch_save),
    .result_failed(dispatch_failed),
    .result_error(dispatch_error),
    .result_detail(dispatch_detail),
    .mem_valid(mem_valid[1+:3]),
    .mem_ready(mem_ready[1+:3]),
    .mem_write(mem_write[1+:3]),
    .mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:3*MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[4+:12]),
    .mem_data(mem_data[72+:216]),
    .mem_rsp_valid(mem_rsp_valid[1+:3]),
    .mem_rsp_ready(mem_rsp_ready[1+:3]),
    .mem_rsp_data(mem_rsp_data[72+:216]),
    .mem_rsp_status(mem_rsp_status[8+:24]),
    .idle(dispatch_idle)
);
    assign idle=base_idle&&payload_idle&&dispatch_idle&&control_fork_idle;
wire control_fork_idle;
wire  dispatch_event_valid;
wire  dispatch_event_ready;
wire [3:0] dispatch_event_kind;
wire [7:0] dispatch_event_data;
wire [31:0] dispatch_event_arg0;
wire [31:0] dispatch_event_arg1;
wire [23:0] dispatch_event_length;
wire [7:0] dispatch_event_type;
wire [7:0] dispatch_event_flags;
wire [30:0] dispatch_event_stream;
wire [USER_WIDTH-1:0] dispatch_event_user;
http2_control_event_fork #(.USER_WIDTH(USER_WIDTH)) control_fork(
    .clk(clk),
    .rst(rst),
    .idle(control_fork_idle),
    .s_valid(sem_valid),
    .s_ready(sem_ready),
    .s_kind(sem_kind),
    .s_data(sem_data),
    .s_arg0(sem_arg0),
    .s_arg1(sem_arg1),
    .s_length(sem_length),
    .s_type(sem_type),
    .s_flags(sem_flags),
    .s_stream(sem_stream),
    .s_user(sem_user),
    .m_valid(dispatch_event_valid),
    .m_ready(dispatch_event_ready),
    .m_kind(dispatch_event_kind),
    .m_data(dispatch_event_data),
    .m_arg0(dispatch_event_arg0),
    .m_arg1(dispatch_event_arg1),
    .m_length(dispatch_event_length),
    .m_type(dispatch_event_type),
    .m_flags(dispatch_event_flags),
    .m_stream(dispatch_event_stream),
    .m_user(dispatch_event_user),
    .control_valid(flow_event_valid),
    .control_ready(flow_event_ready),
    .control_kind(flow_event_kind),
    .control_data(flow_event_data),
    .control_arg0(flow_event_arg0),
    .control_arg1(flow_event_arg1),
    .control_length(flow_event_length),
    .control_type(flow_event_type),
    .control_flags(flow_event_flags),
    .control_stream(flow_event_stream),
    .control_user(flow_event_user)
);
endmodule
`default_nettype wire
