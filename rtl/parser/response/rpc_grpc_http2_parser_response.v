`timescale 1ns/1ps
`default_nettype none
// Actual Parser-side RPC controller, Unicode/serializer and gRPC DATA framing.
// Remote inverse/BPE remain on Tokenizer. Credit ledger and HEADERS/trailers remain external.
module rpc_grpc_http2_parser_response #(
parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384,
parameter integer MAX_MESSAGE_BYTES=6*MAX_TEXT_BYTES+46
)(
    input wire  clk,
    input wire  rst,
    input wire [31:0] s_axis_tokens_tdata,
    input wire [3:0] s_axis_tokens_tkeep,
    input wire  s_axis_tokens_tvalid,
    output wire  s_axis_tokens_tready,
    input wire  s_axis_tokens_tlast,
    input wire [USER_WIDTH-1:0] s_axis_tokens_tuser,
    input wire [30:0] s_stream,
    input wire [31:0] s_generation,
    input wire [31:0] s_model_epoch,
    input wire [31:0] s_schema_epoch,
    input wire [31:0] s_ordinal,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_progress_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_progress_bytes,
    input wire [31:0] cfg_model_epoch,
    input wire [31:0] cfg_schema_epoch,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_directory_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_directory_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes,
    input wire  cfg_strip_special,
    input wire  cfg_replace_invalid,
    input wire [1:0] cfg_format,
    input wire [28:0] cfg_protobuf_field,
    output wire  directory_valid,
    input wire  directory_ready,
    output wire [USER_WIDTH-1:0] directory_user,
    output wire [30:0] directory_stream,
    output wire [MEMORY_ADDR_WIDTH-1:0] directory_pool_base,
    output wire [MEMORY_ADDR_WIDTH:0] directory_pool_bytes,
    input wire  directory_result_valid,
    output wire  directory_result_ready,
    input wire [7:0] directory_status,
    input wire [7:0] directory_memory_status,
    input wire [MEMORY_ADDR_WIDTH-1:0] directory_address,
    input wire [USER_WIDTH-1:0] directory_application,
    input wire [31:0] directory_generation,
    input wire  directory_protobuf,
    input wire  directory_unsupported_encoding,
    output wire [511:0] m_axis_tx_tdata,
    output wire [63:0] m_axis_tx_tkeep,
    output wire  m_axis_tx_tvalid,
    input wire  m_axis_tx_tready,
    output wire  m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire  result_valid,
    input wire  result_ready,
    output wire [7:0] result_stage,
    output wire [7:0] result_status,
    output wire [7:0] result_memory_status,
    output wire [USER_WIDTH-1:0] result_user,
    output wire [USER_WIDTH-1:0] result_application,
    output wire [30:0] result_stream,
    output wire [31:0] result_generation,
    output wire [31:0] result_model_epoch,
    output wire [31:0] result_schema_epoch,
    output wire [31:0] result_ordinal,
    output wire [31:0] result_bytes,
    output wire  result_eos,
    output wire  result_tx_emitted,
    output wire  recovery_required,
    output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire  directory_lease_active,
    output wire  idle,
    output wire [1:0] mem_valid,
    input wire [1:0] mem_ready,
    output wire [1:0] mem_write,
    output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [7:0] mem_bytes,
    output wire [143:0] mem_data,
    input wire [1:0] mem_rsp_valid,
    output wire [1:0] mem_rsp_ready,
    input wire [143:0] mem_rsp_data,
    input wire [15:0] mem_rsp_status,
    output wire [31:0] link_r_s_axis_tokens_tdata,
    output wire [3:0] link_r_s_axis_tokens_tkeep,
    output wire  link_r_s_axis_tokens_tvalid,
    input wire  link_r_s_axis_tokens_tready,
    output wire  link_r_s_axis_tokens_tlast,
    output wire [USER_WIDTH-1:0] link_r_s_axis_tokens_tuser,
    output wire  link_r_lease_valid,
    output wire [USER_WIDTH-1:0] link_r_lease_user,
    output wire [USER_WIDTH-1:0] link_r_lease_application,
    output wire [30:0] link_r_lease_stream,
    output wire [31:0] link_r_lease_generation,
    output wire [31:0] link_r_lease_model_epoch,
    output wire [31:0] link_r_lease_schema_epoch,
    output wire [31:0] link_r_cfg_active_model_epoch,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_directory_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_pool_base,
    output wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_directory_bytes,
    output wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_pool_bytes,
    output wire  link_r_cfg_strip_special,
    output wire  link_r_cfg_replace_invalid,
    output wire [1:0] link_r_cfg_format,
    output wire [28:0] link_r_cfg_protobuf_field,
    output wire [23:0] link_r_carry_in,
    output wire [1:0] link_r_carry_in_count,
    input wire  link_r_result_valid,
    output wire  link_r_result_ready,
    input wire [7:0] link_r_result_stage,
    input wire [7:0] link_r_result_status,
    input wire [7:0] link_r_result_memory_status,
    input wire [23:0] link_r_carry_out,
    input wire [1:0] link_r_carry_out_count,
    input wire [31:0] link_r_result_bytes,
    input wire  link_r_idle,
    input wire  link_s_start_valid,
    output wire  link_s_start_ready,
    input wire [USER_WIDTH-1:0] link_s_start_user,
    input wire  link_s_start_eos,
    input wire  link_s_start_replace,
    input wire [23:0] link_s_start_carry,
    input wire [1:0] link_s_start_carry_count,
    input wire [1:0] link_s_start_format,
    input wire [28:0] link_s_start_protobuf_field,
    input wire [127:0] link_s_s_axis_text_tdata,
    input wire [15:0] link_s_s_axis_text_tkeep,
    input wire  link_s_s_axis_text_tvalid,
    output wire  link_s_s_axis_text_tready,
    input wire  link_s_s_axis_text_tlast,
    input wire [USER_WIDTH-1:0] link_s_s_axis_text_tuser,
    input wire  link_s_s_axis_text_abort,
    output wire  link_s_result_valid,
    input wire  link_s_result_ready,
    output wire [7:0] link_s_result_stage,
    output wire [7:0] link_s_result_status,
    output wire [23:0] link_s_result_carry,
    output wire [1:0] link_s_result_carry_count,
    output wire [31:0] link_s_result_bytes,
    output wire  link_s_idle,
    input wire [23:0] cfg_peer_max_frame_bytes,
    output wire  frame_req_valid,
    input wire  frame_req_ready,
    output wire [USER_WIDTH-1:0] frame_req_user,
    output wire [30:0] frame_req_stream,
    output wire [23:0] frame_req_max_bytes,
    input wire [23:0] frame_grant_bytes,
    output wire [31:0] result_serialized_bytes,
    output wire [31:0] result_wire_bytes,
    output wire [31:0] result_frames,
    output wire  result_progress_committed
,
    input wire  closed_valid,
    input wire [USER_WIDTH-1:0] closed_user,
    input wire [30:0] closed_stream,
    input wire [31:0] closed_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] closed_address,
    input wire [MEMORY_ADDR_WIDTH-1:0] closed_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] closed_pool_bytes,
    input wire  service_abort,
    input wire  directory_abort,
    input wire  closed_reservation_verified,
    output wire  result_cancelled
,
    input wire  envelope_freeze,
    input wire  envelope_wire_fenced,
    output wire  envelope_drained,
    output wire  envelope_recovery_required,
    output wire [7:0] envelope_error_status,
    output wire [7:0] envelope_error_memory_status,
    output wire  data_frame_tx_done
);
wire  transport_req_valid;
wire  transport_req_ready;
wire [2:0] transport_req_op;
wire  transport_private_abort_proof;
wire  transport_rsp_valid;
wire  transport_rsp_ready;
wire [7:0] transport_rsp_status;
wire [7:0] transport_rsp_memory_status;
wire [1:0] transport_result_format;
wire  transport_header_intent;
wire  transport_headers_sent;
wire  transport_trailer_intent;
wire  transport_trailers_sent;
wire  transport_busy;
wire  transport_retirement_pending;
wire seq_data_admit,seq_terminal,seq_private_failed,seq_header_select,seq_idle,seq_cancelled;
wire [31:0] seq_header_bytes;wire [1:0] seq_header_frames;
wire [511:0] body_tdata,header_tdata;wire [63:0] body_tkeep,header_tkeep;
wire body_tvalid,body_tready,body_tlast,header_tvalid,header_tready,header_tlast;
wire [USER_WIDTH-1:0] body_tuser,header_tuser;
wire header_req_valid,header_req_ready,header_abort_valid,header_abort_ready,header_result_valid,header_result_ready;
wire [1:0] header_req_kind,header_req_encoding,header_result_kind;
wire [USER_WIDTH-1:0] header_req_user,header_result_user;wire [30:0] header_req_stream,header_result_stream;
wire [7:0] header_result_status;wire header_result_tx_emitted,header_idle;wire [6:0] header_result_wire_bytes;
assign data_frame_tx_done=body_tvalid&&body_tready&&body_tlast;
assign m_axis_tx_tdata=seq_header_select?header_tdata:body_tdata;
assign m_axis_tx_tkeep=seq_header_select?header_tkeep:body_tkeep;
assign m_axis_tx_tvalid=seq_header_select?header_tvalid:body_tvalid&&seq_data_admit;
assign m_axis_tx_tlast=seq_header_select?header_tlast:body_tlast;
assign m_axis_tx_tuser=seq_header_select?header_tuser:body_tuser;
assign header_tready=seq_header_select&&m_axis_tx_tready;
assign body_tready=!seq_header_select&&seq_data_admit&&m_axis_tx_tready;
reg active,kill_ungranted,directory_requested,release_pending,transport_recovery;
reg [USER_WIDTH-1:0] owner;
reg [MEMORY_ADDR_WIDTH-1:0] held_address,transport_recovery_address;
wire rpc_ready,rpc_result_valid,rpc_directory_ready,rpc_lease,rpc_idle,rpc_recovery,rpc_buffered;
wire [7:0] rpc_stage,rpc_status,rpc_memory;
wire [31:0] rpc_bytes;
wire [MEMORY_ADDR_WIDTH-1:0] rpc_recovery_address;
wire [511:0] raw_data;wire [63:0] raw_keep;wire raw_valid,raw_ready,raw_last;
wire [USER_WIDTH-1:0] raw_user;
wire framer_start_ready,framer_valid,framer_result,framer_idle,framer_tx_emitted,framer_message_ready;
wire [7:0] framer_status;
wire [31:0] framer_message_bytes,framer_wire_bytes,framer_frames;
wire accept_guard=!active&&!transport_recovery&&seq_idle&&!envelope_recovery_required&&!rpc_recovery&&!service_abort;
assign s_axis_tokens_tready=!rst&&accept_guard&&rpc_ready&&framer_start_ready;
wire accept=s_axis_tokens_tvalid&&s_axis_tokens_tready;
wire authorized=rpc_result_valid&&rpc_status==0&&directory_requested&&release_pending&&!kill_ungranted;
// Durable progress commits before credit reservation or any wire output.
assign frame_req_valid=framer_valid&&authorized&&seq_data_admit;
assign raw_ready=active&&!kill_ungranted&&framer_message_ready;
wire failed_before_grant=rpc_result_valid&&rpc_status!=0||seq_private_failed;
assign result_valid=active&&rpc_result_valid&&(!directory_requested||release_pending)&&seq_terminal&&!transport_busy&&!transport_retirement_pending&&
    (failed_before_grant?kill_ungranted&&framer_idle:framer_result);
wire retire=result_valid&&result_ready;
// The real LOAD is acknowledged only with public retirement, even though
// the child has already completed its local RELEASE -> RESULT transition.
assign directory_result_ready=retire&&directory_requested&&release_pending;
assign directory_lease_active=active&&directory_requested;
assign result_stage=rpc_status!=0?rpc_stage:envelope_error_status!=0?8'd20:seq_cancelled?8'd17:framer_status!=0?8'd16:8'd0;
assign result_status=rpc_status!=0?rpc_status:envelope_error_status!=0?envelope_error_status:seq_cancelled?8'd1:framer_status;
assign result_memory_status=rpc_status!=0?rpc_memory:envelope_error_memory_status;
assign result_bytes=result_status==0?rpc_bytes:32'd0;
assign result_serialized_bytes=framer_message_bytes;
assign result_wire_bytes=framer_wire_bytes+seq_header_bytes;assign result_frames=framer_frames+seq_header_frames;
assign result_tx_emitted=framer_tx_emitted||seq_header_frames!=0;
assign result_progress_committed=rpc_result_valid&&rpc_status==0;
wire rpc_cancelled;
wire expected_closed=closed_reservation_verified&&framer_result&&framer_status==5;
assign result_cancelled=rpc_result_valid&&(rpc_cancelled||rpc_status==0&&(expected_closed||seq_cancelled));
wire transport_failure=active&&rpc_result_valid&&rpc_status==0&&framer_result&&framer_status!=0&&!expected_closed;
assign recovery_required=rpc_recovery||transport_recovery||transport_failure||envelope_recovery_required;
assign recovery_address=rpc_recovery?rpc_recovery_address:
    transport_failure?held_address:transport_recovery_address;
assign idle=!active&&!kill_ungranted&&rpc_idle&&framer_idle&&seq_idle&&header_idle;
always @(posedge clk)begin
    if(rst)begin active<=0;kill_ungranted<=0;directory_requested<=0;release_pending<=0;
        owner<=0;held_address<=0;transport_recovery<=0;transport_recovery_address<=0;end
    else begin
        if(accept)begin active<=1;owner<=s_axis_tokens_tuser;kill_ungranted<=0;directory_requested<=0;release_pending<=0;held_address<=0;end
        if(active&&directory_valid&&directory_ready)directory_requested<=1;
        if(active&&directory_requested&&directory_result_valid)held_address<=directory_address;
        if(active&&rpc_directory_ready&&directory_result_valid)release_pending<=1;
        // No grant is permitted until child success. A failed child therefore
        // has no wire bytes or reserved credits; its private buffer can reset
        // without resetting a connection or releasing the actual directory LOAD.
        if(active&&failed_before_grant)kill_ungranted<=1;
        if(transport_failure)begin transport_recovery<=1;transport_recovery_address<=held_address;end
        if(retire)begin active<=0;kill_ungranted<=0;directory_requested<=0;release_pending<=0;end
    end
end
rpc_http2_response_partition #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) rpc(
    .clk(clk),
    .rst(rst),
    .s_axis_tokens_tdata(s_axis_tokens_tdata),
    .s_axis_tokens_tkeep(s_axis_tokens_tkeep),
    .s_axis_tokens_tvalid(s_axis_tokens_tvalid&&accept_guard&&framer_start_ready),
    .s_axis_tokens_tready(rpc_ready),
    .s_axis_tokens_tlast(s_axis_tokens_tlast),
    .s_axis_tokens_tuser(s_axis_tokens_tuser),
    .s_stream(s_stream),
    .s_generation(s_generation),
    .s_model_epoch(s_model_epoch),
    .s_schema_epoch(s_schema_epoch),
    .s_ordinal(s_ordinal),
    .cfg_stream_base(cfg_stream_base),
    .cfg_progress_base(cfg_progress_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_stream_bytes(cfg_stream_bytes),
    .cfg_progress_bytes(cfg_progress_bytes),
    .cfg_model_epoch(cfg_model_epoch),
    .cfg_schema_epoch(cfg_schema_epoch),
    .cfg_directory_base(cfg_directory_base),
    .cfg_pool_base(cfg_pool_base),
    .cfg_directory_bytes(cfg_directory_bytes),
    .cfg_pool_bytes(cfg_pool_bytes),
    .cfg_strip_special(cfg_strip_special),
    .cfg_replace_invalid(cfg_replace_invalid),
    .cfg_format(cfg_format),
    .cfg_protobuf_field(cfg_protobuf_field),
    .directory_valid(directory_valid),
    .directory_ready(directory_ready),
    .directory_user(directory_user),
    .directory_stream(directory_stream),
    .directory_pool_base(directory_pool_base),
    .directory_pool_bytes(directory_pool_bytes),
    .directory_result_valid(directory_result_valid),
    .directory_result_ready(rpc_directory_ready),
    .directory_status(directory_status),
    .directory_memory_status(directory_memory_status),
    .directory_address(directory_address),
    .directory_application(directory_application),
    .directory_generation(directory_generation),
    .directory_protobuf(directory_protobuf),
    .directory_unsupported_encoding(directory_unsupported_encoding),
    .m_axis_tx_tdata(),
    .m_axis_tx_tkeep(),
    .m_axis_tx_tvalid(),
    .m_axis_tx_tready(raw_ready),
    .m_axis_tx_tlast(),
    .m_axis_tx_tuser(),
    .result_valid(rpc_result_valid),
    .result_ready(retire),
    .result_stage(rpc_stage),
    .result_status(rpc_status),
    .result_memory_status(rpc_memory),
    .result_user(result_user),
    .result_application(result_application),
    .result_stream(result_stream),
    .result_generation(result_generation),
    .result_model_epoch(result_model_epoch),
    .result_schema_epoch(result_schema_epoch),
    .result_ordinal(result_ordinal),
    .result_bytes(rpc_bytes),
    .result_eos(result_eos),
    .result_tx_emitted(rpc_buffered),
    .recovery_required(rpc_recovery),
    .recovery_address(rpc_recovery_address),
    .directory_lease_active(rpc_lease),
    .idle(rpc_idle),
    .mem_valid(mem_valid),
    .mem_ready(mem_ready),
    .mem_write(mem_write),
    .mem_addr(mem_addr),
    .mem_bytes(mem_bytes),
    .mem_data(mem_data),
    .mem_rsp_valid(mem_rsp_valid),
    .mem_rsp_ready(mem_rsp_ready),
    .mem_rsp_data(mem_rsp_data),
    .mem_rsp_status(mem_rsp_status),
    .link_r_s_axis_tokens_tdata(link_r_s_axis_tokens_tdata),
    .link_r_s_axis_tokens_tkeep(link_r_s_axis_tokens_tkeep),
    .link_r_s_axis_tokens_tvalid(link_r_s_axis_tokens_tvalid),
    .link_r_s_axis_tokens_tready(link_r_s_axis_tokens_tready),
    .link_r_s_axis_tokens_tlast(link_r_s_axis_tokens_tlast),
    .link_r_s_axis_tokens_tuser(link_r_s_axis_tokens_tuser),
    .link_r_lease_valid(link_r_lease_valid),
    .link_r_lease_user(link_r_lease_user),
    .link_r_lease_application(link_r_lease_application),
    .link_r_lease_stream(link_r_lease_stream),
    .link_r_lease_generation(link_r_lease_generation),
    .link_r_lease_model_epoch(link_r_lease_model_epoch),
    .link_r_lease_schema_epoch(link_r_lease_schema_epoch),
    .link_r_cfg_active_model_epoch(link_r_cfg_active_model_epoch),
    .link_r_cfg_directory_base(link_r_cfg_directory_base),
    .link_r_cfg_pool_base(link_r_cfg_pool_base),
    .link_r_cfg_directory_bytes(link_r_cfg_directory_bytes),
    .link_r_cfg_pool_bytes(link_r_cfg_pool_bytes),
    .link_r_cfg_strip_special(link_r_cfg_strip_special),
    .link_r_cfg_replace_invalid(link_r_cfg_replace_invalid),
    .link_r_cfg_format(link_r_cfg_format),
    .link_r_cfg_protobuf_field(link_r_cfg_protobuf_field),
    .link_r_carry_in(link_r_carry_in),
    .link_r_carry_in_count(link_r_carry_in_count),
    .link_r_result_valid(link_r_result_valid),
    .link_r_result_ready(link_r_result_ready),
    .link_r_result_stage(link_r_result_stage),
    .link_r_result_status(link_r_result_status),
    .link_r_result_memory_status(link_r_result_memory_status),
    .link_r_carry_out(link_r_carry_out),
    .link_r_carry_out_count(link_r_carry_out_count),
    .link_r_result_bytes(link_r_result_bytes),
    .link_r_idle(link_r_idle),
    .local_tx_accepted(raw_valid&&raw_ready),
    .closed_valid(closed_valid),
    .closed_user(closed_user),
    .closed_stream(closed_stream),
    .closed_generation(closed_generation),
    .closed_address(closed_address),
    .closed_pool_base(closed_pool_base),
    .closed_pool_bytes(closed_pool_bytes),
    .result_cancelled(rpc_cancelled),
    .service_abort(service_abort),
    .directory_abort(directory_abort),
    .transport_req_valid(transport_req_valid),
    .transport_req_ready(transport_req_ready),
    .transport_req_op(transport_req_op),
    .transport_private_abort_proof(transport_private_abort_proof),
    .transport_rsp_valid(transport_rsp_valid),
    .transport_rsp_ready(transport_rsp_ready),
    .transport_rsp_status(transport_rsp_status),
    .transport_rsp_memory_status(transport_rsp_memory_status),
    .transport_result_format(transport_result_format),
    .transport_header_intent(transport_header_intent),
    .transport_headers_sent(transport_headers_sent),
    .transport_trailer_intent(transport_trailer_intent),
    .transport_trailers_sent(transport_trailers_sent),
    .transport_busy(transport_busy),
    .transport_retirement_pending(transport_retirement_pending)
);
utf8_serialized_chunk #(.USER_WIDTH(USER_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) serializer(
    .clk(clk),
    .rst(rst),
    .start_valid(link_s_start_valid),
    .start_ready(link_s_start_ready),
    .start_user(link_s_start_user),
    .start_eos(link_s_start_eos),
    .start_replace(link_s_start_replace),
    .start_carry(link_s_start_carry),
    .start_carry_count(link_s_start_carry_count),
    .start_format(link_s_start_format),
    .start_protobuf_field(link_s_start_protobuf_field),
    .s_axis_text_tdata(link_s_s_axis_text_tdata),
    .s_axis_text_tkeep(link_s_s_axis_text_tkeep),
    .s_axis_text_tvalid(link_s_s_axis_text_tvalid),
    .s_axis_text_tready(link_s_s_axis_text_tready),
    .s_axis_text_tlast(link_s_s_axis_text_tlast),
    .s_axis_text_tuser(link_s_s_axis_text_tuser),
    .s_axis_text_abort(link_s_s_axis_text_abort),
    .m_axis_tx_tdata(raw_data),
    .m_axis_tx_tkeep(raw_keep),
    .m_axis_tx_tvalid(raw_valid),
    .m_axis_tx_tready(raw_ready),
    .m_axis_tx_tlast(raw_last),
    .m_axis_tx_tuser(raw_user),
    .result_valid(link_s_result_valid),
    .result_ready(link_s_result_ready),
    .result_stage(link_s_result_stage),
    .result_status(link_s_result_status),
    .result_carry(link_s_result_carry),
    .result_carry_count(link_s_result_carry_count),
    .result_bytes(link_s_result_bytes),
    .result_user(),
    .idle(link_s_idle)
);
grpc_registered_input_framer #(.USER_WIDTH(USER_WIDTH),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)) framer(
    .clk(clk),
    .rst(rst||kill_ungranted),
    .start_valid(accept),
    .start_ready(framer_start_ready),
    .start_user(s_axis_tokens_tuser),
    .start_stream(s_stream),
    .cfg_peer_max_frame_bytes(cfg_peer_max_frame_bytes),
    .s_axis_message_tdata(raw_data),
    .s_axis_message_tkeep(raw_keep),
    .s_axis_message_tvalid(raw_valid&&active&&!kill_ungranted),
    .s_axis_message_tready(framer_message_ready),
    .s_axis_message_tlast(raw_last),
    .s_axis_message_tuser(owner),
    .s_axis_message_abort(raw_user!=result_application),
    .frame_req_valid(framer_valid),
    .frame_req_ready(frame_req_ready&&authorized&&seq_data_admit),
    .frame_req_user(frame_req_user),
    .frame_req_stream(frame_req_stream),
    .frame_req_max_bytes(frame_req_max_bytes),
    .frame_grant_bytes(frame_grant_bytes),
    .m_axis_tx_tdata(body_tdata),
    .m_axis_tx_tkeep(body_tkeep),
    .m_axis_tx_tvalid(body_tvalid),
    .m_axis_tx_tready(body_tready),
    .m_axis_tx_tlast(body_tlast),
    .m_axis_tx_tuser(body_tuser),
    .result_valid(framer_result),
    .result_ready(retire),
    .result_status(framer_status),
    .result_user(),
    .result_stream(),
    .result_message_bytes(framer_message_bytes),
    .result_wire_bytes(framer_wire_bytes),
    .result_frames(framer_frames),
    .result_tx_emitted(framer_tx_emitted),
    .idle(framer_idle)
);
grpc_rpc_envelope #(.USER_WIDTH(USER_WIDTH)) envelope(
    .clk(clk),
    .rst(rst),
    .accept(accept),
    .accept_user(s_axis_tokens_tuser),
    .accept_stream(s_stream),
    .rpc_valid(rpc_result_valid&&(!directory_requested||release_pending)),
    .rpc_status(rpc_status),
    .rpc_eos(result_eos),
    .rpc_format(transport_result_format),
    .header_intent(transport_header_intent),
    .headers_sent(transport_headers_sent),
    .framer_result(framer_result),
    .framer_status(framer_status),
    .matching_freeze(envelope_freeze),
    .wire_fenced(envelope_wire_fenced),
    .data_admit(seq_data_admit),
    .terminal_admit(seq_terminal),
    .private_failed(seq_private_failed),
    .drained(envelope_drained),
    .recovery_required(envelope_recovery_required),
    .expected_cancelled(seq_cancelled),
    .error_status(envelope_error_status),
    .error_memory_status(envelope_error_memory_status),
    .metadata_req_valid(transport_req_valid),
    .metadata_req_ready(transport_req_ready),
    .metadata_req_op(transport_req_op),
    .metadata_private_abort_proof(transport_private_abort_proof),
    .metadata_rsp_valid(transport_rsp_valid),
    .metadata_rsp_ready(transport_rsp_ready),
    .metadata_rsp_status(transport_rsp_status),
    .metadata_rsp_memory_status(transport_rsp_memory_status),
    .header_select(seq_header_select),
    .retire(retire),
    .idle(seq_idle),
    .header_wire_bytes(seq_header_bytes),
    .header_frames(seq_header_frames),
    .header_req_valid(header_req_valid),
    .header_req_ready(header_req_ready),
    .header_req_kind(header_req_kind),
    .header_req_encoding(header_req_encoding),
    .header_req_user(header_req_user),
    .header_req_stream(header_req_stream),
    .header_abort_valid(header_abort_valid),
    .header_abort_ready(header_abort_ready),
    .header_result_valid(header_result_valid),
    .header_result_ready(header_result_ready),
    .header_result_status(header_result_status),
    .header_result_tx_emitted(header_result_tx_emitted),
    .header_result_kind(header_result_kind),
    .header_result_wire_bytes(header_result_wire_bytes),
    .header_result_user(header_result_user),
    .header_result_stream(header_result_stream)
);
grpc_response_headers #(.USER_WIDTH(USER_WIDTH)) headers(
    .clk(clk),
    .rst(rst),
    .req_valid(header_req_valid),
    .req_ready(header_req_ready),
    .req_kind(header_req_kind),
    .req_encoding(header_req_encoding),
    .req_grpc_status(32'd0),
    .req_user(header_req_user),
    .req_stream(header_req_stream),
    .abort_valid(header_abort_valid),
    .abort_ready(header_abort_ready),
    .wire_fenced(envelope_wire_fenced),
    .m_axis_tx_tdata(header_tdata),
    .m_axis_tx_tkeep(header_tkeep),
    .m_axis_tx_tvalid(header_tvalid),
    .m_axis_tx_tready(header_tready),
    .m_axis_tx_tlast(header_tlast),
    .m_axis_tx_tuser(header_tuser),
    .result_valid(header_result_valid),
    .result_ready(header_result_ready),
    .result_status(header_result_status),
    .result_tx_emitted(header_result_tx_emitted),
    .result_kind(header_result_kind),
    .result_user(header_result_user),
    .result_stream(header_result_stream),
    .result_wire_bytes(header_result_wire_bytes),
    .idle(header_idle)
);endmodule
`default_nettype wire
