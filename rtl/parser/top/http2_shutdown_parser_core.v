`timescale 1ns/1ps
`default_nettype none
module http2_shutdown_parser_core #(
parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384
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
input wire  admit_packets,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
input wire  command_valid,
output wire  command_ready,
input wire [1:0] command_op,
input wire [USER_WIDTH-1:0] command_user,
input wire  command_server_role,
input wire  command_allow_push,
input wire [23:0] command_max_frame_bytes,
input wire [MEMORY_ADDR_WIDTH-1:0] command_buffer_base,
input wire [MEMORY_ADDR_WIDTH-1:0] command_table_base,
input wire [MEMORY_ADDR_WIDTH-1:0] command_scratch_base,
input wire [MEMORY_ADDR_WIDTH:0] command_buffer_bytes,
input wire [MEMORY_ADDR_WIDTH:0] command_table_bytes,
input wire [MEMORY_ADDR_WIDTH:0] command_scratch_bytes,
input wire [31:0] command_hpack_maximum,
input wire [31:0] command_hpack_allowed,
input wire [31:0] command_header_list_limit,
input wire [31:0] command_required_maximum,
input wire  command_required_update,
input wire [511:0] s_axis_rx_tdata,
input wire [63:0] s_axis_rx_tkeep,
input wire  s_axis_rx_tvalid,
output wire  s_axis_rx_tready,
input wire  s_axis_rx_tlast,
input wire [USER_WIDTH-1:0] s_axis_rx_tuser,
output wire  rsp_valid,
input wire  rsp_ready,
output wire  rsp_is_command,
output wire [1:0] rsp_command_op,
output wire [7:0] rsp_status,
output wire [7:0] rsp_detail,
output wire [7:0] rsp_memory_status,
output wire [31:0] rsp_http2_error,
output wire [USER_WIDTH-1:0] rsp_user,
input wire [31:0] s_axis_rx_tag,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_route_base,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_route_strings_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_payload_slot_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_route_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_route_strings_bytes,
input wire [31:0] cfg_routes,
input wire [31:0] cfg_model_epoch,
input wire [31:0] cfg_schema_epoch,
output wire  header_valid,
input wire  header_ready,
output wire [3:0] header_status,
output wire [7:0] header_detail,
output wire [7:0] header_memory_status,
output wire [7:0] header_control_status,
output wire [7:0] header_cleanup_status,
output wire  header_connection_error,
output wire [31:0] header_http2_error,
output wire [9:0] header_http_status,
output wire [7:0] header_grpc_status,
output wire [USER_WIDTH-1:0] header_user,
output wire [30:0] header_stream,
output wire [31:0] header_generation,
output wire [MEMORY_ADDR_WIDTH-1:0] header_address,
output wire [15:0] header_application,
output wire [31:0] header_model_epoch,
output wire [31:0] header_schema_epoch,
output wire  header_trailers,
output wire  header_end_stream,
output wire  admission_recovery_required,
output wire [MEMORY_ADDR_WIDTH-1:0] admission_recovery_address,
output wire [USER_WIDTH-1:0] admission_recovery_user,
output wire  transport_recovery_required,
output wire [MEMORY_ADDR_WIDTH-1:0] transport_recovery_address,
output wire  control_event_valid,
input wire  control_event_ready,
output wire [3:0] control_event_kind,
output wire [31:0] control_event_arg0,
output wire [31:0] control_event_arg1,
output wire [30:0] control_event_stream,
output wire [USER_WIDTH-1:0] control_event_user,
output wire [7:0] transport_packet_status,
output wire [7:0] transport_packet_detail,
output wire [7:0] transport_packet_memory_status,
output wire [31:0] transport_packet_http2_error,
output wire  idle,
output wire [26*1-1:0] mem_valid,
input wire [26*1-1:0] mem_ready,
output wire [26*1-1:0] mem_write,
output wire [26*MEMORY_ADDR_WIDTH-1:0] mem_addr,
output wire [26*4-1:0] mem_bytes,
output wire [26*72-1:0] mem_data,
input wire [26*1-1:0] mem_rsp_valid,
output wire [26*1-1:0] mem_rsp_ready,
input wire [26*72-1:0] mem_rsp_data,
input wire [26*8-1:0] mem_rsp_status,
input wire [31:0] s_axis_generated_tdata,
input wire [3:0] s_axis_generated_tkeep,
input wire  s_axis_generated_tvalid,
output wire  s_axis_generated_tready,
input wire  s_axis_generated_tlast,
input wire [USER_WIDTH-1:0] s_axis_generated_tuser,
input wire [30:0] generated_stream,
input wire [31:0] generated_generation,
input wire [31:0] generated_model_epoch,
input wire [31:0] generated_schema_epoch,
input wire [31:0] generated_ordinal,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_response_progress_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_response_progress_bytes,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_response_directory_base,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_response_pool_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_response_directory_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_response_pool_bytes,
input wire  cfg_response_strip_special,
input wire  cfg_response_replace_invalid,
input wire [1:0] cfg_response_format,
input wire [28:0] cfg_response_protobuf_field,
output wire [511:0] m_axis_tx_tdata,
output wire [63:0] m_axis_tx_tkeep,
output wire  m_axis_tx_tvalid,
input wire  m_axis_tx_tready,
output wire  m_axis_tx_tlast,
output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
output wire  response_result_valid,
input wire  response_result_ready,
output wire [7:0] response_result_stage,
output wire [7:0] response_result_status,
output wire [7:0] response_result_memory_status,
output wire [USER_WIDTH-1:0] response_result_user,
output wire [USER_WIDTH-1:0] response_result_application,
output wire [30:0] response_result_stream,
output wire [31:0] response_result_generation,
output wire [31:0] response_result_model_epoch,
output wire [31:0] response_result_schema_epoch,
output wire [31:0] response_result_ordinal,
output wire [31:0] response_result_bytes,
output wire  response_result_eos,
output wire  response_result_tx_emitted,
output wire  response_recovery_required,
output wire [MEMORY_ADDR_WIDTH-1:0] response_recovery_address,
output wire  response_directory_lease_active,
output wire  response_idle,
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
input wire  link_f_pack_idle,
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
output wire  flow_event_valid,
output wire  flow_event_ready,
output wire [3:0] flow_event_kind,
output wire [7:0] flow_event_data,
output wire [31:0] flow_event_arg0,
output wire [31:0] flow_event_arg1,
output wire [23:0] flow_event_length,
output wire [7:0] flow_event_type,
output wire [7:0] flow_event_flags,
output wire [30:0] flow_event_stream,
output wire [USER_WIDTH-1:0] flow_event_user,
input wire [23:0] cfg_peer_max_frame_bytes,
output wire [31:0] result_serialized_bytes,
output wire [31:0] result_wire_bytes,
output wire [31:0] result_frames,
output wire  response_result_progress_committed,
output wire  response_record_lease_active,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_window_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_window_bytes,
output wire [7:0] header_window_status,
output wire [7:0] command_window_status,
output wire [7:0] command_window_cleanup_status,
input wire  window_req_valid,
output wire  window_req_ready,
input wire [3:0] window_req_op,
input wire  window_req_maintenance,
input wire [USER_WIDTH-1:0] window_req_user,
input wire [30:0] window_req_stream,
input wire [31:0] window_req_generation,
input wire [MEMORY_ADDR_WIDTH-1:0] window_req_record_address,
input wire [31:0] window_req_amount,
input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_context_base,
input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_stream_base,
input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_window_base,
input wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_work_floor,
input wire [MEMORY_ADDR_WIDTH:0] window_cfg_context_bytes,
input wire [MEMORY_ADDR_WIDTH:0] window_cfg_stream_bytes,
input wire [MEMORY_ADDR_WIDTH:0] window_cfg_window_bytes,
output wire  window_rsp_valid,
input wire  window_rsp_ready,
output wire [3:0] window_rsp_op,
output wire [USER_WIDTH-1:0] window_rsp_user,
output wire [30:0] window_rsp_stream,
output wire [7:0] window_rsp_status,
output wire [7:0] window_rsp_detail,
output wire [7:0] window_rsp_memory_status,
output wire  window_rsp_connection_error,
output wire [31:0] window_rsp_http2_error,
output wire [23:0] window_rsp_grant_bytes,
output wire [31:0] window_rsp_connection_window,
output wire [31:0] window_rsp_initial_window,
output wire [31:0] window_rsp_stream_window,
output wire [23:0] window_rsp_max_frame_bytes,
output wire [31:0] window_rsp_affected_streams,
output wire  window_recovery_required,
output wire [MEMORY_ADDR_WIDTH-1:0] window_recovery_address,
output wire  window_busy,
output wire [7:0] window_lock_status,
output wire  credit_parked,
output wire  directory_pool_lock_active,
output wire [7:0] response_result_credit_status,
output wire [7:0] response_result_credit_detail,
output wire [31:0] response_result_credit_http2_error,
output wire  response_result_credit_connection_error,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_control_journal_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_control_journal_bytes,
input wire [MEMORY_ADDR_WIDTH:0] cfg_control_slot_bytes,
output wire [7:0] command_control_status,
output wire [7:0] packet_control_status,
output wire [7:0] packet_control_detail,
output wire [7:0] packet_control_memory_status,
output wire [7:0] journal_control_status,
output wire [7:0] journal_control_detail,
output wire [7:0] journal_control_memory_status,
output wire  journal_control_connection_error,
output wire [31:0] journal_control_http2_error,
output wire [31:0] journal_control_frames,
output wire [31:0] journal_control_ack_frames,
output wire [31:0] journal_control_window_updates,
output wire  cancel_valid,
output wire  cancel_ready,
output wire [USER_WIDTH-1:0] cancel_user,
output wire  cancel_goaway,
output wire [30:0] cancel_stream,
output wire [31:0] cancel_arg0,
output wire [31:0] cancel_arg1,
output wire  cancel_result_valid,
output wire  cancel_result_ready,
output wire [7:0] cancel_status,
output wire  journal_recovery_required,
output wire [MEMORY_ADDR_WIDTH-1:0] journal_recovery_address,
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_peer_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_peer_bytes,
output wire [7:0] peer_format_status,
output wire [7:0] peer_format_memory_status,
output wire [7:0] history_status,
output wire [7:0] history_detail,
output wire [7:0] history_memory_status,
output wire  history_closed,
output wire [30:0] history_last_stream,
output wire [31:0] history_queries,
output wire  response_result_cancelled,
output wire  response_result_retirement_pending,
output wire  shutdown_busy,
output wire  shutdown_recovery_required,
output wire  reset_processed,
output wire [31:0] resets_processed,
output wire [31:0] goaways_processed,
output wire [7:0] shutdown_status,
output wire [7:0] shutdown_detail,
output wire [7:0] shutdown_memory_status,
output wire  peer_goaway_received,
output wire [30:0] peer_goaway_last_stream,
output wire [31:0] peer_goaway_error
);
wire [7:0] cancel_detail;
wire [7:0] cancel_memory_status;
wire  cancel_connection_error;
wire [31:0] cancel_http2_error;
wire  goaway_req_valid;
wire  goaway_req_ready;
wire [USER_WIDTH-1:0] goaway_user;
wire [30:0] goaway_last_stream;
wire [31:0] goaway_error;
wire  goaway_rsp_valid;
wire  goaway_rsp_ready;
wire [7:0] goaway_rsp_status;
wire [7:0] goaway_rsp_detail;
wire [7:0] goaway_rsp_memory_status;
wire  goaway_rsp_connection_error;
wire [31:0] goaway_rsp_http2_error;
wire [3:0] goaway_rsp_op;
wire [USER_WIDTH-1:0] goaway_rsp_user;
wire  shutdown_classify_valid;
wire  shutdown_classify_ready;
wire [USER_WIDTH-1:0] shutdown_classify_user;
wire [30:0] shutdown_classify_stream;
wire  shutdown_classify_rsp_valid;
wire  shutdown_classify_rsp_ready;
wire [7:0] shutdown_classify_rsp_status;
wire [7:0] shutdown_classify_rsp_detail;
wire [7:0] shutdown_classify_rsp_memory_status;
wire [USER_WIDTH-1:0] shutdown_classify_rsp_user;
wire [30:0] shutdown_classify_rsp_stream;
wire  shutdown_classify_rsp_closed;
wire [30:0] shutdown_classify_rsp_last_stream;
wire  shutdown_return_window_rsp_binding_valid;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_return_window_rsp_record_address;
wire [31:0] shutdown_return_window_rsp_generation;
wire  shutdown_return_window_rsp_send_closed;
wire  shutdown_return_freeze_valid;
wire  shutdown_return_freeze_ready;
wire [USER_WIDTH-1:0] shutdown_return_freeze_user;
wire [30:0] shutdown_return_freeze_stream;
wire  shutdown_return_freeze_active;
wire  shutdown_return_freeze_drained;
wire  shutdown_return_freeze_binding_valid;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_return_freeze_record_address;
wire [31:0] shutdown_return_freeze_generation;
wire  shutdown_return_freeze_release_valid;
wire  shutdown_return_freeze_release_ready;
wire  shutdown_return_frame_wire_pending;
wire  shutdown_return_frame_tracking_error;
wire [512-1:0] shutdown_return_b_axis_tdata;
wire [64-1:0] shutdown_return_b_axis_tkeep;
wire  shutdown_return_b_axis_tvalid;
wire  shutdown_return_b_axis_tready;
wire  shutdown_return_b_axis_tlast;
wire [USER_WIDTH-1:0] shutdown_return_b_axis_tuser;
wire  shutdown_return_data_wire_paused;
wire  shutdown_return_result_cancelled;
wire  shutdown_return_result_retirement_pending;
wire  service_control_req_valid;
wire  service_control_req_ready;
wire [2:0] service_control_req_op;
wire [MEMORY_ADDR_WIDTH-1:0] service_control_pool_base;
wire [MEMORY_ADDR_WIDTH:0] service_control_pool_bytes;
wire [USER_WIDTH-1:0] service_control_req_user;
wire [USER_WIDTH-1:0] service_control_req_application;
wire [30:0] service_control_req_stream;
wire [31:0] service_control_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] service_control_req_address;
wire [MEMORY_ADDR_WIDTH-1:0] service_control_req_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] service_control_req_buffer_bytes;
wire [31:0] service_control_req_message_limit;
wire  service_control_req_protobuf;
wire  service_control_req_unsupported_encoding;
wire  service_control_req_maintenance;
wire [255:0] service_control_req_state;
wire  service_control_rsp_valid;
wire  service_control_rsp_ready;
wire [7:0] service_control_rsp_status;
wire [7:0] service_control_rsp_detail;
wire [7:0] service_control_rsp_memory_status;
wire [2:0] service_control_rsp_op;
wire [MEMORY_ADDR_WIDTH-1:0] service_control_rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] service_control_rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] service_control_rsp_buffer_bytes;
wire [USER_WIDTH-1:0] service_control_rsp_user;
wire [USER_WIDTH-1:0] service_control_rsp_application;
wire [30:0] service_control_rsp_stream;
wire [31:0] service_control_rsp_generation;
wire [31:0] service_control_rsp_message_limit;
wire  service_control_rsp_protobuf;
wire  service_control_rsp_unsupported_encoding;
wire [255:0] service_control_rsp_state;
wire  service_directory_idle;
wire  service_window_rsp_binding_valid;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_rsp_record_address;
wire [31:0] service_window_rsp_generation;
wire  service_window_rsp_send_closed;
wire  shutdown_close_valid;
wire  shutdown_close_ready;
wire [USER_WIDTH-1:0] shutdown_close_user;
wire [30:0] shutdown_close_stream;
wire  shutdown_close_rsp_valid;
wire  shutdown_close_rsp_ready;
wire  shutdown_directory_valid;
wire  shutdown_directory_ready;
wire [31:0] shutdown_directory_generation;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_directory_address;
wire  shutdown_directory_rsp_valid;
wire  shutdown_directory_rsp_ready;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_owned_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_owned_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_owned_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] shutdown_owned_work_floor;
wire [MEMORY_ADDR_WIDTH:0] shutdown_owned_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] shutdown_owned_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] shutdown_owned_window_bytes;
wire  shutdown_request_ready;
wire  shutdown_scope_match;
assign service_control_req_valid=shutdown_dir_owner==1?dir_req_valid:shutdown_dir_owner==3&&shutdown_directory_valid;
assign dir_req_ready=shutdown_dir_owner==1&&service_control_req_ready;
assign shutdown_directory_ready=shutdown_dir_owner==3&&service_control_req_ready;
assign service_control_req_op=shutdown_dir_owner==3?3'd3:dir_req_op;
assign service_control_pool_base=shutdown_dir_owner==3?shutdown_owned_stream_base:dir_cfg_pool_base;
assign service_control_pool_bytes=shutdown_dir_owner==3?shutdown_owned_stream_bytes:dir_cfg_pool_bytes;
assign service_control_req_user=shutdown_dir_owner==3?shutdown_close_user:dir_req_user;
assign service_control_req_application=shutdown_dir_owner==3?0:dir_req_application;
assign service_control_req_stream=shutdown_dir_owner==3?shutdown_close_stream:dir_req_stream;
assign service_control_req_generation=shutdown_dir_owner==3?shutdown_directory_generation:dir_req_generation;
assign service_control_req_address=shutdown_dir_owner==3?shutdown_directory_address:dir_req_address;
assign service_control_req_buffer_base=shutdown_dir_owner==3?0:dir_req_buffer_base;
assign service_control_req_buffer_bytes=shutdown_dir_owner==3?0:dir_req_buffer_bytes;
assign service_control_req_message_limit=shutdown_dir_owner==3?0:dir_req_message_limit;
assign service_control_req_protobuf=shutdown_dir_owner==3?0:dir_req_protobuf;
assign service_control_req_unsupported_encoding=shutdown_dir_owner==3?0:dir_req_unsupported_encoding;
assign service_control_req_maintenance=shutdown_dir_owner==3?0:dir_req_maintenance;
assign service_control_req_state=shutdown_dir_owner==3?0:dir_req_state;
assign dir_rsp_valid=shutdown_dir_owner==2&&service_control_rsp_valid;
assign shutdown_directory_rsp_valid=shutdown_dir_owner==4&&service_control_rsp_valid;
assign service_control_rsp_ready=shutdown_dir_owner==2?dir_rsp_ready:shutdown_dir_owner==4&&shutdown_directory_rsp_ready;
assign dir_rsp_status=service_control_rsp_status;
assign dir_rsp_detail=service_control_rsp_detail;
assign dir_rsp_memory_status=service_control_rsp_memory_status;
assign dir_rsp_op=service_control_rsp_op;
assign dir_rsp_address=service_control_rsp_address;
assign dir_rsp_buffer_base=service_control_rsp_buffer_base;
assign dir_rsp_buffer_bytes=service_control_rsp_buffer_bytes;
assign dir_rsp_user=service_control_rsp_user;
assign dir_rsp_application=service_control_rsp_application;
assign dir_rsp_stream=service_control_rsp_stream;
assign dir_rsp_generation=service_control_rsp_generation;
assign dir_rsp_message_limit=service_control_rsp_message_limit;
assign dir_rsp_protobuf=service_control_rsp_protobuf;
assign dir_rsp_unsupported_encoding=service_control_rsp_unsupported_encoding;
assign dir_rsp_state=service_control_rsp_state;
reg [2:0] shutdown_dir_owner;
assign dir_idle=service_directory_idle&&shutdown_dir_owner==0&&!shutdown_directory_valid;
always @(posedge clk)begin if(rst)shutdown_dir_owner<=0;else case(shutdown_dir_owner)
0:if(shutdown_directory_valid)shutdown_dir_owner<=3;else if(dir_req_valid&&!shutdown_busy)shutdown_dir_owner<=1;
1:if(dir_req_valid&&service_control_req_ready)shutdown_dir_owner<=2;
2:if(service_control_rsp_valid&&dir_rsp_ready)shutdown_dir_owner<=0;
3:if(shutdown_directory_valid&&service_control_req_ready)shutdown_dir_owner<=4;
4:if(service_control_rsp_valid&&shutdown_directory_rsp_ready)shutdown_dir_owner<=0;
default:shutdown_dir_owner<=0;endcase end
assign shutdown_close_ready=shutdown_window_send&&service_window_req_ready;
assign shutdown_close_rsp_valid=window_owner==8&&service_window_rsp_valid;
reg [MEMORY_ADDR_WIDTH-1:0] return_scope_context_base;
reg [MEMORY_ADDR_WIDTH:0] return_scope_context_bytes;
reg [MEMORY_ADDR_WIDTH-1:0] return_scope_stream_base;
reg [MEMORY_ADDR_WIDTH:0] return_scope_stream_bytes;
reg [MEMORY_ADDR_WIDTH-1:0] return_scope_window_base;
reg [MEMORY_ADDR_WIDTH:0] return_scope_window_bytes;
reg [MEMORY_ADDR_WIDTH-1:0] return_scope_work_floor;
assign shutdown_scope_match=return_scope_context_base==shutdown_owned_context_base&&return_scope_context_bytes==shutdown_owned_context_bytes&&return_scope_stream_base==shutdown_owned_stream_base&&return_scope_stream_bytes==shutdown_owned_stream_bytes&&return_scope_window_base==shutdown_owned_window_base&&return_scope_window_bytes==shutdown_owned_window_bytes&&return_scope_work_floor==shutdown_owned_work_floor;
always @(posedge clk)begin if(rst)begin return_scope_context_base<=0;return_scope_context_bytes<=0;return_scope_stream_base<=0;return_scope_stream_bytes<=0;return_scope_window_base<=0;return_scope_window_bytes<=0;return_scope_work_floor<=0;end else if(s_axis_generated_tvalid&&s_axis_generated_tready)begin return_scope_context_base<=active_context_base;return_scope_context_bytes<=active_context_bytes;return_scope_stream_base<=owned_stream_base;return_scope_stream_bytes<=owned_stream_bytes;return_scope_window_base<=active_window_base;return_scope_window_bytes<=active_window_bytes;return_scope_work_floor<=cfg_work_floor;end end
assign cancel_ready=shutdown_request_ready&&ctl_history_fence;
assign shutdown_status=cancel_status;assign shutdown_detail=cancel_detail;assign shutdown_memory_status=cancel_memory_status;
assign goaway_user=shutdown_close_user;assign shutdown_classify_user=shutdown_close_user;assign shutdown_classify_stream=shutdown_close_stream;
http2_stream_shutdown #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) shutdown(
    .clk(clk),
    .rst(rst),
    .req_valid(cancel_valid&&ctl_history_fence),
    .req_ready(shutdown_request_ready),
    .req_goaway(cancel_goaway),
    .req_user(cancel_user),
    .req_stream(cancel_stream),
    .req_arg0(cancel_arg0),
    .req_arg1(cancel_arg1),
    .history_fence(ctl_history_fence),
    .cfg_context_base(ctl_cfg_context_base),
    .cfg_stream_base(ctl_cfg_stream_base),
    .cfg_window_base(ctl_cfg_window_base),
    .cfg_work_floor(ctl_cfg_work_floor),
    .cfg_context_bytes(ctl_cfg_context_bytes),
    .cfg_stream_bytes(ctl_cfg_stream_bytes),
    .cfg_window_bytes(ctl_cfg_window_bytes),
    .rsp_valid(cancel_result_valid),
    .rsp_ready(cancel_result_ready),
    .rsp_status(cancel_status),
    .rsp_detail(cancel_detail),
    .rsp_memory_status(cancel_memory_status),
    .rsp_connection_error(cancel_connection_error),
    .rsp_http2_error(cancel_http2_error),
    .rsp_user(),
    .rsp_stream(),
    .recovery_required(shutdown_recovery_required),
    .busy(shutdown_busy),
    .idle(),
    .reset_processed(reset_processed),
    .resets_processed(resets_processed),
    .goaways_processed(goaways_processed),
    .return_key_valid(return_pending),
    .return_scope_match(shutdown_scope_match),
    .return_user(return_user),
    .return_stream(return_stream),
    .freeze_valid(shutdown_return_freeze_valid),
    .freeze_ready(shutdown_return_freeze_ready),
    .freeze_user(shutdown_return_freeze_user),
    .freeze_stream(shutdown_return_freeze_stream),
    .freeze_drained(shutdown_return_freeze_drained),
    .frame_tracking_error(shutdown_return_frame_tracking_error),
    .freeze_release_valid(shutdown_return_freeze_release_valid),
    .freeze_release_ready(shutdown_return_freeze_release_ready),
    .close_valid(shutdown_close_valid),
    .close_ready(shutdown_close_ready),
    .close_user(shutdown_close_user),
    .close_stream(shutdown_close_stream),
    .close_rsp_valid(shutdown_close_rsp_valid),
    .close_rsp_ready(shutdown_close_rsp_ready),
    .close_rsp_op(service_window_rsp_op),
    .close_rsp_user(service_window_rsp_user),
    .close_rsp_stream(service_window_rsp_stream),
    .close_rsp_status(service_window_rsp_status),
    .close_rsp_detail(service_window_rsp_detail),
    .close_rsp_memory_status(service_window_rsp_memory_status),
    .close_rsp_connection_error(service_window_rsp_connection_error),
    .close_rsp_http2_error(service_window_rsp_http2_error),
    .close_rsp_binding_valid(service_window_rsp_binding_valid),
    .close_rsp_send_closed(service_window_rsp_send_closed),
    .close_rsp_generation(service_window_rsp_generation),
    .close_rsp_address(service_window_rsp_record_address),
    .directory_valid(shutdown_directory_valid),
    .directory_ready(shutdown_directory_ready),
    .directory_generation(shutdown_directory_generation),
    .directory_address(shutdown_directory_address),
    .directory_rsp_valid(shutdown_directory_rsp_valid),
    .directory_rsp_ready(shutdown_directory_rsp_ready),
    .directory_rsp_status(service_control_rsp_status),
    .directory_rsp_detail(service_control_rsp_detail),
    .directory_rsp_memory_status(service_control_rsp_memory_status),
    .directory_rsp_op(service_control_rsp_op),
    .directory_rsp_user(service_control_rsp_user),
    .directory_rsp_stream(service_control_rsp_stream),
    .directory_rsp_generation(service_control_rsp_generation),
    .directory_rsp_address(service_control_rsp_address),
    .classify_valid(shutdown_classify_valid),
    .classify_ready(shutdown_classify_ready),
    .classify_rsp_valid(shutdown_classify_rsp_valid),
    .classify_rsp_ready(shutdown_classify_rsp_ready),
    .classify_rsp_status(shutdown_classify_rsp_status),
    .classify_rsp_detail(shutdown_classify_rsp_detail),
    .classify_rsp_memory_status(shutdown_classify_rsp_memory_status),
    .classify_rsp_closed(shutdown_classify_rsp_closed),
    .classify_rsp_user(shutdown_classify_rsp_user),
    .classify_rsp_stream(shutdown_classify_rsp_stream),
    .peer_valid(goaway_req_valid),
    .peer_ready(goaway_req_ready),
    .peer_last_stream(goaway_last_stream),
    .peer_error(goaway_error),
    .peer_rsp_valid(goaway_rsp_valid),
    .peer_rsp_ready(goaway_rsp_ready),
    .peer_rsp_status(goaway_rsp_status),
    .peer_rsp_detail(goaway_rsp_detail),
    .peer_rsp_memory_status(goaway_rsp_memory_status),
    .peer_rsp_connection_error(goaway_rsp_connection_error),
    .peer_rsp_http2_error(goaway_rsp_http2_error),
    .peer_rsp_op(goaway_rsp_op),
    .peer_rsp_user(goaway_rsp_user),
    .owned_context_base(shutdown_owned_context_base),
    .owned_stream_base(shutdown_owned_stream_base),
    .owned_window_base(shutdown_owned_window_base),
    .owned_work_floor(shutdown_owned_work_floor),
    .owned_context_bytes(shutdown_owned_context_bytes),
    .owned_stream_bytes(shutdown_owned_stream_bytes),
    .owned_window_bytes(shutdown_owned_window_bytes)
);

wire ctl_history_fence;

wire [MEMORY_ADDR_WIDTH-1:0] ctl_cfg_peer_base;
wire [MEMORY_ADDR_WIDTH:0] ctl_cfg_peer_bytes;

wire  ctl_start_valid;
wire  ctl_start_ready;
wire  ctl_start_format;
wire  ctl_start_maintenance;
wire [USER_WIDTH-1:0] ctl_start_user;
wire  ctl_finish_valid;
wire  ctl_finish_ready;
wire  ctl_finish_commit;
wire  ctl_result_valid;
wire  ctl_result_ready;
wire [7:0] ctl_result_status;
wire [7:0] ctl_result_detail;
wire [7:0] ctl_result_memory_status;
wire  control_drop_events;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_cfg_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_cfg_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_cfg_journal_base;
wire [MEMORY_ADDR_WIDTH:0] ctl_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] ctl_cfg_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] ctl_cfg_window_bytes;
wire [MEMORY_ADDR_WIDTH:0] ctl_cfg_journal_bytes;
wire [MEMORY_ADDR_WIDTH:0] ctl_cfg_slot_bytes;
wire control_window_send=window_owner==5;
wire journal_idle,tx_idle;
assign ctl_window_req_ready=control_window_send&&service_window_req_ready;
assign ctl_window_rsp_valid=window_owner==6&&service_window_rsp_valid;
assign flow_event_ready=control_drop_events?1'b1:ctl_flow_ready;
wire ctl_flow_ready;
wire  ctl_window_req_valid;
wire  ctl_window_req_ready;
wire [3:0] ctl_window_req_op;
wire  ctl_window_req_maintenance;
wire [USER_WIDTH-1:0] ctl_window_req_user;
wire [30:0] ctl_window_req_stream;
wire [31:0] ctl_window_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_window_req_record_address;
wire [31:0] ctl_window_req_amount;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_window_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_window_cfg_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_window_cfg_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] ctl_window_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] ctl_window_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] ctl_window_cfg_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] ctl_window_cfg_window_bytes;
wire  ctl_window_rsp_valid;
wire  ctl_window_rsp_ready;
wire [3:0] ctl_window_rsp_op;
wire [USER_WIDTH-1:0] ctl_window_rsp_user;
wire [30:0] ctl_window_rsp_stream;
wire [7:0] ctl_window_rsp_status;
wire [7:0] ctl_window_rsp_detail;
wire [7:0] ctl_window_rsp_memory_status;
wire  ctl_window_rsp_connection_error;
wire [31:0] ctl_window_rsp_http2_error;
assign ctl_window_rsp_op=service_window_rsp_op;
assign ctl_window_rsp_user=service_window_rsp_user;
assign ctl_window_rsp_stream=service_window_rsp_stream;
assign ctl_window_rsp_status=service_window_rsp_status;
assign ctl_window_rsp_detail=service_window_rsp_detail;
assign ctl_window_rsp_memory_status=service_window_rsp_memory_status;
assign ctl_window_rsp_connection_error=service_window_rsp_connection_error;
assign ctl_window_rsp_http2_error=service_window_rsp_http2_error;
wire [511:0] ack_m_axis_tx_tdata;
wire [511:0] return_m_axis_tx_tdata;
wire [63:0] ack_m_axis_tx_tkeep;
wire [63:0] return_m_axis_tx_tkeep;
wire  ack_m_axis_tx_tvalid;
wire  return_m_axis_tx_tvalid;
wire  ack_m_axis_tx_tready;
wire  return_m_axis_tx_tready;
wire  ack_m_axis_tx_tlast;
wire  return_m_axis_tx_tlast;
wire [USER_WIDTH-1:0] ack_m_axis_tx_tuser;
wire [USER_WIDTH-1:0] return_m_axis_tx_tuser;
http2_shutdown_classified_controls #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) controls(
    .clk(clk),
    .rst(rst),
    .start_valid(ctl_start_valid),
    .start_ready(ctl_start_ready),
    .start_format(ctl_start_format),
    .start_maintenance(ctl_start_maintenance),
    .start_authority(1'b1),
    .start_user(ctl_start_user),
    .cfg_context_base(ctl_cfg_context_base),
    .cfg_journal_base(ctl_cfg_journal_base),
    .cfg_work_floor(ctl_cfg_work_floor),
    .cfg_context_bytes(ctl_cfg_context_bytes),
    .cfg_journal_bytes(ctl_cfg_journal_bytes),
    .cfg_slot_bytes(ctl_cfg_slot_bytes),
    .s_valid(flow_event_valid&&!control_drop_events),
    .s_ready(ctl_flow_ready),
    .s_kind(flow_event_kind),
    .s_data(flow_event_data),
    .s_arg0(flow_event_arg0),
    .s_arg1(flow_event_arg1),
    .s_length(flow_event_length),
    .s_type(flow_event_type),
    .s_flags(flow_event_flags),
    .s_stream(flow_event_stream),
    .s_user(flow_event_user),
    .finish_valid(ctl_finish_valid),
    .finish_ready(ctl_finish_ready),
    .finish_commit(ctl_finish_commit),
    .result_valid(ctl_result_valid),
    .result_ready(ctl_result_ready),
    .result_status(ctl_result_status),
    .result_detail(ctl_result_detail),
    .result_memory_status(ctl_result_memory_status),
    .result_user(),
    .result_committed(),
    .result_records(),
    .result_frames(),
    .recovery_required(journal_recovery_required),
    .recovery_address(journal_recovery_address),
    .idle(journal_idle),
    .mem_valid(mem_valid[23*1+:3*1]),
    .mem_ready(mem_ready[23*1+:3*1]),
    .mem_write(mem_write[23*1+:3*1]),
    .mem_addr(mem_addr[23*MEMORY_ADDR_WIDTH+:3*MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[23*4+:3*4]),
    .mem_data(mem_data[23*72+:3*72]),
    .mem_rsp_valid(mem_rsp_valid[23*1+:3*1]),
    .mem_rsp_ready(mem_rsp_ready[23*1+:3*1]),
    .mem_rsp_data(mem_rsp_data[23*72+:3*72]),
    .mem_rsp_status(mem_rsp_status[23*8+:3*8]),
    .cfg_stream_base(ctl_cfg_stream_base),
    .cfg_window_base(ctl_cfg_window_base),
    .cfg_stream_bytes(ctl_cfg_stream_bytes),
    .cfg_window_bytes(ctl_cfg_window_bytes),
    .control_status(journal_control_status),
    .control_detail(journal_control_detail),
    .control_memory_status(journal_control_memory_status),
    .control_connection_error(journal_control_connection_error),
    .control_http2_error(journal_control_http2_error),
    .control_frames(journal_control_frames),
    .control_ack_frames(journal_control_ack_frames),
    .control_window_updates(journal_control_window_updates),
    .window_req_valid(ctl_window_req_valid),
    .window_req_ready(ctl_window_req_ready),
    .window_req_op(ctl_window_req_op),
    .window_req_maintenance(ctl_window_req_maintenance),
    .window_req_user(ctl_window_req_user),
    .window_req_stream(ctl_window_req_stream),
    .window_req_generation(ctl_window_req_generation),
    .window_req_record_address(ctl_window_req_record_address),
    .window_req_amount(ctl_window_req_amount),
    .window_cfg_context_base(ctl_window_cfg_context_base),
    .window_cfg_stream_base(ctl_window_cfg_stream_base),
    .window_cfg_window_base(ctl_window_cfg_window_base),
    .window_cfg_work_floor(ctl_window_cfg_work_floor),
    .window_cfg_context_bytes(ctl_window_cfg_context_bytes),
    .window_cfg_stream_bytes(ctl_window_cfg_stream_bytes),
    .window_cfg_window_bytes(ctl_window_cfg_window_bytes),
    .window_rsp_valid(ctl_window_rsp_valid),
    .window_rsp_ready(ctl_window_rsp_ready),
    .window_rsp_op(ctl_window_rsp_op),
    .window_rsp_user(ctl_window_rsp_user),
    .window_rsp_stream(ctl_window_rsp_stream),
    .window_rsp_status(ctl_window_rsp_status),
    .window_rsp_detail(ctl_window_rsp_detail),
    .window_rsp_memory_status(ctl_window_rsp_memory_status),
    .window_rsp_connection_error(ctl_window_rsp_connection_error),
    .window_rsp_http2_error(ctl_window_rsp_http2_error),
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
    .m_axis_tx_tdata(ack_m_axis_tx_tdata),
    .m_axis_tx_tkeep(ack_m_axis_tx_tkeep),
    .m_axis_tx_tvalid(ack_m_axis_tx_tvalid),
    .m_axis_tx_tready(ack_m_axis_tx_tready),
    .m_axis_tx_tlast(ack_m_axis_tx_tlast),
    .m_axis_tx_tuser(ack_m_axis_tx_tuser),
    .cfg_peer_base(ctl_cfg_peer_base),
    .cfg_peer_bytes(ctl_cfg_peer_bytes),
    .peer_format_status(peer_format_status),
    .peer_format_memory_status(peer_format_memory_status),
    .peer_cmd_req_valid(0),
    .peer_cmd_req_ready(),
    .peer_cmd_req_op(0),
    .peer_cmd_req_authority(0),
    .peer_cmd_req_maintenance(0),
    .peer_cmd_req_user(0),
    .peer_cmd_req_payload(0),
    .peer_cmd_rsp_valid(),
    .peer_cmd_rsp_ready(0),
    .peer_cmd_rsp_status(),
    .peer_cmd_rsp_detail(),
    .peer_cmd_rsp_memory_status(),
    .peer_cmd_rsp_connection_error(),
    .peer_cmd_rsp_http2_error(),
    .peer_cmd_rsp_op(),
    .peer_cmd_rsp_user(),
    .peer_cmd_rsp_wire_retired(),
    .peer_cmd_rsp_ack_matched(),
    .peer_cmd_rsp_header_table_size(),
    .peer_cmd_rsp_max_concurrent_streams(),
    .peer_cmd_rsp_max_header_list_size(),
    .peer_cmd_rsp_enable_push(),
    .peer_cmd_rsp_ping_pending(),
    .peer_cmd_rsp_settings_pending(),
    .peer_cmd_rsp_settings_acks(),
    .peer_cmd_rsp_ping_acks(),
    .peer_cmd_rsp_ping_payload(),
    .history_fence(ctl_history_fence),
    .history_status(history_status),
    .history_detail(history_detail),
    .history_memory_status(history_memory_status),
    .history_closed(history_closed),
    .history_last_stream(history_last_stream),
    .history_queries(history_queries),
    .cancel_detail(cancel_detail),
    .cancel_memory_status(cancel_memory_status),
    .cancel_connection_error(cancel_connection_error),
    .cancel_http2_error(cancel_http2_error),
    .goaway_req_valid(goaway_req_valid),
    .goaway_req_ready(goaway_req_ready),
    .goaway_user(goaway_user),
    .goaway_last_stream(goaway_last_stream),
    .goaway_error(goaway_error),
    .goaway_rsp_valid(goaway_rsp_valid),
    .goaway_rsp_ready(goaway_rsp_ready),
    .goaway_rsp_status(goaway_rsp_status),
    .goaway_rsp_detail(goaway_rsp_detail),
    .goaway_rsp_memory_status(goaway_rsp_memory_status),
    .goaway_rsp_connection_error(goaway_rsp_connection_error),
    .goaway_rsp_http2_error(goaway_rsp_http2_error),
    .goaway_rsp_op(goaway_rsp_op),
    .goaway_rsp_user(goaway_rsp_user),
    .peer_goaway_received(peer_goaway_received),
    .peer_goaway_last_stream(peer_goaway_last_stream),
    .peer_goaway_error(peer_goaway_error),
    .shutdown_classify_valid(shutdown_classify_valid),
    .shutdown_classify_ready(shutdown_classify_ready),
    .shutdown_classify_user(shutdown_classify_user),
    .shutdown_classify_stream(shutdown_classify_stream),
    .shutdown_classify_rsp_valid(shutdown_classify_rsp_valid),
    .shutdown_classify_rsp_ready(shutdown_classify_rsp_ready),
    .shutdown_classify_rsp_status(shutdown_classify_rsp_status),
    .shutdown_classify_rsp_detail(shutdown_classify_rsp_detail),
    .shutdown_classify_rsp_memory_status(shutdown_classify_rsp_memory_status),
    .shutdown_classify_rsp_user(shutdown_classify_rsp_user),
    .shutdown_classify_rsp_stream(shutdown_classify_rsp_stream),
    .shutdown_classify_rsp_closed(shutdown_classify_rsp_closed),
    .shutdown_classify_rsp_last_stream(shutdown_classify_rsp_last_stream)
);
assign tx_idle=response_idle;


wire  init_window_req_valid;
wire  init_window_req_ready;
wire [3:0] init_window_req_op;
wire  init_window_req_maintenance;
wire [USER_WIDTH-1:0] init_window_req_user;
wire [30:0] init_window_req_stream;
wire [31:0] init_window_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] init_window_req_record_address;
wire [31:0] init_window_req_amount;
wire  init_window_rsp_valid;
wire  init_window_rsp_ready;
wire [7:0] init_window_rsp_status;
wire [7:0] init_window_rsp_detail;
wire [7:0] init_window_rsp_memory_status;
wire  init_window_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] init_window_recovery_address;
wire [MEMORY_ADDR_WIDTH-1:0] init_window_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] init_window_cfg_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] init_window_cfg_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] init_window_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] init_window_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] init_window_cfg_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] init_window_cfg_window_bytes;
wire  service_window_req_valid;
wire  service_window_req_ready;
wire [3:0] service_window_req_op;
wire  service_window_req_maintenance;
wire [USER_WIDTH-1:0] service_window_req_user;
wire [30:0] service_window_req_stream;
wire [31:0] service_window_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_req_record_address;
wire [31:0] service_window_req_amount;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_cfg_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_cfg_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] service_window_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] service_window_cfg_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] service_window_cfg_window_bytes;
wire  service_window_rsp_valid;
wire  service_window_rsp_ready;
wire [3:0] service_window_rsp_op;
wire [USER_WIDTH-1:0] service_window_rsp_user;
wire [30:0] service_window_rsp_stream;
wire [7:0] service_window_rsp_status;
wire [7:0] service_window_rsp_detail;
wire [7:0] service_window_rsp_memory_status;
wire  service_window_rsp_connection_error;
wire [31:0] service_window_rsp_http2_error;
wire [23:0] service_window_rsp_grant_bytes;
wire [31:0] service_window_rsp_connection_window;
wire [31:0] service_window_rsp_initial_window;
wire [31:0] service_window_rsp_stream_window;
wire [23:0] service_window_rsp_max_frame_bytes;
wire [31:0] service_window_rsp_affected_streams;
wire  service_window_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] service_window_recovery_address;
wire  service_window_busy;
wire [7:0] service_window_lock_status;
reg [MEMORY_ADDR_WIDTH-1:0] active_context_base,active_window_base;
reg [MEMORY_ADDR_WIDTH:0] active_context_bytes,active_window_bytes;
always @(posedge clk)begin
    if(rst)begin active_context_base<=0;active_context_bytes<=0;active_window_base<=0;active_window_bytes<=0;end
    else if(command_valid&&command_ready||s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin
        active_context_base<=cfg_context_base;active_context_bytes<=cfg_context_bytes;
        active_window_base<=cfg_window_base;active_window_bytes<=cfg_window_bytes;
    end end
reg [3:0] window_owner;
wire shutdown_window_send=window_owner==7;
wire forward_window_send=window_owner==1,external_window_send=window_owner==3;
assign service_window_req_valid=shutdown_window_send?shutdown_close_valid:forward_window_send?init_window_req_valid:control_window_send?ctl_window_req_valid:external_window_send&&window_req_valid;
assign init_window_req_ready=forward_window_send&&service_window_req_ready;
assign window_req_ready=external_window_send&&service_window_req_ready;
assign init_window_rsp_valid=window_owner==2&&service_window_rsp_valid;
assign window_rsp_valid=window_owner==4&&service_window_rsp_valid;
assign service_window_rsp_ready=window_owner==8?shutdown_close_rsp_ready:window_owner==2?init_window_rsp_ready:window_owner==6?ctl_window_rsp_ready:window_owner==4&&window_rsp_ready;
assign init_window_recovery_required=service_window_recovery_required;
assign init_window_recovery_address=service_window_recovery_address;
always @(posedge clk)begin
    if(rst)window_owner<=0;else case(window_owner)
        0:if(init_window_req_valid)window_owner<=1;else if(shutdown_close_valid)window_owner<=7;else if(ctl_window_req_valid)window_owner<=5;else if(window_req_valid&&!shutdown_recovery_required)window_owner<=3;
        1:if(init_window_req_valid&&service_window_req_ready)window_owner<=2;
        2:if(service_window_rsp_valid&&init_window_rsp_ready)window_owner<=0;
        3:if(window_req_valid&&service_window_req_ready)window_owner<=4;
        4:if(service_window_rsp_valid&&window_rsp_ready)window_owner<=0;
        5:if(ctl_window_req_valid&&service_window_req_ready)window_owner<=6;
        6:if(service_window_rsp_valid&&ctl_window_rsp_ready)window_owner<=0;
        7:if(shutdown_close_valid&&service_window_req_ready)window_owner<=8;
        8:if(service_window_rsp_valid&&shutdown_close_rsp_ready)window_owner<=0;
        default:window_owner<=0;endcase end
assign service_window_req_op=shutdown_window_send?4'd10:forward_window_send?init_window_req_op:control_window_send?ctl_window_req_op:window_req_op;
assign service_window_req_maintenance=shutdown_window_send?1'b0:forward_window_send?init_window_req_maintenance:control_window_send?ctl_window_req_maintenance:window_req_maintenance;
assign service_window_req_user=shutdown_window_send?shutdown_close_user:forward_window_send?init_window_req_user:control_window_send?ctl_window_req_user:window_req_user;
assign service_window_req_stream=shutdown_window_send?shutdown_close_stream:forward_window_send?init_window_req_stream:control_window_send?ctl_window_req_stream:window_req_stream;
assign service_window_req_generation=shutdown_window_send?0:forward_window_send?init_window_req_generation:control_window_send?ctl_window_req_generation:window_req_generation;
assign service_window_req_record_address=shutdown_window_send?0:forward_window_send?init_window_req_record_address:control_window_send?ctl_window_req_record_address:window_req_record_address;
assign service_window_req_amount=shutdown_window_send?0:forward_window_send?init_window_req_amount:control_window_send?ctl_window_req_amount:window_req_amount;
assign service_window_cfg_context_base=shutdown_window_send?shutdown_owned_context_base:forward_window_send?init_window_cfg_context_base:control_window_send?ctl_window_cfg_context_base:window_cfg_context_base;
assign service_window_cfg_stream_base=shutdown_window_send?shutdown_owned_stream_base:forward_window_send?init_window_cfg_stream_base:control_window_send?ctl_window_cfg_stream_base:window_cfg_stream_base;
assign service_window_cfg_window_base=shutdown_window_send?shutdown_owned_window_base:forward_window_send?init_window_cfg_window_base:control_window_send?ctl_window_cfg_window_base:window_cfg_window_base;
assign service_window_cfg_work_floor=shutdown_window_send?shutdown_owned_work_floor:forward_window_send?init_window_cfg_work_floor:control_window_send?ctl_window_cfg_work_floor:window_cfg_work_floor;
assign service_window_cfg_context_bytes=shutdown_window_send?shutdown_owned_context_bytes:forward_window_send?init_window_cfg_context_bytes:control_window_send?ctl_window_cfg_context_bytes:window_cfg_context_bytes;
assign service_window_cfg_stream_bytes=shutdown_window_send?shutdown_owned_stream_bytes:forward_window_send?init_window_cfg_stream_bytes:control_window_send?ctl_window_cfg_stream_bytes:window_cfg_stream_bytes;
assign service_window_cfg_window_bytes=shutdown_window_send?shutdown_owned_window_bytes:forward_window_send?init_window_cfg_window_bytes:control_window_send?ctl_window_cfg_window_bytes:window_cfg_window_bytes;
assign window_rsp_op=service_window_rsp_op;
assign window_rsp_user=service_window_rsp_user;
assign window_rsp_stream=service_window_rsp_stream;
assign window_rsp_status=service_window_rsp_status;
assign init_window_rsp_status=service_window_rsp_status;
assign window_rsp_detail=service_window_rsp_detail;
assign init_window_rsp_detail=service_window_rsp_detail;
assign window_rsp_memory_status=service_window_rsp_memory_status;
assign init_window_rsp_memory_status=service_window_rsp_memory_status;
assign window_rsp_connection_error=service_window_rsp_connection_error;
assign window_rsp_http2_error=service_window_rsp_http2_error;
assign window_rsp_grant_bytes=service_window_rsp_grant_bytes;
assign window_rsp_connection_window=service_window_rsp_connection_window;
assign window_rsp_initial_window=service_window_rsp_initial_window;
assign window_rsp_stream_window=service_window_rsp_stream_window;
assign window_rsp_max_frame_bytes=service_window_rsp_max_frame_bytes;
assign window_rsp_affected_streams=service_window_rsp_affected_streams;
assign window_recovery_required=service_window_recovery_required;
assign window_recovery_address=service_window_recovery_address;
assign window_busy=service_window_busy;
assign window_lock_status=service_window_lock_status;

wire  f_queue_cfg_valid;
wire  f_queue_cfg_ready;
wire  f_control_valid;
wire  f_control_ready;
wire [2:0] f_control_op;
wire [USER_WIDTH-1:0] f_control_user;
wire [USER_WIDTH-1:0] f_control_application;
wire [30:0] f_control_stream;
wire [31:0] f_control_generation;
wire [MEMORY_ADDR_WIDTH-1:0] f_control_address;
wire [MEMORY_ADDR_WIDTH-1:0] f_control_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] f_control_buffer_bytes;
wire [31:0] f_control_message_limit;
wire  f_control_protobuf;
wire  f_control_unsupported_encoding;
wire  f_control_maintenance;
wire  f_control_result_valid;
wire  f_control_result_ready;
wire [7:0] f_control_status;
wire [7:0] f_control_detail;
wire [7:0] f_control_memory_status;
wire [2:0] f_control_result_op;
wire [MEMORY_ADDR_WIDTH-1:0] f_control_result_address;
wire [MEMORY_ADDR_WIDTH-1:0] f_control_result_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] f_control_result_buffer_bytes;
wire [USER_WIDTH-1:0] f_control_result_user;
wire [USER_WIDTH-1:0] f_control_result_application;
wire [30:0] f_control_result_stream;
wire [31:0] f_control_result_generation;
wire [31:0] f_control_result_message_limit;
wire  f_control_result_protobuf;
wire  f_control_result_unsupported_encoding;
wire [255:0] f_control_result_state;
wire  f_stream_cfg_valid;
wire  f_stream_cfg_ready;
wire  f_cfg_schema_valid;
wire  f_cfg_schema_ready;
wire  f_cfg_quiescent;
wire  f_command_valid;
wire  f_command_ready;
wire  f_s_axis_rx_tvalid;
wire  f_s_axis_rx_tready;
wire  f_idle;
wire [19:0] f_mem_valid;
wire [19:0] f_mem_ready;
wire [19:0] f_mem_write;
wire [20*MEMORY_ADDR_WIDTH-1:0] f_mem_addr;
wire [79:0] f_mem_bytes;
wire [1439:0] f_mem_data;
wire [19:0] f_mem_rsp_valid;
wire [19:0] f_mem_rsp_ready;
wire [1439:0] f_mem_rsp_data;
wire [159:0] f_mem_rsp_status;
wire  dir_req_valid;
wire  dir_req_ready;
wire [2:0] dir_req_op;
wire [MEMORY_ADDR_WIDTH-1:0] dir_cfg_pool_base;
wire [MEMORY_ADDR_WIDTH:0] dir_cfg_pool_bytes;
wire [USER_WIDTH-1:0] dir_req_user;
wire [USER_WIDTH-1:0] dir_req_application;
wire [30:0] dir_req_stream;
wire [31:0] dir_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] dir_req_address;
wire [MEMORY_ADDR_WIDTH-1:0] dir_req_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] dir_req_buffer_bytes;
wire [31:0] dir_req_message_limit;
wire  dir_req_protobuf;
wire  dir_req_unsupported_encoding;
wire  dir_req_maintenance;
wire [255:0] dir_req_state;
wire  dir_rsp_valid;
wire  dir_rsp_ready;
wire [7:0] dir_rsp_status;
wire [7:0] dir_rsp_detail;
wire [7:0] dir_rsp_memory_status;
wire [2:0] dir_rsp_op;
wire [MEMORY_ADDR_WIDTH-1:0] dir_rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] dir_rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] dir_rsp_buffer_bytes;
wire [USER_WIDTH-1:0] dir_rsp_user;
wire [USER_WIDTH-1:0] dir_rsp_application;
wire [30:0] dir_rsp_stream;
wire [31:0] dir_rsp_generation;
wire [31:0] dir_rsp_message_limit;
wire  dir_rsp_protobuf;
wire  dir_rsp_unsupported_encoding;
wire [255:0] dir_rsp_state;
wire  dir_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] dir_recovery_address;
wire  dir_idle;
reg shutdown_control_offered;
wire shutdown_control_admit=shutdown_control_offered||(!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required);
assign f_control_valid=control_valid&&shutdown_control_admit;
assign control_ready=f_control_ready&&shutdown_control_admit;
always @(posedge clk)begin
if(rst)shutdown_control_offered<=0;
else if(f_control_valid)shutdown_control_offered<=!f_control_ready;
end
assign f_control_op=control_op;
assign f_control_user=control_user;
assign f_control_application=control_application;
assign f_control_stream=control_stream;
assign f_control_generation=control_generation;
assign f_control_address=control_address;
assign f_control_buffer_base=control_buffer_base;
assign f_control_buffer_bytes=control_buffer_bytes;
assign f_control_message_limit=control_message_limit;
assign f_control_protobuf=control_protobuf;
assign f_control_unsupported_encoding=control_unsupported_encoding;
assign f_control_maintenance=control_maintenance;
assign control_result_valid=f_control_result_valid;
assign f_control_result_ready=control_result_ready;
assign control_status=f_control_status;
assign control_detail=f_control_detail;
assign control_memory_status=f_control_memory_status;
assign control_result_op=f_control_result_op;
assign control_result_address=f_control_result_address;
assign control_result_buffer_base=f_control_result_buffer_base;
assign control_result_buffer_bytes=f_control_result_buffer_bytes;
assign control_result_user=f_control_result_user;
assign control_result_application=f_control_result_application;
assign control_result_stream=f_control_result_stream;
assign control_result_generation=f_control_result_generation;
assign control_result_message_limit=f_control_result_message_limit;
assign control_result_protobuf=f_control_result_protobuf;
assign control_result_unsupported_encoding=f_control_result_unsupported_encoding;
assign control_result_state=f_control_result_state;
assign f_queue_cfg_valid=queue_cfg_valid&&allow_config;
assign queue_cfg_ready=f_queue_cfg_ready&&allow_config;
assign f_stream_cfg_valid=stream_cfg_valid&&allow_config;
assign stream_cfg_ready=f_stream_cfg_ready&&allow_config;
assign f_cfg_schema_valid=cfg_schema_valid&&allow_config;
assign cfg_schema_ready=f_cfg_schema_ready&&allow_config;
assign f_command_valid=command_valid&&allow_config;
assign command_ready=f_command_ready&&allow_config;
wire r_directory_valid,r_directory_ready;
reg rx_active,return_pending,owned_stream_valid,forward_quiet,return_ack_seen,generated_offered;
reg [USER_WIDTH-1:0] return_user;reg [30:0] return_stream;
reg [MEMORY_ADDR_WIDTH-1:0] pending_stream_base,owned_stream_base;
reg [MEMORY_ADDR_WIDTH:0] pending_stream_bytes,owned_stream_bytes;
wire reverse_input_ready;
wire reverse_new_admit=owned_stream_valid&&!return_pending&&!cfg_unlock&&!control_valid&&!journal_recovery_required&&
    !command_valid&&!queue_cfg_valid&&!stream_cfg_valid&&!queue_cfg_result_valid&&!stream_cfg_result_valid;
wire reverse_admit=generated_offered||(reverse_new_admit&&!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required);
wire lookup_admit=return_pending&&forward_quiet&&!rx_active&&!control_valid&&!journal_recovery_required;
wire allow_new_rx=!journal_recovery_required&&!(s_axis_generated_tvalid&&reverse_admit)&&!(r_directory_valid&&lookup_admit);
wire allow_config=!return_pending&&!generated_offered&&!shutdown_busy&&!cancel_valid&&!shutdown_recovery_required;
assign f_s_axis_rx_tvalid=s_axis_rx_tvalid&&(rx_active||allow_new_rx);
assign s_axis_rx_tready=f_s_axis_rx_tready&&(rx_active||allow_new_rx);
assign s_axis_generated_tready=reverse_input_ready&&reverse_admit;
assign cfg_quiescent=f_cfg_quiescent&&allow_config;
assign idle=f_idle&&response_idle&&journal_idle&&tx_idle&&!rx_active&&!s_axis_generated_tvalid&&!shutdown_busy&&!shutdown_recovery_required&&shutdown_dir_owner==0;
always @(posedge clk)begin
    if(rst)begin
        rx_active<=0;return_pending<=0;owned_stream_valid<=0;forward_quiet<=0;return_ack_seen<=0;generated_offered<=0;return_user<=0;return_stream<=0;
        pending_stream_base<=0;pending_stream_bytes<=0;owned_stream_base<=0;owned_stream_bytes<=0;
    end else begin
        forward_quiet<=f_idle&&!(s_axis_rx_tvalid&&s_axis_rx_tready)&&!control_valid&&!command_valid&&
            !queue_cfg_valid&&!stream_cfg_valid;
        if(s_axis_rx_tvalid&&s_axis_rx_tready)rx_active<=!s_axis_rx_tlast;
        if(s_axis_generated_tvalid&&reverse_admit)generated_offered<=!reverse_input_ready;
        if(s_axis_generated_tvalid&&s_axis_generated_tready)begin
            return_pending<=1;return_ack_seen<=0;return_user<=s_axis_generated_tuser;return_stream<=generated_stream;
        end
        if(response_result_valid&&response_result_ready)return_ack_seen<=1;
        if(return_ack_seen&&!response_record_lease_active&&!response_result_retirement_pending)begin return_pending<=0;return_ack_seen<=0;end
        if(stream_cfg_valid&&stream_cfg_ready)begin pending_stream_base<=cfg_stream_base;pending_stream_bytes<=cfg_stream_bytes;end
        if(stream_cfg_result_valid&&stream_cfg_status==0)begin owned_stream_base<=pending_stream_base;owned_stream_bytes<=pending_stream_bytes;owned_stream_valid<=1;end
    end
end
assign mem_valid[0+:20]=f_mem_valid;
assign f_mem_ready=mem_ready[0+:20];
assign mem_write[0+:20]=f_mem_write;
assign mem_addr[0+:20*MEMORY_ADDR_WIDTH]=f_mem_addr;
assign mem_bytes[0+:80]=f_mem_bytes;
assign mem_data[0+:1440]=f_mem_data;
assign f_mem_rsp_valid=mem_rsp_valid[0+:20];
assign mem_rsp_ready[0+:20]=f_mem_rsp_ready;
assign f_mem_rsp_data=mem_rsp_data[0+:1440];
assign f_mem_rsp_status=mem_rsp_status[0+:160];
http2_classified_parser_transport #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),
.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)) forward(
    .clk(clk),
    .rst(rst),
    .cfg_stream_base(cfg_stream_base),
    .cfg_stream_bytes(cfg_stream_bytes),
    .queue_cfg_valid(f_queue_cfg_valid),
    .queue_cfg_ready(f_queue_cfg_ready),
    .queue_cfg_clear(queue_cfg_clear),
    .maintenance_grant(maintenance_grant),
    .queue_cfg_base(queue_cfg_base),
    .queue_cfg_bytes(queue_cfg_bytes),
    .queue_cfg_result_valid(queue_cfg_result_valid),
    .queue_cfg_result_ready(queue_cfg_result_ready),
    .queue_cfg_status(queue_cfg_status),
    .control_valid(f_control_valid),
    .control_ready(f_control_ready),
    .control_op(f_control_op),
    .control_user(f_control_user),
    .control_application(f_control_application),
    .control_stream(f_control_stream),
    .control_generation(f_control_generation),
    .control_address(f_control_address),
    .control_buffer_base(f_control_buffer_base),
    .control_buffer_bytes(f_control_buffer_bytes),
    .control_message_limit(f_control_message_limit),
    .control_protobuf(f_control_protobuf),
    .control_unsupported_encoding(f_control_unsupported_encoding),
    .control_maintenance(f_control_maintenance),
    .control_result_valid(f_control_result_valid),
    .control_result_ready(f_control_result_ready),
    .control_status(f_control_status),
    .control_detail(f_control_detail),
    .control_memory_status(f_control_memory_status),
    .control_result_op(f_control_result_op),
    .control_result_address(f_control_result_address),
    .control_result_buffer_base(f_control_result_buffer_base),
    .control_result_buffer_bytes(f_control_result_buffer_bytes),
    .control_result_user(f_control_result_user),
    .control_result_application(f_control_result_application),
    .control_result_stream(f_control_result_stream),
    .control_result_generation(f_control_result_generation),
    .control_result_message_limit(f_control_result_message_limit),
    .control_result_protobuf(f_control_result_protobuf),
    .control_result_unsupported_encoding(f_control_result_unsupported_encoding),
    .control_result_state(f_control_result_state),
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
    .stream_cfg_valid(f_stream_cfg_valid),
    .stream_cfg_ready(f_stream_cfg_ready),
    .stream_cfg_result_valid(stream_cfg_result_valid),
    .stream_cfg_result_ready(stream_cfg_result_ready),
    .stream_cfg_status(stream_cfg_status),
    .cfg_unlock(cfg_unlock),
    .cfg_schema_valid(f_cfg_schema_valid),
    .cfg_schema_ready(f_cfg_schema_ready),
    .cfg_quiescent(f_cfg_quiescent),
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
    .m_axis_tokens_tdata(m_axis_tokens_tdata),
    .m_axis_tokens_tkeep(m_axis_tokens_tkeep),
    .m_axis_tokens_tvalid(m_axis_tokens_tvalid),
    .m_axis_tokens_tready(m_axis_tokens_tready),
    .m_axis_tokens_tlast(m_axis_tokens_tlast),
    .m_axis_tokens_tuser(m_axis_tokens_tuser),
    .dma_connection(dma_connection),
    .dma_stream(dma_stream),
    .dma_generation(dma_generation),
    .dma_ordinal(dma_ordinal),
    .dma_packet_tag(dma_packet_tag),
    .completion_count(completion_count),
    .completion_token_stage(completion_token_stage),
    .completion_token_detail(completion_token_detail),
    .completion_token_status(completion_token_status),
    .s_return_tdata(128'd0),
    .s_return_tkeep(16'd0),
    .s_return_tvalid(1'b0),
    .s_return_tready(),
    .s_return_tlast(1'b0),
    .s_return_tuser({USER_WIDTH{1'b0}}),
    .m_return_tdata(),
    .m_return_tkeep(),
    .m_return_tvalid(),
    .m_return_tready(1'b1),
    .m_return_tlast(),
    .m_return_tuser(),
    .admit_packets(admit_packets),
    .cfg_context_base(cfg_context_base),
    .cfg_context_bytes(cfg_context_bytes),
    .command_valid(f_command_valid),
    .command_ready(f_command_ready),
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
    .s_axis_rx_tvalid(f_s_axis_rx_tvalid),
    .s_axis_rx_tready(f_s_axis_rx_tready),
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
    .idle(f_idle),
    .mem_valid(f_mem_valid),
    .mem_ready(f_mem_ready),
    .mem_write(f_mem_write),
    .mem_addr(f_mem_addr),
    .mem_bytes(f_mem_bytes),
    .mem_data(f_mem_data),
    .mem_rsp_valid(f_mem_rsp_valid),
    .mem_rsp_ready(f_mem_rsp_ready),
    .mem_rsp_data(f_mem_rsp_data),
    .mem_rsp_status(f_mem_rsp_status),
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
    .dir_req_valid(dir_req_valid),
    .dir_req_ready(dir_req_ready),
    .dir_req_op(dir_req_op),
    .dir_cfg_pool_base(dir_cfg_pool_base),
    .dir_cfg_pool_bytes(dir_cfg_pool_bytes),
    .dir_req_user(dir_req_user),
    .dir_req_application(dir_req_application),
    .dir_req_stream(dir_req_stream),
    .dir_req_generation(dir_req_generation),
    .dir_req_address(dir_req_address),
    .dir_req_buffer_base(dir_req_buffer_base),
    .dir_req_buffer_bytes(dir_req_buffer_bytes),
    .dir_req_message_limit(dir_req_message_limit),
    .dir_req_protobuf(dir_req_protobuf),
    .dir_req_unsupported_encoding(dir_req_unsupported_encoding),
    .dir_req_maintenance(dir_req_maintenance),
    .dir_req_state(dir_req_state),
    .dir_rsp_valid(dir_rsp_valid),
    .dir_rsp_ready(dir_rsp_ready),
    .dir_rsp_status(dir_rsp_status),
    .dir_rsp_detail(dir_rsp_detail),
    .dir_rsp_memory_status(dir_rsp_memory_status),
    .dir_rsp_op(dir_rsp_op),
    .dir_rsp_address(dir_rsp_address),
    .dir_rsp_buffer_base(dir_rsp_buffer_base),
    .dir_rsp_buffer_bytes(dir_rsp_buffer_bytes),
    .dir_rsp_user(dir_rsp_user),
    .dir_rsp_application(dir_rsp_application),
    .dir_rsp_stream(dir_rsp_stream),
    .dir_rsp_generation(dir_rsp_generation),
    .dir_rsp_message_limit(dir_rsp_message_limit),
    .dir_rsp_protobuf(dir_rsp_protobuf),
    .dir_rsp_unsupported_encoding(dir_rsp_unsupported_encoding),
    .dir_rsp_state(dir_rsp_state),
    .dir_recovery_required(dir_recovery_required),
    .dir_recovery_address(dir_recovery_address),
    .dir_idle(dir_idle),
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
    .cfg_window_base(cfg_window_base),
    .cfg_window_bytes(cfg_window_bytes),
    .header_window_status(header_window_status),
    .command_window_status(command_window_status),
    .command_window_cleanup_status(command_window_cleanup_status),
    .init_window_req_valid(init_window_req_valid),
    .init_window_req_ready(init_window_req_ready),
    .init_window_req_op(init_window_req_op),
    .init_window_req_maintenance(init_window_req_maintenance),
    .init_window_req_user(init_window_req_user),
    .init_window_req_stream(init_window_req_stream),
    .init_window_req_generation(init_window_req_generation),
    .init_window_req_record_address(init_window_req_record_address),
    .init_window_req_amount(init_window_req_amount),
    .init_window_rsp_valid(init_window_rsp_valid),
    .init_window_rsp_ready(init_window_rsp_ready),
    .init_window_rsp_status(init_window_rsp_status),
    .init_window_rsp_detail(init_window_rsp_detail),
    .init_window_rsp_memory_status(init_window_rsp_memory_status),
    .init_window_recovery_required(init_window_recovery_required),
    .init_window_recovery_address(init_window_recovery_address),
    .init_window_cfg_context_base(init_window_cfg_context_base),
    .init_window_cfg_stream_base(init_window_cfg_stream_base),
    .init_window_cfg_window_base(init_window_cfg_window_base),
    .init_window_cfg_work_floor(init_window_cfg_work_floor),
    .init_window_cfg_context_bytes(init_window_cfg_context_bytes),
    .init_window_cfg_stream_bytes(init_window_cfg_stream_bytes),
    .init_window_cfg_window_bytes(init_window_cfg_window_bytes),
    .cfg_control_journal_base(cfg_control_journal_base),
    .cfg_control_journal_bytes(cfg_control_journal_bytes),
    .cfg_control_slot_bytes(cfg_control_slot_bytes),
    .command_control_status(command_control_status),
    .packet_control_status(packet_control_status),
    .packet_control_detail(packet_control_detail),
    .packet_control_memory_status(packet_control_memory_status),
    .ctl_start_valid(ctl_start_valid),
    .ctl_start_ready(ctl_start_ready),
    .ctl_start_format(ctl_start_format),
    .ctl_start_maintenance(ctl_start_maintenance),
    .ctl_start_user(ctl_start_user),
    .ctl_finish_valid(ctl_finish_valid),
    .ctl_finish_ready(ctl_finish_ready),
    .ctl_finish_commit(ctl_finish_commit),
    .ctl_result_valid(ctl_result_valid),
    .ctl_result_ready(ctl_result_ready),
    .ctl_result_status(ctl_result_status),
    .ctl_result_detail(ctl_result_detail),
    .ctl_result_memory_status(ctl_result_memory_status),
    .control_drop_events(control_drop_events),
    .ctl_cfg_context_base(ctl_cfg_context_base),
    .ctl_cfg_stream_base(ctl_cfg_stream_base),
    .ctl_cfg_window_base(ctl_cfg_window_base),
    .ctl_cfg_work_floor(ctl_cfg_work_floor),
    .ctl_cfg_journal_base(ctl_cfg_journal_base),
    .ctl_cfg_context_bytes(ctl_cfg_context_bytes),
    .ctl_cfg_stream_bytes(ctl_cfg_stream_bytes),
    .ctl_cfg_window_bytes(ctl_cfg_window_bytes),
    .ctl_cfg_journal_bytes(ctl_cfg_journal_bytes),
    .ctl_cfg_slot_bytes(ctl_cfg_slot_bytes),
    .cfg_peer_base(cfg_peer_base),
    .cfg_peer_bytes(cfg_peer_bytes),
    .ctl_cfg_peer_base(ctl_cfg_peer_base),
    .ctl_cfg_peer_bytes(ctl_cfg_peer_bytes),
    .ctl_history_fence(ctl_history_fence),
    .ctl_result_http2_error(journal_control_http2_error)
);
rpc_grpc_cancellable_return #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) reverse(
    .clk(clk),
    .rst(rst),
    .s_axis_tokens_tdata(s_axis_generated_tdata),
    .s_axis_tokens_tkeep(s_axis_generated_tkeep),
    .s_axis_tokens_tvalid(s_axis_generated_tvalid&&reverse_admit),
    .s_axis_tokens_tready(reverse_input_ready),
    .s_axis_tokens_tlast(s_axis_generated_tlast),
    .s_axis_tokens_tuser(s_axis_generated_tuser),
    .s_stream(generated_stream),
    .s_generation(generated_generation),
    .s_model_epoch(generated_model_epoch),
    .s_schema_epoch(generated_schema_epoch),
    .s_ordinal(generated_ordinal),
    .cfg_stream_base(owned_stream_base),
    .cfg_progress_base(cfg_response_progress_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_stream_bytes(owned_stream_bytes),
    .cfg_progress_bytes(cfg_response_progress_bytes),
    .cfg_model_epoch(cfg_model_epoch),
    .cfg_schema_epoch(cfg_schema_epoch),
    .cfg_directory_base(cfg_response_directory_base),
    .cfg_pool_base(cfg_response_pool_base),
    .cfg_directory_bytes(cfg_response_directory_bytes),
    .cfg_pool_bytes(cfg_response_pool_bytes),
    .cfg_strip_special(cfg_response_strip_special),
    .cfg_replace_invalid(cfg_response_replace_invalid),
    .cfg_format(cfg_response_format),
    .cfg_protobuf_field(cfg_response_protobuf_field),
    .m_axis_tx_tdata(m_axis_tx_tdata),
    .m_axis_tx_tkeep(m_axis_tx_tkeep),
    .m_axis_tx_tvalid(m_axis_tx_tvalid),
    .m_axis_tx_tready(m_axis_tx_tready),
    .m_axis_tx_tlast(m_axis_tx_tlast),
    .m_axis_tx_tuser(m_axis_tx_tuser),
    .result_valid(response_result_valid),
    .result_ready(response_result_ready),
    .result_stage(response_result_stage),
    .result_status(response_result_status),
    .result_memory_status(response_result_memory_status),
    .result_user(response_result_user),
    .result_application(response_result_application),
    .result_stream(response_result_stream),
    .result_generation(response_result_generation),
    .result_model_epoch(response_result_model_epoch),
    .result_schema_epoch(response_result_schema_epoch),
    .result_ordinal(response_result_ordinal),
    .result_bytes(response_result_bytes),
    .result_eos(response_result_eos),
    .result_tx_emitted(response_result_tx_emitted),
    .recovery_required(response_recovery_required),
    .recovery_address(response_recovery_address),
    .directory_lease_active(response_directory_lease_active),
    .idle(response_idle),
    .mem_valid(mem_valid[20*1+:3*1]),
    .mem_ready(mem_ready[20*1+:3*1]),
    .mem_write(mem_write[20*1+:3*1]),
    .mem_addr(mem_addr[20*MEMORY_ADDR_WIDTH+:3*MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[20*4+:3*4]),
    .mem_data(mem_data[20*72+:3*72]),
    .mem_rsp_valid(mem_rsp_valid[20*1+:3*1]),
    .mem_rsp_ready(mem_rsp_ready[20*1+:3*1]),
    .mem_rsp_data(mem_rsp_data[20*72+:3*72]),
    .mem_rsp_status(mem_rsp_status[20*8+:3*8]),
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
    .cfg_peer_max_frame_bytes(cfg_peer_max_frame_bytes),
    .result_serialized_bytes(result_serialized_bytes),
    .result_wire_bytes(result_wire_bytes),
    .result_frames(result_frames),
    .result_progress_committed(response_result_progress_committed),
    .control_req_valid(service_control_req_valid),
    .control_req_ready(service_control_req_ready),
    .control_req_op(service_control_req_op),
    .control_pool_base(service_control_pool_base),
    .control_pool_bytes(service_control_pool_bytes),
    .control_req_user(service_control_req_user),
    .control_req_application(service_control_req_application),
    .control_req_stream(service_control_req_stream),
    .control_req_generation(service_control_req_generation),
    .control_req_address(service_control_req_address),
    .control_req_buffer_base(service_control_req_buffer_base),
    .control_req_buffer_bytes(service_control_req_buffer_bytes),
    .control_req_message_limit(service_control_req_message_limit),
    .control_req_protobuf(service_control_req_protobuf),
    .control_req_unsupported_encoding(service_control_req_unsupported_encoding),
    .control_req_maintenance(service_control_req_maintenance),
    .control_req_state(service_control_req_state),
    .control_rsp_valid(service_control_rsp_valid),
    .control_rsp_ready(service_control_rsp_ready),
    .control_rsp_status(service_control_rsp_status),
    .control_rsp_detail(service_control_rsp_detail),
    .control_rsp_memory_status(service_control_rsp_memory_status),
    .control_rsp_op(service_control_rsp_op),
    .control_rsp_address(service_control_rsp_address),
    .control_rsp_buffer_base(service_control_rsp_buffer_base),
    .control_rsp_buffer_bytes(service_control_rsp_buffer_bytes),
    .control_rsp_user(service_control_rsp_user),
    .control_rsp_application(service_control_rsp_application),
    .control_rsp_stream(service_control_rsp_stream),
    .control_rsp_generation(service_control_rsp_generation),
    .control_rsp_message_limit(service_control_rsp_message_limit),
    .control_rsp_protobuf(service_control_rsp_protobuf),
    .control_rsp_unsupported_encoding(service_control_rsp_unsupported_encoding),
    .control_rsp_state(service_control_rsp_state),
    .window_req_valid(service_window_req_valid),
    .window_req_ready(service_window_req_ready),
    .window_req_op(service_window_req_op),
    .window_req_maintenance(service_window_req_maintenance),
    .window_req_user(service_window_req_user),
    .window_req_stream(service_window_req_stream),
    .window_req_generation(service_window_req_generation),
    .window_req_record_address(service_window_req_record_address),
    .window_req_amount(service_window_req_amount),
    .window_cfg_context_base(service_window_cfg_context_base),
    .window_cfg_stream_base(service_window_cfg_stream_base),
    .window_cfg_window_base(service_window_cfg_window_base),
    .window_cfg_work_floor(service_window_cfg_work_floor),
    .window_cfg_context_bytes(service_window_cfg_context_bytes),
    .window_cfg_stream_bytes(service_window_cfg_stream_bytes),
    .window_cfg_window_bytes(service_window_cfg_window_bytes),
    .window_rsp_valid(service_window_rsp_valid),
    .window_rsp_ready(service_window_rsp_ready),
    .window_rsp_op(service_window_rsp_op),
    .window_rsp_user(service_window_rsp_user),
    .window_rsp_stream(service_window_rsp_stream),
    .window_rsp_status(service_window_rsp_status),
    .window_rsp_detail(service_window_rsp_detail),
    .window_rsp_memory_status(service_window_rsp_memory_status),
    .window_rsp_connection_error(service_window_rsp_connection_error),
    .window_rsp_http2_error(service_window_rsp_http2_error),
    .window_rsp_grant_bytes(service_window_rsp_grant_bytes),
    .window_rsp_connection_window(service_window_rsp_connection_window),
    .window_rsp_initial_window(service_window_rsp_initial_window),
    .window_rsp_stream_window(service_window_rsp_stream_window),
    .window_rsp_max_frame_bytes(service_window_rsp_max_frame_bytes),
    .window_rsp_affected_streams(service_window_rsp_affected_streams),
    .window_recovery_required(service_window_recovery_required),
    .window_recovery_address(service_window_recovery_address),
    .window_busy(service_window_busy),
    .window_lock_status(service_window_lock_status),
    .cfg_context_base(active_context_base),
    .cfg_context_bytes(active_context_bytes),
    .cfg_window_base(active_window_base),
    .cfg_window_bytes(active_window_bytes),
    .record_lease_active(response_record_lease_active),
    .directory_recovery_required(dir_recovery_required),
    .directory_recovery_address(dir_recovery_address),
    .credit_parked(credit_parked),
    .directory_pool_lock_active(directory_pool_lock_active),
    .result_credit_status(response_result_credit_status),
    .result_credit_detail(response_result_credit_detail),
    .result_credit_http2_error(response_result_credit_http2_error),
    .result_credit_connection_error(response_result_credit_connection_error),
    .lookup_admit(lookup_admit),
    .lookup_waiting(r_directory_valid),
    .lookup_ready(r_directory_ready),
    .control_idle(service_directory_idle),
    .window_rsp_binding_valid(service_window_rsp_binding_valid),
    .window_rsp_record_address(service_window_rsp_record_address),
    .window_rsp_generation(service_window_rsp_generation),
    .window_rsp_send_closed(service_window_rsp_send_closed),
    .freeze_valid(shutdown_return_freeze_valid),
    .freeze_ready(shutdown_return_freeze_ready),
    .freeze_user(shutdown_return_freeze_user),
    .freeze_stream(shutdown_return_freeze_stream),
    .freeze_active(shutdown_return_freeze_active),
    .freeze_drained(shutdown_return_freeze_drained),
    .freeze_binding_valid(shutdown_return_freeze_binding_valid),
    .freeze_record_address(shutdown_return_freeze_record_address),
    .freeze_generation(shutdown_return_freeze_generation),
    .freeze_release_valid(shutdown_return_freeze_release_valid),
    .freeze_release_ready(shutdown_return_freeze_release_ready),
    .frame_wire_pending(shutdown_return_frame_wire_pending),
    .frame_tracking_error(shutdown_return_frame_tracking_error),
    .b_axis_tdata(ack_m_axis_tx_tdata),
    .b_axis_tkeep(ack_m_axis_tx_tkeep),
    .b_axis_tvalid(ack_m_axis_tx_tvalid),
    .b_axis_tready(ack_m_axis_tx_tready),
    .b_axis_tlast(ack_m_axis_tx_tlast),
    .b_axis_tuser(ack_m_axis_tx_tuser),
    .data_wire_paused(shutdown_return_data_wire_paused),
    .result_cancelled(response_result_cancelled),
    .result_retirement_pending(response_result_retirement_pending)
);

endmodule
`default_nettype wire
