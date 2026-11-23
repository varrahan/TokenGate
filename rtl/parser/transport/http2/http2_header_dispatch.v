`timescale 1ns/1ps
`default_nettype none
// Reassemble unpadded HEADERS/CONTINUATION bytes in external memory and run
// HPACK in connection order. Scratch header pointers and block completion are
// leased until acknowledged. Semantic DATA/control events pass downstream.
module http2_header_dispatch #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16,parameter integer BLOCK_START_PORT=0
)(
    input wire clk,input wire rst,input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,input wire [767:0] cfg_state,
    input wire s_valid,output wire s_ready,input wire [3:0] s_kind,input wire [7:0] s_data,input wire [31:0] s_arg0,s_arg1,
    input wire [23:0] s_length,input wire [7:0] s_type,s_flags,input wire [30:0] s_stream,input wire [USER_WIDTH-1:0] s_user,
    output reg m_valid,input wire m_ready,output reg [3:0] m_kind,output reg [7:0] m_data,output reg [31:0] m_arg0,m_arg1,
    output reg [23:0] m_length,output reg [7:0] m_type,m_flags,output reg [30:0] m_stream,output wire [USER_WIDTH-1:0] m_user,
    output wire header_valid,input wire header_ready,output wire [MEMORY_ADDR_WIDTH-1:0] header_name_base,header_value_base,
    output wire [31:0] header_name_bytes,header_value_bytes,output wire [1:0] header_representation,output wire [USER_WIDTH-1:0] header_user,
    output wire block_start_valid,input wire block_start_ready,output wire [30:0] block_start_stream,block_start_promised_stream,
    output wire [7:0] block_start_type,block_start_flags,output wire [USER_WIDTH-1:0] block_start_user,
    output wire block_valid,input wire block_ready,output wire [30:0] block_stream,block_promised_stream,output wire [7:0] block_type,block_flags,
    output reg [31:0] block_headers,block_list_bytes,output wire [USER_WIDTH-1:0] block_user,
    input wire finish_valid,output wire result_valid,input wire result_ready,output wire [767:0] result_state,
    output reg result_failed,output reg [31:0] result_error,output reg [7:0] result_detail,
    output wire [2:0] mem_valid,input wire [2:0] mem_ready,output wire [2:0] mem_write,
    output wire [3*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [11:0] mem_bytes,output wire [215:0] mem_data,
    input wire [2:0] mem_rsp_valid,output wire [2:0] mem_rsp_ready,input wire [215:0] mem_rsp_data,input wire [23:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,CHECK=1,RUN=2,WRITE_REQ=3,WRITE_WAIT=4,HP_START=5,FEED_REQ=6,FEED_WAIT=7,FEED_SEND=8,HP_WAIT=9,BLOCK_DONE=10,DRAIN=11,FINISH=12,RESULT=13;
    reg [3:0] state;
    reg [767:0] saved;
    reg [USER_WIDTH-1:0] context_id;
    reg [7:0] byte_value;
    reg [31:0] feed_position;
    reg discard,header_exposed,hpack_started,block_started;
    wire [31:0] buffer_base=saved[0+:32],buffer_bytes=saved[32+:32],table_base=saved[64+:32],table_bytes=saved[96+:32];
    wire [31:0] scratch_base=saved[128+:32],scratch_bytes=saved[160+:32],maximum=saved[192+:32],allowed=saved[224+:32];
    wire [31:0] used=saved[256+:32],entries=saved[288+:32],list_limit=saved[320+:32],required_maximum=saved[352+:32];
    wire required_update=saved[384];
    wire [31:0] buffered=saved[416+:32],fragment_bytes=saved[576+:32],fragment_received=saved[608+:32];
    wire block_active=saved[496];wire frame_active=saved[552];
    wire [63:0] buffer_end={32'd0,buffer_base}+buffer_bytes,table_end={32'd0,table_base}+table_bytes,scratch_end={32'd0,scratch_base}+scratch_bytes;
    wire config_good=buffer_bytes!=0&&scratch_bytes!=0&&buffer_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&table_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&scratch_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (buffer_end<=table_base||table_end<=buffer_base)&&(buffer_end<=scratch_base||scratch_end<=buffer_base)&&(table_end<=scratch_base||scratch_end<=table_base)&&
        maximum<=table_bytes&&allowed<=table_bytes&&used<=maximum&&entries<=(used>>5)&&((used==0)==(entries==0))&&buffered<=buffer_bytes&&
        saved[415:385]==0&&saved[479]==0&&saved[511:497]==0&&saved[543]==0&&saved[575:553]==0&&saved[767:640]==0&&
        (!block_active||(saved[478:448]!=0&&(saved[495:488]==1||saved[495:488]==5)));
    wire is_header=s_type==1||s_type==5||s_type==9;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire slot_request=state==WRITE_REQ||state==FEED_REQ&&!discard&&hp_input_ready&&feed_position<buffered;
    wire [31:0] slot_address=buffer_base+(state==WRITE_REQ?buffered:feed_position);
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(slot_request),.req_ready(slot_ready),.req_write(state==WRITE_REQ),.req_addr(slot_address[MEMORY_ADDR_WIDTH-1:0]),.req_bytes(4'd1),.req_data({64'd0,byte_value}),
        .result_valid(slot_valid),.result_ready(state==WRITE_WAIT||state==FEED_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),
        .mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(slot_idle));
    wire hp_start_ready,hp_input_ready,hp_header_valid,hp_completion_valid,hp_idle;
    wire [7:0] hp_status,hp_detail,hp_aux;wire [31:0] hp_maximum,hp_used,hp_entries,hp_headers,hp_list_bytes;
    hpack_header_decoder #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.USER_WIDTH(USER_WIDTH)) hpack(
        .clk(clk),.rst(rst),.start_valid(state==HP_START&&!hpack_started),.start_ready(hp_start_ready),.start_bytes(buffered),.start_user(context_id),
        .cfg_table_base(table_base[MEMORY_ADDR_WIDTH-1:0]),.cfg_scratch_base(scratch_base[MEMORY_ADDR_WIDTH-1:0]),.cfg_table_bytes(table_bytes[MEMORY_ADDR_WIDTH:0]),.cfg_scratch_bytes(scratch_bytes[MEMORY_ADDR_WIDTH:0]),
        .cfg_maximum(maximum),.cfg_allowed_maximum(allowed),.cfg_used(used),.cfg_entries(entries),.cfg_header_list_limit(list_limit),.cfg_required_update(required_update),.cfg_required_maximum(required_maximum),
        .s_data(byte_value),.s_valid(state==FEED_SEND),.s_ready(hp_input_ready),.s_user(context_id),
        .header_valid(hp_header_valid),.header_ready(discard&&!header_exposed?1'b1:header_ready),.header_name_base(header_name_base),.header_value_base(header_value_base),
        .header_name_bytes(header_name_bytes),.header_value_bytes(header_value_bytes),.header_representation(header_representation),.header_user(header_user),
        .completion_valid(hp_completion_valid),.completion_ready(state==HP_WAIT),.completion_status(hp_status),.completion_detail(hp_detail),.completion_aux(hp_aux),
        .completion_maximum(hp_maximum),.completion_used(hp_used),.completion_entries(hp_entries),.completion_headers(hp_headers),.completion_list_bytes(hp_list_bytes),.completion_user(),
        .mem_valid(mem_valid[1+:2]),.mem_ready(mem_ready[1+:2]),.mem_write(mem_write[1+:2]),.mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:2*MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[4+:8]),.mem_data(mem_data[72+:144]),
        .mem_rsp_valid(mem_rsp_valid[1+:2]),.mem_rsp_ready(mem_rsp_ready[1+:2]),.mem_rsp_data(mem_rsp_data[72+:144]),.mem_rsp_status(mem_rsp_status[8+:16]),.idle(hp_idle));
    assign start_ready=!rst&&state==IDLE;
    assign s_ready=!rst&&(state==RUN&&(!m_valid||m_ready)||state==DRAIN);
    assign header_valid=hp_header_valid&&(!discard||header_exposed);
    // Independently acknowledge HPACK and the admission/validation consumer.
    // Either may wait without causing the other to accept a duplicate BEGIN.
    assign block_start_valid=BLOCK_START_PORT&&state==HP_START&&!block_started;
    assign block_start_stream=saved[478:448];assign block_start_promised_stream=saved[542:512];
    assign block_start_type=saved[495:488];assign block_start_flags=saved[487:480];assign block_start_user=context_id;
    assign block_valid=state==BLOCK_DONE;assign block_stream=saved[478:448];assign block_promised_stream=saved[542:512];
    assign block_type=saved[495:488];assign block_flags=saved[487:480];assign block_user=context_id;
    assign m_user=context_id;
    assign result_valid=state==RESULT;assign result_state=result_failed?768'd0:saved;
    assign idle=state==IDLE&&!m_valid&&hp_idle&&slot_idle&&!(start_valid&&start_ready);
    task fail(input [31:0] error,input [7:0] detail);
        begin result_failed<=1;result_error<=error;result_detail<=detail;discard<=1;state<=DRAIN;end
    endtask
    task forward_event;
        begin m_valid<=1;m_kind<=s_kind;m_data<=s_data;m_arg0<=s_arg0;m_arg1<=s_arg1;m_length<=s_length;m_type<=s_type;m_flags<=s_flags;m_stream<=s_stream;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;saved<=0;context_id<=0;byte_value<=0;feed_position<=0;discard<=0;header_exposed<=0;hpack_started<=0;block_started<=0;
            m_valid<=0;m_kind<=0;m_data<=0;m_arg0<=0;m_arg1<=0;m_length<=0;m_type<=0;m_flags<=0;m_stream<=0;
            block_headers<=0;block_list_bytes<=0;result_failed<=0;result_error<=0;result_detail<=0;
        end else begin
            if(m_valid&&m_ready)m_valid<=0;
            if(hp_header_valid&&!discard)header_exposed<=1;
            if(header_valid&&header_ready)header_exposed<=0;
            case(state)
                IDLE:if(start_valid&&start_ready)begin saved<=cfg_state;context_id<=start_user;discard<=0;header_exposed<=0;result_failed<=0;result_error<=0;result_detail<=0;state<=CHECK;end
                CHECK:if(!config_good)fail(2,1);else state<=RUN;
                RUN:begin
                    if(s_valid&&s_ready)begin
                        if(s_user!=context_id)fail(2,2);
                        else if(s_kind==11&&s_arg1==0)begin forward_event;fail(s_arg0,3);end
                        else if(s_kind==0)begin
                            if(frame_active)fail(2,4);
                            else begin
                                saved[552]<=1;saved[551:544]<=s_type;saved[607:576]<=0;saved[639:608]<=0;
                                if(is_header)begin
                                    if(s_type==9)begin if(!block_active||block_stream!=s_stream)fail(1,5);end
                                    else if(block_active)fail(1,5);
                                    else begin saved[496]<=1;saved[495:488]<=s_type;saved[487:480]<=s_flags;saved[479:448]<={1'b0,s_stream};saved[447:416]<=0;saved[543:512]<=0;end
                                end else forward_event;
                            end
                        end else if(!is_header)begin
                            if(s_kind==3)saved[552]<=0;
                            forward_event;
                        end else if(!frame_active||!block_active||block_stream!=s_stream)fail(2,6);
                        else if(s_kind==1)begin
                            if({32'd0,buffered}+s_arg0>buffer_bytes)fail(11,7);
                            else begin saved[607:576]<=s_arg0;if(s_type==5)saved[543:512]<=s_arg1;end
                        end else if(s_kind==2)begin
                            if(buffered>=buffer_bytes||fragment_received>=fragment_bytes)fail(11,7);
                            else begin byte_value<=s_data;state<=WRITE_REQ;end
                        end else if(s_kind==3)begin
                            saved[552]<=0;
                            if(fragment_received!=fragment_bytes)fail(2,8);
                            else if(s_flags[2])begin hpack_started<=0;block_started<=0;state<=HP_START;end
                        end else if(s_kind!=9)fail(2,9);
                    end else if(finish_valid&&(!m_valid||m_ready))state<=FINISH;
                end
                WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
                WRITE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(2,10);
                    else begin saved[447:416]<=buffered+1'b1;saved[639:608]<=fragment_received+1'b1;state<=RUN;end
                end
                HP_START:begin
                    if(!hpack_started&&hp_start_ready)hpack_started<=1;
                    if(!block_started&&(!BLOCK_START_PORT||block_start_ready))block_started<=1;
                    if((hpack_started||hp_start_ready)&&(block_started||!BLOCK_START_PORT||block_start_ready))begin
                        feed_position<=0;state<=buffered==0?HP_WAIT:FEED_REQ;
                    end
                end
                FEED_REQ:begin
                    if(hp_input_ready)begin
                        if(discard)begin byte_value<=0;state<=FEED_SEND;end
                        else if(slot_ready)state<=FEED_WAIT;
                    end
                end
                FEED_WAIT:if(slot_valid)begin
                    if(slot_status!=0)begin discard<=1;result_failed<=1;result_error<=2;result_detail<=11;byte_value<=0;end
                    else byte_value<=slot_data[7:0];
                    state<=FEED_SEND;
                end
                FEED_SEND:if(hp_input_ready)begin feed_position<=feed_position+1'b1;state<=feed_position+1==buffered?HP_WAIT:FEED_REQ;end
                HP_WAIT:if(hp_completion_valid)begin
                    if(discard)state<=DRAIN;
                    else if(hp_status!=0)begin
                        result_failed<=1;result_error<=hp_status==5||hp_status==11?32'd11:
                            ((hp_status==3||hp_status==9)&&hp_aux!=0)||hp_status==1||hp_status==6||hp_status==7||hp_status==8||hp_status==12||(hp_status==3&&hp_detail>=4)?32'd2:32'd9;
                        result_detail<=8'h80|hp_status;discard<=1;state<=DRAIN;
                    end else begin
                        saved[223:192]<=hp_maximum;saved[287:256]<=hp_used;saved[319:288]<=hp_entries;saved[384]<=0;saved[496]<=0;saved[447:416]<=0;
                        block_headers<=hp_headers;block_list_bytes<=hp_list_bytes;state<=BLOCK_DONE;
                    end
                end
                BLOCK_DONE:if(block_ready)state<=RUN;
                DRAIN:if(finish_valid&&!m_valid&&slot_idle&&hp_idle)state<=FINISH;
                FINISH:if(!m_valid&&slot_idle&&hp_idle)state<=RESULT;
                RESULT:if(result_ready)state<=IDLE;
                default:state<=DRAIN;
            endcase
        end
    end
endmodule
`default_nettype wire
