`timescale 1ns/1ps
`default_nettype none
// Four independently occupied stages: capture/config validation, parent-node
// fetch, sorted-edge binary search, child-node/terminal fetch. The three read
// clients can overlap through the common memory fabric. Each request evaluates
// one (node, byte) transition; callers feed next_node back for string traversal.
module trie_search_pipeline #(
    parameter integer NODE_WIDTH=18,parameter integer ID_WIDTH=17,
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,input wire cfg_unlock,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_node_base,input wire [MEMORY_ADDR_WIDTH-1:0] cfg_edge_base,
    input wire [31:0] cfg_node_count,input wire [31:0] cfg_edge_count,
    input wire req_valid,output wire req_ready,input wire [NODE_WIDTH-1:0] req_node,input wire [7:0] req_byte,
    input wire req_last,input wire [USER_WIDTH-1:0] req_user,
    output wire rsp_valid,input wire rsp_ready,output wire rsp_match,output wire rsp_terminal,
    output wire [NODE_WIDTH-1:0] rsp_next_node,output wire [ID_WIDTH-1:0] rsp_token,
    output wire rsp_last,output wire [USER_WIDTH-1:0] rsp_user,output wire [7:0] rsp_status,
    output wire [2:0] mem_rd_valid,input wire [2:0] mem_rd_ready,
    output wire [3*MEMORY_ADDR_WIDTH-1:0] mem_rd_addr,output wire [11:0] mem_rd_bytes,
    input wire [2:0] mem_rsp_valid,output wire [2:0] mem_rsp_ready,
    input wire [215:0] mem_rsp_data,input wire [23:0] mem_rsp_status,
    output wire idle
);
    localparam EMPTY=0,ISSUE=1,WAIT_DATA=2,RESULT=3,SEARCH=4;
    localparam integer TERMINAL_BIT=NODE_WIDTH+9+ID_WIDTH;
    reg valid0,last0;reg [7:0] byte0,status0;
    reg [NODE_WIDTH-1:0] node0;reg [USER_WIDTH-1:0] user0;
    reg [MEMORY_ADDR_WIDTH-1:0] node_base0,edge_base0;
    reg [31:0] node_count0,edge_count0;
    reg [2:0] state1,state2,state3;
    reg [7:0] byte1,status1;reg last1;
    reg [NODE_WIDTH-1:0] node1,first_edge1;reg [8:0] children1;
    reg [USER_WIDTH-1:0] user1;
    reg [MEMORY_ADDR_WIDTH-1:0] node_base1,edge_base1;
    reg [31:0] node_count1,edge_count1;
    reg [7:0] byte2,status2;reg last2,found2,direct_edge2;
    reg [NODE_WIDTH-1:0] first_edge2,child2,parent2;reg [8:0] low2,high2,middle2;
    reg [USER_WIDTH-1:0] user2;
    reg [MEMORY_ADDR_WIDTH-1:0] node_base2,edge_base2;
    reg [31:0] node_count2,edge_count2;
    reg [7:0] status3;reg last3,found3,terminal3;
    reg [NODE_WIDTH-1:0] child3;reg [ID_WIDTH-1:0] token3;
    reg [USER_WIDTH-1:0] user3;
    reg [MEMORY_ADDR_WIDTH-1:0] node_base3;
    reg [31:0] edge_count3;
    wire [63:0] configured_node_end=cfg_node_base+64'd6*cfg_node_count;
    wire [63:0] configured_edge_end=cfg_edge_base+64'd4*cfg_edge_count;
    wire configuration_good=cfg_node_count!=0&&cfg_node_count<=(64'd1<<NODE_WIDTH)&&cfg_edge_count<(64'd1<<NODE_WIDTH)&&
                           configured_node_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&configured_edge_end<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire [63:0] parent_address=node_base1+64'd6*node1;
    wire [63:0] edge_address=edge_base2+64'd4*({1'b0,first_edge2}+{1'b0,middle2});
    wire [63:0] child_address=node_base3+64'd6*child3;
    wire [9:0] middle_sum={1'b0,low2}+{1'b0,high2};
    wire [47:0] parent_record=mem_rsp_data[0+:48];
    wire [31:0] edge_record=mem_rsp_data[72+:32];
    wire [47:0] child_record=mem_rsp_data[144+:48];
    function bad_node(input [47:0] record_value,input [31:0] available_edges);
        reg [32:0] end_edge;
        begin
            end_edge={1'b0,record_value[0+:NODE_WIDTH]}+{1'b0,record_value[NODE_WIDTH+:9]};
            bad_node=(record_value>>(TERMINAL_BIT+1))!=0||record_value[NODE_WIDTH+:9]>256||end_edge>{1'b0,available_edges}||
                     (!record_value[TERMINAL_BIT]&&record_value[NODE_WIDTH+9+:ID_WIDTH]!=0);
        end
    endfunction
    assign req_ready=!rst&&!cfg_unlock&&!valid0;
    assign mem_rd_valid[0]=!rst&&state1==ISSUE;
    assign mem_rd_valid[1]=!rst&&state2==ISSUE;
    assign mem_rd_valid[2]=!rst&&state3==ISSUE;
    assign mem_rd_addr={child_address[MEMORY_ADDR_WIDTH-1:0],edge_address[MEMORY_ADDR_WIDTH-1:0],parent_address[MEMORY_ADDR_WIDTH-1:0]};
    assign mem_rd_bytes={4'd6,4'd4,4'd6};
    assign mem_rsp_ready={state3==WAIT_DATA,state2==WAIT_DATA,state1==WAIT_DATA};
    assign rsp_valid=state3==RESULT;
    assign rsp_match=found3;assign rsp_terminal=terminal3;assign rsp_next_node=child3;assign rsp_token=token3;
    assign rsp_last=last3;assign rsp_user=user3;assign rsp_status=status3;
    assign idle=!valid0&&state1==EMPTY&&state2==EMPTY&&state3==EMPTY&&!(req_valid&&req_ready);
    initial begin
        if(NODE_WIDTH<1||NODE_WIDTH>24||ID_WIDTH<1||TERMINAL_BIT>=48)$error("Trie fields exceed packed ABI");
    end
    always @(posedge clk)begin
        if(rst)begin
            valid0<=0;last0<=0;byte0<=0;status0<=0;node0<=0;user0<=0;node_base0<=0;edge_base0<=0;node_count0<=0;edge_count0<=0;
            state1<=EMPTY;state2<=EMPTY;state3<=EMPTY;
            byte1<=0;status1<=0;last1<=0;node1<=0;first_edge1<=0;children1<=0;user1<=0;node_base1<=0;edge_base1<=0;node_count1<=0;edge_count1<=0;
            byte2<=0;status2<=0;last2<=0;found2<=0;direct_edge2<=0;first_edge2<=0;child2<=0;parent2<=0;low2<=0;high2<=0;middle2<=0;user2<=0;
            node_base2<=0;edge_base2<=0;node_count2<=0;edge_count2<=0;
            status3<=0;last3<=0;found3<=0;terminal3<=0;child3<=0;token3<=0;user3<=0;node_base3<=0;edge_count3<=0;
        end else begin
            if(req_valid&&req_ready)begin
                valid0<=1;node0<=req_node;byte0<=req_byte;last0<=req_last;user0<=req_user;
                node_base0<=cfg_node_base;edge_base0<=cfg_edge_base;node_count0<=cfg_node_count;edge_count0<=cfg_edge_count;
                status0<=(!configuration_good||{1'b0,req_node}>=cfg_node_count)?1:0;
            end
            case(state1)
                EMPTY:if(valid0)begin
                    valid0<=0;node1<=node0;byte1<=byte0;last1<=last0;user1<=user0;status1<=status0;
                    node_base1<=node_base0;edge_base1<=edge_base0;node_count1<=node_count0;edge_count1<=edge_count0;
                    first_edge1<=0;children1<=0;state1<=status0!=0?RESULT:ISSUE;
                end
                ISSUE:if(mem_rd_ready[0])state1<=WAIT_DATA;
                WAIT_DATA:if(mem_rsp_valid[0])begin
                    if(mem_rsp_status[0+:8]!=0)status1<=8'h10|mem_rsp_status[0+:8];
                    else if(bad_node(parent_record,edge_count1)||(node_count1>1&&parent_record[NODE_WIDTH+:9]==0&&!parent_record[TERMINAL_BIT]))status1<=2;
                    else begin first_edge1<=parent_record[0+:NODE_WIDTH];children1<=parent_record[NODE_WIDTH+:9];end
                    state1<=RESULT;
                end
                RESULT:if(state2==EMPTY)state1<=EMPTY;
                default:state1<=EMPTY;
            endcase
            case(state2)
                EMPTY:if(state1==RESULT)begin
                    byte2<=byte1;last2<=last1;user2<=user1;status2<=status1;first_edge2<=first_edge1;parent2<=node1;
                    node_base2<=node_base1;edge_base2<=edge_base1;node_count2<=node_count1;edge_count2<=edge_count1;
                    low2<=0;high2<=children1;middle2<=children1==256?{1'b0,byte1}:9'd0;child2<=0;found2<=0;direct_edge2<=children1==256;
                    // A valid sorted 256-child node contains every byte once.
                    // Its edge index is the byte itself, avoiding a root search.
                    state2<=status1!=0||children1==0?RESULT:children1==256?ISSUE:SEARCH;
                end
                SEARCH:if(low2>=high2)state2<=RESULT;
                       else begin middle2<=middle_sum[9:1];state2<=ISSUE;end
                ISSUE:if(mem_rd_ready[1])state2<=WAIT_DATA;
                WAIT_DATA:if(mem_rsp_valid[1])begin
                    if(mem_rsp_status[8+:8]!=0)begin status2<=8'h20|mem_rsp_status[8+:8];state2<=RESULT;end
                    else if((edge_record>>(NODE_WIDTH+8))!=0||{1'b0,edge_record[8+:NODE_WIDTH]}>=node_count2||edge_record[8+:NODE_WIDTH]<=parent2||
                            (direct_edge2&&edge_record[7:0]!=byte2))begin status2<=3;state2<=RESULT;end
                    else if(edge_record[7:0]==byte2)begin found2<=1;child2<=edge_record[8+:NODE_WIDTH];state2<=RESULT;end
                    else begin
                        if(edge_record[7:0]<byte2)low2<=middle2+1'b1;else high2<=middle2;
                        state2<=SEARCH;
                    end
                end
                RESULT:if(state3==EMPTY)state2<=EMPTY;
                default:state2<=EMPTY;
            endcase
            case(state3)
                EMPTY:if(state2==RESULT)begin
                    last3<=last2;user3<=user2;status3<=status2;found3<=found2;child3<=found2?child2:0;
                    terminal3<=0;token3<=0;node_base3<=node_base2;edge_count3<=edge_count2;
                    state3<=status2!=0||!found2?RESULT:ISSUE;
                end
                ISSUE:if(mem_rd_ready[2])state3<=WAIT_DATA;
                WAIT_DATA:if(mem_rsp_valid[2])begin
                    if(mem_rsp_status[16+:8]!=0)begin status3<=8'h30|mem_rsp_status[16+:8];found3<=0;child3<=0;end
                    else if(bad_node(child_record,edge_count3)||(child_record[NODE_WIDTH+:9]==0&&!child_record[TERMINAL_BIT]))begin status3<=2;found3<=0;child3<=0;end
                    else begin
                        terminal3<=child_record[TERMINAL_BIT];
                        token3<=child_record[TERMINAL_BIT]?child_record[NODE_WIDTH+9+:ID_WIDTH]:0;
                    end
                    state3<=RESULT;
                end
                RESULT:if(rsp_ready)state3<=EMPTY;
                default:state3<=EMPTY;
            endcase
        end
    end
endmodule
`default_nettype wire
