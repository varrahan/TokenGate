`timescale 1ns/1ps
`default_nettype none
// Committed semantic gRPC ingress -> live directory validation -> actual Parser.
// Packet/control mutations are excluded while a payload lease is being replayed.
module grpc_shared_directory_parser #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,
    parameter integer FIFO_DEPTH=16,parameter integer MAX_TEXT_BYTES=16384,parameter integer MAX_FIELD_BYTES=16384
)(
    input wire clk,input wire rst,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes,
    input wire queue_cfg_valid,output wire queue_cfg_ready,input wire queue_cfg_clear,input wire maintenance_grant,
    input wire [MEMORY_ADDR_WIDTH-1:0] queue_cfg_base,input wire [MEMORY_ADDR_WIDTH:0] queue_cfg_bytes,
    output wire queue_cfg_result_valid,input wire queue_cfg_result_ready,output wire [7:0] queue_cfg_status,
    input wire control_valid,output wire control_ready,input wire [2:0] control_op,
    input wire [USER_WIDTH-1:0] control_user,control_application,input wire [30:0] control_stream,input wire [31:0] control_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] control_address,control_buffer_base,input wire [MEMORY_ADDR_WIDTH:0] control_buffer_bytes,
    input wire [31:0] control_message_limit,input wire control_protobuf,control_unsupported_encoding,control_maintenance,
    output wire control_result_valid,input wire control_result_ready,output wire [7:0] control_status,control_detail,control_memory_status,
    output wire [2:0] control_result_op,output wire [MEMORY_ADDR_WIDTH-1:0] control_result_address,control_result_buffer_base,
    output wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes,output wire [USER_WIDTH-1:0] control_result_user,control_result_application,
    output wire [30:0] control_result_stream,output wire [31:0] control_result_generation,control_result_message_limit,
    output wire control_result_protobuf,control_result_unsupported_encoding,output wire [255:0] control_result_state,
    input wire packet_start_valid,output wire packet_start_ready,input wire [USER_WIDTH-1:0] packet_start_user,input wire [31:0] packet_start_tag,
    input wire s_valid,output wire s_ready,input wire [1:0] s_kind,input wire [7:0] s_data,input wire [30:0] s_stream,
    input wire prepare_valid,output wire prepare_ready,output wire prepared_valid,input wire prepared_ready,output wire prepared_failed,output wire [7:0] prepared_status,
    input wire decision_valid,output wire decision_ready,input wire decision_commit,
    output wire packet_result_valid,input wire packet_result_ready,output wire packet_committed,
    output wire [7:0] packet_status,packet_detail,packet_memory_status,output wire [USER_WIDTH-1:0] packet_user,output wire [31:0] packet_tag,
    output wire rpc_error_valid,input wire rpc_error_ready,output wire [7:0] rpc_error_status,rpc_error_detail,rpc_error_memory_status,
    output wire [USER_WIDTH-1:0] rpc_error_user,rpc_error_application,output wire [30:0] rpc_error_stream,output wire [31:0] rpc_error_generation,rpc_error_packet_tag,
    output wire stream_recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] stream_recovery_address,
    output wire queue_recovery_required,output wire [7:0] queue_recovery_detail,queue_recovery_memory_status,
    output wire retirement_pending,output wire [31:0] queued_count,pending_count,output wire idle,
    output wire [4:0] mem_valid,input wire [4:0] mem_ready,output wire [4:0] mem_write,
    output wire [5*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [19:0] mem_bytes,output wire [359:0] mem_data,
    input wire [4:0] mem_rsp_valid,output wire [4:0] mem_rsp_ready,input wire [359:0] mem_rsp_data,input wire [39:0] mem_rsp_status,
    input wire admit_messages,
    input wire stream_cfg_valid,output wire stream_cfg_ready,output reg stream_cfg_result_valid,
    input wire stream_cfg_result_ready,output reg [7:0] stream_cfg_status,
    input wire cfg_unlock,input wire cfg_schema_valid,output wire cfg_schema_ready,output wire cfg_quiescent,
    input wire [3:0] cfg_schema_index,input wire [255:0] cfg_schema_key,input wire [5:0] cfg_schema_key_length,
    input wire cfg_schema_json_enable,input wire [28:0] cfg_schema_field,input wire cfg_schema_proto_enable,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire [USER_WIDTH-1:0] text_connection,output wire [30:0] text_stream,output wire [31:0] text_generation,text_ordinal,text_packet_tag,
    output wire completion_valid,input wire completion_ready,output wire [7:0] completion_status,completion_detail,completion_memory_status,
    output wire [USER_WIDTH-1:0] completion_user,completion_application,output wire [30:0] completion_stream,
    output wire [31:0] completion_generation,completion_ordinal,completion_packet_tag,
    output wire payload_lease_active
,
    output wire  dir_req_valid,
    input wire  dir_req_ready,
    output wire [2:0] dir_req_op,
    output wire [MEMORY_ADDR_WIDTH-1:0] dir_cfg_pool_base,
    output wire [MEMORY_ADDR_WIDTH:0] dir_cfg_pool_bytes,
    output wire [USER_WIDTH-1:0] dir_req_user,
    output wire [USER_WIDTH-1:0] dir_req_application,
    output wire [30:0] dir_req_stream,
    output wire [31:0] dir_req_generation,
    output wire [MEMORY_ADDR_WIDTH-1:0] dir_req_address,
    output wire [MEMORY_ADDR_WIDTH-1:0] dir_req_buffer_base,
    output wire [MEMORY_ADDR_WIDTH:0] dir_req_buffer_bytes,
    output wire [31:0] dir_req_message_limit,
    output wire  dir_req_protobuf,
    output wire  dir_req_unsupported_encoding,
    output wire  dir_req_maintenance,
    output wire [255:0] dir_req_state,
    input wire  dir_rsp_valid,
    output wire  dir_rsp_ready,
    input wire [7:0] dir_rsp_status,
    input wire [7:0] dir_rsp_detail,
    input wire [7:0] dir_rsp_memory_status,
    input wire [2:0] dir_rsp_op,
    input wire [MEMORY_ADDR_WIDTH-1:0] dir_rsp_address,
    input wire [MEMORY_ADDR_WIDTH-1:0] dir_rsp_buffer_base,
    input wire [MEMORY_ADDR_WIDTH:0] dir_rsp_buffer_bytes,
    input wire [USER_WIDTH-1:0] dir_rsp_user,
    input wire [USER_WIDTH-1:0] dir_rsp_application,
    input wire [30:0] dir_rsp_stream,
    input wire [31:0] dir_rsp_generation,
    input wire [31:0] dir_rsp_message_limit,
    input wire  dir_rsp_protobuf,
    input wire  dir_rsp_unsupported_encoding,
    input wire [255:0] dir_rsp_state,
    input wire  dir_recovery_required,
    input wire [MEMORY_ADDR_WIDTH-1:0] dir_recovery_address,
    input wire  dir_idle
);

    localparam IDLE=0,EXTERNAL_CONTROL=1,LOOKUP_REQ=2,LOOKUP_WAIT=3,VERIFY=4,APP_START=5,APP_RUN=6,RESULT=7;
    reg [2:0] state;reg packet_busy,engines_quiet;
    reg stream_configured;reg [MEMORY_ADDR_WIDTH-1:0] stream_pool_base;
    reg [MEMORY_ADDR_WIDTH:0] stream_pool_bytes;
    wire [63:0] stream_pool_end={1'b0,cfg_stream_base}+{1'b0,cfg_stream_bytes};
    wire stream_config_good=cfg_stream_bytes>=128&&cfg_stream_bytes[6:0]==0&&stream_pool_end<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire normal_mode=state==IDLE||state==EXTERNAL_CONTROL;
    wire query=state==LOOKUP_REQ||state==LOOKUP_WAIT;
    wire engine_idle,app_idle,engine_packet_start_ready,engine_s_ready,engine_prepare_ready,engine_queue_cfg_ready;
    wire engine_control_ready,engine_control_result_valid;
    wire engine_control_valid=state==LOOKUP_REQ||state==IDLE&&control_valid&&stream_configured&&!stream_cfg_result_valid;
    wire engine_control_result_ready=state==LOOKUP_WAIT||state==EXTERNAL_CONTROL&&control_result_ready;
    wire [7:0] engine_control_status,engine_control_detail,engine_control_memory_status;
    wire [2:0] engine_control_result_op;
    wire [MEMORY_ADDR_WIDTH-1:0] engine_control_result_address,engine_control_result_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] engine_control_result_buffer_bytes;
    wire [USER_WIDTH-1:0] engine_control_result_user,engine_control_result_application;
    wire [30:0] engine_control_result_stream;
    wire [31:0] engine_control_result_generation,engine_control_result_message_limit;
    wire engine_control_result_protobuf,engine_control_result_unsupported_encoding;
    wire [255:0] engine_control_result_state;
    wire descriptor_valid;wire [USER_WIDTH-1:0] queue_user,queue_application;
    wire [30:0] queue_stream;wire queue_protobuf;
    wire [MEMORY_ADDR_WIDTH-1:0] queue_base;wire [31:0] queue_bytes,queue_ordinal,queue_generation,queue_packet_tag;
    reg [USER_WIDTH-1:0] descriptor_user,descriptor_application;reg [30:0] descriptor_stream;reg descriptor_protobuf;
    reg [MEMORY_ADDR_WIDTH-1:0] descriptor_base;reg [31:0] descriptor_bytes,descriptor_ordinal,descriptor_generation,descriptor_packet_tag;
    reg [7:0] lookup_status,lookup_memory,status,detail,memory_status;reg [7:0] checks;
    wire [63:0] descriptor_end={1'b0,descriptor_base}+{32'd0,descriptor_bytes};
    wire [63:0] allocation_end={1'b0,engine_control_result_buffer_base}+{1'b0,engine_control_result_buffer_bytes};
    wire [63:0] committed_end={1'b0,engine_control_result_buffer_base}+{32'd0,engine_control_result_state[31:0]};
    wire start_message=state==IDLE&&!packet_busy&&stream_configured&&!stream_cfg_result_valid&&admit_messages&&descriptor_valid&&app_idle&&
        !control_valid&&!queue_cfg_valid&&!queue_cfg_result_valid&&!cfg_unlock&&
        !stream_recovery_required&&!queue_recovery_required&&!retirement_pending;
    assign control_ready=state==IDLE&&stream_configured&&!stream_cfg_result_valid&&engine_control_ready;
    assign control_result_valid=state==EXTERNAL_CONTROL&&engine_control_result_valid;
    assign packet_start_ready=engine_packet_start_ready&&normal_mode&&!start_message&&!cfg_unlock&&stream_configured&&!stream_cfg_result_valid&&!stream_cfg_valid;
    assign s_ready=engine_s_ready&&normal_mode;
    assign prepare_ready=engine_prepare_ready&&normal_mode;
    assign queue_cfg_ready=engine_queue_cfg_ready&&normal_mode&&!stream_cfg_result_valid;
    // The registered quiet proof cuts the global tokenizer-idle/admission
    // chain out of the pool-register enable. Immediate queue and control guards
    // exclude work admitted since that proof; stream_cfg_valid already blocks
    // packet admission, and a nonempty queue prevents reconfiguration.
    assign stream_cfg_ready=!rst&&state==IDLE&&!packet_busy&&engines_quiet&&!descriptor_valid&&queued_count==0&&pending_count==0&&
        !stream_cfg_result_valid&&!control_valid&&!queue_cfg_valid&&!queue_cfg_result_valid&&
        !stream_recovery_required&&!queue_recovery_required&&!retirement_pending&&(!stream_configured||maintenance_grant);
    assign control_status=engine_control_status;
    assign control_detail=engine_control_detail;
    assign control_memory_status=engine_control_memory_status;
    assign control_result_op=engine_control_result_op;
    assign control_result_address=engine_control_result_address;
    assign control_result_buffer_base=engine_control_result_buffer_base;
    assign control_result_buffer_bytes=engine_control_result_buffer_bytes;
    assign control_result_user=engine_control_result_user;
    assign control_result_application=engine_control_result_application;
    assign control_result_stream=engine_control_result_stream;
    assign control_result_generation=engine_control_result_generation;
    assign control_result_message_limit=engine_control_result_message_limit;
    assign control_result_protobuf=engine_control_result_protobuf;
    assign control_result_unsupported_encoding=engine_control_result_unsupported_encoding;
    assign control_result_state=engine_control_result_state;
    grpc_external_directory_ingress #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) ingress(
    .clk(clk),
    .rst(rst),
    .cfg_stream_base(stream_pool_base),
    .cfg_stream_bytes(stream_pool_bytes),
    .queue_cfg_valid(queue_cfg_valid&&normal_mode&&!stream_cfg_result_valid),
    .queue_cfg_ready(engine_queue_cfg_ready),
    .queue_cfg_clear(queue_cfg_clear),
    .maintenance_grant(maintenance_grant),
    .queue_cfg_base(queue_cfg_base),
    .queue_cfg_bytes(queue_cfg_bytes),
    .queue_cfg_result_valid(queue_cfg_result_valid),
    .queue_cfg_result_ready(queue_cfg_result_ready),
    .queue_cfg_status(queue_cfg_status),
    .control_valid(engine_control_valid),
    .control_ready(engine_control_ready),
    .control_op(query?3'd1:control_op),
    .control_user(query?descriptor_user:control_user),
    .control_application(control_application),
    .control_stream(query?descriptor_stream:control_stream),
    .control_generation(control_generation),
    .control_address(control_address),
    .control_buffer_base(control_buffer_base),
    .control_buffer_bytes(control_buffer_bytes),
    .control_message_limit(control_message_limit),
    .control_protobuf(control_protobuf),
    .control_unsupported_encoding(control_unsupported_encoding),
    .control_maintenance(control_maintenance),
    .control_result_valid(engine_control_result_valid),
    .control_result_ready(engine_control_result_ready),
    .control_status(engine_control_status),
    .control_detail(engine_control_detail),
    .control_memory_status(engine_control_memory_status),
    .control_result_op(engine_control_result_op),
    .control_result_address(engine_control_result_address),
    .control_result_buffer_base(engine_control_result_buffer_base),
    .control_result_buffer_bytes(engine_control_result_buffer_bytes),
    .control_result_user(engine_control_result_user),
    .control_result_application(engine_control_result_application),
    .control_result_stream(engine_control_result_stream),
    .control_result_generation(engine_control_result_generation),
    .control_result_message_limit(engine_control_result_message_limit),
    .control_result_protobuf(engine_control_result_protobuf),
    .control_result_unsupported_encoding(engine_control_result_unsupported_encoding),
    .control_result_state(engine_control_result_state),
    .packet_start_valid(packet_start_valid&&normal_mode&&!start_message&&!cfg_unlock&&stream_configured&&!stream_cfg_result_valid&&!stream_cfg_valid),
    .packet_start_ready(engine_packet_start_ready),
    .packet_start_user(packet_start_user),
    .packet_start_tag(packet_start_tag),
    .s_valid(s_valid&&normal_mode),
    .s_ready(engine_s_ready),
    .s_kind(s_kind),
    .s_data(s_data),
    .s_stream(s_stream),
    .prepare_valid(prepare_valid&&normal_mode),
    .prepare_ready(engine_prepare_ready),
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
    .m_valid(descriptor_valid),
    .m_ready(state==RESULT&&completion_ready),
    .m_user(queue_user),
    .m_application(queue_application),
    .m_stream(queue_stream),
    .m_protobuf(queue_protobuf),
    .m_base(queue_base),
    .m_bytes(queue_bytes),
    .m_ordinal(queue_ordinal),
    .m_generation(queue_generation),
    .m_packet_tag(queue_packet_tag),
    .stream_recovery_required(stream_recovery_required),
    .stream_recovery_address(stream_recovery_address),
    .queue_recovery_required(queue_recovery_required),
    .queue_recovery_detail(queue_recovery_detail),
    .queue_recovery_memory_status(queue_recovery_memory_status),
    .retirement_pending(retirement_pending),
    .queued_count(queued_count),
    .pending_count(pending_count),
    .idle(engine_idle),
    .mem_valid(mem_valid[3:0]),
    .mem_ready(mem_ready[3:0]),
    .mem_write(mem_write[3:0]),
    .mem_addr(mem_addr[0+:4*MEMORY_ADDR_WIDTH]),
    .mem_bytes(mem_bytes[15:0]),
    .mem_data(mem_data[287:0]),
    .mem_rsp_valid(mem_rsp_valid[3:0]),
    .mem_rsp_ready(mem_rsp_ready[3:0]),
    .mem_rsp_data(mem_rsp_data[287:0]),
    .mem_rsp_status(mem_rsp_status[31:0]),
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
    .dir_idle(dir_idle)
);

    wire app_message_ready,app_completion_valid;wire [7:0] app_status,app_detail,app_memory;
    wire [USER_WIDTH-1:0] app_user,app_application;wire [30:0] app_stream;wire [31:0] app_ordinal;
    // A registered empty-pipeline proof avoids feeding Parser idle through its
    // own schema-unlock input. Immediate guards exclude every new admission.
    assign cfg_quiescent=state==IDLE&&!packet_busy&&engines_quiet&&!descriptor_valid&&queued_count==0&&pending_count==0&&
        !control_valid&&!packet_start_valid&&!queue_cfg_valid&&!queue_cfg_result_valid&&!stream_cfg_result_valid&&!stream_cfg_valid&&
        !stream_recovery_required&&!queue_recovery_required&&!retirement_pending;
    wire schema_unlock=cfg_unlock&&cfg_quiescent;
    grpc_application_decoder #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)) application(
        .clk(clk),.rst(rst),.message_valid(state==APP_START),.message_ready(app_message_ready),
        .message_base(descriptor_base),.message_bytes(descriptor_bytes),.message_ordinal(descriptor_ordinal),.message_user(descriptor_user),
        .message_application(descriptor_application),.message_stream(descriptor_stream),.message_protobuf(descriptor_protobuf),
        .cfg_unlock(schema_unlock),.cfg_schema_valid(cfg_schema_valid&&schema_unlock),.cfg_schema_ready(cfg_schema_ready),.cfg_schema_index(cfg_schema_index),
        .cfg_schema_key(cfg_schema_key),.cfg_schema_key_length(cfg_schema_key_length),.cfg_schema_json_enable(cfg_schema_json_enable),.cfg_schema_field(cfg_schema_field),.cfg_schema_proto_enable(cfg_schema_proto_enable),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),.m_axis_text_tready(m_axis_text_tready),.m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),
        .completion_valid(app_completion_valid),.completion_ready(state==APP_RUN),.completion_status(app_status),.completion_detail(app_detail),.completion_memory_status(app_memory),
        .completion_user(app_user),.completion_application(app_application),.completion_stream(app_stream),.completion_ordinal(app_ordinal),
        .mem_valid(mem_valid[4]),.mem_ready(mem_ready[4]),.mem_write(mem_write[4]),.mem_addr(mem_addr[4*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[16+:4]),.mem_data(mem_data[288+:72]),
        .mem_rsp_valid(mem_rsp_valid[4]),.mem_rsp_ready(mem_rsp_ready[4]),.mem_rsp_data(mem_rsp_data[288+:72]),.mem_rsp_status(mem_rsp_status[32+:8]),.idle(app_idle));
    assign text_connection=descriptor_user;assign text_stream=descriptor_stream;assign text_generation=descriptor_generation;
    assign text_ordinal=descriptor_ordinal;assign text_packet_tag=descriptor_packet_tag;
    assign completion_valid=state==RESULT;assign completion_status=status;assign completion_detail=detail;assign completion_memory_status=memory_status;
    assign completion_user=descriptor_user;assign completion_application=descriptor_application;assign completion_stream=descriptor_stream;
    assign completion_generation=descriptor_generation;assign completion_ordinal=descriptor_ordinal;assign completion_packet_tag=descriptor_packet_tag;
    assign payload_lease_active=state>=LOOKUP_REQ;
    assign idle=state==IDLE&&!packet_busy&&engine_idle&&app_idle&&!control_valid&&!packet_start_valid&&!stream_cfg_result_valid&&!stream_cfg_valid&&
        !stream_recovery_required&&!queue_recovery_required&&!retirement_pending;
    task reject(input [7:0] code,input [7:0] reason,input [7:0] memory_code);
        begin status<=code;detail<=reason;memory_status<=memory_code;state<=RESULT;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;packet_busy<=0;engines_quiet<=0;stream_configured<=0;stream_pool_base<=0;stream_pool_bytes<=0;stream_cfg_result_valid<=0;stream_cfg_status<=0;
            descriptor_user<=0;descriptor_application<=0;descriptor_stream<=0;descriptor_protobuf<=0;descriptor_base<=0;
            descriptor_bytes<=0;descriptor_ordinal<=0;descriptor_generation<=0;descriptor_packet_tag<=0;lookup_status<=0;lookup_memory<=0;checks<=0;status<=0;detail<=0;memory_status<=0;
        end else begin
            engines_quiet<=engine_idle&&app_idle;
            if(stream_cfg_result_valid&&stream_cfg_result_ready)stream_cfg_result_valid<=0;
            if(stream_cfg_valid&&stream_cfg_ready)begin
                stream_cfg_result_valid<=1;stream_cfg_status<=stream_config_good?8'd0:8'd1;
                if(stream_config_good)begin stream_configured<=1;stream_pool_base<=cfg_stream_base;stream_pool_bytes<=cfg_stream_bytes;end
            end
            if(packet_start_valid&&packet_start_ready)packet_busy<=1;
            if(packet_result_valid&&packet_result_ready)packet_busy<=0;
            case(state)
                IDLE:begin
                    if(control_valid&&control_ready)state<=EXTERNAL_CONTROL;
                    else if(start_message)begin
                        descriptor_user<=queue_user;descriptor_application<=queue_application;descriptor_stream<=queue_stream;descriptor_protobuf<=queue_protobuf;
                        descriptor_base<=queue_base;descriptor_bytes<=queue_bytes;descriptor_ordinal<=queue_ordinal;descriptor_generation<=queue_generation;descriptor_packet_tag<=queue_packet_tag;
                        status<=0;detail<=0;memory_status<=0;state<=LOOKUP_REQ;
                    end
                end
                EXTERNAL_CONTROL:if(engine_control_result_valid&&control_result_ready)state<=IDLE;
                LOOKUP_REQ:if(engine_control_ready)state<=LOOKUP_WAIT;
                LOOKUP_WAIT:if(engine_control_result_valid)begin
                    lookup_status<=engine_control_status;lookup_memory<=engine_control_memory_status;
                    checks[0]<=engine_control_result_user==descriptor_user&&engine_control_result_stream==descriptor_stream;
                    checks[1]<=engine_control_result_generation==descriptor_generation;
                    checks[2]<=engine_control_result_application==descriptor_application&&engine_control_result_protobuf==descriptor_protobuf;
                    checks[3]<=descriptor_bytes<=engine_control_result_message_limit;
                    checks[4]<=descriptor_bytes==0?descriptor_base==0:descriptor_base>=engine_control_result_buffer_base;
                    checks[5]<=descriptor_bytes==0||descriptor_end<=allocation_end;
                    checks[6]<=descriptor_bytes==0||descriptor_end<=committed_end;
                    checks[7]<=descriptor_ordinal<engine_control_result_state[159:128]||
                        engine_control_result_state[164]&&descriptor_ordinal==32'hffffffff;
                    state<=VERIFY;
                end
                VERIFY:begin
                    if(lookup_status==3)reject(4,1,0);
                    else if(lookup_status!=0)reject(6,lookup_status,lookup_memory);
                    else if(!checks[0])reject(5,1,0);
                    else if(!checks[1])reject(4,2,0);
                    else if(!checks[2])reject(5,2,0);
                    else if(!(&checks[6:3]))reject(5,3,0);
                    else if(!checks[7])reject(5,4,0);
                    else state<=APP_START;
                end
                APP_START:if(app_message_ready)state<=APP_RUN;
                APP_RUN:if(app_completion_valid)begin status<=app_status;detail<=app_detail;memory_status<=app_memory;state<=RESULT;end
                RESULT:if(completion_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire

