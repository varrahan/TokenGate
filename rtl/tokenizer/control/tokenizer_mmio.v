`timescale 1ns/1ps
`default_nettype none
// AXI-Lite host register bridge. AW and W are captured independently; B/R
// remain stable under stalls. A memory doorbell's B response follows the
// external loader completion, not merely command acceptance. See MMIO map.
module tokenizer_mmio #(parameter integer MEMORY_ADDR_WIDTH=23)(
    input wire clk,input wire rst,
    input wire [15:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
    input wire [15:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,output reg s_axi_rvalid,input wire s_axi_rready,
    output reg update_req,output reg commit,output reg abort_update,output reg tables_valid,
    input wire cfg_unlock,input wire [31:0] epoch,input wire vocabulary_valid,input wire protocol_error,input wire draining,input wire datapath_idle,
    output wire cfg_valid,input wire cfg_ready,output reg [MEMORY_ADDR_WIDTH-1:0] cfg_addr,output reg [3:0] cfg_bytes,output reg [71:0] cfg_data,
    input wire cfg_rsp_valid,output wire cfg_rsp_ready,input wire [7:0] cfg_rsp_status,
    output wire cfg_invalidate_valid,input wire cfg_invalidate_ready,
    output reg [1:0] cfg_profile,
    output reg [MEMORY_ADDR_WIDTH-1:0] cfg_class_base,cfg_hash_base,cfg_node_base,cfg_edge_base,
    output reg [31:0] cfg_node_count,cfg_edge_count,
    output reg [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,cfg_scalar_base,cfg_merge_base,cfg_commit_base,
    output reg [MEMORY_ADDR_WIDTH:0] cfg_scalar_bytes,cfg_merge_bytes,cfg_commit_bytes,
    output reg [MEMORY_ADDR_WIDTH-1:0] directory_base,pool_base,output reg strip_special_tokens
);
    localparam GATHER=0,EXECUTE=1,ISSUE=2,WAIT_CFG=3,INVALIDATE=4,RESPONSE=5;
    localparam OKAY=2'b00,SLVERR=2'b10,DECERR=2'b11;
    reg [2:0] state;
    reg aw_have,w_have,sticky_protocol,sticky_loader;
    reg [15:0] address;
    reg [31:0] write_data;
    reg [3:0] write_strobes;
    reg [7:0] last_memory_status;
    wire memory_busy=state==ISSUE||state==WAIT_CFG||state==INVALIDATE;
    assign s_axi_awready=!rst&&state==GATHER&&!aw_have;
    assign s_axi_wready=!rst&&state==GATHER&&!w_have;
    assign s_axi_arready=!rst&&(!s_axi_rvalid||s_axi_rready);
    assign cfg_valid=!rst&&state==ISSUE;
    assign cfg_rsp_ready=state==WAIT_CFG;
    assign cfg_invalidate_valid=!rst&&state==INVALIDATE;
    // Explicit function inputs preserve combinational dependencies even when
    // repeated partial writes keep the address unchanged in event simulators.
    wire [959:0] register_bank;
    assign register_bank[0*32+:32]=32'h50545831;
    assign register_bank[1*32+:32]={25'd0,sticky_loader,sticky_protocol,memory_busy,datapath_idle,vocabulary_valid,draining,cfg_unlock};
    assign register_bank[2*32+:32]=0;
    assign register_bank[3*32+:32]=epoch;
    assign register_bank[4*32+:32]={31'd0,tables_valid};
    assign register_bank[5*32+:32]={24'd0,last_memory_status};
    assign register_bank[6*32+:32]=cfg_addr;
    assign register_bank[7*32+:32]={28'd0,cfg_bytes};
    assign register_bank[8*32+:32]=cfg_data[31:0];
    assign register_bank[9*32+:32]=cfg_data[63:32];
    assign register_bank[10*32+:32]={24'd0,cfg_data[71:64]};
    assign register_bank[11*32+:32]=0;
    assign register_bank[12*32+:32]={30'd0,cfg_profile};
    assign register_bank[13*32+:32]=cfg_class_base;
    assign register_bank[14*32+:32]=cfg_hash_base;
    assign register_bank[15*32+:32]=cfg_node_base;
    assign register_bank[16*32+:32]=cfg_edge_base;
    assign register_bank[17*32+:32]=cfg_node_count;
    assign register_bank[18*32+:32]=cfg_edge_count;
    assign register_bank[19*32+:32]=cfg_work_floor;
    assign register_bank[20*32+:32]=cfg_scalar_base;
    assign register_bank[21*32+:32]=cfg_scalar_bytes;
    assign register_bank[22*32+:32]=cfg_merge_base;
    assign register_bank[23*32+:32]=cfg_merge_bytes;
    assign register_bank[24*32+:32]=cfg_commit_base;
    assign register_bank[25*32+:32]=cfg_commit_bytes;
    assign register_bank[26*32+:32]=directory_base;
    assign register_bank[27*32+:32]=pool_base;
    assign register_bank[28*32+:32]={31'd0,strip_special_tokens};
    assign register_bank[29*32+:32]=0;
    function [31:0] register_value(input [15:0] a,input [959:0] bank);
        begin register_value=a[1:0]==0&&a<=16'h0074 ? bank[a[6:2]*32+:32] : 32'd0;end
    endfunction
    function readable(input [15:0] a);
        begin readable=a[1:0]==0&&a<=16'h0074;end
    endfunction
    function configurable(input [15:0] a);
        begin configurable=a==16'h0010||(a>=16'h0018&&a<=16'h0028)||(a>=16'h0030&&a<=16'h0070);end
    endfunction
    function [31:0] merge_bytes(input [31:0] old_value,input [31:0] new_value,input [3:0] strobes);
        integer lane;
        begin
            merge_bytes=old_value;
            for(lane=0;lane<4;lane=lane+1)if(strobes[lane])merge_bytes[lane*8+:8]=new_value[lane*8+:8];
        end
    endfunction
    wire [31:0] merged=merge_bytes(register_value(address,register_bank),write_data,write_strobes);
    wire [31:0] action=merge_bytes(0,write_data,write_strobes);
    wire address_register=address==16'h0018||address==16'h0034||address==16'h0038||address==16'h003c||address==16'h0040||
        address==16'h004c||address==16'h0050||address==16'h0058||address==16'h0060||address==16'h0068||address==16'h006c;
    wire capacity_register=address==16'h0054||address==16'h005c||address==16'h0064;
    wire register_range_good=(!address_register||(merged>>MEMORY_ADDR_WIDTH)==0)&&
        (!capacity_register||(merged>>(MEMORY_ADDR_WIDTH+1))==0)&&
        (address!=16'h0010||merged<=1)&&(address!=16'h001c||merged<=9)&&
        (address!=16'h0028||merged<=255)&&(address!=16'h0030||merged<=2)&&(address!=16'h0070||merged<=1);
    task respond(input [1:0] status);
        begin s_axi_bresp<=status;s_axi_bvalid<=1;state<=RESPONSE;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=GATHER;aw_have<=0;w_have<=0;address<=0;write_data<=0;write_strobes<=0;
            s_axi_bvalid<=0;s_axi_bresp<=OKAY;s_axi_rvalid<=0;s_axi_rdata<=0;s_axi_rresp<=OKAY;
            update_req<=0;commit<=0;abort_update<=0;tables_valid<=0;sticky_protocol<=0;sticky_loader<=0;last_memory_status<=0;
            cfg_addr<=0;cfg_bytes<=0;cfg_data<=0;cfg_profile<=0;cfg_class_base<=0;cfg_hash_base<=0;cfg_node_base<=0;cfg_edge_base<=0;cfg_node_count<=0;cfg_edge_count<=0;
            cfg_work_floor<=0;cfg_scalar_base<=0;cfg_scalar_bytes<=0;cfg_merge_base<=0;cfg_merge_bytes<=0;cfg_commit_base<=0;cfg_commit_bytes<=0;directory_base<=0;pool_base<=0;strip_special_tokens<=0;
        end else begin
            update_req<=0;commit<=0;abort_update<=0;
            if(s_axi_awvalid&&s_axi_awready)begin address<=s_axi_awaddr;aw_have<=1;end
            if(s_axi_wvalid&&s_axi_wready)begin write_data<=s_axi_wdata;write_strobes<=s_axi_wstrb;w_have<=1;end
            if(s_axi_rvalid&&s_axi_rready)s_axi_rvalid<=0;
            if(s_axi_arvalid&&s_axi_arready)begin
                s_axi_rvalid<=1;s_axi_rdata<=register_value(s_axi_araddr,register_bank);s_axi_rresp<=readable(s_axi_araddr)?OKAY:DECERR;
            end
            case(state)
                GATHER:if(aw_have&&w_have)state<=EXECUTE;
                EXECUTE:begin
                    if(address[1:0]!=0)respond(SLVERR);
                    else if(write_strobes==0)respond(OKAY);
                    else if(address==16'h0008)begin
                        case(action)
                            32'd1:begin update_req<=1;respond(OKAY);end
                            32'd2:begin commit<=1;respond(cfg_unlock&&datapath_idle&&tables_valid?OKAY:SLVERR);end
                            32'd4:begin abort_update<=1;tables_valid<=0;respond(cfg_unlock?OKAY:SLVERR);end
                            32'd8:if(cfg_unlock)state<=INVALIDATE;else respond(SLVERR);
                            default:respond(SLVERR);
                        endcase
                    end else if(address==16'h002c)begin
                        if(action!=1||!cfg_unlock||cfg_bytes<1||cfg_bytes>9||({1'b0,cfg_addr}+{1'b0,cfg_bytes})>(64'd1<<MEMORY_ADDR_WIDTH))respond(SLVERR);
                        else begin tables_valid<=0;state<=ISSUE;end
                    end else if(address==16'h0074)begin
                        if(action>3)respond(SLVERR);
                        else begin if(action[0])sticky_protocol<=0;if(action[1])sticky_loader<=0;respond(OKAY);end
                    end else if(configurable(address))begin
                        if(!cfg_unlock||!datapath_idle||!register_range_good)respond(SLVERR);
                        else begin
                            tables_valid<=0;
                            case(address)
                                16'h0010:tables_valid<=merged[0];
                                16'h0018:cfg_addr<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h001c:cfg_bytes<=merged[3:0];
                                16'h0020:cfg_data[31:0]<=merged;
                                16'h0024:cfg_data[63:32]<=merged;
                                16'h0028:cfg_data[71:64]<=merged[7:0];
                                16'h0030:cfg_profile<=merged[1:0];
                                16'h0034:cfg_class_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0038:cfg_hash_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h003c:cfg_node_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0040:cfg_edge_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0044:cfg_node_count<=merged;
                                16'h0048:cfg_edge_count<=merged;
                                16'h004c:cfg_work_floor<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0050:cfg_scalar_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0054:cfg_scalar_bytes<=merged[MEMORY_ADDR_WIDTH:0];
                                16'h0058:cfg_merge_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h005c:cfg_merge_bytes<=merged[MEMORY_ADDR_WIDTH:0];
                                16'h0060:cfg_commit_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0064:cfg_commit_bytes<=merged[MEMORY_ADDR_WIDTH:0];
                                16'h0068:directory_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h006c:pool_base<=merged[MEMORY_ADDR_WIDTH-1:0];
                                16'h0070:strip_special_tokens<=merged[0];
                            endcase
                            respond(OKAY);
                        end
                    end else respond(DECERR);
                end
                ISSUE:if(cfg_ready)state<=WAIT_CFG;
                WAIT_CFG:if(cfg_rsp_valid)begin
                    last_memory_status<=cfg_rsp_status;if(cfg_rsp_status!=0)sticky_loader<=1;
                    respond(cfg_rsp_status==0?OKAY:SLVERR);
                end
                INVALIDATE:if(cfg_invalidate_ready)respond(OKAY);
                RESPONSE:if(s_axi_bvalid&&s_axi_bready)begin s_axi_bvalid<=0;aw_have<=0;w_have<=0;state<=GATHER;end
                default:state<=GATHER;
            endcase
            if(protocol_error)sticky_protocol<=1;
        end
    end
    initial if(MEMORY_ADDR_WIDTH>30||MEMORY_ADDR_WIDTH<1)$error("Unsupported MMIO address width");
endmodule
`default_nettype wire
