`timescale 1ns/1ps
`default_nettype none
// Exact ranked BPE on a pretokenized byte-ID piece. Runtime workspace stores
// 8-byte nodes: token ID [31:0], next index [63:32], FFFFFFFF=end. Merging
// rewrites the left node and unlinks the right; node indices never shift.
// Full scans select lowest rank and leftmost ties. This is a correctness
// backend; priority-queue/throughput optimization remains separate work.
module bpe_external_merge_unit #(
    parameter integer ID_WIDTH=17,parameter integer RANK_WIDTH=17,
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,input wire cancel,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_bytes,
    input wire [ID_WIDTH-1:0] s_token,input wire s_keep,input wire s_valid,output wire s_ready,
    input wire s_piece_last,input wire s_sequence_last,input wire [USER_WIDTH-1:0] s_user,
    output wire [ID_WIDTH-1:0] m_token,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_piece_last,output wire m_sequence_last,output wire [USER_WIDTH-1:0] m_user,
    output wire rank_req_valid,input wire rank_req_ready,output wire [ID_WIDTH-1:0] rank_req_left,output wire [ID_WIDTH-1:0] rank_req_right,
    input wire rank_rsp_valid,output wire rank_rsp_ready,input wire rank_rsp_found,
    input wire [ID_WIDTH-1:0] rank_rsp_merged,input wire [RANK_WIDTH-1:0] rank_rsp_rank,input wire [7:0] rank_rsp_status,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire error_valid,input wire error_ready,output reg [7:0] error_code,output reg [7:0] error_status,
    output wire [USER_WIDTH-1:0] error_user,output wire idle
);
    localparam LOAD=0,STORE_CHECK=1,STORE_REQ=2,STORE_WAIT=3,HEAD_REQ=4,HEAD_WAIT=5,RIGHT_REQ=6,RIGHT_WAIT=7,
               RANK_REQ=8,RANK_WAIT=9,APPLY=10,MERGE_REQ=11,MERGE_WAIT=12,OUT_REQ=13,OUT_WAIT=14,EMIT=15,EMPTY=16,ERROR_STATE=17;
    localparam [31:0] END_INDEX=32'hffffffff;
    reg [4:0] state;
    reg piece_open,cancel_pending,sequence_last,store_last,store_adds,best_valid,out_last;
    reg [MEMORY_ADDR_WIDTH-1:0] base;
    reg [MEMORY_ADDR_WIDTH:0] capacity;
    reg [USER_WIDTH-1:0] context_id;
    reg [31:0] loaded,live_count,store_index,left_index,right_index,right_next,best_index,best_next,read_index,out_next,nodes_seen,emit_seen;
    reg [ID_WIDTH-1:0] last_loaded,left_token,right_token,best_merged,out_token;
    reg [RANK_WIDTH-1:0] best_rank;
    reg [63:0] store_record;
    wire cancelling=cancel||cancel_pending;
    wire [31:0] address_index=state==STORE_CHECK||state==STORE_REQ||state==STORE_WAIT?store_index:
                             state==MERGE_REQ||state==MERGE_WAIT?best_index:state==HEAD_REQ||state==HEAD_WAIT?32'd0:
                             state==RIGHT_REQ||state==RIGHT_WAIT?right_index:read_index;
    wire [63:0] byte_address=base+64'd8*address_index;
    // STORE_CHECK always checks store_index. Keep this bounds cone separate
    // from the state-selected address mux used by memory commands, avoiding
    // state -> address mux -> add/compare -> state feedback on this decision.
    wire [63:0] store_end=64'd8*store_index+8;
    wire store_good=store_end<=capacity&&{1'b0,base}+store_end<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire [63:0] configured_end=cfg_base+{1'b0,cfg_bytes};
    wire [31:0] response_next=mem_rsp_data[63:32];
    wire [31:0] response_token=mem_rsp_data[31:0];
    function bad_record(input [63:0] record_value,input [31:0] index_value,input [31:0] bound);
        begin bad_record=(record_value[31:0]>>ID_WIDTH)!=0||
            (record_value[63:32]!=END_INDEX&&!(record_value[63:32]>index_value&&record_value[63:32]<bound));end
    endfunction
    assign s_ready=!rst&&!cancelling&&state==LOAD;
    assign m_token=state==EMPTY?{ID_WIDTH{1'b0}}:out_token;
    assign m_keep=state==EMIT;
    assign m_valid=state==EMIT||state==EMPTY;
    assign m_piece_last=state==EMPTY||(state==EMIT&&out_last);
    assign m_sequence_last=m_piece_last&&sequence_last;
    assign m_user=context_id;
    assign rank_req_valid=!rst&&state==RANK_REQ;
    assign rank_req_left=left_token;assign rank_req_right=right_token;
    assign rank_rsp_ready=state==RANK_WAIT;
    assign mem_valid=!rst&&(state==STORE_REQ||state==HEAD_REQ||state==RIGHT_REQ||state==MERGE_REQ||state==OUT_REQ);
    assign mem_write=state==STORE_REQ||state==MERGE_REQ;
    assign mem_addr=byte_address[MEMORY_ADDR_WIDTH-1:0];assign mem_bytes=8;
    assign mem_data=state==MERGE_REQ?{8'd0,best_next,{(32-ID_WIDTH){1'b0}},best_merged}:{8'd0,store_record};
    assign mem_rsp_ready=state==STORE_WAIT||state==HEAD_WAIT||state==RIGHT_WAIT||state==MERGE_WAIT||state==OUT_WAIT;
    assign error_valid=state==ERROR_STATE;assign error_user=context_id;
    assign idle=state==LOAD&&!piece_open&&loaded==0;
    task clear_piece;
        begin state<=LOAD;piece_open<=0;loaded<=0;live_count<=0;cancel_pending<=0;best_valid<=0;nodes_seen<=0;emit_seen<=0;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=LOAD;piece_open<=0;cancel_pending<=0;sequence_last<=0;store_last<=0;store_adds<=0;best_valid<=0;
            base<=0;capacity<=0;context_id<=0;loaded<=0;live_count<=0;store_index<=0;left_index<=0;right_index<=0;right_next<=0;
            best_index<=0;best_next<=0;read_index<=0;out_next<=0;out_last<=0;nodes_seen<=0;emit_seen<=0;
            last_loaded<=0;left_token<=0;right_token<=0;best_merged<=0;out_token<=0;best_rank<=0;store_record<=0;error_code<=0;error_status<=0;
        end else begin
            if(cancel)cancel_pending<=1;
            if(cancelling)begin
                // Do not retract a stalled command or result. Finish any
                // accepted transaction before releasing this client's state.
                case(state)
                    STORE_REQ:if(mem_ready)state<=STORE_WAIT;
                    HEAD_REQ:if(mem_ready)state<=HEAD_WAIT;
                    RIGHT_REQ:if(mem_ready)state<=RIGHT_WAIT;
                    MERGE_REQ:if(mem_ready)state<=MERGE_WAIT;
                    OUT_REQ:if(mem_ready)state<=OUT_WAIT;
                    STORE_WAIT,HEAD_WAIT,RIGHT_WAIT,MERGE_WAIT,OUT_WAIT:if(mem_rsp_valid)clear_piece();
                    RANK_REQ:if(rank_req_ready)state<=RANK_WAIT;
                    RANK_WAIT:if(rank_rsp_valid)clear_piece();
                    EMIT,EMPTY:if(m_ready)clear_piece();
                    ERROR_STATE:if(error_ready)clear_piece();
                    default:clear_piece();
                endcase
            end else case(state)
                LOAD:if(s_valid&&s_ready&&(s_keep||s_piece_last))begin
                    if(!piece_open)begin base<=cfg_base;capacity<=cfg_bytes;context_id<=s_user;piece_open<=1;error_code<=0;error_status<=0;end
                    if((!piece_open&&configured_end>(64'd1<<MEMORY_ADDR_WIDTH))||(piece_open&&s_user!=context_id))begin
                        error_code<=piece_open?5:6;error_status<=0;state<=ERROR_STATE;
                    end else if(s_keep)begin
                        store_index<=loaded;store_record<={s_piece_last?END_INDEX:loaded+1'b1,{(32-ID_WIDTH){1'b0}},s_token};
                        store_last<=s_piece_last;store_adds<=1;last_loaded<=s_token;sequence_last<=s_sequence_last;state<=STORE_CHECK;
                    end else if(s_piece_last)begin
                        sequence_last<=s_sequence_last;
                        if(loaded==0)state<=EMPTY;
                        else begin
                            store_index<=loaded-1'b1;store_record<={END_INDEX,{(32-ID_WIDTH){1'b0}},last_loaded};
                            store_last<=1;store_adds<=0;state<=STORE_CHECK;
                        end
                    end
                end
                STORE_CHECK:if(!store_good)begin error_code<=1;error_status<=0;state<=ERROR_STATE;end else state<=STORE_REQ;
                STORE_REQ:if(mem_ready)state<=STORE_WAIT;
                STORE_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=2;error_status<=mem_rsp_status;state<=ERROR_STATE;end
                    else begin
                        if(store_adds)begin loaded<=loaded+1'b1;live_count<=live_count+1'b1;end
                        best_valid<=0;state<=store_last?HEAD_REQ:LOAD;
                    end
                end
                HEAD_REQ:if(mem_ready)state<=HEAD_WAIT;
                HEAD_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=2;error_status<=mem_rsp_status;state<=ERROR_STATE;end
                    else if(bad_record(mem_rsp_data[63:0],0,loaded)||(response_next==END_INDEX)!=(live_count==1))begin error_code<=4;error_status<=0;state<=ERROR_STATE;end
                    else begin
                        left_index<=0;left_token<=response_token[ID_WIDTH-1:0];nodes_seen<=1;right_index<=response_next;
                        state<=response_next==END_INDEX?APPLY:RIGHT_REQ;
                    end
                end
                RIGHT_REQ:if(mem_ready)state<=RIGHT_WAIT;
                RIGHT_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=2;error_status<=mem_rsp_status;state<=ERROR_STATE;end
                    else if(bad_record(mem_rsp_data[63:0],right_index,loaded)||(response_next==END_INDEX)!=(nodes_seen+1==live_count)||nodes_seen>=live_count)begin error_code<=4;error_status<=0;state<=ERROR_STATE;end
                    else begin right_token<=response_token[ID_WIDTH-1:0];right_next<=response_next;nodes_seen<=nodes_seen+1'b1;state<=RANK_REQ;end
                end
                RANK_REQ:if(rank_req_ready)state<=RANK_WAIT;
                RANK_WAIT:if(rank_rsp_valid)begin
                    if(rank_rsp_status!=0)begin error_code<=3;error_status<=rank_rsp_status;state<=ERROR_STATE;end
                    else begin
                        if(rank_rsp_found&&(!best_valid||rank_rsp_rank<best_rank))begin
                            best_valid<=1;best_rank<=rank_rsp_rank;best_merged<=rank_rsp_merged;best_index<=left_index;best_next<=right_next;
                        end
                        if(right_next==END_INDEX)state<=APPLY;
                        else begin left_index<=right_index;left_token<=right_token;right_index<=right_next;state<=RIGHT_REQ;end
                    end
                end
                APPLY:if(best_valid)state<=MERGE_REQ;else begin read_index<=0;emit_seen<=0;state<=OUT_REQ;end
                MERGE_REQ:if(mem_ready)state<=MERGE_WAIT;
                MERGE_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=2;error_status<=mem_rsp_status;state<=ERROR_STATE;end
                    else begin live_count<=live_count-1'b1;best_valid<=0;state<=HEAD_REQ;end
                end
                OUT_REQ:if(mem_ready)state<=OUT_WAIT;
                OUT_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=2;error_status<=mem_rsp_status;state<=ERROR_STATE;end
                    else if(bad_record(mem_rsp_data[63:0],read_index,loaded)||(response_next==END_INDEX)!=(emit_seen+1==live_count)||emit_seen>=live_count)begin error_code<=4;error_status<=0;state<=ERROR_STATE;end
                    // Capture the terminal decision with the validated record.
                    // It must not pass through a 32-bit comparison into every
                    // piece-reset enable on the output handshake.
                    else begin out_token<=response_token[ID_WIDTH-1:0];out_next<=response_next;out_last<=response_next==END_INDEX;emit_seen<=emit_seen+1'b1;state<=EMIT;end
                end
                EMIT:if(m_ready)begin if(out_last)clear_piece();else begin read_index<=out_next;state<=OUT_REQ;end end
                EMPTY:if(m_ready)clear_piece();
                ERROR_STATE:if(error_ready)clear_piece();
                default:clear_piece();
            endcase
        end
    end
endmodule
`default_nettype wire
