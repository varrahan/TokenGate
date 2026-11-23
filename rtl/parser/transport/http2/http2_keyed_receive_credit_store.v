`timescale 1ns/1ps
`default_nettype none
// Generated actual runtime key lookup plus durable receive accounting.
// Parent holds connection/directory-pool authority until public result ACK.
// req_keyed resolves wire keys; address/generation must be zero on input.
module http2_keyed_receive_credit_store #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(
    input wire  clk,
    input wire  rst,
    input wire  req_valid,
    output wire  req_ready,
    input wire [3:0] req_op,
    input wire  req_authority,
    input wire  req_maintenance,
    input wire [USER_WIDTH-1:0] req_user,
    input wire [30:0] req_stream,
    input wire [31:0] req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_record_address,
    input wire [31:0] req_amount,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_rpc_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_receive_connection_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_receive_stream_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_rpc_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_receive_connection_bytes,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_receive_stream_bytes,
    input wire  context_write_busy,
    input wire [USER_WIDTH-1:0] context_write_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] context_write_address,
    input wire  context_write_fault,
    input wire [USER_WIDTH-1:0] context_write_fault_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] context_write_fault_address,
    input wire [7:0] context_write_fault_memory_status,
    output wire  rsp_valid,
    input wire  rsp_ready,
    output wire [3:0] rsp_op,
    output wire [USER_WIDTH-1:0] rsp_user,
    output wire [30:0] rsp_stream,
    output wire [7:0] rsp_status,
    output wire [7:0] rsp_detail,
    output wire [7:0] rsp_memory_status,
    output wire  rsp_connection_error,
    output wire [31:0] rsp_http2_error,
    output wire [31:0] rsp_connection_available,
    output wire [31:0] rsp_stream_available,
    output wire [31:0] rsp_connection_pending,
    output wire [31:0] rsp_stream_pending,
    output wire  rsp_debit_authorized,
    output wire  rsp_wire_retired,
    output wire [31:0] rsp_update_bytes,
    output wire  recovery_required,
    output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire [511:0] m_axis_tx_tdata,
    output wire [63:0] m_axis_tx_tkeep,
    output wire  m_axis_tx_tvalid,
    input wire  m_axis_tx_tready,
    output wire  m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire  mem_valid,
    input wire  mem_ready,
    output wire  mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,
    output wire [71:0] mem_data,
    input wire  mem_rsp_valid,
    output wire  mem_rsp_ready,
    input wire [71:0] mem_rsp_data,
    input wire [7:0] mem_rsp_status,
    output wire  idle,
    input wire  req_keyed,
    output wire  rsp_binding_valid,
    output wire [MEMORY_ADDR_WIDTH-1:0] rsp_record_address,
    output wire [31:0] rsp_generation
);
reg [3:0] held_req_op;
reg  held_req_authority;
reg  held_req_maintenance;
reg [USER_WIDTH-1:0] held_req_user;
reg [30:0] held_req_stream;
reg [31:0] held_req_generation;
reg [MEMORY_ADDR_WIDTH-1:0] held_req_record_address;
reg [31:0] held_req_amount;
reg [MEMORY_ADDR_WIDTH-1:0] held_cfg_context_base;
reg [MEMORY_ADDR_WIDTH-1:0] held_cfg_rpc_base;
reg [MEMORY_ADDR_WIDTH-1:0] held_cfg_receive_connection_base;
reg [MEMORY_ADDR_WIDTH-1:0] held_cfg_receive_stream_base;
reg [MEMORY_ADDR_WIDTH-1:0] held_cfg_work_floor;
reg [MEMORY_ADDR_WIDTH:0] held_cfg_context_bytes;
reg [MEMORY_ADDR_WIDTH:0] held_cfg_rpc_bytes;
reg [MEMORY_ADDR_WIDTH:0] held_cfg_receive_connection_bytes;
reg [MEMORY_ADDR_WIDTH:0] held_cfg_receive_stream_bytes;
reg  held_req_keyed;
wire  c_req_valid;
wire  c_req_ready;
wire [3:0] c_req_op;
wire  c_req_authority;
wire  c_req_maintenance;
wire [USER_WIDTH-1:0] c_req_user;
wire [30:0] c_req_stream;
wire [31:0] c_req_generation;
wire [MEMORY_ADDR_WIDTH-1:0] c_req_record_address;
wire [31:0] c_req_amount;
wire [MEMORY_ADDR_WIDTH-1:0] c_cfg_context_base;
wire [MEMORY_ADDR_WIDTH-1:0] c_cfg_rpc_base;
wire [MEMORY_ADDR_WIDTH-1:0] c_cfg_receive_connection_base;
wire [MEMORY_ADDR_WIDTH-1:0] c_cfg_receive_stream_base;
wire [MEMORY_ADDR_WIDTH-1:0] c_cfg_work_floor;
wire [MEMORY_ADDR_WIDTH:0] c_cfg_context_bytes;
wire [MEMORY_ADDR_WIDTH:0] c_cfg_rpc_bytes;
wire [MEMORY_ADDR_WIDTH:0] c_cfg_receive_connection_bytes;
wire [MEMORY_ADDR_WIDTH:0] c_cfg_receive_stream_bytes;
wire  c_rsp_valid;
wire  c_rsp_ready;
wire [3:0] c_rsp_op;
wire [USER_WIDTH-1:0] c_rsp_user;
wire [30:0] c_rsp_stream;
wire [7:0] c_rsp_status;
wire [7:0] c_rsp_detail;
wire [7:0] c_rsp_memory_status;
wire  c_rsp_connection_error;
wire [31:0] c_rsp_http2_error;
wire [31:0] c_rsp_connection_available;
wire [31:0] c_rsp_stream_available;
wire [31:0] c_rsp_connection_pending;
wire [31:0] c_rsp_stream_pending;
wire  c_rsp_debit_authorized;
wire  c_rsp_wire_retired;
wire [31:0] c_rsp_update_bytes;
wire  c_recovery_required;
wire [MEMORY_ADDR_WIDTH-1:0] c_recovery_address;
wire [511:0] c_m_axis_tx_tdata;
wire [63:0] c_m_axis_tx_tkeep;
wire  c_m_axis_tx_tvalid;
wire  c_m_axis_tx_tready;
wire  c_m_axis_tx_tlast;
wire [USER_WIDTH-1:0] c_m_axis_tx_tuser;
wire  c_mem_valid;
wire  c_mem_ready;
wire  c_mem_write;
wire [MEMORY_ADDR_WIDTH-1:0] c_mem_addr;
wire [3:0] c_mem_bytes;
wire [71:0] c_mem_data;
wire  c_mem_rsp_valid;
wire  c_mem_rsp_ready;
wire [71:0] c_mem_rsp_data;
wire [7:0] c_mem_rsp_status;
wire  c_idle;
wire  scan_mem_valid;
assign mem_valid=selected_scan?scan_mem_valid:c_mem_valid;
wire  scan_mem_ready;
assign scan_mem_ready=selected_scan&&mem_ready;
assign c_mem_ready=!selected_scan&&mem_ready;
wire  scan_mem_write;
assign mem_write=selected_scan?scan_mem_write:c_mem_write;
wire [MEMORY_ADDR_WIDTH-1:0] scan_mem_addr;
assign mem_addr=selected_scan?scan_mem_addr:c_mem_addr;
wire [3:0] scan_mem_bytes;
assign mem_bytes=selected_scan?scan_mem_bytes:c_mem_bytes;
wire [71:0] scan_mem_data;
assign mem_data=selected_scan?scan_mem_data:c_mem_data;
wire  scan_mem_rsp_valid;
assign scan_mem_rsp_valid=selected_scan&&mem_rsp_valid;
assign c_mem_rsp_valid=!selected_scan&&mem_rsp_valid;
wire  scan_mem_rsp_ready;
assign mem_rsp_ready=selected_scan?scan_mem_rsp_ready:c_mem_rsp_ready;
wire [71:0] scan_mem_rsp_data;
assign scan_mem_rsp_data=mem_rsp_data;
assign c_mem_rsp_data=mem_rsp_data;
wire [7:0] scan_mem_rsp_status;
assign scan_mem_rsp_status=mem_rsp_status;
assign c_mem_rsp_status=mem_rsp_status;
assign rsp_connection_available=c_rsp_connection_available;
assign rsp_stream_available=c_rsp_stream_available;
assign rsp_connection_pending=c_rsp_connection_pending;
assign rsp_stream_pending=c_rsp_stream_pending;

localparam IDLE=0,PREPARE=1,PRECHECK_SEND=2,PRECHECK_WAIT=3,SCAN_REQ=4,SCAN_WAIT=5,
    SCAN_CHECK=6,COMMAND_SEND=7,COMMAND_WAIT=8,LOCAL_RESULT=9;
reg [3:0] state;
reg [MEMORY_ADDR_WIDTH-1:0] resolved_address,scan_address;
reg [31:0] resolved_generation;
reg [1:0] word_index;
reg [255:0] record_data;
integer record_bank;
reg [7:0] local_status,local_detail,local_memory;
reg local_connection_error;reg [31:0] local_http2_error;
reg scan_recovery;reg [MEMORY_ADDR_WIDTH-1:0] scan_recovery_address;
reg [USER_WIDTH+9*MEMORY_ADDR_WIDTH+4-1:0] scan_recovery_scope;
wire [USER_WIDTH+9*MEMORY_ADDR_WIDTH+4-1:0] current_scope={held_req_user,
    held_cfg_context_base,held_cfg_rpc_base,held_cfg_receive_connection_base,held_cfg_receive_stream_base,held_cfg_work_floor,
    held_cfg_context_bytes,held_cfg_rpc_bytes,held_cfg_receive_connection_bytes,held_cfg_receive_stream_bytes};
wire selected_scan=state==SCAN_REQ||state==SCAN_WAIT||state==SCAN_CHECK;
wire [63:0] pool_end={1'b0,held_cfg_rpc_base}+{1'b0,held_cfg_rpc_bytes};
wire [MEMORY_ADDR_WIDTH-1:0] scan_word_address=scan_address+word_index*8;
wire scan_slot_ready,scan_slot_valid,scan_slot_idle;
wire [71:0] scan_slot_data;wire [7:0] scan_slot_status;
memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) lookup_slot(
    .clk(clk),.rst(rst),.req_valid(state==SCAN_REQ),.req_ready(scan_slot_ready),.req_write(1'b0),
    .req_addr(scan_word_address),.req_bytes(4'd8),.req_data(72'd0),.result_valid(scan_slot_valid),
    .result_ready(state==SCAN_WAIT),.result_data(scan_slot_data),.result_status(scan_slot_status),
    .mem_valid(scan_mem_valid),.mem_ready(scan_mem_ready),.mem_write(scan_mem_write),.mem_addr(scan_mem_addr),
    .mem_bytes(scan_mem_bytes),.mem_data(scan_mem_data),.mem_rsp_valid(scan_mem_rsp_valid),.mem_rsp_ready(scan_mem_rsp_ready),
    .mem_rsp_data(scan_mem_rsp_data),.mem_rsp_status(scan_mem_rsp_status),.idle(scan_slot_idle));
assign req_ready=!rst&&state==IDLE&&c_idle&&scan_slot_idle;
assign c_req_valid=state==PRECHECK_SEND||state==COMMAND_SEND;
assign c_rsp_ready=state==PRECHECK_WAIT||state==COMMAND_WAIT&&rsp_ready;
assign rsp_valid=state==LOCAL_RESULT||state==COMMAND_WAIT&&c_rsp_valid;
assign rsp_op=held_req_op;assign rsp_user=held_req_user;assign rsp_stream=held_req_stream;
assign rsp_status=state==LOCAL_RESULT?local_status:c_rsp_status;
assign rsp_detail=state==LOCAL_RESULT?local_detail:c_rsp_detail;
assign rsp_memory_status=state==LOCAL_RESULT?local_memory:c_rsp_memory_status;
assign rsp_connection_error=state==LOCAL_RESULT?local_connection_error:c_rsp_connection_error;
assign rsp_http2_error=state==LOCAL_RESULT?local_http2_error:c_rsp_http2_error;
assign rsp_debit_authorized=state==COMMAND_WAIT&&c_rsp_debit_authorized;
assign rsp_wire_retired=state==COMMAND_WAIT&&c_rsp_wire_retired;
assign rsp_update_bytes=state==COMMAND_WAIT?c_rsp_update_bytes:0;
assign rsp_binding_valid=rsp_valid&&rsp_status==0&&held_req_stream!=0&&resolved_generation!=0;
assign rsp_record_address=resolved_address;assign rsp_generation=resolved_generation;
assign recovery_required=scan_recovery||c_recovery_required;
assign recovery_address=scan_recovery?scan_recovery_address:c_recovery_address;
assign idle=state==IDLE&&c_idle&&scan_slot_idle&&!req_valid;
task local_fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status,input quarantine);
    begin local_status<=status;local_detail<=detail;local_memory<=memory_status;
        local_connection_error<=status!=3;local_http2_error<=status==3?0:2;state<=LOCAL_RESULT;
        if(quarantine)begin scan_recovery<=1;scan_recovery_address<=scan_word_address;scan_recovery_scope<=current_scope;end
    end
endtask
task next_record;
    begin
        if({1'b0,scan_address}+128<pool_end)begin scan_address<=scan_address+128;word_index<=0;state<=SCAN_REQ;end
        else local_fail(3,10,0,0);
    end
endtask
always @(posedge clk)begin
    if(rst)begin
        state<=IDLE;resolved_address<=0;resolved_generation<=0;scan_address<=0;word_index<=0;record_data<=0;
        local_status<=0;local_detail<=0;local_memory<=0;local_connection_error<=0;local_http2_error<=0;
        scan_recovery<=0;scan_recovery_address<=0;scan_recovery_scope<=0;
        held_req_op<=0;held_req_authority<=0;held_req_maintenance<=0;held_req_user<=0;held_req_stream<=0;held_req_generation<=0;held_req_record_address<=0;held_req_amount<=0;held_cfg_context_base<=0;held_cfg_rpc_base<=0;held_cfg_receive_connection_base<=0;held_cfg_receive_stream_base<=0;held_cfg_work_floor<=0;held_cfg_context_bytes<=0;held_cfg_rpc_bytes<=0;held_cfg_receive_connection_bytes<=0;held_cfg_receive_stream_bytes<=0;held_req_keyed<=0;
    end else case(state)
        IDLE:if(req_valid&&req_ready)begin
            held_req_op<=req_op;held_req_authority<=req_authority;held_req_maintenance<=req_maintenance;held_req_user<=req_user;held_req_stream<=req_stream;held_req_generation<=req_generation;held_req_record_address<=req_record_address;held_req_amount<=req_amount;held_cfg_context_base<=cfg_context_base;held_cfg_rpc_base<=cfg_rpc_base;held_cfg_receive_connection_base<=cfg_receive_connection_base;held_cfg_receive_stream_base<=cfg_receive_stream_base;held_cfg_work_floor<=cfg_work_floor;held_cfg_context_bytes<=cfg_context_bytes;held_cfg_rpc_bytes<=cfg_rpc_bytes;held_cfg_receive_connection_bytes<=cfg_receive_connection_bytes;held_cfg_receive_stream_bytes<=cfg_receive_stream_bytes;held_req_keyed<=req_keyed;
            resolved_address<=req_record_address;resolved_generation<=req_generation;
            local_status<=0;local_detail<=0;local_memory<=0;local_connection_error<=0;local_http2_error<=0;state<=PREPARE;
        end
        PREPARE:if(scan_recovery&&(held_req_keyed||held_req_op!=0||!held_req_maintenance||current_scope!=scan_recovery_scope))local_fail(6,1,0,0);
            else if(held_req_keyed&&(held_req_stream==0||held_req_generation!=0||held_req_record_address!=0||
                !(held_req_op==2||held_req_op==3||held_req_op==4||held_req_op==5||held_req_op==8)))local_fail(2,7,0,0);
            else state<=held_req_keyed?PRECHECK_SEND:COMMAND_SEND;
        PRECHECK_SEND:if(c_req_ready)state<=PRECHECK_WAIT;
        PRECHECK_WAIT:if(c_rsp_valid)begin
            if(c_rsp_status!=0)begin
                local_status<=c_rsp_status;local_detail<=c_rsp_detail;local_memory<=c_rsp_memory_status;
                local_connection_error<=c_rsp_connection_error;local_http2_error<=c_rsp_http2_error;state<=LOCAL_RESULT;
            end else begin scan_address<=held_cfg_rpc_base;word_index<=0;state<=SCAN_REQ;end
        end
        SCAN_REQ:if(scan_slot_ready)state<=SCAN_WAIT;
        SCAN_WAIT:if(scan_slot_valid)begin
            if(scan_slot_status!=0)local_fail(5,20,scan_slot_status,1);
            else if(word_index==0&&scan_slot_data[63:0]==0)next_record;
            else if(word_index==0&&(scan_slot_data[31:0]!=32'h47525331||!scan_slot_data[32]||scan_slot_data[63:35]!=0))local_fail(5,21,0,1);
            else if(word_index==1&&(scan_slot_data[63]||scan_slot_data[62:32]==0))local_fail(5,21,0,1);
            else if(word_index==1&&(scan_slot_data[15:0]!=held_req_user||scan_slot_data[62:32]!=held_req_stream))next_record;
            else begin
                for(record_bank=0;record_bank<4;record_bank=record_bank+1)if(word_index==record_bank)record_data[record_bank*64+:64]<=scan_slot_data[63:0];
                if(word_index==3)state<=SCAN_CHECK;else begin word_index<=word_index+1'b1;state<=SCAN_REQ;end
            end
        end
        SCAN_CHECK:if(record_data[255:224]==0)local_fail(5,21,0,1);
            else begin resolved_address<=scan_address;resolved_generation<=record_data[255:224];state<=COMMAND_SEND;end
        COMMAND_SEND:if(c_req_ready)state<=COMMAND_WAIT;
        COMMAND_WAIT:if(c_rsp_valid&&rsp_ready)begin
            if(held_req_op==0&&c_rsp_status==0)begin scan_recovery<=0;scan_recovery_address<=0;end
            state<=IDLE;
        end
        LOCAL_RESULT:if(rsp_ready)state<=IDLE;
        default:state<=IDLE;
    endcase
end

http2_receive_credit_store #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) controller(
    .clk(clk),
    .rst(rst),
    .req_valid(c_req_valid),
    .req_ready(c_req_ready),
    .req_op(state==PRECHECK_SEND?4'd8:held_req_op),
    .req_authority(held_req_authority),
    .req_maintenance(held_req_maintenance),
    .req_user(held_req_user),
    .req_stream(state==PRECHECK_SEND?31'd0:held_req_stream),
    .req_generation(state==PRECHECK_SEND?32'd0:resolved_generation),
    .req_record_address(state==PRECHECK_SEND?{MEMORY_ADDR_WIDTH{1'b0}}:resolved_address),
    .req_amount(state==PRECHECK_SEND?32'd0:held_req_amount),
    .cfg_context_base(held_cfg_context_base),
    .cfg_rpc_base(held_cfg_rpc_base),
    .cfg_receive_connection_base(held_cfg_receive_connection_base),
    .cfg_receive_stream_base(held_cfg_receive_stream_base),
    .cfg_work_floor(held_cfg_work_floor),
    .cfg_context_bytes(held_cfg_context_bytes),
    .cfg_rpc_bytes(held_cfg_rpc_bytes),
    .cfg_receive_connection_bytes(held_cfg_receive_connection_bytes),
    .cfg_receive_stream_bytes(held_cfg_receive_stream_bytes),
    .context_write_busy(context_write_busy),
    .context_write_user(context_write_user),
    .context_write_address(context_write_address),
    .context_write_fault(context_write_fault),
    .context_write_fault_user(context_write_fault_user),
    .context_write_fault_address(context_write_fault_address),
    .context_write_fault_memory_status(context_write_fault_memory_status),
    .rsp_valid(c_rsp_valid),
    .rsp_ready(c_rsp_ready),
    .rsp_op(c_rsp_op),
    .rsp_user(c_rsp_user),
    .rsp_stream(c_rsp_stream),
    .rsp_status(c_rsp_status),
    .rsp_detail(c_rsp_detail),
    .rsp_memory_status(c_rsp_memory_status),
    .rsp_connection_error(c_rsp_connection_error),
    .rsp_http2_error(c_rsp_http2_error),
    .rsp_connection_available(c_rsp_connection_available),
    .rsp_stream_available(c_rsp_stream_available),
    .rsp_connection_pending(c_rsp_connection_pending),
    .rsp_stream_pending(c_rsp_stream_pending),
    .rsp_debit_authorized(c_rsp_debit_authorized),
    .rsp_wire_retired(c_rsp_wire_retired),
    .rsp_update_bytes(c_rsp_update_bytes),
    .recovery_required(c_recovery_required),
    .recovery_address(c_recovery_address),
    .m_axis_tx_tdata(m_axis_tx_tdata),
    .m_axis_tx_tkeep(m_axis_tx_tkeep),
    .m_axis_tx_tvalid(m_axis_tx_tvalid),
    .m_axis_tx_tready(m_axis_tx_tready),
    .m_axis_tx_tlast(m_axis_tx_tlast),
    .m_axis_tx_tuser(m_axis_tx_tuser),
    .mem_valid(c_mem_valid),
    .mem_ready(c_mem_ready),
    .mem_write(c_mem_write),
    .mem_addr(c_mem_addr),
    .mem_bytes(c_mem_bytes),
    .mem_data(c_mem_data),
    .mem_rsp_valid(c_mem_rsp_valid),
    .mem_rsp_ready(c_mem_rsp_ready),
    .mem_rsp_data(c_mem_rsp_data),
    .mem_rsp_status(c_mem_rsp_status),
    .idle(c_idle)
);
endmodule
`default_nettype wire
