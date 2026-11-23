`timescale 1ns/1ps
`default_nettype none
// Gate the real receive backend behind the actual shared directory pool lock.
// INIT reuses held admission ownership; CLOSE reuses its held directory result.
// Neither bypass may invent ownership. All ordinary requests acquire the lock.
module http2_receive_pool_gate #(parameter integer MEMORY_ADDR_WIDTH=23)(
    input wire clk,rst,
    input wire command_valid,output wire command_ready,input wire command_is_init,command_is_close,
    input wire [MEMORY_ADDR_WIDTH-1:0] command_pool_base,input wire [MEMORY_ADDR_WIDTH:0] command_pool_bytes,
    input wire admission_owned,close_owned,
    output wire backend_valid,input wire backend_ready,output wire backend_authority,
    input wire backend_result_valid,output wire backend_result_ready,
    input wire [7:0] backend_status,backend_detail,backend_memory_status,
    input wire [31:0] backend_http2_error,input wire backend_debit_authorized,
    output wire result_valid,input wire result_ready,
    output wire [7:0] result_status,result_detail,result_memory_status,
    output wire [31:0] result_http2_error,output wire result_debit_authorized,
    output wire lock_valid,input wire lock_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] lock_base,output wire [MEMORY_ADDR_WIDTH:0] lock_bytes,
    input wire lock_result_valid,output wire lock_result_ready,input wire [7:0] lock_status,
    input wire lock_active,output wire unlock_valid,input wire unlock_ready,
    output wire idle
);
    localparam IDLE=0,LOCK_SEND=1,LOCK_WAIT=2,ISSUE=3,RESULT=4,UNLOCK=5,ERROR_ACCEPT=6,ERROR_RESULT=7;
    reg [2:0] state;reg initialization,closing;reg [7:0] held_lock_status;
    reg [MEMORY_ADDR_WIDTH-1:0] pool_base;reg [MEMORY_ADDR_WIDTH:0] pool_bytes;
    wire scope_matches=pool_base==command_pool_base&&pool_bytes==command_pool_bytes&&
        initialization==command_is_init&&closing==command_is_close;
    assign command_ready=!rst&&(state==ERROR_ACCEPT||state==ISSUE&&backend_ready);
    assign backend_valid=!rst&&state==ISSUE&&command_valid;
    assign backend_authority=scope_matches&&(initialization?admission_owned:closing?close_owned:lock_active);
    assign backend_result_ready=!rst&&state==RESULT&&result_ready;
    assign result_valid=!rst&&(state==ERROR_RESULT||state==RESULT&&backend_result_valid);
    assign result_status=state==ERROR_RESULT?8'd7:backend_status;
    assign result_detail=state==ERROR_RESULT?held_lock_status:backend_detail;
    assign result_memory_status=state==ERROR_RESULT?8'd0:backend_memory_status;
    assign result_http2_error=state==ERROR_RESULT?32'd2:backend_http2_error;
    assign result_debit_authorized=state==RESULT&&backend_debit_authorized;
    assign lock_valid=!rst&&state==LOCK_SEND;
    assign lock_base=pool_base;assign lock_bytes=pool_bytes;
    assign lock_result_ready=!rst&&state==LOCK_WAIT;
    assign unlock_valid=!rst&&state==UNLOCK;
    assign idle=state==IDLE&&!command_valid;
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;initialization<=0;closing<=0;held_lock_status<=0;pool_base<=0;pool_bytes<=0;end
        else case(state)
            IDLE:if(command_valid)begin
                initialization<=command_is_init;closing<=command_is_close;
                pool_base<=command_pool_base;pool_bytes<=command_pool_bytes;held_lock_status<=0;
                state<=command_is_init||command_is_close?ISSUE:LOCK_SEND;
            end
            LOCK_SEND:if(lock_ready)state<=LOCK_WAIT;
            LOCK_WAIT:if(lock_result_valid)begin held_lock_status<=lock_status;state<=lock_status==0?ISSUE:ERROR_ACCEPT;end
            ISSUE:if(command_valid&&backend_ready)state<=RESULT;
            RESULT:if(backend_result_valid&&result_ready)state<=initialization||closing?IDLE:UNLOCK;
            UNLOCK:if(unlock_ready)state<=IDLE;
            ERROR_ACCEPT:if(command_valid)state<=ERROR_RESULT;
            ERROR_RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
