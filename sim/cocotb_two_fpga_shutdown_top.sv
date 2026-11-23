`timescale 1ns/1ps
`default_nettype none
// Passive fixture: separate production applications and local fabrics.
module cocotb_two_fpga_shutdown_top;
localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
reg  clk=0;
reg  rst=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
reg  queue_cfg_valid=0;
wire  queue_cfg_ready;
reg  queue_cfg_clear=0;
reg  maintenance_grant=0;
reg [MEMORY_ADDR_WIDTH-1:0] queue_cfg_base=0;
reg [MEMORY_ADDR_WIDTH:0] queue_cfg_bytes=0;
wire  queue_cfg_result_valid;
reg  queue_cfg_result_ready=0;
wire [7:0] queue_cfg_status;
reg  control_valid=0;
wire  control_ready;
reg [2:0] control_op=0;
reg [USER_WIDTH-1:0] control_user=0;
reg [USER_WIDTH-1:0] control_application=0;
reg [30:0] control_stream=0;
reg [31:0] control_generation=0;
reg [MEMORY_ADDR_WIDTH-1:0] control_address=0;
reg [MEMORY_ADDR_WIDTH-1:0] control_buffer_base=0;
reg [MEMORY_ADDR_WIDTH:0] control_buffer_bytes=0;
reg [31:0] control_message_limit=0;
reg  control_protobuf=0;
reg  control_unsupported_encoding=0;
reg  control_maintenance=0;
wire  control_result_valid;
reg  control_result_ready=0;
wire [7:0] control_status;
wire [7:0] control_detail;
wire [7:0] control_memory_status;
wire [2:0] control_result_op;
wire [MEMORY_ADDR_WIDTH-1:0] control_result_address;
wire [MEMORY_ADDR_WIDTH-1:0] control_result_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes;
wire [USER_WIDTH-1:0] control_result_user;
wire [USER_WIDTH-1:0] control_result_application;
wire [30:0] control_result_stream;
wire [31:0] control_result_generation;
wire [31:0] control_result_message_limit;
wire  control_result_protobuf;
wire  control_result_unsupported_encoding;
wire [255:0] control_result_state;
wire  packet_result_valid;
reg  packet_result_ready=0;
wire  packet_committed;
wire [7:0] packet_status;
wire [7:0] packet_detail;
wire [7:0] packet_memory_status;
wire [USER_WIDTH-1:0] packet_user;
wire [31:0] packet_tag;
wire  rpc_error_valid;
reg  rpc_error_ready=0;
wire [7:0] rpc_error_status;
wire [7:0] rpc_error_detail;
wire [7:0] rpc_error_memory_status;
wire [USER_WIDTH-1:0] rpc_error_user;
wire [USER_WIDTH-1:0] rpc_error_application;
wire [30:0] rpc_error_stream;
wire [31:0] rpc_error_generation;
wire [31:0] rpc_error_packet_tag;
wire  stream_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] stream_recovery_address;
wire  queue_recovery_required;
wire [7:0] queue_recovery_detail;
wire [7:0] queue_recovery_memory_status;
wire  retirement_pending;
wire [31:0] queued_count;
wire [31:0] pending_count;
reg  admit_messages=0;
reg  stream_cfg_valid=0;
wire  stream_cfg_ready;
wire  stream_cfg_result_valid;
reg  stream_cfg_result_ready=0;
wire [7:0] stream_cfg_status;
reg  cfg_unlock=0;
reg  cfg_schema_valid=0;
wire  cfg_schema_ready;
wire  cfg_quiescent;
reg [3:0] cfg_schema_index=0;
reg [255:0] cfg_schema_key=0;
reg [5:0] cfg_schema_key_length=0;
reg  cfg_schema_json_enable=0;
reg [28:0] cfg_schema_field=0;
reg  cfg_schema_proto_enable=0;
wire  completion_valid;
reg  completion_ready=0;
wire [7:0] completion_status;
wire [7:0] completion_detail;
wire [7:0] completion_memory_status;
wire [USER_WIDTH-1:0] completion_user;
wire [USER_WIDTH-1:0] completion_application;
wire [30:0] completion_stream;
wire [31:0] completion_generation;
wire [31:0] completion_ordinal;
wire [31:0] completion_packet_tag;
wire  payload_lease_active;
reg [1:0] cfg_token_profile=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_class_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_hash_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_node_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_edge_base=0;
reg [31:0] cfg_token_node_count=0;
reg [31:0] cfg_token_edge_count=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_work_floor=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_scalar_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_merge_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_token_commit_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_token_scalar_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_token_merge_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_token_commit_bytes=0;
wire [511:0] m_axis_tokens_tdata;
wire [63:0] m_axis_tokens_tkeep;
wire  m_axis_tokens_tvalid;
reg  m_axis_tokens_tready=0;
wire  m_axis_tokens_tlast;
wire [USER_WIDTH-1:0] m_axis_tokens_tuser;
wire [USER_WIDTH-1:0] dma_connection;
wire [30:0] dma_stream;
wire [31:0] dma_generation;
wire [31:0] dma_ordinal;
wire [31:0] dma_packet_tag;
wire [31:0] completion_count;
wire [7:0] completion_token_stage;
wire [7:0] completion_token_detail;
wire [7:0] completion_token_status;
reg  admit_packets=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
reg  command_valid=0;
wire  command_ready;
reg [1:0] command_op=0;
reg [USER_WIDTH-1:0] command_user=0;
reg  command_server_role=0;
reg  command_allow_push=0;
reg [23:0] command_max_frame_bytes=0;
reg [MEMORY_ADDR_WIDTH-1:0] command_buffer_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] command_table_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] command_scratch_base=0;
reg [MEMORY_ADDR_WIDTH:0] command_buffer_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] command_table_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] command_scratch_bytes=0;
reg [31:0] command_hpack_maximum=0;
reg [31:0] command_hpack_allowed=0;
reg [31:0] command_header_list_limit=0;
reg [31:0] command_required_maximum=0;
reg  command_required_update=0;
reg [511:0] s_axis_rx_tdata=0;
reg [63:0] s_axis_rx_tkeep=0;
reg  s_axis_rx_tvalid=0;
wire  s_axis_rx_tready;
reg  s_axis_rx_tlast=0;
reg [USER_WIDTH-1:0] s_axis_rx_tuser=0;
wire  rsp_valid;
reg  rsp_ready=0;
wire  rsp_is_command;
wire [1:0] rsp_command_op;
wire [7:0] rsp_status;
wire [7:0] rsp_detail;
wire [7:0] rsp_memory_status;
wire [31:0] rsp_http2_error;
wire [USER_WIDTH-1:0] rsp_user;
reg [31:0] s_axis_rx_tag=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_route_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_route_strings_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_payload_slot_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_route_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_route_strings_bytes=0;
reg [31:0] cfg_routes=0;
reg [31:0] cfg_model_epoch=0;
reg [31:0] cfg_schema_epoch=0;
wire  header_valid;
reg  header_ready=0;
wire [3:0] header_status;
wire [7:0] header_detail;
wire [7:0] header_memory_status;
wire [7:0] header_control_status;
wire [7:0] header_cleanup_status;
wire  header_connection_error;
wire [31:0] header_http2_error;
wire [9:0] header_http_status;
wire [7:0] header_grpc_status;
wire [USER_WIDTH-1:0] header_user;
wire [30:0] header_stream;
wire [31:0] header_generation;
wire [MEMORY_ADDR_WIDTH-1:0] header_address;
wire [15:0] header_application;
wire [31:0] header_model_epoch;
wire [31:0] header_schema_epoch;
wire  header_trailers;
wire  header_end_stream;
wire  admission_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] admission_recovery_address;
wire [USER_WIDTH-1:0] admission_recovery_user;
wire  transport_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] transport_recovery_address;
wire  control_event_valid;
reg  control_event_ready=0;
wire [3:0] control_event_kind;
wire [31:0] control_event_arg0;
wire [31:0] control_event_arg1;
wire [30:0] control_event_stream;
wire [USER_WIDTH-1:0] control_event_user;
wire [7:0] transport_packet_status;
wire [7:0] transport_packet_detail;
wire [7:0] transport_packet_memory_status;
wire [31:0] transport_packet_http2_error;
wire  idle;
wire [26*1-1:0] mem_valid;
wire [26*1-1:0] mem_ready;
wire [26*1-1:0] mem_write;
wire [26*MEMORY_ADDR_WIDTH-1:0] mem_addr;
wire [26*4-1:0] mem_bytes;
wire [26*72-1:0] mem_data;
wire [26*1-1:0] mem_rsp_valid;
wire [26*1-1:0] mem_rsp_ready;
wire [26*72-1:0] mem_rsp_data;
wire [26*8-1:0] mem_rsp_status;
reg [31:0] s_axis_generated_tdata=0;
reg [3:0] s_axis_generated_tkeep=0;
reg  s_axis_generated_tvalid=0;
wire  s_axis_generated_tready;
reg  s_axis_generated_tlast=0;
reg [USER_WIDTH-1:0] s_axis_generated_tuser=0;
reg [30:0] generated_stream=0;
reg [31:0] generated_generation=0;
reg [31:0] generated_model_epoch=0;
reg [31:0] generated_schema_epoch=0;
reg [31:0] generated_ordinal=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_response_progress_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_response_progress_bytes=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_response_directory_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_response_pool_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_response_directory_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_response_pool_bytes=0;
reg  cfg_response_strip_special=0;
reg  cfg_response_replace_invalid=0;
reg [1:0] cfg_response_format=0;
reg [28:0] cfg_response_protobuf_field=0;
wire [511:0] m_axis_tx_tdata;
wire [63:0] m_axis_tx_tkeep;
wire  m_axis_tx_tvalid;
reg  m_axis_tx_tready=0;
wire  m_axis_tx_tlast;
wire [USER_WIDTH-1:0] m_axis_tx_tuser;
wire  response_result_valid;
reg  response_result_ready=0;
wire [7:0] response_result_stage;
wire [7:0] response_result_status;
wire [7:0] response_result_memory_status;
wire [USER_WIDTH-1:0] response_result_user;
wire [USER_WIDTH-1:0] response_result_application;
wire [30:0] response_result_stream;
wire [31:0] response_result_generation;
wire [31:0] response_result_model_epoch;
wire [31:0] response_result_schema_epoch;
wire [31:0] response_result_ordinal;
wire [31:0] response_result_bytes;
wire  response_result_eos;
wire  response_result_tx_emitted;
wire  response_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] response_recovery_address;
wire  response_directory_lease_active;
wire  response_idle;
wire  link_f_bpe_admit_sequences;
wire [1:0] link_f_bpe_cfg_profile;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_class_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_hash_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_node_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_edge_base;
wire [31:0] link_f_bpe_cfg_node_count;
wire [31:0] link_f_bpe_cfg_edge_count;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_scalar_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_merge_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_f_bpe_cfg_commit_base;
wire [MEMORY_ADDR_WIDTH:0] link_f_bpe_cfg_scalar_bytes;
wire [MEMORY_ADDR_WIDTH:0] link_f_bpe_cfg_merge_bytes;
wire [MEMORY_ADDR_WIDTH:0] link_f_bpe_cfg_commit_bytes;
wire [127:0] link_f_bpe_s_axis_text_tdata;
wire [15:0] link_f_bpe_s_axis_text_tkeep;
wire  link_f_bpe_s_axis_text_tvalid;
wire  link_f_bpe_s_axis_text_tready;
wire  link_f_bpe_s_axis_text_tlast;
wire [USER_WIDTH-1:0] link_f_bpe_s_axis_text_tuser;
wire  link_f_bpe_completion_valid;
wire  link_f_bpe_completion_ready;
wire  link_f_bpe_completion_failed;
wire [31:0] link_f_bpe_completion_count;
wire [USER_WIDTH-1:0] link_f_bpe_completion_user;
wire  link_f_bpe_error_valid;
wire  link_f_bpe_error_ready;
wire [7:0] link_f_bpe_error_stage;
wire [7:0] link_f_bpe_error_detail;
wire [7:0] link_f_bpe_error_status;
wire [USER_WIDTH-1:0] link_f_bpe_error_user;
wire  link_f_bpe_idle;
wire  link_f_pack_idle;
wire [31:0] link_r_s_axis_tokens_tdata;
wire [3:0] link_r_s_axis_tokens_tkeep;
wire  link_r_s_axis_tokens_tvalid;
wire  link_r_s_axis_tokens_tready;
wire  link_r_s_axis_tokens_tlast;
wire [USER_WIDTH-1:0] link_r_s_axis_tokens_tuser;
wire  link_r_lease_valid;
wire [USER_WIDTH-1:0] link_r_lease_user;
wire [USER_WIDTH-1:0] link_r_lease_application;
wire [30:0] link_r_lease_stream;
wire [31:0] link_r_lease_generation;
wire [31:0] link_r_lease_model_epoch;
wire [31:0] link_r_lease_schema_epoch;
wire [31:0] link_r_cfg_active_model_epoch;
wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_directory_base;
wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_pool_base;
wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_directory_bytes;
wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_pool_bytes;
wire  link_r_cfg_strip_special;
wire  link_r_cfg_replace_invalid;
wire [1:0] link_r_cfg_format;
wire [28:0] link_r_cfg_protobuf_field;
wire [23:0] link_r_carry_in;
wire [1:0] link_r_carry_in_count;
wire  link_r_result_valid;
wire  link_r_result_ready;
wire [7:0] link_r_result_stage;
wire [7:0] link_r_result_status;
wire [7:0] link_r_result_memory_status;
wire [23:0] link_r_carry_out;
wire [1:0] link_r_carry_out_count;
wire [31:0] link_r_result_bytes;
wire  link_r_idle;
wire  link_s_start_valid;
wire  link_s_start_ready;
wire [USER_WIDTH-1:0] link_s_start_user;
wire  link_s_start_eos;
wire  link_s_start_replace;
wire [23:0] link_s_start_carry;
wire [1:0] link_s_start_carry_count;
wire [1:0] link_s_start_format;
wire [28:0] link_s_start_protobuf_field;
wire [127:0] link_s_s_axis_text_tdata;
wire [15:0] link_s_s_axis_text_tkeep;
wire  link_s_s_axis_text_tvalid;
wire  link_s_s_axis_text_tready;
wire  link_s_s_axis_text_tlast;
wire [USER_WIDTH-1:0] link_s_s_axis_text_tuser;
wire  link_s_s_axis_text_abort;
wire  link_s_result_valid;
wire  link_s_result_ready;
wire [7:0] link_s_result_stage;
wire [7:0] link_s_result_status;
wire [23:0] link_s_result_carry;
wire [1:0] link_s_result_carry_count;
wire [31:0] link_s_result_bytes;
wire  link_s_idle;
wire  flow_event_valid;
wire  flow_event_ready;
wire [3:0] flow_event_kind;
wire [7:0] flow_event_data;
wire [31:0] flow_event_arg0;
wire [31:0] flow_event_arg1;
wire [23:0] flow_event_length;
wire [7:0] flow_event_type;
wire [7:0] flow_event_flags;
wire [30:0] flow_event_stream;
wire [USER_WIDTH-1:0] flow_event_user;
reg [23:0] cfg_peer_max_frame_bytes=0;
wire [31:0] result_serialized_bytes;
wire [31:0] result_wire_bytes;
wire [31:0] result_frames;
wire  response_result_progress_committed;
wire  response_record_lease_active;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_window_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_window_bytes=0;
wire [7:0] header_window_status;
wire [7:0] command_window_status;
wire [7:0] command_window_cleanup_status;
reg  window_req_valid=0;
wire  window_req_ready;
reg [3:0] window_req_op=0;
reg  window_req_maintenance=0;
reg [USER_WIDTH-1:0] window_req_user=0;
reg [30:0] window_req_stream=0;
reg [31:0] window_req_generation=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_req_record_address=0;
reg [31:0] window_req_amount=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_window_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] window_cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH:0] window_cfg_context_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] window_cfg_stream_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] window_cfg_window_bytes=0;
wire  window_rsp_valid;
reg  window_rsp_ready=0;
wire [3:0] window_rsp_op;
wire [USER_WIDTH-1:0] window_rsp_user;
wire [30:0] window_rsp_stream;
wire [7:0] window_rsp_status;
wire [7:0] window_rsp_detail;
wire [7:0] window_rsp_memory_status;
wire  window_rsp_connection_error;
wire [31:0] window_rsp_http2_error;
wire [23:0] window_rsp_grant_bytes;
wire [31:0] window_rsp_connection_window;
wire [31:0] window_rsp_initial_window;
wire [31:0] window_rsp_stream_window;
wire [23:0] window_rsp_max_frame_bytes;
wire [31:0] window_rsp_affected_streams;
wire  window_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] window_recovery_address;
wire  window_busy;
wire [7:0] window_lock_status;
wire  credit_parked;
wire  directory_pool_lock_active;
wire [7:0] response_result_credit_status;
wire [7:0] response_result_credit_detail;
wire [31:0] response_result_credit_http2_error;
wire  response_result_credit_connection_error;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_control_journal_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_control_journal_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_control_slot_bytes=0;
wire [7:0] command_control_status;
wire [7:0] packet_control_status;
wire [7:0] packet_control_detail;
wire [7:0] packet_control_memory_status;
wire [7:0] journal_control_status;
wire [7:0] journal_control_detail;
wire [7:0] journal_control_memory_status;
wire  journal_control_connection_error;
wire [31:0] journal_control_http2_error;
wire [31:0] journal_control_frames;
wire [31:0] journal_control_ack_frames;
wire [31:0] journal_control_window_updates;
wire  cancel_valid;
wire  cancel_ready;
wire [USER_WIDTH-1:0] cancel_user;
wire  cancel_goaway;
wire [30:0] cancel_stream;
wire [31:0] cancel_arg0;
wire [31:0] cancel_arg1;
wire  cancel_result_valid;
wire  cancel_result_ready;
wire [7:0] cancel_status;
wire  journal_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] journal_recovery_address;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_peer_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_peer_bytes=0;
wire [7:0] peer_format_status;
wire [7:0] peer_format_memory_status;
wire [7:0] history_status;
wire [7:0] history_detail;
wire [7:0] history_memory_status;
wire  history_closed;
wire [30:0] history_last_stream;
wire [31:0] history_queries;
wire  response_result_cancelled;
wire  response_result_retirement_pending;
wire  shutdown_busy;
wire  shutdown_recovery_required;
wire  reset_processed;
wire [31:0] resets_processed;
wire [31:0] goaways_processed;
wire [7:0] shutdown_status;
wire [7:0] shutdown_detail;
wire [7:0] shutdown_memory_status;
wire  peer_goaway_received;
wire [30:0] peer_goaway_last_stream;
wire [31:0] peer_goaway_error;
wire [17*1-1:0] p_mem_valid;
wire [17*1-1:0] p_mem_ready;
wire [17*1-1:0] p_mem_write;
wire [17*MEMORY_ADDR_WIDTH-1:0] p_mem_addr;
wire [17*4-1:0] p_mem_bytes;
wire [17*72-1:0] p_mem_data;
wire [17*1-1:0] p_mem_rsp_valid;
wire [17*1-1:0] p_mem_rsp_ready;
wire [17*72-1:0] p_mem_rsp_data;
wire [17*8-1:0] p_mem_rsp_status;
wire [17*8-1:0] p_fabric_status;wire p_fabric_idle;
wire [9*1-1:0] t_mem_valid;
wire [9*1-1:0] t_mem_ready;
wire [9*1-1:0] t_mem_write;
wire [9*MEMORY_ADDR_WIDTH-1:0] t_mem_addr;
wire [9*4-1:0] t_mem_bytes;
wire [9*72-1:0] t_mem_data;
wire [9*1-1:0] t_mem_rsp_valid;
wire [9*1-1:0] t_mem_rsp_ready;
wire [9*72-1:0] t_mem_rsp_data;
wire [9*8-1:0] t_mem_rsp_status;
wire [9*8-1:0] t_fabric_status;wire t_fabric_idle;
http2_shutdown_parser_application #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) dut(
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
    .admit_messages(admit_messages),
    .stream_cfg_valid(stream_cfg_valid),
    .stream_cfg_ready(stream_cfg_ready),
    .stream_cfg_result_valid(stream_cfg_result_valid),
    .stream_cfg_result_ready(stream_cfg_result_ready),
    .stream_cfg_status(stream_cfg_status),
    .cfg_unlock(cfg_unlock),
    .cfg_schema_valid(cfg_schema_valid),
    .cfg_schema_ready(cfg_schema_ready),
    .cfg_quiescent(cfg_quiescent),
    .cfg_schema_index(cfg_schema_index),
    .cfg_schema_key(cfg_schema_key),
    .cfg_schema_key_length(cfg_schema_key_length),
    .cfg_schema_json_enable(cfg_schema_json_enable),
    .cfg_schema_field(cfg_schema_field),
    .cfg_schema_proto_enable(cfg_schema_proto_enable),
    .completion_valid(completion_valid),
    .completion_ready(completion_ready),
    .completion_status(completion_status),
    .completion_detail(completion_detail),
    .completion_memory_status(completion_memory_status),
    .completion_user(completion_user),
    .completion_application(completion_application),
    .completion_stream(completion_stream),
    .completion_generation(completion_generation),
    .completion_ordinal(completion_ordinal),
    .completion_packet_tag(completion_packet_tag),
    .payload_lease_active(payload_lease_active),
    .cfg_token_profile(cfg_token_profile),
    .cfg_token_class_base(cfg_token_class_base),
    .cfg_token_hash_base(cfg_token_hash_base),
    .cfg_token_node_base(cfg_token_node_base),
    .cfg_token_edge_base(cfg_token_edge_base),
    .cfg_token_node_count(cfg_token_node_count),
    .cfg_token_edge_count(cfg_token_edge_count),
    .cfg_token_work_floor(cfg_token_work_floor),
    .cfg_token_scalar_base(cfg_token_scalar_base),
    .cfg_token_merge_base(cfg_token_merge_base),
    .cfg_token_commit_base(cfg_token_commit_base),
    .cfg_token_scalar_bytes(cfg_token_scalar_bytes),
    .cfg_token_merge_bytes(cfg_token_merge_bytes),
    .cfg_token_commit_bytes(cfg_token_commit_bytes),
    .dma_connection(dma_connection),
    .dma_stream(dma_stream),
    .dma_generation(dma_generation),
    .dma_ordinal(dma_ordinal),
    .dma_packet_tag(dma_packet_tag),
    .completion_count(completion_count),
    .completion_token_stage(completion_token_stage),
    .completion_token_detail(completion_token_detail),
    .completion_token_status(completion_token_status),
    .admit_packets(admit_packets),
    .cfg_context_base(cfg_context_base),
    .cfg_context_bytes(cfg_context_bytes),
    .command_valid(command_valid),
    .command_ready(command_ready),
    .command_op(command_op),
    .command_user(command_user),
    .command_server_role(command_server_role),
    .command_allow_push(command_allow_push),
    .command_max_frame_bytes(command_max_frame_bytes),
    .command_buffer_base(command_buffer_base),
    .command_table_base(command_table_base),
    .command_scratch_base(command_scratch_base),
    .command_buffer_bytes(command_buffer_bytes),
    .command_table_bytes(command_table_bytes),
    .command_scratch_bytes(command_scratch_bytes),
    .command_hpack_maximum(command_hpack_maximum),
    .command_hpack_allowed(command_hpack_allowed),
    .command_header_list_limit(command_header_list_limit),
    .command_required_maximum(command_required_maximum),
    .command_required_update(command_required_update),
    .s_axis_rx_tdata(s_axis_rx_tdata),
    .s_axis_rx_tkeep(s_axis_rx_tkeep),
    .s_axis_rx_tvalid(s_axis_rx_tvalid),
    .s_axis_rx_tready(s_axis_rx_tready),
    .s_axis_rx_tlast(s_axis_rx_tlast),
    .s_axis_rx_tuser(s_axis_rx_tuser),
    .rsp_valid(rsp_valid),
    .rsp_ready(rsp_ready),
    .rsp_is_command(rsp_is_command),
    .rsp_command_op(rsp_command_op),
    .rsp_status(rsp_status),
    .rsp_detail(rsp_detail),
    .rsp_memory_status(rsp_memory_status),
    .rsp_http2_error(rsp_http2_error),
    .rsp_user(rsp_user),
    .s_axis_rx_tag(s_axis_rx_tag),
    .cfg_payload_base(cfg_payload_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_route_base(cfg_route_base),
    .cfg_route_strings_base(cfg_route_strings_base),
    .cfg_payload_bytes(cfg_payload_bytes),
    .cfg_payload_slot_bytes(cfg_payload_slot_bytes),
    .cfg_route_bytes(cfg_route_bytes),
    .cfg_route_strings_bytes(cfg_route_strings_bytes),
    .cfg_routes(cfg_routes),
    .cfg_model_epoch(cfg_model_epoch),
    .cfg_schema_epoch(cfg_schema_epoch),
    .header_valid(header_valid),
    .header_ready(header_ready),
    .header_status(header_status),
    .header_detail(header_detail),
    .header_memory_status(header_memory_status),
    .header_control_status(header_control_status),
    .header_cleanup_status(header_cleanup_status),
    .header_connection_error(header_connection_error),
    .header_http2_error(header_http2_error),
    .header_http_status(header_http_status),
    .header_grpc_status(header_grpc_status),
    .header_user(header_user),
    .header_stream(header_stream),
    .header_generation(header_generation),
    .header_address(header_address),
    .header_application(header_application),
    .header_model_epoch(header_model_epoch),
    .header_schema_epoch(header_schema_epoch),
    .header_trailers(header_trailers),
    .header_end_stream(header_end_stream),
    .admission_recovery_required(admission_recovery_required),
    .admission_recovery_address(admission_recovery_address),
    .admission_recovery_user(admission_recovery_user),
    .transport_recovery_required(transport_recovery_required),
    .transport_recovery_address(transport_recovery_address),
    .control_event_valid(control_event_valid),
    .control_event_ready(control_event_ready),
    .control_event_kind(control_event_kind),
    .control_event_arg0(control_event_arg0),
    .control_event_arg1(control_event_arg1),
    .control_event_stream(control_event_stream),
    .control_event_user(control_event_user),
    .transport_packet_status(transport_packet_status),
    .transport_packet_detail(transport_packet_detail),
    .transport_packet_memory_status(transport_packet_memory_status),
    .transport_packet_http2_error(transport_packet_http2_error),
    .idle(idle),
    .mem_valid(p_mem_valid),
    .mem_ready(p_mem_ready),
    .mem_write(p_mem_write),
    .mem_addr(p_mem_addr),
    .mem_bytes(p_mem_bytes),
    .mem_data(p_mem_data),
    .mem_rsp_valid(p_mem_rsp_valid),
    .mem_rsp_ready(p_mem_rsp_ready),
    .mem_rsp_data(p_mem_rsp_data),
    .mem_rsp_status(p_mem_rsp_status),
    .s_axis_generated_tdata(s_axis_generated_tdata),
    .s_axis_generated_tkeep(s_axis_generated_tkeep),
    .s_axis_generated_tvalid(s_axis_generated_tvalid),
    .s_axis_generated_tready(s_axis_generated_tready),
    .s_axis_generated_tlast(s_axis_generated_tlast),
    .s_axis_generated_tuser(s_axis_generated_tuser),
    .generated_stream(generated_stream),
    .generated_generation(generated_generation),
    .generated_model_epoch(generated_model_epoch),
    .generated_schema_epoch(generated_schema_epoch),
    .generated_ordinal(generated_ordinal),
    .cfg_response_progress_base(cfg_response_progress_base),
    .cfg_response_progress_bytes(cfg_response_progress_bytes),
    .cfg_response_directory_base(cfg_response_directory_base),
    .cfg_response_pool_base(cfg_response_pool_base),
    .cfg_response_directory_bytes(cfg_response_directory_bytes),
    .cfg_response_pool_bytes(cfg_response_pool_bytes),
    .cfg_response_strip_special(cfg_response_strip_special),
    .cfg_response_replace_invalid(cfg_response_replace_invalid),
    .cfg_response_format(cfg_response_format),
    .cfg_response_protobuf_field(cfg_response_protobuf_field),
    .m_axis_tx_tdata(m_axis_tx_tdata),
    .m_axis_tx_tkeep(m_axis_tx_tkeep),
    .m_axis_tx_tvalid(m_axis_tx_tvalid),
    .m_axis_tx_tready(m_axis_tx_tready),
    .m_axis_tx_tlast(m_axis_tx_tlast),
    .m_axis_tx_tuser(m_axis_tx_tuser),
    .response_result_valid(response_result_valid),
    .response_result_ready(response_result_ready),
    .response_result_stage(response_result_stage),
    .response_result_status(response_result_status),
    .response_result_memory_status(response_result_memory_status),
    .response_result_user(response_result_user),
    .response_result_application(response_result_application),
    .response_result_stream(response_result_stream),
    .response_result_generation(response_result_generation),
    .response_result_model_epoch(response_result_model_epoch),
    .response_result_schema_epoch(response_result_schema_epoch),
    .response_result_ordinal(response_result_ordinal),
    .response_result_bytes(response_result_bytes),
    .response_result_eos(response_result_eos),
    .response_result_tx_emitted(response_result_tx_emitted),
    .response_recovery_required(response_recovery_required),
    .response_recovery_address(response_recovery_address),
    .response_directory_lease_active(response_directory_lease_active),
    .response_idle(response_idle),
    .link_f_bpe_admit_sequences(link_f_bpe_admit_sequences),
    .link_f_bpe_cfg_profile(link_f_bpe_cfg_profile),
    .link_f_bpe_cfg_class_base(link_f_bpe_cfg_class_base),
    .link_f_bpe_cfg_hash_base(link_f_bpe_cfg_hash_base),
    .link_f_bpe_cfg_node_base(link_f_bpe_cfg_node_base),
    .link_f_bpe_cfg_edge_base(link_f_bpe_cfg_edge_base),
    .link_f_bpe_cfg_node_count(link_f_bpe_cfg_node_count),
    .link_f_bpe_cfg_edge_count(link_f_bpe_cfg_edge_count),
    .link_f_bpe_cfg_work_floor(link_f_bpe_cfg_work_floor),
    .link_f_bpe_cfg_scalar_base(link_f_bpe_cfg_scalar_base),
    .link_f_bpe_cfg_merge_base(link_f_bpe_cfg_merge_base),
    .link_f_bpe_cfg_commit_base(link_f_bpe_cfg_commit_base),
    .link_f_bpe_cfg_scalar_bytes(link_f_bpe_cfg_scalar_bytes),
    .link_f_bpe_cfg_merge_bytes(link_f_bpe_cfg_merge_bytes),
    .link_f_bpe_cfg_commit_bytes(link_f_bpe_cfg_commit_bytes),
    .link_f_bpe_s_axis_text_tdata(link_f_bpe_s_axis_text_tdata),
    .link_f_bpe_s_axis_text_tkeep(link_f_bpe_s_axis_text_tkeep),
    .link_f_bpe_s_axis_text_tvalid(link_f_bpe_s_axis_text_tvalid),
    .link_f_bpe_s_axis_text_tready(link_f_bpe_s_axis_text_tready),
    .link_f_bpe_s_axis_text_tlast(link_f_bpe_s_axis_text_tlast),
    .link_f_bpe_s_axis_text_tuser(link_f_bpe_s_axis_text_tuser),
    .link_f_bpe_completion_valid(link_f_bpe_completion_valid),
    .link_f_bpe_completion_ready(link_f_bpe_completion_ready),
    .link_f_bpe_completion_failed(link_f_bpe_completion_failed),
    .link_f_bpe_completion_count(link_f_bpe_completion_count),
    .link_f_bpe_completion_user(link_f_bpe_completion_user),
    .link_f_bpe_error_valid(link_f_bpe_error_valid),
    .link_f_bpe_error_ready(link_f_bpe_error_ready),
    .link_f_bpe_error_stage(link_f_bpe_error_stage),
    .link_f_bpe_error_detail(link_f_bpe_error_detail),
    .link_f_bpe_error_status(link_f_bpe_error_status),
    .link_f_bpe_error_user(link_f_bpe_error_user),
    .link_f_bpe_idle(link_f_bpe_idle),
    .link_f_pack_idle(link_f_pack_idle),
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
    .link_s_start_valid(link_s_start_valid),
    .link_s_start_ready(link_s_start_ready),
    .link_s_start_user(link_s_start_user),
    .link_s_start_eos(link_s_start_eos),
    .link_s_start_replace(link_s_start_replace),
    .link_s_start_carry(link_s_start_carry),
    .link_s_start_carry_count(link_s_start_carry_count),
    .link_s_start_format(link_s_start_format),
    .link_s_start_protobuf_field(link_s_start_protobuf_field),
    .link_s_s_axis_text_tdata(link_s_s_axis_text_tdata),
    .link_s_s_axis_text_tkeep(link_s_s_axis_text_tkeep),
    .link_s_s_axis_text_tvalid(link_s_s_axis_text_tvalid),
    .link_s_s_axis_text_tready(link_s_s_axis_text_tready),
    .link_s_s_axis_text_tlast(link_s_s_axis_text_tlast),
    .link_s_s_axis_text_tuser(link_s_s_axis_text_tuser),
    .link_s_s_axis_text_abort(link_s_s_axis_text_abort),
    .link_s_result_valid(link_s_result_valid),
    .link_s_result_ready(link_s_result_ready),
    .link_s_result_stage(link_s_result_stage),
    .link_s_result_status(link_s_result_status),
    .link_s_result_carry(link_s_result_carry),
    .link_s_result_carry_count(link_s_result_carry_count),
    .link_s_result_bytes(link_s_result_bytes),
    .link_s_idle(link_s_idle),
    .flow_event_valid(flow_event_valid),
    .flow_event_ready(flow_event_ready),
    .flow_event_kind(flow_event_kind),
    .flow_event_data(flow_event_data),
    .flow_event_arg0(flow_event_arg0),
    .flow_event_arg1(flow_event_arg1),
    .flow_event_length(flow_event_length),
    .flow_event_type(flow_event_type),
    .flow_event_flags(flow_event_flags),
    .flow_event_stream(flow_event_stream),
    .flow_event_user(flow_event_user),
    .cfg_peer_max_frame_bytes(cfg_peer_max_frame_bytes),
    .result_serialized_bytes(result_serialized_bytes),
    .result_wire_bytes(result_wire_bytes),
    .result_frames(result_frames),
    .response_result_progress_committed(response_result_progress_committed),
    .response_record_lease_active(response_record_lease_active),
    .cfg_window_base(cfg_window_base),
    .cfg_window_bytes(cfg_window_bytes),
    .header_window_status(header_window_status),
    .command_window_status(command_window_status),
    .command_window_cleanup_status(command_window_cleanup_status),
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
    .window_rsp_grant_bytes(window_rsp_grant_bytes),
    .window_rsp_connection_window(window_rsp_connection_window),
    .window_rsp_initial_window(window_rsp_initial_window),
    .window_rsp_stream_window(window_rsp_stream_window),
    .window_rsp_max_frame_bytes(window_rsp_max_frame_bytes),
    .window_rsp_affected_streams(window_rsp_affected_streams),
    .window_recovery_required(window_recovery_required),
    .window_recovery_address(window_recovery_address),
    .window_busy(window_busy),
    .window_lock_status(window_lock_status),
    .credit_parked(credit_parked),
    .directory_pool_lock_active(directory_pool_lock_active),
    .response_result_credit_status(response_result_credit_status),
    .response_result_credit_detail(response_result_credit_detail),
    .response_result_credit_http2_error(response_result_credit_http2_error),
    .response_result_credit_connection_error(response_result_credit_connection_error),
    .cfg_control_journal_base(cfg_control_journal_base),
    .cfg_control_journal_bytes(cfg_control_journal_bytes),
    .cfg_control_slot_bytes(cfg_control_slot_bytes),
    .command_control_status(command_control_status),
    .packet_control_status(packet_control_status),
    .packet_control_detail(packet_control_detail),
    .packet_control_memory_status(packet_control_memory_status),
    .journal_control_status(journal_control_status),
    .journal_control_detail(journal_control_detail),
    .journal_control_memory_status(journal_control_memory_status),
    .journal_control_connection_error(journal_control_connection_error),
    .journal_control_http2_error(journal_control_http2_error),
    .journal_control_frames(journal_control_frames),
    .journal_control_ack_frames(journal_control_ack_frames),
    .journal_control_window_updates(journal_control_window_updates),
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
    .journal_recovery_required(journal_recovery_required),
    .journal_recovery_address(journal_recovery_address),
    .cfg_peer_base(cfg_peer_base),
    .cfg_peer_bytes(cfg_peer_bytes),
    .peer_format_status(peer_format_status),
    .peer_format_memory_status(peer_format_memory_status),
    .history_status(history_status),
    .history_detail(history_detail),
    .history_memory_status(history_memory_status),
    .history_closed(history_closed),
    .history_last_stream(history_last_stream),
    .history_queries(history_queries),
    .response_result_cancelled(response_result_cancelled),
    .response_result_retirement_pending(response_result_retirement_pending),
    .shutdown_busy(shutdown_busy),
    .shutdown_recovery_required(shutdown_recovery_required),
    .reset_processed(reset_processed),
    .resets_processed(resets_processed),
    .goaways_processed(goaways_processed),
    .shutdown_status(shutdown_status),
    .shutdown_detail(shutdown_detail),
    .shutdown_memory_status(shutdown_memory_status),
    .peer_goaway_received(peer_goaway_received),
    .peer_goaway_last_stream(peer_goaway_last_stream),
    .peer_goaway_error(peer_goaway_error)
);
tokenizer_fpga_memory_subsystem #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) tokenizer(
    .clk(clk),
    .rst(rst),
    .link_f_bpe_admit_sequences(link_f_bpe_admit_sequences),
    .link_f_bpe_cfg_profile(link_f_bpe_cfg_profile),
    .link_f_bpe_cfg_class_base(link_f_bpe_cfg_class_base),
    .link_f_bpe_cfg_hash_base(link_f_bpe_cfg_hash_base),
    .link_f_bpe_cfg_node_base(link_f_bpe_cfg_node_base),
    .link_f_bpe_cfg_edge_base(link_f_bpe_cfg_edge_base),
    .link_f_bpe_cfg_node_count(link_f_bpe_cfg_node_count),
    .link_f_bpe_cfg_edge_count(link_f_bpe_cfg_edge_count),
    .link_f_bpe_cfg_work_floor(link_f_bpe_cfg_work_floor),
    .link_f_bpe_cfg_scalar_base(link_f_bpe_cfg_scalar_base),
    .link_f_bpe_cfg_merge_base(link_f_bpe_cfg_merge_base),
    .link_f_bpe_cfg_commit_base(link_f_bpe_cfg_commit_base),
    .link_f_bpe_cfg_scalar_bytes(link_f_bpe_cfg_scalar_bytes),
    .link_f_bpe_cfg_merge_bytes(link_f_bpe_cfg_merge_bytes),
    .link_f_bpe_cfg_commit_bytes(link_f_bpe_cfg_commit_bytes),
    .link_f_bpe_s_axis_text_tdata(link_f_bpe_s_axis_text_tdata),
    .link_f_bpe_s_axis_text_tkeep(link_f_bpe_s_axis_text_tkeep),
    .link_f_bpe_s_axis_text_tvalid(link_f_bpe_s_axis_text_tvalid),
    .link_f_bpe_s_axis_text_tready(link_f_bpe_s_axis_text_tready),
    .link_f_bpe_s_axis_text_tlast(link_f_bpe_s_axis_text_tlast),
    .link_f_bpe_s_axis_text_tuser(link_f_bpe_s_axis_text_tuser),
    .link_f_bpe_completion_valid(link_f_bpe_completion_valid),
    .link_f_bpe_completion_ready(link_f_bpe_completion_ready),
    .link_f_bpe_completion_failed(link_f_bpe_completion_failed),
    .link_f_bpe_completion_count(link_f_bpe_completion_count),
    .link_f_bpe_completion_user(link_f_bpe_completion_user),
    .link_f_bpe_error_valid(link_f_bpe_error_valid),
    .link_f_bpe_error_ready(link_f_bpe_error_ready),
    .link_f_bpe_error_stage(link_f_bpe_error_stage),
    .link_f_bpe_error_detail(link_f_bpe_error_detail),
    .link_f_bpe_error_status(link_f_bpe_error_status),
    .link_f_bpe_error_user(link_f_bpe_error_user),
    .link_f_bpe_idle(link_f_bpe_idle),
    .link_f_pack_idle(link_f_pack_idle),
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
    .link_s_start_valid(link_s_start_valid),
    .link_s_start_ready(link_s_start_ready),
    .link_s_start_user(link_s_start_user),
    .link_s_start_eos(link_s_start_eos),
    .link_s_start_replace(link_s_start_replace),
    .link_s_start_carry(link_s_start_carry),
    .link_s_start_carry_count(link_s_start_carry_count),
    .link_s_start_format(link_s_start_format),
    .link_s_start_protobuf_field(link_s_start_protobuf_field),
    .link_s_s_axis_text_tdata(link_s_s_axis_text_tdata),
    .link_s_s_axis_text_tkeep(link_s_s_axis_text_tkeep),
    .link_s_s_axis_text_tvalid(link_s_s_axis_text_tvalid),
    .link_s_s_axis_text_tready(link_s_s_axis_text_tready),
    .link_s_s_axis_text_tlast(link_s_s_axis_text_tlast),
    .link_s_s_axis_text_tuser(link_s_s_axis_text_tuser),
    .link_s_s_axis_text_abort(link_s_s_axis_text_abort),
    .link_s_result_valid(link_s_result_valid),
    .link_s_result_ready(link_s_result_ready),
    .link_s_result_stage(link_s_result_stage),
    .link_s_result_status(link_s_result_status),
    .link_s_result_carry(link_s_result_carry),
    .link_s_result_carry_count(link_s_result_carry_count),
    .link_s_result_bytes(link_s_result_bytes),
    .link_s_idle(link_s_idle),
    .m_axis_tokens_tdata(m_axis_tokens_tdata),
    .m_axis_tokens_tkeep(m_axis_tokens_tkeep),
    .m_axis_tokens_tvalid(m_axis_tokens_tvalid),
    .m_axis_tokens_tready(m_axis_tokens_tready),
    .m_axis_tokens_tlast(m_axis_tokens_tlast),
    .m_axis_tokens_tuser(m_axis_tokens_tuser),
    .cfg_invalidate_valid(1'b0),
    .cfg_invalidate_ready(),
    .memory_idle(t_fabric_idle),
    .m_axi_araddr(t_axi_araddr),
    .m_axi_arlen(t_axi_arlen),
    .m_axi_arsize(t_axi_arsize),
    .m_axi_arburst(t_axi_arburst),
    .m_axi_arvalid(t_axi_arvalid),
    .m_axi_arready(t_axi_arready),
    .m_axi_rdata(t_axi_rdata),
    .m_axi_rresp(t_axi_rresp),
    .m_axi_rlast(t_axi_rlast),
    .m_axi_rvalid(t_axi_rvalid),
    .m_axi_rready(t_axi_rready),
    .m_axi_awaddr(t_axi_awaddr),
    .m_axi_awlen(t_axi_awlen),
    .m_axi_awsize(t_axi_awsize),
    .m_axi_awburst(t_axi_awburst),
    .m_axi_awvalid(t_axi_awvalid),
    .m_axi_awready(t_axi_awready),
    .m_axi_wdata(t_axi_wdata),
    .m_axi_wstrb(t_axi_wstrb),
    .m_axi_wlast(t_axi_wlast),
    .m_axi_wvalid(t_axi_wvalid),
    .m_axi_wready(t_axi_wready),
    .m_axi_bresp(t_axi_bresp),
    .m_axi_bvalid(t_axi_bvalid),
    .m_axi_bready(t_axi_bready)
);
wire fabric_idle=p_fabric_idle&&t_fabric_idle;wire [26*8-1:0] fabric_status;
integer fault_client=-1,fault_target=-1,response_index=0;reg fault_arm=0,fault_injected=0;
assign mem_valid[1*1+:1]=p_mem_valid[0*1+:1];
assign mem_ready[1*1+:1]=p_mem_ready[0*1+:1];
assign mem_write[1*1+:1]=p_mem_write[0*1+:1];
assign mem_addr[1*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[0*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[1*4+:4]=p_mem_bytes[0*4+:4];
assign mem_data[1*72+:72]=p_mem_data[0*72+:72];
assign mem_rsp_valid[1*1+:1]=p_mem_rsp_valid[0*1+:1];
assign mem_rsp_ready[1*1+:1]=p_mem_rsp_ready[0*1+:1];
assign mem_rsp_data[1*72+:72]=p_mem_rsp_data[0*72+:72];
assign p_mem_rsp_status[0*8+:8]=mem_rsp_status[1*8+:8];
assign fabric_status[1*8+:8]=p_fabric_status[0*8+:8];
assign mem_valid[2*1+:1]=p_mem_valid[1*1+:1];
assign mem_ready[2*1+:1]=p_mem_ready[1*1+:1];
assign mem_write[2*1+:1]=p_mem_write[1*1+:1];
assign mem_addr[2*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[1*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[2*4+:4]=p_mem_bytes[1*4+:4];
assign mem_data[2*72+:72]=p_mem_data[1*72+:72];
assign mem_rsp_valid[2*1+:1]=p_mem_rsp_valid[1*1+:1];
assign mem_rsp_ready[2*1+:1]=p_mem_rsp_ready[1*1+:1];
assign mem_rsp_data[2*72+:72]=p_mem_rsp_data[1*72+:72];
assign p_mem_rsp_status[1*8+:8]=mem_rsp_status[2*8+:8];
assign fabric_status[2*8+:8]=p_fabric_status[1*8+:8];
assign mem_valid[3*1+:1]=p_mem_valid[2*1+:1];
assign mem_ready[3*1+:1]=p_mem_ready[2*1+:1];
assign mem_write[3*1+:1]=p_mem_write[2*1+:1];
assign mem_addr[3*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[2*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[3*4+:4]=p_mem_bytes[2*4+:4];
assign mem_data[3*72+:72]=p_mem_data[2*72+:72];
assign mem_rsp_valid[3*1+:1]=p_mem_rsp_valid[2*1+:1];
assign mem_rsp_ready[3*1+:1]=p_mem_rsp_ready[2*1+:1];
assign mem_rsp_data[3*72+:72]=p_mem_rsp_data[2*72+:72];
assign p_mem_rsp_status[2*8+:8]=mem_rsp_status[3*8+:8];
assign fabric_status[3*8+:8]=p_fabric_status[2*8+:8];
assign mem_valid[4*1+:1]=p_mem_valid[3*1+:1];
assign mem_ready[4*1+:1]=p_mem_ready[3*1+:1];
assign mem_write[4*1+:1]=p_mem_write[3*1+:1];
assign mem_addr[4*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[3*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[4*4+:4]=p_mem_bytes[3*4+:4];
assign mem_data[4*72+:72]=p_mem_data[3*72+:72];
assign mem_rsp_valid[4*1+:1]=p_mem_rsp_valid[3*1+:1];
assign mem_rsp_ready[4*1+:1]=p_mem_rsp_ready[3*1+:1];
assign mem_rsp_data[4*72+:72]=p_mem_rsp_data[3*72+:72];
assign p_mem_rsp_status[3*8+:8]=mem_rsp_status[4*8+:8];
assign fabric_status[4*8+:8]=p_fabric_status[3*8+:8];
assign mem_valid[13*1+:1]=p_mem_valid[4*1+:1];
assign mem_ready[13*1+:1]=p_mem_ready[4*1+:1];
assign mem_write[13*1+:1]=p_mem_write[4*1+:1];
assign mem_addr[13*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[4*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[13*4+:4]=p_mem_bytes[4*4+:4];
assign mem_data[13*72+:72]=p_mem_data[4*72+:72];
assign mem_rsp_valid[13*1+:1]=p_mem_rsp_valid[4*1+:1];
assign mem_rsp_ready[13*1+:1]=p_mem_rsp_ready[4*1+:1];
assign mem_rsp_data[13*72+:72]=p_mem_rsp_data[4*72+:72];
assign p_mem_rsp_status[4*8+:8]=mem_rsp_status[13*8+:8];
assign fabric_status[13*8+:8]=p_fabric_status[4*8+:8];
assign mem_valid[14*1+:1]=p_mem_valid[5*1+:1];
assign mem_ready[14*1+:1]=p_mem_ready[5*1+:1];
assign mem_write[14*1+:1]=p_mem_write[5*1+:1];
assign mem_addr[14*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[5*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[14*4+:4]=p_mem_bytes[5*4+:4];
assign mem_data[14*72+:72]=p_mem_data[5*72+:72];
assign mem_rsp_valid[14*1+:1]=p_mem_rsp_valid[5*1+:1];
assign mem_rsp_ready[14*1+:1]=p_mem_rsp_ready[5*1+:1];
assign mem_rsp_data[14*72+:72]=p_mem_rsp_data[5*72+:72];
assign p_mem_rsp_status[5*8+:8]=mem_rsp_status[14*8+:8];
assign fabric_status[14*8+:8]=p_fabric_status[5*8+:8];
assign mem_valid[15*1+:1]=p_mem_valid[6*1+:1];
assign mem_ready[15*1+:1]=p_mem_ready[6*1+:1];
assign mem_write[15*1+:1]=p_mem_write[6*1+:1];
assign mem_addr[15*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[6*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[15*4+:4]=p_mem_bytes[6*4+:4];
assign mem_data[15*72+:72]=p_mem_data[6*72+:72];
assign mem_rsp_valid[15*1+:1]=p_mem_rsp_valid[6*1+:1];
assign mem_rsp_ready[15*1+:1]=p_mem_rsp_ready[6*1+:1];
assign mem_rsp_data[15*72+:72]=p_mem_rsp_data[6*72+:72];
assign p_mem_rsp_status[6*8+:8]=mem_rsp_status[15*8+:8];
assign fabric_status[15*8+:8]=p_fabric_status[6*8+:8];
assign mem_valid[16*1+:1]=p_mem_valid[7*1+:1];
assign mem_ready[16*1+:1]=p_mem_ready[7*1+:1];
assign mem_write[16*1+:1]=p_mem_write[7*1+:1];
assign mem_addr[16*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[7*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[16*4+:4]=p_mem_bytes[7*4+:4];
assign mem_data[16*72+:72]=p_mem_data[7*72+:72];
assign mem_rsp_valid[16*1+:1]=p_mem_rsp_valid[7*1+:1];
assign mem_rsp_ready[16*1+:1]=p_mem_rsp_ready[7*1+:1];
assign mem_rsp_data[16*72+:72]=p_mem_rsp_data[7*72+:72];
assign p_mem_rsp_status[7*8+:8]=mem_rsp_status[16*8+:8];
assign fabric_status[16*8+:8]=p_fabric_status[7*8+:8];
assign mem_valid[17*1+:1]=p_mem_valid[8*1+:1];
assign mem_ready[17*1+:1]=p_mem_ready[8*1+:1];
assign mem_write[17*1+:1]=p_mem_write[8*1+:1];
assign mem_addr[17*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[8*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[17*4+:4]=p_mem_bytes[8*4+:4];
assign mem_data[17*72+:72]=p_mem_data[8*72+:72];
assign mem_rsp_valid[17*1+:1]=p_mem_rsp_valid[8*1+:1];
assign mem_rsp_ready[17*1+:1]=p_mem_rsp_ready[8*1+:1];
assign mem_rsp_data[17*72+:72]=p_mem_rsp_data[8*72+:72];
assign p_mem_rsp_status[8*8+:8]=mem_rsp_status[17*8+:8];
assign fabric_status[17*8+:8]=p_fabric_status[8*8+:8];
assign mem_valid[18*1+:1]=p_mem_valid[9*1+:1];
assign mem_ready[18*1+:1]=p_mem_ready[9*1+:1];
assign mem_write[18*1+:1]=p_mem_write[9*1+:1];
assign mem_addr[18*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[9*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[18*4+:4]=p_mem_bytes[9*4+:4];
assign mem_data[18*72+:72]=p_mem_data[9*72+:72];
assign mem_rsp_valid[18*1+:1]=p_mem_rsp_valid[9*1+:1];
assign mem_rsp_ready[18*1+:1]=p_mem_rsp_ready[9*1+:1];
assign mem_rsp_data[18*72+:72]=p_mem_rsp_data[9*72+:72];
assign p_mem_rsp_status[9*8+:8]=mem_rsp_status[18*8+:8];
assign fabric_status[18*8+:8]=p_fabric_status[9*8+:8];
assign mem_valid[19*1+:1]=p_mem_valid[10*1+:1];
assign mem_ready[19*1+:1]=p_mem_ready[10*1+:1];
assign mem_write[19*1+:1]=p_mem_write[10*1+:1];
assign mem_addr[19*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[10*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[19*4+:4]=p_mem_bytes[10*4+:4];
assign mem_data[19*72+:72]=p_mem_data[10*72+:72];
assign mem_rsp_valid[19*1+:1]=p_mem_rsp_valid[10*1+:1];
assign mem_rsp_ready[19*1+:1]=p_mem_rsp_ready[10*1+:1];
assign mem_rsp_data[19*72+:72]=p_mem_rsp_data[10*72+:72];
assign p_mem_rsp_status[10*8+:8]=mem_rsp_status[19*8+:8];
assign fabric_status[19*8+:8]=p_fabric_status[10*8+:8];
assign mem_valid[20*1+:1]=p_mem_valid[11*1+:1];
assign mem_ready[20*1+:1]=p_mem_ready[11*1+:1];
assign mem_write[20*1+:1]=p_mem_write[11*1+:1];
assign mem_addr[20*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[11*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[20*4+:4]=p_mem_bytes[11*4+:4];
assign mem_data[20*72+:72]=p_mem_data[11*72+:72];
assign mem_rsp_valid[20*1+:1]=p_mem_rsp_valid[11*1+:1];
assign mem_rsp_ready[20*1+:1]=p_mem_rsp_ready[11*1+:1];
assign mem_rsp_data[20*72+:72]=p_mem_rsp_data[11*72+:72];
assign p_mem_rsp_status[11*8+:8]=mem_rsp_status[20*8+:8];
assign fabric_status[20*8+:8]=p_fabric_status[11*8+:8];
assign mem_valid[0*1+:1]=p_mem_valid[12*1+:1];
assign mem_ready[0*1+:1]=p_mem_ready[12*1+:1];
assign mem_write[0*1+:1]=p_mem_write[12*1+:1];
assign mem_addr[0*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[12*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[0*4+:4]=p_mem_bytes[12*4+:4];
assign mem_data[0*72+:72]=p_mem_data[12*72+:72];
assign mem_rsp_valid[0*1+:1]=p_mem_rsp_valid[12*1+:1];
assign mem_rsp_ready[0*1+:1]=p_mem_rsp_ready[12*1+:1];
assign mem_rsp_data[0*72+:72]=p_mem_rsp_data[12*72+:72];
assign p_mem_rsp_status[12*8+:8]=mem_rsp_status[0*8+:8];
assign fabric_status[0*8+:8]=p_fabric_status[12*8+:8];
assign mem_valid[22*1+:1]=p_mem_valid[13*1+:1];
assign mem_ready[22*1+:1]=p_mem_ready[13*1+:1];
assign mem_write[22*1+:1]=p_mem_write[13*1+:1];
assign mem_addr[22*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[13*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[22*4+:4]=p_mem_bytes[13*4+:4];
assign mem_data[22*72+:72]=p_mem_data[13*72+:72];
assign mem_rsp_valid[22*1+:1]=p_mem_rsp_valid[13*1+:1];
assign mem_rsp_ready[22*1+:1]=p_mem_rsp_ready[13*1+:1];
assign mem_rsp_data[22*72+:72]=p_mem_rsp_data[13*72+:72];
assign p_mem_rsp_status[13*8+:8]=mem_rsp_status[22*8+:8];
assign fabric_status[22*8+:8]=p_fabric_status[13*8+:8];
assign mem_valid[23*1+:1]=p_mem_valid[14*1+:1];
assign mem_ready[23*1+:1]=p_mem_ready[14*1+:1];
assign mem_write[23*1+:1]=p_mem_write[14*1+:1];
assign mem_addr[23*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[14*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[23*4+:4]=p_mem_bytes[14*4+:4];
assign mem_data[23*72+:72]=p_mem_data[14*72+:72];
assign mem_rsp_valid[23*1+:1]=p_mem_rsp_valid[14*1+:1];
assign mem_rsp_ready[23*1+:1]=p_mem_rsp_ready[14*1+:1];
assign mem_rsp_data[23*72+:72]=p_mem_rsp_data[14*72+:72];
assign p_mem_rsp_status[14*8+:8]=mem_rsp_status[23*8+:8];
assign fabric_status[23*8+:8]=p_fabric_status[14*8+:8];
assign mem_valid[24*1+:1]=p_mem_valid[15*1+:1];
assign mem_ready[24*1+:1]=p_mem_ready[15*1+:1];
assign mem_write[24*1+:1]=p_mem_write[15*1+:1];
assign mem_addr[24*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[15*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[24*4+:4]=p_mem_bytes[15*4+:4];
assign mem_data[24*72+:72]=p_mem_data[15*72+:72];
assign mem_rsp_valid[24*1+:1]=p_mem_rsp_valid[15*1+:1];
assign mem_rsp_ready[24*1+:1]=p_mem_rsp_ready[15*1+:1];
assign mem_rsp_data[24*72+:72]=p_mem_rsp_data[15*72+:72];
assign p_mem_rsp_status[15*8+:8]=mem_rsp_status[24*8+:8];
assign fabric_status[24*8+:8]=p_fabric_status[15*8+:8];
assign mem_valid[25*1+:1]=p_mem_valid[16*1+:1];
assign mem_ready[25*1+:1]=p_mem_ready[16*1+:1];
assign mem_write[25*1+:1]=p_mem_write[16*1+:1];
assign mem_addr[25*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=p_mem_addr[16*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[25*4+:4]=p_mem_bytes[16*4+:4];
assign mem_data[25*72+:72]=p_mem_data[16*72+:72];
assign mem_rsp_valid[25*1+:1]=p_mem_rsp_valid[16*1+:1];
assign mem_rsp_ready[25*1+:1]=p_mem_rsp_ready[16*1+:1];
assign mem_rsp_data[25*72+:72]=p_mem_rsp_data[16*72+:72];
assign p_mem_rsp_status[16*8+:8]=mem_rsp_status[25*8+:8];
assign fabric_status[25*8+:8]=p_fabric_status[16*8+:8];
assign mem_valid[5*1+:1]=t_mem_valid[0*1+:1];
assign mem_ready[5*1+:1]=t_mem_ready[0*1+:1];
assign mem_write[5*1+:1]=t_mem_write[0*1+:1];
assign mem_addr[5*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[0*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[5*4+:4]=t_mem_bytes[0*4+:4];
assign mem_data[5*72+:72]=t_mem_data[0*72+:72];
assign mem_rsp_valid[5*1+:1]=t_mem_rsp_valid[0*1+:1];
assign mem_rsp_ready[5*1+:1]=t_mem_rsp_ready[0*1+:1];
assign mem_rsp_data[5*72+:72]=t_mem_rsp_data[0*72+:72];
assign t_mem_rsp_status[0*8+:8]=mem_rsp_status[5*8+:8];
assign fabric_status[5*8+:8]=t_fabric_status[0*8+:8];
assign mem_valid[6*1+:1]=t_mem_valid[1*1+:1];
assign mem_ready[6*1+:1]=t_mem_ready[1*1+:1];
assign mem_write[6*1+:1]=t_mem_write[1*1+:1];
assign mem_addr[6*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[1*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[6*4+:4]=t_mem_bytes[1*4+:4];
assign mem_data[6*72+:72]=t_mem_data[1*72+:72];
assign mem_rsp_valid[6*1+:1]=t_mem_rsp_valid[1*1+:1];
assign mem_rsp_ready[6*1+:1]=t_mem_rsp_ready[1*1+:1];
assign mem_rsp_data[6*72+:72]=t_mem_rsp_data[1*72+:72];
assign t_mem_rsp_status[1*8+:8]=mem_rsp_status[6*8+:8];
assign fabric_status[6*8+:8]=t_fabric_status[1*8+:8];
assign mem_valid[7*1+:1]=t_mem_valid[2*1+:1];
assign mem_ready[7*1+:1]=t_mem_ready[2*1+:1];
assign mem_write[7*1+:1]=t_mem_write[2*1+:1];
assign mem_addr[7*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[2*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[7*4+:4]=t_mem_bytes[2*4+:4];
assign mem_data[7*72+:72]=t_mem_data[2*72+:72];
assign mem_rsp_valid[7*1+:1]=t_mem_rsp_valid[2*1+:1];
assign mem_rsp_ready[7*1+:1]=t_mem_rsp_ready[2*1+:1];
assign mem_rsp_data[7*72+:72]=t_mem_rsp_data[2*72+:72];
assign t_mem_rsp_status[2*8+:8]=mem_rsp_status[7*8+:8];
assign fabric_status[7*8+:8]=t_fabric_status[2*8+:8];
assign mem_valid[8*1+:1]=t_mem_valid[3*1+:1];
assign mem_ready[8*1+:1]=t_mem_ready[3*1+:1];
assign mem_write[8*1+:1]=t_mem_write[3*1+:1];
assign mem_addr[8*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[3*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[8*4+:4]=t_mem_bytes[3*4+:4];
assign mem_data[8*72+:72]=t_mem_data[3*72+:72];
assign mem_rsp_valid[8*1+:1]=t_mem_rsp_valid[3*1+:1];
assign mem_rsp_ready[8*1+:1]=t_mem_rsp_ready[3*1+:1];
assign mem_rsp_data[8*72+:72]=t_mem_rsp_data[3*72+:72];
assign t_mem_rsp_status[3*8+:8]=mem_rsp_status[8*8+:8];
assign fabric_status[8*8+:8]=t_fabric_status[3*8+:8];
assign mem_valid[9*1+:1]=t_mem_valid[4*1+:1];
assign mem_ready[9*1+:1]=t_mem_ready[4*1+:1];
assign mem_write[9*1+:1]=t_mem_write[4*1+:1];
assign mem_addr[9*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[4*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[9*4+:4]=t_mem_bytes[4*4+:4];
assign mem_data[9*72+:72]=t_mem_data[4*72+:72];
assign mem_rsp_valid[9*1+:1]=t_mem_rsp_valid[4*1+:1];
assign mem_rsp_ready[9*1+:1]=t_mem_rsp_ready[4*1+:1];
assign mem_rsp_data[9*72+:72]=t_mem_rsp_data[4*72+:72];
assign t_mem_rsp_status[4*8+:8]=mem_rsp_status[9*8+:8];
assign fabric_status[9*8+:8]=t_fabric_status[4*8+:8];
assign mem_valid[10*1+:1]=t_mem_valid[5*1+:1];
assign mem_ready[10*1+:1]=t_mem_ready[5*1+:1];
assign mem_write[10*1+:1]=t_mem_write[5*1+:1];
assign mem_addr[10*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[5*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[10*4+:4]=t_mem_bytes[5*4+:4];
assign mem_data[10*72+:72]=t_mem_data[5*72+:72];
assign mem_rsp_valid[10*1+:1]=t_mem_rsp_valid[5*1+:1];
assign mem_rsp_ready[10*1+:1]=t_mem_rsp_ready[5*1+:1];
assign mem_rsp_data[10*72+:72]=t_mem_rsp_data[5*72+:72];
assign t_mem_rsp_status[5*8+:8]=mem_rsp_status[10*8+:8];
assign fabric_status[10*8+:8]=t_fabric_status[5*8+:8];
assign mem_valid[11*1+:1]=t_mem_valid[6*1+:1];
assign mem_ready[11*1+:1]=t_mem_ready[6*1+:1];
assign mem_write[11*1+:1]=t_mem_write[6*1+:1];
assign mem_addr[11*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[6*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[11*4+:4]=t_mem_bytes[6*4+:4];
assign mem_data[11*72+:72]=t_mem_data[6*72+:72];
assign mem_rsp_valid[11*1+:1]=t_mem_rsp_valid[6*1+:1];
assign mem_rsp_ready[11*1+:1]=t_mem_rsp_ready[6*1+:1];
assign mem_rsp_data[11*72+:72]=t_mem_rsp_data[6*72+:72];
assign t_mem_rsp_status[6*8+:8]=mem_rsp_status[11*8+:8];
assign fabric_status[11*8+:8]=t_fabric_status[6*8+:8];
assign mem_valid[12*1+:1]=t_mem_valid[7*1+:1];
assign mem_ready[12*1+:1]=t_mem_ready[7*1+:1];
assign mem_write[12*1+:1]=t_mem_write[7*1+:1];
assign mem_addr[12*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[7*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[12*4+:4]=t_mem_bytes[7*4+:4];
assign mem_data[12*72+:72]=t_mem_data[7*72+:72];
assign mem_rsp_valid[12*1+:1]=t_mem_rsp_valid[7*1+:1];
assign mem_rsp_ready[12*1+:1]=t_mem_rsp_ready[7*1+:1];
assign mem_rsp_data[12*72+:72]=t_mem_rsp_data[7*72+:72];
assign t_mem_rsp_status[7*8+:8]=mem_rsp_status[12*8+:8];
assign fabric_status[12*8+:8]=t_fabric_status[7*8+:8];
assign mem_valid[21*1+:1]=t_mem_valid[8*1+:1];
assign mem_ready[21*1+:1]=t_mem_ready[8*1+:1];
assign mem_write[21*1+:1]=t_mem_write[8*1+:1];
assign mem_addr[21*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=t_mem_addr[8*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH];
assign mem_bytes[21*4+:4]=t_mem_bytes[8*4+:4];
assign mem_data[21*72+:72]=t_mem_data[8*72+:72];
assign mem_rsp_valid[21*1+:1]=t_mem_rsp_valid[8*1+:1];
assign mem_rsp_ready[21*1+:1]=t_mem_rsp_ready[8*1+:1];
assign mem_rsp_data[21*72+:72]=t_mem_rsp_data[8*72+:72];
assign t_mem_rsp_status[8*8+:8]=mem_rsp_status[21*8+:8];
assign fabric_status[21*8+:8]=t_fabric_status[8*8+:8];
reg  p_axi_arready=0;
reg [63:0] p_axi_rdata=0;
reg [1:0] p_axi_rresp=0;
reg  p_axi_rlast=0;
reg  p_axi_rvalid=0;
reg  p_axi_awready=0;
reg  p_axi_wready=0;
reg [1:0] p_axi_bresp=0;
reg  p_axi_bvalid=0;
wire [22:0] p_axi_araddr;
wire [7:0] p_axi_arlen;
wire [2:0] p_axi_arsize;
wire [1:0] p_axi_arburst;
wire  p_axi_arvalid;
wire  p_axi_rready;
wire [22:0] p_axi_awaddr;
wire [7:0] p_axi_awlen;
wire [2:0] p_axi_awsize;
wire [1:0] p_axi_awburst;
wire  p_axi_awvalid;
wire [63:0] p_axi_wdata;
wire [7:0] p_axi_wstrb;
wire  p_axi_wlast;
wire  p_axi_wvalid;
wire  p_axi_bready;
external_memory_fabric #(.CLIENTS(17)) p_fabric(
    .clk(clk),
    .rst(rst),
    .invalidate_valid(1'b0),
    .invalidate_ready(),
    .s_valid(p_mem_valid),
    .s_ready(p_mem_ready),
    .s_write(p_mem_write),
    .s_addr(p_mem_addr),
    .s_bytes(p_mem_bytes),
    .s_data(p_mem_data),
    .rsp_valid(p_mem_rsp_valid),
    .rsp_ready(p_mem_rsp_ready),
    .rsp_data(p_mem_rsp_data),
    .rsp_status(p_fabric_status),
    .idle(p_fabric_idle),
    .m_axi_arready(p_axi_arready),
    .m_axi_rdata(p_axi_rdata),
    .m_axi_rresp(p_axi_rresp),
    .m_axi_rlast(p_axi_rlast),
    .m_axi_rvalid(p_axi_rvalid),
    .m_axi_awready(p_axi_awready),
    .m_axi_wready(p_axi_wready),
    .m_axi_bresp(p_axi_bresp),
    .m_axi_bvalid(p_axi_bvalid),
    .m_axi_araddr(p_axi_araddr),
    .m_axi_arlen(p_axi_arlen),
    .m_axi_arsize(p_axi_arsize),
    .m_axi_arburst(p_axi_arburst),
    .m_axi_arvalid(p_axi_arvalid),
    .m_axi_rready(p_axi_rready),
    .m_axi_awaddr(p_axi_awaddr),
    .m_axi_awlen(p_axi_awlen),
    .m_axi_awsize(p_axi_awsize),
    .m_axi_awburst(p_axi_awburst),
    .m_axi_awvalid(p_axi_awvalid),
    .m_axi_wdata(p_axi_wdata),
    .m_axi_wstrb(p_axi_wstrb),
    .m_axi_wlast(p_axi_wlast),
    .m_axi_wvalid(p_axi_wvalid),
    .m_axi_bready(p_axi_bready)
);
reg  t_axi_arready=0;
reg [63:0] t_axi_rdata=0;
reg [1:0] t_axi_rresp=0;
reg  t_axi_rlast=0;
reg  t_axi_rvalid=0;
reg  t_axi_awready=0;
reg  t_axi_wready=0;
reg [1:0] t_axi_bresp=0;
reg  t_axi_bvalid=0;
wire [22:0] t_axi_araddr;
wire [7:0] t_axi_arlen;
wire [2:0] t_axi_arsize;
wire [1:0] t_axi_arburst;
wire  t_axi_arvalid;
wire  t_axi_rready;
wire [22:0] t_axi_awaddr;
wire [7:0] t_axi_awlen;
wire [2:0] t_axi_awsize;
wire [1:0] t_axi_awburst;
wire  t_axi_awvalid;
wire [63:0] t_axi_wdata;
wire [7:0] t_axi_wstrb;
wire  t_axi_wlast;
wire  t_axi_wvalid;
wire  t_axi_bready;
assign t_mem_valid=tokenizer.mem_valid;
assign t_mem_ready=tokenizer.mem_ready;
assign t_mem_write=tokenizer.mem_write;
assign t_mem_addr=tokenizer.mem_addr;
assign t_mem_bytes=tokenizer.mem_bytes;
assign t_mem_data=tokenizer.mem_data;
assign t_mem_rsp_valid=tokenizer.mem_rsp_valid;
assign t_mem_rsp_ready=tokenizer.mem_rsp_ready;
assign t_mem_rsp_data=tokenizer.mem_rsp_data;
generate for(genvar status_client=0;status_client<9;status_client=status_client+1)begin: tokenizer_status
assign t_fabric_status[status_client*8+:8]=tokenizer.fabric.arbiter.statuses[status_client];
end endgenerate
initial force tokenizer.application.mem_rsp_status=t_mem_rsp_status;
generate for(genvar client=0;client<26;client=client+1)begin: fault_ports
assign mem_rsp_status[client*8+:8]=(fault_client==client&&!fault_injected&&response_index==fault_target)?8'h75:fabric_status[client*8+:8];
end endgenerate
always @(posedge clk)begin
if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end
else if(fault_client>=0&&fault_client<26&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin
if(!fault_injected&&response_index==fault_target)fault_injected<=1;response_index<=response_index+1;
end end
endmodule
`default_nettype wire
