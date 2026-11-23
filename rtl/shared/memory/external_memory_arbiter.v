`timescale 1ns/1ps
`default_nettype none
// Fair arbitration across read AND write commands. Each client owns one
// request slot and one response slot. A stalled response occupies only that
// client's slot; other clients can keep using the single-outstanding cache.
module external_memory_arbiter #(
    parameter integer CLIENTS=4,
    parameter integer ADDR_WIDTH=23
)(
    input wire clk,input wire rst,input wire pause,
    input wire [CLIENTS-1:0] s_valid,output wire [CLIENTS-1:0] s_ready,
    input wire [CLIENTS-1:0] s_write,
    input wire [CLIENTS*ADDR_WIDTH-1:0] s_addr,
    input wire [CLIENTS*4-1:0] s_bytes,input wire [CLIENTS*72-1:0] s_data,
    output wire [CLIENTS-1:0] rsp_valid,input wire [CLIENTS-1:0] rsp_ready,
    output wire [CLIENTS*72-1:0] rsp_data,output wire [CLIENTS*8-1:0] rsp_status,
    output wire rd_valid,input wire rd_ready,output wire [ADDR_WIDTH-1:0] rd_addr,output wire [3:0] rd_bytes,
    input wire rd_rsp_valid,output wire rd_rsp_ready,input wire [71:0] rd_rsp_data,input wire [7:0] rd_rsp_status,
    output wire wr_valid,input wire wr_ready,output wire [ADDR_WIDTH-1:0] wr_addr,output wire [3:0] wr_bytes,output wire [71:0] wr_data,
    input wire wr_rsp_valid,output wire wr_rsp_ready,input wire [7:0] wr_rsp_status,
    output wire idle,output wire drained
);
    localparam integer CLIENT_WIDTH=CLIENTS<=1?1:$clog2(CLIENTS);
    localparam IDLE=0,READ_CMD=1,READ_WAIT=2,WRITE_CMD=3,WRITE_WAIT=4;
    reg [2:0] state;
    reg [CLIENTS-1:0] occupied,pending,responses;
    reg [ADDR_WIDTH-1:0] addresses[0:CLIENTS-1];
    reg [3:0] lengths[0:CLIENTS-1];
    reg [71:0] payloads[0:CLIENTS-1],results[0:CLIENTS-1];
    reg [7:0] statuses[0:CLIENTS-1];
    reg [CLIENTS-1:0] writes;
    reg [CLIENT_WIDTH-1:0] next_client,owner;
    reg [ADDR_WIDTH-1:0] active_address;
    reg [3:0] active_length;
    reg [71:0] active_payload;
    reg found;
    integer chosen,candidate,offset;
    always @*begin
        found=0;chosen=0;candidate=0;
        for(offset=0;offset<CLIENTS;offset=offset+1)begin
            candidate=next_client+offset;
            if(candidate>=CLIENTS)candidate=candidate-CLIENTS;
            if(!found&&pending[candidate])begin found=1;chosen=candidate;end
        end
    end
    assign s_ready={CLIENTS{!rst&&!pause}} & ~occupied;
    assign rsp_valid=responses;
    generate for(genvar i=0;i<CLIENTS;i=i+1)begin: response_ports
        assign rsp_data[i*72+:72]=results[i];
        assign rsp_status[i*8+:8]=statuses[i];
    end endgenerate
    assign rd_valid=!rst&&state==READ_CMD;
    assign rd_addr=active_address;assign rd_bytes=active_length;
    assign rd_rsp_ready=state==READ_WAIT;
    assign wr_valid=!rst&&state==WRITE_CMD;
    assign wr_addr=active_address;assign wr_bytes=active_length;assign wr_data=active_payload;
    assign wr_rsp_ready=state==WRITE_WAIT;
    assign drained=state==IDLE && !(|occupied) && !(|pending) && !(|responses);
    assign idle=drained && !(|s_valid);
    integer client;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;occupied<=0;pending<=0;responses<=0;writes<=0;next_client<=0;owner<=0;
            active_address<=0;active_length<=0;active_payload<=0;
            for(client=0;client<CLIENTS;client=client+1)begin
                addresses[client]<=0;lengths[client]<=0;payloads[client]<=0;results[client]<=0;statuses[client]<=0;
            end
        end else begin
            for(client=0;client<CLIENTS;client=client+1)begin
                if(responses[client]&&rsp_ready[client])begin responses[client]<=0;occupied[client]<=0;end
                if(s_valid[client]&&s_ready[client])begin
                    occupied[client]<=1;pending[client]<=1;writes[client]<=s_write[client];
                    addresses[client]<=s_addr[client*ADDR_WIDTH+:ADDR_WIDTH];
                    lengths[client]<=s_bytes[client*4+:4];payloads[client]<=s_data[client*72+:72];
                end
            end
            case(state)
                IDLE:if(found)begin
                    owner<=chosen;pending[chosen]<=0;
                    active_address<=addresses[chosen];active_length<=lengths[chosen];active_payload<=payloads[chosen];
                    next_client<=chosen+1==CLIENTS?0:chosen+1;
                    state<=writes[chosen]?WRITE_CMD:READ_CMD;
                end
                READ_CMD:if(rd_ready)state<=READ_WAIT;
                WRITE_CMD:if(wr_ready)state<=WRITE_WAIT;
                READ_WAIT:if(rd_rsp_valid)begin
                    results[owner]<=rd_rsp_data;statuses[owner]<=rd_rsp_status;responses[owner]<=1;state<=IDLE;
                end
                WRITE_WAIT:if(wr_rsp_valid)begin
                    results[owner]<=0;statuses[owner]<=wr_rsp_status;responses[owner]<=1;state<=IDLE;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
