`timescale 1ns/1ps
`default_nettype none
// One generated token -> inverse lookup -> 128-bit BoW -> UTF-8/application
// response. The caller supplies a validated RPC lease and external carry.
// Local idle retires a chunk, not the complete GPU/RPC image lease.
module generated_response_chunk #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384
)(
    input wire clk,input wire rst,
    input wire [31:0] s_axis_tokens_tdata,input wire [3:0] s_axis_tokens_tkeep,
    input wire s_axis_tokens_tvalid,output wire s_axis_tokens_tready,
    input wire s_axis_tokens_tlast,input wire [USER_WIDTH-1:0] s_axis_tokens_tuser,
    input wire lease_valid,input wire [USER_WIDTH-1:0] lease_user,lease_application,
    input wire [30:0] lease_stream,input wire [31:0] lease_generation,lease_model_epoch,lease_schema_epoch,
    input wire [31:0] cfg_active_model_epoch,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_directory_base,cfg_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_directory_bytes,cfg_pool_bytes,
    input wire cfg_strip_special,cfg_replace_invalid,input wire [1:0] cfg_format,input wire [28:0] cfg_protobuf_field,
    input wire [23:0] carry_in,input wire [1:0] carry_in_count,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire result_valid,input wire result_ready,output wire [7:0] result_stage,result_status,
    output wire [7:0] result_memory_status,
    output wire [23:0] carry_out,output wire [1:0] carry_out_count,output wire [31:0] result_bytes,
    output wire [USER_WIDTH-1:0] result_user,result_application,
    output wire [30:0] result_stream,output wire [31:0] result_generation,result_model_epoch,result_schema_epoch,
    output wire result_eos,
    output wire mem_rd_valid,input wire mem_rd_ready,output wire [MEMORY_ADDR_WIDTH-1:0] mem_rd_addr,
    output wire [3:0] mem_rd_bytes,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,output wire idle
);
    localparam IDLE=0,CHECK=1,START_CHUNK=2,SEND_TOKEN=3,SEND_EMPTY=4,RUN=5,RESULT=6;
    reg [2:0] state;
    reg [31:0] token,generation,model_epoch,schema_epoch;
    reg token_present,eos,strip_special,replace_invalid;
    reg [USER_WIDTH-1:0] owner,application;
    reg [30:0] stream_id;reg [1:0] format_mode;reg [28:0] protobuf_field;
    reg [MEMORY_ADDR_WIDTH-1:0] directory_base,pool_base;
    reg [MEMORY_ADDR_WIDTH:0] directory_bytes,pool_bytes;
    reg [23:0] original_carry;reg [1:0] original_count;
    reg [7:0] binding_status,guard_status,lookup_status,memory_status;
    reg external_pending,local_response,first_read,response_directory;
    wire [63:0] directory_end={1'b0,directory_base}+{1'b0,directory_bytes};
    wire [63:0] pool_end={1'b0,pool_base}+{1'b0,pool_bytes};
    wire [63:0] token_end={32'd0,token}*8+8;
    wire config_good=directory_bytes>=8&&directory_bytes[2:0]==0&&pool_bytes>=8&&pool_bytes[2:0]==0&&
        directory_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&pool_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (directory_end<=pool_base||pool_end<=directory_base);
    wire engine_idle,engine_ready,engine_error,engine_rd_valid,engine_rd_ready,engine_rsp_valid,engine_rsp_ready;
    wire [7:0] engine_error_code,engine_rsp_status;
    wire [MEMORY_ADDR_WIDTH-1:0] engine_rd_addr;wire [3:0] engine_rd_bytes;
    wire [71:0] engine_rsp_data;
    wire [63:0] request_end={1'b0,engine_rd_addr}+{60'd0,engine_rd_bytes};
    wire request_good=engine_rd_bytes==8&&(first_read?
        engine_rd_addr>=directory_base&&request_end<=directory_end:
        engine_rd_addr>=pool_base&&request_end<=pool_end);
    wire [63:0] entry_end={32'd0,mem_rsp_data[47:16]}+{48'd0,mem_rsp_data[63:48]};
    wire entry_bad=response_directory&&mem_rsp_status==0&&mem_rsp_data[1]&&
        (mem_rsp_data[15:2]!=0||entry_end>{1'b0,pool_bytes});
    assign mem_rd_valid=engine_rd_valid&&!external_pending&&!local_response&&request_good;
    assign mem_rd_addr=engine_rd_addr;assign mem_rd_bytes=engine_rd_bytes;
    assign engine_rd_ready=!external_pending&&!local_response&&(request_good?mem_rd_ready:1'b1);
    assign engine_rsp_valid=local_response||(external_pending&&mem_rsp_valid);
    assign engine_rsp_data=local_response?72'd0:mem_rsp_data;
    assign engine_rsp_status=local_response ? 8'he1:entry_bad ? 8'he2:mem_rsp_status;
    assign mem_rsp_ready=external_pending&&engine_rsp_ready;
    wire [127:0] raw_data,bow_data;wire [15:0] raw_keep,bow_keep;
    wire [USER_WIDTH-1:0] raw_user,bow_user;
    wire raw_valid,raw_ready,raw_last,bow_valid,bow_ready,bow_last;
    wire [127:0] bridge_data=state==SEND_EMPTY?128'd0:raw_data;
    wire [15:0] bridge_keep=state==SEND_EMPTY?16'd0:raw_keep;
    wire bridge_valid=state==SEND_EMPTY||raw_valid;
    wire bridge_ready;
    assign raw_ready=bridge_ready&&state!=SEND_EMPTY;
    wire chunk_ready,chunk_result,chunk_idle;
    wire [7:0] chunk_stage,chunk_status;
    wire [23:0] chunk_carry;wire [1:0] chunk_count;wire [31:0] chunk_bytes;
    assign s_axis_tokens_tready=!rst&&state==IDLE&&engine_idle&&chunk_ready;
    assign result_valid=state==RESULT;
    assign result_stage=binding_status!=0 ? 8'd1:guard_status!=0 ? 8'd2:lookup_status!=0 ? 8'd3:
        chunk_stage!=0 ? chunk_stage+8'd3:8'd0;
    assign result_status=binding_status!=0?binding_status:guard_status!=0?guard_status:lookup_status!=0?lookup_status:chunk_status;
    assign result_memory_status=memory_status;
    assign carry_out=result_status!=0?original_carry:chunk_carry;
    assign carry_out_count=result_status!=0?original_count:chunk_count;
    assign result_bytes=result_status!=0?32'd0:chunk_bytes;
    assign result_user=owner;assign result_application=application;assign result_stream=stream_id;
    assign result_generation=generation;assign result_model_epoch=model_epoch;assign result_schema_epoch=schema_epoch;
    assign result_eos=eos;
    assign idle=state==IDLE&&engine_idle&&chunk_idle&&!external_pending&&!local_response;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;token<=0;generation<=0;model_epoch<=0;schema_epoch<=0;token_present<=0;eos<=0;strip_special<=0;replace_invalid<=0;
            owner<=0;application<=0;stream_id<=0;format_mode<=0;protobuf_field<=0;directory_base<=0;pool_base<=0;directory_bytes<=0;pool_bytes<=0;
            original_carry<=0;original_count<=0;binding_status<=0;guard_status<=0;lookup_status<=0;memory_status<=0;
            external_pending<=0;local_response<=0;first_read<=1;response_directory<=0;
        end else begin
            if(engine_rd_valid&&engine_rd_ready)begin
                first_read<=0;response_directory<=first_read;
                if(request_good)external_pending<=1;
                else begin local_response<=1;guard_status<=1;end
            end
            if(engine_rsp_valid&&engine_rsp_ready)begin
                if(local_response)local_response<=0;
                else begin
                    external_pending<=0;
                    if(entry_bad)guard_status<=2;
                    if(mem_rsp_status!=0&&memory_status==0)memory_status<=mem_rsp_status;
                end
            end
            if(engine_error&&lookup_status==0)lookup_status<=engine_error_code;
            case(state)
                IDLE:if(s_axis_tokens_tvalid&&s_axis_tokens_tready)begin
                    token<=s_axis_tokens_tdata;token_present<=s_axis_tokens_tkeep==4'hf;eos<=s_axis_tokens_tlast;
                    owner<=lease_user;application<=lease_application;stream_id<=lease_stream;generation<=lease_generation;
                    model_epoch<=lease_model_epoch;schema_epoch<=lease_schema_epoch;
                    directory_base<=cfg_directory_base;directory_bytes<=cfg_directory_bytes;pool_base<=cfg_pool_base;pool_bytes<=cfg_pool_bytes;
                    strip_special<=cfg_strip_special;replace_invalid<=cfg_replace_invalid;format_mode<=cfg_format;protobuf_field<=cfg_protobuf_field;
                    original_carry<=carry_in;original_count<=carry_in_count;guard_status<=0;lookup_status<=0;memory_status<=0;first_read<=1;
                    binding_status<=!lease_valid?1:lease_model_epoch!=cfg_active_model_epoch?2:lease_generation==0?3:
                        (s_axis_tokens_tkeep!=4'hf&&(s_axis_tokens_tkeep!=0||!s_axis_tokens_tlast))?4:
                        s_axis_tokens_tuser!=lease_user?7:0;
                    state<=CHECK;
                end
                CHECK:if(binding_status!=0)state<=RESULT;
                    else if(!config_good)begin binding_status<=5;state<=RESULT;end
                    else if(token_present&&token_end>{1'b0,directory_bytes})begin binding_status<=6;state<=RESULT;end
                    else state<=START_CHUNK;
                START_CHUNK:if(chunk_ready)state<=token_present?SEND_TOKEN:SEND_EMPTY;
                SEND_TOKEN:if(engine_ready)state<=RUN;
                SEND_EMPTY:if(bridge_ready)state<=RUN;
                RUN:if(chunk_result&&engine_idle&&!external_pending&&!local_response)state<=RESULT;
                RESULT:if(result_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
    // A forced per-token boundary flushes short output promptly. Model bases
    // and strip policy still come from the externally held whole-RPC lease.
    detokenizer_engine #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),
        .POOL_ADDR_WIDTH(MEMORY_ADDR_WIDTH-3),.EXTERNAL_MEMORY(1)) lookup(
        .clk(clk),.rst(rst),.cfg_unlock(state==IDLE),.cfg_valid(1'b0),.cfg_ready(),.cfg_pool(1'b0),.cfg_addr(32'd0),.cfg_data(64'd0),.cfg_error(),
        .strip_special_tokens(strip_special),.directory_base(directory_base),.pool_base(pool_base),
        .s_axis_tokens_tdata(token),.s_axis_tokens_tvalid(state==SEND_TOKEN),.s_axis_tokens_tready(engine_ready),
        .s_axis_tokens_tlast(1'b1),.s_axis_tokens_tuser(application),
        .m_axis_text_tdata(raw_data),.m_axis_text_tkeep(raw_keep),.m_axis_text_tvalid(raw_valid),.m_axis_text_tready(raw_ready),
        .m_axis_text_tlast(raw_last),.m_axis_text_tuser(raw_user),
        .error_valid(engine_error),.error_ready(state==RUN),.error_code(engine_error_code),.error_user(),.idle(engine_idle),
        .mem_rd_valid(engine_rd_valid),.mem_rd_ready(engine_rd_ready),.mem_rd_addr(engine_rd_addr),.mem_rd_bytes(engine_rd_bytes),
        .mem_rsp_valid(engine_rsp_valid),.mem_rsp_ready(engine_rsp_ready),.mem_rsp_data(engine_rsp_data),.mem_rsp_status(engine_rsp_status));
    bow_axi_bridge #(.USER_WIDTH(USER_WIDTH)) bow(
        .clk(clk),.rst(rst),.s_ingress_tdata(128'd0),.s_ingress_tkeep(16'd0),.s_ingress_tvalid(1'b0),.s_ingress_tready(),
        .s_ingress_tlast(1'b0),.s_ingress_tuser({USER_WIDTH{1'b0}}),.m_ingress_tdata(),.m_ingress_tkeep(),.m_ingress_tvalid(),
        .m_ingress_tready(1'b1),.m_ingress_tlast(),.m_ingress_tuser(),
        .s_egress_tdata(bridge_data),.s_egress_tkeep(bridge_keep),.s_egress_tvalid(bridge_valid),.s_egress_tready(bridge_ready),
        .s_egress_tlast(state==SEND_EMPTY||raw_last),.s_egress_tuser(state==SEND_EMPTY?application:raw_user),
        .m_egress_tdata(bow_data),.m_egress_tkeep(bow_keep),.m_egress_tvalid(bow_valid),.m_egress_tready(bow_ready),
        .m_egress_tlast(bow_last),.m_egress_tuser(bow_user));
    utf8_serialized_chunk #(.USER_WIDTH(USER_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) response(
        .clk(clk),.rst(rst),.start_valid(state==START_CHUNK),.start_ready(chunk_ready),.start_user(application),
        .start_eos(eos),.start_replace(replace_invalid),.start_carry(original_carry),.start_carry_count(original_count),
        .start_format(format_mode),.start_protobuf_field(protobuf_field),
        .s_axis_text_tdata(bow_data),.s_axis_text_tkeep(bow_keep),.s_axis_text_tvalid(bow_valid),.s_axis_text_tready(bow_ready),
        .s_axis_text_tlast(bow_last),.s_axis_text_tuser(bow_user),.s_axis_text_abort(bow_last&&(lookup_status!=0||guard_status!=0)),
        .m_axis_tx_tdata(m_axis_tx_tdata),.m_axis_tx_tkeep(m_axis_tx_tkeep),.m_axis_tx_tvalid(m_axis_tx_tvalid),
        .m_axis_tx_tready(m_axis_tx_tready),.m_axis_tx_tlast(m_axis_tx_tlast),.m_axis_tx_tuser(m_axis_tx_tuser),
        .result_valid(chunk_result),.result_ready(state==RESULT&&result_ready&&binding_status==0),
        .result_stage(chunk_stage),.result_status(chunk_status),.result_carry(chunk_carry),.result_carry_count(chunk_count),
        .result_bytes(chunk_bytes),.result_user(),.idle(chunk_idle));
endmodule
`default_nettype wire
