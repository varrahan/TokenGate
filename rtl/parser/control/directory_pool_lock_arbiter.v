`timescale 1ns/1ps
`default_nettype none
// Two owners, one actual directory lock. Ownership starts before the lock
// offer and survives grant/result backpressure through actual unlock ACK.
module directory_pool_lock_arbiter #(parameter integer MEMORY_ADDR_WIDTH=23)(
    input wire clk,rst,
    input wire a_lock_valid,output wire a_lock_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] a_lock_base,input wire [MEMORY_ADDR_WIDTH:0] a_lock_bytes,
    output wire a_result_valid,input wire a_result_ready,output wire [7:0] a_status,
    output wire a_active,input wire a_unlock_valid,output wire a_unlock_ready,
    input wire b_lock_valid,output wire b_lock_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] b_lock_base,input wire [MEMORY_ADDR_WIDTH:0] b_lock_bytes,
    output wire b_result_valid,input wire b_result_ready,output wire [7:0] b_status,
    output wire b_active,input wire b_unlock_valid,output wire b_unlock_ready,
    output wire m_lock_valid,input wire m_lock_ready,
    output reg [MEMORY_ADDR_WIDTH-1:0] m_lock_base,output reg [MEMORY_ADDR_WIDTH:0] m_lock_bytes,
    input wire m_result_valid,output wire m_result_ready,input wire [7:0] m_status,
    input wire m_active,output wire m_unlock_valid,input wire m_unlock_ready,output wire idle
);
    localparam IDLE=0,REQUEST=1,RESULT=2,HELD=3;
    reg [1:0] state;reg owner,prefer_b;
    wire choose_b=a_lock_valid&&b_lock_valid?prefer_b:b_lock_valid;
    assign m_lock_valid=!rst&&state==REQUEST;
    assign a_lock_ready=!rst&&state==REQUEST&&!owner&&m_lock_ready;
    assign b_lock_ready=!rst&&state==REQUEST&&owner&&m_lock_ready;
    assign a_result_valid=!rst&&state==RESULT&&!owner&&m_result_valid;
    assign b_result_valid=!rst&&state==RESULT&&owner&&m_result_valid;
    assign m_result_ready=!rst&&state==RESULT&&(owner?b_result_ready:a_result_ready);
    assign a_status=m_status;assign b_status=m_status;
    assign a_active=!rst&&!owner&&(state==RESULT||state==HELD)&&m_active;
    assign b_active=!rst&&owner&&(state==RESULT||state==HELD)&&m_active;
    assign m_unlock_valid=!rst&&state==HELD&&(owner?b_unlock_valid:a_unlock_valid);
    assign a_unlock_ready=!rst&&state==HELD&&!owner&&m_unlock_ready;
    assign b_unlock_ready=!rst&&state==HELD&&owner&&m_unlock_ready;
    assign idle=state==IDLE&&!a_lock_valid&&!b_lock_valid;
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;owner<=0;prefer_b<=0;m_lock_base<=0;m_lock_bytes<=0;end
        else case(state)
            IDLE:if(a_lock_valid||b_lock_valid)begin
                owner<=choose_b;m_lock_base<=choose_b?b_lock_base:a_lock_base;
                m_lock_bytes<=choose_b?b_lock_bytes:a_lock_bytes;state<=REQUEST;
            end
            REQUEST:if(m_lock_ready)state<=RESULT;
            RESULT:if(m_result_valid&&m_result_ready)begin
                if(m_status==0)state<=HELD;else begin state<=IDLE;prefer_b<=!owner;end
            end
            HELD:if(m_unlock_valid&&m_unlock_ready)begin state<=IDLE;prefer_b<=!owner;end
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
