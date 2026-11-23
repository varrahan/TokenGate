`timescale 1ns/1ps
`default_nettype none
// Packet adapter for the unchanged 512-bit DMA ingress. start selects the
// saved connection state before accepting this packet. TLAST ends a fragment,
// not an HTTP/2 frame or stream. No new packet enters before completion ACK.
module http2_axis_ingress #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire start_fresh,input wire [USER_WIDTH-1:0] start_user,
    input wire [159:0] cfg_state,input wire [23:0] cfg_max_frame_bytes,input wire cfg_server_role,cfg_allow_push,
    input wire [511:0] s_axis_rx_tdata,input wire [63:0] s_axis_rx_tkeep,input wire s_axis_rx_tvalid,output wire s_axis_rx_tready,
    input wire s_axis_rx_tlast,input wire [USER_WIDTH-1:0] s_axis_rx_tuser,
    output wire event_valid,input wire event_ready,output wire [1:0] event_kind,output wire [7:0] event_data,
    output wire [23:0] event_length,output wire [7:0] event_type,event_flags,output wire [30:0] event_stream,
    output wire event_payload_last,output wire [31:0] event_error,output wire [USER_WIDTH-1:0] event_user,
    output wire completion_valid,input wire completion_ready,output wire completion_failed,
    output wire [31:0] completion_error,output wire [7:0] completion_detail,output wire [159:0] completion_state,
    output wire [USER_WIDTH-1:0] completion_user,output wire idle
);
    reg accepting;
    wire core_ready,unpack_ready,unpack_idle,core_idle;
    wire [7:0] byte_data;wire byte_keep,byte_valid,byte_ready,byte_last;wire [USER_WIDTH-1:0] byte_user;
    assign start_ready=core_ready&&unpack_idle&&!accepting;
    assign s_axis_rx_tready=accepting&&unpack_ready;
    assign idle=core_idle&&unpack_idle&&!accepting;
    always @(posedge clk)begin
        if(rst)accepting<=0;
        else begin
            if(start_valid&&start_ready)accepting<=1;
            if(s_axis_rx_tvalid&&s_axis_rx_tready&&s_axis_rx_tlast)accepting<=0;
        end
    end
    axis_byte_unpacker #(.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)) unpacker(
        .clk(clk),.rst(rst),.s_data(s_axis_rx_tdata),.s_keep(s_axis_rx_tkeep),.s_valid(s_axis_rx_tvalid&&accepting),.s_ready(unpack_ready),
        .s_last(s_axis_rx_tlast),.s_user(s_axis_rx_tuser),.m_data(byte_data),.m_keep(byte_keep),.m_valid(byte_valid),.m_ready(byte_ready),.m_last(byte_last),.m_user(byte_user),.idle(unpack_idle));
    http2_frame_reader #(.USER_WIDTH(USER_WIDTH)) reader(
        .clk(clk),.rst(rst),.start_valid(start_valid&&unpack_idle&&!accepting),.start_ready(core_ready),.start_fresh(start_fresh),.start_user(start_user),
        .cfg_state(cfg_state),.cfg_max_frame_bytes(cfg_max_frame_bytes),.cfg_server_role(cfg_server_role),.cfg_allow_push(cfg_allow_push),
        .s_data(byte_data),.s_keep(byte_keep),.s_valid(byte_valid),.s_ready(byte_ready),.s_last(byte_last),.s_user(byte_user),
        .event_valid(event_valid),.event_ready(event_ready),.event_kind(event_kind),.event_data(event_data),.event_length(event_length),.event_type(event_type),.event_flags(event_flags),.event_stream(event_stream),
        .event_payload_last(event_payload_last),.event_error(event_error),.event_user(event_user),.completion_valid(completion_valid),.completion_ready(completion_ready),.completion_failed(completion_failed),
        .completion_error(completion_error),.completion_detail(completion_detail),.completion_state(completion_state),.completion_user(completion_user),.idle(core_idle));
endmodule
`default_nettype wire
