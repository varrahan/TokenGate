`timescale 1ns/1ps
`default_nettype none
// AXI-Lite schema staging and durable apply. The system owner must fence new
// requests and drain all existing schema users before granting cfg_unlock;
// decoder-local quiescence alone does not grant whole-system ownership.
// Hold the grant through the apply B response. No payload configuration words.
module parser_schema_mmio #(
    parameter integer ENTRIES=16,
    parameter integer INDEX_WIDTH=(ENTRIES>1?$clog2(ENTRIES):1)
)(
    input wire clk,input wire rst,
    input wire [15:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
    input wire [15:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
    input wire cfg_unlock,input wire cfg_quiescent,
    output wire cfg_schema_valid,input wire cfg_schema_ready,
    output reg [INDEX_WIDTH-1:0] cfg_schema_index,
    output reg [255:0] cfg_schema_key,output reg [5:0] cfg_schema_key_length,
    output reg cfg_schema_json_enable,output reg [28:0] cfg_schema_field,output reg cfg_schema_proto_enable,
    output reg [31:0] schema_epoch,output reg schema_committed,output wire busy
);
    localparam COLLECT=0,EXECUTE=1,ISSUE=2,DURABLE=3,RESPONSE=4;
    localparam OKAY=2'b00,SLVERR=2'b10,DECERR=2'b11;
    reg [2:0] state;
    reg aw_have,w_have;
    reg [15:0] address;
    reg [31:0] write_data;
    reg [3:0] write_strobes;
    reg [31:0] staged_index,staged_length,staged_flags,staged_field;
    reg [255:0] staged_key;
    wire [511:0] register_bank;
    wire [31:0] merged;
    wire padding_good=(staged_key>>(staged_length*8))==0;
    wire schema_good=staged_index<ENTRIES&&staged_length<=32&&staged_flags<=3&&
        staged_field[31:29]==0&&(!staged_flags[0]||padding_good)&&(!staged_flags[1]||staged_field!=0);
    assign s_axi_awready=!rst&&state==COLLECT&&!aw_have;
    assign s_axi_wready=!rst&&state==COLLECT&&!w_have;
    assign s_axi_arready=!rst&&(!s_axi_rvalid||s_axi_rready);
    assign cfg_schema_valid=!rst&&state==ISSUE;
    assign busy=state==ISSUE||state==DURABLE;
    assign register_bank[0*32+:32]=32'h50534331;
    assign register_bank[1*32+:32]={29'd0,cfg_quiescent,cfg_unlock,busy};
    assign register_bank[2*32+:32]=0;
    assign register_bank[3*32+:32]=schema_epoch;
    assign register_bank[4*32+:32]=staged_index;
    assign register_bank[5*32+:32]=staged_length;
    assign register_bank[6*32+:32]=staged_flags;
    assign register_bank[7*32+:32]=staged_field;
    assign register_bank[8*32+:256]=staged_key;
    function [31:0] value(input [15:0] a,input [511:0] bank);
        begin value=a[1:0]==0&&a<=16'h003c ? bank[a[5:2]*32+:32] : 32'd0;end
    endfunction
    function [31:0] merge_bytes(input [31:0] old_value,input [31:0] new_value,input [3:0] strobes);
        integer lane;
        begin
            merge_bytes=old_value;
            for(lane=0;lane<4;lane=lane+1)if(strobes[lane])merge_bytes[lane*8+:8]=new_value[lane*8+:8];
        end
    endfunction
    assign merged=merge_bytes(value(address,register_bank),write_data,write_strobes);
    task respond(input [1:0] status);
        begin s_axi_bresp<=status;s_axi_bvalid<=1;state<=RESPONSE;end
    endtask
    initial begin if(ENTRIES<1||ENTRIES>16||INDEX_WIDTH<1||INDEX_WIDTH>4||2**INDEX_WIDTH<ENTRIES)$error("Unsupported schema MMIO dimensions");end
    always @(posedge clk)begin
        if(rst)begin
            state<=COLLECT;aw_have<=0;w_have<=0;address<=0;write_data<=0;write_strobes<=0;
            s_axi_bresp<=0;s_axi_bvalid<=0;s_axi_rdata<=0;s_axi_rresp<=0;s_axi_rvalid<=0;
            staged_index<=0;staged_length<=0;staged_flags<=0;staged_field<=0;staged_key<=0;
            cfg_schema_index<=0;cfg_schema_key<=0;cfg_schema_key_length<=0;
            cfg_schema_json_enable<=0;cfg_schema_field<=0;cfg_schema_proto_enable<=0;
            schema_epoch<=0;schema_committed<=0;
        end else begin
            schema_committed<=0;
            if(s_axi_awvalid&&s_axi_awready)begin address<=s_axi_awaddr;aw_have<=1;end
            if(s_axi_wvalid&&s_axi_wready)begin write_data<=s_axi_wdata;write_strobes<=s_axi_wstrb;w_have<=1;end
            if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
            if(s_axi_arvalid&&s_axi_arready)begin
                s_axi_rvalid<=1;s_axi_rdata<=value(s_axi_araddr,register_bank);
                s_axi_rresp<=s_axi_araddr[1:0]==0&&s_axi_araddr<=16'h003c ? OKAY : DECERR;
            end
            case(state)
                COLLECT:if(aw_have&&w_have)state<=EXECUTE;
                EXECUTE:begin
                    if(address[1:0]!=0)respond(SLVERR);
                    else if(address>16'h003c)respond(DECERR);
                    else if(write_strobes==0)respond(OKAY);
                    else if(address==16'h0008)begin
                        if(merge_bytes(0,write_data,write_strobes)!=1||!cfg_unlock||!cfg_quiescent||!schema_good||schema_epoch==32'hffffffff)respond(SLVERR);
                        else begin
                            cfg_schema_index<=staged_index[INDEX_WIDTH-1:0];cfg_schema_key<=staged_key;
                            cfg_schema_key_length<=staged_length[5:0];cfg_schema_field<=staged_field[28:0];
                            cfg_schema_json_enable<=staged_flags[0];cfg_schema_proto_enable<=staged_flags[1];state<=ISSUE;
                        end
                    end else if(address<16'h0010)respond(SLVERR);
                    else begin
                        case(address)
                            16'h0010:staged_index<=merged;
                            16'h0014:staged_length<=merged;
                            16'h0018:staged_flags<=merged;
                            16'h001c:staged_field<=merged;
                            default:staged_key[(address[5:2]-8)*32+:32]<=merged;
                        endcase
                        respond(OKAY);
                    end
                end
                ISSUE:if(cfg_schema_ready)state<=DURABLE;
                // Native schema CAM accepts first, then writes every key byte.
                // Its ready/quiescent returns only after the final durable row.
                DURABLE:if(cfg_schema_ready&&cfg_quiescent)begin
                    schema_epoch<=schema_epoch+1'b1;schema_committed<=1;respond(OKAY);
                end
                RESPONSE:if(s_axi_bvalid&&s_axi_bready)begin
                    s_axi_bvalid<=0;aw_have<=0;w_have<=0;state<=COLLECT;
                end
                default:state<=COLLECT;
            endcase
        end
    end
endmodule
`default_nettype wire
