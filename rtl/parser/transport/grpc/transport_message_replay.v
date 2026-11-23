`timescale 1ns/1ps
`default_nettype none
// Replay a staged, complete application message. A failed read terminates the
// packet with an explicit abort marker; a valid-looking prefix cannot commit.
module transport_message_replay #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,input wire start_valid,output wire start_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] start_base,input wire [31:0] start_bytes,input wire [USER_WIDTH-1:0] start_user,
    output wire [511:0] m_axis_tdata,output wire [63:0] m_axis_tkeep,output wire m_axis_tvalid,input wire m_axis_tready,
    output wire m_axis_tlast,output wire [USER_WIDTH-1:0] m_axis_tuser,output wire m_axis_abort,
    output wire result_valid,input wire result_ready,output reg [7:0] result_status,result_memory_status,
    output wire mem_valid,input wire mem_ready,output wire mem_write,output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,output wire [71:0] mem_data,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,output wire idle
);
    localparam IDLE=0,CHECK=1,READ_REQ=2,READ_WAIT=3,SEND=4,RESULT=5;
    reg [2:0] state;reg [MEMORY_ADDR_WIDTH-1:0] base;reg [31:0] remaining,offset;
    reg [USER_WIDTH-1:0] context_id;reg [511:0] beat_data;reg [63:0] beat_keep;reg [2:0] word_index;reg beat_last,aborted;
    integer replay_lane;
    wire [63:0] allocation_end={1'b0,base}+{32'd0,remaining};
    wire [MEMORY_ADDR_WIDTH-1:0] address=base+offset;
    wire [3:0] chunk=remaining>=8?4'd8:remaining[3:0];
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==READ_REQ),.req_ready(slot_ready),.req_write(1'b0),.req_addr(address),.req_bytes(chunk),.req_data(72'd0),
        .result_valid(slot_valid),.result_ready(state==READ_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign start_ready=!rst&&state==IDLE;assign idle=state==IDLE&&slot_idle&&!(start_valid&&start_ready);
    assign m_axis_tdata=beat_data;assign m_axis_tkeep=beat_keep;assign m_axis_tlast=beat_last;assign m_axis_tuser=context_id;
    assign m_axis_tvalid=state==SEND;assign m_axis_abort=aborted;assign result_valid=state==RESULT;
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;base<=0;remaining<=0;offset<=0;context_id<=0;beat_data<=0;beat_keep<=0;word_index<=0;beat_last<=0;aborted<=0;result_status<=0;result_memory_status<=0;end
        else case(state)
            IDLE:if(start_valid&&start_ready)begin
                base<=start_base;remaining<=start_bytes;offset<=0;context_id<=start_user;
                beat_data<=0;beat_keep<=0;word_index<=0;beat_last<=0;aborted<=0;result_status<=0;result_memory_status<=0;state<=CHECK;
            end
            CHECK:begin
                if(allocation_end>(64'd1<<MEMORY_ADDR_WIDTH))begin result_status<=1;aborted<=1;beat_last<=1;state<=SEND;end
                else if(remaining==0)begin beat_last<=1;state<=SEND;end
                else state<=READ_REQ;
            end
            READ_REQ:if(slot_ready)state<=READ_WAIT;
            READ_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin
                    result_status<=2;result_memory_status<=slot_status;beat_data<=0;beat_keep<=0;aborted<=1;beat_last<=1;state<=SEND;
                end else begin
                    for(replay_lane=0;replay_lane<8;replay_lane=replay_lane+1)beat_data[word_index*64+replay_lane*8+:8]<=replay_lane<chunk?slot_data[replay_lane*8+:8]:8'd0;
                    beat_keep[word_index*8+:8]<=chunk==8?8'hff:(8'h1<<chunk)-1'b1;
                    remaining<=remaining-chunk;offset<=offset+chunk;
                    if(remaining==chunk)begin beat_last<=1;state<=SEND;end
                    else if(word_index==7)begin beat_last<=0;state<=SEND;end
                    else begin word_index<=word_index+1'b1;state<=READ_REQ;end
                end
            end
            SEND:if(m_axis_tready)begin
                if(beat_last)state<=RESULT;
                else begin beat_data<=0;beat_keep<=0;word_index<=0;state<=READ_REQ;end
            end
            RESULT:if(result_ready)state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
