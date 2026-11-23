`timescale 1ns/1ps
`default_nettype none
// Actual failed-packet owner supplies authority and retains the history fence
// through result ACK. Read the real closed context/high-water record; never
// infer last-stream from a shadow register or a caller-supplied stream number.
// Existing wire/GPU owners must drain before GOAWAY. Host close is a distinct
// external handshake after GOAWAY's actual wire retirement, not a queue ACK.
module http2_local_error_response #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,rst,
    input wire req_valid,output wire req_ready,input wire req_authority,
    input wire [USER_WIDTH-1:0] req_user,input wire [31:0] req_http2_error,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
    input wire history_fence,peer_drained,
    output wire rsp_valid,input wire rsp_ready,
    output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,
    output wire transport_close_valid,input wire transport_close_ready,
    output wire [USER_WIDTH-1:0] transport_close_user,
    output wire [31:0] transport_close_http2_error,output wire [30:0] transport_close_last_stream,
    output wire [7:0] transport_close_status,transport_close_detail,transport_close_memory_status,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire busy,idle
);
    localparam IDLE=0,GEOMETRY=1,CHECK=2,RAW_REQ=3,RAW_WAIT=4,RAW_CHECK=5,
        HW_REQ=6,HW_WAIT=7,HW_CHECK=8,DRAIN=9,TX=10,CLOSE=11,RESULT=12;
    reg [3:0] state;reg authority,fence_lost;
    reg [USER_WIDTH-1:0] owner;reg [31:0] error_code;reg [30:0] last_stream;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,work_floor,context_address;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes;
    reg [63:0] context_full,context_limit,contexts_end,raw_header,history;
    wire geometry_good=context_bytes>=256&&context_bytes[7:0]==0&&contexts>=work_floor&&
        contexts_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&context_limit<=contexts_end;
    wire fence_good=history_fence&&!fence_lost;
    wire slot_ready,slot_valid;wire [71:0] slot_data;wire [7:0] slot_status;
    assign req_ready=!rst&&state==IDLE;assign rsp_valid=!rst&&state==RESULT;
    assign transport_close_valid=!rst&&state==CLOSE;
    assign transport_close_user=owner;assign transport_close_http2_error=error_code;
    assign transport_close_last_stream=last_stream;
    assign transport_close_status=rsp_status;assign transport_close_detail=rsp_detail;
    assign transport_close_memory_status=rsp_memory_status;
    assign busy=state!=IDLE;assign idle=state==IDLE&&!req_valid;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==RAW_REQ||state==HW_REQ),.req_ready(slot_ready),.req_write(1'b0),
        .req_addr(state==HW_REQ?context_address+160:context_address),.req_bytes(4'd8),.req_data(72'd0),
        .result_valid(slot_valid),.result_ready(state==RAW_WAIT||state==HW_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle());
    reg [511:0] packet;integer lane;
    always @*begin
        packet=0;packet[23:16]=8;packet[31:24]=7;
        for(lane=0;lane<4;lane=lane+1)begin
            packet[72+lane*8+:8]=({1'b0,last_stream}>>(24-8*lane));
            packet[104+lane*8+:8]=(error_code>>(24-8*lane));
        end
    end
    assign m_axis_tx_tdata=packet;assign m_axis_tx_tkeep=64'h1ffff;
    assign m_axis_tx_tvalid=!rst&&state==TX;assign m_axis_tx_tlast=1;assign m_axis_tx_tuser=owner;
    task fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status,input close_host);
        begin rsp_status<=status;rsp_detail<=detail;rsp_memory_status<=memory_status;state<=close_host?CLOSE:RESULT;end
    endtask
    initial begin if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<10||MEMORY_ADDR_WIDTH>30)$error("Unsupported local-error widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;authority<=0;fence_lost<=0;owner<=0;error_code<=0;last_stream<=0;
            contexts<=0;work_floor<=0;context_address<=0;context_bytes<=0;
            context_full<=0;context_limit<=0;contexts_end<=0;raw_header<=0;history<=0;
            rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;
        end else begin
            if(state!=IDLE&&state!=RESULT&&!history_fence)fence_lost<=1;
            case(state)
                IDLE:if(req_valid&&req_ready)begin
                    authority<=req_authority;owner<=req_user;error_code<=req_http2_error;last_stream<=0;
                    contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;work_floor<=cfg_work_floor;
                    fence_lost<=!history_fence;rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;state<=GEOMETRY;
                end
                GEOMETRY:begin
                    context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);
                    context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;
                    contexts_end<={1'b0,contexts}+{1'b0,context_bytes};state<=CHECK;
                end
                CHECK:begin
                    context_address<=context_full[MEMORY_ADDR_WIDTH-1:0];
                    if(!authority||!fence_good||error_code==0)fail(7,1,0,0);
                    else if(!geometry_good)fail(2,1,0,1);else state<=RAW_REQ;
                end
                RAW_REQ:if(slot_ready)state<=RAW_WAIT;
                RAW_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(5,1,slot_status,1);
                    else begin raw_header<=slot_data[63:0];state<=RAW_CHECK;end
                end
                RAW_CHECK:if(!fence_good)fail(7,2,0,1);
                    else if(raw_header!=0)fail(3,1,0,1);else state<=HW_REQ;
                HW_REQ:if(slot_ready)state<=HW_WAIT;
                HW_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(5,2,slot_status,1);
                    else begin history<=slot_data[63:0];state<=HW_CHECK;end
                end
                HW_CHECK:if(!fence_good)fail(7,2,0,1);
                    else if(history[31:0]!=32'h48325731||history[63]||history[62:32]!=0&&!history[32])fail(3,2,0,1);
                    else begin last_stream<=history[62:32];state<=DRAIN;end
                DRAIN:if(!fence_good)fail(7,2,0,1);else if(peer_drained)state<=TX;
                // Once offered, drain the real wire promise even if the fence
                // subsequently breaks. Never withdraw VALID or change bytes.
                TX:if(m_axis_tx_tready)begin
                    if(!fence_good)begin rsp_status<=7;rsp_detail<=3;end
                    state<=CLOSE;
                end
                CLOSE:if(transport_close_ready)begin
                    if(!fence_good)begin rsp_status<=7;rsp_detail<=3;end
                    state<=RESULT;
                end
                RESULT:if(rsp_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
