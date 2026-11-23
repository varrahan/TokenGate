`timescale 1ns/1ps
`default_nettype none
// One response-engine lease, not a fixed limit on live RPC records.
// Cache a real LOAD and release the backend while preserving record authority.
// Status 11 is a local lease/pool conflict; no backend memory command is issued.
module grpc_pool_locked_stream_store #(
parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire  clk,
    input wire  rst,
    input wire  req_valid,
    output wire  req_ready,
    input wire [2:0] req_op,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes,
    input wire [USER_WIDTH-1:0] req_user,
    input wire [USER_WIDTH-1:0] req_application,
    input wire [30:0] req_stream,
    input wire [31:0] req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_address,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_buffer_base,
    input wire [MEMORY_ADDR_WIDTH:0] req_buffer_bytes,
    input wire [31:0] req_message_limit,
    input wire  req_protobuf,
    input wire  req_unsupported_encoding,
    input wire  req_maintenance,
    input wire [255:0] req_state,
    output reg  rsp_valid,
    input wire  rsp_ready,
    output reg [7:0] rsp_status,
    output reg [7:0] rsp_detail,
    output reg [7:0] rsp_memory_status,
    output reg [2:0] rsp_op,
    output reg [MEMORY_ADDR_WIDTH-1:0] rsp_address,
    output reg [MEMORY_ADDR_WIDTH-1:0] rsp_buffer_base,
    output reg [MEMORY_ADDR_WIDTH:0] rsp_buffer_bytes,
    output reg [USER_WIDTH-1:0] rsp_user,
    output reg [USER_WIDTH-1:0] rsp_application,
    output reg [30:0] rsp_stream,
    output reg [31:0] rsp_generation,
    output reg [31:0] rsp_message_limit,
    output reg  rsp_protobuf,
    output reg  rsp_unsupported_encoding,
    output reg [255:0] rsp_state,
    output wire  recovery_required,
    output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire  idle,
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
    input wire  lease_valid,
    output wire  lease_ready,
    input wire [USER_WIDTH-1:0] lease_user,
    input wire [30:0] lease_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] lease_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] lease_pool_bytes,
    input wire  lease_rsp_ready,
    output wire  lease_active,
    output reg  lease_rsp_valid,
    output reg [7:0] lease_rsp_status,
    output reg [7:0] lease_rsp_detail,
    output reg [7:0] lease_rsp_memory_status,
    output reg [2:0] lease_rsp_op,
    output reg [MEMORY_ADDR_WIDTH-1:0] lease_rsp_address,
    output reg [MEMORY_ADDR_WIDTH-1:0] lease_rsp_buffer_base,
    output reg [MEMORY_ADDR_WIDTH:0] lease_rsp_buffer_bytes,
    output reg [USER_WIDTH-1:0] lease_rsp_user,
    output reg [USER_WIDTH-1:0] lease_rsp_application,
    output reg [30:0] lease_rsp_stream,
    output reg [31:0] lease_rsp_generation,
    output reg [31:0] lease_rsp_message_limit,
    output reg  lease_rsp_protobuf,
    output reg  lease_rsp_unsupported_encoding,
    output reg [255:0] lease_rsp_state
,
    input wire  pool_lock_valid,
    output wire  pool_lock_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] pool_lock_base,
    input wire [MEMORY_ADDR_WIDTH:0] pool_lock_bytes,
    output wire  pool_lock_result_valid,
    input wire  pool_lock_result_ready,
    output wire [7:0] pool_lock_status,
    output wire  pool_lock_active,
    input wire  pool_unlock_valid,
    output wire  pool_unlock_ready
);
localparam IDLE=0,CHECK_GUARDS=1,DECIDE=2,SEND=3,WAIT_RESULT=4;
reg [2:0] state;reg pending_lease,prefer_lease;reg [4:0] guards;
reg [MEMORY_ADDR_WIDTH-1:0] held_pool_base;
reg [MEMORY_ADDR_WIDTH:0] held_pool_bytes;
wire backend_ready,backend_idle;
reg [2:0] pending_req_op;
reg [MEMORY_ADDR_WIDTH-1:0] pending_cfg_pool_base;
reg [MEMORY_ADDR_WIDTH:0] pending_cfg_pool_bytes;
reg [USER_WIDTH-1:0] pending_req_user;
reg [USER_WIDTH-1:0] pending_req_application;
reg [30:0] pending_req_stream;
reg [31:0] pending_req_generation;
reg [MEMORY_ADDR_WIDTH-1:0] pending_req_address;
reg [MEMORY_ADDR_WIDTH-1:0] pending_req_buffer_base;
reg [MEMORY_ADDR_WIDTH:0] pending_req_buffer_bytes;
reg [31:0] pending_req_message_limit;
reg  pending_req_protobuf;
reg  pending_req_unsupported_encoding;
reg  pending_req_maintenance;
reg [255:0] pending_req_state;
wire  backend_rsp_valid;
wire [7:0] backend_rsp_status;
wire [7:0] backend_rsp_detail;
wire [7:0] backend_rsp_memory_status;
wire [2:0] backend_rsp_op;
wire [MEMORY_ADDR_WIDTH-1:0] backend_rsp_address;
wire [MEMORY_ADDR_WIDTH-1:0] backend_rsp_buffer_base;
wire [MEMORY_ADDR_WIDTH:0] backend_rsp_buffer_bytes;
wire [USER_WIDTH-1:0] backend_rsp_user;
wire [USER_WIDTH-1:0] backend_rsp_application;
wire [30:0] backend_rsp_stream;
wire [31:0] backend_rsp_generation;
wire [31:0] backend_rsp_message_limit;
wire  backend_rsp_protobuf;
wire  backend_rsp_unsupported_encoding;
wire [255:0] backend_rsp_state;

// Pool ownership waits for all previously accepted backend operations, while
// cached result slots can remain held or retire. Neither frontend can admit
// a new operation between lock acceptance and the explicit release handshake.
localparam POOL_IDLE=0,POOL_CHECK=1,POOL_DRAIN=2,POOL_HELD=3,POOL_ERROR=4;
reg [2:0] pool_state;
reg [MEMORY_ADDR_WIDTH-1:0] locked_base;
reg [MEMORY_ADDR_WIDTH:0] locked_bytes;
reg [7:0] locked_status;
reg pool_result_acked;
wire pool_gate=pool_state!=POOL_IDLE||pool_lock_valid;
wire [63:0] locked_end={1'b0,locked_base}+{1'b0,locked_bytes};
wire lock_layout_good=locked_bytes>=128&&locked_bytes[6:0]==0&&locked_end<=(64'd1<<MEMORY_ADDR_WIDTH);
assign pool_lock_ready=!rst&&pool_state==POOL_IDLE;
assign pool_lock_active=pool_state==POOL_HELD;
assign pool_lock_result_valid=!rst&&(pool_state==POOL_ERROR||pool_state==POOL_HELD&&!pool_result_acked);
assign pool_lock_status=locked_status;
assign pool_unlock_ready=!rst&&pool_state==POOL_HELD&&pool_result_acked;
always @(posedge clk)begin
    if(rst)begin pool_state<=POOL_IDLE;locked_base<=0;locked_bytes<=0;locked_status<=0;pool_result_acked<=0;end
    else case(pool_state)
        POOL_IDLE:if(pool_lock_valid&&pool_lock_ready)begin
            locked_base<=pool_lock_base;locked_bytes<=pool_lock_bytes;locked_status<=0;pool_result_acked<=0;pool_state<=POOL_CHECK;
        end
        POOL_CHECK:if(!lock_layout_good)begin locked_status<=1;pool_state<=POOL_ERROR;end else pool_state<=POOL_DRAIN;
        POOL_DRAIN:if(state==IDLE&&backend_idle)begin
            if(recovery_required)begin locked_status<=3;pool_state<=POOL_ERROR;end
            else if(lease_active&&(locked_base!=held_pool_base||locked_bytes!=held_pool_bytes))begin locked_status<=2;pool_state<=POOL_ERROR;end
            else pool_state<=POOL_HELD;
        end
        POOL_HELD:begin
            if(pool_lock_result_valid&&pool_lock_result_ready)pool_result_acked<=1;
            if(pool_unlock_valid&&pool_unlock_ready)begin pool_state<=POOL_IDLE;pool_result_acked<=0;end
        end
        POOL_ERROR:if(pool_lock_result_ready)pool_state<=POOL_IDLE;
        default:pool_state<=POOL_IDLE;
    endcase
end

wire control_candidate=req_valid&&!rsp_valid;
wire lease_candidate=lease_valid&&!lease_rsp_valid;
assign req_ready=!rst&&!pool_gate&&state==IDLE&&!rsp_valid&&(!lease_candidate||!prefer_lease);
assign lease_ready=!rst&&!pool_gate&&state==IDLE&&!lease_rsp_valid&&(!control_candidate||prefer_lease);
wire control_accept=req_valid&&req_ready,lease_accept=lease_valid&&lease_ready;
assign lease_active=lease_rsp_valid&&lease_rsp_status==0;
assign idle=pool_state==POOL_IDLE&&!pool_lock_valid&&state==IDLE&&backend_idle&&!rsp_valid&&!lease_rsp_valid&&!req_valid&&!lease_valid;
wire [63:0] pending_record_end={1'b0,pending_req_address}+64'd128;
wire [63:0] held_record_end={1'b0,lease_rsp_address}+64'd128;
wire [63:0] pending_pool_end={1'b0,pending_cfg_pool_base}+{1'b0,pending_cfg_pool_bytes};
wire record_overlaps={1'b0,pending_req_address}<held_record_end&&{1'b0,lease_rsp_address}<pending_record_end;
wire pool_overlaps={1'b0,pending_cfg_pool_base}<held_record_end&&{1'b0,lease_rsp_address}<pending_pool_end;
wire same_pool=pending_cfg_pool_base==held_pool_base&&pending_cfg_pool_bytes==held_pool_bytes;
wire same_binding=pending_req_address==lease_rsp_address&&pending_req_user==lease_rsp_user&&
    pending_req_stream==lease_rsp_stream&&pending_req_generation==lease_rsp_generation;
reg [7:0] conflict;
always @*begin
    conflict=0;
    if(guards[0])begin
        if(pending_req_op==3&&guards[1])conflict=1;
        else if(pending_req_op==4&&guards[2])conflict=2;
        else if(pending_req_op==5&&guards[1])conflict=3;
        else if(pending_req_op==2&&guards[1]&&!(guards[3]&&guards[4]))conflict=4;
        else if(pending_req_op==0&&guards[2]&&!guards[3])conflict=5;
        else if(pending_req_op<=6&&!guards[3])conflict=6;
    end
end
grpc_stream_store #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) store(
    .clk(clk),
    .rst(rst),
    .req_valid(state==SEND),
    .req_ready(backend_ready),
    .req_op(pending_req_op),
    .cfg_pool_base(pending_cfg_pool_base),
    .cfg_pool_bytes(pending_cfg_pool_bytes),
    .req_user(pending_req_user),
    .req_application(pending_req_application),
    .req_stream(pending_req_stream),
    .req_generation(pending_req_generation),
    .req_address(pending_req_address),
    .req_buffer_base(pending_req_buffer_base),
    .req_buffer_bytes(pending_req_buffer_bytes),
    .req_message_limit(pending_req_message_limit),
    .req_protobuf(pending_req_protobuf),
    .req_unsupported_encoding(pending_req_unsupported_encoding),
    .req_maintenance(pending_req_maintenance),
    .req_state(pending_req_state),
    .rsp_valid(backend_rsp_valid),
    .rsp_ready(!rst&&state==WAIT_RESULT),
    .rsp_status(backend_rsp_status),
    .rsp_detail(backend_rsp_detail),
    .rsp_memory_status(backend_rsp_memory_status),
    .rsp_op(backend_rsp_op),
    .rsp_address(backend_rsp_address),
    .rsp_buffer_base(backend_rsp_buffer_base),
    .rsp_buffer_bytes(backend_rsp_buffer_bytes),
    .rsp_user(backend_rsp_user),
    .rsp_application(backend_rsp_application),
    .rsp_stream(backend_rsp_stream),
    .rsp_generation(backend_rsp_generation),
    .rsp_message_limit(backend_rsp_message_limit),
    .rsp_protobuf(backend_rsp_protobuf),
    .rsp_unsupported_encoding(backend_rsp_unsupported_encoding),
    .rsp_state(backend_rsp_state),
    .recovery_required(recovery_required),
    .recovery_address(recovery_address),
    .idle(backend_idle),
    .mem_valid(mem_valid),
    .mem_ready(mem_ready),
    .mem_write(mem_write),
    .mem_addr(mem_addr),
    .mem_bytes(mem_bytes),
    .mem_data(mem_data),
    .mem_rsp_valid(mem_rsp_valid),
    .mem_rsp_ready(mem_rsp_ready),
    .mem_rsp_data(mem_rsp_data),
    .mem_rsp_status(mem_rsp_status)
);
always @(posedge clk)begin
    if(rst)begin
        state<=IDLE;pending_lease<=0;prefer_lease<=0;guards<=0;held_pool_base<=0;held_pool_bytes<=0;
        pending_req_op<=0;
        pending_cfg_pool_base<=0;
        pending_cfg_pool_bytes<=0;
        pending_req_user<=0;
        pending_req_application<=0;
        pending_req_stream<=0;
        pending_req_generation<=0;
        pending_req_address<=0;
        pending_req_buffer_base<=0;
        pending_req_buffer_bytes<=0;
        pending_req_message_limit<=0;
        pending_req_protobuf<=0;
        pending_req_unsupported_encoding<=0;
        pending_req_maintenance<=0;
        pending_req_state<=0;
        rsp_valid<=0;lease_rsp_valid<=0;
        rsp_status<=0;lease_rsp_status<=0;
        rsp_detail<=0;lease_rsp_detail<=0;
        rsp_memory_status<=0;lease_rsp_memory_status<=0;
        rsp_op<=0;lease_rsp_op<=0;
        rsp_address<=0;lease_rsp_address<=0;
        rsp_buffer_base<=0;lease_rsp_buffer_base<=0;
        rsp_buffer_bytes<=0;lease_rsp_buffer_bytes<=0;
        rsp_user<=0;lease_rsp_user<=0;
        rsp_application<=0;lease_rsp_application<=0;
        rsp_stream<=0;lease_rsp_stream<=0;
        rsp_generation<=0;lease_rsp_generation<=0;
        rsp_message_limit<=0;lease_rsp_message_limit<=0;
        rsp_protobuf<=0;lease_rsp_protobuf<=0;
        rsp_unsupported_encoding<=0;lease_rsp_unsupported_encoding<=0;
        rsp_state<=0;lease_rsp_state<=0;
    end else begin
        if(rsp_valid&&rsp_ready)rsp_valid<=0;
        if(lease_rsp_valid&&lease_rsp_ready)lease_rsp_valid<=0;
        case(state)
            IDLE:if(control_accept||lease_accept)begin
                pending_lease<=lease_accept;prefer_lease<=control_accept;
                pending_req_op<=lease_accept?3'd1:req_op;
                pending_cfg_pool_base<=lease_accept?lease_pool_base:cfg_pool_base;
                pending_cfg_pool_bytes<=lease_accept?lease_pool_bytes:cfg_pool_bytes;
                pending_req_user<=lease_accept?lease_user:req_user;
                pending_req_application<=lease_accept?0:req_application;
                pending_req_stream<=lease_accept?lease_stream:req_stream;
                pending_req_generation<=lease_accept?0:req_generation;
                pending_req_address<=lease_accept?0:req_address;
                pending_req_buffer_base<=lease_accept?0:req_buffer_base;
                pending_req_buffer_bytes<=lease_accept?0:req_buffer_bytes;
                pending_req_message_limit<=lease_accept?0:req_message_limit;
                pending_req_protobuf<=lease_accept?0:req_protobuf;
                pending_req_unsupported_encoding<=lease_accept?0:req_unsupported_encoding;
                pending_req_maintenance<=lease_accept?0:req_maintenance;
                pending_req_state<=lease_accept?0:req_state;
                state<=lease_accept?SEND:CHECK_GUARDS;
            end
            CHECK_GUARDS:begin
                guards<={same_binding,same_pool,pool_overlaps,record_overlaps,lease_active};state<=DECIDE;
            end
            DECIDE:if(conflict!=0)begin
                rsp_valid<=1'b1;
                rsp_status<=8'd11;
                rsp_detail<=conflict;
                rsp_memory_status<=0;
                rsp_op<=pending_req_op;
                rsp_address<=pending_req_address;
                rsp_buffer_base<=0;
                rsp_buffer_bytes<=0;
                rsp_user<=pending_req_user;
                rsp_application<=0;
                rsp_stream<=pending_req_stream;
                rsp_generation<=0;
                rsp_message_limit<=0;
                rsp_protobuf<=0;
                rsp_unsupported_encoding<=0;
                rsp_state<=0;
                state<=IDLE;
            end else state<=SEND;
            SEND:if(backend_ready)state<=WAIT_RESULT;
            WAIT_RESULT:if(backend_rsp_valid)begin
                if(pending_lease)begin
                    lease_rsp_valid<=backend_rsp_valid;
                    lease_rsp_status<=backend_rsp_status;
                    lease_rsp_detail<=backend_rsp_detail;
                    lease_rsp_memory_status<=backend_rsp_memory_status;
                    lease_rsp_op<=backend_rsp_op;
                    lease_rsp_address<=backend_rsp_address;
                    lease_rsp_buffer_base<=backend_rsp_buffer_base;
                    lease_rsp_buffer_bytes<=backend_rsp_buffer_bytes;
                    lease_rsp_user<=backend_rsp_user;
                    lease_rsp_application<=backend_rsp_application;
                    lease_rsp_stream<=backend_rsp_stream;
                    lease_rsp_generation<=backend_rsp_generation;
                    lease_rsp_message_limit<=backend_rsp_message_limit;
                    lease_rsp_protobuf<=backend_rsp_protobuf;
                    lease_rsp_unsupported_encoding<=backend_rsp_unsupported_encoding;
                    lease_rsp_state<=backend_rsp_state;
                    held_pool_base<=pending_cfg_pool_base;held_pool_bytes<=pending_cfg_pool_bytes;
                end else begin
                    rsp_valid<=backend_rsp_valid;
                    rsp_status<=backend_rsp_status;
                    rsp_detail<=backend_rsp_detail;
                    rsp_memory_status<=backend_rsp_memory_status;
                    rsp_op<=backend_rsp_op;
                    rsp_address<=backend_rsp_address;
                    rsp_buffer_base<=backend_rsp_buffer_base;
                    rsp_buffer_bytes<=backend_rsp_buffer_bytes;
                    rsp_user<=backend_rsp_user;
                    rsp_application<=backend_rsp_application;
                    rsp_stream<=backend_rsp_stream;
                    rsp_generation<=backend_rsp_generation;
                    rsp_message_limit<=backend_rsp_message_limit;
                    rsp_protobuf<=backend_rsp_protobuf;
                    rsp_unsupported_encoding<=backend_rsp_unsupported_encoding;
                    rsp_state<=backend_rsp_state;
                end
                state<=IDLE;
            end
            default:state<=IDLE;
        endcase
    end
end
endmodule
`default_nettype wire
