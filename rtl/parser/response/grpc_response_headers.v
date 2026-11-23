`timescale 1ns/1ps
`default_nettype none
// Stateless HPACK response blocks. Static :status 200 and never-indexed
// literals do not create a connection-specific encoder table. The caller owns
// RPC ordering, durable transmission intent, actual LOAD authority and credit.
// Each block fits one 512-bit beat, below the minimum HTTP/2 frame-size limit.
// A private abort is legal only with the actual outer wire-arbiter fence.
module grpc_response_headers #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,rst,
    input wire req_valid,output wire req_ready,
    input wire [1:0] req_kind, // 0 initial; 1 trailers; 2 trailers-only error
    input wire [1:0] req_encoding, // 0 application/grpc; 1 +proto; 2 +json
    input wire [31:0] req_grpc_status,
    input wire [USER_WIDTH-1:0] req_user,input wire [30:0] req_stream,
    input wire abort_valid,output wire abort_ready,input wire wire_fenced,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,
    output wire m_axis_tx_tlast,output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire result_valid,input wire result_ready,
    output reg [7:0] result_status,output reg result_tx_emitted,
    output wire [1:0] result_kind,output wire [USER_WIDTH-1:0] result_user,
    output wire [30:0] result_stream,output wire [6:0] result_wire_bytes,
    output wire idle
);
    localparam IDLE=0,CHECK=1,BUILD=2,TX=3,RESULT=4;
    localparam [175:0] PROTO="application/grpc+proto";
    localparam [175:0] JSON={"application/grpc+json",8'd0};
    localparam [175:0] GRPC={"application/grpc",48'd0};
    localparam [87:0] STATUS_NAME="grpc-status";
    reg [2:0] state;reg [1:0] kind,encoding;
    reg [31:0] status_code;reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id;
    reg [511:0] packet;reg [6:0] packet_bytes;
    reg [511:0] next_packet;integer cursor,content_bytes,index,payload_bytes;
    wire abort_take=abort_valid&&abort_ready;
    assign req_ready=!rst&&state==IDLE&&!abort_valid;
    // Completion wins a race with abort. A held completed result is preserved.
    assign abort_ready=!rst&&wire_fenced&&!(state==TX&&m_axis_tx_tready);
    assign m_axis_tx_tdata=packet;
    assign m_axis_tx_tkeep=(64'h1<<packet_bytes)-1'b1;
    assign m_axis_tx_tvalid=!rst&&state==TX;
    assign m_axis_tx_tlast=1'b1;assign m_axis_tx_tuser=owner;
    assign result_valid=state==RESULT;assign result_kind=kind;
    assign result_user=owner;assign result_stream=stream_id;
    assign result_wire_bytes=result_tx_emitted?packet_bytes:7'd0;
    assign idle=state==IDLE&&!req_valid;
    always @*begin
        next_packet=0;cursor=9;
        content_bytes=encoding==1?22:encoding==2?21:16;
        if(kind!=1)begin
            next_packet[cursor*8+:8]=8'h88;cursor=cursor+1;
            // Never-indexed literal, static-table name 31, uncompressed value.
            next_packet[cursor*8+:8]=8'h1f;cursor=cursor+1;
            next_packet[cursor*8+:8]=8'h10;cursor=cursor+1;
            next_packet[cursor*8+:8]=content_bytes;cursor=cursor+1;
            for(index=0;index<22;index=index+1)if(index<content_bytes)begin
                next_packet[cursor*8+:8]=encoding==1?PROTO[(21-index)*8+:8]:
                    encoding==2?JSON[(21-index)*8+:8]:GRPC[(21-index)*8+:8];
                cursor=cursor+1;
            end
        end
        if(kind!=0)begin
            next_packet[cursor*8+:8]=8'h10;cursor=cursor+1;
            next_packet[cursor*8+:8]=8'd11;cursor=cursor+1;
            for(index=0;index<11;index=index+1)begin
                next_packet[cursor*8+:8]=STATUS_NAME[(10-index)*8+:8];cursor=cursor+1;
            end
            next_packet[cursor*8+:8]=status_code>=10?8'd2:8'd1;cursor=cursor+1;
            if(status_code>=10)begin next_packet[cursor*8+:8]=8'h31;cursor=cursor+1;end
            next_packet[cursor*8+:8]=8'h30+(status_code>=10?status_code-10:status_code);cursor=cursor+1;
        end
        payload_bytes=cursor-9;
        next_packet[7:0]=0;next_packet[15:8]=0;next_packet[23:16]=payload_bytes;
        next_packet[31:24]=8'd1;next_packet[39:32]=kind==0?8'h04:8'h05;
        next_packet[47:40]={1'b0,stream_id[30:24]};next_packet[55:48]=stream_id[23:16];
        next_packet[63:56]=stream_id[15:8];next_packet[71:64]=stream_id[7:0];
    end
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;kind<=0;encoding<=0;status_code<=0;owner<=0;stream_id<=0;
            packet<=0;packet_bytes<=0;result_status<=0;result_tx_emitted<=0;end
        else if(abort_take&&state!=IDLE&&state!=RESULT)begin
            result_status<=5;result_tx_emitted<=0;state<=RESULT;
        end else case(state)
            IDLE:if(req_valid&&req_ready)begin
                kind<=req_kind;encoding<=req_encoding;status_code<=req_grpc_status;
                owner<=req_user;stream_id<=req_stream;result_status<=0;result_tx_emitted<=0;packet_bytes<=0;state<=CHECK;
            end
            CHECK:if(kind>2)begin result_status<=1;state<=RESULT;end
                else if(stream_id==0||!stream_id[0])begin result_status<=2;state<=RESULT;end
                else if(encoding>2)begin result_status<=3;state<=RESULT;end
                else if(status_code>16||kind==0&&status_code!=0||kind==2&&status_code==0)begin result_status<=4;state<=RESULT;end
                else state<=BUILD;
            BUILD:begin packet<=next_packet;packet_bytes<=cursor;state<=TX;end
            TX:if(m_axis_tx_tready)begin result_tx_emitted<=1;state<=RESULT;end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
