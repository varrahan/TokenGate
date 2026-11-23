`timescale 1ns/1ps
`default_nettype none
// Generated logical partition. Physical transport is not implemented here.
// Restore an actual RPC directory binding, pin its LOAD result through response
// retirement, and persist per-generation Unicode carry/ordinal/policy. The
// directory control arbiter must keep the held LOAD exclusive. Whole-RPC/GPU
// image ownership and HTTP/2 response framing remain the parent's responsibility.
module rpc_http2_response_partition #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384
)(
    input wire clk,input wire rst,
    input wire [31:0] s_axis_tokens_tdata,input wire [3:0] s_axis_tokens_tkeep,
    input wire s_axis_tokens_tvalid,output wire s_axis_tokens_tready,
    input wire s_axis_tokens_tlast,input wire [USER_WIDTH-1:0] s_axis_tokens_tuser,
    input wire [30:0] s_stream,input wire [31:0] s_generation,s_model_epoch,s_schema_epoch,s_ordinal,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_stream_base,cfg_progress_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_stream_bytes,cfg_progress_bytes,
    input wire [31:0] cfg_model_epoch,cfg_schema_epoch,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_directory_base,cfg_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_directory_bytes,cfg_pool_bytes,
    input wire cfg_strip_special,cfg_replace_invalid,input wire [1:0] cfg_format,input wire [28:0] cfg_protobuf_field,
    output wire directory_valid,input wire directory_ready,
    output wire [USER_WIDTH-1:0] directory_user,output wire [30:0] directory_stream,
    output wire [MEMORY_ADDR_WIDTH-1:0] directory_pool_base,output wire [MEMORY_ADDR_WIDTH:0] directory_pool_bytes,
    input wire directory_result_valid,output wire directory_result_ready,
    input wire [7:0] directory_status,directory_memory_status,
    input wire [MEMORY_ADDR_WIDTH-1:0] directory_address,
    input wire [USER_WIDTH-1:0] directory_application,
    input wire [31:0] directory_generation,input wire directory_protobuf,directory_unsupported_encoding,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire result_valid,input wire result_ready,output reg [7:0] result_stage,result_status,result_memory_status,
    output wire [USER_WIDTH-1:0] result_user,result_application,output wire [30:0] result_stream,
    output wire [31:0] result_generation,result_model_epoch,result_schema_epoch,result_ordinal,
    output reg [31:0] result_bytes,output wire result_eos,output reg result_tx_emitted,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire directory_lease_active,output wire idle,
    output wire [1:0] mem_valid,input wire [1:0] mem_ready,output wire [1:0] mem_write,
    output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [7:0] mem_bytes,output wire [143:0] mem_data,
    input wire [1:0] mem_rsp_valid,output wire [1:0] mem_rsp_ready,input wire [143:0] mem_rsp_data,input wire [15:0] mem_rsp_status
,
    output wire [31:0] link_r_s_axis_tokens_tdata,
    output wire [3:0] link_r_s_axis_tokens_tkeep,
    output wire  link_r_s_axis_tokens_tvalid,
    input wire  link_r_s_axis_tokens_tready,
    output wire  link_r_s_axis_tokens_tlast,
    output wire [USER_WIDTH-1:0] link_r_s_axis_tokens_tuser,
    output wire  link_r_lease_valid,
    output wire [USER_WIDTH-1:0] link_r_lease_user,
    output wire [USER_WIDTH-1:0] link_r_lease_application,
    output wire [30:0] link_r_lease_stream,
    output wire [31:0] link_r_lease_generation,
    output wire [31:0] link_r_lease_model_epoch,
    output wire [31:0] link_r_lease_schema_epoch,
    output wire [31:0] link_r_cfg_active_model_epoch,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_directory_base,
    output wire [MEMORY_ADDR_WIDTH-1:0] link_r_cfg_pool_base,
    output wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_directory_bytes,
    output wire [MEMORY_ADDR_WIDTH:0] link_r_cfg_pool_bytes,
    output wire  link_r_cfg_strip_special,
    output wire  link_r_cfg_replace_invalid,
    output wire [1:0] link_r_cfg_format,
    output wire [28:0] link_r_cfg_protobuf_field,
    output wire [23:0] link_r_carry_in,
    output wire [1:0] link_r_carry_in_count,
    input wire  link_r_result_valid,
    output wire  link_r_result_ready,
    input wire [7:0] link_r_result_stage,
    input wire [7:0] link_r_result_status,
    input wire [7:0] link_r_result_memory_status,
    input wire [23:0] link_r_carry_out,
    input wire [1:0] link_r_carry_out_count,
    input wire [31:0] link_r_result_bytes,
    input wire  link_r_idle,
    input wire  local_tx_accepted
,
    input wire  closed_valid,
    input wire [USER_WIDTH-1:0] closed_user,
    input wire [30:0] closed_stream,
    input wire [31:0] closed_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] closed_address,
    input wire [MEMORY_ADDR_WIDTH-1:0] closed_pool_base,
    input wire [MEMORY_ADDR_WIDTH:0] closed_pool_bytes,
    input wire  service_abort,
    input wire  directory_abort,
    output wire  result_cancelled
,
    input wire  transport_req_valid,
    output wire  transport_req_ready,
    input wire [2:0] transport_req_op,
    input wire  transport_private_abort_proof,
    output wire  transport_rsp_valid,
    input wire  transport_rsp_ready,
    output reg [7:0] transport_rsp_status,
    output reg [7:0] transport_rsp_memory_status,
    output wire [1:0] transport_result_format,
    output wire  transport_header_intent,
    output wire  transport_headers_sent,
    output wire  transport_trailer_intent,
    output wire  transport_trailers_sent,
    output wire  transport_busy,
    output wire  transport_retirement_pending
);
    localparam IDLE=0,CHECK=1,DREQ=2,DWAIT=3,AREAD=4,AWAIT=5,ACHECK=6,
        PREAD=7,PWAIT=8,PCHECK=9,SEND=10,RUN=11,INVALIDATE=12,IWAIT=13,
        WRITE=14,WWAIT=15,COMMIT=16,CWAIT=17,RELEASE=18,RESULT=19,
        T_CHECK=20,T_INVALIDATE=21,T_IWAIT=22,T_WRITE=23,T_WWAIT=24,T_COMMIT=25,T_CWAIT=26,T_RESULT=27;
    localparam [31:0] AUX_MAGIC=32'h48325231,PROGRESS_MAGIC=32'h52535031;
    reg [4:0] state;reg [2:0] word_index;
    reg [2:0] transport_operation;reg private_abort_proof,base_ack_pending;
    wire base_complete=state==RESULT||state>=T_CHECK;
    wire base_ack=result_valid&&result_ready;
    wire transport_authority=directory_result_valid&&directory_status==0&&
        directory_generation==generation&&directory_address==rpc_address&&directory_application==application&&loaded_address_good;
    assign transport_req_ready=!rst&&state==RESULT&&!result_ready&&!base_ack_pending&&result_status==0&&!recovery_required;
    assign transport_rsp_valid=state==T_RESULT;
    assign transport_result_format=format_mode;
    assign transport_header_intent=progress[187];assign transport_headers_sent=progress[188];
    assign transport_trailer_intent=progress[189];assign transport_trailers_sent=progress[190];
    assign transport_busy=state>=T_CHECK;assign transport_retirement_pending=base_ack_pending;
    reg [31:0] token,generation,model_epoch,schema_epoch,ordinal,active_model,active_schema;
    reg [3:0] token_keep;reg eos,protobuf_mode,encoding_mode,directory_held,child_started;
    reg [USER_WIDTH-1:0] owner,application;reg [30:0] stream_id;
    reg [MEMORY_ADDR_WIDTH-1:0] streams,progress_base,work_floor,rpc_address,progress_address,directory_base,pool_base;
    reg [MEMORY_ADDR_WIDTH:0] stream_bytes,progress_bytes,directory_bytes,pool_bytes;
    reg strip_special,replace_invalid;reg [1:0] format_mode;reg [28:0] protobuf_field;
    reg [511:0] auxiliary;reg [255:0] progress;
    reg [23:0] carry;reg [1:0] carry_count;
    wire [63:0] stream_end={1'b0,streams}+{1'b0,stream_bytes};
    wire [63:0] progress_end={1'b0,progress_base}+{1'b0,progress_bytes};
    wire [63:0] directory_end={1'b0,directory_base}+{1'b0,directory_bytes};
    wire [63:0] pool_end={1'b0,pool_base}+{1'b0,pool_bytes};
    wire config_good=stream_bytes>=128&&stream_bytes[6:0]==0&&progress_bytes>=32&&progress_bytes[4:0]==0&&
        {1'b0,progress_bytes}>=(stream_bytes>>2)&&streams>=work_floor&&progress_base>=work_floor&&
        stream_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&progress_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (stream_end<=progress_base||progress_end<=streams)&&directory_end<=work_floor&&pool_end<=work_floor;
    wire loaded_address_good=directory_address>=streams&&{1'b0,directory_address}+128<=stream_end&&((directory_address-streams)&127)==0;
    wire auxiliary_good=auxiliary[31:0]==AUX_MAGIC&&auxiliary[63:32]==generation&&
        auxiliary[95:64]==model_epoch&&auxiliary[127:96]==schema_epoch&&
        auxiliary[447:432]==application&&auxiliary[431:422]==0&&auxiliary[420]==protobuf_mode&&
        auxiliary[421]==encoding_mode&&auxiliary[418]&&auxiliary[511:510]==0&&auxiliary[509:507]<=5&&auxiliary[351:256]==0;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire slot_request=state==AREAD||state==PREAD||state==INVALIDATE||state==WRITE||state==COMMIT||
        state==T_INVALIDATE||state==T_WRITE||state==T_COMMIT;
    wire slot_write=state==INVALIDATE||state==WRITE||state==COMMIT||state==T_INVALIDATE||state==T_WRITE||state==T_COMMIT;
    wire [MEMORY_ADDR_WIDTH-1:0] slot_address=state==AREAD||state==AWAIT?rpc_address+64+word_index*8:
        progress_address+(state==PREAD||state==PWAIT||state==WRITE||state==WWAIT||state==T_WRITE||state==T_WWAIT?word_index*8:0);
    wire [63:0] progress_words[0:3];integer load_index;
    generate for(genvar bank=0;bank<4;bank=bank+1)begin: progress_banks
        assign progress_words[bank]=progress[bank*64+:64];
    end endgenerate
    wire [71:0] write_data=state==INVALIDATE||state==T_INVALIDATE?72'd0:state==COMMIT||state==T_COMMIT?{8'd0,progress[63:0]}:{8'd0,progress_words[word_index[1:0]]};
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) metadata(
        .clk(clk),.rst(rst),.req_valid(slot_request),.req_ready(slot_ready),.req_write(slot_write),.req_addr(slot_address),.req_bytes(4'd8),.req_data(write_data),
        .result_valid(slot_valid),.result_ready(state==AWAIT||state==PWAIT||state==IWAIT||state==WWAIT||state==CWAIT||state==T_IWAIT||state==T_WWAIT||state==T_CWAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),
        .mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(slot_idle));
    wire child_ready,child_valid,child_idle;wire [7:0] child_stage,child_status,child_memory;
    wire [23:0] child_carry;wire [1:0] child_count;wire [31:0] child_bytes;
    reg cancelled;
    // CHECK already validates the captured pool. Register its full-width end
    // there so lookup suppression does not add pool addition ahead of range
    // comparison and the actual directory-arbitration enable. DREQ starts at
    // the same edge as before; a later close still suppresses its real LOAD.
    reg [63:0] checked_stream_end;
    // Only the parent actual window service may supply this acknowledged close.
    // Before DREQ handshakes there is no shared-memory or remote inverse owner.
    wire closed_address_good=closed_address>=streams&&{1'b0,closed_address}+128<=checked_stream_end&&((closed_address-streams)&127)==0;
    wire early_closed=state==DREQ&&closed_valid&&closed_user==owner&&closed_stream==stream_id&&
        closed_generation!=0&&closed_pool_base==streams&&closed_pool_bytes==stream_bytes&&closed_address_good&&
        !directory_held&&!child_started&&slot_idle&&child_idle;
    wire early_abort=state==DREQ&&service_abort&&!directory_held&&!child_started&&slot_idle&&child_idle;
    assign result_cancelled=cancelled;
    assign directory_valid=state==DREQ&&!early_closed&&!early_abort;assign directory_user=owner;assign directory_stream=stream_id;
    assign directory_pool_base=streams;assign directory_pool_bytes=stream_bytes;
    assign directory_result_ready=state==RELEASE&&directory_held;
    assign directory_lease_active=directory_held;
    assign s_axis_tokens_tready=!rst&&state==IDLE&&child_ready;
    assign result_valid=base_complete&&!base_ack_pending;assign result_user=owner;assign result_application=application;
    assign result_stream=stream_id;assign result_generation=generation;assign result_model_epoch=model_epoch;
    assign result_schema_epoch=schema_epoch;assign result_ordinal=ordinal;assign result_eos=eos;
    assign idle=state==IDLE&&slot_idle&&child_idle&&!directory_held;
    assign mem_write[1]=0;assign mem_data[72+:72]=0;
    assign link_r_s_axis_tokens_tdata=token;
assign link_r_s_axis_tokens_tkeep=token_keep;
assign link_r_s_axis_tokens_tvalid=state==SEND;
assign child_ready=link_r_s_axis_tokens_tready;
assign link_r_s_axis_tokens_tlast=eos;
assign link_r_s_axis_tokens_tuser=owner;
assign link_r_lease_valid=directory_held;
assign link_r_lease_user=owner;
assign link_r_lease_application=application;
assign link_r_lease_stream=stream_id;
assign link_r_lease_generation=generation;
assign link_r_lease_model_epoch=model_epoch;
assign link_r_lease_schema_epoch=schema_epoch;
assign link_r_cfg_active_model_epoch=active_model;
assign link_r_cfg_directory_base=directory_base;
assign link_r_cfg_pool_base=pool_base;
assign link_r_cfg_directory_bytes=directory_bytes;
assign link_r_cfg_pool_bytes=pool_bytes;
assign link_r_cfg_strip_special=strip_special;
assign link_r_cfg_replace_invalid=replace_invalid;
assign link_r_cfg_format=format_mode;
assign link_r_cfg_protobuf_field=protobuf_field;
assign link_r_carry_in=carry;
assign link_r_carry_in_count=carry_count;
assign m_axis_tx_tdata=0;
assign m_axis_tx_tkeep=0;
assign m_axis_tx_tvalid=0;
assign m_axis_tx_tlast=0;
assign m_axis_tx_tuser=0;
assign child_valid=link_r_result_valid;
assign link_r_result_ready=state==RESULT&&(base_ack_pending||result_ready)&&child_started;
assign child_stage=link_r_result_stage;
assign child_status=link_r_result_status;
assign child_memory=link_r_result_memory_status;
assign child_carry=link_r_carry_out;
assign child_count=link_r_carry_out_count;
assign child_bytes=link_r_result_bytes;
assign mem_valid[1]=0;
assign mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=0;
assign mem_bytes[4+:4]=0;
assign mem_rsp_ready[1]=0;
assign child_idle=link_r_idle;
    task fail(input [7:0] stage_code,input [7:0] status_code,input [7:0] memory_code);
        begin result_stage<=stage_code;result_status<=status_code;result_memory_status<=memory_code;result_bytes<=0;state<=RELEASE;end
    endtask
    task transport_failure(input [7:0] code,input [7:0] memory_code,input uncertain);
        begin transport_rsp_status<=code;transport_rsp_memory_status<=memory_code;state<=T_RESULT;
            if(uncertain)begin recovery_required<=1;recovery_address<=slot_address;end
        end
    endtask
    task quarantine(input [7:0] status_code);
        begin recovery_required<=1;recovery_address<=slot_address;fail(5,status_code,slot_status);end
    endtask
    initial begin if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>31)$error("Unsupported response-controller widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;transport_operation<=0;private_abort_proof<=0;base_ack_pending<=0;transport_rsp_status<=0;transport_rsp_memory_status<=0;cancelled<=0;checked_stream_end<=0;word_index<=0;token<=0;token_keep<=0;eos<=0;generation<=0;model_epoch<=0;schema_epoch<=0;ordinal<=0;active_model<=0;active_schema<=0;
            protobuf_mode<=0;encoding_mode<=0;directory_held<=0;child_started<=0;owner<=0;application<=0;stream_id<=0;
            streams<=0;progress_base<=0;work_floor<=0;rpc_address<=0;progress_address<=0;directory_base<=0;pool_base<=0;
            stream_bytes<=0;progress_bytes<=0;directory_bytes<=0;pool_bytes<=0;strip_special<=0;replace_invalid<=0;format_mode<=0;protobuf_field<=0;
            auxiliary<=0;progress<=0;carry<=0;carry_count<=0;result_stage<=0;result_status<=0;result_memory_status<=0;result_bytes<=0;result_tx_emitted<=0;recovery_required<=0;recovery_address<=0;
        end else begin
        if(local_tx_accepted)result_tx_emitted<=1;
        if(base_ack&&state!=RESULT)base_ack_pending<=1;
        case(state)
            IDLE:if(s_axis_tokens_tvalid&&s_axis_tokens_tready)begin
                cancelled<=0;token<=s_axis_tokens_tdata;token_keep<=s_axis_tokens_tkeep;eos<=s_axis_tokens_tlast;owner<=s_axis_tokens_tuser;
                stream_id<=s_stream;generation<=s_generation;model_epoch<=s_model_epoch;schema_epoch<=s_schema_epoch;ordinal<=s_ordinal;
                active_model<=cfg_model_epoch;active_schema<=cfg_schema_epoch;streams<=cfg_stream_base;stream_bytes<=cfg_stream_bytes;
                progress_base<=cfg_progress_base;progress_bytes<=cfg_progress_bytes;work_floor<=cfg_work_floor;
                directory_base<=cfg_directory_base;directory_bytes<=cfg_directory_bytes;pool_base<=cfg_pool_base;pool_bytes<=cfg_pool_bytes;
                strip_special<=cfg_strip_special;replace_invalid<=cfg_replace_invalid;format_mode<=cfg_format;protobuf_field<=cfg_protobuf_field;
                application<=0;carry<=0;carry_count<=0;auxiliary<=0;progress<=0;word_index<=0;child_started<=0;
                result_stage<=0;result_status<=0;result_memory_status<=0;result_bytes<=0;result_tx_emitted<=0;state<=CHECK;
            end
            CHECK:if(recovery_required)fail(1,3,0);
                else if(!config_good)fail(1,1,0);
                else if(stream_id==0||!stream_id[0]||generation==0||(token_keep!=15&&(token_keep!=0||!eos)))fail(1,2,0);
                else if(model_epoch!=active_model||schema_epoch!=active_schema)fail(3,3,0);
                else begin checked_stream_end<=stream_end;state<=DREQ;end
            DREQ:if(early_abort)fail(directory_abort?8'd2:8'd17,directory_abort?8'd6:8'd3,0);
            else if(early_closed)begin
                rpc_address<=closed_address;cancelled<=closed_generation==generation;
                // Preserve the submitted identity. A stale generation is a
                // terminal mismatch, not authority over the newer allocation.
                fail(17,closed_generation==generation?8'd1:8'd2,0);
            end else if(directory_ready)state<=DWAIT;
            DWAIT:if(directory_result_valid)begin
                directory_held<=1;application<=directory_application;protobuf_mode<=directory_protobuf;encoding_mode<=directory_unsupported_encoding;
                rpc_address<=directory_address;progress_address<=progress_base+((directory_address-streams)>>2);
                if(directory_status!=0)fail(2,directory_status,directory_memory_status);
                else if(directory_generation!=generation)fail(3,1,0);
                else if(!loaded_address_good)fail(3,2,0);
                else if(directory_unsupported_encoding)fail(3,4,0);
                else begin word_index<=0;state<=AREAD;end
            end
            AREAD:if(slot_ready)state<=AWAIT;
            AWAIT:if(slot_valid)begin
                if(slot_status!=0)quarantine(1);
                else begin
                    for(load_index=0;load_index<8;load_index=load_index+1)
                        if(word_index==load_index)auxiliary[load_index*64+:64]<=slot_data[63:0];
                    if(word_index==7)state<=ACHECK;else begin word_index<=word_index+1'b1;state<=AREAD;end
                end
            end
            ACHECK:if(!auxiliary_good)fail(3,2,0);else begin word_index<=0;state<=PREAD;end
            PREAD:if(slot_ready)state<=PWAIT;
            PWAIT:if(slot_valid)begin
                if(slot_status!=0)quarantine(2);
                else begin
                    for(load_index=0;load_index<4;load_index=load_index+1)
                        if(word_index==load_index)progress[load_index*64+:64]<=slot_data[63:0];
                    if(word_index==3)state<=PCHECK;else begin word_index<=word_index+1'b1;state<=PREAD;end
                end
            end
            PCHECK:if(progress[63:0]==0||progress[31:0]==PROGRESS_MAGIC&&progress[63:32]!=generation)begin
                if(ordinal!=0)fail(4,3,0);
                else if(format_mode==1)fail(3,6,0);else if((format_mode==2)!=protobuf_mode)fail(3,5,0);
                else begin
                    progress<={31'd0,strip_special,replace_invalid,format_mode,protobuf_field,64'd0,schema_epoch,model_epoch,generation,PROGRESS_MAGIC};
                    state<=SEND;
                end
            end else if(progress[31:0]!=PROGRESS_MAGIC||progress[191]!=0||progress[255:225]!=0)fail(4,1,0);
            else if(progress[187]||progress[189])begin recovery_required<=1;recovery_address<=progress_address;fail(4,6,0);end
            else if(!progress[188]||progress[190]&&!progress[186])fail(4,7,0);
            else if(progress[95:64]!=model_epoch||progress[127:96]!=schema_epoch)fail(4,2,0);
            else if(progress[186])fail(4,4,0);
            else if(progress[159:128]!=ordinal)fail(4,3,0);
            else if(ordinal==32'hffffffff)fail(4,5,0);
            else if(progress[222:221]==1)fail(3,6,0);else if((progress[222:221]==2)!=protobuf_mode)fail(3,5,0);
            else begin
                carry<=progress[183:160];carry_count<=progress[185:184];protobuf_field<=progress[220:192];
                format_mode<=progress[222:221];replace_invalid<=progress[223];strip_special<=progress[224];state<=SEND;
            end
            SEND:if(child_ready)begin child_started<=1;state<=RUN;end
            RUN:if(child_valid)begin
                result_stage<=child_stage==0?8'd0:child_stage+8'd5;result_status<=child_status;result_memory_status<=child_memory;
                if(child_status!=0)begin result_bytes<=0;state<=RELEASE;end
                else begin
                    result_bytes<=child_bytes;progress[186:128]<={eos,child_count,child_carry,ordinal+32'd1};
                    if(ordinal==0)progress[187]<=1;
                    state<=INVALIDATE;
                end
            end
            INVALIDATE:if(slot_ready)state<=IWAIT;
            IWAIT:if(slot_valid)begin if(slot_status!=0)quarantine(3);else begin word_index<=1;state<=WRITE;end end
            WRITE:if(slot_ready)state<=WWAIT;
            WWAIT:if(slot_valid)begin
                if(slot_status!=0)quarantine(3);
                else if(word_index==3)state<=COMMIT;
                else begin word_index<=word_index+1'b1;state<=WRITE;end
            end
            COMMIT:if(slot_ready)state<=CWAIT;
            CWAIT:if(slot_valid)begin if(slot_status!=0)quarantine(3);else state<=RELEASE;end
            RELEASE:if(!directory_held||directory_result_valid)begin directory_held<=0;state<=RESULT;end
            RESULT:if(base_ack_pending||base_ack)begin base_ack_pending<=0;state<=IDLE;end
            else if(transport_req_valid&&transport_req_ready)begin
                transport_operation<=transport_req_op;private_abort_proof<=transport_private_abort_proof;
                transport_rsp_status<=0;transport_rsp_memory_status<=0;state<=T_CHECK;
            end
            T_CHECK:if(!transport_authority)transport_failure(2,0,0);
                else case(transport_operation)
                    // Caller has an actual successful initial-header wire result.
                    0:if(!progress[187]||progress[188]||progress[189]||progress[190])transport_failure(1,0,0);
                        else begin progress[187]<=0;progress[188]<=1;state<=T_INVALIDATE;end
                    // Caller has witnessed the actual final DATA TLAST.
                    1:if(!progress[186]||!progress[188]||progress[187]||progress[189]||progress[190])transport_failure(1,0,0);
                        else begin progress[189]<=1;state<=T_INVALIDATE;end
                    // Caller has the actual successful trailing HEADERS result.
                    2:if(!progress[189]||!progress[188]||progress[187]||progress[190])transport_failure(1,0,0);
                        else begin progress[189]<=0;progress[190]<=1;state<=T_INVALIDATE;end
                    // Only an actual formatter abort result can prove that the
                    // initial block was private and no bytes reached the wire.
                    3:if(!private_abort_proof||!progress[187]||progress[188]||progress[189]||progress[190])transport_failure(1,0,0);
                        else begin progress[187]<=0;state<=T_INVALIDATE;end
                    4:if(!private_abort_proof||!progress[189]||!progress[188]||progress[187]||progress[190])transport_failure(1,0,0);
                        else begin progress[189]<=0;state<=T_INVALIDATE;end
                    default:transport_failure(1,0,0);
                endcase
            T_INVALIDATE:if(slot_ready)state<=T_IWAIT;
            T_IWAIT:if(slot_valid)begin
                if(slot_status!=0)transport_failure(3,slot_status,1);else begin word_index<=1;state<=T_WRITE;end
            end
            T_WRITE:if(slot_ready)state<=T_WWAIT;
            T_WWAIT:if(slot_valid)begin
                if(slot_status!=0)transport_failure(3,slot_status,1);
                else if(word_index==3)state<=T_COMMIT;else begin word_index<=word_index+1'b1;state<=T_WRITE;end
            end
            T_COMMIT:if(slot_ready)state<=T_CWAIT;
            T_CWAIT:if(slot_valid)begin if(slot_status!=0)transport_failure(3,slot_status,1);else state<=T_RESULT;end
            T_RESULT:if(transport_rsp_ready)state<=RESULT;
            default:state<=IDLE;
        endcase
        end
    end
endmodule
`default_nettype wire
