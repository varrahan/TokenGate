`timescale 1ns/1ps
`default_nettype none
// Generated logical partition. Physical transport is not implemented here.
// Admitted semantic gRPC -> actual Parser -> independent BoW -> full BPE -> DMA.
// A successful message lease retires only after the token DMA and completion.
module grpc_prefill_parser_partition #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,
    parameter integer FIFO_DEPTH=16,parameter integer MAX_TEXT_BYTES=16384,parameter integer MAX_FIELD_BYTES=16384
)(
    input wire  clk,
    input wire  rst,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes,
    input wire  queue_cfg_valid,
    output wire  queue_cfg_ready,
    input wire  queue_cfg_clear,
    input wire  maintenance_grant,
    input wire [MEMORY_ADDR_WIDTH-1:0] queue_cfg_base,
    input wire [MEMORY_ADDR_WIDTH:0] queue_cfg_bytes,
    output wire  queue_cfg_result_valid,
    input wire  queue_cfg_result_ready,
    output wire [7:0] queue_cfg_status,
    input wire  control_valid,
    output wire  control_ready,
    input wire [2:0] control_op,
    input wire [USER_WIDTH-1:0] control_user,
    input wire [USER_WIDTH-1:0] control_application,
    input wire [30:0] control_stream,
    input wire [31:0] control_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] control_address,
    input wire [MEMORY_ADDR_WIDTH-1:0] control_buffer_base,
    input wire [MEMORY_ADDR_WIDTH:0] control_buffer_bytes,
    input wire [31:0] control_message_limit,
    input wire  control_protobuf,
    input wire  control_unsupported_encoding,
    input wire  control_maintenance,
    output wire  control_result_valid,
    input wire  control_result_ready,
    output wire [7:0] control_status,
    output wire [7:0] control_detail,
    output wire [7:0] control_memory_status,
    output wire [2:0] control_result_op,
    output wire [MEMORY_ADDR_WIDTH-1:0] control_result_address,
    output wire [MEMORY_ADDR_WIDTH-1:0] control_result_buffer_base,
    output wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes,
    output wire [USER_WIDTH-1:0] control_result_user,
    output wire [USER_WIDTH-1:0] control_result_application,
    output wire [30:0] control_result_stream,
    output wire [31:0] control_result_generation,
    output wire [31:0] control_result_message_limit,
    output wire  control_result_protobuf,
    output wire  control_result_unsupported_encoding,
    output wire [255:0] control_result_state,
    input wire  packet_start_valid,
    output wire  packet_start_ready,
    input wire [USER_WIDTH-1:0] packet_start_user,
    input wire [31:0] packet_start_tag,
    input wire  s_valid,
    output wire  s_ready,
    input wire [1:0] s_kind,
    input wire [7:0] s_data,
    input wire [30:0] s_stream,
    input wire  prepare_valid,
    output wire  prepare_ready,
    output wire  prepared_valid,
    input wire  prepared_ready,
    output wire  prepared_failed,
    output wire [7:0] prepared_status,
    input wire  decision_valid,
    output wire  decision_ready,
    input wire  decision_commit,
    output wire  packet_result_valid,
    input wire  packet_result_ready,
    output wire  packet_committed,
    output wire [7:0] packet_status,
    output wire [7:0] packet_detail,
    output wire [7:0] packet_memory_status,
    output wire [USER_WIDTH-1:0] packet_user,
    output wire [31:0] packet_tag,
    output wire  rpc_error_valid,
    input wire  rpc_error_ready,
    output wire [7:0] rpc_error_status,
    output wire [7:0] rpc_error_detail,
    output wire [7:0] rpc_error_memory_status,
    output wire [USER_WIDTH-1:0] rpc_error_user,
    output wire [USER_WIDTH-1:0] rpc_error_application,
    output wire [30:0] rpc_error_stream,
    output wire [31:0] rpc_error_generation,
    output wire [31:0] rpc_error_packet_tag,
    output wire  stream_recovery_required,
    output wire [MEMORY_ADDR_WIDTH-1:0] stream_recovery_address,
    output wire  queue_recovery_required,
    output wire [7:0] queue_recovery_detail,
    output wire [7:0] queue_recovery_memory_status,
    output wire  retirement_pending,
    output wire [31:0] queued_count,
    output wire [31:0] pending_count,
    output wire  idle,
    output wire [12:0] mem_valid,
    input wire [12:0] mem_ready,
    output wire [12:0] mem_write,
    output wire [13*MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [51:0] mem_bytes,
    output wire [935:0] mem_data,
    input wire [12:0] mem_rsp_valid,
    output wire [12:0] mem_rsp_ready,
    input wire [935:0] mem_rsp_data,
    input wire [103:0] mem_rsp_status,
    input wire  admit_messages,
    input wire  stream_cfg_valid,
    output wire  stream_cfg_ready,
    output wire  stream_cfg_result_valid,
    input wire  stream_cfg_result_ready,
    output wire [7:0] stream_cfg_status,
    input wire  cfg_unlock,
    input wire  cfg_schema_valid,
    output wire  cfg_schema_ready,
    output wire  cfg_quiescent,
    input wire [3:0] cfg_schema_index,
    input wire [255:0] cfg_schema_key,
    input wire [5:0] cfg_schema_key_length,
    input wire  cfg_schema_json_enable,
    input wire [28:0] cfg_schema_field,
    input wire  cfg_schema_proto_enable,
    output wire  completion_valid,
    input wire  completion_ready,
    output wire [7:0] completion_status,
    output wire [7:0] completion_detail,
    output wire [7:0] completion_memory_status,
    output wire [USER_WIDTH-1:0] completion_user,
    output wire [USER_WIDTH-1:0] completion_application,
    output wire [30:0] completion_stream,
    output wire [31:0] completion_generation,
    output wire [31:0] completion_ordinal,
    output wire [31:0] completion_packet_tag,
    output wire  payload_lease_active,
    input wire [1:0] cfg_token_profile,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_class_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_hash_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_node_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_edge_base,
    input wire [31:0] cfg_token_node_count,
    input wire [31:0] cfg_token_edge_count,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_work_floor,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_scalar_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_merge_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_token_commit_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_token_scalar_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_token_merge_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_token_commit_bytes,
    output wire [511:0] m_axis_tokens_tdata,
    output wire [63:0] m_axis_tokens_tkeep,
    output wire  m_axis_tokens_tvalid,
    input wire  m_axis_tokens_tready,
    output wire  m_axis_tokens_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tokens_tuser,
    output wire [USER_WIDTH-1:0] dma_connection,
    output wire [30:0] dma_stream,
    output wire [31:0] dma_generation,
    output wire [31:0] dma_ordinal,
    output wire [31:0] dma_packet_tag,
    output wire [31:0] completion_count,
    output wire [7:0] completion_token_stage,
    output wire [7:0] completion_token_detail,
    output wire [7:0] completion_token_status,
    input wire [127:0] s_return_tdata,
    input wire [15:0] s_return_tkeep,
    input wire  s_return_tvalid,
    output wire  s_return_tready,
    input wire  s_return_tlast,
    input wire [USER_WIDTH-1:0] s_return_tuser,
    output wire [127:0] m_return_tdata,
    output wire [15:0] m_return_tkeep,
    output wire  m_return_tvalid,
    input wire  m_return_tready,
    output wire  m_return_tlast,
    output wire [USER_WIDTH-1:0] m_return_tuser
,
    output wire  link_f_bpe_admit_sequences,
    output wire [1:0] link_f_bpe_cfg_profile,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_class_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_hash_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_node_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_edge_base,
    output wire [31:0] link_f_bpe_cfg_node_count,
    output wire [31:0] link_f_bpe_cfg_edge_count,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_work_floor,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_scalar_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_merge_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_commit_base,
    output wire [MEMORY_ADDR_WIDTH:0] link_f_bpe_cfg_scalar_bytes,
    output wire [MEMORY_ADDR_WIDTH:0] link_f_bpe_cfg_merge_bytes,
    output wire [MEMORY_ADDR_WIDTH:0] link_f_bpe_cfg_commit_bytes,
    output wire [127:0] link_f_bpe_s_axis_text_tdata,
    output wire [15:0] link_f_bpe_s_axis_text_tkeep,
    output wire  link_f_bpe_s_axis_text_tvalid,
    input wire  link_f_bpe_s_axis_text_tready,
    output wire  link_f_bpe_s_axis_text_tlast,
    output wire [USER_WIDTH-1:0] link_f_bpe_s_axis_text_tuser,
    input wire  link_f_bpe_completion_valid,
    output wire  link_f_bpe_completion_ready,
    input wire  link_f_bpe_completion_failed,
    input wire [31:0] link_f_bpe_completion_count,
    input wire [USER_WIDTH-1:0] link_f_bpe_completion_user,
    input wire  link_f_bpe_error_valid,
    output wire  link_f_bpe_error_ready,
    input wire [7:0] link_f_bpe_error_stage,
    input wire [7:0] link_f_bpe_error_detail,
    input wire [7:0] link_f_bpe_error_status,
    input wire [USER_WIDTH-1:0] link_f_bpe_error_user,
    input wire  link_f_bpe_idle,
    input wire  link_f_pack_idle
);
    wire parser_idle,parser_quiescent,token_idle,pack_idle;
    wire [127:0] parser_data,bow_data;wire [15:0] parser_keep,bow_keep;
    wire parser_valid,parser_ready,parser_last,bow_valid,bow_ready,bow_last;wire [USER_WIDTH-1:0] parser_user,bow_user;
    wire parser_completion_valid,token_completion_valid,token_failed,token_error_valid;wire [7:0] parser_status,parser_detail,parser_memory;
    wire [31:0] token_count;wire [USER_WIDTH-1:0] token_completion_user,token_error_user;
    wire [7:0] token_error_stage,token_error_detail,token_error_status;
    reg sequence_open,error_seen;reg [7:0] saved_stage,saved_detail,saved_status;
    reg [1:0] token_cfg_profile;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_class_base;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_hash_base;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_node_base;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_edge_base;
    reg [31:0] token_cfg_node_count;
    reg [31:0] token_cfg_edge_count;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_work_floor;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_scalar_base;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_merge_base;
    reg [MEMORY_ADDR_WIDTH-1:0] token_cfg_commit_base;
    reg [MEMORY_ADDR_WIDTH:0] token_cfg_scalar_bytes;
    reg [MEMORY_ADDR_WIDTH:0] token_cfg_merge_bytes;
    reg [MEMORY_ADDR_WIDTH:0] token_cfg_commit_bytes;
    grpc_ingress_parser #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)) parser(
        .clk(clk),
        .rst(rst),
        .cfg_stream_base(cfg_stream_base),
        .cfg_stream_bytes(cfg_stream_bytes),
        .queue_cfg_valid(queue_cfg_valid),
        .queue_cfg_ready(queue_cfg_ready),
        .queue_cfg_clear(queue_cfg_clear),
        .maintenance_grant(maintenance_grant),
        .queue_cfg_base(queue_cfg_base),
        .queue_cfg_bytes(queue_cfg_bytes),
        .queue_cfg_result_valid(queue_cfg_result_valid),
        .queue_cfg_result_ready(queue_cfg_result_ready),
        .queue_cfg_status(queue_cfg_status),
        .control_valid(control_valid),
        .control_ready(control_ready),
        .control_op(control_op),
        .control_user(control_user),
        .control_application(control_application),
        .control_stream(control_stream),
        .control_generation(control_generation),
        .control_address(control_address),
        .control_buffer_base(control_buffer_base),
        .control_buffer_bytes(control_buffer_bytes),
        .control_message_limit(control_message_limit),
        .control_protobuf(control_protobuf),
        .control_unsupported_encoding(control_unsupported_encoding),
        .control_maintenance(control_maintenance),
        .control_result_valid(control_result_valid),
        .control_result_ready(control_result_ready),
        .control_status(control_status),
        .control_detail(control_detail),
        .control_memory_status(control_memory_status),
        .control_result_op(control_result_op),
        .control_result_address(control_result_address),
        .control_result_buffer_base(control_result_buffer_base),
        .control_result_buffer_bytes(control_result_buffer_bytes),
        .control_result_user(control_result_user),
        .control_result_application(control_result_application),
        .control_result_stream(control_result_stream),
        .control_result_generation(control_result_generation),
        .control_result_message_limit(control_result_message_limit),
        .control_result_protobuf(control_result_protobuf),
        .control_result_unsupported_encoding(control_result_unsupported_encoding),
        .control_result_state(control_result_state),
        .packet_start_valid(packet_start_valid),
        .packet_start_ready(packet_start_ready),
        .packet_start_user(packet_start_user),
        .packet_start_tag(packet_start_tag),
        .s_valid(s_valid),
        .s_ready(s_ready),
        .s_kind(s_kind),
        .s_data(s_data),
        .s_stream(s_stream),
        .prepare_valid(prepare_valid),
        .prepare_ready(prepare_ready),
        .prepared_valid(prepared_valid),
        .prepared_ready(prepared_ready),
        .prepared_failed(prepared_failed),
        .prepared_status(prepared_status),
        .decision_valid(decision_valid),
        .decision_ready(decision_ready),
        .decision_commit(decision_commit),
        .packet_result_valid(packet_result_valid),
        .packet_result_ready(packet_result_ready),
        .packet_committed(packet_committed),
        .packet_status(packet_status),
        .packet_detail(packet_detail),
        .packet_memory_status(packet_memory_status),
        .packet_user(packet_user),
        .packet_tag(packet_tag),
        .rpc_error_valid(rpc_error_valid),
        .rpc_error_ready(rpc_error_ready),
        .rpc_error_status(rpc_error_status),
        .rpc_error_detail(rpc_error_detail),
        .rpc_error_memory_status(rpc_error_memory_status),
        .rpc_error_user(rpc_error_user),
        .rpc_error_application(rpc_error_application),
        .rpc_error_stream(rpc_error_stream),
        .rpc_error_generation(rpc_error_generation),
        .rpc_error_packet_tag(rpc_error_packet_tag),
        .stream_recovery_required(stream_recovery_required),
        .stream_recovery_address(stream_recovery_address),
        .queue_recovery_required(queue_recovery_required),
        .queue_recovery_detail(queue_recovery_detail),
        .queue_recovery_memory_status(queue_recovery_memory_status),
        .retirement_pending(retirement_pending),
        .queued_count(queued_count),
        .pending_count(pending_count),
        .idle(parser_idle),
        .mem_valid(mem_valid[4:0]),
        .mem_ready(mem_ready[4:0]),
        .mem_write(mem_write[4:0]),
        .mem_addr(mem_addr[0+:5*MEMORY_ADDR_WIDTH]),
        .mem_bytes(mem_bytes[19:0]),
        .mem_data(mem_data[359:0]),
        .mem_rsp_valid(mem_rsp_valid[4:0]),
        .mem_rsp_ready(mem_rsp_ready[4:0]),
        .mem_rsp_data(mem_rsp_data[359:0]),
        .mem_rsp_status(mem_rsp_status[39:0]),
        .admit_messages(admit_messages&&token_idle),
        .stream_cfg_valid(stream_cfg_valid),
        .stream_cfg_ready(stream_cfg_ready),
        .stream_cfg_result_valid(stream_cfg_result_valid),
        .stream_cfg_result_ready(stream_cfg_result_ready),
        .stream_cfg_status(stream_cfg_status),
        .cfg_unlock(cfg_unlock&&token_idle&&pack_idle&&!sequence_open),
        .cfg_schema_valid(cfg_schema_valid),
        .cfg_schema_ready(cfg_schema_ready),
        .cfg_quiescent(parser_quiescent),
        .cfg_schema_index(cfg_schema_index),
        .cfg_schema_key(cfg_schema_key),
        .cfg_schema_key_length(cfg_schema_key_length),
        .cfg_schema_json_enable(cfg_schema_json_enable),
        .cfg_schema_field(cfg_schema_field),
        .cfg_schema_proto_enable(cfg_schema_proto_enable),
        .m_axis_text_tdata(parser_data),
        .m_axis_text_tkeep(parser_keep),
        .m_axis_text_tvalid(parser_valid),
        .m_axis_text_tready(parser_ready),
        .m_axis_text_tlast(parser_last),
        .m_axis_text_tuser(parser_user),
        .text_connection(),
        .text_stream(),
        .text_generation(),
        .text_ordinal(),
        .text_packet_tag(),
        .completion_valid(parser_completion_valid),
        .completion_ready(completion_valid&&completion_ready),
        .completion_status(parser_status),
        .completion_detail(parser_detail),
        .completion_memory_status(parser_memory),
        .completion_user(completion_user),
        .completion_application(completion_application),
        .completion_stream(completion_stream),
        .completion_generation(completion_generation),
        .completion_ordinal(completion_ordinal),
        .completion_packet_tag(completion_packet_tag),
        .payload_lease_active(payload_lease_active)
    );
    bow_axi_bridge #(.USER_WIDTH(USER_WIDTH)) bow(
        .clk(clk),.rst(rst),.s_ingress_tdata(parser_data),.s_ingress_tkeep(parser_keep),.s_ingress_tvalid(parser_valid),.s_ingress_tready(parser_ready),.s_ingress_tlast(parser_last),.s_ingress_tuser(parser_user),
        .m_ingress_tdata(bow_data),.m_ingress_tkeep(bow_keep),.m_ingress_tvalid(bow_valid),.m_ingress_tready(bow_ready),.m_ingress_tlast(bow_last),.m_ingress_tuser(bow_user),
        .s_egress_tdata(s_return_tdata),.s_egress_tkeep(s_return_tkeep),.s_egress_tvalid(s_return_tvalid),.s_egress_tready(s_return_tready),.s_egress_tlast(s_return_tlast),.s_egress_tuser(s_return_tuser),
        .m_egress_tdata(m_return_tdata),.m_egress_tkeep(m_return_tkeep),.m_egress_tvalid(m_return_tvalid),.m_egress_tready(m_return_tready),.m_egress_tlast(m_return_tlast),.m_egress_tuser(m_return_tuser));
    wire [31:0] token_data;wire [3:0] token_keep;wire token_valid,token_ready,token_last;wire [USER_WIDTH-1:0] token_user;
    assign link_f_bpe_admit_sequences=sequence_open;
assign link_f_bpe_cfg_profile=token_cfg_profile;
assign link_f_bpe_cfg_class_base=token_cfg_class_base;
assign link_f_bpe_cfg_hash_base=token_cfg_hash_base;
assign link_f_bpe_cfg_node_base=token_cfg_node_base;
assign link_f_bpe_cfg_edge_base=token_cfg_edge_base;
assign link_f_bpe_cfg_node_count=token_cfg_node_count;
assign link_f_bpe_cfg_edge_count=token_cfg_edge_count;
assign link_f_bpe_cfg_work_floor=token_cfg_work_floor;
assign link_f_bpe_cfg_scalar_base=token_cfg_scalar_base;
assign link_f_bpe_cfg_merge_base=token_cfg_merge_base;
assign link_f_bpe_cfg_commit_base=token_cfg_commit_base;
assign link_f_bpe_cfg_scalar_bytes=token_cfg_scalar_bytes;
assign link_f_bpe_cfg_merge_bytes=token_cfg_merge_bytes;
assign link_f_bpe_cfg_commit_bytes=token_cfg_commit_bytes;
assign link_f_bpe_s_axis_text_tdata=bow_data;
assign link_f_bpe_s_axis_text_tkeep=bow_keep;
assign link_f_bpe_s_axis_text_tvalid=bow_valid;
assign bow_ready=link_f_bpe_s_axis_text_tready;
assign link_f_bpe_s_axis_text_tlast=bow_last;
assign link_f_bpe_s_axis_text_tuser=bow_user;
assign token_completion_valid=link_f_bpe_completion_valid;
assign link_f_bpe_completion_ready=completion_valid&&completion_ready&&parser_status==0;
assign token_failed=link_f_bpe_completion_failed;
assign token_count=link_f_bpe_completion_count;
assign token_completion_user=link_f_bpe_completion_user;
assign token_error_valid=link_f_bpe_error_valid;
assign link_f_bpe_error_ready=!error_seen;
assign token_error_stage=link_f_bpe_error_stage;
assign token_error_detail=link_f_bpe_error_detail;
assign token_error_status=link_f_bpe_error_status;
assign token_error_user=link_f_bpe_error_user;
assign mem_valid[12:5]=0;
assign mem_write[12:5]=0;
assign mem_addr[5*MEMORY_ADDR_WIDTH+:8*MEMORY_ADDR_WIDTH]=0;
assign mem_bytes[20+:32]=0;
assign mem_data[360+:576]=0;
assign mem_rsp_ready[12:5]=0;
assign token_idle=link_f_bpe_idle;
    assign m_axis_tokens_tdata=0;
assign m_axis_tokens_tkeep=0;
assign m_axis_tokens_tvalid=0;
assign m_axis_tokens_tlast=0;
assign m_axis_tokens_tuser=0;
assign pack_idle=link_f_pack_idle;
    assign completion_valid=parser_completion_valid&&(parser_status!=0||token_completion_valid&&pack_idle);
    assign completion_status=parser_status!=0?parser_status:token_failed?8'd7:8'd0;
    assign completion_detail=parser_status!=0?parser_detail:saved_detail;
    assign completion_memory_status=parser_status!=0?parser_memory:saved_status;
    assign completion_count=parser_status!=0?32'd0:token_count;
    assign completion_token_stage=parser_status==0?saved_stage:8'd0;
    assign completion_token_detail=parser_status==0?saved_detail:8'd0;
    assign completion_token_status=parser_status==0?saved_status:8'd0;
    assign dma_connection=completion_user;assign dma_stream=completion_stream;assign dma_generation=completion_generation;
    assign dma_ordinal=completion_ordinal;assign dma_packet_tag=completion_packet_tag;
    assign cfg_quiescent=parser_quiescent&&token_idle&&pack_idle&&!sequence_open;
    assign idle=parser_idle&&token_idle&&pack_idle&&!sequence_open&&!parser_valid&&!bow_valid&&!m_return_tvalid&&!s_return_tvalid;
    always @(posedge clk)begin
        if(rst)begin sequence_open<=0;error_seen<=0;saved_stage<=0;saved_detail<=0;saved_status<=0;token_cfg_profile<=0;token_cfg_class_base<=0;token_cfg_hash_base<=0;token_cfg_node_base<=0;token_cfg_edge_base<=0;token_cfg_node_count<=0;token_cfg_edge_count<=0;token_cfg_work_floor<=0;token_cfg_scalar_base<=0;token_cfg_merge_base<=0;token_cfg_commit_base<=0;token_cfg_scalar_bytes<=0;token_cfg_merge_bytes<=0;token_cfg_commit_bytes<=0;end
        else begin
            if(parser_valid&&parser_ready&&!sequence_open)begin
                sequence_open<=1;
                token_cfg_profile<=cfg_token_profile;
                token_cfg_class_base<=cfg_token_class_base;
                token_cfg_hash_base<=cfg_token_hash_base;
                token_cfg_node_base<=cfg_token_node_base;
                token_cfg_edge_base<=cfg_token_edge_base;
                token_cfg_node_count<=cfg_token_node_count;
                token_cfg_edge_count<=cfg_token_edge_count;
                token_cfg_work_floor<=cfg_token_work_floor;
                token_cfg_scalar_base<=cfg_token_scalar_base;
                token_cfg_merge_base<=cfg_token_merge_base;
                token_cfg_commit_base<=cfg_token_commit_base;
                token_cfg_scalar_bytes<=cfg_token_scalar_bytes;
                token_cfg_merge_bytes<=cfg_token_merge_bytes;
                token_cfg_commit_bytes<=cfg_token_commit_bytes;
            end
            if(token_error_valid&&!error_seen)begin error_seen<=1;saved_stage<=token_error_stage;saved_detail<=token_error_detail;saved_status<=token_error_status;end
            if(completion_valid&&completion_ready)begin sequence_open<=0;error_seen<=0;saved_stage<=0;saved_detail<=0;saved_status<=0;end
        end
    end
endmodule
`default_nettype wire

