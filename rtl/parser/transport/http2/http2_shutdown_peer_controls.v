`timescale 1ns/1ps
`default_nettype none
// Journal replay owns peer notices. External commands support FORMAT/READ/local TX only.
// Parent must hold actual connection ownership and disjoint arena fences.
module http2_shutdown_peer_controls #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(
input wire  clk,
input wire  rst,
input wire  start_valid,
output wire  start_ready,
input wire  start_format,
input wire  start_maintenance,
input wire  start_authority,
input wire [USER_WIDTH-1:0] start_user,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_journal_base,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,
input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_journal_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_slot_bytes,
input wire  s_valid,
output wire  s_ready,
input wire [3:0] s_kind,
input wire [7:0] s_data,
input wire [31:0] s_arg0,
input wire [31:0] s_arg1,
input wire [23:0] s_length,
input wire [7:0] s_type,
input wire [7:0] s_flags,
input wire [30:0] s_stream,
input wire [USER_WIDTH-1:0] s_user,
input wire  finish_valid,
output wire  finish_ready,
input wire  finish_commit,
output wire  result_valid,
input wire  result_ready,
output wire [7:0] result_status,
output wire [7:0] result_detail,
output wire [7:0] result_memory_status,
output wire [USER_WIDTH-1:0] result_user,
output wire  result_committed,
output wire [31:0] result_records,
output wire [31:0] result_frames,
output wire  recovery_required,
output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
output wire  idle,
output wire [2*1-1:0] mem_valid,
input wire [2*1-1:0] mem_ready,
output wire [2*1-1:0] mem_write,
output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,
output wire [2*4-1:0] mem_bytes,
output wire [2*72-1:0] mem_data,
input wire [2*1-1:0] mem_rsp_valid,
output wire [2*1-1:0] mem_rsp_ready,
input wire [2*72-1:0] mem_rsp_data,
input wire [2*8-1:0] mem_rsp_status,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_window_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_window_bytes,
output wire [7:0] control_status,
output wire [7:0] control_detail,
output wire [7:0] control_memory_status,
output wire  control_connection_error,
output wire [31:0] control_http2_error,
output wire [31:0] control_frames,
output wire [31:0] control_ack_frames,
output wire [31:0] control_window_updates,
output wire  window_req_valid,
input wire  window_req_ready,
output wire [3:0] window_req_op,
output wire  window_req_maintenance,
output wire [USER_WIDTH-1:0] window_req_user,
output wire [30:0] window_req_stream,
output wire [31:0] window_req_generation,
output wire [MEMORY_ADDR_WIDTH-1:0] window_req_record_address,
output wire [31:0] window_req_amount,
output wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_context_base,
output wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_stream_base,
output wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_window_base,
output wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_work_floor,
output wire [MEMORY_ADDR_WIDTH:0] window_cfg_context_bytes,
output wire [MEMORY_ADDR_WIDTH:0] window_cfg_stream_bytes,
output wire [MEMORY_ADDR_WIDTH:0] window_cfg_window_bytes,
input wire  window_rsp_valid,
output wire  window_rsp_ready,
input wire [3:0] window_rsp_op,
input wire [USER_WIDTH-1:0] window_rsp_user,
input wire [30:0] window_rsp_stream,
input wire [7:0] window_rsp_status,
input wire [7:0] window_rsp_detail,
input wire [7:0] window_rsp_memory_status,
input wire  window_rsp_connection_error,
input wire [31:0] window_rsp_http2_error,
output wire  cancel_valid,
input wire  cancel_ready,
output wire [USER_WIDTH-1:0] cancel_user,
output wire  cancel_goaway,
output wire [30:0] cancel_stream,
output wire [31:0] cancel_arg0,
output wire [31:0] cancel_arg1,
input wire  cancel_result_valid,
output wire  cancel_result_ready,
input wire [7:0] cancel_status,
output wire  classify_valid,
input wire  classify_ready,
output wire [USER_WIDTH-1:0] classify_user,
output wire [30:0] classify_stream,
input wire  classify_result_valid,
output wire  classify_result_ready,
input wire [7:0] classify_status,
input wire  classify_closed,
output wire [511:0] m_axis_tx_tdata,
output wire [63:0] m_axis_tx_tkeep,
output wire  m_axis_tx_tvalid,
input wire  m_axis_tx_tready,
output wire  m_axis_tx_tlast,
output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_peer_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_peer_bytes,
output wire [7:0] peer_format_status,
output wire [7:0] peer_format_memory_status,
input wire  peer_cmd_req_valid,
output wire  peer_cmd_req_ready,
input wire [3:0] peer_cmd_req_op,
input wire  peer_cmd_req_authority,
input wire  peer_cmd_req_maintenance,
input wire [USER_WIDTH-1:0] peer_cmd_req_user,
input wire [63:0] peer_cmd_req_payload,
output wire  peer_cmd_rsp_valid,
input wire  peer_cmd_rsp_ready,
output wire [7:0] peer_cmd_rsp_status,
output wire [7:0] peer_cmd_rsp_detail,
output wire [7:0] peer_cmd_rsp_memory_status,
output wire  peer_cmd_rsp_connection_error,
output wire [31:0] peer_cmd_rsp_http2_error,
output wire [3:0] peer_cmd_rsp_op,
output wire [USER_WIDTH-1:0] peer_cmd_rsp_user,
output wire  peer_cmd_rsp_wire_retired,
output wire  peer_cmd_rsp_ack_matched,
output wire [31:0] peer_cmd_rsp_header_table_size,
output wire [31:0] peer_cmd_rsp_max_concurrent_streams,
output wire [31:0] peer_cmd_rsp_max_header_list_size,
output wire  peer_cmd_rsp_enable_push,
output wire  peer_cmd_rsp_ping_pending,
output wire [31:0] peer_cmd_rsp_settings_pending,
output wire [31:0] peer_cmd_rsp_settings_acks,
output wire [31:0] peer_cmd_rsp_ping_acks,
output wire [63:0] peer_cmd_rsp_ping_payload
 ,
    input wire [7:0] cancel_detail,
    input wire [7:0] cancel_memory_status,
    input wire  cancel_connection_error,
    input wire [31:0] cancel_http2_error,
    input wire  goaway_req_valid,
    output wire  goaway_req_ready,
    input wire [USER_WIDTH-1:0] goaway_user,
    input wire [30:0] goaway_last_stream,
    input wire [31:0] goaway_error,
    output wire  goaway_rsp_valid,
    input wire  goaway_rsp_ready,
    output wire [7:0] goaway_rsp_status,
    output wire [7:0] goaway_rsp_detail,
    output wire [7:0] goaway_rsp_memory_status,
    output wire  goaway_rsp_connection_error,
    output wire [31:0] goaway_rsp_http2_error,
    output wire [3:0] goaway_rsp_op,
    output wire [USER_WIDTH-1:0] goaway_rsp_user,
    output wire  peer_goaway_received,
    output wire [30:0] peer_goaway_last_stream,
    output wire [31:0] peer_goaway_error
);
wire  j_start_ready;
wire  j_result_valid;
wire  j_result_ready;
wire [7:0] j_result_status;
wire [7:0] j_result_detail;
wire [7:0] j_result_memory_status;
wire  j_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] j_recovery_address;
wire  j_idle;
wire [7:0] j_control_memory_status;
wire  j_control_connection_error;
wire [31:0] j_control_http2_error;
wire  j_notice_valid;
wire  j_notice_ready;
wire [1:0] j_notice_kind;
wire [USER_WIDTH-1:0] j_notice_user;
wire [15:0] j_notice_setting;
wire [31:0] j_notice_value;
wire [63:0] j_notice_payload;
wire  j_notice_result_valid;
wire  j_notice_result_ready;
wire [7:0] j_notice_status;
wire [511:0] j_m_axis_tx_tdata;
wire [63:0] j_m_axis_tx_tkeep;
wire  j_m_axis_tx_tvalid;
wire  j_m_axis_tx_tready;
wire  j_m_axis_tx_tlast;
wire [USER_WIDTH-1:0] j_m_axis_tx_tuser;
wire  p_req_valid;
wire  p_req_ready;
wire [3:0] p_req_op;
wire  p_req_authority;
wire  p_req_maintenance;
wire [USER_WIDTH-1:0] p_req_user;
wire [15:0] p_req_setting;
wire [31:0] p_req_value;
wire [63:0] p_req_payload;
wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_peer_base;
wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] p_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] p_cfg_peer_bytes;
wire  p_rsp_valid;
wire  p_rsp_ready;
wire [7:0] p_rsp_status;
wire [7:0] p_rsp_detail;
wire [7:0] p_rsp_memory_status;
wire  p_rsp_connection_error;
wire [31:0] p_rsp_http2_error;
wire [3:0] p_rsp_op;
wire [USER_WIDTH-1:0] p_rsp_user;
wire  p_rsp_wire_retired;
wire  p_rsp_ack_matched;
wire [31:0] p_rsp_header_table_size;
wire [31:0] p_rsp_max_concurrent_streams;
wire [31:0] p_rsp_max_header_list_size;
wire  p_rsp_enable_push;
wire  p_rsp_ping_pending;
wire [31:0] p_rsp_settings_pending;
wire [31:0] p_rsp_settings_acks;
wire [31:0] p_rsp_ping_acks;
wire [63:0] p_rsp_ping_payload;
wire  p_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] p_recovery_address;
wire [511:0] p_m_axis_tx_tdata;
wire [63:0] p_m_axis_tx_tkeep;
wire  p_m_axis_tx_tvalid;
wire  p_m_axis_tx_tready;
wire  p_m_axis_tx_tlast;
wire [USER_WIDTH-1:0] p_m_axis_tx_tuser;
wire  p_idle;
reg [3:0] peer_owner;reg [2:0] format_phase;
reg [USER_WIDTH-1:0] format_user;
reg owned_authority,owned_maintenance;
reg [MEMORY_ADDR_WIDTH-1:0] owned_context_base,owned_peer_base,owned_work_floor;
reg [MEMORY_ADDR_WIDTH:0] owned_context_bytes,owned_peer_bytes;
reg [7:0] format_status,format_detail,format_memory,notice_memory;
reg notice_connection_error;reg [31:0] notice_http2_error;
wire start_gate=format_phase==0&&peer_owner==0&&p_idle&&(!p_recovery_required||start_format&&start_maintenance);
assign start_ready=j_start_ready&&start_gate;
assign peer_format_status=format_status;assign peer_format_memory_status=format_memory;
assign result_valid=j_result_valid&&(format_phase==0||format_phase==4);
assign result_status=j_result_status!=0?j_result_status:format_status!=0?8'd10:8'd0;
assign result_detail=j_result_status!=0?j_result_detail:format_detail;
assign result_memory_status=j_result_memory_status!=0?j_result_memory_status:notice_memory!=0?notice_memory:format_memory;
assign j_result_ready=result_valid&&result_ready;
assign recovery_required=j_recovery_required||p_recovery_required;
assign recovery_address=p_recovery_required?p_recovery_address:j_recovery_address;
assign control_http2_error=notice_connection_error?notice_http2_error:j_control_http2_error;
assign control_connection_error=notice_connection_error||j_control_connection_error;
assign control_memory_status=notice_memory!=0?notice_memory:j_control_memory_status;
wire tx_idle;assign idle=j_idle&&p_idle&&peer_owner==0&&format_phase==0&&tx_idle;
assign p_req_valid=peer_owner==9?goaway_req_valid:peer_owner==1?j_notice_valid:peer_owner==3?peer_cmd_req_valid:peer_owner==5||peer_owner==7;
assign p_req_op=peer_owner==9?4'd7:peer_owner==1?(j_notice_kind==0?4:j_notice_kind==1?5:j_notice_kind==2?6:15):peer_owner==5?0:peer_owner==7?2:peer_cmd_req_op<=3?peer_cmd_req_op:15;
assign p_req_user=peer_owner==9?goaway_user:peer_owner==1?j_notice_user:peer_owner==5||peer_owner==7?format_user:peer_cmd_req_user;
assign p_req_authority=peer_owner==9?(owned_authority&&goaway_user==format_user):peer_owner==3?peer_cmd_req_authority:owned_authority;
assign p_req_maintenance=peer_owner==5?owned_maintenance:peer_owner==3&&peer_cmd_req_maintenance;
assign p_req_setting=peer_owner==1?j_notice_setting:0;
assign p_req_value=peer_owner==9?{1'b0,goaway_last_stream}:peer_owner==1?j_notice_value:0;
assign p_req_payload=peer_owner==9?{32'd0,goaway_error}:peer_owner==1?j_notice_payload:peer_cmd_req_payload;
assign p_cfg_context_base=peer_owner==3?cfg_context_base:owned_context_base;
assign p_cfg_context_bytes=peer_owner==3?cfg_context_bytes:owned_context_bytes;
assign p_cfg_peer_base=peer_owner==3?cfg_peer_base:owned_peer_base;
assign p_cfg_peer_bytes=peer_owner==3?cfg_peer_bytes:owned_peer_bytes;
assign p_cfg_work_floor=peer_owner==3?cfg_work_floor:owned_work_floor;
assign j_notice_ready=peer_owner==1&&p_req_ready;
assign peer_cmd_req_ready=peer_owner==3&&p_req_ready;
assign j_notice_result_valid=peer_owner==2&&p_rsp_valid;
assign peer_cmd_rsp_valid=peer_owner==4&&p_rsp_valid;
assign p_rsp_ready=peer_owner==10?goaway_rsp_ready:peer_owner==2?j_notice_result_ready:peer_owner==4?peer_cmd_rsp_ready:peer_owner==6||peer_owner==8;
assign j_notice_status=p_rsp_status;
always @(posedge clk)begin
if(rst)begin peer_owner<=0;format_phase<=0;format_user<=0;owned_authority<=0;owned_maintenance<=0;
owned_context_base<=0;owned_context_bytes<=0;owned_peer_base<=0;owned_peer_bytes<=0;owned_work_floor<=0;
format_status<=0;format_detail<=0;format_memory<=0;notice_memory<=0;notice_connection_error<=0;notice_http2_error<=0;end
else begin
if(start_valid&&start_ready)begin
format_phase<=start_format?1:0;format_user<=start_user;owned_authority<=start_authority;owned_maintenance<=start_maintenance;
owned_context_base<=cfg_context_base;owned_context_bytes<=cfg_context_bytes;owned_peer_base<=cfg_peer_base;owned_peer_bytes<=cfg_peer_bytes;owned_work_floor<=cfg_work_floor;
format_status<=0;format_detail<=0;format_memory<=0;notice_memory<=0;notice_connection_error<=0;notice_http2_error<=0;end
if(format_phase==1&&j_result_valid)format_phase<=j_result_status==0?2:4;
if(result_valid&&result_ready)format_phase<=0;
case(peer_owner)
0:if(format_phase==2)peer_owner<=5;else if(format_phase==5)peer_owner<=7;else if(j_notice_valid)peer_owner<=1;else if(goaway_req_valid&&!start_valid)peer_owner<=9;else if(peer_cmd_req_valid&&j_idle&&!start_valid)peer_owner<=3;
1:if(j_notice_valid&&p_req_ready)peer_owner<=2;
2:if(p_rsp_valid&&j_notice_result_ready)begin peer_owner<=0;
if(p_rsp_status!=0)begin notice_memory<=p_rsp_memory_status;notice_connection_error<=p_rsp_connection_error;notice_http2_error<=p_rsp_http2_error;end end
3:if(peer_cmd_req_valid&&p_req_ready)peer_owner<=4;
4:if(p_rsp_valid&&peer_cmd_rsp_ready)peer_owner<=0;
5:if(p_req_ready)begin peer_owner<=6;format_phase<=3;end
6:if(p_rsp_valid)begin peer_owner<=0;format_phase<=p_rsp_status==0?5:4;format_status<=p_rsp_status;format_detail<=p_rsp_detail;format_memory<=p_rsp_memory_status;end
7:if(p_req_ready)begin peer_owner<=8;format_phase<=6;end
8:if(p_rsp_valid)begin peer_owner<=0;format_phase<=4;format_status<=p_rsp_status;format_detail<=p_rsp_detail;format_memory<=p_rsp_memory_status;end
9:if(goaway_req_valid&&p_req_ready)peer_owner<=10;
10:if(p_rsp_valid&&goaway_rsp_ready)peer_owner<=0;
default:peer_owner<=0;endcase end end
assign peer_cmd_rsp_status=p_rsp_status;
assign peer_cmd_rsp_detail=p_rsp_detail;
assign peer_cmd_rsp_memory_status=p_rsp_memory_status;
assign peer_cmd_rsp_connection_error=p_rsp_connection_error;
assign peer_cmd_rsp_http2_error=p_rsp_http2_error;
assign peer_cmd_rsp_op=p_rsp_op;
assign peer_cmd_rsp_user=p_rsp_user;
assign peer_cmd_rsp_wire_retired=p_rsp_wire_retired;
assign peer_cmd_rsp_ack_matched=p_rsp_ack_matched;
assign peer_cmd_rsp_header_table_size=p_rsp_header_table_size;
assign peer_cmd_rsp_max_concurrent_streams=p_rsp_max_concurrent_streams;
assign peer_cmd_rsp_max_header_list_size=p_rsp_max_header_list_size;
assign peer_cmd_rsp_enable_push=p_rsp_enable_push;
assign peer_cmd_rsp_ping_pending=p_rsp_ping_pending;
assign peer_cmd_rsp_settings_pending=p_rsp_settings_pending;
assign peer_cmd_rsp_settings_acks=p_rsp_settings_acks;
assign peer_cmd_rsp_ping_acks=p_rsp_ping_acks;
assign peer_cmd_rsp_ping_payload=p_rsp_ping_payload;
http2_shutdown_journaled_controls #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) journaled(
    .clk(clk),
    .rst(rst),
    .start_valid(start_valid&&start_gate),
    .start_ready(j_start_ready),
    .start_format(start_format),
    .start_maintenance(start_maintenance),
    .start_authority(start_authority),
    .start_user(start_user),
    .cfg_context_base(cfg_context_base),
    .cfg_journal_base(cfg_journal_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_context_bytes(cfg_context_bytes),
    .cfg_journal_bytes(cfg_journal_bytes),
    .cfg_slot_bytes(cfg_slot_bytes),
    .s_valid(s_valid),
    .s_ready(s_ready),
    .s_kind(s_kind),
    .s_data(s_data),
    .s_arg0(s_arg0),
    .s_arg1(s_arg1),
    .s_length(s_length),
    .s_type(s_type),
    .s_flags(s_flags),
    .s_stream(s_stream),
    .s_user(s_user),
    .finish_valid(finish_valid),
    .finish_ready(finish_ready),
    .finish_commit(finish_commit),
    .result_valid(j_result_valid),
    .result_ready(j_result_ready),
    .result_status(j_result_status),
    .result_detail(j_result_detail),
    .result_memory_status(j_result_memory_status),
    .result_user(result_user),
    .result_committed(result_committed),
    .result_records(result_records),
    .result_frames(result_frames),
    .recovery_required(j_recovery_required),
    .recovery_address(j_recovery_address),
    .idle(j_idle),
    .mem_valid(mem_valid[0+:1]),
    .mem_ready(mem_ready[0+:1]),
    .mem_write(mem_write[0+:1]),
    .mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[0+:4]),
    .mem_data(mem_data[0+:72]),
    .mem_rsp_valid(mem_rsp_valid[0+:1]),
    .mem_rsp_ready(mem_rsp_ready[0+:1]),
    .mem_rsp_data(mem_rsp_data[0+:72]),
    .mem_rsp_status(mem_rsp_status[0+:8]),
    .cfg_stream_base(cfg_stream_base),
    .cfg_window_base(cfg_window_base),
    .cfg_stream_bytes(cfg_stream_bytes),
    .cfg_window_bytes(cfg_window_bytes),
    .control_status(control_status),
    .control_detail(control_detail),
    .control_memory_status(j_control_memory_status),
    .control_connection_error(j_control_connection_error),
    .control_http2_error(j_control_http2_error),
    .control_frames(control_frames),
    .control_ack_frames(control_ack_frames),
    .control_window_updates(control_window_updates),
    .window_req_valid(window_req_valid),
    .window_req_ready(window_req_ready),
    .window_req_op(window_req_op),
    .window_req_maintenance(window_req_maintenance),
    .window_req_user(window_req_user),
    .window_req_stream(window_req_stream),
    .window_req_generation(window_req_generation),
    .window_req_record_address(window_req_record_address),
    .window_req_amount(window_req_amount),
    .window_cfg_context_base(window_cfg_context_base),
    .window_cfg_stream_base(window_cfg_stream_base),
    .window_cfg_window_base(window_cfg_window_base),
    .window_cfg_work_floor(window_cfg_work_floor),
    .window_cfg_context_bytes(window_cfg_context_bytes),
    .window_cfg_stream_bytes(window_cfg_stream_bytes),
    .window_cfg_window_bytes(window_cfg_window_bytes),
    .window_rsp_valid(window_rsp_valid),
    .window_rsp_ready(window_rsp_ready),
    .window_rsp_op(window_rsp_op),
    .window_rsp_user(window_rsp_user),
    .window_rsp_stream(window_rsp_stream),
    .window_rsp_status(window_rsp_status),
    .window_rsp_detail(window_rsp_detail),
    .window_rsp_memory_status(window_rsp_memory_status),
    .window_rsp_connection_error(window_rsp_connection_error),
    .window_rsp_http2_error(window_rsp_http2_error),
    .notice_valid(j_notice_valid),
    .notice_ready(j_notice_ready),
    .notice_kind(j_notice_kind),
    .notice_user(j_notice_user),
    .notice_setting(j_notice_setting),
    .notice_value(j_notice_value),
    .notice_payload(j_notice_payload),
    .notice_result_valid(j_notice_result_valid),
    .notice_result_ready(j_notice_result_ready),
    .notice_status(j_notice_status),
    .cancel_valid(cancel_valid),
    .cancel_ready(cancel_ready),
    .cancel_user(cancel_user),
    .cancel_goaway(cancel_goaway),
    .cancel_stream(cancel_stream),
    .cancel_arg0(cancel_arg0),
    .cancel_arg1(cancel_arg1),
    .cancel_result_valid(cancel_result_valid),
    .cancel_result_ready(cancel_result_ready),
    .cancel_status(cancel_status),
    .classify_valid(classify_valid),
    .classify_ready(classify_ready),
    .classify_user(classify_user),
    .classify_stream(classify_stream),
    .classify_result_valid(classify_result_valid),
    .classify_result_ready(classify_result_ready),
    .classify_status(classify_status),
    .classify_closed(classify_closed),
    .m_axis_tx_tdata(j_m_axis_tx_tdata),
    .m_axis_tx_tkeep(j_m_axis_tx_tkeep),
    .m_axis_tx_tvalid(j_m_axis_tx_tvalid),
    .m_axis_tx_tready(j_m_axis_tx_tready),
    .m_axis_tx_tlast(j_m_axis_tx_tlast),
    .m_axis_tx_tuser(j_m_axis_tx_tuser),
    .cancel_detail(cancel_detail),
    .cancel_memory_status(cancel_memory_status),
    .cancel_connection_error(cancel_connection_error),
    .cancel_http2_error(cancel_http2_error)
);
http2_shutdown_peer_state #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) peer(
    .clk(clk),
    .rst(rst),
    .req_valid(p_req_valid),
    .req_ready(p_req_ready),
    .req_op(p_req_op),
    .req_authority(p_req_authority),
    .req_maintenance(p_req_maintenance),
    .req_user(p_req_user),
    .req_setting(p_req_setting),
    .req_value(p_req_value),
    .req_payload(p_req_payload),
    .cfg_context_base(p_cfg_context_base),
    .cfg_peer_base(p_cfg_peer_base),
    .cfg_work_floor(p_cfg_work_floor),
    .cfg_context_bytes(p_cfg_context_bytes),
    .cfg_peer_bytes(p_cfg_peer_bytes),
    .rsp_valid(p_rsp_valid),
    .rsp_ready(p_rsp_ready),
    .rsp_status(p_rsp_status),
    .rsp_detail(p_rsp_detail),
    .rsp_memory_status(p_rsp_memory_status),
    .rsp_connection_error(p_rsp_connection_error),
    .rsp_http2_error(p_rsp_http2_error),
    .rsp_op(p_rsp_op),
    .rsp_user(p_rsp_user),
    .rsp_wire_retired(p_rsp_wire_retired),
    .rsp_ack_matched(p_rsp_ack_matched),
    .rsp_header_table_size(p_rsp_header_table_size),
    .rsp_max_concurrent_streams(p_rsp_max_concurrent_streams),
    .rsp_max_header_list_size(p_rsp_max_header_list_size),
    .rsp_enable_push(p_rsp_enable_push),
    .rsp_ping_pending(p_rsp_ping_pending),
    .rsp_settings_pending(p_rsp_settings_pending),
    .rsp_settings_acks(p_rsp_settings_acks),
    .rsp_ping_acks(p_rsp_ping_acks),
    .rsp_ping_payload(p_rsp_ping_payload),
    .recovery_required(p_recovery_required),
    .recovery_address(p_recovery_address),
    .m_axis_tx_tdata(p_m_axis_tx_tdata),
    .m_axis_tx_tkeep(p_m_axis_tx_tkeep),
    .m_axis_tx_tvalid(p_m_axis_tx_tvalid),
    .m_axis_tx_tready(p_m_axis_tx_tready),
    .m_axis_tx_tlast(p_m_axis_tx_tlast),
    .m_axis_tx_tuser(p_m_axis_tx_tuser),
    .mem_valid(mem_valid[1+:1]),
    .mem_ready(mem_ready[1+:1]),
    .mem_write(mem_write[1+:1]),
    .mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[4+:4]),
    .mem_data(mem_data[72+:72]),
    .mem_rsp_valid(mem_rsp_valid[1+:1]),
    .mem_rsp_ready(mem_rsp_ready[1+:1]),
    .mem_rsp_data(mem_rsp_data[72+:72]),
    .mem_rsp_status(mem_rsp_status[8+:8]),
    .idle(p_idle),
    .rsp_goaway_received(peer_goaway_received),
    .rsp_goaway_last_stream(peer_goaway_last_stream),
    .rsp_goaway_error(peer_goaway_error)
);
axis_frame_arbiter #(.DATA_WIDTH(512),.KEEP_WIDTH(64),.USER_WIDTH(USER_WIDTH)) tx(
    .clk(clk),
    .rst(rst),
    .a_axis_tdata(j_m_axis_tx_tdata),
    .a_axis_tkeep(j_m_axis_tx_tkeep),
    .a_axis_tvalid(j_m_axis_tx_tvalid),
    .a_axis_tready(j_m_axis_tx_tready),
    .a_axis_tlast(j_m_axis_tx_tlast),
    .a_axis_tuser(j_m_axis_tx_tuser),
    .b_axis_tdata(p_m_axis_tx_tdata),
    .b_axis_tkeep(p_m_axis_tx_tkeep),
    .b_axis_tvalid(p_m_axis_tx_tvalid),
    .b_axis_tready(p_m_axis_tx_tready),
    .b_axis_tlast(p_m_axis_tx_tlast),
    .b_axis_tuser(p_m_axis_tx_tuser),
    .m_axis_tdata(m_axis_tx_tdata),
    .m_axis_tkeep(m_axis_tx_tkeep),
    .m_axis_tvalid(m_axis_tx_tvalid),
    .m_axis_tready(m_axis_tx_tready),
    .m_axis_tlast(m_axis_tx_tlast),
    .m_axis_tuser(m_axis_tx_tuser),
    .idle(tx_idle)
);
assign goaway_req_ready=peer_owner==9&&p_req_ready;
assign goaway_rsp_valid=peer_owner==10&&p_rsp_valid;
assign goaway_rsp_status=p_rsp_status;
assign goaway_rsp_detail=p_rsp_detail;
assign goaway_rsp_memory_status=p_rsp_memory_status;
assign goaway_rsp_connection_error=p_rsp_connection_error;
assign goaway_rsp_http2_error=p_rsp_http2_error;
assign goaway_rsp_op=p_rsp_op;
assign goaway_rsp_user=p_rsp_user;
endmodule
`default_nettype wire
