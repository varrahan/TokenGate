`timescale 1ns/1ps
`default_nettype none
// Pre-admitted, depadded DATA events -> persisted gRPC progress and committed
// descriptors. Packet PREPARE precedes the external transport COMMIT decision.
// Committed descriptors still require live-generation/payload-lease admission.
module grpc_ingress_engine #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23
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
    output wire m_valid,input wire m_ready,output wire [USER_WIDTH-1:0] m_user,m_application,output wire [30:0] m_stream,
    output wire m_protobuf,output wire [MEMORY_ADDR_WIDTH-1:0] m_base,output wire [31:0] m_bytes,m_ordinal,m_generation,m_packet_tag,
    output wire stream_recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] stream_recovery_address,
    output wire queue_recovery_required,output wire [7:0] queue_recovery_detail,queue_recovery_memory_status,
    output wire retirement_pending,output wire [31:0] queued_count,pending_count,output wire idle,
    output wire [3:0] mem_valid,input wire [3:0] mem_ready,output wire [3:0] mem_write,
    output wire [4*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [15:0] mem_bytes,output wire [287:0] mem_data,
    input wire [3:0] mem_rsp_valid,output wire [3:0] mem_rsp_ready,input wire [287:0] mem_rsp_data,input wire [31:0] mem_rsp_status
);
    localparam READY=0,STORE_REQ=1,STORE_WAIT=2,CORE_START=3,FEED=4,FLUSH=5,ACK_CORE=6,RPC_ERROR=7,
        CONTROL_RESULT=8,PREPARED=9,DECISION=10,QUEUE_RESULT=11,PACKET_RESULT=12,RECOVERY=13,PREPARE_WAIT=14;
    localparam A_LOAD=0,A_SAVE=1,A_CLOSE_RPC=2,A_CONTROL=3,A_RETIRE_FIND=4,A_RETIRE_CLOSE=5;
    localparam WHY_EVENT=0,WHY_PREPARE=1,WHY_CONTROL=2;
    reg [3:0] state;reg [2:0] action;reg [1:0] reason;
    reg packet_active,cache_active,held_valid,packet_fatal,retire_needed,result_delivered,control_rejected,rpc_pending;
    reg [USER_WIDTH-1:0] owner,cached_application;reg [31:0] tag,cached_generation;reg [30:0] cached_stream,held_stream;
    reg [MEMORY_ADDR_WIDTH-1:0] packet_pool_base,cached_address,cached_buffer_base;
    reg [MEMORY_ADDR_WIDTH:0] packet_pool_bytes,cached_buffer_bytes;
    reg [31:0] cached_limit;reg cached_protobuf,cached_encoding;reg [255:0] cached_state;
    reg [1:0] held_kind;reg [7:0] held_data;
    reg committed,prep_failed;reg [7:0] status,detail,memory_status,error_status,error_detail,error_memory,prep_status;
    reg [USER_WIDTH-1:0] error_application;reg [30:0] error_stream;reg [31:0] error_generation;
    reg [2:0] c_op;reg [USER_WIDTH-1:0] c_user,c_application;reg [30:0] c_stream;reg [31:0] c_generation,c_limit;
    reg [MEMORY_ADDR_WIDTH-1:0] c_address,c_buffer_base,c_pool_base;reg [MEMORY_ADDR_WIDTH:0] c_buffer_bytes,c_pool_bytes;
    reg c_protobuf,c_encoding,c_maintenance;
    reg [2:0] r_op;reg [USER_WIDTH-1:0] r_user,r_application;reg [30:0] r_stream;reg [31:0] r_generation,r_limit;
    reg [MEMORY_ADDR_WIDTH-1:0] r_address,r_buffer_base,r_pool_base;reg [MEMORY_ADDR_WIDTH:0] r_buffer_bytes,r_pool_bytes;
    reg r_protobuf,r_encoding,r_maintenance;reg [255:0] r_state;
    wire store_ready,store_valid,store_idle;wire [7:0] store_status,store_detail,store_memory;wire [2:0] store_op;
    wire [MEMORY_ADDR_WIDTH-1:0] store_address,store_buffer_base;wire [MEMORY_ADDR_WIDTH:0] store_buffer_bytes;
    wire [USER_WIDTH-1:0] store_user,store_application;wire [30:0] store_stream;wire [31:0] store_generation,store_limit;
    wire store_protobuf,store_encoding;wire [255:0] store_state;
    grpc_stream_store #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) registry(
        .clk(clk),.rst(rst),.req_valid(state==STORE_REQ),.req_ready(store_ready),.req_op(r_op),.cfg_pool_base(r_pool_base),.cfg_pool_bytes(r_pool_bytes),
        .req_user(r_user),.req_application(r_application),.req_stream(r_stream),.req_generation(r_generation),.req_address(r_address),.req_buffer_base(r_buffer_base),.req_buffer_bytes(r_buffer_bytes),
        .req_message_limit(r_limit),.req_protobuf(r_protobuf),.req_unsupported_encoding(r_encoding),.req_maintenance(r_maintenance),.req_state(r_state),
        .rsp_valid(store_valid),.rsp_ready(state==STORE_WAIT&&action!=A_CONTROL||state==CONTROL_RESULT&&!control_rejected&&control_result_ready),.rsp_status(store_status),.rsp_detail(store_detail),.rsp_memory_status(store_memory),.rsp_op(store_op),
        .rsp_address(store_address),.rsp_buffer_base(store_buffer_base),.rsp_buffer_bytes(store_buffer_bytes),.rsp_user(store_user),.rsp_application(store_application),.rsp_stream(store_stream),.rsp_generation(store_generation),.rsp_message_limit(store_limit),.rsp_protobuf(store_protobuf),.rsp_unsupported_encoding(store_encoding),.rsp_state(store_state),
        .recovery_required(stream_recovery_required),.recovery_address(stream_recovery_address),.idle(store_idle),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),.mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]));
    wire core_start_ready,core_ready,core_result_valid,core_idle,core_message_valid,queue_append_ready;
    // Register the complete descriptor before bounds/reservation arithmetic.
    // PREPARE must drain this stage as well as the acknowledged queue writer.
    reg descriptor_valid;
    reg [USER_WIDTH-1:0] descriptor_user,descriptor_application;
    reg [30:0] descriptor_stream;reg descriptor_protobuf;
    reg [MEMORY_ADDR_WIDTH-1:0] descriptor_base;
    reg [31:0] descriptor_bytes,descriptor_ordinal,descriptor_generation;
    wire [255:0] core_state;wire [7:0] core_status,core_detail,core_memory;
    wire [MEMORY_ADDR_WIDTH-1:0] core_message_base;wire [31:0] core_message_bytes,core_message_ordinal;
    wire [USER_WIDTH-1:0] core_message_user,core_message_application;wire [30:0] core_message_stream;
    grpc_message_deframer #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) decoder(
        .clk(clk),.rst(rst),.start_valid(state==CORE_START),.start_ready(core_start_ready),.start_user(owner),.start_stream(cached_stream),.start_application(cached_application),
        .cfg_buffer_base(cached_buffer_base),.cfg_buffer_bytes(cached_buffer_bytes),.cfg_message_limit(cached_limit),.cfg_unsupported_encoding(cached_encoding),.cfg_state(cached_state),
        .s_valid(state==FEED&&held_valid),.s_ready(core_ready),.s_kind(held_kind),.s_data(held_data),.s_user(owner),.s_stream(held_stream),
        .message_valid(core_message_valid),.message_ready(!descriptor_valid),.message_base(core_message_base),.message_bytes(core_message_bytes),.message_ordinal(core_message_ordinal),.message_user(core_message_user),.message_application(core_message_application),.message_stream(core_message_stream),
        .finish_valid(state==FLUSH),.result_valid(core_result_valid),.result_ready(state==ACK_CORE),.result_state(core_state),.result_status(core_status),.result_detail(core_detail),.result_memory_status(core_memory),.result_user(),.result_stream(),
        .mem_valid(mem_valid[1]),.mem_ready(mem_ready[1]),.mem_write(mem_write[1]),.mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[4+:4]),.mem_data(mem_data[72+:72]),.mem_rsp_valid(mem_rsp_valid[1]),.mem_rsp_ready(mem_rsp_ready[1]),.mem_rsp_data(mem_rsp_data[72+:72]),.mem_rsp_status(mem_rsp_status[8+:8]),.idle(core_idle));
    wire queue_begin_ready,queue_finish_ready,queue_result_valid,queue_committed,queue_failed,queue_idle,queue_cfg_ready_internal;
    wire [7:0] queue_status,queue_detail,queue_memory;wire [USER_WIDTH-1:0] queue_user;wire [31:0] queue_tag;
    wire config_allowed=(state==READY||state==RECOVERY)&&!packet_active&&!cache_active&&!control_valid&&(!queue_cfg_clear||maintenance_grant);
    wire start_allowed=state==READY&&!packet_active&&!control_valid&&!queue_cfg_valid&&!queue_cfg_result_valid&&!stream_recovery_required&&!queue_recovery_required&&!retire_needed;
    grpc_descriptor_queue #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) descriptors(
        .clk(clk),.rst(rst),.cfg_valid(queue_cfg_valid&&config_allowed),.cfg_ready(queue_cfg_ready_internal),.cfg_clear(queue_cfg_clear),.cfg_base(queue_cfg_base),.cfg_bytes(queue_cfg_bytes),.cfg_result_valid(queue_cfg_result_valid),.cfg_result_ready(queue_cfg_result_ready),.cfg_status(queue_cfg_status),
        .begin_valid(packet_start_valid&&start_allowed),.begin_ready(queue_begin_ready),.begin_user(packet_start_user),.begin_tag(packet_start_tag),
        .s_valid(descriptor_valid),.s_ready(queue_append_ready),.s_user(descriptor_user),.s_application(descriptor_application),.s_stream(descriptor_stream),.s_protobuf(descriptor_protobuf),.s_base(descriptor_base),.s_bytes(descriptor_bytes),.s_ordinal(descriptor_ordinal),.s_generation(descriptor_generation),
        .finish_valid(state==DECISION&&decision_valid),.finish_ready(queue_finish_ready),.finish_commit(decision_commit&&!packet_fatal),.finish_result_valid(queue_result_valid),.finish_result_ready(state==QUEUE_RESULT),.finish_committed(queue_committed),.finish_status(queue_status),.finish_detail(queue_detail),.finish_memory_status(queue_memory),.finish_user(queue_user),.finish_tag(queue_tag),
        .m_valid(m_valid),.m_ready(m_ready),.m_user(m_user),.m_application(m_application),.m_stream(m_stream),.m_protobuf(m_protobuf),.m_base(m_base),.m_bytes(m_bytes),.m_ordinal(m_ordinal),.m_generation(m_generation),.m_packet_tag(m_packet_tag),
        .transaction_active(),.transaction_failed(queue_failed),.recovery_required(queue_recovery_required),.recovery_detail(queue_recovery_detail),.recovery_memory_status(queue_recovery_memory_status),.queued_count(queued_count),.pending_count(pending_count),.idle(queue_idle),
        .mem_valid(mem_valid[2+:2]),.mem_ready(mem_ready[2+:2]),.mem_write(mem_write[2+:2]),.mem_addr(mem_addr[2*MEMORY_ADDR_WIDTH+:2*MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[8+:8]),.mem_data(mem_data[144+:144]),.mem_rsp_valid(mem_rsp_valid[2+:2]),.mem_rsp_ready(mem_rsp_ready[2+:2]),.mem_rsp_data(mem_rsp_data[144+:144]),.mem_rsp_status(mem_rsp_status[16+:16]));
    assign queue_cfg_ready=queue_cfg_ready_internal&&config_allowed;
    assign packet_start_ready=start_allowed&&queue_begin_ready;
    assign control_ready=!rst&&(state==READY||state==RECOVERY)&&!queue_cfg_result_valid;
    assign s_ready=!rst&&state==READY&&packet_active&&!control_valid;
    assign prepare_ready=!rst&&state==READY&&packet_active&&!control_valid&&!s_valid;
    assign prepared_valid=state==PREPARED;assign prepared_failed=prep_failed;assign prepared_status=prep_status;
    assign decision_ready=state==DECISION&&queue_finish_ready;
    assign packet_result_valid=state==PACKET_RESULT;assign packet_committed=committed;assign packet_status=status;assign packet_detail=detail;assign packet_memory_status=memory_status;assign packet_user=owner;assign packet_tag=tag;
    assign retirement_pending=retire_needed;
    assign rpc_error_valid=state==RPC_ERROR;assign rpc_error_user=owner;assign rpc_error_stream=error_stream;assign rpc_error_application=error_application;assign rpc_error_generation=error_generation;assign rpc_error_status=error_status;assign rpc_error_detail=error_detail;assign rpc_error_memory_status=error_memory;assign rpc_error_packet_tag=tag;
    assign control_result_valid=state==CONTROL_RESULT;
    assign control_status=control_rejected?8'd7:store_status;assign control_detail=control_rejected?8'h20:store_detail;assign control_memory_status=control_rejected?8'd0:store_memory;
    assign control_result_op=control_rejected?c_op:store_op;assign control_result_user=control_rejected?c_user:store_user;assign control_result_stream=control_rejected?c_stream:store_stream;
    assign control_result_address=control_rejected?{MEMORY_ADDR_WIDTH{1'b0}}:store_address;assign control_result_buffer_base=control_rejected?{MEMORY_ADDR_WIDTH{1'b0}}:store_buffer_base;assign control_result_buffer_bytes=control_rejected?{(MEMORY_ADDR_WIDTH+1){1'b0}}:store_buffer_bytes;
    assign control_result_application=control_rejected?{USER_WIDTH{1'b0}}:store_application;assign control_result_generation=control_rejected?32'd0:store_generation;assign control_result_message_limit=control_rejected?32'd0:store_limit;
    assign control_result_protobuf=!control_rejected&&store_protobuf;assign control_result_unsupported_encoding=!control_rejected&&store_encoding;assign control_result_state=control_rejected?256'd0:store_state;
    assign idle=state==READY&&!packet_active&&!cache_active&&!descriptor_valid&&!retire_needed&&store_idle&&core_idle&&queue_idle&&!control_valid&&!packet_start_valid;
    always @(posedge clk)begin
        if(rst)begin descriptor_valid<=0;descriptor_user<=0;descriptor_application<=0;descriptor_stream<=0;descriptor_protobuf<=0;descriptor_base<=0;descriptor_bytes<=0;descriptor_ordinal<=0;descriptor_generation<=0;end
        else if(!descriptor_valid)begin
            if(core_message_valid)begin
                descriptor_valid<=1;descriptor_user<=core_message_user;descriptor_application<=core_message_application;
                descriptor_stream<=core_message_stream;descriptor_protobuf<=cached_protobuf;descriptor_base<=core_message_base;
                descriptor_bytes<=core_message_bytes;descriptor_ordinal<=core_message_ordinal;descriptor_generation<=cached_generation;
            end
        end else if(queue_append_ready)descriptor_valid<=0;
    end
    task load_event;
        begin
            r_op<=1;r_user<=owner;r_stream<=held_stream;r_application<=0;r_generation<=0;r_address<=0;r_buffer_base<=0;r_buffer_bytes<=0;r_limit<=0;r_protobuf<=0;r_encoding<=0;r_maintenance<=0;r_state<=0;
            r_pool_base<=packet_pool_base;r_pool_bytes<=packet_pool_bytes;action<=A_LOAD;state<=STORE_REQ;
        end
    endtask
    task persist(input close_rpc);
        begin
            r_op<=close_rpc?3'd3:3'd2;r_user<=owner;r_stream<=cached_stream;r_application<=cached_application;r_generation<=cached_generation;r_address<=cached_address;
            r_buffer_base<=0;r_buffer_bytes<=0;r_limit<=0;r_protobuf<=0;r_encoding<=0;r_maintenance<=0;r_state<=core_state;
            r_pool_base<=packet_pool_base;r_pool_bytes<=packet_pool_bytes;action<=close_rpc?A_CLOSE_RPC:A_SAVE;state<=STORE_REQ;
        end
    endtask
    task send_control;
        begin
            r_op<=c_op;r_user<=c_user;r_application<=c_application;r_stream<=c_stream;r_generation<=c_generation;r_address<=c_address;
            r_buffer_base<=c_buffer_base;r_buffer_bytes<=c_buffer_bytes;r_limit<=c_limit;r_protobuf<=c_protobuf;r_encoding<=c_encoding;r_maintenance<=c_maintenance;r_state<=0;
            r_pool_base<=c_pool_base;r_pool_bytes<=c_pool_bytes;action<=A_CONTROL;state<=STORE_REQ;
        end
    endtask
    task retire_search;
        begin
            r_op<=6;r_user<=owner;r_stream<=0;r_application<=0;r_generation<=0;r_address<=0;r_buffer_base<=0;r_buffer_bytes<=0;r_limit<=0;r_protobuf<=0;r_encoding<=0;r_maintenance<=0;r_state<=0;
            r_pool_base<=packet_pool_base;r_pool_bytes<=packet_pool_bytes;action<=A_RETIRE_FIND;state<=STORE_REQ;
        end
    endtask
    task continue_work;
        begin
            if(reason==WHY_CONTROL)begin
                if(packet_fatal)begin control_rejected<=1;state<=CONTROL_RESULT;end else send_control;
            end else if(reason==WHY_PREPARE)state<=PREPARE_WAIT;
            else if(held_valid&&!packet_fatal)load_event;
            else begin held_valid<=0;state<=READY;end
        end
    endtask
    task fatal_store;
        begin packet_fatal<=1;status<=13;detail<=8'h80|store_status;memory_status<=store_memory;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=READY;action<=0;reason<=0;packet_active<=0;cache_active<=0;held_valid<=0;packet_fatal<=0;retire_needed<=0;result_delivered<=0;control_rejected<=0;rpc_pending<=0;
            owner<=0;tag<=0;cached_application<=0;cached_generation<=0;cached_stream<=0;held_stream<=0;packet_pool_base<=0;packet_pool_bytes<=0;cached_address<=0;cached_buffer_base<=0;cached_buffer_bytes<=0;
            cached_limit<=0;cached_protobuf<=0;cached_encoding<=0;cached_state<=0;held_kind<=0;held_data<=0;committed<=0;status<=0;detail<=0;memory_status<=0;prep_failed<=0;prep_status<=0;
            error_status<=0;error_detail<=0;error_memory<=0;error_application<=0;error_stream<=0;error_generation<=0;
            c_op<=0;c_user<=0;c_application<=0;c_stream<=0;c_generation<=0;c_limit<=0;c_address<=0;c_buffer_base<=0;c_pool_base<=0;c_buffer_bytes<=0;c_pool_bytes<=0;c_protobuf<=0;c_encoding<=0;c_maintenance<=0;
            r_op<=0;r_user<=0;r_application<=0;r_stream<=0;r_generation<=0;r_limit<=0;r_address<=0;r_buffer_base<=0;r_pool_base<=0;r_buffer_bytes<=0;r_pool_bytes<=0;r_protobuf<=0;r_encoding<=0;r_maintenance<=0;r_state<=0;
        end else begin
            if(packet_active&&queue_failed)packet_fatal<=1;
            case(state)
                READY,RECOVERY:begin
                    if(control_valid&&control_ready)begin
                        c_op<=control_op;c_user<=control_user;c_application<=control_application;c_stream<=control_stream;c_generation<=control_generation;c_limit<=control_message_limit;
                        c_address<=control_address;c_buffer_base<=control_buffer_base;c_buffer_bytes<=control_buffer_bytes;c_protobuf<=control_protobuf;c_encoding<=control_unsupported_encoding;c_maintenance<=control_maintenance;
                        c_pool_base<=packet_active||retire_needed?packet_pool_base:cfg_stream_base;c_pool_bytes<=packet_active||retire_needed?packet_pool_bytes:cfg_stream_bytes;
                        control_rejected<=control_op==2||packet_active&&(control_op==4||control_op==5)||state==RECOVERY&&control_op!=4&&control_op!=5;
                        if(control_op==2||packet_active&&(control_op==4||control_op==5)||state==RECOVERY&&control_op!=4&&control_op!=5||packet_fatal&&packet_active)begin control_rejected<=1;state<=CONTROL_RESULT;end
                        else if(cache_active)begin reason<=WHY_CONTROL;state<=FLUSH;end
                        else begin
                            r_op<=control_op;r_user<=control_user;r_application<=control_application;r_stream<=control_stream;r_generation<=control_generation;r_limit<=control_message_limit;
                            r_address<=control_address;r_buffer_base<=control_buffer_base;r_buffer_bytes<=control_buffer_bytes;r_protobuf<=control_protobuf;r_encoding<=control_unsupported_encoding;r_maintenance<=control_maintenance;r_state<=0;
                            r_pool_base<=packet_active||retire_needed?packet_pool_base:cfg_stream_base;r_pool_bytes<=packet_active||retire_needed?packet_pool_bytes:cfg_stream_bytes;action<=A_CONTROL;state<=STORE_REQ;
                        end
                    end else if(state==RECOVERY)begin
                        if(queue_cfg_result_valid&&queue_cfg_result_ready&&queue_cfg_status==0&&!stream_recovery_required&&retire_needed)retire_search;
                    end else if(packet_start_valid&&packet_start_ready)begin
                        packet_active<=1;owner<=packet_start_user;tag<=packet_start_tag;packet_pool_base<=cfg_stream_base;packet_pool_bytes<=cfg_stream_bytes;
                        packet_fatal<=0;status<=0;detail<=0;memory_status<=0;committed<=0;held_valid<=0;result_delivered<=0;rpc_pending<=0;
                    end else if(s_valid&&s_ready)begin
                        if(!packet_fatal)begin
                            held_kind<=s_kind;held_data<=s_data;held_stream<=s_stream;held_valid<=1;reason<=WHY_EVENT;
                            if(cache_active&&cached_stream==s_stream)state<=FEED;
                            else if(cache_active)state<=FLUSH;
                            else begin
                                r_op<=1;r_user<=owner;r_stream<=s_stream;r_application<=0;r_generation<=0;r_address<=0;r_buffer_base<=0;r_buffer_bytes<=0;r_limit<=0;r_protobuf<=0;r_encoding<=0;r_maintenance<=0;r_state<=0;
                                r_pool_base<=packet_pool_base;r_pool_bytes<=packet_pool_bytes;action<=A_LOAD;state<=STORE_REQ;
                            end
                        end
                    end else if(prepare_valid&&prepare_ready)begin reason<=WHY_PREPARE;state<=cache_active?FLUSH:PREPARE_WAIT;end
                end
                STORE_REQ:if(store_ready)state<=STORE_WAIT;
                STORE_WAIT:if(store_valid)begin
                    case(action)
                        A_CONTROL:state<=CONTROL_RESULT;
                        A_LOAD:begin
                            if(store_status==0)begin
                                cached_address<=store_address;cached_application<=store_application;cached_stream<=held_stream;cached_generation<=store_generation;cached_buffer_base<=store_buffer_base;cached_buffer_bytes<=store_buffer_bytes;cached_limit<=store_limit;cached_protobuf<=store_protobuf;cached_encoding<=store_encoding;cached_state<=store_state;state<=CORE_START;
                            end else if(store_status==3)begin
                                error_status<=13;error_detail<=8'h43;error_memory<=0;error_stream<=held_stream;error_application<=0;error_generation<=0;held_valid<=0;state<=RPC_ERROR;
                            end else begin fatal_store;held_valid<=0;state<=READY;end
                        end
                        A_SAVE,A_CLOSE_RPC:begin if(store_status!=0)begin fatal_store;rpc_pending<=0;end state<=ACK_CORE;end
                        A_RETIRE_FIND:begin
                            if(store_status==3)begin retire_needed<=0;state<=result_delivered?READY:PACKET_RESULT;end
                            else if(store_status==0)begin
                                r_op<=3;r_user<=owner;r_stream<=store_stream;r_generation<=store_generation;r_address<=store_address;r_state<=0;action<=A_RETIRE_CLOSE;state<=STORE_REQ;
                            end else begin fatal_store;state<=result_delivered?RECOVERY:PACKET_RESULT;end
                        end
                        A_RETIRE_CLOSE:begin if(store_status==0)retire_search;else begin fatal_store;state<=result_delivered?RECOVERY:PACKET_RESULT;end end
                        default:begin fatal_store;state<=READY;end
                    endcase
                end
                CORE_START:if(core_start_ready)begin cache_active<=1;state<=FEED;end
                FEED:if(core_ready)begin held_valid<=0;state<=READY;end
                FLUSH:if(core_result_valid)begin
                    if(core_status!=0&&!packet_fatal)begin
                        error_status<=core_status;error_detail<=core_detail;error_memory<=core_memory;error_stream<=cached_stream;error_application<=cached_application;error_generation<=cached_generation;rpc_pending<=1;persist(1'b1);
                    end else if(packet_fatal)begin rpc_pending<=0;state<=ACK_CORE;end
                    else begin rpc_pending<=0;persist(1'b0);end
                end
                ACK_CORE:if(core_result_valid)begin cache_active<=0;if(rpc_pending&&!packet_fatal)state<=RPC_ERROR;else continue_work;end
                RPC_ERROR:if(rpc_error_ready)begin rpc_pending<=0;continue_work;end
                CONTROL_RESULT:if(control_result_ready)begin
                    if(retire_needed)begin
                        if(!control_rejected&&store_status==0&&!stream_recovery_required&&!queue_recovery_required)retire_search;else state<=RECOVERY;
                    end else state<=READY;
                end
                PREPARE_WAIT:if(!descriptor_valid&&queue_finish_ready)begin prep_failed<=packet_fatal||queue_failed;prep_status<=status;state<=PREPARED;end
                PREPARED:if(prepared_ready)state<=DECISION;
                DECISION:if(decision_valid&&decision_ready)state<=QUEUE_RESULT;
                QUEUE_RESULT:if(queue_result_valid)begin
                    packet_active<=0;committed<=queue_committed&&!packet_fatal;
                    if(status==0)begin status<=queue_status;detail<=queue_detail;memory_status<=queue_memory;end
                    if(queue_committed&&!packet_fatal)state<=PACKET_RESULT;
                    else begin retire_needed<=1;if(stream_recovery_required)state<=PACKET_RESULT;else retire_search;end
                end
                PACKET_RESULT:if(packet_result_ready)begin result_delivered<=1;state<=retire_needed?RECOVERY:READY;end
                default:state<=READY;
            endcase
        end
    end
endmodule
`default_nettype wire
