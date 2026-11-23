`timescale 1ns/1ps
`default_nettype none
// 128-bit text -> exact UTF-8 byte pieces. Scalar records are staged in a
// runtime-sized external workspace. Classification and memory commands are
// variable latency; writes must complete before the splitter starts reading.
// The system allocator must reserve a nonoverlapping workspace for this
// admitted sequence. No model tables or bytes are fixed in this module.
module bpe_pretokenizer #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,input wire admit_sequences,
    input wire [1:0] cfg_profile,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_workspace_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_workspace_bytes,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_class_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] active_class_base,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,input wire s_axis_text_tlast,input wire [USER_WIDTH-1:0] s_axis_text_tuser,
    output wire [7:0] m_data,output wire m_keep,output wire m_valid,input wire m_ready,
    output wire m_piece_last,output wire m_sequence_last,output wire [USER_WIDTH-1:0] m_user,
    output wire class_req_valid,input wire class_req_ready,output wire [20:0] class_req_codepoint,
    input wire class_rsp_valid,output wire class_rsp_ready,input wire [1:0] class_rsp_class,input wire [7:0] class_rsp_status,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire error_valid,input wire error_ready,output reg [7:0] error_code,output reg [7:0] error_status,
    output wire [USER_WIDTH-1:0] error_user,output wire idle,output wire drained
);
    localparam COLLECT=0,CLASS_REQ=1,CLASS_WAIT=2,WRITE_REQ=3,WRITE_WAIT=4,START_SPLIT=5,SPLIT=6,
               EMIT_READ_REQ=7,EMIT_READ_WAIT=8,EMIT_BYTES=9,EMIT_EMPTY=10,DRAIN_INPUT=11,ERROR_STATE=12,RESET_PIPE=13;
    reg [3:0] state;
    reg sequence_active,input_closed,drain_done,scalar_last,piece_sequence_last;
    reg [1:0] profile,emit_lane;
    reg [MEMORY_ADDR_WIDTH-1:0] workspace_base,class_base;
    reg [MEMORY_ADDR_WIDTH:0] workspace_bytes;
    // Complete eight-byte records that fit each independently checked limit.
    // These limits are captured with the base/length, so request/error control
    // does not depend on an address addition followed by an extent addition.
    reg [MEMORY_ADDR_WIDTH:0] workspace_record_capacity,address_record_capacity;
    reg [USER_WIDTH-1:0] context_id;
    reg [31:0] scalar_count,record_index,span_end,scalar_raw,emit_raw;
    reg [20:0] scalar_cp;reg [2:0] scalar_length,emit_length;
    reg [63:0] record_word;
    wire flush=rst||state==RESET_PIPE;
    wire collecting=state==COLLECT||state==CLASS_REQ||state==CLASS_WAIT||state==WRITE_REQ||state==WRITE_WAIT||state==DRAIN_INPUT;
    wire input_gate=collecting&&!input_closed&&(sequence_active||admit_sequences);
    wire unpack_ready,unpack_idle,byte_valid,byte_ready,byte_keep,byte_last;
    wire [7:0] byte_data;wire [USER_WIDTH-1:0] byte_user;
    assign s_axis_text_tready=input_gate&&unpack_ready;
    axis_byte_unpacker #(.DATA_WIDTH(128),.USER_WIDTH(USER_WIDTH)) unpacker(
        .clk(clk),.rst(flush),.s_data(s_axis_text_tdata),.s_keep(s_axis_text_tkeep),.s_valid(s_axis_text_tvalid&&input_gate),.s_ready(unpack_ready),
        .s_last(s_axis_text_tlast),.s_user(s_axis_text_tuser),.m_data(byte_data),.m_keep(byte_keep),.m_valid(byte_valid),.m_ready(byte_ready),.m_last(byte_last),.m_user(byte_user),.idle(unpack_idle));
    wire cp_valid,cp_ready,cp_keep,cp_last,cp_error,cp_error_ready,cp_idle;
    wire [20:0] cp_value;wire [31:0] cp_raw;wire [2:0] cp_length;
    wire [USER_WIDTH-1:0] cp_user;wire [7:0] cp_error_code;
    assign cp_ready=state==COLLECT||state==DRAIN_INPUT;
    assign cp_error_ready=state==COLLECT||state==DRAIN_INPUT;
    utf8_codepoint_reader #(.USER_WIDTH(USER_WIDTH)) scalar_reader(
        .clk(clk),.rst(flush),.s_data(byte_data),.s_keep(byte_keep),.s_valid(byte_valid),.s_ready(byte_ready),.s_last(byte_last),.s_user(byte_user),
        .m_codepoint(cp_value),.m_bytes(cp_raw),.m_length(cp_length),.m_keep(cp_keep),.m_valid(cp_valid),.m_ready(cp_ready),.m_last(cp_last),.m_user(cp_user),
        .error_valid(cp_error),.error_ready(cp_error_ready),.error_code(cp_error_code),.error_user(),.idle(cp_idle));
    wire split_start_ready,split_rd_valid,split_rd_ready,split_rsp_ready,split_valid,split_last,split_error,split_idle;
    wire [31:0] split_rd_index,split_start,split_count;wire [7:0] split_error_code,split_error_status;
    regex_splitter_fsm #(.USER_WIDTH(USER_WIDTH)) splitter(
        .clk(clk),.rst(flush),.s_valid(state==START_SPLIT),.s_ready(split_start_ready),.s_count(scalar_count),.s_profile(profile),.s_user(context_id),
        .rd_valid(split_rd_valid),.rd_ready(split_rd_ready),.rd_index(split_rd_index),
        .rd_rsp_valid(mem_rsp_valid&&state==SPLIT),.rd_rsp_ready(split_rsp_ready),.rd_rsp_record(mem_rsp_data[63:0]),.rd_rsp_status(mem_rsp_status),
        .m_valid(split_valid),.m_ready(state==SPLIT),.m_start(split_start),.m_count(split_count),.m_sequence_last(split_last),.m_user(),
        .error_valid(split_error),.error_ready(state==ERROR_STATE),.error_code(split_error_code),.error_status(split_error_status),.error_user(),.idle(split_idle));
    wire [63:0] new_write_end=64'd8*scalar_count+8;
    wire [63:0] write_address=workspace_base+64'd8*scalar_count;
    wire [63:0] read_address=workspace_base+64'd8*(state==SPLIT?split_rd_index:record_index);
    // The splitter guard is consumed only in SPLIT. Keep its address separate
    // from emit reads so an emit index cannot feed splitter control timing.
    wire [63:0] split_read_address=workspace_base+64'd8*split_rd_index;
    wire write_good=MEMORY_ADDR_WIDTH<64?
        scalar_count<workspace_record_capacity&&scalar_count<address_record_capacity:
        new_write_end<=workspace_bytes&&write_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire split_read_good=split_rd_index<scalar_count&&(MEMORY_ADDR_WIDTH<64?
        split_rd_index<address_record_capacity:split_read_address+8<=(64'd1<<MEMORY_ADDR_WIDTH));
    wire [63:0] configured_end={1'b0,cfg_workspace_base}+{1'b0,cfg_workspace_bytes};
    assign active_class_base=class_base;
    assign class_req_valid=!rst&&state==CLASS_REQ;
    assign class_req_codepoint=scalar_cp;
    assign class_rsp_ready=state==CLASS_WAIT;
    assign mem_valid=!rst&&(state==WRITE_REQ||state==EMIT_READ_REQ||(state==SPLIT&&split_rd_valid&&split_read_good));
    assign mem_write=state==WRITE_REQ;
    assign mem_addr=state==WRITE_REQ?write_address[MEMORY_ADDR_WIDTH-1:0]:read_address[MEMORY_ADDR_WIDTH-1:0];
    assign mem_bytes=8;
    assign mem_data={8'd0,record_word};
    assign split_rd_ready=state==SPLIT&&mem_ready&&split_read_good;
    assign mem_rsp_ready=state==WRITE_WAIT||state==EMIT_READ_WAIT||(state==SPLIT&&split_rsp_ready);
    assign m_valid=state==EMIT_BYTES||state==EMIT_EMPTY;
    assign m_keep=state==EMIT_BYTES;
    assign m_data=state==EMIT_EMPTY?8'd0:emit_raw[emit_lane*8+:8];
    assign m_piece_last=state==EMIT_EMPTY||(state==EMIT_BYTES&&emit_lane+1==emit_length&&record_index+1==span_end);
    assign m_sequence_last=m_piece_last&&piece_sequence_last;
    assign m_user=context_id;
    assign error_valid=state==ERROR_STATE;
    assign error_user=context_id;
    // drained describes admitted internal work; idle additionally accounts for
    // an input about to be accepted. The parent epoch closes admission first.
    assign drained=state==COLLECT&&!sequence_active&&unpack_idle&&cp_idle&&split_idle;
    assign idle=drained&&!(s_axis_text_tvalid&&input_gate);
    always @(posedge clk)begin
        if(rst)begin
            state<=COLLECT;sequence_active<=0;input_closed<=0;drain_done<=0;scalar_last<=0;piece_sequence_last<=0;
            profile<=0;emit_lane<=0;workspace_base<=0;workspace_bytes<=0;class_base<=0;context_id<=0;
            workspace_record_capacity<=0;address_record_capacity<=(64'd1<<MEMORY_ADDR_WIDTH)>>3;
            scalar_count<=0;record_index<=0;span_end<=0;scalar_raw<=0;emit_raw<=0;scalar_cp<=0;scalar_length<=0;emit_length<=0;record_word<=0;
            error_code<=0;error_status<=0;
        end else begin
            case(state)
                COLLECT:begin
                    if(cp_error)begin error_code<=4;error_status<=cp_error_code;drain_done<=1;state<=DRAIN_INPUT;end
                    else if(cp_valid&&cp_ready)begin
                        if(!cp_keep&&cp_last)state<=START_SPLIT;
                        else if(cp_keep)begin
                            scalar_cp<=cp_value;scalar_raw<=cp_raw;scalar_length<=cp_length;scalar_last<=cp_last;
                            if(!write_good)begin error_code<=3;error_status<=0;drain_done<=cp_last;state<=DRAIN_INPUT;end
                            else state<=CLASS_REQ;
                        end
                    end
                end
                CLASS_REQ:if(class_req_ready)state<=CLASS_WAIT;
                CLASS_WAIT:if(class_rsp_valid)begin
                    if(class_rsp_status!=0)begin error_code<=5;error_status<=class_rsp_status;drain_done<=scalar_last;state<=DRAIN_INPUT;end
                    else begin record_word<={6'd0,scalar_length,class_rsp_class,scalar_cp,scalar_raw};state<=WRITE_REQ;end
                end
                WRITE_REQ:if(mem_ready)state<=WRITE_WAIT;
                WRITE_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=6;error_status<=mem_rsp_status;drain_done<=scalar_last;state<=DRAIN_INPUT;end
                    else begin scalar_count<=scalar_count+1'b1;state<=scalar_last?START_SPLIT:COLLECT;end
                end
                START_SPLIT:if(split_start_ready)state<=SPLIT;
                SPLIT:begin
                    if(split_error)begin error_code<=7;error_status<=split_error_status;state<=ERROR_STATE;end
                    else if(split_rd_valid&&!split_read_good)begin error_code<=8;error_status<=0;state<=ERROR_STATE;end
                    else if(split_valid)begin
                        record_index<=split_start;span_end<=split_start+split_count;piece_sequence_last<=split_last;
                        if({1'b0,split_start}+{1'b0,split_count}>{1'b0,scalar_count})begin error_code<=8;error_status<=0;state<=ERROR_STATE;end
                        else if(split_count==0)state<=EMIT_EMPTY;
                        else state<=EMIT_READ_REQ;
                    end
                end
                EMIT_READ_REQ:if(mem_ready)state<=EMIT_READ_WAIT;
                EMIT_READ_WAIT:if(mem_rsp_valid)begin
                    if(mem_rsp_status!=0)begin error_code<=9;error_status<=mem_rsp_status;state<=ERROR_STATE;end
                    else if(mem_rsp_data[63:58]!=0||mem_rsp_data[57:55]<1||mem_rsp_data[57:55]>4)begin error_code<=10;error_status<=0;state<=ERROR_STATE;end
                    else begin emit_raw<=mem_rsp_data[31:0];emit_length<=mem_rsp_data[57:55];emit_lane<=0;state<=EMIT_BYTES;end
                end
                EMIT_BYTES:if(m_ready)begin
                    if(emit_lane+1==emit_length)begin
                        if(record_index+1==span_end)state<=piece_sequence_last?RESET_PIPE:SPLIT;
                        else begin record_index<=record_index+1'b1;state<=EMIT_READ_REQ;end
                    end else emit_lane<=emit_lane+1'b1;
                end
                EMIT_EMPTY:if(m_ready)state<=RESET_PIPE;
                DRAIN_INPUT:begin
                    if((cp_valid&&cp_ready&&cp_last)||cp_error)drain_done<=1;
                    if(drain_done&&input_closed&&unpack_idle&&cp_idle)state<=ERROR_STATE;
                end
                ERROR_STATE:if(error_ready)state<=RESET_PIPE;
                RESET_PIPE:begin
                    sequence_active<=0;input_closed<=0;drain_done<=0;scalar_count<=0;state<=COLLECT;
                end
                default:state<=COLLECT;
            endcase
            if(s_axis_text_tvalid&&s_axis_text_tready)begin
                if(s_axis_text_tlast)input_closed<=1;
                if(!sequence_active)begin
                    sequence_active<=1;profile<=cfg_profile;workspace_base<=cfg_workspace_base;workspace_bytes<=cfg_workspace_bytes;class_base<=cfg_class_base;
                    workspace_record_capacity<=cfg_workspace_bytes>>3;
                    address_record_capacity<=((64'd1<<MEMORY_ADDR_WIDTH)-{1'b0,cfg_workspace_base})>>3;
                    context_id<=s_axis_text_tuser;error_code<=0;error_status<=0;
                    if(cfg_profile>2||configured_end>(64'd1<<MEMORY_ADDR_WIDTH))begin
                        error_code<=cfg_profile>2?1:2;drain_done<=0;state<=DRAIN_INPUT;
                    end
                end
            end
        end
    end
endmodule
`default_nettype wire
