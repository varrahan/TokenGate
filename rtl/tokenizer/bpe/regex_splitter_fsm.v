`timescale 1ns/1ps
`default_nettype none
// Runtime-selected cl100k/Llama-3/GPT-2 pretokenizer. Indexed scalar records
// live in external working memory; arbitrarily long whitespace/word runs do
// not require an unbounded on-chip lookahead FIFO. Emits scalar-index spans.
// Record ABI: raw UTF-8 [31:0], scalar [52:32], class [54:53], length [57:55].
module regex_splitter_fsm #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire s_valid,output wire s_ready,input wire [31:0] s_count,
    input wire [1:0] s_profile,input wire [USER_WIDTH-1:0] s_user,
    output wire rd_valid,input wire rd_ready,output wire [31:0] rd_index,
    input wire rd_rsp_valid,output wire rd_rsp_ready,input wire [63:0] rd_rsp_record,input wire [7:0] rd_rsp_status,
    output wire m_valid,input wire m_ready,output wire [31:0] m_start,output wire [31:0] m_count,
    output wire m_sequence_last,output wire [USER_WIDTH-1:0] m_user,
    output wire error_valid,input wire error_ready,output reg [7:0] error_code,output reg [7:0] error_status,
    output wire [USER_WIDTH-1:0] error_user,output wire idle
);
    localparam IDLE=0,ISSUE=1,WAIT_RECORD=2,AFTER_HEAD=3,AFTER_SECOND=4,SELECT_BRANCH=5,
               SCAN_CHECK=6,SCAN_EVAL=7,OUTPUT_SPAN=8,ERROR_STATE=9;
    localparam LETTER=1,NUMBER=2,SPACE=3;
    localparam CL100K=0,LLAMA3=1,GPT2=2;
    localparam WORD_RUN=0,NUMBER_RUN=1,PUNCT_RUN=2,NEWLINE_RUN=3,SPACE_RUN=4;
    reg [3:0] state,resume_state;
    reg [2:0] run_mode;
    reg [1:0] profile,fetch_slot,number_count;
    reg [31:0] total_count,start_index,end_index,scan_index,fetch_index,last_newline_end;
    reg newline_found,second_valid,third_valid;
    reg [20:0] head_cp,second_cp,third_cp,scan_cp;
    reg [1:0] head_class,second_class,scan_class;
    reg [USER_WIDTH-1:0] context_id;
    wire [32:0] start_plus_one={1'b0,start_index}+1'b1;
    wire [32:0] start_plus_two={1'b0,start_index}+2'd2;
    function [20:0] contraction_lower(input [20:0] cp,input [1:0] selected_profile);
        begin
            if(selected_profile==GPT2)contraction_lower=cp;
            else if(cp>=65&&cp<=90)contraction_lower=cp+32;
            else if(cp==21'h17f)contraction_lower=115;
            else contraction_lower=cp;
        end
    endfunction
    wire [20:0] second_lower=contraction_lower(second_cp,profile);
    wire [20:0] third_lower=contraction_lower(third_cp,profile);
    wire single_contraction=second_lower==115||second_lower==100||second_lower==109||second_lower==116;
    wire double_contraction=(second_lower==108&&third_lower==108)||(second_lower==118&&third_lower==101)||(second_lower==114&&third_lower==101);
    wire prefix_letter=profile==GPT2?head_cp==32:(head_class!=LETTER&&head_class!=NUMBER&&head_cp!=10&&head_cp!=13);
    assign s_ready=!rst&&state==IDLE;
    assign rd_valid=!rst&&state==ISSUE;
    assign rd_index=fetch_index;
    assign rd_rsp_ready=state==WAIT_RECORD;
    assign m_valid=state==OUTPUT_SPAN;
    assign m_start=start_index;
    assign m_count=end_index-start_index;
    assign m_sequence_last=end_index==total_count;
    assign m_user=context_id;
    assign error_valid=state==ERROR_STATE;
    assign error_user=context_id;
    assign idle=state==IDLE&&!s_valid;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;resume_state<=IDLE;run_mode<=0;profile<=0;fetch_slot<=0;number_count<=0;
            total_count<=0;start_index<=0;end_index<=0;scan_index<=0;fetch_index<=0;last_newline_end<=0;
            newline_found<=0;second_valid<=0;third_valid<=0;head_cp<=0;second_cp<=0;third_cp<=0;scan_cp<=0;
            head_class<=0;second_class<=0;scan_class<=0;context_id<=0;error_code<=0;error_status<=0;
        end else case(state)
            IDLE:if(s_valid&&s_ready)begin
                total_count<=s_count;profile<=s_profile;context_id<=s_user;start_index<=0;end_index<=0;
                second_valid<=0;third_valid<=0;error_code<=0;error_status<=0;
                if(s_profile>GPT2)begin error_code<=1;state<=ERROR_STATE;end
                else if(s_count==0)state<=OUTPUT_SPAN;
                else begin fetch_index<=0;fetch_slot<=0;resume_state<=AFTER_HEAD;state<=ISSUE;end
            end
            ISSUE:if(rd_ready)state<=WAIT_RECORD;
            WAIT_RECORD:if(rd_rsp_valid)begin
                if(rd_rsp_status!=0)begin error_code<=2;error_status<=rd_rsp_status;state<=ERROR_STATE;end
                else begin
                    case(fetch_slot)
                        0:begin head_cp<=rd_rsp_record[52:32];head_class<=rd_rsp_record[54:53];end
                        1:begin second_cp<=rd_rsp_record[52:32];second_class<=rd_rsp_record[54:53];end
                        2:third_cp<=rd_rsp_record[52:32];
                        3:begin scan_cp<=rd_rsp_record[52:32];scan_class<=rd_rsp_record[54:53];end
                    endcase
                    state<=resume_state;
                end
            end
            AFTER_HEAD:begin
                second_valid<=start_plus_one<{1'b0,total_count};third_valid<=0;
                if(start_plus_one<{1'b0,total_count})begin
                    fetch_index<=start_plus_one[31:0];fetch_slot<=1;resume_state<=AFTER_SECOND;state<=ISSUE;
                end else state<=SELECT_BRANCH;
            end
            AFTER_SECOND:begin
                third_valid<=start_plus_two<{1'b0,total_count};
                if(start_plus_two<{1'b0,total_count})begin
                    fetch_index<=start_plus_two[31:0];fetch_slot<=2;resume_state<=SELECT_BRANCH;state<=ISSUE;
                end else state<=SELECT_BRANCH;
            end
            SELECT_BRANCH:begin
                if(head_cp==39&&second_valid&&single_contraction)begin end_index<=start_index+2;state<=OUTPUT_SPAN;end
                else if(head_cp==39&&second_valid&&third_valid&&double_contraction)begin end_index<=start_index+3;state<=OUTPUT_SPAN;end
                else begin
                    state<=SCAN_CHECK;number_count<=1;
                    if(head_class==LETTER||(prefix_letter&&second_valid&&second_class==LETTER))begin
                        run_mode<=WORD_RUN;scan_index<=head_class==LETTER?start_index+1:start_index+2;
                    end else if(head_class==NUMBER||(profile==GPT2&&head_cp==32&&second_valid&&second_class==NUMBER))begin
                        run_mode<=NUMBER_RUN;scan_index<=head_class==NUMBER?start_index+1:start_index+2;
                    end else if(head_class==0||(head_cp==32&&second_valid&&second_class==0))begin
                        run_mode<=PUNCT_RUN;scan_index<=head_class==0?start_index+1:start_index+2;
                    end else begin
                        run_mode<=SPACE_RUN;scan_index<=start_index+1;
                        newline_found<=head_cp==10||head_cp==13;
                        last_newline_end<=start_index+1;
                    end
                end
            end
            SCAN_CHECK:begin
                if(scan_index==total_count)begin
                    if(run_mode==SPACE_RUN&&profile!=CL100K&&profile!=GPT2&&newline_found)end_index<=last_newline_end;
                    else end_index<=total_count;
                    state<=OUTPUT_SPAN;
                end else if(run_mode==NUMBER_RUN&&profile!=GPT2&&number_count==3)begin end_index<=scan_index;state<=OUTPUT_SPAN;end
                else begin fetch_index<=scan_index;fetch_slot<=3;resume_state<=SCAN_EVAL;state<=ISSUE;end
            end
            SCAN_EVAL:case(run_mode)
                WORD_RUN:if(scan_class==LETTER)begin scan_index<=scan_index+1'b1;state<=SCAN_CHECK;end
                         else begin end_index<=scan_index;state<=OUTPUT_SPAN;end
                NUMBER_RUN:if(scan_class==NUMBER)begin scan_index<=scan_index+1'b1;number_count<=number_count+1'b1;state<=SCAN_CHECK;end
                           else begin end_index<=scan_index;state<=OUTPUT_SPAN;end
                PUNCT_RUN:if(scan_class==0)begin scan_index<=scan_index+1'b1;state<=SCAN_CHECK;end
                          else if(profile!=GPT2&&(scan_cp==10||scan_cp==13))begin run_mode<=NEWLINE_RUN;scan_index<=scan_index+1'b1;state<=SCAN_CHECK;end
                          else begin end_index<=scan_index;state<=OUTPUT_SPAN;end
                NEWLINE_RUN:if(scan_cp==10||scan_cp==13)begin scan_index<=scan_index+1'b1;state<=SCAN_CHECK;end
                            else begin end_index<=scan_index;state<=OUTPUT_SPAN;end
                SPACE_RUN:if(scan_class==SPACE)begin
                    scan_index<=scan_index+1'b1;state<=SCAN_CHECK;
                    if(scan_cp==10||scan_cp==13)begin newline_found<=1;last_newline_end<=scan_index+1'b1;end
                end else begin
                    if(profile!=GPT2&&newline_found)end_index<=last_newline_end;
                    else if(scan_index-start_index>1)end_index<=scan_index-1'b1;
                    else end_index<=scan_index;
                    state<=OUTPUT_SPAN;
                end
            endcase
            OUTPUT_SPAN:if(m_ready)begin
                if(end_index==total_count)state<=IDLE;
                else begin
                    start_index<=end_index;fetch_index<=end_index;fetch_slot<=0;resume_state<=AFTER_HEAD;state<=ISSUE;
                end
            end
            ERROR_STATE:if(error_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
