`timescale 1ns/1ps
`default_nettype none
// One connection fragment, with explicit state handoff between DMA packets.
// The caller saves/restores the 160-bit record per connection. Payload events
// retain padding/priority/control bytes for the next transport stage.
module http2_frame_reader #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire start_fresh,input wire [USER_WIDTH-1:0] start_user,
    input wire [159:0] cfg_state,input wire [23:0] cfg_max_frame_bytes,input wire cfg_server_role,cfg_allow_push,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output wire s_ready,input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output wire event_valid,input wire event_ready,output wire [1:0] event_kind,output wire [7:0] event_data,
    output wire [23:0] event_length,output wire [7:0] event_type,event_flags,output wire [30:0] event_stream,
    output wire event_payload_last,output wire [31:0] event_error,output wire [USER_WIDTH-1:0] event_user,
    output wire completion_valid,input wire completion_ready,output reg completion_failed,
    output reg [31:0] completion_error,output reg [7:0] completion_detail,output wire [159:0] completion_state,
    output wire [USER_WIDTH-1:0] completion_user,output wire idle
);
    localparam IDLE=0,CHECK=1,PREFACE=2,FRAME_HEADER=3,VALIDATE=4,HEADER_EVENT=5,PAYLOAD=6,PAYLOAD_EVENT=7,
        END_EVENT=8,SKIP=9,STREAM_ERROR_EVENT=10,ABORT=11,RESULT=12;
    reg [3:0] state,header_index;
    reg [4:0] preface_index;
    reg [1:0] phase;
    reg [23:0] length,payload_remaining,max_frame_bytes;
    reg [7:0] frame_type,flags,payload_data;
    reg [30:0] stream_id,continuation_stream;
    reg first_frame,server_role,allow_push,bad_reserved;
    reg [USER_WIDTH-1:0] context_id;
    localparam [191:0] CLIENT_MAGIC=192'h505249202a20485454502f322e300d0a0d0a534d0d0a0d0a;
    wire [7:0] magic_byte=CLIENT_MAGIC[(23-preface_index)*8+:8];
    wire config_good=!bad_reserved&&max_frame_bytes>=16384&&header_index<=8&&preface_index<=24&&
        (phase!=0||preface_index<24)&&((phase!=2&&phase!=3)||(payload_remaining!=0&&payload_remaining<=length&&!first_frame));
    wire needs_stream=frame_type==0||frame_type==1||frame_type==2||frame_type==3||frame_type==5||frame_type==9;
    wire needs_connection=frame_type==4||frame_type==6||frame_type==7;
    wire bad_length=(frame_type==2&&length!=5)||(frame_type==3&&length!=4)||
        (frame_type==4&&((flags[0]&&length!=0)||length%6!=0))||(frame_type==5&&length<(flags[3]?5:4))||
        (frame_type==6&&length!=8)||(frame_type==7&&length<8)||(frame_type==8&&length!=4)||
        (frame_type==1&&flags[5]&&length<(flags[3]?6:5));
    wire read_state=state==PREFACE||state==FRAME_HEADER||state==PAYLOAD||state==SKIP;
    assign start_ready=!rst&&state==IDLE;
    assign s_ready=!rst&&(read_state||state==ABORT);
    assign event_valid=state==HEADER_EVENT||state==PAYLOAD_EVENT||state==END_EVENT||state==STREAM_ERROR_EVENT;
    assign event_kind=state==PAYLOAD_EVENT?2'd1:state==END_EVENT?2'd2:state==STREAM_ERROR_EVENT?2'd3:2'd0;
    assign event_data=state==PAYLOAD_EVENT?payload_data:8'd0;
    assign event_length=length;assign event_type=frame_type;assign event_flags=flags;assign event_stream=stream_id;
    assign event_payload_last=state==PAYLOAD_EVENT&&payload_remaining==0;
    assign event_error=state==STREAM_ERROR_EVENT?32'd6:32'd0;
    assign event_user=context_id;
    assign completion_valid=state==RESULT;
    assign completion_state=completion_failed?160'd0:{22'd0,first_frame,phase,continuation_stream,payload_remaining,stream_id,flags,frame_type,length,header_index,preface_index};
    assign completion_user=context_id;
    assign idle=state==IDLE&&!(start_valid&&start_ready);
    task fail(input [31:0] code,input [7:0] detail,input ended);
        begin completion_failed<=1;completion_error<=code;completion_detail<=detail;state<=ended?RESULT:ABORT;end
    endtask
    task next_header;
        begin phase<=1;header_index<=0;length<=0;frame_type<=0;flags<=0;stream_id<=0;payload_remaining<=0;state<=FRAME_HEADER;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;header_index<=0;preface_index<=0;phase<=0;length<=0;payload_remaining<=0;max_frame_bytes<=0;
            frame_type<=0;flags<=0;payload_data<=0;stream_id<=0;continuation_stream<=0;first_frame<=1;server_role<=1;allow_push<=0;bad_reserved<=0;context_id<=0;
            completion_failed<=0;completion_error<=0;completion_detail<=0;
        end else begin
            case(state)
                IDLE:if(start_valid&&start_ready)begin
                    max_frame_bytes<=cfg_max_frame_bytes;server_role<=cfg_server_role;allow_push<=cfg_allow_push;context_id<=start_user;
                    completion_failed<=0;completion_error<=0;completion_detail<=0;state<=CHECK;
                    if(start_fresh)begin
                        preface_index<=cfg_server_role?0:24;header_index<=0;length<=0;frame_type<=0;flags<=0;stream_id<=0;
                        payload_remaining<=0;continuation_stream<=0;phase<=cfg_server_role?0:1;first_frame<=1;bad_reserved<=0;
                    end else begin
                        {first_frame,phase,continuation_stream,payload_remaining,stream_id,flags,frame_type,length,header_index,preface_index}<=cfg_state[137:0];
                        bad_reserved<=cfg_state[159:138]!=0;
                    end
                end
                CHECK:if(!config_good)fail(2,1,0);else state<=phase==0?PREFACE:phase==1?FRAME_HEADER:phase==2?PAYLOAD:SKIP;
                PREFACE:if(s_valid&&s_ready&&s_keep)begin
                    if(s_data!=magic_byte)fail(1,2,0);
                    else if(preface_index==23)begin preface_index<=24;phase<=1;state<=FRAME_HEADER;end
                    else preface_index<=preface_index+1'b1;
                end
                FRAME_HEADER:if(s_valid&&s_ready&&s_keep)begin
                    case(header_index)
                        0:length[23:16]<=s_data;
                        1:length[15:8]<=s_data;
                        2:length[7:0]<=s_data;
                        3:frame_type<=s_data;
                        4:flags<=s_data;
                        5:stream_id[30:24]<=s_data[6:0];
                        6:stream_id[23:16]<=s_data;
                        7:stream_id[15:8]<=s_data;
                        8:stream_id[7:0]<=s_data;
                    endcase
                    if(header_index==8)state<=VALIDATE;else header_index<=header_index+1'b1;
                end
                VALIDATE:begin
                    if(length>max_frame_bytes)fail(6,3,0);
                    else if(continuation_stream!=0&&(frame_type!=9||stream_id!=continuation_stream))fail(1,4,0);
                    else if(frame_type==9&&continuation_stream==0)fail(1,4,0);
                    else if(first_frame&&(frame_type!=4||flags[0]))fail(1,5,0);
                    else if((needs_stream&&stream_id==0)||(needs_connection&&stream_id!=0))fail(1,6,0);
                    else if(frame_type==5&&(server_role||!allow_push))fail(1,7,0);
                    else if(bad_length)begin
                        if(frame_type==2)begin payload_remaining<=length;state<=STREAM_ERROR_EVENT;end
                        else fail(6,8,0);
                    end else begin
                        first_frame<=0;payload_remaining<=length;
                        if((frame_type==1||frame_type==5)&&!flags[2])continuation_stream<=stream_id;
                        else if(frame_type==9&&flags[2])continuation_stream<=0;
                        if(frame_type>9)begin if(length==0)next_header;else begin phase<=3;state<=SKIP;end end
                        else state<=HEADER_EVENT;
                    end
                end
                HEADER_EVENT:if(event_ready)begin if(length==0)state<=END_EVENT;else begin phase<=2;state<=PAYLOAD;end end
                PAYLOAD:if(s_valid&&s_ready&&s_keep)begin payload_data<=s_data;payload_remaining<=payload_remaining-1'b1;state<=PAYLOAD_EVENT;end
                PAYLOAD_EVENT:if(event_ready)state<=payload_remaining==0?END_EVENT:PAYLOAD;
                END_EVENT:if(event_ready)next_header;
                STREAM_ERROR_EVENT:if(event_ready)begin if(payload_remaining==0)next_header;else begin phase<=3;state<=SKIP;end end
                SKIP:if(s_valid&&s_ready&&s_keep)begin
                    payload_remaining<=payload_remaining-1'b1;if(payload_remaining==1)next_header;
                end
                ABORT:if(s_valid&&s_ready&&s_last)state<=RESULT;
                RESULT:if(completion_ready)state<=IDLE;
                default:state<=ABORT;
            endcase
            if(read_state&&s_valid&&s_ready)begin
                if(s_last)begin if(s_keep)fail(2,9,1);else state<=RESULT;end
                if(s_user!=context_id)fail(2,10,s_last);
            end
        end
    end
endmodule
`default_nettype wire
