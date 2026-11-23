`timescale 1ns/1ps
`default_nettype none
module cocotb_windowed_admission_top;
localparam integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
reg  clk=0;
reg  rst=0;
reg  reset_valid=0;
wire  reset_ready;
reg [USER_WIDTH-1:0] reset_user=0;
reg  maintenance_grant=0;
reg  begin_valid=0;
wire  begin_ready;
reg [USER_WIDTH-1:0] begin_user=0;
reg [30:0] begin_stream=0;
reg  begin_end_stream=0;
reg  admit_new=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base=0;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_payload_slot_bytes=0;
reg [31:0] cfg_model_epoch=0;
reg [31:0] cfg_schema_epoch=0;
wire  context_valid;
reg  context_ready=0;
wire [USER_WIDTH-1:0] context_user;
wire [30:0] context_stream;
wire  context_trailers;
wire  context_end_stream;
wire [MEMORY_ADDR_WIDTH-1:0] context_scratch_base;
wire [MEMORY_ADDR_WIDTH:0] context_scratch_bytes;
reg  candidate_valid=0;
wire  candidate_ready;
reg [2:0] candidate_status=0;
reg [9:0] candidate_http_status=0;
reg [USER_WIDTH-1:0] candidate_user=0;
reg [30:0] candidate_stream=0;
reg  candidate_end_stream=0;
reg  candidate_admissible=0;
reg [15:0] candidate_application=0;
reg [1:0] candidate_format=0;
reg  candidate_identity_encoding=0;
reg [31:0] candidate_message_limit=0;
reg [31:0] candidate_model_epoch=0;
reg [31:0] candidate_schema_epoch=0;
reg [31:0] candidate_route_entry=0;
reg  candidate_length_valid=0;
reg [63:0] candidate_content_length=0;
reg  candidate_timeout_valid=0;
reg [26:0] candidate_timeout_value=0;
reg [2:0] candidate_timeout_unit=0;
wire  result_valid;
reg  result_ready=0;
wire  result_is_reset;
wire  result_trailers;
wire  result_end_stream;
wire [3:0] result_status;
wire [7:0] result_detail;
wire [7:0] result_memory_status;
wire [7:0] result_control_status;
wire [7:0] result_cleanup_status;
wire  result_connection_error;
wire [31:0] result_http2_error;
wire [9:0] result_http_status;
wire [7:0] result_grpc_status;
wire [USER_WIDTH-1:0] result_user;
wire [30:0] result_stream;
wire [15:0] result_application;
wire [31:0] result_generation;
wire [31:0] result_model_epoch;
wire [31:0] result_schema_epoch;
wire [MEMORY_ADDR_WIDTH-1:0] result_address;
wire [MEMORY_ADDR_WIDTH-1:0] result_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] result_buffer_bytes;
wire  result_protobuf;
wire  result_unsupported_encoding;
wire  recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] recovery_address;
wire [USER_WIDTH-1:0] recovery_user;
wire  control_valid;
wire  control_ready;
wire [2:0] control_op;
wire [USER_WIDTH-1:0] control_user;
wire [15:0] control_application;
wire [30:0] control_stream;
wire [31:0] control_generation;
wire [MEMORY_ADDR_WIDTH-1:0] control_address;
wire [MEMORY_ADDR_WIDTH-1:0] control_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] control_buffer_bytes;
wire [31:0] control_message_limit;
wire  control_protobuf;
wire  control_unsupported_encoding;
wire  control_maintenance;
wire  control_result_valid;
wire  control_result_ready;
wire [7:0] control_status;
wire [7:0] control_memory_status;
wire [MEMORY_ADDR_WIDTH-1:0] control_result_address;
wire [MEMORY_ADDR_WIDTH-1:0] control_result_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes;
wire [15:0] control_result_application;
wire [31:0] control_result_generation;
wire [31:0] control_result_message_limit;
wire  control_result_protobuf;
wire  control_result_unsupported_encoding;
wire [255:0] control_result_state;
wire  idle;
reg [MEMORY_ADDR_WIDTH-1:0] cfg_window_base=0;
reg [MEMORY_ADDR_WIDTH:0] cfg_window_bytes=0;
wire [MEMORY_ADDR_WIDTH-1:0] control_pool_base;
wire [MEMORY_ADDR_WIDTH:0] control_pool_bytes;
wire  init_valid;
wire  init_ready;
wire [USER_WIDTH-1:0] init_user;
wire [30:0] init_stream;
wire [31:0] init_generation;
wire [MEMORY_ADDR_WIDTH-1:0] init_record_address;
wire  init_result_valid;
wire  init_result_ready;
wire [7:0] init_status;
wire [7:0] init_memory_status;
wire  init_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] init_recovery_address;
wire [7:0] result_window_status;
wire [MEMORY_ADDR_WIDTH-1:0] init_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] init_cfg_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] init_cfg_window_base;
wire [MEMORY_ADDR_WIDTH-1:0] init_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] init_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] init_cfg_stream_bytes;
wire [MEMORY_ADDR_WIDTH:0] init_cfg_window_bytes;
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
wire [3*1-1:0] mem_valid;
wire [2*1-1:0] s_mem_valid;
assign mem_valid={s_mem_valid,a_mem_valid};
reg [3*1-1:0] mem_ready=0;
wire [2*1-1:0] s_mem_ready;
assign a_mem_ready=mem_ready[0+:1];
assign s_mem_ready=mem_ready[1+:2*1];
wire [3*1-1:0] mem_write;
wire [2*1-1:0] s_mem_write;
assign mem_write={s_mem_write,a_mem_write};
wire [3*MEMORY_ADDR_WIDTH-1:0] mem_addr;
wire [2*MEMORY_ADDR_WIDTH-1:0] s_mem_addr;
assign mem_addr={s_mem_addr,a_mem_addr};
wire [3*4-1:0] mem_bytes;
wire [2*4-1:0] s_mem_bytes;
assign mem_bytes={s_mem_bytes,a_mem_bytes};
wire [3*72-1:0] mem_data;
wire [2*72-1:0] s_mem_data;
assign mem_data={s_mem_data,a_mem_data};
reg [3*1-1:0] mem_rsp_valid=0;
wire [2*1-1:0] s_mem_rsp_valid;
assign a_mem_rsp_valid=mem_rsp_valid[0+:1];
assign s_mem_rsp_valid=mem_rsp_valid[1+:2*1];
wire [3*1-1:0] mem_rsp_ready;
wire [2*1-1:0] s_mem_rsp_ready;
assign mem_rsp_ready={s_mem_rsp_ready,a_mem_rsp_ready};
reg [3*72-1:0] mem_rsp_data=0;
wire [2*72-1:0] s_mem_rsp_data;
assign a_mem_rsp_data=mem_rsp_data[0+:72];
assign s_mem_rsp_data=mem_rsp_data[72+:2*72];
reg [3*8-1:0] mem_rsp_status=0;
wire [2*8-1:0] s_mem_rsp_status;
assign a_mem_rsp_status=mem_rsp_status[0+:8];
assign s_mem_rsp_status=mem_rsp_status[8+:2*8];
reg  host_req_valid=0;
wire  host_req_ready;
reg [2:0] host_req_op=0;
reg [MEMORY_ADDR_WIDTH-1:0] host_cfg_pool_base=0;
reg [MEMORY_ADDR_WIDTH:0] host_cfg_pool_bytes=0;
reg [USER_WIDTH-1:0] host_req_user=0;
reg [USER_WIDTH-1:0] host_req_application=0;
reg [30:0] host_req_stream=0;
reg [31:0] host_req_generation=0;
reg [MEMORY_ADDR_WIDTH-1:0] host_req_address=0;
reg [MEMORY_ADDR_WIDTH-1:0] host_req_buffer_base=0;
reg [MEMORY_ADDR_WIDTH:0] host_req_buffer_bytes=0;
reg [31:0] host_req_message_limit=0;
reg  host_req_protobuf=0;
reg  host_req_unsupported_encoding=0;
reg  host_req_maintenance=0;
reg [255:0] host_req_state=0;
wire  host_rsp_valid;
reg  host_rsp_ready=0;
wire [7:0] host_rsp_status;
wire [7:0] s_rsp_status;
assign host_rsp_status=s_rsp_status;
wire [7:0] host_rsp_detail;
wire [7:0] s_rsp_detail;
assign host_rsp_detail=s_rsp_detail;
wire [7:0] host_rsp_memory_status;
wire [7:0] s_rsp_memory_status;
assign host_rsp_memory_status=s_rsp_memory_status;
wire [2:0] host_rsp_op;
wire [2:0] s_rsp_op;
assign host_rsp_op=s_rsp_op;
wire [MEMORY_ADDR_WIDTH-1:0] host_rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] s_rsp_address;
assign host_rsp_address=s_rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] host_rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH-1:0] s_rsp_buffer_base;
assign host_rsp_buffer_base=s_rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] host_rsp_buffer_bytes;
wire [MEMORY_ADDR_WIDTH:0] s_rsp_buffer_bytes;
assign host_rsp_buffer_bytes=s_rsp_buffer_bytes;
wire [USER_WIDTH-1:0] host_rsp_user;
wire [USER_WIDTH-1:0] s_rsp_user;
assign host_rsp_user=s_rsp_user;
wire [USER_WIDTH-1:0] host_rsp_application;
wire [USER_WIDTH-1:0] s_rsp_application;
assign host_rsp_application=s_rsp_application;
wire [30:0] host_rsp_stream;
wire [30:0] s_rsp_stream;
assign host_rsp_stream=s_rsp_stream;
wire [31:0] host_rsp_generation;
wire [31:0] s_rsp_generation;
assign host_rsp_generation=s_rsp_generation;
wire [31:0] host_rsp_message_limit;
wire [31:0] s_rsp_message_limit;
assign host_rsp_message_limit=s_rsp_message_limit;
wire  host_rsp_protobuf;
wire  s_rsp_protobuf;
assign host_rsp_protobuf=s_rsp_protobuf;
wire  host_rsp_unsupported_encoding;
wire  s_rsp_unsupported_encoding;
assign host_rsp_unsupported_encoding=s_rsp_unsupported_encoding;
wire [255:0] host_rsp_state;
wire [255:0] s_rsp_state;
assign host_rsp_state=s_rsp_state;
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
wire [3:0] s_window_rsp_op;
assign window_rsp_op=s_window_rsp_op;
wire [USER_WIDTH-1:0] window_rsp_user;
wire [USER_WIDTH-1:0] s_window_rsp_user;
assign window_rsp_user=s_window_rsp_user;
wire [30:0] window_rsp_stream;
wire [30:0] s_window_rsp_stream;
assign window_rsp_stream=s_window_rsp_stream;
wire [7:0] window_rsp_status;
wire [7:0] s_window_rsp_status;
assign window_rsp_status=s_window_rsp_status;
wire [7:0] window_rsp_detail;
wire [7:0] s_window_rsp_detail;
assign window_rsp_detail=s_window_rsp_detail;
wire [7:0] window_rsp_memory_status;
wire [7:0] s_window_rsp_memory_status;
assign window_rsp_memory_status=s_window_rsp_memory_status;
wire  window_rsp_connection_error;
wire  s_window_rsp_connection_error;
assign window_rsp_connection_error=s_window_rsp_connection_error;
wire [31:0] window_rsp_http2_error;
wire [31:0] s_window_rsp_http2_error;
assign window_rsp_http2_error=s_window_rsp_http2_error;
wire [23:0] window_rsp_grant_bytes;
wire [23:0] s_window_rsp_grant_bytes;
assign window_rsp_grant_bytes=s_window_rsp_grant_bytes;
wire [31:0] window_rsp_connection_window;
wire [31:0] s_window_rsp_connection_window;
assign window_rsp_connection_window=s_window_rsp_connection_window;
wire [31:0] window_rsp_initial_window;
wire [31:0] s_window_rsp_initial_window;
assign window_rsp_initial_window=s_window_rsp_initial_window;
wire [31:0] window_rsp_stream_window;
wire [31:0] s_window_rsp_stream_window;
assign window_rsp_stream_window=s_window_rsp_stream_window;
wire [23:0] window_rsp_max_frame_bytes;
wire [23:0] s_window_rsp_max_frame_bytes;
assign window_rsp_max_frame_bytes=s_window_rsp_max_frame_bytes;
wire [31:0] window_rsp_affected_streams;
wire [31:0] s_window_rsp_affected_streams;
assign window_rsp_affected_streams=s_window_rsp_affected_streams;
wire  window_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] window_recovery_address;
wire  window_busy;
wire [7:0] window_lock_status;
reg [1:0] dir_owner=0,win_owner=0;
wire s_req_ready,s_rsp_valid,s_window_req_ready,s_window_rsp_valid;
wire directory_recovery_required;wire [22:0] directory_recovery_address;
wire directory_pool_lock_active,service_idle;
assign control_ready=dir_owner==0&&s_req_ready;
assign host_req_ready=dir_owner==0&&!control_valid&&idle&&s_req_ready;
assign control_result_valid=dir_owner==1&&s_rsp_valid;
assign host_rsp_valid=dir_owner==2&&s_rsp_valid;
assign init_ready=win_owner==0&&s_window_req_ready;
assign window_req_ready=win_owner==0&&!init_valid&&s_window_req_ready;
assign init_result_valid=win_owner==1&&s_window_rsp_valid;
assign window_rsp_valid=win_owner==2&&s_window_rsp_valid;
assign init_status=s_window_rsp_status;assign init_memory_status=s_window_rsp_memory_status;
assign init_recovery_required=window_recovery_required;assign init_recovery_address=window_recovery_address;
assign control_status=s_rsp_status;
assign control_memory_status=s_rsp_memory_status;
assign control_result_address=s_rsp_address;
assign control_result_buffer_base=s_rsp_buffer_base;
assign control_result_buffer_bytes=s_rsp_buffer_bytes;
assign control_result_application=s_rsp_application;
assign control_result_generation=s_rsp_generation;
assign control_result_message_limit=s_rsp_message_limit;
assign control_result_protobuf=s_rsp_protobuf;
assign control_result_unsupported_encoding=s_rsp_unsupported_encoding;
assign control_result_state=s_rsp_state;
http2_windowed_rpc_admission #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) admission(
    .clk(clk),
    .rst(rst),
    .reset_valid(reset_valid),
    .reset_ready(reset_ready),
    .reset_user(reset_user),
    .maintenance_grant(maintenance_grant),
    .begin_valid(begin_valid),
    .begin_ready(begin_ready),
    .begin_user(begin_user),
    .begin_stream(begin_stream),
    .begin_end_stream(begin_end_stream),
    .admit_new(admit_new),
    .cfg_context_base(cfg_context_base),
    .cfg_stream_base(cfg_stream_base),
    .cfg_payload_base(cfg_payload_base),
    .cfg_work_floor(cfg_work_floor),
    .cfg_context_bytes(cfg_context_bytes),
    .cfg_stream_bytes(cfg_stream_bytes),
    .cfg_payload_bytes(cfg_payload_bytes),
    .cfg_payload_slot_bytes(cfg_payload_slot_bytes),
    .cfg_model_epoch(cfg_model_epoch),
    .cfg_schema_epoch(cfg_schema_epoch),
    .context_valid(context_valid),
    .context_ready(context_ready),
    .context_user(context_user),
    .context_stream(context_stream),
    .context_trailers(context_trailers),
    .context_end_stream(context_end_stream),
    .context_scratch_base(context_scratch_base),
    .context_scratch_bytes(context_scratch_bytes),
    .candidate_valid(candidate_valid),
    .candidate_ready(candidate_ready),
    .candidate_status(candidate_status),
    .candidate_http_status(candidate_http_status),
    .candidate_user(candidate_user),
    .candidate_stream(candidate_stream),
    .candidate_end_stream(candidate_end_stream),
    .candidate_admissible(candidate_admissible),
    .candidate_application(candidate_application),
    .candidate_format(candidate_format),
    .candidate_identity_encoding(candidate_identity_encoding),
    .candidate_message_limit(candidate_message_limit),
    .candidate_model_epoch(candidate_model_epoch),
    .candidate_schema_epoch(candidate_schema_epoch),
    .candidate_route_entry(candidate_route_entry),
    .candidate_length_valid(candidate_length_valid),
    .candidate_content_length(candidate_content_length),
    .candidate_timeout_valid(candidate_timeout_valid),
    .candidate_timeout_value(candidate_timeout_value),
    .candidate_timeout_unit(candidate_timeout_unit),
    .result_valid(result_valid),
    .result_ready(result_ready),
    .result_is_reset(result_is_reset),
    .result_trailers(result_trailers),
    .result_end_stream(result_end_stream),
    .result_status(result_status),
    .result_detail(result_detail),
    .result_memory_status(result_memory_status),
    .result_control_status(result_control_status),
    .result_cleanup_status(result_cleanup_status),
    .result_connection_error(result_connection_error),
    .result_http2_error(result_http2_error),
    .result_http_status(result_http_status),
    .result_grpc_status(result_grpc_status),
    .result_user(result_user),
    .result_stream(result_stream),
    .result_application(result_application),
    .result_generation(result_generation),
    .result_model_epoch(result_model_epoch),
    .result_schema_epoch(result_schema_epoch),
    .result_address(result_address),
    .result_buffer_base(result_buffer_base),
    .result_buffer_bytes(result_buffer_bytes),
    .result_protobuf(result_protobuf),
    .result_unsupported_encoding(result_unsupported_encoding),
    .recovery_required(recovery_required),
    .recovery_address(recovery_address),
    .recovery_user(recovery_user),
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
    .control_memory_status(control_memory_status),
    .control_result_address(control_result_address),
    .control_result_buffer_base(control_result_buffer_base),
    .control_result_buffer_bytes(control_result_buffer_bytes),
    .control_result_application(control_result_application),
    .control_result_generation(control_result_generation),
    .control_result_message_limit(control_result_message_limit),
    .control_result_protobuf(control_result_protobuf),
    .control_result_unsupported_encoding(control_result_unsupported_encoding),
    .control_result_state(control_result_state),
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
    .idle(idle),
    .cfg_window_base(cfg_window_base),
    .cfg_window_bytes(cfg_window_bytes),
    .control_pool_base(control_pool_base),
    .control_pool_bytes(control_pool_bytes),
    .init_valid(init_valid),
    .init_ready(init_ready),
    .init_user(init_user),
    .init_stream(init_stream),
    .init_generation(init_generation),
    .init_record_address(init_record_address),
    .init_result_valid(init_result_valid),
    .init_result_ready(init_result_ready),
    .init_status(init_status),
    .init_memory_status(init_memory_status),
    .init_recovery_required(init_recovery_required),
    .init_recovery_address(init_recovery_address),
    .result_window_status(result_window_status),
    .init_cfg_context_base(init_cfg_context_base),
    .init_cfg_stream_base(init_cfg_stream_base),
    .init_cfg_window_base(init_cfg_window_base),
    .init_cfg_work_floor(init_cfg_work_floor),
    .init_cfg_context_bytes(init_cfg_context_bytes),
    .init_cfg_stream_bytes(init_cfg_stream_bytes),
    .init_cfg_window_bytes(init_cfg_window_bytes)
);
http2_owned_keyed_windows #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) service(
    .clk(clk),
    .rst(rst),
    .req_valid(dir_owner==0&&(control_valid||host_req_valid&&idle)),
    .req_ready(s_req_ready),
    .req_op(control_valid?control_op:host_req_op),
    .cfg_pool_base(control_valid?control_pool_base:host_cfg_pool_base),
    .cfg_pool_bytes(control_valid?control_pool_bytes:host_cfg_pool_bytes),
    .req_user(control_valid?control_user:host_req_user),
    .req_application(control_valid?control_application:host_req_application),
    .req_stream(control_valid?control_stream:host_req_stream),
    .req_generation(control_valid?control_generation:host_req_generation),
    .req_address(control_valid?control_address:host_req_address),
    .req_buffer_base(control_valid?control_buffer_base:host_req_buffer_base),
    .req_buffer_bytes(control_valid?control_buffer_bytes:host_req_buffer_bytes),
    .req_message_limit(control_valid?control_message_limit:host_req_message_limit),
    .req_protobuf(control_valid?control_protobuf:host_req_protobuf),
    .req_unsupported_encoding(control_valid?control_unsupported_encoding:host_req_unsupported_encoding),
    .req_maintenance(control_valid?control_maintenance:host_req_maintenance),
    .req_state(control_valid?256'd0:host_req_state),
    .rsp_valid(s_rsp_valid),
    .rsp_ready(dir_owner==1?control_result_ready:dir_owner==2&&host_rsp_ready),
    .rsp_status(s_rsp_status),
    .rsp_detail(s_rsp_detail),
    .rsp_memory_status(s_rsp_memory_status),
    .rsp_op(s_rsp_op),
    .rsp_address(s_rsp_address),
    .rsp_buffer_base(s_rsp_buffer_base),
    .rsp_buffer_bytes(s_rsp_buffer_bytes),
    .rsp_user(s_rsp_user),
    .rsp_application(s_rsp_application),
    .rsp_stream(s_rsp_stream),
    .rsp_generation(s_rsp_generation),
    .rsp_message_limit(s_rsp_message_limit),
    .rsp_protobuf(s_rsp_protobuf),
    .rsp_unsupported_encoding(s_rsp_unsupported_encoding),
    .rsp_state(s_rsp_state),
    .recovery_required(directory_recovery_required),
    .recovery_address(directory_recovery_address),
    .lease_valid(1'b0),
    .lease_ready(),
    .lease_user('0),
    .lease_stream('0),
    .lease_pool_base('0),
    .lease_pool_bytes('0),
    .lease_rsp_ready(1'b0),
    .lease_active(),
    .lease_rsp_valid(),
    .lease_rsp_status(),
    .lease_rsp_detail(),
    .lease_rsp_memory_status(),
    .lease_rsp_op(),
    .lease_rsp_address(),
    .lease_rsp_buffer_base(),
    .lease_rsp_buffer_bytes(),
    .lease_rsp_user(),
    .lease_rsp_application(),
    .lease_rsp_stream(),
    .lease_rsp_generation(),
    .lease_rsp_message_limit(),
    .lease_rsp_protobuf(),
    .lease_rsp_unsupported_encoding(),
    .lease_rsp_state(),
    .window_req_valid(win_owner==0&&(init_valid||window_req_valid)),
    .window_req_ready(s_window_req_ready),
    .window_req_op(init_valid?4'd1:window_req_op),
    .window_req_maintenance(init_valid?1'b0:window_req_maintenance),
    .window_req_user(init_valid?init_user:window_req_user),
    .window_req_stream(init_valid?init_stream:window_req_stream),
    .window_req_generation(init_valid?init_generation:window_req_generation),
    .window_req_record_address(init_valid?init_record_address:window_req_record_address),
    .window_req_amount(init_valid?32'd0:window_req_amount),
    .window_cfg_context_base(init_valid?init_cfg_context_base:window_cfg_context_base),
    .window_cfg_stream_base(init_valid?init_cfg_stream_base:window_cfg_stream_base),
    .window_cfg_window_base(init_valid?init_cfg_window_base:window_cfg_window_base),
    .window_cfg_work_floor(init_valid?init_cfg_work_floor:window_cfg_work_floor),
    .window_cfg_context_bytes(init_valid?init_cfg_context_bytes:window_cfg_context_bytes),
    .window_cfg_stream_bytes(init_valid?init_cfg_stream_bytes:window_cfg_stream_bytes),
    .window_cfg_window_bytes(init_valid?init_cfg_window_bytes:window_cfg_window_bytes),
    .window_rsp_valid(s_window_rsp_valid),
    .window_rsp_ready(win_owner==1?init_result_ready:win_owner==2&&window_rsp_ready),
    .window_rsp_op(s_window_rsp_op),
    .window_rsp_user(s_window_rsp_user),
    .window_rsp_stream(s_window_rsp_stream),
    .window_rsp_status(s_window_rsp_status),
    .window_rsp_detail(s_window_rsp_detail),
    .window_rsp_memory_status(s_window_rsp_memory_status),
    .window_rsp_connection_error(s_window_rsp_connection_error),
    .window_rsp_http2_error(s_window_rsp_http2_error),
    .window_rsp_grant_bytes(s_window_rsp_grant_bytes),
    .window_rsp_connection_window(s_window_rsp_connection_window),
    .window_rsp_initial_window(s_window_rsp_initial_window),
    .window_rsp_stream_window(s_window_rsp_stream_window),
    .window_rsp_max_frame_bytes(s_window_rsp_max_frame_bytes),
    .window_rsp_affected_streams(s_window_rsp_affected_streams),
    .window_recovery_required(window_recovery_required),
    .window_recovery_address(window_recovery_address),
    .idle(service_idle),
    .window_busy(window_busy),
    .window_lock_status(window_lock_status),
    .directory_pool_lock_active(directory_pool_lock_active),
    .mem_valid(s_mem_valid),
    .mem_ready(s_mem_ready),
    .mem_write(s_mem_write),
    .mem_addr(s_mem_addr),
    .mem_bytes(s_mem_bytes),
    .mem_data(s_mem_data),
    .mem_rsp_valid(s_mem_rsp_valid),
    .mem_rsp_ready(s_mem_rsp_ready),
    .mem_rsp_data(s_mem_rsp_data),
    .mem_rsp_status(s_mem_rsp_status)
);
always @(posedge clk)begin
    if(rst)begin dir_owner<=0;win_owner<=0;end else begin
        if(dir_owner==0&&s_req_ready&&(control_valid||host_req_valid&&idle))dir_owner<=control_valid?1:2;
        if(s_rsp_valid&&(dir_owner==1?control_result_ready:dir_owner==2&&host_rsp_ready))dir_owner<=0;
        if(win_owner==0&&s_window_req_ready&&(init_valid||window_req_valid))win_owner<=init_valid?1:2;
        if(s_window_rsp_valid&&(win_owner==1?init_result_ready:win_owner==2&&window_rsp_ready))win_owner<=0;
    end
end
endmodule
`default_nettype wire
