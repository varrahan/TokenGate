`timescale 1ns/1ps
`default_nettype none
// Runtime-loadable inverse vocabulary and byte pool. Token length is 16 bits;
// the pool uses a full 32-bit byte offset. No 32-byte truncation is performed.
// Directory word: [63:48] length, [47:16] byte offset, [15:2] reserved,
//                 [1] entry valid, [0] special/control token.
module detokenizer_engine #(
    parameter integer VOCAB_ADDR_WIDTH=17,
    parameter integer POOL_ADDR_WIDTH=17,
    parameter integer USER_WIDTH=16,
    // SCU35 default: the common external loader owns table writes. The legacy
    // cfg_* word-loading port is active only with EXTERNAL_MEMORY=0.
    parameter integer EXTERNAL_MEMORY=1,
    parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk, input wire rst,
    input wire cfg_unlock, input wire cfg_valid, output wire cfg_ready,
    input wire cfg_pool, input wire [31:0] cfg_addr, input wire [63:0] cfg_data,
    output wire cfg_error,
    input wire strip_special_tokens,
    input wire [31:0] s_axis_tokens_tdata,
    input wire s_axis_tokens_tvalid, output wire s_axis_tokens_tready,
    input wire s_axis_tokens_tlast,
    input wire [USER_WIDTH-1:0] s_axis_tokens_tuser,
    output wire [127:0] m_axis_text_tdata, output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid, input wire m_axis_text_tready,
    output wire m_axis_text_tlast, output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire error_valid, input wire error_ready,
    output reg [7:0] error_code, output wire [USER_WIDTH-1:0] error_user,
    output wire idle,
    input wire [MEMORY_ADDR_WIDTH-1:0] directory_base,
    input wire [MEMORY_ADDR_WIDTH-1:0] pool_base,
    output wire mem_rd_valid,input wire mem_rd_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_rd_addr,
    output wire [3:0] mem_rd_bytes,
    input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status
);
    localparam IDLE=0,DIR_REQ=1,DIR_WAIT=2,POOL_REQ=3,POOL_WAIT=4,
               EMIT=5,END_MARKER=6,ERROR_STATE=7;
    reg [3:0] state;
    reg [31:0] token_id, byte_offset;
    reg [15:0] remaining;
    reg token_last,strip_latched;
    reg [USER_WIDTH-1:0] context_id;
    reg [63:0] pool_word;
    reg [2:0] lane;
    reg sequence_open;
    reg [MEMORY_ADDR_WIDTH-1:0] directory_base_latched,pool_base_latched;
    wire dir_cfg_ready,pool_cfg_ready,dir_req_ready,pool_req_ready;
    wire dir_rsp_valid,pool_rsp_valid;
    wire [63:0] dir_rsp_data,pool_rsp_data;
    wire cfg_in_range = cfg_pool ? ((cfg_addr >> POOL_ADDR_WIDTH)==0) :
                                              ((cfg_addr >> VOCAB_ADDR_WIDTH)==0);
    assign cfg_ready = !EXTERNAL_MEMORY && cfg_unlock && (cfg_pool ? pool_cfg_ready : dir_cfg_ready);
    assign cfg_error = cfg_valid && cfg_ready && !cfg_in_range;
    // Extend before arithmetic: a corrupt/configured base must not alias a
    // valid word by truncating an out-of-range external address.
    wire [63:0] directory_address={32'd0,token_id}*8+directory_base_latched;
    wire [63:0] pool_address={32'd0,byte_offset[31:3],3'd0}+pool_base_latched;
    wire directory_address_good=directory_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire pool_address_good=pool_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire dir_rsp_error=EXTERNAL_MEMORY && mem_rsp_status!=0;
    wire pool_rsp_error=EXTERNAL_MEMORY && mem_rsp_status!=0;
    generate if(EXTERNAL_MEMORY)begin: external_tables
        assign dir_cfg_ready=0;
        assign pool_cfg_ready=0;
        assign dir_req_ready=mem_rd_ready && directory_address_good;
        assign pool_req_ready=mem_rd_ready && pool_address_good;
        assign dir_rsp_valid=mem_rsp_valid && state==DIR_WAIT;
        assign pool_rsp_valid=mem_rsp_valid && state==POOL_WAIT;
        assign dir_rsp_data=mem_rsp_data[63:0];
        assign pool_rsp_data=mem_rsp_data[63:0];
        assign mem_rd_valid=!rst && ((state==DIR_REQ && directory_address_good) ||
                                                    (state==POOL_REQ && pool_address_good));
        assign mem_rd_addr=state==DIR_REQ ? directory_address[MEMORY_ADDR_WIDTH-1:0] : pool_address[MEMORY_ADDR_WIDTH-1:0];
        assign mem_rd_bytes=8;
        assign mem_rsp_ready=state==DIR_WAIT || state==POOL_WAIT;
    end else begin: native_tables
    assign mem_rd_valid=0;assign mem_rd_addr=0;assign mem_rd_bytes=0;assign mem_rsp_ready=0;
    programmable_table_ram #(.ADDR_WIDTH(VOCAB_ADDR_WIDTH)) inverted_vocab_table (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),
        .cfg_valid(cfg_valid && !cfg_pool && cfg_in_range),.cfg_ready(dir_cfg_ready),
        .cfg_addr(cfg_addr[VOCAB_ADDR_WIDTH-1:0]),.cfg_data(cfg_data),
        .rd_valid(state==DIR_REQ),.rd_ready(dir_req_ready),
        .rd_addr(token_id[VOCAB_ADDR_WIDTH-1:0]),
        .rsp_valid(dir_rsp_valid),.rsp_data(dir_rsp_data));
    programmable_table_ram #(.ADDR_WIDTH(POOL_ADDR_WIDTH)) string_pool_memory (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock),
        .cfg_valid(cfg_valid && cfg_pool && cfg_in_range),.cfg_ready(pool_cfg_ready),
        .cfg_addr(cfg_addr[POOL_ADDR_WIDTH-1:0]),.cfg_data(cfg_data),
        .rd_valid(state==POOL_REQ),.rd_ready(pool_req_ready),
        .rd_addr(byte_offset[POOL_ADDR_WIDTH+2:3]),
        .rsp_valid(pool_rsp_valid),.rsp_data(pool_rsp_data));
    end endgenerate
    wire byte_ready;
    wire byte_valid = state==EMIT || state==END_MARKER;
    wire byte_keep = state==EMIT;
    wire byte_last = (state==END_MARKER) || (state==EMIT && remaining==1 && token_last);
    axis_byte_packer #(.USER_WIDTH(USER_WIDTH)) byte_stream_reconstruct (
        .clk(clk),.rst(rst),.s_data(pool_word[lane*8 +: 8]),.s_keep(byte_keep),
        .s_valid(byte_valid),.s_ready(byte_ready),.s_last(byte_last),.s_user(context_id),
        .m_data(m_axis_text_tdata),.m_keep(m_axis_text_tkeep),
        .m_valid(m_axis_text_tvalid),.m_ready(m_axis_text_tready),
        .m_last(m_axis_text_tlast),.m_user(m_axis_text_tuser));
    // idle includes a partially packed packet and a stalled final beat.
    // sequence_open clears only when the final output beat is accepted.
    assign idle = state==IDLE && !sequence_open && !m_axis_text_tvalid;
    assign s_axis_tokens_tready = !rst && !cfg_unlock && state==IDLE &&
                                 !(m_axis_text_tvalid && m_axis_text_tlast);
    assign error_valid = state==ERROR_STATE;
    assign error_user = context_id;
    wire [32:0] entry_end = {1'b0,dir_rsp_data[47:16]} + {17'b0,dir_rsp_data[63:48]};
    always @(posedge clk) begin
        if(rst) begin
            state<=IDLE; token_id<=0; byte_offset<=0; remaining<=0;
            token_last<=0; context_id<=0; pool_word<=0; lane<=0;
            error_code<=0; strip_latched<=0; sequence_open<=0;
            directory_base_latched<=0;pool_base_latched<=0;
        end else begin
            if(m_axis_text_tvalid && m_axis_text_tready && m_axis_text_tlast)
                sequence_open<=0;
            case(state)
                IDLE: if(s_axis_tokens_tvalid && s_axis_tokens_tready) begin
                    token_id<=s_axis_tokens_tdata; token_last<=s_axis_tokens_tlast;
                    context_id<=s_axis_tokens_tuser;
                    sequence_open<=1;
                    if(!sequence_open)begin
                        directory_base_latched<=directory_base;pool_base_latched<=pool_base;
                        strip_latched<=strip_special_tokens;
                    end
                    if((s_axis_tokens_tdata >> VOCAB_ADDR_WIDTH)!=0) begin
                        error_code<=1; state<=ERROR_STATE;
                    end else state<=DIR_REQ;
                end
                DIR_REQ: if(EXTERNAL_MEMORY && !directory_address_good)begin error_code<=6;state<=ERROR_STATE;end
                         else if(dir_req_ready) state<=DIR_WAIT;
                DIR_WAIT: if(dir_rsp_valid) begin
                    if(dir_rsp_error)begin error_code<=4;state<=ERROR_STATE;end
                    else if(!dir_rsp_data[1]) begin error_code<=2; state<=ERROR_STATE; end
                    else if(entry_end > (64'd8 << POOL_ADDR_WIDTH)) begin
                        error_code<=3; state<=ERROR_STATE;
                    end else if(dir_rsp_data[63:48]==0 || (strip_latched && dir_rsp_data[0])) begin
                        state<=token_last ? END_MARKER : IDLE;
                    end else begin
                        remaining<=dir_rsp_data[63:48]; byte_offset<=dir_rsp_data[47:16];
                        lane<=dir_rsp_data[18:16]; state<=POOL_REQ;
                    end
                end
                POOL_REQ: if(EXTERNAL_MEMORY && !pool_address_good)begin error_code<=6;state<=ERROR_STATE;end
                          else if(pool_req_ready) state<=POOL_WAIT;
                POOL_WAIT: if(pool_rsp_valid) begin
                    if(pool_rsp_error)begin error_code<=5;state<=ERROR_STATE;end
                    else begin pool_word<=pool_rsp_data; state<=EMIT; end
                end
                EMIT: if(byte_ready) begin
                    remaining<=remaining-1'b1; byte_offset<=byte_offset+1'b1; lane<=lane+1'b1;
                    if(remaining==1) state<=IDLE;
                    else if(lane==7) state<=POOL_REQ;
                end
                END_MARKER: if(byte_ready) state<=IDLE;
                ERROR_STATE: if(error_ready) state<=token_last ? END_MARKER : IDLE;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
