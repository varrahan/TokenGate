`timescale 1ns/1ps
`default_nettype none
// Called only after the actual owned window lookup returned missing-key.
// The parent must hold the actual connection/admission fence through response
// retirement. Read-only: no shadow directory or caller-supplied high-water mark.
// Current request admission is the server path (odd client-initiated streams).
// No server-initiated streams exist in that path; missing even IDs are idle.
module http2_missing_stream_classifier #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire req_missing_key,
    input wire history_fence,input wire [USER_WIDTH-1:0] req_user,input wire [30:0] req_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
    output wire rsp_valid,input wire rsp_ready,output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,
    output wire [USER_WIDTH-1:0] rsp_user,output wire [30:0] rsp_stream,
    output reg rsp_closed,output reg [30:0] rsp_last_stream,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,GEOMETRY=1,CHECK=2,RAW_REQ=3,RAW_WAIT=4,RAW_CHECK=5,HW_REQ=6,HW_WAIT=7,DECIDE=8,RESULT=9;
    reg [3:0] state;reg missing_key,fence_lost;
    reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,work_floor,context_address;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes;
    reg [63:0] context_full,context_limit,contexts_end,raw_header,history;
    wire geometry_good=context_bytes>=256&&contexts>=work_floor&&contexts_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&context_limit<=contexts_end;
    wire slot_ready,slot_valid;wire [71:0] slot_data;wire [7:0] slot_status;
    assign req_ready=!rst&&state==IDLE;assign rsp_valid=state==RESULT;assign rsp_user=owner;assign rsp_stream=stream_id;
    assign idle=state==IDLE&&!req_valid;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==RAW_REQ||state==HW_REQ),.req_ready(slot_ready),.req_write(1'b0),
        .req_addr(state==HW_REQ?context_address+160:context_address),.req_bytes(4'd8),.req_data(72'd0),
        .result_valid(slot_valid),.result_ready(state==RAW_WAIT||state==HW_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle());
    task fail(input [7:0] status,input [7:0] detail);
        begin rsp_status<=status;rsp_detail<=detail;rsp_closed<=0;state<=RESULT;end
    endtask
    initial begin if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>30)$error("Unsupported classifier widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;missing_key<=0;fence_lost<=0;owner<=0;stream_id<=0;contexts<=0;work_floor<=0;context_address<=0;context_bytes<=0;
            context_full<=0;context_limit<=0;contexts_end<=0;raw_header<=0;history<=0;
            rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_closed<=0;rsp_last_stream<=0;
        end else begin
            if(state!=IDLE&&state!=RESULT&&!history_fence)fence_lost<=1;
            case(state)
                IDLE:if(req_valid&&req_ready)begin
                    owner<=req_user;stream_id<=req_stream;missing_key<=req_missing_key;fence_lost<=!history_fence;
                    contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;work_floor<=cfg_work_floor;
                    rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_closed<=0;rsp_last_stream<=0;state<=GEOMETRY;
                end
                GEOMETRY:begin
                    context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);
                    context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;
                    contexts_end<={1'b0,contexts}+{1'b0,context_bytes};state<=CHECK;
                end
                CHECK:begin
                    context_address<=context_full[MEMORY_ADDR_WIDTH-1:0];
                    if(!geometry_good)fail(2,1);
                    else if(!missing_key||fence_lost||!history_fence)fail(7,1);
                    else if(stream_id==0)fail(4,1);else state<=RAW_REQ;
                end
                RAW_REQ:if(slot_ready)state<=RAW_WAIT;
                RAW_WAIT:if(slot_valid)begin
                    if(slot_status!=0)begin rsp_memory_status<=slot_status;fail(5,1);end
                    else begin raw_header<=slot_data[63:0];state<=RAW_CHECK;end
                end
                RAW_CHECK:if(fence_lost||!history_fence)fail(7,2);
                    else if(raw_header[31:0]!=32'h48324331||!raw_header[32]||raw_header[39:36]!=0||raw_header[63:40]<16384)fail(3,1);
                    else if(!raw_header[33])fail(3,3); // The actual admission path supports server ownership.
                    else state<=HW_REQ;
                HW_REQ:if(slot_ready)state<=HW_WAIT;
                HW_WAIT:if(slot_valid)begin
                    if(slot_status!=0)begin rsp_memory_status<=slot_status;fail(5,2);end
                    else begin history<=slot_data[63:0];state<=DECIDE;end
                end
                DECIDE:if(fence_lost||!history_fence)fail(7,2);
                    else if(history[31:0]!=32'h48325731||history[63]||history[62:32]!=0&&!history[32])fail(3,2);
                    else begin rsp_last_stream<=history[62:32];rsp_closed<=stream_id[0]&&stream_id<=history[62:32];state<=RESULT;end
                RESULT:if(rsp_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
