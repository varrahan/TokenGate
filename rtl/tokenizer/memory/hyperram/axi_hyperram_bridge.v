`timescale 1ns/1ps
`default_nettype none
// AXI4 frontend for a buffered HyperRAM transaction engine. Both interfaces
// use clk. A real 250 MHz / memory-clock boundary requires an AXI CDC adapter.
// One read and one write may be buffered independently. No host backpressure
// reaches a running HyperBus transaction: the command contains the full burst.
module axi_hyperram_bridge #(
    parameter ADDR_WIDTH=23
)(
    input wire clk,rst,
    input wire [ADDR_WIDTH-1:0] s_axi_araddr,
    input wire [7:0] s_axi_arlen,
    input wire [2:0] s_axi_arsize,
    input wire [1:0] s_axi_arburst,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [63:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output wire s_axi_rlast,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    input wire [ADDR_WIDTH-1:0] s_axi_awaddr,
    input wire [7:0] s_axi_awlen,
    input wire [2:0] s_axi_awsize,
    input wire [1:0] s_axi_awburst,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [63:0] s_axi_wdata,
    input wire [7:0] s_axi_wstrb,
    input wire s_axi_wlast,s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    output wire hb_cmd_valid,
    input wire hb_cmd_ready,
    output wire hb_cmd_write,
    output wire [ADDR_WIDTH-1:0] hb_cmd_address,
    output wire [6:0] hb_cmd_bytes,
    output wire [511:0] hb_cmd_data,
    output wire [63:0] hb_cmd_strobes,
    input wire hb_rsp_valid,
    output wire hb_rsp_ready,
    input wire [511:0] hb_rsp_data,
    input wire hb_rsp_error,
    output wire idle
);
    reg read_pending,read_issued,read_geometry;
    reg [ADDR_WIDTH-1:0] read_address;
    reg [7:0] read_length,read_index;
    reg [511:0] read_buffer;
    reg write_pending,write_issued,write_geometry,write_complete,write_overflow;
    reg [ADDR_WIDTH-1:0] write_address;
    reg [7:0] write_length;
    reg [3:0] write_count;
    reg [511:0] write_buffer;
    reg [63:0] write_strobes;
    reg [1:0] command_select,active;
    reg prefer_write;

    function geometry;
        input [ADDR_WIDTH-1:0] address;
        input [7:0] length;
        input [2:0] size;
        input [1:0] burst;
        reg [ADDR_WIDTH:0] finish;
        reg [12:0] page_finish;
        begin
            finish={1'b0,address}+(({1'b0,length}+9'd1)<<3);
            page_finish={1'b0,address[11:0]}+(({1'b0,length}+9'd1)<<3);
            geometry=length<8&&size==3&&burst==1&&address[2:0]==0&&
                finish<={1'b1,{ADDR_WIDTH{1'b0}}}&&page_finish<=13'd4096;
        end
    endfunction

    assign s_axi_arready=!rst&&!read_pending;
    assign s_axi_awready=!rst&&!write_pending;
    // Keep draining malformed overlong write bursts through their actual LAST.
    // A complete write is never sent to the memory before address/length checks.
    assign s_axi_wready=!rst&&!write_complete&&!s_axi_bvalid;
    assign s_axi_rdata=s_axi_rresp==0?read_buffer[read_index[2:0]*64+:64]:64'd0;
    assign s_axi_rlast=s_axi_rvalid&&read_index==read_length;
    assign hb_cmd_valid=!rst&&command_select!=0&&active==0;
    assign hb_cmd_write=command_select==2;
    assign hb_cmd_address=command_select==2?write_address:read_address;
    assign hb_cmd_bytes=command_select==2?({1'b0,write_length[2:0]}+4'd1)*8:
        ({1'b0,read_length[2:0]}+4'd1)*8;
    assign hb_cmd_data=command_select==2?write_buffer:512'd0;
    assign hb_cmd_strobes=command_select==2?write_strobes:64'd0;
    assign hb_rsp_ready=!rst&&active!=0;
    assign idle=!rst&&!read_pending&&!write_pending&&write_count==0&&!write_complete&&active==0&&command_select==0;

    wire read_waiting=read_pending&&!read_issued;
    wire write_waiting=write_pending&&write_complete&&!write_issued;
    always @(posedge clk)begin
        if(rst)begin
            read_pending<=0;read_issued<=0;read_geometry<=0;read_address<=0;read_length<=0;read_index<=0;read_buffer<=0;
            write_pending<=0;write_issued<=0;write_geometry<=0;write_address<=0;write_length<=0;
            write_complete<=0;write_overflow<=0;write_count<=0;write_buffer<=0;write_strobes<=0;
            command_select<=0;active<=0;prefer_write<=0;
            s_axi_rvalid<=0;s_axi_rresp<=0;s_axi_bvalid<=0;s_axi_bresp<=0;
        end else begin
            if(s_axi_arvalid&&s_axi_arready)begin
                read_pending<=1;read_issued<=0;read_address<=s_axi_araddr;read_length<=s_axi_arlen;read_index<=0;
                read_geometry<=geometry(s_axi_araddr,s_axi_arlen,s_axi_arsize,s_axi_arburst);
            end
            if(s_axi_awvalid&&s_axi_awready)begin
                write_pending<=1;write_issued<=0;write_address<=s_axi_awaddr;write_length<=s_axi_awlen;
                write_geometry<=geometry(s_axi_awaddr,s_axi_awlen,s_axi_awsize,s_axi_awburst);
            end
            if(s_axi_wvalid&&s_axi_wready)begin
                if(write_count<8)begin
                    write_buffer[write_count[2:0]*64+:64]<=s_axi_wdata;
                    write_strobes[write_count[2:0]*8+:8]<=s_axi_wstrb;
                    write_count<=write_count+1'b1;
                end else write_overflow<=1;
                if(s_axi_wlast)write_complete<=1;
            end
            if(s_axi_rvalid&&s_axi_rready)begin
                if(read_index==read_length)begin s_axi_rvalid<=0;read_pending<=0;read_issued<=0;end
                else read_index<=read_index+1'b1;
            end
            if(s_axi_bvalid&&s_axi_bready)begin
                s_axi_bvalid<=0;write_pending<=0;write_issued<=0;write_complete<=0;write_overflow<=0;
                write_count<=0;write_buffer<=0;write_strobes<=0;
            end
            if(active==0&&command_select==0)begin
                if(write_waiting&&(!read_waiting||prefer_write))begin
                    prefer_write<=0;
                    if(!write_geometry)begin write_issued<=1;s_axi_bvalid<=1;s_axi_bresp<=3;end
                    else if(write_overflow||write_count!={1'b0,write_length}+1)begin
                        write_issued<=1;s_axi_bvalid<=1;s_axi_bresp<=2;
                    end else command_select<=2;
                end else if(read_waiting)begin
                    prefer_write<=1;
                    if(!read_geometry)begin read_issued<=1;s_axi_rvalid<=1;s_axi_rresp<=3;read_buffer<=0;end
                    else command_select<=1;
                end
            end
            if(hb_cmd_valid&&hb_cmd_ready)begin
                active<=command_select;command_select<=0;
                if(command_select==1)read_issued<=1;else write_issued<=1;
            end
            if(hb_rsp_valid&&hb_rsp_ready)begin
                if(active==1)begin read_buffer<=hb_rsp_data;s_axi_rvalid<=1;s_axi_rresp<=hb_rsp_error?2'd2:2'd0;end
                else begin s_axi_bvalid<=1;s_axi_bresp<=hb_rsp_error?2'd2:2'd0;end
                active<=0;
            end
        end
    end
endmodule
`default_nettype wire
