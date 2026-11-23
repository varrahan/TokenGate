`timescale 1ns/1ps
`default_nettype none
// S27KS0642 startup, in the memory word-clock domain. power_good and phy_ready
// must be qualified synchronous inputs. RESET# invalidates the memory image.
module hyperram_startup #(
    parameter MEMORY_CLOCK_HZ=200000000,
    parameter CONFIG_LATENCY=7,
    parameter FIXED_LATENCY=1
)(
    input wire clk,rst,power_good,phy_ready,
    input wire contents_reload_ack,transactions_idle,
    output wire fabric_reset,engine_reset,engine_enable,phy_reset_n,
    output wire memory_ready,
    output reg startup_fault,
    output reg [7:0] startup_detail,
    output wire [3:0] startup_phase,
    output reg contents_lost,
    output reg [15:0] device_id0,device_id1,config_readback,
    output wire [3:0] engine_latency,
    output wire engine_fixed_latency,
    output wire init_cmd_valid,
    input wire init_cmd_ready,
    output wire init_cmd_write,
    output wire [22:0] init_cmd_address,
    output wire [511:0] init_cmd_data,
    input wire init_rsp_valid,
    output wire init_rsp_ready,
    input wire [511:0] init_rsp_data,
    input wire init_rsp_error,
    input wire [7:0] init_rsp_detail
);
    localparam RESET_LOW=0,POWER_WAIT=1,SEND_ID0=2,WAIT_ID0=3,
        SEND_ID1=4,WAIT_ID1=5,SEND_CONFIG=6,WAIT_CONFIG=7,
        SEND_VERIFY=8,WAIT_VERIFY=9,READY=10,FAULT=11;
    localparam MIN_LATENCY=MEMORY_CLOCK_HZ>166000000?7:MEMORY_CLOCK_HZ>133000000?6:
        MEMORY_CLOCK_HZ>104000000?5:MEMORY_CLOCK_HZ>85000000?4:3;
    // Infineon 002-24692 Rev. *I Tables 22/25: 200 ns reset pulse and
    // 150 us after RESET# rises. Use the cold-start interval on every reset.
    localparam RESET_CYCLES=((MEMORY_CLOCK_HZ/1000)*200+999999)/1000000;
    localparam POWERUP_CYCLES=((MEMORY_CLOCK_HZ/1000)*150+999)/1000;
    localparam [3:0] LATENCY_CODE=CONFIG_LATENCY==3?14:CONFIG_LATENCY==4?15:
        CONFIG_LATENCY==5?0:CONFIG_LATENCY==6?1:2;
    // Preserve reserved fields, normal operation, 34-ohm drive and burst setup.
    localparam [15:0] CONFIG_WORD=16'h8f07|({12'd0,LATENCY_CODE}<<4)|(FIXED_LATENCY?16'h0008:16'h0000);
    reg [3:0] state;
    reg [31:0] timer;
    reg configured;
    assign fabric_reset=rst||!power_good||!phy_ready;
    assign engine_reset=fabric_reset||state==RESET_LOW;
    assign phy_reset_n=!engine_reset;
    assign memory_ready=!fabric_reset&&state==READY;
    assign engine_enable=!fabric_reset&&state>=SEND_ID0&&state<=READY;
    assign startup_phase=state;
    assign engine_latency=configured?CONFIG_LATENCY:7;
    assign engine_fixed_latency=configured?FIXED_LATENCY!=0:1'b1;
    assign init_cmd_valid=!fabric_reset&&(state==SEND_ID0||state==SEND_ID1||state==SEND_CONFIG||state==SEND_VERIFY);
    assign init_cmd_write=state==SEND_CONFIG;
    assign init_cmd_address=state==SEND_ID0?23'd0:state==SEND_ID1?23'd2:23'h1000;
    assign init_cmd_data={496'd0,CONFIG_WORD};
    assign init_rsp_ready=!fabric_reset&&(state==WAIT_ID0||state==WAIT_ID1||state==WAIT_CONFIG||state==WAIT_VERIFY);
    always @(posedge clk)begin
        if(fabric_reset)begin
            state<=RESET_LOW;timer<=RESET_CYCLES-1;configured<=0;
            startup_fault<=0;startup_detail<=0;contents_lost<=1;
            device_id0<=0;device_id1<=0;config_readback<=0;
        end else begin
            if(contents_reload_ack&&memory_ready&&transactions_idle)contents_lost<=0;
            case(state)
                RESET_LOW:if(timer==0)begin state<=POWER_WAIT;timer<=POWERUP_CYCLES-1;end
                    else timer<=timer-1'b1;
                POWER_WAIT:if(timer==0)state<=SEND_ID0;else timer<=timer-1'b1;
                SEND_ID0:if(init_cmd_valid&&init_cmd_ready)state<=WAIT_ID0;
                SEND_ID1:if(init_cmd_valid&&init_cmd_ready)state<=WAIT_ID1;
                SEND_CONFIG:if(init_cmd_valid&&init_cmd_ready)state<=WAIT_CONFIG;
                SEND_VERIFY:if(init_cmd_valid&&init_cmd_ready)state<=WAIT_VERIFY;
                WAIT_ID0,WAIT_ID1,WAIT_CONFIG,WAIT_VERIFY:if(init_rsp_valid&&init_rsp_ready)begin
                    if(init_rsp_error)begin
                        startup_fault<=1;startup_detail<=8'h20|init_rsp_detail;state<=FAULT;
                    end else case(state)
                        WAIT_ID0:begin
                            device_id0<=init_rsp_data[15:0];
                            if(init_rsp_data[15:0]!=16'h0c81)begin startup_fault<=1;startup_detail<=8'h11;state<=FAULT;end
                            else state<=SEND_ID1;
                        end
                        WAIT_ID1:begin
                            device_id1<=init_rsp_data[15:0];
                            if(init_rsp_data[15:0]!=16'h0001)begin startup_fault<=1;startup_detail<=8'h12;state<=FAULT;end
                            else state<=SEND_CONFIG;
                        end
                        WAIT_CONFIG:begin configured<=1;state<=SEND_VERIFY;end
                        WAIT_VERIFY:begin
                            config_readback<=init_rsp_data[15:0];
                            if(init_rsp_data[15:0]!=CONFIG_WORD)begin startup_fault<=1;startup_detail<=8'h13;state<=FAULT;end
                            else state<=READY;
                        end
                    endcase
                end
                READY:begin end
                FAULT:begin end
                default:begin startup_fault<=1;startup_detail<=8'h1f;state<=FAULT;end
            endcase
        end
    end
    initial begin
        if(MEMORY_CLOCK_HZ<85000000||MEMORY_CLOCK_HZ>200000000||CONFIG_LATENCY<MIN_LATENCY||CONFIG_LATENCY>7)
            $error("Invalid HyperRAM startup clock/latency setting");
        if(FIXED_LATENCY!=0&&FIXED_LATENCY!=1)$error("FIXED_LATENCY must be zero or one");
    end
endmodule
`default_nettype wire
