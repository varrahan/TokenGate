`timescale 1ns/1ps
`default_nettype none
// Read-only absence check under the real directory pool lock. This is not
// global reload authority: the caller must also fence admission, GPU work,
// transport, queues and retained recovery. Configuration must be the owned
// geometry acknowledged by the actual directory, never live host pins.
// Status: 0 empty, 1 scope/geometry, 2 active RPC, 3 lock rejection,
// 4 memory error, 5 malformed nonzero header, 6 lost lock authority.
module rpc_pool_empty_probe #(
    parameter integer MEMORY_ADDR_WIDTH=23,
    parameter [31:0] RPC_MAGIC=32'h47525331
)(
    input wire clk,rst,
    input wire req_valid,output wire req_ready,
    input wire [63:0] req_tag,input wire req_hold_empty,req_scope_valid,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] req_pool_bytes,
    output wire result_valid,input wire result_ready,
    output reg [63:0] result_tag,output reg [7:0] result_status,
    output reg result_empty,result_holding_requested,
    output reg [MEMORY_ADDR_WIDTH-1:0] result_pool_base,result_address,
    output reg [MEMORY_ADDR_WIDTH:0] result_pool_bytes,
    output reg [63:0] result_header,output reg [31:0] result_records_examined,
    output reg [7:0] result_lock_status,result_memory_status,
    input wire release_valid,output wire release_ready,
    output wire certificate_active,output reg recovery_required,
    output wire admission_fence,output wire idle,
    output wire lock_valid,input wire lock_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] lock_base,
    output wire [MEMORY_ADDR_WIDTH:0] lock_bytes,
    input wire lock_result_valid,output wire lock_result_ready,
    input wire [7:0] lock_status,input wire lock_active,
    output wire unlock_valid,input wire unlock_ready,
    output wire memory_owner,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status
);
    localparam IDLE=0,CHECK=1,LOCK_SEND=2,LOCK_WAIT=3,READ_SEND=4,
        READ_WAIT=5,UNLOCK=6,RESULT=7,HELD=8;
    reg [3:0] state;
    reg scope_valid,owned;
    reg [MEMORY_ADDR_WIDTH-1:0] cursor;
    wire [63:0] pool_end={1'b0,result_pool_base}+{1'b0,result_pool_bytes};
    wire geometry_good=result_pool_bytes>=128&&result_pool_bytes[6:0]==0&&
        pool_end<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire slot_ready,slot_valid,slot_idle;
    wire [71:0] slot_data;
    wire [7:0] slot_status;
    wire current_lock=owned&&lock_active&&!recovery_required;
    assign req_ready=!rst&&state==IDLE&&!recovery_required;
    assign result_valid=!rst&&state==RESULT;
    assign lock_valid=!rst&&state==LOCK_SEND;
    assign lock_base=result_pool_base;assign lock_bytes=result_pool_bytes;
    assign lock_result_ready=!rst&&state==LOCK_WAIT;
    assign unlock_valid=!rst&&owned&&lock_active&&!recovery_required&&
        (state==UNLOCK||state==HELD&&release_valid);
    assign release_ready=!rst&&state==HELD&&current_lock&&unlock_ready;
    // Result fields describe the immutable snapshot. This separate live
    // certificate revokes immediately if the actual lock/reset is lost.
    assign certificate_active=!rst&&current_lock&&result_empty&&
        result_holding_requested&&(state==RESULT||state==HELD);
    assign memory_owner=!rst&&owned;
    assign admission_fence=!rst&&(recovery_required||owned||
        state==CHECK||state==LOCK_SEND||state==LOCK_WAIT||state==READ_SEND||state==READ_WAIT||state==UNLOCK);
    // BUSY/error/unlocked-empty results may be held without stopping traffic.
    assign idle=state==IDLE&&slot_idle&&!req_valid&&!recovery_required;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==READ_SEND&&current_lock),.req_ready(slot_ready),
        .req_write(1'b0),.req_addr(cursor),.req_bytes(4'd8),.req_data(72'd0),
        .result_valid(slot_valid),.result_ready(state==READ_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),
        .mem_bytes(mem_bytes),.mem_data(mem_data),.mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),
        .mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;scope_valid<=0;owned<=0;cursor<=0;recovery_required<=0;
            result_tag<=0;result_status<=0;result_empty<=0;result_holding_requested<=0;
            result_pool_base<=0;result_pool_bytes<=0;result_address<=0;result_header<=0;
            result_records_examined<=0;result_lock_status<=0;result_memory_status<=0;
        end else begin
            if(owned&&!lock_active)recovery_required<=1;
            case(state)
                IDLE:if(req_valid&&req_ready)begin
                    result_tag<=req_tag;result_pool_base<=req_pool_base;result_pool_bytes<=req_pool_bytes;
                    result_holding_requested<=req_hold_empty;scope_valid<=req_scope_valid;
                    result_status<=0;result_empty<=0;result_address<=0;result_header<=0;
                    result_records_examined<=0;result_lock_status<=0;result_memory_status<=0;state<=CHECK;
                end
                CHECK:if(!scope_valid||!geometry_good)begin result_status<=1;state<=RESULT;end
                    else begin cursor<=result_pool_base;state<=LOCK_SEND;end
                LOCK_SEND:if(lock_ready)state<=LOCK_WAIT;
                LOCK_WAIT:if(lock_result_valid)begin
                    result_lock_status<=lock_status;
                    if(lock_status!=0)begin result_status<=3;state<=RESULT;end
                    else begin owned<=1;state<=READ_SEND;end
                end
                READ_SEND:if(!lock_active||recovery_required)begin result_status<=6;result_address<=cursor;state<=UNLOCK;end
                    else if(slot_ready)state<=READ_WAIT;
                READ_WAIT:if(slot_valid)begin
                    result_address<=cursor;result_header<=slot_data[63:0];result_memory_status<=slot_status;
                    if(!current_lock)begin result_status<=6;state<=UNLOCK;end
                    else if(slot_status!=0)begin result_status<=4;state<=UNLOCK;end
                    else begin
                        result_records_examined<=result_records_examined+1'b1;
                        if(slot_data[63:0]!=0)begin
                            result_status<=slot_data[31:0]==RPC_MAGIC&&slot_data[32]&&slot_data[63:35]==0?8'd2:8'd5;
                            state<=UNLOCK;
                        end else if({1'b0,cursor}+64'd128>=pool_end)begin
                            result_empty<=1;
                            state<=result_holding_requested?RESULT:UNLOCK;
                        end else begin cursor<=cursor+128;state<=READ_SEND;end
                    end
                end
                UNLOCK:if(recovery_required||!lock_active)begin
                        owned<=0;result_status<=6;result_empty<=0;state<=RESULT;
                    end else if(unlock_valid&&unlock_ready)begin owned<=0;state<=RESULT;end
                RESULT:if(result_ready)state<=owned?HELD:IDLE;
                HELD:if(release_valid&&release_ready)begin owned<=0;state<=IDLE;end
                default:begin recovery_required<=1;state<=RESULT;result_status<=6;end
            endcase
        end
    end
    initial begin
        if(MEMORY_ADDR_WIDTH<10||MEMORY_ADDR_WIDTH>31)$error("Unsupported RPC probe address width");
    end
endmodule
`default_nettype wire
