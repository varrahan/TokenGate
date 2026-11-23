`timescale 1ns/1ps
`default_nettype none
// Compact sparse AXI byte lanes through a registered merge tree. Present a
// caller-consumed byte window and a separate count=0,last=1 packet-end record.
// Windows do not combine two source beats; callers may retain partial tokens.
module axis_compacting_window #(
    parameter integer INPUT_BYTES=64,parameter integer WINDOW_BYTES=8,
    parameter integer USER_WIDTH=16,
    parameter integer STAGES=$clog2(INPUT_BYTES),
    parameter integer COUNT_WIDTH=$clog2(INPUT_BYTES+1),
    parameter integer WINDOW_COUNT_WIDTH=$clog2(WINDOW_BYTES+1)
)(
    input wire clk,input wire rst,
    input wire [INPUT_BYTES*8-1:0] s_data,input wire [INPUT_BYTES-1:0] s_keep,
    input wire s_valid,output wire s_ready,input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output wire [WINDOW_BYTES*8-1:0] m_data,output wire [WINDOW_COUNT_WIDTH-1:0] m_count,
    output wire m_valid,input wire m_ready,input wire [WINDOW_COUNT_WIDTH-1:0] m_consumed,
    output wire m_last,output wire [USER_WIDTH-1:0] m_user,output wire idle
);
    reg [INPUT_BYTES*8-1:0] tree_data[0:STAGES];
    reg [COUNT_WIDTH-1:0] tree_count[0:STAGES][0:INPUT_BYTES-1];
    reg [STAGES:0] valid_pipe,last_pipe;
    reg [USER_WIDTH-1:0] user_pipe[0:STAGES];
    reg occupied,last_pending;
    reg [INPUT_BYTES*8-1:0] window_data;
    reg [COUNT_WIDTH-1:0] remaining;
    reg [USER_WIDTH-1:0] context_id;
    wire advance=!valid_pipe[STAGES]||!occupied;
    wire [WINDOW_COUNT_WIDTH-1:0] take=m_consumed<=m_count?m_consumed:0;
    assign s_ready=!rst&&advance;
    assign m_data=window_data[WINDOW_BYTES*8-1:0];
    assign m_count=remaining>WINDOW_BYTES?WINDOW_BYTES:remaining;
    assign m_valid=!rst&&occupied;
    assign m_last=occupied&&remaining==0&&last_pending;
    assign m_user=context_id;
    assign idle=!rst&&!occupied&&!(|valid_pipe)&&!s_valid;
    integer stage;
    always @(posedge clk)begin
        if(rst)begin valid_pipe<=0;last_pipe<=0;end
        else if(advance)begin
            valid_pipe[0]<=s_valid;
            if(s_valid)begin last_pipe[0]<=s_last;user_pipe[0]<=s_user;end
            for(stage=1;stage<=STAGES;stage=stage+1)begin
                valid_pipe[stage]<=valid_pipe[stage-1];
                if(valid_pipe[stage-1])begin last_pipe[stage]<=last_pipe[stage-1];user_pipe[stage]<=user_pipe[stage-1];end
            end
        end
    end
    genvar lane,level,group_index;
    generate for(lane=0;lane<INPUT_BYTES;lane=lane+1)begin: source_lanes
        always @(posedge clk)if(!rst&&advance&&s_valid)begin
            tree_data[0][lane*8+:8]<=s_keep[lane]?s_data[lane*8+:8]:8'd0;
            tree_count[0][lane]<=s_keep[lane]?1:0;
        end
    end
    for(level=1;level<=STAGES;level=level+1)begin: merge_levels
        localparam integer GROUP_BYTES=2**level;
        localparam integer HALF_BITS=GROUP_BYTES*4;
        for(group_index=0;group_index<INPUT_BYTES/GROUP_BYTES;group_index=group_index+1)begin: groups
            always @(posedge clk)if(!rst&&advance&&valid_pipe[level-1])begin
                tree_data[level][group_index*GROUP_BYTES*8+:GROUP_BYTES*8]<=
                    {{HALF_BITS{1'b0}},tree_data[level-1][group_index*GROUP_BYTES*8+:HALF_BITS]}|
                    ({{HALF_BITS{1'b0}},tree_data[level-1][group_index*GROUP_BYTES*8+HALF_BITS+:HALF_BITS]}<<
                     (tree_count[level-1][group_index*2]*8));
                tree_count[level][group_index]<=tree_count[level-1][group_index*2]+tree_count[level-1][group_index*2+1];
            end
        end
    end endgenerate
    always @(posedge clk)begin
        if(rst)begin occupied<=0;last_pending<=0;window_data<=0;remaining<=0;context_id<=0;end
        else if(!occupied)begin
            if(valid_pipe[STAGES])begin
                window_data<=tree_data[STAGES];remaining<=tree_count[STAGES][0];
                last_pending<=last_pipe[STAGES];context_id<=user_pipe[STAGES];
                occupied<=tree_count[STAGES][0]!=0||last_pipe[STAGES];
            end
        end else if(m_valid&&m_ready)begin
            if(remaining==0)begin occupied<=0;last_pending<=0;end
            else if(take!=0)begin
                window_data<=window_data>>(take*8);remaining<=remaining-take;
                if(remaining==take&&!last_pending)occupied<=0;
            end
        end
    end
`ifndef SYNTHESIS
    initial begin
        if(INPUT_BYTES<2||2**STAGES!=INPUT_BYTES||WINDOW_BYTES<1||WINDOW_BYTES>INPUT_BYTES)
            $fatal(1,"Compacting window requires power-of-two input bytes and a bounded output window");
    end
`endif
endmodule
`default_nettype wire
