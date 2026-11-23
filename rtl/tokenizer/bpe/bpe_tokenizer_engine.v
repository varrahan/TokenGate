`timescale 1ns/1ps
`default_nettype none
// Complete text-to-token correctness datapath. Eight external-memory clients:
// classes, scalar workspace, trie parent/edge/child, ranks, merge workspace,
// and whole-sequence token staging. All writes are acknowledged before use.
// Computation failures release no tokens. A staging READ failure can follow
// a released prefix: a keep=0/TLAST terminator and failed completion require
// the consumer to discard that sequence. Completion is part of the protocol.
module bpe_tokenizer_engine #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,
    parameter integer ID_WIDTH=17,parameter integer NODE_WIDTH=18,parameter integer HASH_ADDR_WIDTH=18
)(
    input wire clk,input wire rst,input wire admit_sequences,
    input wire [1:0] cfg_profile,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_class_base,cfg_hash_base,cfg_node_base,cfg_edge_base,
    input wire [31:0] cfg_node_count,cfg_edge_count,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,cfg_scalar_base,cfg_merge_base,cfg_commit_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_scalar_bytes,cfg_merge_bytes,cfg_commit_bytes,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,input wire s_axis_text_tlast,input wire [USER_WIDTH-1:0] s_axis_text_tuser,
    output wire [31:0] m_axis_tokens_tdata,output wire [3:0] m_axis_tokens_tkeep,
    output wire m_axis_tokens_tvalid,input wire m_axis_tokens_tready,output wire m_axis_tokens_tlast,output wire [USER_WIDTH-1:0] m_axis_tokens_tuser,
    output wire completion_valid,input wire completion_ready,output wire completion_failed,
    output wire [31:0] completion_count,output wire [USER_WIDTH-1:0] completion_user,
    output wire error_valid,input wire error_ready,output reg [7:0] error_stage,error_detail,error_status,
    output wire [USER_WIDTH-1:0] error_user,
    output wire [7:0] mem_valid,input wire [7:0] mem_ready,output wire [7:0] mem_write,
    output wire [8*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [31:0] mem_bytes,output wire [575:0] mem_data,
    input wire [7:0] mem_rsp_valid,output wire [7:0] mem_rsp_ready,input wire [575:0] mem_rsp_data,input wire [63:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,BYTE=1,TRIE_WAIT=2,FEED=3,MERGE_WAIT=4,COMMIT_WAIT=5,RELEASE=6,
               READ_REQ=7,READ_WAIT=8,OUT_TOKEN=9,EMPTY_OUT=10,DRAIN_RAW=11,ABORT=12,
               ABORT_TERM=13,ERROR_STATE=14,DONE_OK=15,DONE_BAD=16,RESET_PIPE=17;
    reg [4:0] state;
    reg source_closed,source_bad,release_started,piece_last,sequence_last,kept_byte;
    reg [1:0] profile;
    reg [MEMORY_ADDR_WIDTH-1:0] class_base,hash_base,node_base,edge_base,scalar_base,merge_base,commit_base;
    reg [MEMORY_ADDR_WIDTH:0] scalar_bytes,merge_bytes,commit_bytes;
    reg [31:0] node_count,edge_count,token_count,release_index,output_token;
    // Capacity is consumed only after an acknowledged staging write. Keeping
    // the remaining slots avoids an add/compare chain on merger backpressure.
    reg [MEMORY_ADDR_WIDTH-2:0] commit_remaining;
    reg [ID_WIDTH-1:0] byte_token;
    reg [USER_WIDTH-1:0] context_id;
    wire flush=rst||state==RESET_PIPE;
    wire [63:0] scalar_end={1'b0,cfg_scalar_base}+{1'b0,cfg_scalar_bytes};
    wire [63:0] merge_end={1'b0,cfg_merge_base}+{1'b0,cfg_merge_bytes};
    wire [63:0] commit_end={1'b0,cfg_commit_base}+{1'b0,cfg_commit_bytes};
    wire configuration_good=cfg_profile<=2&&cfg_node_count!=0&&cfg_node_count<=(64'd1<<NODE_WIDTH)&&cfg_edge_count<(64'd1<<NODE_WIDTH)&&
        cfg_scalar_base>=cfg_work_floor&&cfg_merge_base>=cfg_work_floor&&cfg_commit_base>=cfg_work_floor&&
        scalar_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&merge_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&commit_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (scalar_end<=cfg_merge_base||merge_end<=cfg_scalar_base)&&
        (scalar_end<=cfg_commit_base||commit_end<=cfg_scalar_base)&&
        (merge_end<=cfg_commit_base||commit_end<=cfg_merge_base)&&
        cfg_class_base+64'd278528<=cfg_work_floor&&cfg_hash_base+64'd9*(64'd1<<HASH_ADDR_WIDTH)<=cfg_work_floor&&
        cfg_node_base+64'd6*cfg_node_count<=cfg_work_floor&&cfg_edge_base+64'd4*cfg_edge_count<=cfg_work_floor;
    // Validate the live configuration in a separate clock stage. Comparing its
    // complete signature before admission preserves first-accepted-beat
    // snapshots, including when configuration changes while an input waits.
    localparam integer CONFIG_WIDTH=11*MEMORY_ADDR_WIDTH+69;
    wire [CONFIG_WIDTH-1:0] config_signature={cfg_profile,cfg_class_base,cfg_hash_base,cfg_node_base,cfg_edge_base,
        cfg_node_count,cfg_edge_count,cfg_work_floor,cfg_scalar_base,cfg_merge_base,cfg_commit_base,cfg_scalar_bytes,cfg_merge_bytes,cfg_commit_bytes};
    reg [CONFIG_WIDTH-1:0] validated_signature;
    reg validated_good,validation_valid;
    wire configuration_matches=validation_valid&&config_signature==validated_signature;
    always @(posedge clk)begin
        if(rst)begin validated_signature<=0;validated_good<=0;validation_valid<=0;end
        else begin validated_signature<=config_signature;validated_good<=configuration_good;validation_valid<=1;end
    end
    wire pre_ready,pre_valid,pre_keep,pre_last,pre_eos,pre_drained,pre_error;
    wire [7:0] pre_data,pre_error_code,pre_error_status;
    wire [USER_WIDTH-1:0] pre_user;
    wire class_req_valid,class_req_ready,class_rsp_valid,class_rsp_ready,class_idle;
    wire [20:0] class_cp;wire [1:0] class_value;wire [7:0] class_status;
    wire [MEMORY_ADDR_WIDTH-1:0] active_class_base;
    wire input_to_pre=(state==IDLE&&admit_sequences&&configuration_matches&&validated_good)||(state==BYTE&&!source_closed);
    assign s_axis_text_tready=!rst&&((state==DRAIN_RAW||(state==IDLE&&admit_sequences&&configuration_matches&&!validated_good))?1'b1:input_to_pre&&pre_ready);
    wire pre_consume;
    bpe_pretokenizer #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) frontend(
        .clk(clk),.rst(flush),.admit_sequences(state==IDLE&&admit_sequences&&configuration_matches&&validated_good),
        .cfg_profile(state==IDLE?cfg_profile:profile),.cfg_workspace_base(state==IDLE?cfg_scalar_base:scalar_base),
        .cfg_workspace_bytes(state==IDLE?cfg_scalar_bytes:scalar_bytes),.cfg_class_base(state==IDLE?cfg_class_base:class_base),.active_class_base(active_class_base),
        .s_axis_text_tdata(s_axis_text_tdata),.s_axis_text_tkeep(s_axis_text_tkeep),.s_axis_text_tvalid(s_axis_text_tvalid&&input_to_pre),.s_axis_text_tready(pre_ready),
        .s_axis_text_tlast(s_axis_text_tlast),.s_axis_text_tuser(s_axis_text_tuser),
        .m_data(pre_data),.m_keep(pre_keep),.m_valid(pre_valid),.m_ready(pre_consume),.m_piece_last(pre_last),.m_sequence_last(pre_eos),.m_user(pre_user),
        .class_req_valid(class_req_valid),.class_req_ready(class_req_ready),.class_req_codepoint(class_cp),
        .class_rsp_valid(class_rsp_valid),.class_rsp_ready(class_rsp_ready),.class_rsp_class(class_value),.class_rsp_status(class_status),
        .mem_valid(mem_valid[1]),.mem_ready(mem_ready[1]),.mem_write(mem_write[1]),.mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[4+:4]),.mem_data(mem_data[72+:72]),
        .mem_rsp_valid(mem_rsp_valid[1]),.mem_rsp_ready(mem_rsp_ready[1]),.mem_rsp_data(mem_rsp_data[72+:72]),.mem_rsp_status(mem_rsp_status[8+:8]),
        .error_valid(pre_error),.error_ready(state==ABORT),.error_code(pre_error_code),.error_status(pre_error_status),.error_user(),.idle(),.drained(pre_drained));
    unicode_external_lookup #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) classifier(
        .clk(clk),.rst(flush),.cfg_unlock(1'b0),.class_base(active_class_base),
        .req_valid(class_req_valid),.req_ready(class_req_ready),.req_codepoint(class_cp),
        .rsp_valid(class_rsp_valid),.rsp_ready(class_rsp_ready),.rsp_class(class_value),.rsp_status(class_status),
        .mem_rd_valid(mem_valid[0]),.mem_rd_ready(mem_ready[0]),.mem_rd_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_rd_bytes(mem_bytes[0+:4]),
        .mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(class_idle));
    assign mem_write[0]=0;assign mem_data[0+:72]=0;

    // This slot owns a byte transition until its result has been consumed,
    // including while the main sequencer drains a failed prompt.
    localparam T_EMPTY=0,T_ISSUE=1,T_WAIT=2,T_RESULT=3;
    reg [1:0] trie_slot_state;
    reg [7:0] trie_byte;
    reg trie_match,trie_terminal;
    reg [ID_WIDTH-1:0] trie_token;
    reg [7:0] trie_status;
    wire trie_req_ready,trie_rsp_valid,trie_rsp_match,trie_rsp_terminal,trie_idle;
    wire [ID_WIDTH-1:0] trie_rsp_token;wire [7:0] trie_rsp_status;
    trie_search_pipeline #(.NODE_WIDTH(NODE_WIDTH),.ID_WIDTH(ID_WIDTH),.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) trie(
        .clk(clk),.rst(flush),.cfg_unlock(1'b0),.cfg_node_base(node_base),.cfg_edge_base(edge_base),.cfg_node_count(node_count),.cfg_edge_count(edge_count),
        .req_valid(trie_slot_state==T_ISSUE),.req_ready(trie_req_ready),.req_node({NODE_WIDTH{1'b0}}),.req_byte(trie_byte),.req_last(1'b1),.req_user(context_id),
        .rsp_valid(trie_rsp_valid),.rsp_ready(trie_slot_state==T_WAIT),.rsp_match(trie_rsp_match),.rsp_terminal(trie_rsp_terminal),.rsp_next_node(),.rsp_token(trie_rsp_token),.rsp_last(),.rsp_user(),.rsp_status(trie_rsp_status),
        .mem_rd_valid(mem_valid[2+:3]),.mem_rd_ready(mem_ready[2+:3]),.mem_rd_addr(mem_addr[2*MEMORY_ADDR_WIDTH+:3*MEMORY_ADDR_WIDTH]),.mem_rd_bytes(mem_bytes[8+:12]),
        .mem_rsp_valid(mem_rsp_valid[2+:3]),.mem_rsp_ready(mem_rsp_ready[2+:3]),.mem_rsp_data(mem_rsp_data[144+:216]),.mem_rsp_status(mem_rsp_status[16+:24]),.idle(trie_idle));
    assign mem_write[2+:3]=0;assign mem_data[144+:216]=0;
    always @(posedge clk)begin
        if(flush)begin trie_slot_state<=T_EMPTY;trie_byte<=0;trie_match<=0;trie_terminal<=0;trie_token<=0;trie_status<=0;end
        else case(trie_slot_state)
            T_EMPTY:if(state==BYTE&&pre_valid&&pre_consume&&pre_keep)begin trie_byte<=pre_data;trie_slot_state<=T_ISSUE;end
            T_ISSUE:if(trie_req_ready)trie_slot_state<=T_WAIT;
            T_WAIT:if(trie_rsp_valid)begin trie_match<=trie_rsp_match;trie_terminal<=trie_rsp_terminal;trie_token<=trie_rsp_token;trie_status<=trie_rsp_status;trie_slot_state<=T_RESULT;end
            T_RESULT:if(state==TRIE_WAIT||state==ABORT)trie_slot_state<=T_EMPTY;
        endcase
    end

    wire merge_input_ready,merge_valid,merge_keep,merge_last,merge_eos,merge_idle,merge_error;
    assign pre_consume=(state==BYTE&&merge_input_ready&&trie_slot_state==T_EMPTY)||state==ABORT;
    wire [ID_WIDTH-1:0] merge_token;wire [USER_WIDTH-1:0] merge_user;
    wire [7:0] merge_error_code,merge_error_status;
    wire rank_req_valid,rank_req_ready,rank_rsp_valid,rank_rsp_ready,rank_found,rank_idle;
    wire [ID_WIDTH-1:0] rank_left,rank_right,rank_merged,rank_rank;wire [7:0] rank_status;
    wire [63:0] commit_address=commit_base+64'd4*token_count;
    wire commit_room=commit_remaining!=0;
    wire slot_req_ready,slot_result_valid,slot_idle;
    wire [71:0] slot_result_data;wire [7:0] slot_result_status;
    wire merge_output_ready=state==ABORT||(state==MERGE_WAIT&&(!merge_keep||!commit_room||slot_req_ready));
    bpe_external_merge_unit #(.ID_WIDTH(ID_WIDTH),.RANK_WIDTH(ID_WIDTH),.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) merger(
        .clk(clk),.rst(flush),.cancel(state==ABORT),.cfg_base(merge_base),.cfg_bytes(merge_bytes),
        .s_token(byte_token),.s_keep(kept_byte),.s_valid(state==FEED),.s_ready(merge_input_ready),.s_piece_last(piece_last),.s_sequence_last(sequence_last),.s_user(context_id),
        .m_token(merge_token),.m_keep(merge_keep),.m_valid(merge_valid),.m_ready(merge_output_ready),.m_piece_last(merge_last),.m_sequence_last(merge_eos),.m_user(merge_user),
        .rank_req_valid(rank_req_valid),.rank_req_ready(rank_req_ready),.rank_req_left(rank_left),.rank_req_right(rank_right),
        .rank_rsp_valid(rank_rsp_valid),.rank_rsp_ready(rank_rsp_ready),.rank_rsp_found(rank_found),.rank_rsp_merged(rank_merged),.rank_rsp_rank(rank_rank),.rank_rsp_status(rank_status),
        .mem_valid(mem_valid[6]),.mem_ready(mem_ready[6]),.mem_write(mem_write[6]),.mem_addr(mem_addr[6*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[24+:4]),.mem_data(mem_data[432+:72]),
        .mem_rsp_valid(mem_rsp_valid[6]),.mem_rsp_ready(mem_rsp_ready[6]),.mem_rsp_data(mem_rsp_data[432+:72]),.mem_rsp_status(mem_rsp_status[48+:8]),
        .error_valid(merge_error),.error_ready(state==ABORT),.error_code(merge_error_code),.error_status(merge_error_status),.error_user(),.idle(merge_idle));
    bpe_rank_lookup #(.ID_WIDTH(ID_WIDTH),.RANK_WIDTH(ID_WIDTH),.HASH_ADDR_WIDTH(HASH_ADDR_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) ranks(
        .clk(clk),.rst(flush),.cfg_unlock(1'b0),.cfg_valid(1'b0),.cfg_ready(),.cfg_addr({HASH_ADDR_WIDTH{1'b0}}),.cfg_data(72'd0),
        .req_valid(rank_req_valid),.req_ready(rank_req_ready),.req_left(rank_left),.req_right(rank_right),
        .rsp_valid(rank_rsp_valid),.rsp_ready(rank_rsp_ready),.rsp_found(rank_found),.rsp_merged(rank_merged),.rsp_rank(rank_rank),.rsp_status(rank_status),.idle(rank_idle),.hash_base(hash_base),
        .mem_rd_valid(mem_valid[5]),.mem_rd_ready(mem_ready[5]),.mem_rd_addr(mem_addr[5*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_rd_bytes(mem_bytes[20+:4]),
        .mem_rsp_valid(mem_rsp_valid[5]),.mem_rsp_ready(mem_rsp_ready[5]),.mem_rsp_data(mem_rsp_data[360+:72]),.mem_rsp_status(mem_rsp_status[40+:8]));
    assign mem_write[5]=0;assign mem_data[360+:72]=0;
    wire slot_write=state==MERGE_WAIT;
    wire slot_req_valid=(state==MERGE_WAIT&&merge_valid&&merge_keep&&commit_room)||state==READ_REQ;
    wire [63:0] slot_address=slot_write?commit_address:commit_base+64'd4*release_index;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) commit_slot(
        .clk(clk),.rst(flush),.req_valid(slot_req_valid),.req_ready(slot_req_ready),.req_write(slot_write),.req_addr(slot_address[MEMORY_ADDR_WIDTH-1:0]),.req_bytes(4'd4),.req_data({{(72-ID_WIDTH){1'b0}},merge_token}),
        .result_valid(slot_result_valid),.result_ready(state==COMMIT_WAIT||state==READ_WAIT||state==ABORT),.result_data(slot_result_data),.result_status(slot_result_status),
        .mem_valid(mem_valid[7]),.mem_ready(mem_ready[7]),.mem_write(mem_write[7]),.mem_addr(mem_addr[7*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[28+:4]),.mem_data(mem_data[504+:72]),
        .mem_rsp_valid(mem_rsp_valid[7]),.mem_rsp_ready(mem_rsp_ready[7]),.mem_rsp_data(mem_rsp_data[504+:72]),.mem_rsp_status(mem_rsp_status[56+:8]),.idle(slot_idle));
    assign m_axis_tokens_tvalid=state==OUT_TOKEN||state==EMPTY_OUT||state==ABORT_TERM;
    assign m_axis_tokens_tdata=state==OUT_TOKEN?output_token:32'd0;
    assign m_axis_tokens_tkeep=state==OUT_TOKEN?4'hf:4'd0;
    assign m_axis_tokens_tlast=state!=OUT_TOKEN||release_index+1==token_count;
    assign m_axis_tokens_tuser=context_id;
    assign completion_valid=state==DONE_OK||state==DONE_BAD;
    assign completion_failed=state==DONE_BAD;
    assign completion_count=state==DONE_OK?token_count:32'd0;
    assign completion_user=context_id;
    assign error_valid=state==ERROR_STATE;assign error_user=context_id;
    // Pending, unaccepted text is not admitted work. The epoch controller
    // closes admission before checking this drained state; a first-beat
    // handshake changes state immediately and therefore blocks that barrier.
    assign idle=state==IDLE&&pre_drained&&merge_idle&&trie_idle&&class_idle&&rank_idle&&slot_idle&&trie_slot_state==T_EMPTY;
    wire children_idle=pre_drained&&merge_idle&&trie_idle&&class_idle&&rank_idle&&slot_idle&&trie_slot_state==T_EMPTY;
    wire processing=state==BYTE||state==TRIE_WAIT||state==FEED||state==MERGE_WAIT||state==COMMIT_WAIT||state==RELEASE||state==READ_REQ||state==READ_WAIT||state==OUT_TOKEN||state==EMPTY_OUT;
    task fail(input [7:0] stage_value,input [7:0] detail_value,input [7:0] status_value);
        begin error_stage<=stage_value;error_detail<=detail_value;error_status<=status_value;state<=ABORT;end
    endtask
    initial begin
        if(ID_WIDTH>32||ID_WIDTH<1||MEMORY_ADDR_WIDTH>31)$error("Unsupported tokenizer field widths");
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;source_closed<=0;source_bad<=0;release_started<=0;piece_last<=0;sequence_last<=0;kept_byte<=0;
            profile<=0;class_base<=0;hash_base<=0;node_base<=0;edge_base<=0;scalar_base<=0;merge_base<=0;commit_base<=0;
            scalar_bytes<=0;merge_bytes<=0;commit_bytes<=0;commit_remaining<=0;node_count<=0;edge_count<=0;token_count<=0;release_index<=0;output_token<=0;byte_token<=0;context_id<=0;
            error_stage<=0;error_detail<=0;error_status<=0;
        end else begin
            case(state)
                IDLE:if(s_axis_text_tvalid&&s_axis_text_tready)begin
                    context_id<=s_axis_text_tuser;source_closed<=s_axis_text_tlast;source_bad<=0;release_started<=0;token_count<=0;release_index<=0;
                    profile<=cfg_profile;class_base<=cfg_class_base;hash_base<=cfg_hash_base;node_base<=cfg_node_base;edge_base<=cfg_edge_base;
                    node_count<=cfg_node_count;edge_count<=cfg_edge_count;scalar_base<=cfg_scalar_base;merge_base<=cfg_merge_base;commit_base<=cfg_commit_base;
                    scalar_bytes<=cfg_scalar_bytes;merge_bytes<=cfg_merge_bytes;commit_bytes<=cfg_commit_bytes;
                    commit_remaining<=cfg_commit_bytes[MEMORY_ADDR_WIDTH:2];
                    error_stage<=0;error_detail<=0;error_status<=0;
                    if(!validated_good)begin error_stage<=1;state<=s_axis_text_tlast?ERROR_STATE:DRAIN_RAW;end else state<=BYTE;
                end
                BYTE:if(pre_valid&&pre_consume)begin
                    piece_last<=pre_last;sequence_last<=pre_eos;kept_byte<=pre_keep;
                    if(pre_keep)state<=TRIE_WAIT;else begin byte_token<=0;state<=FEED;end
                end
                TRIE_WAIT:if(trie_slot_state==T_RESULT)begin
                    if(trie_status!=0||!trie_match||!trie_terminal)fail(3,(trie_status!=0?8'd0:!trie_match?8'd1:8'd2),trie_status);
                    else begin byte_token<=trie_token;state<=FEED;end
                end
                FEED:if(merge_input_ready)state<=piece_last?MERGE_WAIT:BYTE;
                MERGE_WAIT:if(merge_valid&&merge_output_ready)begin
                    if(merge_user!=context_id)fail(4,8'd7,0);
                    else if(merge_keep)begin
                        if(!commit_room)fail(5,0,0);
                        else begin piece_last<=merge_last;sequence_last<=merge_eos;state<=COMMIT_WAIT;end
                    end else if(!merge_last)fail(4,8'd8,0);
                    else state<=merge_eos?RELEASE:BYTE;
                end
                COMMIT_WAIT:if(slot_result_valid)begin
                    if(slot_result_status!=0)fail(6,0,slot_result_status);
                    else begin token_count<=token_count+1'b1;commit_remaining<=commit_remaining-1'b1;state<=piece_last?(sequence_last?RELEASE:BYTE):MERGE_WAIT;end
                end
                RELEASE:begin release_index<=0;state<=token_count==0?EMPTY_OUT:READ_REQ;end
                READ_REQ:if(slot_req_ready)state<=READ_WAIT;
                READ_WAIT:if(slot_result_valid)begin
                    if(slot_result_status!=0)fail(7,0,slot_result_status);
                    else if((slot_result_data[31:0]>>ID_WIDTH)!=0)fail(8,0,0);
                    else begin output_token<=slot_result_data[31:0];state<=OUT_TOKEN;end
                end
                OUT_TOKEN:if(m_axis_tokens_tready)begin
                    release_started<=1;
                    if(release_index+1==token_count)state<=DONE_OK;else begin release_index<=release_index+1'b1;state<=READ_REQ;end
                end
                EMPTY_OUT:if(m_axis_tokens_tready)state<=DONE_OK;
                DRAIN_RAW:if(s_axis_text_tvalid&&s_axis_text_tready&&s_axis_text_tlast)state<=ERROR_STATE;
                ABORT:if(children_idle)state<=release_started?ABORT_TERM:ERROR_STATE;
                ABORT_TERM:if(m_axis_tokens_tready)state<=ERROR_STATE;
                ERROR_STATE:if(error_ready)state<=DONE_BAD;
                DONE_OK,DONE_BAD:if(completion_ready)state<=RESET_PIPE;
                RESET_PIPE:begin source_closed<=0;source_bad<=0;state<=IDLE;end
                default:state<=RESET_PIPE;
            endcase
            if(state!=IDLE&&state!=DRAIN_RAW&&s_axis_text_tvalid&&s_axis_text_tready)begin
                if(s_axis_text_tlast)source_closed<=1;
                if(s_axis_text_tuser!=context_id)source_bad<=1;
            end
            if(processing)begin
                if(source_bad&&source_closed)fail(9,0,0);
                else if(pre_error)fail(2,pre_error_code,pre_error_status);
                else if(merge_error)fail(4,merge_error_code,merge_error_status);
            end
        end
    end
endmodule
`default_nettype wire
