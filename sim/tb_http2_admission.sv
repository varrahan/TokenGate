`timescale 1ns/1ps
module tb_http2_admission;
    localparam integer MEMORY_ADDR_WIDTH=23,USER_WIDTH=16;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic  reset_valid=0;
    wire  reset_ready;
    logic [USER_WIDTH-1:0] reset_user=0;
    logic  maintenance_grant=0;
    logic  begin_valid=0;
    wire  begin_ready;
    logic [USER_WIDTH-1:0] begin_user=0;
    logic [30:0] begin_stream=0;
    logic  begin_end_stream=0;
    logic  admit_new=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_context_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_payload_base=0;
    logic [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_context_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_payload_bytes=0;
    logic [MEMORY_ADDR_WIDTH:0] cfg_payload_slot_bytes=0;
    logic [31:0] cfg_model_epoch=0;
    logic [31:0] cfg_schema_epoch=0;
    wire  context_valid;
    logic  context_ready=0;
    wire [USER_WIDTH-1:0] context_user;
    wire [30:0] context_stream;
    wire  context_trailers;
    wire  context_end_stream;
    wire [22:0] context_scratch_base;wire [23:0] context_scratch_bytes;
    logic  candidate_valid=0;
    wire  candidate_ready;
    logic [2:0] candidate_status=0;
    logic [9:0] candidate_http_status=0;
    logic [USER_WIDTH-1:0] candidate_user=0;
    logic [30:0] candidate_stream=0;
    logic  candidate_end_stream=0;
    logic  candidate_admissible=0;
    logic [15:0] candidate_application=0;
    logic [1:0] candidate_format=0;
    logic  candidate_identity_encoding=0;
    logic [31:0] candidate_message_limit=0;
    logic [31:0] candidate_model_epoch=0;
    logic [31:0] candidate_schema_epoch=0;
    logic [31:0] candidate_route_entry=0;
    logic  candidate_length_valid=0;
    logic [63:0] candidate_content_length=0;
    logic  candidate_timeout_valid=0;
    logic [26:0] candidate_timeout_value=0;
    logic [2:0] candidate_timeout_unit=0;
    wire  result_valid;
    logic  result_ready=0;
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
    wire  mem_valid;
    wire  mem_ready;
    wire  mem_write;
    wire [MEMORY_ADDR_WIDTH-1:0] mem_addr;
    wire [3:0] mem_bytes;
    wire [71:0] mem_data;
    wire  mem_rsp_valid;
    wire  mem_rsp_ready;
    wire [71:0] mem_rsp_data;
    wire [7:0] mem_rsp_status;
    wire  idle;
    http2_rpc_admission dut(.*);
    wire [MEMORY_ADDR_WIDTH-1:0] eng_cfg_stream_base;
    wire [MEMORY_ADDR_WIDTH:0] eng_cfg_stream_bytes;
    logic  eng_queue_cfg_valid=0;
    wire  eng_queue_cfg_ready;
    logic  eng_queue_cfg_clear=0;
    logic  eng_maintenance_grant=0;
    logic [MEMORY_ADDR_WIDTH-1:0] eng_queue_cfg_base=0;
    logic [MEMORY_ADDR_WIDTH:0] eng_queue_cfg_bytes=0;
    wire  eng_queue_cfg_result_valid;
    logic  eng_queue_cfg_result_ready=0;
    wire [7:0] eng_queue_cfg_status;
    wire  eng_control_valid;
    wire  eng_control_ready;
    wire [2:0] eng_control_op;
    wire [USER_WIDTH-1:0] eng_control_user;
    wire [USER_WIDTH-1:0] eng_control_application;
    wire [30:0] eng_control_stream;
    wire [31:0] eng_control_generation;
    wire [MEMORY_ADDR_WIDTH-1:0] eng_control_address;
    wire [MEMORY_ADDR_WIDTH-1:0] eng_control_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] eng_control_buffer_bytes;
    wire [31:0] eng_control_message_limit;
    wire  eng_control_protobuf;
    wire  eng_control_unsupported_encoding;
    wire  eng_control_maintenance;
    wire  eng_control_result_valid;
    wire  eng_control_result_ready;
    wire [7:0] eng_control_status;
    wire [7:0] eng_control_detail;
    wire [7:0] eng_control_memory_status;
    wire [2:0] eng_control_result_op;
    wire [MEMORY_ADDR_WIDTH-1:0] eng_control_result_address;
    wire [MEMORY_ADDR_WIDTH-1:0] eng_control_result_buffer_base;
    wire [MEMORY_ADDR_WIDTH:0] eng_control_result_buffer_bytes;
    wire [USER_WIDTH-1:0] eng_control_result_user;
    wire [USER_WIDTH-1:0] eng_control_result_application;
    wire [30:0] eng_control_result_stream;
    wire [31:0] eng_control_result_generation;
    wire [31:0] eng_control_result_message_limit;
    wire  eng_control_result_protobuf;
    wire  eng_control_result_unsupported_encoding;
    wire [255:0] eng_control_result_state;
    logic  eng_packet_start_valid=0;
    wire  eng_packet_start_ready;
    logic [USER_WIDTH-1:0] eng_packet_start_user=0;
    logic [31:0] eng_packet_start_tag=0;
    logic  eng_s_valid=0;
    wire  eng_s_ready;
    logic [1:0] eng_s_kind=0;
    logic [7:0] eng_s_data=0;
    logic [30:0] eng_s_stream=0;
    logic  eng_prepare_valid=0;
    wire  eng_prepare_ready;
    wire  eng_prepared_valid;
    logic  eng_prepared_ready=0;
    wire  eng_prepared_failed;
    wire [7:0] eng_prepared_status;
    logic  eng_decision_valid=0;
    wire  eng_decision_ready;
    logic  eng_decision_commit=0;
    wire  eng_packet_result_valid;
    logic  eng_packet_result_ready=0;
    wire  eng_packet_committed;
    wire [7:0] eng_packet_status;
    wire [7:0] eng_packet_detail;
    wire [7:0] eng_packet_memory_status;
    wire [USER_WIDTH-1:0] eng_packet_user;
    wire [31:0] eng_packet_tag;
    wire  eng_rpc_error_valid;
    logic  eng_rpc_error_ready=0;
    wire [7:0] eng_rpc_error_status;
    wire [7:0] eng_rpc_error_detail;
    wire [7:0] eng_rpc_error_memory_status;
    wire [USER_WIDTH-1:0] eng_rpc_error_user;
    wire [USER_WIDTH-1:0] eng_rpc_error_application;
    wire [30:0] eng_rpc_error_stream;
    wire [31:0] eng_rpc_error_generation;
    wire [31:0] eng_rpc_error_packet_tag;
    wire  eng_m_valid;
    logic  eng_m_ready=0;
    wire [USER_WIDTH-1:0] eng_m_user;
    wire [USER_WIDTH-1:0] eng_m_application;
    wire [30:0] eng_m_stream;
    wire  eng_m_protobuf;
    wire [MEMORY_ADDR_WIDTH-1:0] eng_m_base;
    wire [31:0] eng_m_bytes;
    wire [31:0] eng_m_ordinal;
    wire [31:0] eng_m_generation;
    wire [31:0] eng_m_packet_tag;
    wire  eng_stream_recovery_required;
    wire [MEMORY_ADDR_WIDTH-1:0] eng_stream_recovery_address;
    wire  eng_queue_recovery_required;
    wire [7:0] eng_queue_recovery_detail;
    wire [7:0] eng_queue_recovery_memory_status;
    wire  eng_retirement_pending;
    wire [31:0] eng_queued_count;
    wire [31:0] eng_pending_count;
    wire  eng_idle;
    wire [3:0] eng_mem_valid;
    wire [3:0] eng_mem_ready;
    wire [3:0] eng_mem_write;
    wire [4*MEMORY_ADDR_WIDTH-1:0] eng_mem_addr;
    wire [15:0] eng_mem_bytes;
    wire [287:0] eng_mem_data;
    wire [3:0] eng_mem_rsp_valid;
    wire [3:0] eng_mem_rsp_ready;
    wire [287:0] eng_mem_rsp_data;
    wire [31:0] eng_mem_rsp_status;
    logic ext_valid=0,ext_rsp_ready=0,ext_owner=0;
    logic [2:0] ext_op=0;logic [15:0] ext_user=0;logic [30:0] ext_stream=0;logic [31:0] ext_generation=0;logic [22:0] ext_address=0;
    wire ext_active=ext_valid&&idle&&!ext_owner;
    assign eng_control_valid=control_valid||ext_active;
    assign control_ready=eng_control_ready&&!ext_active;
    assign eng_control_result_ready=ext_owner?ext_rsp_ready:control_result_ready;
    assign control_result_valid=eng_control_result_valid&&!ext_owner;
    assign eng_cfg_stream_base=23'h780003;assign eng_cfg_stream_bytes=24'd384;
    assign eng_control_op=ext_active?ext_op:control_op;
    assign eng_control_user=ext_active?ext_user:control_user;
    assign eng_control_stream=ext_active?ext_stream:control_stream;
    assign eng_control_generation=ext_active?ext_generation:control_generation;
    assign eng_control_address=ext_active?ext_address:control_address;
    assign eng_control_application=ext_active?16'd0:control_application;
    assign eng_control_buffer_base=ext_active?23'd0:control_buffer_base;
    assign eng_control_buffer_bytes=ext_active?24'd0:control_buffer_bytes;
    assign eng_control_message_limit=ext_active?32'd0:control_message_limit;
    assign eng_control_protobuf=ext_active?1'b0:control_protobuf;
    assign eng_control_unsupported_encoding=ext_active?1'b0:control_unsupported_encoding;
    assign eng_control_maintenance=ext_active?1'b1:control_maintenance;
    assign control_result_address=eng_control_result_address;
    assign control_result_buffer_base=eng_control_result_buffer_base;
    assign control_result_buffer_bytes=eng_control_result_buffer_bytes;
    assign control_result_application=eng_control_result_application;
    assign control_result_generation=eng_control_result_generation;
    assign control_result_message_limit=eng_control_result_message_limit;
    assign control_result_protobuf=eng_control_result_protobuf;
    assign control_result_unsupported_encoding=eng_control_result_unsupported_encoding;
    assign control_result_state=eng_control_result_state;
    assign control_status=eng_control_status;assign control_memory_status=eng_control_memory_status;
    grpc_ingress_engine engine(
        .clk(clk),
        .rst(rst),
        .cfg_stream_base(eng_cfg_stream_base),
        .cfg_stream_bytes(eng_cfg_stream_bytes),
        .queue_cfg_valid(eng_queue_cfg_valid),
        .queue_cfg_ready(eng_queue_cfg_ready),
        .queue_cfg_clear(eng_queue_cfg_clear),
        .maintenance_grant(eng_maintenance_grant),
        .queue_cfg_base(eng_queue_cfg_base),
        .queue_cfg_bytes(eng_queue_cfg_bytes),
        .queue_cfg_result_valid(eng_queue_cfg_result_valid),
        .queue_cfg_result_ready(eng_queue_cfg_result_ready),
        .queue_cfg_status(eng_queue_cfg_status),
        .control_valid(eng_control_valid),
        .control_ready(eng_control_ready),
        .control_op(eng_control_op),
        .control_user(eng_control_user),
        .control_application(eng_control_application),
        .control_stream(eng_control_stream),
        .control_generation(eng_control_generation),
        .control_address(eng_control_address),
        .control_buffer_base(eng_control_buffer_base),
        .control_buffer_bytes(eng_control_buffer_bytes),
        .control_message_limit(eng_control_message_limit),
        .control_protobuf(eng_control_protobuf),
        .control_unsupported_encoding(eng_control_unsupported_encoding),
        .control_maintenance(eng_control_maintenance),
        .control_result_valid(eng_control_result_valid),
        .control_result_ready(eng_control_result_ready),
        .control_status(eng_control_status),
        .control_detail(eng_control_detail),
        .control_memory_status(eng_control_memory_status),
        .control_result_op(eng_control_result_op),
        .control_result_address(eng_control_result_address),
        .control_result_buffer_base(eng_control_result_buffer_base),
        .control_result_buffer_bytes(eng_control_result_buffer_bytes),
        .control_result_user(eng_control_result_user),
        .control_result_application(eng_control_result_application),
        .control_result_stream(eng_control_result_stream),
        .control_result_generation(eng_control_result_generation),
        .control_result_message_limit(eng_control_result_message_limit),
        .control_result_protobuf(eng_control_result_protobuf),
        .control_result_unsupported_encoding(eng_control_result_unsupported_encoding),
        .control_result_state(eng_control_result_state),
        .packet_start_valid(eng_packet_start_valid),
        .packet_start_ready(eng_packet_start_ready),
        .packet_start_user(eng_packet_start_user),
        .packet_start_tag(eng_packet_start_tag),
        .s_valid(eng_s_valid),
        .s_ready(eng_s_ready),
        .s_kind(eng_s_kind),
        .s_data(eng_s_data),
        .s_stream(eng_s_stream),
        .prepare_valid(eng_prepare_valid),
        .prepare_ready(eng_prepare_ready),
        .prepared_valid(eng_prepared_valid),
        .prepared_ready(eng_prepared_ready),
        .prepared_failed(eng_prepared_failed),
        .prepared_status(eng_prepared_status),
        .decision_valid(eng_decision_valid),
        .decision_ready(eng_decision_ready),
        .decision_commit(eng_decision_commit),
        .packet_result_valid(eng_packet_result_valid),
        .packet_result_ready(eng_packet_result_ready),
        .packet_committed(eng_packet_committed),
        .packet_status(eng_packet_status),
        .packet_detail(eng_packet_detail),
        .packet_memory_status(eng_packet_memory_status),
        .packet_user(eng_packet_user),
        .packet_tag(eng_packet_tag),
        .rpc_error_valid(eng_rpc_error_valid),
        .rpc_error_ready(eng_rpc_error_ready),
        .rpc_error_status(eng_rpc_error_status),
        .rpc_error_detail(eng_rpc_error_detail),
        .rpc_error_memory_status(eng_rpc_error_memory_status),
        .rpc_error_user(eng_rpc_error_user),
        .rpc_error_application(eng_rpc_error_application),
        .rpc_error_stream(eng_rpc_error_stream),
        .rpc_error_generation(eng_rpc_error_generation),
        .rpc_error_packet_tag(eng_rpc_error_packet_tag),
        .m_valid(eng_m_valid),
        .m_ready(eng_m_ready),
        .m_user(eng_m_user),
        .m_application(eng_m_application),
        .m_stream(eng_m_stream),
        .m_protobuf(eng_m_protobuf),
        .m_base(eng_m_base),
        .m_bytes(eng_m_bytes),
        .m_ordinal(eng_m_ordinal),
        .m_generation(eng_m_generation),
        .m_packet_tag(eng_m_packet_tag),
        .stream_recovery_required(eng_stream_recovery_required),
        .stream_recovery_address(eng_stream_recovery_address),
        .queue_recovery_required(eng_queue_recovery_required),
        .queue_recovery_detail(eng_queue_recovery_detail),
        .queue_recovery_memory_status(eng_queue_recovery_memory_status),
        .retirement_pending(eng_retirement_pending),
        .queued_count(eng_queued_count),
        .pending_count(eng_pending_count),
        .idle(eng_idle),
        .mem_valid(eng_mem_valid),
        .mem_ready(eng_mem_ready),
        .mem_write(eng_mem_write),
        .mem_addr(eng_mem_addr),
        .mem_bytes(eng_mem_bytes),
        .mem_data(eng_mem_data),
        .mem_rsp_valid(eng_mem_rsp_valid),
        .mem_rsp_ready(eng_mem_rsp_ready),
        .mem_rsp_data(eng_mem_rsp_data),
        .mem_rsp_status(eng_mem_rsp_status)
    );
    always @(posedge clk)if(!rst)begin
        if(ext_active&&eng_control_ready)ext_owner<=1;
        if(ext_owner&&eng_control_result_valid&&ext_rsp_ready)ext_owner<=0;
    end
    wire [5:0] cmd_valid,cmd_ready,cmd_write,response_valid,response_ready;wire [137:0] cmd_addr;wire [23:0] cmd_bytes;
    wire [431:0] cmd_data,response_data;wire [47:0] response_status;
    logic helper_valid=0,helper_ready=0,helper_write=0;logic [22:0] helper_addr=0;logic [3:0] helper_bytes=0;logic [71:0] helper_data=0;
    integer fault_target=-1,store_fault_target=-1,response_count=0,store_response_count=0;bit injected=0,store_injected=0;
    assign cmd_valid={helper_valid,eng_mem_valid,mem_valid};assign cmd_write={helper_write,eng_mem_write,mem_write};
    assign cmd_addr={helper_addr,eng_mem_addr,mem_addr};assign cmd_bytes={helper_bytes,eng_mem_bytes,mem_bytes};assign cmd_data={helper_data,eng_mem_data,mem_data};
    assign mem_ready=cmd_ready[0];assign mem_rsp_valid=response_valid[0];assign mem_rsp_data=response_data[0+:72];
    assign mem_rsp_status=!injected&&response_count==fault_target?8'h91:response_status[0+:8];
    assign eng_mem_ready=cmd_ready[4:1];assign eng_mem_rsp_valid=response_valid[4:1];assign eng_mem_rsp_data=response_data[72+:288];
    assign eng_mem_rsp_status={response_status[16+:24],!store_injected&&store_response_count==store_fault_target?8'h82:response_status[8+:8]};
    assign response_ready={helper_ready,eng_mem_rsp_ready,mem_rsp_ready};
    wire [22:0] araddr,awaddr;wire [7:0] arlen,awlen,wstrb;wire [2:0] arsize,awsize;wire [1:0] arburst,awburst,rresp,bresp;
    wire arvalid,arready,rvalid,rready,rlast,awvalid,awready,wvalid,wready,wlast,bvalid,bready,fabric_idle;wire [63:0] rdata,wdata;
    external_memory_fabric #(.CLIENTS(6)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),.s_valid(cmd_valid),.s_ready(cmd_ready),.s_write(cmd_write),.s_addr(cmd_addr),.s_bytes(cmd_bytes),.s_data(cmd_data),
        .rsp_valid(response_valid),.rsp_ready(response_ready),.rsp_data(response_data),.rsp_status(response_status),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arvalid(arvalid),.m_axi_arready(arready),
        .m_axi_rdata(rdata),.m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready),
        .m_axi_awaddr(awaddr),.m_axi_awlen(awlen),.m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),.m_axi_wvalid(wvalid),.m_axi_wready(wready),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),.m_axi_bready(bready),.idle(fabric_idle));
    axi_external_memory_model #(.INIT_FILE("")) memory_model(
        .clk(clk),.rst(rst),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready),
        .awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),.wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
        .bresp(bresp),.bvalid(bvalid),.bready(bready),.read_fault(1'b0),.fault_line(23'd0),.write_fault(1'b0));
    integer headers=0,accepted=0,rejected=0,resets=0,packets=0,descriptors=0,read_bytes=0,quarantines=0,control_count=0;
    integer expected_last_generation=0;reg [31:0] last_generation;reg [22:0] last_address,last_buffer;reg [7:0] last_detail;
    bit epoch_error=0,identity_error=0,disable_new=0;integer arena_bytes=384;
    bit context_stalled=0,result_stalled=0;bit [5:0] cmd_stalled=0;reg [511:0] held_result;reg [110:0] held_context;reg [99:0] held_command[0:5];
    wire [110:0] context_bundle={context_user,context_stream,context_trailers,context_end_stream,context_scratch_base,context_scratch_bytes};
    wire [511:0] result_bundle={result_is_reset,result_trailers,result_end_stream,result_status,result_detail,result_memory_status,result_control_status,result_cleanup_status,
        result_connection_error,result_http2_error,result_http_status,result_grpc_status,result_user,result_stream,result_application,result_generation,result_model_epoch,result_schema_epoch,
        result_address,result_buffer_base,result_buffer_bytes,result_protobuf,result_unsupported_encoding};
    always @(posedge clk)if(!rst)begin
        if(context_stalled&&(!context_valid||held_context!==context_bundle))$fatal(1,"Admission context unstable");
        context_stalled=context_valid&&!context_ready;held_context=context_bundle;
        if(result_stalled&&(!result_valid||held_result!==result_bundle))$fatal(1,"Admission result unstable");
        result_stalled=result_valid&&!result_ready;held_result=result_bundle;
        if((^{reset_ready,begin_ready,context_valid,candidate_ready,result_valid,control_valid,mem_valid})===1'bx)$fatal(1,"Unknown admission handshake");
        if(result_valid&&((^result_bundle)===1'bx)||context_valid&&((^context_bundle)===1'bx))$fatal(1,"Unknown admission metadata");
        if(result_valid&&(control_valid||mem_valid||begin_ready||reset_ready))$fatal(1,"Held admission result leaked work");
        if(mem_rsp_valid&&mem_rsp_ready)begin if(mem_rsp_status==8'h91)injected<=1;response_count<=response_count+1;end
        if(eng_mem_rsp_valid[0]&&eng_mem_rsp_ready[0])begin if(eng_mem_rsp_status[0+:8]==8'h82)store_injected<=1;store_response_count<=store_response_count+1;end
        if(control_valid&&control_ready)control_count++;
        if(eng_rpc_error_valid)$fatal(1,"Unexpected gRPC decoder error %0d/%0d",eng_rpc_error_status,eng_rpc_error_detail);
        for(integer c=0;c<6;c++)begin
            if(cmd_stalled[c]&&(!cmd_valid[c]||held_command[c]!=={cmd_write[c],cmd_addr[c*23+:23],cmd_bytes[c*4+:4],cmd_data[c*72+:72]}))$fatal(1,"Admission fabric command unstable");
            cmd_stalled[c]=cmd_valid[c]&&!cmd_ready[c];held_command[c]={cmd_write[c],cmd_addr[c*23+:23],cmd_bytes[c*4+:4],cmd_data[c*72+:72]};
            if(cmd_valid[c]&&((^held_command[c])===1'bx))$fatal(1,"Unknown admission memory command");
            if(cmd_valid[c]&&cmd_write[c]&&cmd_addr[c*23+:23]<23'h695700)$fatal(1,"Model region modified by admission test");
        end
        if(mem_valid&&mem_write&&!((mem_addr>=23'h780043&&mem_addr<23'h780183)||mem_addr==23'h7c00a3||mem_addr==23'h7c01a3||mem_addr==23'h7c02a3))$fatal(1,"Admission wrote outside its owned metadata");
    end
    task configuration;
        begin cfg_context_base=23'h7c0003;cfg_context_bytes=768;cfg_stream_base=23'h780003;cfg_stream_bytes=384;
            cfg_payload_base=23'h700003;cfg_payload_bytes=24'(arena_bytes);cfg_payload_slot_bytes=128;cfg_work_floor=23'h695700;cfg_model_epoch=23;cfg_schema_epoch=9;admit_new=!disable_new;end
    endtask
    task poison_configuration;
        begin cfg_context_base='1;cfg_context_bytes=0;cfg_stream_base='1;cfg_stream_bytes=0;cfg_payload_base=0;cfg_payload_bytes=0;cfg_payload_slot_bytes=0;
            cfg_work_floor='1;cfg_model_epoch='1;cfg_schema_epoch='1;admit_new=disable_new;maintenance_grant=0;end
    endtask
    task helper(input bit write_kind,input integer address,input integer size,input [71:0] data,output reg [71:0] answer);
        begin @(negedge clk);helper_valid=1;helper_write=write_kind;helper_addr=23'(address);helper_bytes=4'(size);helper_data=data;
            do @(posedge clk);while(!cmd_ready[5]);@(negedge clk);helper_valid=0;helper_ready=1;
            do @(posedge clk);while(!response_valid[5]);if(response_status[40+:8]!=0)$fatal(1,"Admission helper failed");answer=response_data[360+:72];
            @(negedge clk);helper_ready=0;
        end
    endtask
    task external_control(input integer op,input integer user_id,input integer sid,input integer generation,input integer address,input integer expected_status);
        begin wait(idle);@(negedge clk);ext_op=3'(op);ext_user=16'(user_id);ext_stream=31'(sid);ext_generation=32'(generation);ext_address=23'(address);ext_valid=1;
            do @(posedge clk);while(!eng_control_ready);@(negedge clk);ext_valid=0;
            wait(ext_owner&&eng_control_result_valid);if(eng_control_status!=expected_status)$fatal(1,"External control op=%0d status=%0d/%0d",op,eng_control_status,expected_status);
            @(negedge clk);ext_rsp_ready=1;@(posedge clk);@(negedge clk);ext_rsp_ready=0;wait(!ext_owner);
        end
    endtask
    task acknowledge;
        begin repeat(20)@(negedge clk);result_ready=1;@(posedge clk);@(negedge clk);result_ready=0;wait(idle);end
    endtask
    task reset_connection(input integer user_id,input bit grant,input integer wanted);
        begin @(negedge clk);configuration();reset_user=16'(user_id);maintenance_grant=grant;reset_valid=1;
            do @(posedge clk);while(!reset_ready);@(negedge clk);reset_valid=0;poison_configuration();
            wait(result_valid);if(!result_is_reset||result_user!=user_id||result_status!=wanted)$fatal(1,"Connection metadata reset mismatch status=%0d/%0d detail=%0d",result_status,wanted,result_detail);
            acknowledge();resets++;
        end
    endtask
    task start_packet(input integer user_id);
        begin @(negedge clk);eng_packet_start_user=16'(user_id);eng_packet_start_tag=32'(100+packets);eng_packet_start_valid=1;
            do @(posedge clk);while(!eng_packet_start_ready);@(negedge clk);eng_packet_start_valid=0;
        end
    endtask
    task finish_packet(input bit commit);
        begin @(negedge clk);eng_prepare_valid=1;do @(posedge clk);while(!eng_prepare_ready);@(negedge clk);eng_prepare_valid=0;
            wait(eng_prepared_valid);if(eng_prepared_failed)$fatal(1,"Admission packet prepare failed");eng_prepared_ready=1;@(posedge clk);@(negedge clk);eng_prepared_ready=0;
            eng_decision_valid=1;eng_decision_commit=commit;do @(posedge clk);while(!eng_decision_ready);@(negedge clk);eng_decision_valid=0;
            wait(eng_packet_result_valid);if(eng_packet_committed!=commit)$fatal(1,"Admission packet publication mismatch");
            repeat(5)@(negedge clk);eng_packet_result_ready=1;@(posedge clk);@(negedge clk);eng_packet_result_ready=0;packets++;
        end
    endtask
    task header(input integer user_id,input integer sid,input bit end_flag,input integer app,input integer format,input integer hstatus,input bit admissible,input integer wanted,input bit wanted_trailer);
        begin
            @(negedge clk);configuration();begin_user=16'(user_id);begin_stream=31'(sid);begin_end_stream=end_flag;begin_valid=1;
            do @(posedge clk);while(!begin_ready);@(negedge clk);begin_valid=0;poison_configuration();
            wait(context_valid);repeat(8)@(negedge clk);
            if(context_user!=user_id||context_stream!=sid||context_end_stream!=end_flag||context_trailers!=wanted_trailer)$fatal(1,"Admission live-context mismatch sid=%0d trailer=%0d/%0d",sid,context_trailers,wanted_trailer);
            if(context_scratch_bytes!=0&&(context_scratch_base!=24'h720000+user_id*65536||context_scratch_bytes!=65536))$fatal(1,"Header scratch allocation was not restored from its connection record");
            context_ready=1;@(posedge clk);@(negedge clk);context_ready=0;
            candidate_user=16'(user_id^(identity_error?1:0));candidate_stream=31'(sid);candidate_end_stream=end_flag;
            candidate_status=3'(hstatus);candidate_http_status=hstatus==2?415:0;candidate_admissible=admissible;candidate_application=16'(app);candidate_format=2'(format);
            candidate_identity_encoding=1;candidate_message_limit=128;candidate_model_epoch=epoch_error?999:23;candidate_schema_epoch=9;candidate_route_entry=7;
            candidate_length_valid=0;candidate_content_length=0;candidate_timeout_valid=1;candidate_timeout_value=123;candidate_timeout_unit=3;candidate_valid=1;
            do @(posedge clk);while(!candidate_ready);@(negedge clk);candidate_valid=0;candidate_application='1;candidate_model_epoch='1;candidate_schema_epoch='1;candidate_message_limit=0;
            wait(result_valid);
            if(result_is_reset||result_status!=wanted||result_user!=user_id||result_stream!=sid||result_trailers!=wanted_trailer||result_end_stream!=end_flag)
                $fatal(1,"Admission header sid=%0d status=%0d/%0d detail=%0d control=%0d cleanup=%0d",sid,result_status,wanted,result_detail,result_control_status,result_cleanup_status);
            if(wanted==0)begin
                if(result_generation==0||result_model_epoch!=23||result_schema_epoch!=9||result_buffer_bytes!=128)$fatal(1,"Bad admitted binding");
                if(!wanted_trailer&&result_generation<=expected_last_generation)$fatal(1,"RPC generation reused");
                if(!wanted_trailer)begin expected_last_generation=result_generation;if(result_application!=app||result_protobuf!=(format==0))$fatal(1,"Route binding changed");end
                last_generation=result_generation;last_address=result_address;last_buffer=result_buffer_base;accepted++;
            end else begin
                if({result_generation,result_application,result_address,result_buffer_base,result_buffer_bytes,result_model_epoch,result_schema_epoch,result_protobuf,result_unsupported_encoding}!==185'd0)$fatal(1,"Rejected candidate released authority");
                rejected++;
            end
            last_detail=result_detail;acknowledge();headers++;
        end
    endtask
    task data_event(input integer kind,input integer byte_value,input integer sid);
        begin @(negedge clk);eng_s_valid=1;eng_s_kind=2'(kind);eng_s_data=8'(byte_value);eng_s_stream=31'(sid);
            do @(posedge clk);while(!eng_s_ready);@(negedge clk);eng_s_valid=0;
        end
    endtask
    task message(input integer sid,input string payload_value,input bit end_flag);
        begin data_event(0,0,sid);for(integer shift=3;shift>=0;shift--)data_event(0,(payload_value.len()>>(shift*8))&255,sid);
            for(integer i=0;i<payload_value.len();i++)data_event(0,payload_value[i],sid);if(end_flag)data_event(1,0,sid);
        end
    endtask
    task take_message(input integer user_id,input integer sid,input integer app,input bit protobuf,input integer generation,input integer base,input integer tag,input string bytes_value);
        reg [71:0] answer;
        begin wait(eng_m_valid);repeat(25)@(negedge clk);
            if(eng_m_user!=user_id||eng_m_stream!=sid||eng_m_application!=app||eng_m_protobuf!=protobuf||eng_m_generation!=generation||eng_m_base!=base||eng_m_bytes!=bytes_value.len()||eng_m_ordinal!=0||eng_m_packet_tag!=tag)$fatal(1,"Automatically admitted descriptor mismatch");
            for(integer i=0;i<bytes_value.len();i++)begin helper(0,base+i,1,0,answer);if(answer[7:0]!==bytes_value[i])$fatal(1,"Admitted payload mismatch");read_bytes++;end
            eng_m_ready=1;@(posedge clk);@(negedge clk);eng_m_ready=0;descriptors++;
        end
    endtask
    task fault_setup(input integer target,input integer store_target);
        begin @(negedge clk);fault_target=target;store_fault_target=store_target;response_count=0;store_response_count=0;injected=0;store_injected=0;end
    endtask
    initial begin:driver
        integer g1,g3,a1,a3,b1,b3,saved_gen,saved_address,corrupt_offset;reg [71:0] answer,corrupt_mask;
        repeat(5)@(negedge clk);rst=0;eng_rpc_error_ready=1;
        eng_queue_cfg_base=23'h7f0003;eng_queue_cfg_bytes=512;eng_queue_cfg_valid=1;
        do @(posedge clk);while(!eng_queue_cfg_ready);@(negedge clk);eng_queue_cfg_valid=0;wait(eng_queue_cfg_result_valid);
        if(eng_queue_cfg_status!=0)$fatal(1,"Queue configuration failed");eng_queue_cfg_result_ready=1;@(posedge clk);@(negedge clk);eng_queue_cfg_result_ready=0;
        external_control(4,0,0,0,0,0);
        for(integer u=0;u<3;u++)helper(1,24'h7c0003+u*256+80,8,{8'd0,32'd65536,32'(24'h720000+u*65536)},answer);
        reset_connection(0,0,5);for(integer u=0;u<3;u++)reset_connection(u,1,0);
        start_packet(0);header(0,1,0,17,1,0,1,0,0);g1=last_generation;a1=last_address;b1=last_buffer;
        if(a1!=24'h780003||b1!=24'h700003)$fatal(1,"First arena slot mismatch");
        helper(0,a1+64,8,0,answer);if(answer[31:0]!=32'h48325231||answer[63:32]!=g1)$fatal(1,"RPC sidecar identity missing");
        helper(0,a1+72,8,0,answer);if(answer[63:0]!={32'd9,32'd23})$fatal(1,"RPC epochs missing");
        message(1,"{\"prompt\":\"hello\"}",0);if(eng_m_valid)$fatal(1,"Uncommitted admission published a descriptor");finish_packet(1);
        start_packet(0);header(0,3,0,18,0,0,1,0,0);g3=last_generation;a3=last_address;b3=last_buffer;
        if(a3!=a1+128||b3!=b1+128)$fatal(1,"Live RPC buffer overwritten");message(3,"\012\003abc",1);finish_packet(1);
        start_packet(1);header(1,1,0,19,1,0,1,0,0);saved_gen=last_generation;saved_address=last_address;finish_packet(1);
        reset_connection(0,1,5);
        start_packet(0);header(0,5,0,20,1,0,1,4,0);finish_packet(1);
        external_control(3,1,1,saved_gen,saved_address,0);
        start_packet(0);header(0,5,0,20,1,0,1,2,0);header(0,7,0,20,1,0,1,0,0);saved_gen=last_generation;saved_address=last_address;finish_packet(1);
        external_control(3,0,7,saved_gen,saved_address,0);
        take_message(0,1,17,0,g1,b1,100,"{\"prompt\":\"hello\"}");take_message(0,3,18,1,g3,b3,101,"\012\003abc");
        start_packet(0);header(0,1,1,0,0,0,1,0,1);if(last_generation!=g1||last_buffer!=b1)$fatal(1,"Trailer changed original RPC binding");data_event(1,0,1);finish_packet(1);
        start_packet(0);header(0,1,1,0,0,0,1,2,1);finish_packet(1);
        start_packet(0);header(0,9,0,17,1,1,1,3,0);header(0,11,0,17,1,0,0,3,0);finish_packet(1);
        epoch_error=1;start_packet(0);header(0,13,0,17,1,0,1,4,0);finish_packet(1);epoch_error=0;
        disable_new=1;start_packet(0);header(0,15,0,17,1,0,1,4,0);finish_packet(1);disable_new=0;
        identity_error=1;start_packet(0);header(0,17,0,17,1,0,1,5,0);finish_packet(0);identity_error=0;reset_connection(0,1,0);
        // Every sidecar write acknowledgement, plus high-water read/write and
        // free-slot read. Each error must close tentative OPEN and quarantine.
        for(integer target=0;target<12;target++)begin
            start_packet(0);fault_setup(target,-1);header(0,1,0,17,1,0,1,5,0);
            if(!injected||!recovery_required||recovery_user!=0)$fatal(1,"Admission fault not contained target=%0d",target);
            finish_packet(0);fault_setup(-1,-1);reset_connection(0,1,0);if(recovery_required)$fatal(1,"Exact connection recovery failed");quarantines++;
        end
        // Sidecar corruption must not change the route, generation or model.
        for(integer offset=0;offset<5;offset++)begin
            start_packet(0);header(0,1,0,17,1,0,1,0,0);saved_address=last_address;finish_packet(1);
            case(offset)
                0:begin corrupt_offset=0;corrupt_mask=1;end
                1:begin corrupt_offset=8;corrupt_mask=1;end
                2:begin corrupt_offset=8;corrupt_mask=72'd1<<32;end
                3:begin corrupt_offset=48;corrupt_mask=72'd1<<48;end
                default:begin corrupt_offset=56;corrupt_mask=72'd1<<63;end
            endcase
            helper(0,saved_address+64+corrupt_offset,8,0,answer);helper(1,saved_address+64+corrupt_offset,8,answer^corrupt_mask,answer);
            start_packet(0);header(0,1,1,0,0,0,1,5,1);finish_packet(0);
            if(!recovery_required)$fatal(1,"Corrupt binding not quarantined");quarantines++;
            reset_connection(0,1,0);
        end
        for(integer word_index=0;word_index<8;word_index++)begin
            start_packet(0);header(0,1,0,17,1,0,1,0,0);saved_address=last_address;finish_packet(1);
            start_packet(0);fault_setup(2+word_index,-1);header(0,1,1,0,0,0,1,5,1);
            if(!injected||recovery_address!=saved_address+64+word_index*8)$fatal(1,"Sidecar read failure not contained");
            finish_packet(0);fault_setup(-1,-1);reset_connection(0,1,0);quarantines++;
        end
        start_packet(0);header(0,2,0,17,1,0,1,1,0);finish_packet(0);reset_connection(0,1,0);
        // A shorter arena cannot wrap the scan pointer or allocate a later
        // free record over an existing payload/model region.
        start_packet(1);header(1,3,0,18,1,0,1,0,0);saved_gen=last_generation;saved_address=last_address;finish_packet(1);
        arena_bytes=128;start_packet(0);header(0,1,0,17,1,0,1,4,0);finish_packet(1);arena_bytes=384;
        external_control(3,1,3,saved_gen,saved_address,0);reset_connection(0,1,0);
        // A failed directory OPEN may have an uncertain marker. The real
        // directory's exact RECOVER must finish before connection reuse.
        start_packet(0);fault_setup(-1,6);header(0,1,0,17,1,0,1,5,0);
        if(!store_injected||!eng_stream_recovery_required)$fatal(1,"Failed OPEN did not quarantine the actual directory");
        finish_packet(0);fault_setup(-1,-1);external_control(5,0,0,0,eng_stream_recovery_address,0);
        wait(!eng_retirement_pending&&!eng_stream_recovery_required);reset_connection(0,1,0);
        // Fail sidecar creation and the rollback's first directory read.
        // Both independent recovery conditions must remain observable.
        start_packet(0);fault_setup(4,15);header(0,1,0,17,1,0,1,5,0);
        if(!store_injected||!injected||!recovery_required||!eng_stream_recovery_required||result_cleanup_status!=2)$fatal(1,"Rollback failure was hidden");
        finish_packet(0);fault_setup(-1,-1);external_control(5,0,0,0,eng_stream_recovery_address,0);
        wait(!eng_retirement_pending&&!eng_stream_recovery_required);reset_connection(0,1,0);quarantines++;
        // An uncertain reset write cannot clear quarantine, nor can a grant
        // for a different connection or a revoked grant authorize recovery.
        fault_setup(0,-1);reset_connection(0,1,5);
        if(!injected||!recovery_required||recovery_user!=0||recovery_address!=23'h7c00a3)$fatal(1,"Failed reset lost its exact recovery identity");
        fault_setup(-1,-1);start_packet(1);header(1,5,0,17,1,0,1,5,0);finish_packet(0);
        reset_connection(1,1,5);reset_connection(0,0,5);
        if(!recovery_required||recovery_user!=0)$fatal(1,"Wrong recovery cleared quarantine");
        reset_connection(0,1,0);if(recovery_required)$fatal(1,"Authorized exact recovery failed");quarantines++;
        wait(idle&&fabric_idle);
        if(headers<57||accepted<19||rejected<38||quarantines<27||descriptors!=2||read_bytes<20)$fatal(1,"Insufficient RPC admission coverage");
        $display("PASS: phased HTTP/2 RPC admission -> actual gRPC directory/deframer/queue: %0d headers/%0d admitted/%0d rejected/%0d connection resets/%0d packets/%0d exact descriptors/%0d payload bytes/%0d quarantines; inline OPEN, independent identities, arena ownership, monotonic streams, epochs, rollback and recovery",headers,accepted,rejected,resets,packets,descriptors,read_bytes,quarantines);$finish;
    end
    initial begin #(64'd2000000000);$fatal(1,"Admission timeout state=%0d engine=%0d headers=%0d packet=%0d control=%0d",dut.state,engine.state,headers,packets,control_count);end
endmodule
