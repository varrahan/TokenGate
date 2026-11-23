`timescale 1ns/1ps
`default_nettype none
// Phased HEADERS admission. BEGIN restores live RPC identity before HPACK
// validation; a successful candidate allocates and OPENs the RPC before DATA.
// The parent still owns packet commit, flow control and whole-RPC/GPU leases.
module http2_rpc_admission #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire reset_valid,output wire reset_ready,input wire [USER_WIDTH-1:0] reset_user,input wire maintenance_grant,
    input wire begin_valid,output wire begin_ready,input wire [USER_WIDTH-1:0] begin_user,input wire [30:0] begin_stream,input wire begin_end_stream,
    input wire admit_new,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_stream_base,cfg_payload_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_stream_bytes,cfg_payload_bytes,cfg_payload_slot_bytes,
    input wire [31:0] cfg_model_epoch,cfg_schema_epoch,
    output wire context_valid,input wire context_ready,output wire [USER_WIDTH-1:0] context_user,
    output wire [30:0] context_stream,output wire context_trailers,context_end_stream,
    output reg [MEMORY_ADDR_WIDTH-1:0] context_scratch_base,output reg [MEMORY_ADDR_WIDTH:0] context_scratch_bytes,
    input wire candidate_valid,output wire candidate_ready,input wire [2:0] candidate_status,input wire [9:0] candidate_http_status,
    input wire [USER_WIDTH-1:0] candidate_user,input wire [30:0] candidate_stream,input wire candidate_end_stream,
    input wire candidate_admissible,input wire [15:0] candidate_application,input wire [1:0] candidate_format,
    input wire candidate_identity_encoding,input wire [31:0] candidate_message_limit,candidate_model_epoch,candidate_schema_epoch,candidate_route_entry,
    input wire candidate_length_valid,input wire [63:0] candidate_content_length,
    input wire candidate_timeout_valid,input wire [26:0] candidate_timeout_value,input wire [2:0] candidate_timeout_unit,
    output wire result_valid,input wire result_ready,output wire result_is_reset,output wire result_trailers,result_end_stream,
    output reg [3:0] result_status,output reg [7:0] result_detail,result_memory_status,result_control_status,result_cleanup_status,
    output reg result_connection_error,output reg [31:0] result_http2_error,output reg [9:0] result_http_status,output reg [7:0] result_grpc_status,
    output wire [USER_WIDTH-1:0] result_user,output wire [30:0] result_stream,
    output reg [15:0] result_application,output reg [31:0] result_generation,result_model_epoch,result_schema_epoch,
    output reg [MEMORY_ADDR_WIDTH-1:0] result_address,result_buffer_base,output reg [MEMORY_ADDR_WIDTH:0] result_buffer_bytes,
    output reg result_protobuf,result_unsupported_encoding,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,output reg [USER_WIDTH-1:0] recovery_user,
    output wire control_valid,input wire control_ready,output reg [2:0] control_op,
    output wire [USER_WIDTH-1:0] control_user,output wire [15:0] control_application,output wire [30:0] control_stream,
    output wire [31:0] control_generation,output wire [MEMORY_ADDR_WIDTH-1:0] control_address,control_buffer_base,
    output wire [MEMORY_ADDR_WIDTH:0] control_buffer_bytes,output wire [31:0] control_message_limit,
    output wire control_protobuf,control_unsupported_encoding,control_maintenance,
    input wire control_result_valid,output wire control_result_ready,input wire [7:0] control_status,control_memory_status,
    input wire [MEMORY_ADDR_WIDTH-1:0] control_result_address,control_result_buffer_base,
    input wire [MEMORY_ADDR_WIDTH:0] control_result_buffer_bytes,input wire [15:0] control_result_application,
    input wire [31:0] control_result_generation,control_result_message_limit,input wire control_result_protobuf,control_result_unsupported_encoding,
    input wire [255:0] control_result_state,
    output wire mem_valid,input wire mem_ready,output wire mem_write,output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,output wire [71:0] mem_data,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,output wire idle
);
    localparam IDLE=0,CHECK=1,HW_REQ=2,HW_WAIT=3,CONTROL_REQ=4,CONTROL_WAIT=5,HW_WRITE=6,HW_ACK=7,
        CONTEXT=8,CANDIDATE=9,FREE_REQ=10,FREE_WAIT=11,AUX_REQ=12,AUX_WAIT=13,AUX_CHECK=14,AUX_WRITE=15,AUX_ACK=16,RESULT=17,
        SCRATCH_REQ=18,SCRATCH_WAIT=19,SCRATCH_CHECK=20;
    localparam ACT_LOOKUP=0,ACT_OPEN=1,ACT_CLOSE=2,ACT_RESET=3;
    localparam [31:0] HW_MAGIC=32'h48325731,AUX_MAGIC=32'h48325231,RPC_MAGIC=32'h47525331;
    reg [4:0] state;reg [1:0] action;reg resetting,reset_grant,allow_new,end_stream,known,trailer,remote_closed,loaded_scratch_valid;
    reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id,last_stream;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,streams,payload,work_floor,hw_address,scan_address,scan_buffer,rpc_address,rpc_buffer;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,stream_bytes,payload_bytes,slot_bytes,rpc_capacity;
    reg [31:0] active_model,active_schema,next_generation,rpc_generation,rpc_limit;
    reg [15:0] application;reg protobuf_mode,unsupported_encoding;
    reg [511:0] auxiliary;reg [2:0] word_index;
    wire [63:0] contexts_end={1'b0,contexts}+{1'b0,context_bytes};
    wire [63:0] streams_end={1'b0,streams}+{1'b0,stream_bytes};
    wire [63:0] payload_end={1'b0,payload}+{1'b0,payload_bytes};
    wire [63:0] record_end={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+256;
    wire config_good=context_bytes>=256&&context_bytes[7:0]==0&&stream_bytes>=128&&stream_bytes[6:0]==0&&slot_bytes!=0&&
        contexts>=work_floor&&streams>=work_floor&&payload>=work_floor&&record_end<=contexts_end&&
        contexts_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&streams_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&payload_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (contexts_end<=streams||streams_end<=contexts)&&(contexts_end<=payload||payload_end<=contexts)&&(streams_end<=payload||payload_end<=streams);
    wire slot_fits=scan_buffer>=payload&&{1'b0,scan_buffer}+{1'b0,slot_bytes}<=payload_end;
    wire loaded_address_good=control_result_address>=streams&&{1'b0,control_result_address}+128<=streams_end&&((control_result_address-streams)&127)==0;
    wire loaded_buffer_good=control_result_buffer_base>=payload&&control_result_buffer_bytes==slot_bytes&&
        {1'b0,control_result_buffer_base}+{1'b0,control_result_buffer_bytes}<=payload_end;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire [63:0] scratch_end={32'd0,slot_data[31:0]}+{32'd0,slot_data[63:32]};
    wire scratch_good=slot_data[63:32]!=0&&slot_data[31:0]>=work_floor&&scratch_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (scratch_end<=contexts||slot_data[31:0]>=contexts_end)&&(scratch_end<=streams||slot_data[31:0]>=streams_end)&&
        (scratch_end<=payload||slot_data[31:0]>=payload_end);
    wire request=state==SCRATCH_REQ||state==HW_REQ||state==HW_WRITE||state==FREE_REQ&&slot_fits||state==AUX_REQ||state==AUX_WRITE;
    wire writing=state==HW_WRITE||state==AUX_WRITE;
    wire [MEMORY_ADDR_WIDTH-1:0] request_address=state==SCRATCH_REQ?hw_address-80:(state==HW_REQ||state==HW_WRITE)?hw_address:
        state==FREE_REQ?scan_address:rpc_address+64+{{(MEMORY_ADDR_WIDTH-6){1'b0}},word_index,3'd0};
    wire [63:0] auxiliary_word;
    integer auxiliary_load_index;
    wire [63:0] auxiliary_words[0:7];
    generate for(genvar select_bank=0;select_bank<8;select_bank=select_bank+1)begin: word_select_banks
        assign auxiliary_words[select_bank]=auxiliary[select_bank*64+:64];
    end endgenerate
    assign auxiliary_word=auxiliary_words[word_index];
    wire [71:0] request_data=state==HW_WRITE?{8'd0,1'b0,last_stream,HW_MAGIC}:{8'd0,auxiliary_word};
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(request),.req_ready(slot_ready),.req_write(writing),.req_addr(request_address),.req_bytes(4'd8),.req_data(request_data),
        .result_valid(slot_valid),.result_ready(state==SCRATCH_WAIT||state==HW_WAIT||state==HW_ACK||state==FREE_WAIT||state==AUX_WAIT||state==AUX_ACK),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign reset_ready=!rst&&state==IDLE;assign begin_ready=!rst&&state==IDLE&&!reset_valid;
    assign context_valid=state==CONTEXT;assign context_user=owner;assign context_stream=stream_id;assign context_trailers=trailer;assign context_end_stream=end_stream;
    assign candidate_ready=state==CANDIDATE;
    assign result_valid=state==RESULT;assign result_is_reset=resetting;assign result_user=owner;assign result_stream=stream_id;
    assign result_trailers=trailer;assign result_end_stream=end_stream;
    assign control_valid=!rst&&state==CONTROL_REQ;assign control_result_ready=state==CONTROL_WAIT;
    assign control_user=owner;assign control_application=application;assign control_stream=resetting?31'd0:stream_id;
    assign control_generation=rpc_generation;assign control_address=rpc_address;assign control_buffer_base=rpc_buffer;assign control_buffer_bytes=rpc_capacity;
    assign control_message_limit=rpc_limit;assign control_protobuf=protobuf_mode;assign control_unsupported_encoding=unsupported_encoding;assign control_maintenance=1'b0;
    assign idle=state==IDLE&&slot_idle;
    task clear_authority;
        begin result_application<=0;result_generation<=0;result_model_epoch<=0;result_schema_epoch<=0;result_address<=0;result_buffer_base<=0;
            result_buffer_bytes<=0;result_protobuf<=0;result_unsupported_encoding<=0;end
    endtask
    task error_result;
        input [3:0] status;input [7:0] detail;input conn;input [31:0] h2_error;
        begin result_status<=status;result_detail<=detail;result_connection_error<=conn;result_http2_error<=h2_error;clear_authority;end
    endtask
    task quarantine;
        input [MEMORY_ADDR_WIDTH-1:0] address;input [7:0] detail;input [7:0] memory_status;
        begin recovery_required<=1;recovery_address<=address;recovery_user<=owner;result_memory_status<=memory_status;error_result(5,detail,1,2);end
    endtask
    task publish;
        begin result_application<=application;result_generation<=rpc_generation;result_model_epoch<=auxiliary[95:64];result_schema_epoch<=auxiliary[127:96];
            result_address<=rpc_address;result_buffer_base<=rpc_buffer;result_buffer_bytes<=rpc_capacity;result_protobuf<=protobuf_mode;result_unsupported_encoding<=unsupported_encoding;state<=RESULT;end
    endtask
    task close_then_result;
        begin if(known)begin action<=ACT_CLOSE;control_op<=3;state<=CONTROL_REQ;end else state<=RESULT;end
    endtask
    initial begin if(MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>31||USER_WIDTH<1||USER_WIDTH>16)$error("Unsupported admission widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;action<=0;resetting<=0;reset_grant<=0;allow_new<=0;end_stream<=0;known<=0;trailer<=0;remote_closed<=0;loaded_scratch_valid<=0;owner<=0;stream_id<=0;last_stream<=0;
            contexts<=0;streams<=0;payload<=0;work_floor<=0;hw_address<=0;scan_address<=0;scan_buffer<=0;rpc_address<=0;rpc_buffer<=0;
            context_bytes<=0;stream_bytes<=0;payload_bytes<=0;slot_bytes<=0;rpc_capacity<=0;active_model<=0;active_schema<=0;next_generation<=1;
            rpc_generation<=0;rpc_limit<=0;application<=0;protobuf_mode<=0;unsupported_encoding<=0;auxiliary<=0;word_index<=0;control_op<=0;
            result_status<=0;result_detail<=0;result_memory_status<=0;result_control_status<=0;result_cleanup_status<=0;
            context_scratch_base<=0;context_scratch_bytes<=0;
            result_connection_error<=0;result_http2_error<=0;result_http_status<=0;result_grpc_status<=0;clear_authority;
            recovery_required<=0;recovery_address<=0;recovery_user<=0;
        end else case(state)
            IDLE:if(reset_valid&&reset_ready||begin_valid&&begin_ready)begin
                resetting<=reset_valid;reset_grant<=maintenance_grant;owner<=reset_valid?reset_user:begin_user;stream_id<=reset_valid?31'd0:begin_stream;
                end_stream<=!reset_valid&&begin_end_stream;allow_new<=admit_new;known<=0;trailer<=0;remote_closed<=0;
                contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;streams<=cfg_stream_base;stream_bytes<=cfg_stream_bytes;
                payload<=cfg_payload_base;payload_bytes<=cfg_payload_bytes;slot_bytes<=cfg_payload_slot_bytes;work_floor<=cfg_work_floor;
                active_model<=cfg_model_epoch;active_schema<=cfg_schema_epoch;
                hw_address<=cfg_context_base+((reset_valid?reset_user:begin_user)<<8)+160;
                result_status<=0;result_detail<=0;result_memory_status<=0;result_control_status<=0;result_cleanup_status<=0;
                result_connection_error<=0;result_http2_error<=0;result_http_status<=0;result_grpc_status<=0;clear_authority;state<=CHECK;
                context_scratch_base<=0;context_scratch_bytes<=0;
            end
            CHECK:if(!config_good)begin error_result(5,1,1,2);state<=resetting?RESULT:CONTEXT;end
                else if(recovery_required&&(!resetting||owner!=recovery_user))begin error_result(5,2,1,2);state<=resetting?RESULT:CONTEXT;end
                else if(resetting)begin
                    if(!reset_grant)begin error_result(5,3,1,2);state<=RESULT;end
                    else begin action<=ACT_RESET;control_op<=6;state<=CONTROL_REQ;end
                end else if(stream_id==0||!stream_id[0])begin error_result(1,1,1,1);state<=CONTEXT;end
                else state<=SCRATCH_REQ;
            SCRATCH_REQ:if(slot_ready)state<=SCRATCH_WAIT;
            SCRATCH_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin quarantine(hw_address-80,20,slot_status);state<=CONTEXT;end
                // Do not feed the scratch sum/range comparisons directly into
                // the wide result-clear enable. Keep the checked decision
                // registered before changing any admission authority.
                else begin
                    loaded_scratch_valid<=scratch_good;context_scratch_base<=slot_data[MEMORY_ADDR_WIDTH-1:0];
                    context_scratch_bytes<=slot_data[32+:MEMORY_ADDR_WIDTH+1];state<=SCRATCH_CHECK;
                end
            end
            SCRATCH_CHECK:if(!loaded_scratch_valid)begin context_scratch_base<=0;context_scratch_bytes<=0;quarantine(hw_address-80,21,0);state<=CONTEXT;end
                else state<=HW_REQ;
            HW_REQ:if(slot_ready)state<=HW_WAIT;
            HW_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin quarantine(hw_address,4,slot_status);state<=CONTEXT;end
                else if(slot_data[31:0]!=HW_MAGIC||slot_data[63])begin quarantine(hw_address,5,0);state<=CONTEXT;end
                else begin last_stream<=slot_data[62:32];action<=ACT_LOOKUP;control_op<=1;state<=CONTROL_REQ;end
            end
            CONTROL_REQ:if(control_ready)state<=CONTROL_WAIT;
            CONTROL_WAIT:if(control_result_valid)begin
                if(action==ACT_RESET)begin
                    if(control_status==3)begin last_stream<=0;state<=HW_WRITE;end
                    else begin result_control_status<=control_status;error_result(5,6,1,2);result_memory_status<=control_memory_status;state<=RESULT;end
                end else if(action==ACT_LOOKUP)begin
                    if(control_status==3)begin
                        if(stream_id<=last_stream)begin error_result(2,1,0,5);state<=CONTEXT;end
                        else begin last_stream<=stream_id;state<=HW_WRITE;end
                    end else if(control_status!=0)begin
                        result_control_status<=control_status;result_memory_status<=control_memory_status;error_result(5,7,1,2);state<=CONTEXT;
                    end else begin
                        known<=1;trailer<=1;remote_closed<=control_result_state[163];rpc_address<=control_result_address;rpc_buffer<=control_result_buffer_base;
                        rpc_capacity<=control_result_buffer_bytes;rpc_generation<=control_result_generation;application<=control_result_application;
                        protobuf_mode<=control_result_protobuf;unsupported_encoding<=control_result_unsupported_encoding;rpc_limit<=control_result_message_limit;
                        if(!loaded_address_good||!loaded_buffer_good||stream_id>last_stream)begin error_result(5,8,1,2);state<=CONTEXT;end
                        else begin word_index<=0;state<=AUX_REQ;end
                    end
                end else if(action==ACT_OPEN)begin
                    if(control_status!=0)begin result_control_status<=control_status;result_memory_status<=control_memory_status;error_result(5,9,1,2);state<=RESULT;end
                    else begin
                        known<=1;rpc_address<=control_result_address;
                        if(control_result_address!=scan_address||control_result_generation!=rpc_generation||control_result_application!=application||
                            control_result_buffer_base!=rpc_buffer||control_result_buffer_bytes!=rpc_capacity||control_result_protobuf!=protobuf_mode||
                            control_result_unsupported_encoding!=unsupported_encoding||control_result_message_limit!=rpc_limit)begin
                            rpc_generation<=control_result_generation;error_result(5,10,1,2);action<=ACT_CLOSE;control_op<=3;state<=CONTROL_REQ;
                        end else begin word_index<=0;state<=AUX_WRITE;end
                    end
                end else begin
                    result_cleanup_status<=control_status;
                    if(control_status!=0&&control_status!=3)begin result_control_status<=control_status;result_memory_status<=control_memory_status;error_result(5,11,1,2);end
                    state<=RESULT;
                end
            end
            HW_WRITE:if(slot_ready)state<=HW_ACK;
            HW_ACK:if(slot_valid)begin
                if(slot_status!=0)begin quarantine(hw_address,12,slot_status);state<=resetting?RESULT:CONTEXT;end
                else if(resetting)begin recovery_required<=0;recovery_address<=0;recovery_user<=0;state<=RESULT;end
                else state<=CONTEXT;
            end
            CONTEXT:if(context_ready)state<=CANDIDATE;
            CANDIDATE:if(candidate_valid)begin
                if(candidate_user!=owner||candidate_stream!=stream_id||candidate_end_stream!=end_stream)begin error_result(5,18,1,2);close_then_result;end
                else if(candidate_status==4)begin error_result(6,0,1,0);close_then_result;end
                else if(result_status!=0)close_then_result;
                else if(candidate_status!=0)begin
                    error_result(3,{5'd0,candidate_status},candidate_status==3,candidate_status==3?32'd2:candidate_status==1?32'd1:32'd0);
                    result_http_status<=candidate_http_status;close_then_result;
                end else if(trailer)begin
                    if(remote_closed||auxiliary[419])begin error_result(2,2,0,5);close_then_result;end
                    else if(!end_stream)begin error_result(1,2,0,1);close_then_result;end
                    else begin auxiliary[419]<=1;word_index<=0;state<=AUX_WRITE;end
                end else if(!candidate_admissible)begin error_result(3,4,0,0);result_http_status<=200;result_grpc_status<=12;state<=RESULT;end
                else if(candidate_format>1||candidate_message_limit==0||candidate_timeout_valid&&
                    (candidate_timeout_value==0||candidate_timeout_value>99999999||candidate_timeout_unit>5)||candidate_application>>USER_WIDTH!=0)begin error_result(5,19,1,2);state<=RESULT;end
                else if(!allow_new)begin error_result(4,1,0,7);state<=RESULT;end
                else if(candidate_model_epoch!=active_model||candidate_schema_epoch!=active_schema)begin error_result(4,2,0,7);state<=RESULT;end
                else if(next_generation==0)begin error_result(4,3,0,7);state<=RESULT;end
                else begin
                    application<=candidate_application;protobuf_mode<=candidate_format==0;unsupported_encoding<=!candidate_identity_encoding;
                    rpc_limit<=candidate_message_limit;rpc_capacity<=slot_bytes;rpc_generation<=next_generation;next_generation<=next_generation+1'b1;
                    auxiliary<=0;auxiliary[31:0]<=AUX_MAGIC;auxiliary[63:32]<=next_generation;
                    auxiliary[95:64]<=active_model;auxiliary[127:96]<=active_schema;auxiliary[191:128]<=candidate_content_length;
                    auxiliary[383:352]<=32'd65535;auxiliary[415:384]<=32'd65535;
                    auxiliary[447:416]<={candidate_application,10'd0,!candidate_identity_encoding,candidate_format==0,end_stream,1'b1,candidate_timeout_valid,candidate_length_valid};
                    auxiliary[479:448]<=candidate_route_entry;auxiliary[511:480]<=candidate_timeout_valid?{2'd0,candidate_timeout_unit,candidate_timeout_value}:32'd0;
                    scan_address<=streams;scan_buffer<=payload;state<=FREE_REQ;
                end
            end
            FREE_REQ:if(!slot_fits)begin error_result(4,4,0,7);state<=RESULT;end else if(slot_ready)state<=FREE_WAIT;
            FREE_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin quarantine(scan_address,13,slot_status);state<=RESULT;end
                else if(slot_data[63:0]==0)begin
                    if(!slot_fits)begin error_result(4,4,0,7);state<=RESULT;end
                    else begin rpc_address<=scan_address;rpc_buffer<=scan_buffer;action<=ACT_OPEN;control_op<=0;state<=CONTROL_REQ;end
                end else if(slot_data[31:0]!=RPC_MAGIC||!slot_data[32]||slot_data[63:35]!=0)begin quarantine(scan_address,14,0);state<=RESULT;end
                else if({1'b0,scan_address}+256>streams_end||{1'b0,scan_buffer}+64'd2*slot_bytes>payload_end)begin error_result(4,4,0,7);state<=RESULT;end
                else begin scan_address<=scan_address+128;scan_buffer<=scan_buffer+slot_bytes;state<=FREE_REQ;end
            end
            AUX_REQ:if(slot_ready)state<=AUX_WAIT;
            AUX_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin quarantine(rpc_address+64+word_index*8,15,slot_status);state<=CONTEXT;end
                else begin
                    for(auxiliary_load_index=0;auxiliary_load_index<8;auxiliary_load_index=auxiliary_load_index+1)
                        if(word_index==auxiliary_load_index)auxiliary[auxiliary_load_index*64+:64]<=slot_data[63:0];
                    word_index<=word_index+1'b1;state<=word_index==7?AUX_CHECK:AUX_REQ;
                end
            end
            AUX_CHECK:begin
                if(auxiliary[31:0]!=AUX_MAGIC||auxiliary[63:32]!=rpc_generation||auxiliary[95:64]!=active_model||auxiliary[127:96]!=active_schema||
                    auxiliary[447:432]!=application||auxiliary[431:422]!=0||auxiliary[420]!=protobuf_mode||auxiliary[421]!=unsupported_encoding||
                    !auxiliary[418]||auxiliary[511:510]!=0||auxiliary[509:507]>5||auxiliary[351:256]!=0)begin
                    quarantine(rpc_address+64,16,0);state<=CONTEXT;
                end else state<=CONTEXT;
            end
            AUX_WRITE:if(slot_ready)state<=AUX_ACK;
            AUX_ACK:if(slot_valid)begin
                if(slot_status!=0)begin quarantine(rpc_address+64+word_index*8,17,slot_status);action<=ACT_CLOSE;control_op<=3;state<=CONTROL_REQ;end
                else if(word_index==7)publish;
                else begin word_index<=word_index+1'b1;state<=AUX_WRITE;end
            end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
