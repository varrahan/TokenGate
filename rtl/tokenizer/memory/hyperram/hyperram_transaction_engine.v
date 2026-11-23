`timescale 1ns/1ps
`default_nettype none
// S27KS0642 command/data sequencer, one 16-bit DDR word per PHY cycle.
// PHY words place the first wire byte in [15:8]. PHY input words must already
// be safely captured from RWDS and transferred into clk; this is not a PHY.
// Reference: Infineon 002-24692 Rev. *I, Tables 3/5/6/9 and Figures 9/11/13.
module hyperram_transaction_engine #(
    parameter MEMORY_CLOCK_HZ=200000000
)(
    input wire clk,rst,enable,
    input wire cmd_valid,
    output wire cmd_ready,
    input wire cmd_write,cmd_register,
    input wire [22:0] cmd_address,
    input wire [6:0] cmd_bytes,
    input wire [511:0] cmd_data,
    input wire [63:0] cmd_strobes,
    input wire [3:0] cfg_latency,
    input wire cfg_fixed_latency,
    output wire rsp_valid,
    input wire rsp_ready,
    output wire [511:0] rsp_data,
    output reg rsp_error,
    output reg [7:0] rsp_detail,
    output wire phy_cs_n,phy_clock_enable,phy_dq_oe,
    output wire [15:0] phy_tx_word,
    output wire phy_rwds_oe,
    output wire [1:0] phy_tx_mask,
    input wire phy_latency_extra,
    input wire phy_rx_valid,
    input wire [15:0] phy_rx_word,
    input wire phy_fault,
    output wire phy_rx_enable,phy_rx_flush,
    output wire idle
);
    localparam IDLE=0,SELECT=1,CA=2,LATENCY=3,WRITE=4,READ=5,END_CLOCK=6,RECOVER=7,RESULT=8;
    localparam MIN_LATENCY=MEMORY_CLOCK_HZ>166000000?7:MEMORY_CLOCK_HZ>133000000?6:
        MEMORY_CLOCK_HZ>104000000?5:MEMORY_CLOCK_HZ>85000000?4:3;
    // Below the device's 1 us CS-low limit for its 105 C grade.
    localparam MAX_ACTIVE_CYCLES=(MEMORY_CLOCK_HZ/1000000)*9/10;
    localparam RECOVERY_CYCLES=((MEMORY_CLOCK_HZ/1000000)*40+999)/1000;
    reg [3:0] state;
    reg write_mode,register_mode,fixed_latency,double_latency;
    reg [3:0] latency;
    reg [4:0] latency_left;
    reg [1:0] ca_index;
    reg [5:0] word_index,word_count;
    reg [47:0] command_address;
    reg [511:0] write_buffer,read_buffer;
    reg [63:0] strobes;
    reg [15:0] active_cycles,recovery_left;
    wire active=state==SELECT||state==CA||state==LATENCY||state==WRITE||state==READ;
    wire [23:0] request_end={1'b0,cmd_address}+cmd_bytes;
    wire register_address_read=cmd_address==0||cmd_address==2||cmd_address==23'h1000||cmd_address==23'h1002||
        (cmd_address>=23'h2000&&cmd_address<=23'h2022);
    wire register_address_write=cmd_address==23'h1000||cmd_address==23'h1002;
    wire request_good=cmd_bytes!=0&&cmd_bytes<=64&&!cmd_bytes[0]&&!cmd_address[0]&&request_end<=24'h800000&&
        cfg_latency>=MIN_LATENCY&&cfg_latency<=7&&(!cmd_register||
        cmd_bytes==2&&(cmd_write?register_address_write&&cmd_strobes[1:0]==3:register_address_read));
    wire [15:0] outgoing=write_buffer[word_index[4:0]*16+:16];
    wire [1:0] outgoing_strobes=strobes[word_index[4:0]*2+:2];
    assign cmd_ready=!rst&&enable&&state==IDLE;
    assign rsp_valid=!rst&&state==RESULT;
    assign rsp_data=rsp_error?512'd0:read_buffer;
    assign phy_cs_n=rst||!(active||state==END_CLOCK);
    assign phy_clock_enable=!rst&&(state==CA||state==LATENCY||state==WRITE||state==READ);
    assign phy_dq_oe=!rst&&(state==CA||state==WRITE);
    assign phy_tx_word=state==CA?command_address[47:32]:state==WRITE?
        (register_mode?outgoing:{outgoing[7:0],outgoing[15:8]}):16'd0;
    // Provide a low mask preamble after the memory has released CA-phase RWDS.
    // Register writes never drive RWDS, even while writing their data word.
    assign phy_rwds_oe=!rst&&write_mode&&!register_mode&&
        (state==WRITE||state==LATENCY&&latency_left==1);
    assign phy_tx_mask=state==WRITE?{!outgoing_strobes[0],!outgoing_strobes[1]}:2'b00;
    assign phy_rx_enable=!rst&&state==READ;
    assign phy_rx_flush=rst||state!=READ;
    assign idle=!rst&&state==IDLE;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;write_mode<=0;register_mode<=0;fixed_latency<=0;double_latency<=0;latency<=0;latency_left<=0;
            ca_index<=0;word_index<=0;word_count<=0;command_address<=0;write_buffer<=0;read_buffer<=0;strobes<=0;
            active_cycles<=0;recovery_left<=0;rsp_error<=0;rsp_detail<=0;
        end else begin
            case(state)
                IDLE:if(cmd_valid&&cmd_ready)begin
                    write_mode<=cmd_write;register_mode<=cmd_register;fixed_latency<=cfg_fixed_latency;
                    latency<=cfg_latency;word_count<=cmd_bytes>>1;word_index<=0;ca_index<=0;
                    command_address<={!cmd_write,cmd_register,1'b1,10'd0,cmd_address[22:4],13'd0,cmd_address[3:1]};
                    write_buffer<=cmd_data;strobes<=cmd_strobes;read_buffer<=0;rsp_error<=0;rsp_detail<=0;active_cycles<=0;
                    if(request_good)state<=SELECT;else begin rsp_error<=1;rsp_detail<=1;state<=RESULT;end
                end
                SELECT:state<=CA;
                CA:begin
                    command_address<=command_address<<16;
                    if(ca_index==1)double_latency<=fixed_latency||phy_latency_extra;
                    if(ca_index==2)begin
                        if(register_mode&&write_mode)state<=WRITE;
                        else begin
                            // The third CA word overlaps the first latency cycle.
                            latency_left<=double_latency?latency*2-1:latency-1;
                            state<=LATENCY;
                        end
                    end else ca_index<=ca_index+1'b1;
                end
                LATENCY:if(latency_left==1)state<=write_mode?WRITE:READ;
                    else latency_left<=latency_left-1'b1;
                WRITE:if(word_index+1>=word_count)state<=END_CLOCK;
                    else word_index<=word_index+1'b1;
                READ:if(phy_rx_valid)begin
                    read_buffer[word_index[4:0]*16+:16]<=register_mode?phy_rx_word:{phy_rx_word[7:0],phy_rx_word[15:8]};
                    if(word_index+1>=word_count)state<=END_CLOCK;
                    else word_index<=word_index+1'b1;
                end
                END_CLOCK:begin recovery_left<=RECOVERY_CYCLES;state<=RECOVER;end
                RECOVER:if(recovery_left==1)state<=RESULT;else recovery_left<=recovery_left-1'b1;
                RESULT:if(rsp_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
            if(active)begin
                active_cycles<=active_cycles+1'b1;
                if(phy_fault||active_cycles>=MAX_ACTIVE_CYCLES-2)begin
                    rsp_error<=1;rsp_detail<=phy_fault?8'd3:8'd2;read_buffer<=0;state<=END_CLOCK;
                end
            end
        end
    end
    initial begin
        if(MEMORY_CLOCK_HZ<85000000||MEMORY_CLOCK_HZ>200000000)
            $error("HyperRAM engine supports clock settings from 85 to 200 MHz");
    end
endmodule
`default_nettype wire
