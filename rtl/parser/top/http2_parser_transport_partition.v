`timescale 1ns/1ps
`default_nettype none
// Generated logical partition. Physical transport is not implemented here.
// Raw HTTP/2 -> leased HPACK/request policy -> real RPC admission -> Parser/BPE.
// Control events are exposed to the pending full flow-control/response layer.
// Packet errors conservatively retire this connection, including stream errors.
module http2_parser_transport_partition #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,
    parameter integer MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384
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
    output wire [USER_WIDTH-1:0] m_return_tuser,
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
input wire [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base,cfg_work_floor,cfg_route_base,cfg_route_strings_base,
input wire [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes,cfg_payload_slot_bytes,cfg_route_bytes,cfg_route_strings_bytes,
input wire [31:0] cfg_routes,cfg_model_epoch,cfg_schema_epoch,
output wire header_valid,input wire header_ready,
output wire [3:0] header_status,output wire [7:0] header_detail,header_memory_status,header_control_status,header_cleanup_status,
output wire header_connection_error,output wire [31:0] header_http2_error,output wire [9:0] header_http_status,output wire [7:0] header_grpc_status,
output wire [USER_WIDTH-1:0] header_user,output wire [30:0] header_stream,output wire [31:0] header_generation,
output wire [MEMORY_ADDR_WIDTH-1:0] header_address,
output wire [15:0] header_application,output wire [31:0] header_model_epoch,header_schema_epoch,
output wire header_trailers,header_end_stream,
output wire admission_recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] admission_recovery_address,output wire [USER_WIDTH-1:0] admission_recovery_user,
output wire transport_recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] transport_recovery_address,
output wire control_event_valid,input wire control_event_ready,output wire [3:0] control_event_kind,
output wire [31:0] control_event_arg0,control_event_arg1,output wire [30:0] control_event_stream,output wire [USER_WIDTH-1:0] control_event_user,
output wire [7:0] transport_packet_status,transport_packet_detail,transport_packet_memory_status,output wire [31:0] transport_packet_http2_error,
output wire idle,
output wire [19:0] mem_valid,input wire [19:0] mem_ready,output wire [19:0] mem_write,
output wire [20*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [79:0] mem_bytes,output wire [1439:0] mem_data,
input wire [19:0] mem_rsp_valid,output wire [19:0] mem_rsp_ready,input wire [1439:0] mem_rsp_data,input wire [159:0] mem_rsp_status
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
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_stream_base;
    wire [MEMORY_ADDR_WIDTH:0] p_cfg_stream_bytes;
    wire  p_queue_cfg_valid;
    wire  p_queue_cfg_ready;
    wire  p_queue_cfg_clear;
    wire  p_maintenance_grant;
    wire [MEMORY_ADDR_WIDTH-1:0] p_queue_cfg_base;
    wire [MEMORY_ADDR_WIDTH:0] p_queue_cfg_bytes;
    wire  p_queue_cfg_result_valid;
    wire  p_queue_cfg_result_ready;
    wire [7:0] p_queue_cfg_status;
    wire  p_control_valid;
    wire  p_control_ready;
    wire [2:0] p_control_op;
    wire [USER_WIDTH-1:0] p_control_user;
    wire [USER_WIDTH-1:0] p_control_application;
    wire [30:0] p_control_stream;
    wire [31:0] p_control_generation;
    wire [MEMORY_ADDR_WIDTH-1:0] p_control_address;
    wire [MEMORY_ADDR_WIDTH-1:0] p_control_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] p_control_buffer_bytes;
    wire [31:0] p_control_message_limit;
    wire  p_control_protobuf;
    wire  p_control_unsupported_encoding;
    wire  p_control_maintenance;
    wire  p_control_result_valid;
    wire  p_control_result_ready;
    wire [7:0] p_control_status;
    wire [7:0] p_control_detail;
    wire [7:0] p_control_memory_status;
    wire [2:0] p_control_result_op;
    wire [MEMORY_ADDR_WIDTH-1:0] p_control_result_address;
    wire [MEMORY_ADDR_WIDTH-1:0] p_control_result_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] p_control_result_buffer_bytes;
    wire [USER_WIDTH-1:0] p_control_result_user;
    wire [USER_WIDTH-1:0] p_control_result_application;
    wire [30:0] p_control_result_stream;
    wire [31:0] p_control_result_generation;
    wire [31:0] p_control_result_message_limit;
    wire  p_control_result_protobuf;
    wire  p_control_result_unsupported_encoding;
    wire [255:0] p_control_result_state;
    wire  p_packet_start_valid;
    wire  p_packet_start_ready;
    wire [USER_WIDTH-1:0] p_packet_start_user;
    wire [31:0] p_packet_start_tag;
    wire  p_s_valid;
    wire  p_s_ready;
    wire [1:0] p_s_kind;
    wire [7:0] p_s_data;
    wire [30:0] p_s_stream;
    wire  p_prepare_valid;
    wire  p_prepare_ready;
    wire  p_prepared_valid;
    wire  p_prepared_ready;
    wire  p_prepared_failed;
    wire [7:0] p_prepared_status;
    wire  p_decision_valid;
    wire  p_decision_ready;
    wire  p_decision_commit;
    wire  p_packet_result_valid;
    wire  p_packet_result_ready;
    wire  p_packet_committed;
    wire [7:0] p_packet_status;
    wire [7:0] p_packet_detail;
    wire [7:0] p_packet_memory_status;
    wire [USER_WIDTH-1:0] p_packet_user;
    wire [31:0] p_packet_tag;
    wire  p_rpc_error_valid;
    wire  p_rpc_error_ready;
    wire [7:0] p_rpc_error_status;
    wire [7:0] p_rpc_error_detail;
    wire [7:0] p_rpc_error_memory_status;
    wire [USER_WIDTH-1:0] p_rpc_error_user;
    wire [USER_WIDTH-1:0] p_rpc_error_application;
    wire [30:0] p_rpc_error_stream;
    wire [31:0] p_rpc_error_generation;
    wire [31:0] p_rpc_error_packet_tag;
    wire  p_stream_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] p_stream_recovery_address;
    wire  p_queue_recovery_required;
    wire [7:0] p_queue_recovery_detail;
    wire [7:0] p_queue_recovery_memory_status;
    wire  p_retirement_pending;
    wire [31:0] p_queued_count;
    wire [31:0] p_pending_count;
    wire  p_idle;
    wire [12:0] p_mem_valid;
    wire [12:0] p_mem_ready;
    wire [12:0] p_mem_write;
    wire [13*MEMORY_ADDR_WIDTH-1:0] p_mem_addr;
    wire [51:0] p_mem_bytes;
    wire [935:0] p_mem_data;
    wire [12:0] p_mem_rsp_valid;
    wire [12:0] p_mem_rsp_ready;
    wire [935:0] p_mem_rsp_data;
    wire [103:0] p_mem_rsp_status;
    wire  p_admit_messages;
    wire  p_stream_cfg_valid;
    wire  p_stream_cfg_ready;
    wire  p_stream_cfg_result_valid;
    wire  p_stream_cfg_result_ready;
    wire [7:0] p_stream_cfg_status;
    wire  p_cfg_unlock;
    wire  p_cfg_schema_valid;
    wire  p_cfg_schema_ready;
    wire  p_cfg_quiescent;
    wire [3:0] p_cfg_schema_index;
    wire [255:0] p_cfg_schema_key;
    wire [5:0] p_cfg_schema_key_length;
    wire  p_cfg_schema_json_enable;
    wire [28:0] p_cfg_schema_field;
    wire  p_cfg_schema_proto_enable;
    wire  p_completion_valid;
    wire  p_completion_ready;
    wire [7:0] p_completion_status;
    wire [7:0] p_completion_detail;
    wire [7:0] p_completion_memory_status;
    wire [USER_WIDTH-1:0] p_completion_user;
    wire [USER_WIDTH-1:0] p_completion_application;
    wire [30:0] p_completion_stream;
    wire [31:0] p_completion_generation;
    wire [31:0] p_completion_ordinal;
    wire [31:0] p_completion_packet_tag;
    wire  p_payload_lease_active;
    wire [1:0] p_cfg_token_profile;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_class_base;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_hash_base;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_node_base;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_edge_base;
    wire [31:0] p_cfg_token_node_count;
    wire [31:0] p_cfg_token_edge_count;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_work_floor;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_scalar_base;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_merge_base;
    wire [MEMORY_ADDR_WIDTH-1:0] p_cfg_token_commit_base;
    wire [MEMORY_ADDR_WIDTH:0] p_cfg_token_scalar_bytes;
    wire [MEMORY_ADDR_WIDTH:0] p_cfg_token_merge_bytes;
    wire [MEMORY_ADDR_WIDTH:0] p_cfg_token_commit_bytes;
    wire [511:0] p_m_axis_tokens_tdata;
    wire [63:0] p_m_axis_tokens_tkeep;
    wire  p_m_axis_tokens_tvalid;
    wire  p_m_axis_tokens_tready;
    wire  p_m_axis_tokens_tlast;
    wire [USER_WIDTH-1:0] p_m_axis_tokens_tuser;
    wire [USER_WIDTH-1:0] p_dma_connection;
    wire [30:0] p_dma_stream;
    wire [31:0] p_dma_generation;
    wire [31:0] p_dma_ordinal;
    wire [31:0] p_dma_packet_tag;
    wire [31:0] p_completion_count;
    wire [7:0] p_completion_token_stage;
    wire [7:0] p_completion_token_detail;
    wire [7:0] p_completion_token_status;
    wire [127:0] p_s_return_tdata;
    wire [15:0] p_s_return_tkeep;
    wire  p_s_return_tvalid;
    wire  p_s_return_tready;
    wire  p_s_return_tlast;
    wire [USER_WIDTH-1:0] p_s_return_tuser;
    wire [127:0] p_m_return_tdata;
    wire [15:0] p_m_return_tkeep;
    wire  p_m_return_tvalid;
    wire  p_m_return_tready;
    wire  p_m_return_tlast;
    wire [USER_WIDTH-1:0] p_m_return_tuser;
    wire  r_admit_packets;
    wire [MEMORY_ADDR_WIDTH-1:0] r_cfg_context_base;
    wire [MEMORY_ADDR_WIDTH:0] r_cfg_context_bytes;
    wire  r_command_valid;
    wire  r_command_ready;
    wire [1:0] r_command_op;
    wire [USER_WIDTH-1:0] r_command_user;
    wire  r_command_server_role;
    wire  r_command_allow_push;
    wire [23:0] r_command_max_frame_bytes;
    wire [MEMORY_ADDR_WIDTH-1:0] r_command_buffer_base;
    wire [MEMORY_ADDR_WIDTH-1:0] r_command_table_base;
    wire [MEMORY_ADDR_WIDTH-1:0] r_command_scratch_base;
    wire [MEMORY_ADDR_WIDTH:0] r_command_buffer_bytes;
    wire [MEMORY_ADDR_WIDTH:0] r_command_table_bytes;
    wire [MEMORY_ADDR_WIDTH:0] r_command_scratch_bytes;
    wire [31:0] r_command_hpack_maximum;
    wire [31:0] r_command_hpack_allowed;
    wire [31:0] r_command_header_list_limit;
    wire [31:0] r_command_required_maximum;
    wire  r_command_required_update;
    wire [511:0] r_s_axis_rx_tdata;
    wire [63:0] r_s_axis_rx_tkeep;
    wire  r_s_axis_rx_tvalid;
    wire  r_s_axis_rx_tready;
    wire  r_s_axis_rx_tlast;
    wire [USER_WIDTH-1:0] r_s_axis_rx_tuser;
    wire  r_event_valid;
    wire  r_event_ready;
    wire [3:0] r_event_kind;
    wire [7:0] r_event_data;
    wire [31:0] r_event_arg0;
    wire [31:0] r_event_arg1;
    wire [23:0] r_event_length;
    wire [7:0] r_event_type;
    wire [7:0] r_event_flags;
    wire [30:0] r_event_stream;
    wire [USER_WIDTH-1:0] r_event_user;
    wire  r_header_valid;
    wire  r_header_ready;
    wire [MEMORY_ADDR_WIDTH-1:0] r_header_name_base;
    wire [MEMORY_ADDR_WIDTH-1:0] r_header_value_base;
    wire [31:0] r_header_name_bytes;
    wire [31:0] r_header_value_bytes;
    wire [1:0] r_header_representation;
    wire [USER_WIDTH-1:0] r_header_user;
    wire  r_block_start_valid;
    wire  r_block_start_ready;
    wire [30:0] r_block_start_stream;
    wire [30:0] r_block_start_promised_stream;
    wire [7:0] r_block_start_type;
    wire [7:0] r_block_start_flags;
    wire [USER_WIDTH-1:0] r_block_start_user;
    wire  r_block_valid;
    wire  r_block_ready;
    wire [30:0] r_block_stream;
    wire [30:0] r_block_promised_stream;
    wire [7:0] r_block_type;
    wire [7:0] r_block_flags;
    wire [31:0] r_block_headers;
    wire [31:0] r_block_list_bytes;
    wire [USER_WIDTH-1:0] r_block_user;
    wire  r_rsp_valid;
    wire  r_rsp_ready;
    wire  r_rsp_is_command;
    wire [1:0] r_rsp_command_op;
    wire [7:0] r_rsp_status;
    wire [7:0] r_rsp_detail;
    wire [7:0] r_rsp_memory_status;
    wire [31:0] r_rsp_http2_error;
    wire [USER_WIDTH-1:0] r_rsp_user;
    wire  r_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] r_recovery_address;
    wire [3:0] r_mem_valid;
    wire [3:0] r_mem_ready;
    wire [3:0] r_mem_write;
    wire [4*MEMORY_ADDR_WIDTH-1:0] r_mem_addr;
    wire [15:0] r_mem_bytes;
    wire [287:0] r_mem_data;
    wire [3:0] r_mem_rsp_valid;
    wire [3:0] r_mem_rsp_ready;
    wire [287:0] r_mem_rsp_data;
    wire [31:0] r_mem_rsp_status;
    wire  r_idle;
    wire  a_reset_valid;
    wire  a_reset_ready;
    wire [USER_WIDTH-1:0] a_reset_user;
    wire  a_maintenance_grant;
    wire  a_begin_valid;
    wire  a_begin_ready;
    wire [USER_WIDTH-1:0] a_begin_user;
    wire [30:0] a_begin_stream;
    wire  a_begin_end_stream;
    wire  a_admit_new;
    wire [MEMORY_ADDR_WIDTH-1:0] a_cfg_context_base;
    wire [MEMORY_ADDR_WIDTH-1:0] a_cfg_stream_base;
    wire [MEMORY_ADDR_WIDTH-1:0] a_cfg_payload_base;
    wire [MEMORY_ADDR_WIDTH-1:0] a_cfg_work_floor;
    wire [MEMORY_ADDR_WIDTH:0] a_cfg_context_bytes;
    wire [MEMORY_ADDR_WIDTH:0] a_cfg_stream_bytes;
    wire [MEMORY_ADDR_WIDTH:0] a_cfg_payload_bytes;
    wire [MEMORY_ADDR_WIDTH:0] a_cfg_payload_slot_bytes;
    wire [31:0] a_cfg_model_epoch;
    wire [31:0] a_cfg_schema_epoch;
    wire  a_context_valid;
    wire  a_context_ready;
    wire [USER_WIDTH-1:0] a_context_user;
    wire [30:0] a_context_stream;
    wire  a_context_trailers;
    wire  a_context_end_stream;
    wire [MEMORY_ADDR_WIDTH-1:0] a_context_scratch_base;
    wire [MEMORY_ADDR_WIDTH:0] a_context_scratch_bytes;
    wire  a_candidate_valid;
    wire  a_candidate_ready;
    wire [2:0] a_candidate_status;
    wire [9:0] a_candidate_http_status;
    wire [USER_WIDTH-1:0] a_candidate_user;
    wire [30:0] a_candidate_stream;
    wire  a_candidate_end_stream;
    wire  a_candidate_admissible;
    wire [15:0] a_candidate_application;
    wire [1:0] a_candidate_format;
    wire  a_candidate_identity_encoding;
    wire [31:0] a_candidate_message_limit;
    wire [31:0] a_candidate_model_epoch;
    wire [31:0] a_candidate_schema_epoch;
    wire [31:0] a_candidate_route_entry;
    wire  a_candidate_length_valid;
    wire [63:0] a_candidate_content_length;
    wire  a_candidate_timeout_valid;
    wire [26:0] a_candidate_timeout_value;
    wire [2:0] a_candidate_timeout_unit;
    wire  a_result_valid;
    wire  a_result_ready;
    wire  a_result_is_reset;
    wire  a_result_trailers;
    wire  a_result_end_stream;
    wire [3:0] a_result_status;
    wire [7:0] a_result_detail;
    wire [7:0] a_result_memory_status;
    wire [7:0] a_result_control_status;
    wire [7:0] a_result_cleanup_status;
    wire  a_result_connection_error;
    wire [31:0] a_result_http2_error;
    wire [9:0] a_result_http_status;
    wire [7:0] a_result_grpc_status;
    wire [USER_WIDTH-1:0] a_result_user;
    wire [30:0] a_result_stream;
    wire [15:0] a_result_application;
    wire [31:0] a_result_generation;
    wire [31:0] a_result_model_epoch;
    wire [31:0] a_result_schema_epoch;
    wire [MEMORY_ADDR_WIDTH-1:0] a_result_address;
    wire [MEMORY_ADDR_WIDTH-1:0] a_result_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] a_result_buffer_bytes;
    wire  a_result_protobuf;
    wire  a_result_unsupported_encoding;
    wire  a_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] a_recovery_address;
    wire [USER_WIDTH-1:0] a_recovery_user;
    wire  a_control_valid;
    wire  a_control_ready;
    wire [2:0] a_control_op;
    wire [USER_WIDTH-1:0] a_control_user;
    wire [15:0] a_control_application;
    wire [30:0] a_control_stream;
    wire [31:0] a_control_generation;
    wire [MEMORY_ADDR_WIDTH-1:0] a_control_address;
    wire [MEMORY_ADDR_WIDTH-1:0] a_control_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] a_control_buffer_bytes;
    wire [31:0] a_control_message_limit;
    wire  a_control_protobuf;
    wire  a_control_unsupported_encoding;
    wire  a_control_maintenance;
    wire  a_control_result_valid;
    wire  a_control_result_ready;
    wire [7:0] a_control_status;
    wire [7:0] a_control_memory_status;
    wire [MEMORY_ADDR_WIDTH-1:0] a_control_result_address;
    wire [MEMORY_ADDR_WIDTH-1:0] a_control_result_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] a_control_result_buffer_bytes;
    wire [15:0] a_control_result_application;
    wire [31:0] a_control_result_generation;
    wire [31:0] a_control_result_message_limit;
    wire  a_control_result_protobuf;
    wire  a_control_result_unsupported_encoding;
    wire [255:0] a_control_result_state;
    wire  a_mem_valid;
    wire  a_mem_ready;
    wire  a_mem_write;
    wire [MEMORY_ADDR_WIDTH-1:0] a_mem_addr;
    wire [3:0] a_mem_bytes;
    wire [71:0] a_mem_data;
    wire  a_mem_rsp_valid;
    wire  a_mem_rsp_ready;
    wire [71:0] a_mem_rsp_data;
    wire [7:0] a_mem_rsp_status;
    wire  a_idle;
    wire  h_start_valid;
    wire  h_start_ready;
    wire [USER_WIDTH-1:0] h_start_user;
    wire [30:0] h_start_stream;
    wire  h_start_trailers;
    wire  h_start_end_stream;
    wire [MEMORY_ADDR_WIDTH-1:0] h_cfg_scratch_base;
    wire [MEMORY_ADDR_WIDTH-1:0] h_cfg_route_base;
    wire [MEMORY_ADDR_WIDTH-1:0] h_cfg_route_strings_base;
    wire [MEMORY_ADDR_WIDTH:0] h_cfg_scratch_bytes;
    wire [MEMORY_ADDR_WIDTH:0] h_cfg_route_bytes;
    wire [MEMORY_ADDR_WIDTH:0] h_cfg_route_strings_bytes;
    wire [31:0] h_cfg_routes;
    wire  h_header_valid;
    wire  h_header_ready;
    wire [MEMORY_ADDR_WIDTH-1:0] h_header_name_base;
    wire [MEMORY_ADDR_WIDTH-1:0] h_header_value_base;
    wire [31:0] h_header_name_bytes;
    wire [31:0] h_header_value_bytes;
    wire [1:0] h_header_representation;
    wire [USER_WIDTH-1:0] h_header_user;
    wire  h_field_valid;
    wire  h_field_ready;
    wire [MEMORY_ADDR_WIDTH-1:0] h_field_name_base;
    wire [MEMORY_ADDR_WIDTH-1:0] h_field_value_base;
    wire [31:0] h_field_name_bytes;
    wire [31:0] h_field_value_bytes;
    wire [1:0] h_field_representation;
    wire [3:0] h_field_kind;
    wire [USER_WIDTH-1:0] h_field_user;
    wire  h_finish_valid;
    wire  h_finish_ready;
    wire  h_finish_failed;
    wire  h_result_valid;
    wire  h_result_ready;
    wire  h_result_admissible;
    wire [2:0] h_result_status;
    wire [7:0] h_result_detail;
    wire [7:0] h_result_memory_status;
    wire [9:0] h_result_http_status;
    wire [1:0] h_result_format;
    wire  h_result_identity_encoding;
    wire  h_result_content_length_valid;
    wire [63:0] h_result_content_length;
    wire  h_result_timeout_valid;
    wire [26:0] h_result_timeout_value;
    wire [2:0] h_result_timeout_unit;
    wire [31:0] h_result_headers;
    wire [USER_WIDTH-1:0] h_result_user;
    wire [30:0] h_result_stream;
    wire  h_result_trailers;
    wire  h_result_end_stream;
    wire [2:0] h_result_route_status;
    wire [7:0] h_result_route_detail;
    wire [7:0] h_result_route_memory_status;
    wire [15:0] h_result_application;
    wire [1:0] h_result_formats;
    wire [31:0] h_result_message_limit;
    wire [31:0] h_result_schema_epoch;
    wire [31:0] h_result_model_epoch;
    wire [31:0] h_result_route_entry;
    wire [1:0] h_mem_valid;
    wire [1:0] h_mem_ready;
    wire [1:0] h_mem_write;
    wire [2*MEMORY_ADDR_WIDTH-1:0] h_mem_addr;
    wire [7:0] h_mem_bytes;
    wire [143:0] h_mem_data;
    wire [1:0] h_mem_rsp_valid;
    wire [1:0] h_mem_rsp_ready;
    wire [143:0] h_mem_rsp_data;
    wire [15:0] h_mem_rsp_status;
    wire  h_idle;
    grpc_prefill_parser_partition #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)) prefill(
    .clk(clk),
    .rst(rst),
    .cfg_stream_base(p_cfg_stream_base),
    .cfg_stream_bytes(p_cfg_stream_bytes),
    .queue_cfg_valid(p_queue_cfg_valid),
    .queue_cfg_ready(p_queue_cfg_ready),
    .queue_cfg_clear(p_queue_cfg_clear),
    .maintenance_grant(p_maintenance_grant),
    .queue_cfg_base(p_queue_cfg_base),
    .queue_cfg_bytes(p_queue_cfg_bytes),
    .queue_cfg_result_valid(p_queue_cfg_result_valid),
    .queue_cfg_result_ready(p_queue_cfg_result_ready),
    .queue_cfg_status(p_queue_cfg_status),
    .control_valid(p_control_valid),
    .control_ready(p_control_ready),
    .control_op(p_control_op),
    .control_user(p_control_user),
    .control_application(p_control_application),
    .control_stream(p_control_stream),
    .control_generation(p_control_generation),
    .control_address(p_control_address),
    .control_buffer_base(p_control_buffer_base),
    .control_buffer_bytes(p_control_buffer_bytes),
    .control_message_limit(p_control_message_limit),
    .control_protobuf(p_control_protobuf),
    .control_unsupported_encoding(p_control_unsupported_encoding),
    .control_maintenance(p_control_maintenance),
    .control_result_valid(p_control_result_valid),
    .control_result_ready(p_control_result_ready),
    .control_status(p_control_status),
    .control_detail(p_control_detail),
    .control_memory_status(p_control_memory_status),
    .control_result_op(p_control_result_op),
    .control_result_address(p_control_result_address),
    .control_result_buffer_base(p_control_result_buffer_base),
    .control_result_buffer_bytes(p_control_result_buffer_bytes),
    .control_result_user(p_control_result_user),
    .control_result_application(p_control_result_application),
    .control_result_stream(p_control_result_stream),
    .control_result_generation(p_control_result_generation),
    .control_result_message_limit(p_control_result_message_limit),
    .control_result_protobuf(p_control_result_protobuf),
    .control_result_unsupported_encoding(p_control_result_unsupported_encoding),
    .control_result_state(p_control_result_state),
    .packet_start_valid(p_packet_start_valid),
    .packet_start_ready(p_packet_start_ready),
    .packet_start_user(p_packet_start_user),
    .packet_start_tag(p_packet_start_tag),
    .s_valid(p_s_valid),
    .s_ready(p_s_ready),
    .s_kind(p_s_kind),
    .s_data(p_s_data),
    .s_stream(p_s_stream),
    .prepare_valid(p_prepare_valid),
    .prepare_ready(p_prepare_ready),
    .prepared_valid(p_prepared_valid),
    .prepared_ready(p_prepared_ready),
    .prepared_failed(p_prepared_failed),
    .prepared_status(p_prepared_status),
    .decision_valid(p_decision_valid),
    .decision_ready(p_decision_ready),
    .decision_commit(p_decision_commit),
    .packet_result_valid(p_packet_result_valid),
    .packet_result_ready(p_packet_result_ready),
    .packet_committed(p_packet_committed),
    .packet_status(p_packet_status),
    .packet_detail(p_packet_detail),
    .packet_memory_status(p_packet_memory_status),
    .packet_user(p_packet_user),
    .packet_tag(p_packet_tag),
    .rpc_error_valid(p_rpc_error_valid),
    .rpc_error_ready(p_rpc_error_ready),
    .rpc_error_status(p_rpc_error_status),
    .rpc_error_detail(p_rpc_error_detail),
    .rpc_error_memory_status(p_rpc_error_memory_status),
    .rpc_error_user(p_rpc_error_user),
    .rpc_error_application(p_rpc_error_application),
    .rpc_error_stream(p_rpc_error_stream),
    .rpc_error_generation(p_rpc_error_generation),
    .rpc_error_packet_tag(p_rpc_error_packet_tag),
    .stream_recovery_required(p_stream_recovery_required),
    .stream_recovery_address(p_stream_recovery_address),
    .queue_recovery_required(p_queue_recovery_required),
    .queue_recovery_detail(p_queue_recovery_detail),
    .queue_recovery_memory_status(p_queue_recovery_memory_status),
    .retirement_pending(p_retirement_pending),
    .queued_count(p_queued_count),
    .pending_count(p_pending_count),
    .idle(p_idle),
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
    .admit_messages(p_admit_messages),
    .stream_cfg_valid(p_stream_cfg_valid),
    .stream_cfg_ready(p_stream_cfg_ready),
    .stream_cfg_result_valid(p_stream_cfg_result_valid),
    .stream_cfg_result_ready(p_stream_cfg_result_ready),
    .stream_cfg_status(p_stream_cfg_status),
    .cfg_unlock(p_cfg_unlock),
    .cfg_schema_valid(p_cfg_schema_valid),
    .cfg_schema_ready(p_cfg_schema_ready),
    .cfg_quiescent(p_cfg_quiescent),
    .cfg_schema_index(p_cfg_schema_index),
    .cfg_schema_key(p_cfg_schema_key),
    .cfg_schema_key_length(p_cfg_schema_key_length),
    .cfg_schema_json_enable(p_cfg_schema_json_enable),
    .cfg_schema_field(p_cfg_schema_field),
    .cfg_schema_proto_enable(p_cfg_schema_proto_enable),
    .completion_valid(p_completion_valid),
    .completion_ready(p_completion_ready),
    .completion_status(p_completion_status),
    .completion_detail(p_completion_detail),
    .completion_memory_status(p_completion_memory_status),
    .completion_user(p_completion_user),
    .completion_application(p_completion_application),
    .completion_stream(p_completion_stream),
    .completion_generation(p_completion_generation),
    .completion_ordinal(p_completion_ordinal),
    .completion_packet_tag(p_completion_packet_tag),
    .payload_lease_active(p_payload_lease_active),
    .cfg_token_profile(p_cfg_token_profile),
    .cfg_token_class_base(p_cfg_token_class_base),
    .cfg_token_hash_base(p_cfg_token_hash_base),
    .cfg_token_node_base(p_cfg_token_node_base),
    .cfg_token_edge_base(p_cfg_token_edge_base),
    .cfg_token_node_count(p_cfg_token_node_count),
    .cfg_token_edge_count(p_cfg_token_edge_count),
    .cfg_token_work_floor(p_cfg_token_work_floor),
    .cfg_token_scalar_base(p_cfg_token_scalar_base),
    .cfg_token_merge_base(p_cfg_token_merge_base),
    .cfg_token_commit_base(p_cfg_token_commit_base),
    .cfg_token_scalar_bytes(p_cfg_token_scalar_bytes),
    .cfg_token_merge_bytes(p_cfg_token_merge_bytes),
    .cfg_token_commit_bytes(p_cfg_token_commit_bytes),
    .m_axis_tokens_tdata(p_m_axis_tokens_tdata),
    .m_axis_tokens_tkeep(p_m_axis_tokens_tkeep),
    .m_axis_tokens_tvalid(p_m_axis_tokens_tvalid),
    .m_axis_tokens_tready(p_m_axis_tokens_tready),
    .m_axis_tokens_tlast(p_m_axis_tokens_tlast),
    .m_axis_tokens_tuser(p_m_axis_tokens_tuser),
    .dma_connection(p_dma_connection),
    .dma_stream(p_dma_stream),
    .dma_generation(p_dma_generation),
    .dma_ordinal(p_dma_ordinal),
    .dma_packet_tag(p_dma_packet_tag),
    .completion_count(p_completion_count),
    .completion_token_stage(p_completion_token_stage),
    .completion_token_detail(p_completion_token_detail),
    .completion_token_status(p_completion_token_status),
    .s_return_tdata(p_s_return_tdata),
    .s_return_tkeep(p_s_return_tkeep),
    .s_return_tvalid(p_s_return_tvalid),
    .s_return_tready(p_s_return_tready),
    .s_return_tlast(p_s_return_tlast),
    .s_return_tuser(p_s_return_tuser),
    .m_return_tdata(p_m_return_tdata),
    .m_return_tkeep(p_m_return_tkeep),
    .m_return_tvalid(p_m_return_tvalid),
    .m_return_tready(p_m_return_tready),
    .m_return_tlast(p_m_return_tlast),
    .m_return_tuser(p_m_return_tuser),
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
    .link_f_pack_idle(link_f_pack_idle)
);
    http2_hpack_ingress #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.BLOCK_START_PORT(1)) transport(
        .clk(clk),
        .rst(rst),
        .admit_packets(r_admit_packets),
        .cfg_context_base(r_cfg_context_base),
        .cfg_context_bytes(r_cfg_context_bytes),
        .command_valid(r_command_valid),
        .command_ready(r_command_ready),
        .command_op(r_command_op),
        .command_user(r_command_user),
        .command_server_role(r_command_server_role),
        .command_allow_push(r_command_allow_push),
        .command_max_frame_bytes(r_command_max_frame_bytes),
        .command_buffer_base(r_command_buffer_base),
        .command_table_base(r_command_table_base),
        .command_scratch_base(r_command_scratch_base),
        .command_buffer_bytes(r_command_buffer_bytes),
        .command_table_bytes(r_command_table_bytes),
        .command_scratch_bytes(r_command_scratch_bytes),
        .command_hpack_maximum(r_command_hpack_maximum),
        .command_hpack_allowed(r_command_hpack_allowed),
        .command_header_list_limit(r_command_header_list_limit),
        .command_required_maximum(r_command_required_maximum),
        .command_required_update(r_command_required_update),
        .s_axis_rx_tdata(r_s_axis_rx_tdata),
        .s_axis_rx_tkeep(r_s_axis_rx_tkeep),
        .s_axis_rx_tvalid(r_s_axis_rx_tvalid),
        .s_axis_rx_tready(r_s_axis_rx_tready),
        .s_axis_rx_tlast(r_s_axis_rx_tlast),
        .s_axis_rx_tuser(r_s_axis_rx_tuser),
        .event_valid(r_event_valid),
        .event_ready(r_event_ready),
        .event_kind(r_event_kind),
        .event_data(r_event_data),
        .event_arg0(r_event_arg0),
        .event_arg1(r_event_arg1),
        .event_length(r_event_length),
        .event_type(r_event_type),
        .event_flags(r_event_flags),
        .event_stream(r_event_stream),
        .event_user(r_event_user),
        .header_valid(r_header_valid),
        .header_ready(r_header_ready),
        .header_name_base(r_header_name_base),
        .header_value_base(r_header_value_base),
        .header_name_bytes(r_header_name_bytes),
        .header_value_bytes(r_header_value_bytes),
        .header_representation(r_header_representation),
        .header_user(r_header_user),
        .block_start_valid(r_block_start_valid),
        .block_start_ready(r_block_start_ready),
        .block_start_stream(r_block_start_stream),
        .block_start_promised_stream(r_block_start_promised_stream),
        .block_start_type(r_block_start_type),
        .block_start_flags(r_block_start_flags),
        .block_start_user(r_block_start_user),
        .block_valid(r_block_valid),
        .block_ready(r_block_ready),
        .block_stream(r_block_stream),
        .block_promised_stream(r_block_promised_stream),
        .block_type(r_block_type),
        .block_flags(r_block_flags),
        .block_headers(r_block_headers),
        .block_list_bytes(r_block_list_bytes),
        .block_user(r_block_user),
        .rsp_valid(r_rsp_valid),
        .rsp_ready(r_rsp_ready),
        .rsp_is_command(r_rsp_is_command),
        .rsp_command_op(r_rsp_command_op),
        .rsp_status(r_rsp_status),
        .rsp_detail(r_rsp_detail),
        .rsp_memory_status(r_rsp_memory_status),
        .rsp_http2_error(r_rsp_http2_error),
        .rsp_user(r_rsp_user),
        .recovery_required(r_recovery_required),
        .recovery_address(r_recovery_address),
        .mem_valid(r_mem_valid),
        .mem_ready(r_mem_ready),
        .mem_write(r_mem_write),
        .mem_addr(r_mem_addr),
        .mem_bytes(r_mem_bytes),
        .mem_data(r_mem_data),
        .mem_rsp_valid(r_mem_rsp_valid),
        .mem_rsp_ready(r_mem_rsp_ready),
        .mem_rsp_data(r_mem_rsp_data),
        .mem_rsp_status(r_mem_rsp_status),
        .idle(r_idle)
    );
    http2_rpc_admission #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) admission(
        .clk(clk),
        .rst(rst),
        .reset_valid(a_reset_valid),
        .reset_ready(a_reset_ready),
        .reset_user(a_reset_user),
        .maintenance_grant(a_maintenance_grant),
        .begin_valid(a_begin_valid),
        .begin_ready(a_begin_ready),
        .begin_user(a_begin_user),
        .begin_stream(a_begin_stream),
        .begin_end_stream(a_begin_end_stream),
        .admit_new(a_admit_new),
        .cfg_context_base(a_cfg_context_base),
        .cfg_stream_base(a_cfg_stream_base),
        .cfg_payload_base(a_cfg_payload_base),
        .cfg_work_floor(a_cfg_work_floor),
        .cfg_context_bytes(a_cfg_context_bytes),
        .cfg_stream_bytes(a_cfg_stream_bytes),
        .cfg_payload_bytes(a_cfg_payload_bytes),
        .cfg_payload_slot_bytes(a_cfg_payload_slot_bytes),
        .cfg_model_epoch(a_cfg_model_epoch),
        .cfg_schema_epoch(a_cfg_schema_epoch),
        .context_valid(a_context_valid),
        .context_ready(a_context_ready),
        .context_user(a_context_user),
        .context_stream(a_context_stream),
        .context_trailers(a_context_trailers),
        .context_end_stream(a_context_end_stream),
        .context_scratch_base(a_context_scratch_base),
        .context_scratch_bytes(a_context_scratch_bytes),
        .candidate_valid(a_candidate_valid),
        .candidate_ready(a_candidate_ready),
        .candidate_status(a_candidate_status),
        .candidate_http_status(a_candidate_http_status),
        .candidate_user(a_candidate_user),
        .candidate_stream(a_candidate_stream),
        .candidate_end_stream(a_candidate_end_stream),
        .candidate_admissible(a_candidate_admissible),
        .candidate_application(a_candidate_application),
        .candidate_format(a_candidate_format),
        .candidate_identity_encoding(a_candidate_identity_encoding),
        .candidate_message_limit(a_candidate_message_limit),
        .candidate_model_epoch(a_candidate_model_epoch),
        .candidate_schema_epoch(a_candidate_schema_epoch),
        .candidate_route_entry(a_candidate_route_entry),
        .candidate_length_valid(a_candidate_length_valid),
        .candidate_content_length(a_candidate_content_length),
        .candidate_timeout_valid(a_candidate_timeout_valid),
        .candidate_timeout_value(a_candidate_timeout_value),
        .candidate_timeout_unit(a_candidate_timeout_unit),
        .result_valid(a_result_valid),
        .result_ready(a_result_ready),
        .result_is_reset(a_result_is_reset),
        .result_trailers(a_result_trailers),
        .result_end_stream(a_result_end_stream),
        .result_status(a_result_status),
        .result_detail(a_result_detail),
        .result_memory_status(a_result_memory_status),
        .result_control_status(a_result_control_status),
        .result_cleanup_status(a_result_cleanup_status),
        .result_connection_error(a_result_connection_error),
        .result_http2_error(a_result_http2_error),
        .result_http_status(a_result_http_status),
        .result_grpc_status(a_result_grpc_status),
        .result_user(a_result_user),
        .result_stream(a_result_stream),
        .result_application(a_result_application),
        .result_generation(a_result_generation),
        .result_model_epoch(a_result_model_epoch),
        .result_schema_epoch(a_result_schema_epoch),
        .result_address(a_result_address),
        .result_buffer_base(a_result_buffer_base),
        .result_buffer_bytes(a_result_buffer_bytes),
        .result_protobuf(a_result_protobuf),
        .result_unsupported_encoding(a_result_unsupported_encoding),
        .recovery_required(a_recovery_required),
        .recovery_address(a_recovery_address),
        .recovery_user(a_recovery_user),
        .control_valid(a_control_valid),
        .control_ready(a_control_ready),
        .control_op(a_control_op),
        .control_user(a_control_user),
        .control_application(a_control_application),
        .control_stream(a_control_stream),
        .control_generation(a_control_generation),
        .control_address(a_control_address),
        .control_buffer_base(a_control_buffer_base),
        .control_buffer_bytes(a_control_buffer_bytes),
        .control_message_limit(a_control_message_limit),
        .control_protobuf(a_control_protobuf),
        .control_unsupported_encoding(a_control_unsupported_encoding),
        .control_maintenance(a_control_maintenance),
        .control_result_valid(a_control_result_valid),
        .control_result_ready(a_control_result_ready),
        .control_status(a_control_status),
        .control_memory_status(a_control_memory_status),
        .control_result_address(a_control_result_address),
        .control_result_buffer_base(a_control_result_buffer_base),
        .control_result_buffer_bytes(a_control_result_buffer_bytes),
        .control_result_application(a_control_result_application),
        .control_result_generation(a_control_result_generation),
        .control_result_message_limit(a_control_result_message_limit),
        .control_result_protobuf(a_control_result_protobuf),
        .control_result_unsupported_encoding(a_control_result_unsupported_encoding),
        .control_result_state(a_control_result_state),
        .mem_valid(a_mem_valid),
        .mem_ready(a_mem_ready),
        .mem_write(a_mem_write),
        .mem_addr(a_mem_addr),
        .mem_bytes(a_mem_bytes),
        .mem_data(a_mem_data),
        .mem_rsp_valid(a_mem_rsp_valid),
        .mem_rsp_ready(a_mem_rsp_ready),
        .mem_rsp_data(a_mem_rsp_data),
        .mem_rsp_status(a_mem_rsp_status),
        .idle(a_idle)
    );
    http2_request_router #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) router(
        .clk(clk),
        .rst(rst),
        .start_valid(h_start_valid),
        .start_ready(h_start_ready),
        .start_user(h_start_user),
        .start_stream(h_start_stream),
        .start_trailers(h_start_trailers),
        .start_end_stream(h_start_end_stream),
        .cfg_scratch_base(h_cfg_scratch_base),
        .cfg_route_base(h_cfg_route_base),
        .cfg_route_strings_base(h_cfg_route_strings_base),
        .cfg_scratch_bytes(h_cfg_scratch_bytes),
        .cfg_route_bytes(h_cfg_route_bytes),
        .cfg_route_strings_bytes(h_cfg_route_strings_bytes),
        .cfg_routes(h_cfg_routes),
        .header_valid(h_header_valid),
        .header_ready(h_header_ready),
        .header_name_base(h_header_name_base),
        .header_value_base(h_header_value_base),
        .header_name_bytes(h_header_name_bytes),
        .header_value_bytes(h_header_value_bytes),
        .header_representation(h_header_representation),
        .header_user(h_header_user),
        .field_valid(h_field_valid),
        .field_ready(h_field_ready),
        .field_name_base(h_field_name_base),
        .field_value_base(h_field_value_base),
        .field_name_bytes(h_field_name_bytes),
        .field_value_bytes(h_field_value_bytes),
        .field_representation(h_field_representation),
        .field_kind(h_field_kind),
        .field_user(h_field_user),
        .finish_valid(h_finish_valid),
        .finish_ready(h_finish_ready),
        .finish_failed(h_finish_failed),
        .result_valid(h_result_valid),
        .result_ready(h_result_ready),
        .result_admissible(h_result_admissible),
        .result_status(h_result_status),
        .result_detail(h_result_detail),
        .result_memory_status(h_result_memory_status),
        .result_http_status(h_result_http_status),
        .result_format(h_result_format),
        .result_identity_encoding(h_result_identity_encoding),
        .result_content_length_valid(h_result_content_length_valid),
        .result_content_length(h_result_content_length),
        .result_timeout_valid(h_result_timeout_valid),
        .result_timeout_value(h_result_timeout_value),
        .result_timeout_unit(h_result_timeout_unit),
        .result_headers(h_result_headers),
        .result_user(h_result_user),
        .result_stream(h_result_stream),
        .result_trailers(h_result_trailers),
        .result_end_stream(h_result_end_stream),
        .result_route_status(h_result_route_status),
        .result_route_detail(h_result_route_detail),
        .result_route_memory_status(h_result_route_memory_status),
        .result_application(h_result_application),
        .result_formats(h_result_formats),
        .result_message_limit(h_result_message_limit),
        .result_schema_epoch(h_result_schema_epoch),
        .result_model_epoch(h_result_model_epoch),
        .result_route_entry(h_result_route_entry),
        .mem_valid(h_mem_valid),
        .mem_ready(h_mem_ready),
        .mem_write(h_mem_write),
        .mem_addr(h_mem_addr),
        .mem_bytes(h_mem_bytes),
        .mem_data(h_mem_data),
        .mem_rsp_valid(h_mem_rsp_valid),
        .mem_rsp_ready(h_mem_rsp_ready),
        .mem_rsp_data(h_mem_rsp_data),
        .mem_rsp_status(h_mem_rsp_status),
        .idle(h_idle)
    );
    assign mem_valid[0*1+:13*1]=p_mem_valid;
    assign p_mem_ready=mem_ready[0*1+:13*1];
    assign mem_write[0*1+:13*1]=p_mem_write;
    assign mem_addr[0*MEMORY_ADDR_WIDTH+:13*MEMORY_ADDR_WIDTH]=p_mem_addr;
    assign mem_bytes[0*4+:13*4]=p_mem_bytes;
    assign mem_data[0*72+:13*72]=p_mem_data;
    assign p_mem_rsp_valid=mem_rsp_valid[0*1+:13*1];
    assign mem_rsp_ready[0*1+:13*1]=p_mem_rsp_ready;
    assign p_mem_rsp_data=mem_rsp_data[0*72+:13*72];
    assign p_mem_rsp_status=mem_rsp_status[0*8+:13*8];
    assign mem_valid[13*1+:4*1]=r_mem_valid;
    assign r_mem_ready=mem_ready[13*1+:4*1];
    assign mem_write[13*1+:4*1]=r_mem_write;
    assign mem_addr[13*MEMORY_ADDR_WIDTH+:4*MEMORY_ADDR_WIDTH]=r_mem_addr;
    assign mem_bytes[13*4+:4*4]=r_mem_bytes;
    assign mem_data[13*72+:4*72]=r_mem_data;
    assign r_mem_rsp_valid=mem_rsp_valid[13*1+:4*1];
    assign mem_rsp_ready[13*1+:4*1]=r_mem_rsp_ready;
    assign r_mem_rsp_data=mem_rsp_data[13*72+:4*72];
    assign r_mem_rsp_status=mem_rsp_status[13*8+:4*8];
    assign mem_valid[17*1+:2*1]=h_mem_valid;
    assign h_mem_ready=mem_ready[17*1+:2*1];
    assign mem_write[17*1+:2*1]=h_mem_write;
    assign mem_addr[17*MEMORY_ADDR_WIDTH+:2*MEMORY_ADDR_WIDTH]=h_mem_addr;
    assign mem_bytes[17*4+:2*4]=h_mem_bytes;
    assign mem_data[17*72+:2*72]=h_mem_data;
    assign h_mem_rsp_valid=mem_rsp_valid[17*1+:2*1];
    assign mem_rsp_ready[17*1+:2*1]=h_mem_rsp_ready;
    assign h_mem_rsp_data=mem_rsp_data[17*72+:2*72];
    assign h_mem_rsp_status=mem_rsp_status[17*8+:2*8];
    assign mem_valid[19*1+:1*1]=a_mem_valid;
    assign a_mem_ready=mem_ready[19*1+:1*1];
    assign mem_write[19*1+:1*1]=a_mem_write;
    assign mem_addr[19*MEMORY_ADDR_WIDTH+:1*MEMORY_ADDR_WIDTH]=a_mem_addr;
    assign mem_bytes[19*4+:1*4]=a_mem_bytes;
    assign mem_data[19*72+:1*72]=a_mem_data;
    assign a_mem_rsp_valid=mem_rsp_valid[19*1+:1*1];
    assign mem_rsp_ready[19*1+:1*1]=a_mem_rsp_ready;
    assign a_mem_rsp_data=mem_rsp_data[19*72+:1*72];
    assign a_mem_rsp_status=mem_rsp_status[19*8+:1*8];
    assign p_cfg_stream_base=cfg_stream_base;
    assign p_cfg_stream_bytes=cfg_stream_bytes;
    assign p_queue_cfg_valid=queue_cfg_valid;
    assign queue_cfg_ready=p_queue_cfg_ready;
    assign p_queue_cfg_clear=queue_cfg_clear;
    assign p_maintenance_grant=maintenance_grant;
    assign p_queue_cfg_base=queue_cfg_base;
    assign p_queue_cfg_bytes=queue_cfg_bytes;
    assign queue_cfg_result_valid=p_queue_cfg_result_valid;
    assign p_queue_cfg_result_ready=queue_cfg_result_ready;
    assign queue_cfg_status=p_queue_cfg_status;
    assign packet_committed=p_packet_committed;
    assign packet_status=p_packet_status;
    assign packet_detail=p_packet_detail;
    assign packet_memory_status=p_packet_memory_status;
    assign packet_user=p_packet_user;
    assign packet_tag=p_packet_tag;
    assign rpc_error_valid=p_rpc_error_valid;
    assign p_rpc_error_ready=rpc_error_ready;
    assign rpc_error_status=p_rpc_error_status;
    assign rpc_error_detail=p_rpc_error_detail;
    assign rpc_error_memory_status=p_rpc_error_memory_status;
    assign rpc_error_user=p_rpc_error_user;
    assign rpc_error_application=p_rpc_error_application;
    assign rpc_error_stream=p_rpc_error_stream;
    assign rpc_error_generation=p_rpc_error_generation;
    assign rpc_error_packet_tag=p_rpc_error_packet_tag;
    assign stream_recovery_required=p_stream_recovery_required;
    assign stream_recovery_address=p_stream_recovery_address;
    assign queue_recovery_required=p_queue_recovery_required;
    assign queue_recovery_detail=p_queue_recovery_detail;
    assign queue_recovery_memory_status=p_queue_recovery_memory_status;
    assign retirement_pending=p_retirement_pending;
    assign queued_count=p_queued_count;
    assign pending_count=p_pending_count;
    assign p_admit_messages=admit_messages;
    assign p_stream_cfg_valid=stream_cfg_valid;
    assign stream_cfg_ready=p_stream_cfg_ready;
    assign stream_cfg_result_valid=p_stream_cfg_result_valid;
    assign p_stream_cfg_result_ready=stream_cfg_result_ready;
    assign stream_cfg_status=p_stream_cfg_status;
    assign p_cfg_unlock=cfg_unlock;
    assign p_cfg_schema_valid=cfg_schema_valid;
    assign cfg_schema_ready=p_cfg_schema_ready;
    assign cfg_quiescent=p_cfg_quiescent;
    assign p_cfg_schema_index=cfg_schema_index;
    assign p_cfg_schema_key=cfg_schema_key;
    assign p_cfg_schema_key_length=cfg_schema_key_length;
    assign p_cfg_schema_json_enable=cfg_schema_json_enable;
    assign p_cfg_schema_field=cfg_schema_field;
    assign p_cfg_schema_proto_enable=cfg_schema_proto_enable;
    assign completion_valid=p_completion_valid;
    assign p_completion_ready=completion_ready;
    assign completion_status=p_completion_status;
    assign completion_detail=p_completion_detail;
    assign completion_memory_status=p_completion_memory_status;
    assign completion_user=p_completion_user;
    assign completion_application=p_completion_application;
    assign completion_stream=p_completion_stream;
    assign completion_generation=p_completion_generation;
    assign completion_ordinal=p_completion_ordinal;
    assign completion_packet_tag=p_completion_packet_tag;
    assign payload_lease_active=p_payload_lease_active;
    assign p_cfg_token_profile=cfg_token_profile;
    assign p_cfg_token_class_base=cfg_token_class_base;
    assign p_cfg_token_hash_base=cfg_token_hash_base;
    assign p_cfg_token_node_base=cfg_token_node_base;
    assign p_cfg_token_edge_base=cfg_token_edge_base;
    assign p_cfg_token_node_count=cfg_token_node_count;
    assign p_cfg_token_edge_count=cfg_token_edge_count;
    assign p_cfg_token_work_floor=cfg_token_work_floor;
    assign p_cfg_token_scalar_base=cfg_token_scalar_base;
    assign p_cfg_token_merge_base=cfg_token_merge_base;
    assign p_cfg_token_commit_base=cfg_token_commit_base;
    assign p_cfg_token_scalar_bytes=cfg_token_scalar_bytes;
    assign p_cfg_token_merge_bytes=cfg_token_merge_bytes;
    assign p_cfg_token_commit_bytes=cfg_token_commit_bytes;
    assign m_axis_tokens_tdata=p_m_axis_tokens_tdata;
    assign m_axis_tokens_tkeep=p_m_axis_tokens_tkeep;
    assign m_axis_tokens_tvalid=p_m_axis_tokens_tvalid;
    assign p_m_axis_tokens_tready=m_axis_tokens_tready;
    assign m_axis_tokens_tlast=p_m_axis_tokens_tlast;
    assign m_axis_tokens_tuser=p_m_axis_tokens_tuser;
    assign dma_connection=p_dma_connection;
    assign dma_stream=p_dma_stream;
    assign dma_generation=p_dma_generation;
    assign dma_ordinal=p_dma_ordinal;
    assign dma_packet_tag=p_dma_packet_tag;
    assign completion_count=p_completion_count;
    assign completion_token_stage=p_completion_token_stage;
    assign completion_token_detail=p_completion_token_detail;
    assign completion_token_status=p_completion_token_status;
    assign p_s_return_tdata=s_return_tdata;
    assign p_s_return_tkeep=s_return_tkeep;
    assign p_s_return_tvalid=s_return_tvalid;
    assign s_return_tready=p_s_return_tready;
    assign p_s_return_tlast=s_return_tlast;
    assign p_s_return_tuser=s_return_tuser;
    assign m_return_tdata=p_m_return_tdata;
    assign m_return_tkeep=p_m_return_tkeep;
    assign m_return_tvalid=p_m_return_tvalid;
    assign p_m_return_tready=m_return_tready;
    assign m_return_tlast=p_m_return_tlast;
    assign m_return_tuser=p_m_return_tuser;
    reg [MEMORY_ADDR_WIDTH-1:0] owned_cfg_context_base;
    reg [MEMORY_ADDR_WIDTH:0] owned_cfg_context_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] owned_cfg_payload_base;
    reg [MEMORY_ADDR_WIDTH:0] owned_cfg_payload_bytes;
    reg [MEMORY_ADDR_WIDTH:0] owned_cfg_payload_slot_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] owned_cfg_work_floor;
    reg [MEMORY_ADDR_WIDTH-1:0] owned_cfg_route_base;
    reg [MEMORY_ADDR_WIDTH:0] owned_cfg_route_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] owned_cfg_route_strings_base;
    reg [MEMORY_ADDR_WIDTH:0] owned_cfg_route_strings_bytes;
    reg [31:0] owned_cfg_routes;
    reg [31:0] owned_cfg_model_epoch;
    reg [31:0] owned_cfg_schema_epoch;
    assign r_cfg_context_base=owned_cfg_context_base;
    assign r_cfg_context_bytes=owned_cfg_context_bytes;
    reg [1:0] saved_command_op;
    assign r_command_op=state==CLOSE_SEND?2'd1:saved_command_op;
    reg [USER_WIDTH-1:0] saved_command_user;
    assign r_command_user=state==CLOSE_SEND?packet_owner:saved_command_user;
    reg  saved_command_server_role;
    assign r_command_server_role=saved_command_server_role;
    reg  saved_command_allow_push;
    assign r_command_allow_push=saved_command_allow_push;
    reg [23:0] saved_command_max_frame_bytes;
    assign r_command_max_frame_bytes=saved_command_max_frame_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] saved_command_buffer_base;
    assign r_command_buffer_base=saved_command_buffer_base;
    reg [MEMORY_ADDR_WIDTH-1:0] saved_command_table_base;
    assign r_command_table_base=saved_command_table_base;
    reg [MEMORY_ADDR_WIDTH-1:0] saved_command_scratch_base;
    assign r_command_scratch_base=saved_command_scratch_base;
    reg [MEMORY_ADDR_WIDTH:0] saved_command_buffer_bytes;
    assign r_command_buffer_bytes=saved_command_buffer_bytes;
    reg [MEMORY_ADDR_WIDTH:0] saved_command_table_bytes;
    assign r_command_table_bytes=saved_command_table_bytes;
    reg [MEMORY_ADDR_WIDTH:0] saved_command_scratch_bytes;
    assign r_command_scratch_bytes=saved_command_scratch_bytes;
    reg [31:0] saved_command_hpack_maximum;
    assign r_command_hpack_maximum=saved_command_hpack_maximum;
    reg [31:0] saved_command_hpack_allowed;
    assign r_command_hpack_allowed=saved_command_hpack_allowed;
    reg [31:0] saved_command_header_list_limit;
    assign r_command_header_list_limit=saved_command_header_list_limit;
    reg [31:0] saved_command_required_maximum;
    assign r_command_required_maximum=saved_command_required_maximum;
    reg  saved_command_required_update;
    assign r_command_required_update=saved_command_required_update;
    localparam IDLE=0,PACKET_START=1,RUN=2,PREPARE=3,PREPARED=4,DECISION=5,WAIT_PACKET=6,PACKET_RESULT=7,
        COMMAND_RESET=8,RESET_RESULT=9,COMMAND_SEND=10,COMMAND_WAIT=11,COMMAND_FAILED=12,CLOSE_SEND=13,CLOSE_WAIT=14;
    reg [3:0] state;
    reg first_valid,first_last,packet_fatal,commit_allowed,header_pending,router_active,finish_sent,eos_pending,saved_grant;
    reg [511:0] first_data;reg [63:0] first_keep;reg [USER_WIDTH-1:0] first_user,packet_owner;
    reg [31:0] packet_number;reg [30:0] eos_stream;
    reg [7:0] raw_status,raw_detail,raw_memory;reg [31:0] raw_h2;
    reg [1:0] control_owner;
    reg external_request_locked;
    reg [MEMORY_ADDR_WIDTH-1:0] owned_stream_base,pending_stream_base;
    reg [MEMORY_ADDR_WIDTH:0] owned_stream_bytes,pending_stream_bytes;
    wire external_control_allowed=state==IDLE&&(external_request_locked||!command_valid&&!s_axis_rx_tvalid)&&!a_control_valid;
    wire choose_admission=a_control_valid;
    wire choose_external=external_control_allowed&&control_valid;
    assign p_control_valid=control_owner==0&&(choose_admission||choose_external);
    assign a_control_ready=control_owner==0&&p_control_ready;
    assign control_ready=control_owner==0&&external_control_allowed&&p_control_ready;
    assign p_control_op=choose_admission?a_control_op:control_op;
    assign p_control_user=choose_admission?a_control_user:control_user;
    assign p_control_application=choose_admission?a_control_application:control_application;
    assign p_control_stream=choose_admission?a_control_stream:control_stream;
    assign p_control_generation=choose_admission?a_control_generation:control_generation;
    assign p_control_address=choose_admission?a_control_address:control_address;
    assign p_control_buffer_base=choose_admission?a_control_buffer_base:control_buffer_base;
    assign p_control_buffer_bytes=choose_admission?a_control_buffer_bytes:control_buffer_bytes;
    assign p_control_message_limit=choose_admission?a_control_message_limit:control_message_limit;
    assign p_control_protobuf=choose_admission?a_control_protobuf:control_protobuf;
    assign p_control_unsupported_encoding=choose_admission?a_control_unsupported_encoding:control_unsupported_encoding;
    assign p_control_maintenance=choose_admission?a_control_maintenance:control_maintenance;
    assign p_control_result_ready=control_owner==2?a_control_result_ready:control_owner==1&&control_result_ready;
    assign control_result_valid=control_owner==1&&p_control_result_valid;
    assign a_control_result_valid=control_owner==2&&p_control_result_valid;
    assign control_status=p_control_status;
    assign control_detail=p_control_detail;
    assign control_memory_status=p_control_memory_status;
    assign control_result_op=p_control_result_op;
    assign control_result_address=p_control_result_address;
    assign control_result_buffer_base=p_control_result_buffer_base;
    assign control_result_buffer_bytes=p_control_result_buffer_bytes;
    assign control_result_user=p_control_result_user;
    assign control_result_application=p_control_result_application;
    assign control_result_stream=p_control_result_stream;
    assign control_result_generation=p_control_result_generation;
    assign control_result_message_limit=p_control_result_message_limit;
    assign control_result_protobuf=p_control_result_protobuf;
    assign control_result_unsupported_encoding=p_control_result_unsupported_encoding;
    assign control_result_state=p_control_result_state;
    assign a_control_status=p_control_status;
    assign a_control_memory_status=p_control_memory_status;
    assign a_control_result_address=p_control_result_address;
    assign a_control_result_buffer_base=p_control_result_buffer_base;
    assign a_control_result_buffer_bytes=p_control_result_buffer_bytes;
    assign a_control_result_application=p_control_result_application;
    assign a_control_result_generation=p_control_result_generation;
    assign a_control_result_message_limit=p_control_result_message_limit;
    assign a_control_result_protobuf=p_control_result_protobuf;
    assign a_control_result_unsupported_encoding=p_control_result_unsupported_encoding;
    assign a_control_result_state=p_control_result_state;

    assign command_ready=!rst&&state==IDLE&&control_owner==0&&!control_valid&&p_idle&&r_idle&&a_idle;
    assign r_command_valid=state==COMMAND_SEND||state==CLOSE_SEND;
    assign rsp_valid=state==COMMAND_WAIT&&r_rsp_valid||state==COMMAND_FAILED;
    assign rsp_is_command=1'b1;assign rsp_command_op=saved_command_op;
    assign rsp_status=state==COMMAND_FAILED?8'd8:r_rsp_status;
    assign rsp_detail=state==COMMAND_FAILED?a_result_detail:r_rsp_detail;
    assign rsp_memory_status=state==COMMAND_FAILED?a_result_memory_status:r_rsp_memory_status;
    assign rsp_http2_error=state==COMMAND_FAILED?a_result_http2_error:r_rsp_http2_error;
    assign rsp_user=state==COMMAND_FAILED?a_result_user:r_rsp_user;
    assign r_rsp_ready=state==COMMAND_WAIT?rsp_ready:state==CLOSE_WAIT||state==RUN&&!header_pending&&r_rsp_valid;
    assign r_admit_packets=state==RUN;
    assign s_axis_rx_tready=!rst&&((state==IDLE&&admit_packets&&admit_messages&&!command_valid&&!control_valid&&control_owner==0&&a_idle&&r_idle)||
        state==RUN&&!first_valid&&r_s_axis_rx_tready);
    assign r_s_axis_rx_tvalid=state==RUN&&(first_valid||s_axis_rx_tvalid);
    assign r_s_axis_rx_tdata=first_valid?first_data:s_axis_rx_tdata;
    assign r_s_axis_rx_tkeep=first_valid?first_keep:s_axis_rx_tkeep;
    assign r_s_axis_rx_tlast=first_valid?first_last:s_axis_rx_tlast;
    assign r_s_axis_rx_tuser=first_valid?first_user:s_axis_rx_tuser;
    assign p_packet_start_valid=state==PACKET_START;
    assign p_packet_start_user=packet_owner;assign p_packet_start_tag=packet_number;
    assign p_prepare_valid=state==PREPARE;assign p_prepared_ready=state==PREPARED;
    assign p_decision_valid=state==DECISION;assign p_decision_commit=commit_allowed;
    assign packet_result_valid=state==PACKET_RESULT&&p_packet_result_valid;
    assign p_packet_result_ready=state==PACKET_RESULT&&packet_result_ready;
    assign transport_packet_status=raw_status;assign transport_packet_detail=raw_detail;
    assign transport_packet_memory_status=raw_memory;assign transport_packet_http2_error=raw_h2;
    assign transport_recovery_required=r_recovery_required;assign transport_recovery_address=r_recovery_address;

    assign a_reset_valid=state==COMMAND_RESET;assign a_reset_user=saved_command_user;assign a_maintenance_grant=saved_grant;
    assign a_begin_valid=state==RUN&&r_block_start_valid&&!header_pending;
    assign r_block_start_ready=state==RUN&&!header_pending&&a_begin_ready;
    assign a_begin_user=r_block_start_user;assign a_begin_stream=r_block_start_stream;assign a_begin_end_stream=r_block_start_flags[0];
    assign a_admit_new=admit_messages&&!packet_fatal;
    assign a_cfg_context_base=owned_cfg_context_base;assign a_cfg_context_bytes=owned_cfg_context_bytes;
    assign a_cfg_stream_base=owned_stream_base;assign a_cfg_stream_bytes=owned_stream_bytes;
    assign a_cfg_payload_base=owned_cfg_payload_base;assign a_cfg_payload_bytes=owned_cfg_payload_bytes;assign a_cfg_payload_slot_bytes=owned_cfg_payload_slot_bytes;
    assign a_cfg_work_floor=owned_cfg_work_floor;assign a_cfg_model_epoch=owned_cfg_model_epoch;assign a_cfg_schema_epoch=owned_cfg_schema_epoch;
    assign a_context_ready=h_start_ready;assign h_start_valid=a_context_valid;
    assign h_start_user=a_context_user;assign h_start_stream=a_context_stream;assign h_start_trailers=a_context_trailers;assign h_start_end_stream=a_context_end_stream;
    assign h_cfg_scratch_base=a_context_scratch_base;assign h_cfg_scratch_bytes=a_context_scratch_bytes;
    assign h_cfg_route_base=owned_cfg_route_base;assign h_cfg_route_bytes=owned_cfg_route_bytes;
    assign h_cfg_route_strings_base=owned_cfg_route_strings_base;assign h_cfg_route_strings_bytes=owned_cfg_route_strings_bytes;assign h_cfg_routes=owned_cfg_routes;
    assign h_header_valid=r_header_valid;assign r_header_ready=h_header_ready;
    assign h_header_name_base=r_header_name_base;assign h_header_value_base=r_header_value_base;
    assign h_header_name_bytes=r_header_name_bytes;assign h_header_value_bytes=r_header_value_bytes;
    assign h_header_representation=r_header_representation;assign h_header_user=r_header_user;
    // The router reads every leased field before ACK; application metadata
    // delivery can be attached here when the response controller is connected.
    assign h_field_ready=1'b1;
    assign h_finish_valid=r_block_valid||r_rsp_valid&&!r_rsp_is_command&&r_rsp_status!=0&&router_active&&!finish_sent;
    assign h_finish_failed=r_rsp_valid&&!r_rsp_is_command&&r_rsp_status!=0;
    assign r_block_ready=h_finish_ready;
    assign a_candidate_valid=h_result_valid;assign h_result_ready=a_candidate_ready;
    assign a_candidate_status=h_result_status;assign a_candidate_http_status=h_result_http_status;
    assign a_candidate_user=h_result_user;assign a_candidate_stream=h_result_stream;assign a_candidate_end_stream=h_result_end_stream;
    assign a_candidate_admissible=h_result_admissible;assign a_candidate_application=h_result_application;assign a_candidate_format=h_result_format;
    assign a_candidate_identity_encoding=h_result_identity_encoding;assign a_candidate_message_limit=h_result_message_limit;
    assign a_candidate_model_epoch=h_result_model_epoch;assign a_candidate_schema_epoch=h_result_schema_epoch;assign a_candidate_route_entry=h_result_route_entry;
    assign a_candidate_length_valid=h_result_content_length_valid;assign a_candidate_content_length=h_result_content_length;
    assign a_candidate_timeout_valid=h_result_timeout_valid;assign a_candidate_timeout_value=h_result_timeout_value;assign a_candidate_timeout_unit=h_result_timeout_unit;
    assign header_valid=a_result_valid&&!a_result_is_reset;
    assign a_result_ready=a_result_is_reset?(state==RESET_RESULT&&a_result_status==0||state==COMMAND_FAILED&&rsp_ready):header_ready;
    assign header_status=a_result_status;
    assign header_detail=a_result_detail;
    assign header_memory_status=a_result_memory_status;
    assign header_control_status=a_result_control_status;
    assign header_cleanup_status=a_result_cleanup_status;
    assign header_connection_error=a_result_connection_error;
    assign header_http2_error=a_result_http2_error;
    assign header_http_status=a_result_http_status;
    assign header_grpc_status=a_result_grpc_status;
    assign header_user=a_result_user;
    assign header_stream=a_result_stream;
    assign header_generation=a_result_generation;
    assign header_address=a_result_address;
    assign header_application=a_result_application;
    assign header_model_epoch=a_result_model_epoch;
    assign header_schema_epoch=a_result_schema_epoch;
    assign header_trailers=a_result_trailers;
    assign header_end_stream=a_result_end_stream;
    assign admission_recovery_required=a_recovery_required;assign admission_recovery_address=a_recovery_address;assign admission_recovery_user=a_recovery_user;
    wire data_byte=r_event_kind==2&&r_event_type==0;
    wire data_eos=r_event_kind==3&&r_event_type==0&&r_event_flags[0];
    wire control_event=r_event_kind>=4;
    assign control_event_valid=state==RUN&&!header_pending&&!r_block_start_valid&&r_event_valid&&control_event;
    assign control_event_kind=r_event_kind;assign control_event_arg0=r_event_arg0;assign control_event_arg1=r_event_arg1;
    assign control_event_stream=r_event_stream;assign control_event_user=r_event_user;
    assign p_s_valid=state==RUN&&!packet_fatal&&(eos_pending||!header_pending&&!r_block_start_valid&&r_event_valid&&(data_byte||data_eos));
    assign p_s_kind=eos_pending||data_eos?2'd1:2'd0;
    assign p_s_data=r_event_data;assign p_s_stream=eos_pending?eos_stream:r_event_stream;
    assign r_event_ready=state==RUN&&!header_pending&&!r_block_start_valid&&!eos_pending&&
        (control_event?control_event_ready:packet_fatal||!(data_byte||data_eos)||p_s_ready);
    assign idle=state==IDLE&&control_owner==0&&a_idle&&h_idle&&r_idle&&p_idle&&!header_pending;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;first_valid<=0;first_last<=0;first_data<=0;first_keep<=0;first_user<=0;packet_owner<=0;packet_number<=0;
            packet_fatal<=0;commit_allowed<=0;header_pending<=0;router_active<=0;finish_sent<=0;eos_pending<=0;eos_stream<=0;saved_grant<=0;
            raw_status<=0;raw_detail<=0;raw_memory<=0;raw_h2<=0;control_owner<=0;external_request_locked<=0;
            owned_stream_base<=0;owned_stream_bytes<=0;pending_stream_base<=0;pending_stream_bytes<=0;
        end else begin
            if(stream_cfg_valid&&stream_cfg_ready)begin pending_stream_base<=cfg_stream_base;pending_stream_bytes<=cfg_stream_bytes;end
            if(stream_cfg_result_valid&&stream_cfg_status==0)begin owned_stream_base<=pending_stream_base;owned_stream_bytes<=pending_stream_bytes;end
            if(p_control_valid&&!p_control_ready&&choose_external)external_request_locked<=1;
            if(p_control_valid&&p_control_ready)begin control_owner<=choose_admission?2:1;external_request_locked<=0;end
            if(p_control_result_valid&&p_control_result_ready)control_owner<=0;
            if(r_block_start_valid&&r_block_start_ready)begin header_pending<=1;finish_sent<=0;end
            if(a_context_valid&&a_context_ready)router_active<=1;
            if(h_finish_valid&&h_finish_ready)finish_sent<=1;
            if(header_valid&&header_ready)begin
                router_active<=0;
                if(header_status!=0)begin packet_fatal<=1;header_pending<=0;end
                else if(header_end_stream)begin eos_pending<=1;eos_stream<=header_stream;end
                else header_pending<=0;
            end
            if(eos_pending&&p_s_valid&&p_s_ready)begin eos_pending<=0;header_pending<=0;end
            if(rpc_error_valid&&rpc_error_ready)packet_fatal<=1;
            if(command_valid&&command_ready||s_axis_rx_tvalid&&s_axis_rx_tready&&state==IDLE)begin
                owned_cfg_context_base<=cfg_context_base;
                owned_cfg_context_bytes<=cfg_context_bytes;
                owned_cfg_payload_base<=cfg_payload_base;
                owned_cfg_payload_bytes<=cfg_payload_bytes;
                owned_cfg_payload_slot_bytes<=cfg_payload_slot_bytes;
                owned_cfg_work_floor<=cfg_work_floor;
                owned_cfg_route_base<=cfg_route_base;
                owned_cfg_route_bytes<=cfg_route_bytes;
                owned_cfg_route_strings_base<=cfg_route_strings_base;
                owned_cfg_route_strings_bytes<=cfg_route_strings_bytes;
                owned_cfg_routes<=cfg_routes;
                owned_cfg_model_epoch<=cfg_model_epoch;
                owned_cfg_schema_epoch<=cfg_schema_epoch;
            end
            case(state)
                IDLE:if(command_valid&&command_ready)begin
                                    saved_command_op<=command_op;
                saved_command_user<=command_user;
                saved_command_server_role<=command_server_role;
                saved_command_allow_push<=command_allow_push;
                saved_command_max_frame_bytes<=command_max_frame_bytes;
                saved_command_buffer_base<=command_buffer_base;
                saved_command_table_base<=command_table_base;
                saved_command_scratch_base<=command_scratch_base;
                saved_command_buffer_bytes<=command_buffer_bytes;
                saved_command_table_bytes<=command_table_bytes;
                saved_command_scratch_bytes<=command_scratch_bytes;
                saved_command_hpack_maximum<=command_hpack_maximum;
                saved_command_hpack_allowed<=command_hpack_allowed;
                saved_command_header_list_limit<=command_header_list_limit;
                saved_command_required_maximum<=command_required_maximum;
                saved_command_required_update<=command_required_update;
                    saved_grant<=maintenance_grant;state<=command_op==0?COMMAND_RESET:COMMAND_SEND;
                end else if(s_axis_rx_tvalid&&s_axis_rx_tready)begin
                    first_data<=s_axis_rx_tdata;first_keep<=s_axis_rx_tkeep;first_last<=s_axis_rx_tlast;first_user<=s_axis_rx_tuser;first_valid<=1;
                    packet_owner<=s_axis_rx_tuser;packet_number<=s_axis_rx_tag;packet_fatal<=0;raw_status<=0;raw_detail<=0;raw_memory<=0;raw_h2<=0;state<=PACKET_START;
                end
                COMMAND_RESET:if(a_reset_ready)state<=RESET_RESULT;
                RESET_RESULT:if(a_result_valid)state<=a_result_status==0?COMMAND_SEND:COMMAND_FAILED;
                COMMAND_SEND:if(r_command_ready)state<=COMMAND_WAIT;
                COMMAND_WAIT:if(r_rsp_valid&&rsp_ready)state<=IDLE;
                COMMAND_FAILED:if(rsp_ready)state<=IDLE;
                PACKET_START:if(p_packet_start_ready)state<=RUN;
                RUN:begin
                    if(first_valid&&r_s_axis_rx_tready)first_valid<=0;
                    if(r_rsp_valid&&r_rsp_ready)begin
                        raw_status<=r_rsp_status;raw_detail<=r_rsp_detail;raw_memory<=r_rsp_memory_status;raw_h2<=r_rsp_http2_error;
                        if(r_rsp_status!=0)packet_fatal<=1;state<=PREPARE;
                    end
                end
                PREPARE:if(p_prepare_ready)state<=PREPARED;
                PREPARED:if(p_prepared_valid)begin commit_allowed<=!packet_fatal&&!p_prepared_failed;state<=DECISION;end
                DECISION:if(p_decision_ready)state<=WAIT_PACKET;
                WAIT_PACKET:if(p_packet_result_valid)state<=p_packet_committed?PACKET_RESULT:CLOSE_SEND;
                CLOSE_SEND:if(r_command_ready)state<=CLOSE_WAIT;
                CLOSE_WAIT:if(r_rsp_valid)state<=PACKET_RESULT;
                PACKET_RESULT:if(p_packet_result_valid&&packet_result_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end

endmodule
`default_nettype wire
