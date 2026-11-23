`timescale 1ns/1ps
`default_nettype none
// Consume committed complete frames from http2_control_journal. Source READY
// is delayed until the real window operation, typed callback, or ACK wire beat
// retires. Non-window peer settings/ACK bookkeeping, missing-key classification
// and cancellation must be supplied by actual parent controllers.
module http2_shutdown_control_executor #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_stream_base,cfg_window_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_stream_bytes,cfg_window_bytes,
    input wire s_valid,output wire s_ready,output wire [7:0] s_status,
    input wire [3:0] s_kind,input wire [7:0] s_data,input wire [31:0] s_arg0,s_arg1,
    input wire [23:0] s_length,input wire [7:0] s_type,s_flags,input wire [30:0] s_stream,
    input wire [USER_WIDTH-1:0] s_user,
    input wire finish_valid,output wire finish_ready,input wire finish_abort,
    output wire result_valid,input wire result_ready,output reg [7:0] result_status,result_detail,result_memory_status,
    output reg result_connection_error,output reg [31:0] result_http2_error,
    output wire [USER_WIDTH-1:0] result_user,output reg [31:0] result_frames,result_ack_frames,result_window_updates,
    output wire window_req_valid,input wire window_req_ready,output reg [3:0] window_req_op,
    output wire window_req_maintenance,output wire [USER_WIDTH-1:0] window_req_user,
    output reg [30:0] window_req_stream,output wire [31:0] window_req_generation,
    output wire [MEMORY_ADDR_WIDTH-1:0] window_req_record_address,output reg [31:0] window_req_amount,
    output wire [MEMORY_ADDR_WIDTH-1:0] window_cfg_context_base,window_cfg_stream_base,window_cfg_window_base,window_cfg_work_floor,
    output wire [MEMORY_ADDR_WIDTH:0] window_cfg_context_bytes,window_cfg_stream_bytes,window_cfg_window_bytes,
    input wire window_rsp_valid,output wire window_rsp_ready,input wire [3:0] window_rsp_op,
    input wire [USER_WIDTH-1:0] window_rsp_user,input wire [30:0] window_rsp_stream,
    input wire [7:0] window_rsp_status,window_rsp_detail,window_rsp_memory_status,
    input wire window_rsp_connection_error,input wire [31:0] window_rsp_http2_error,
    output wire notice_valid,input wire notice_ready,output reg [1:0] notice_kind,
    output wire [USER_WIDTH-1:0] notice_user,output reg [15:0] notice_setting,
    output reg [31:0] notice_value,output reg [63:0] notice_payload,
    input wire notice_result_valid,output wire notice_result_ready,input wire [7:0] notice_status,
    output wire cancel_valid,input wire cancel_ready,output wire [USER_WIDTH-1:0] cancel_user,
    output reg cancel_goaway,output reg [30:0] cancel_stream,output reg [31:0] cancel_arg0,cancel_arg1,
    input wire cancel_result_valid,output wire cancel_result_ready,input wire [7:0] cancel_status,
    output wire classify_valid,input wire classify_ready,output wire [USER_WIDTH-1:0] classify_user,
    output wire [30:0] classify_stream,input wire classify_result_valid,output wire classify_result_ready,
    input wire [7:0] classify_status,input wire classify_closed,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,output wire idle
,
    input wire [7:0] cancel_detail,
    input wire [7:0] cancel_memory_status,
    input wire  cancel_connection_error,
    input wire [31:0] cancel_http2_error
);
    localparam IDLE=0,RUN=1,CHECK_EVENT=2,WINDOW_SEND=3,WINDOW_WAIT=4,NOTICE_SEND=5,NOTICE_WAIT=6,
        CANCEL_SEND=7,CANCEL_WAIT=8,CLASSIFY_SEND=9,CLASSIFY_WAIT=10,TX=11,ACK=12,RESULT=13;
    reg [3:0] state,event_kind;reg [USER_WIDTH-1:0] owner,event_user;
    reg frame_active,faulted,payload_seen;reg [7:0] frame_type,frame_flags,event_type,event_flags;
    reg [23:0] frame_length,event_length;reg [30:0] frame_stream,event_stream;
    reg [31:0] event_arg0,event_arg1,setting_bytes;reg [63:0] ping_payload;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,streams,windows,work_floor;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,stream_bytes,window_bytes;
    wire same_frame=event_user==owner&&event_type==frame_type&&event_flags==frame_flags&&event_length==frame_length&&event_stream==frame_stream;
    wire allowed_type=event_type==3||event_type==4||event_type==6||event_type==7||event_type==8;
    assign start_ready=!rst&&state==IDLE;assign s_ready=!rst&&state==ACK;assign s_status=result_status;
    assign finish_ready=!rst&&state==RUN&&!s_valid&&(!frame_active||faulted||finish_abort);
    assign result_valid=state==RESULT;assign result_user=owner;assign idle=state==IDLE&&!start_valid;
    assign window_req_valid=state==WINDOW_SEND;assign window_rsp_ready=state==WINDOW_WAIT;
    assign window_req_maintenance=0;assign window_req_user=owner;assign window_req_generation=0;assign window_req_record_address=0;
    assign window_cfg_context_base=contexts;assign window_cfg_context_bytes=context_bytes;
    assign window_cfg_stream_base=streams;assign window_cfg_stream_bytes=stream_bytes;
    assign window_cfg_window_base=windows;assign window_cfg_window_bytes=window_bytes;assign window_cfg_work_floor=work_floor;
    assign notice_valid=state==NOTICE_SEND;assign notice_result_ready=state==NOTICE_WAIT;assign notice_user=owner;
    assign cancel_valid=state==CANCEL_SEND;assign cancel_result_ready=state==CANCEL_WAIT;assign cancel_user=owner;
    assign classify_valid=state==CLASSIFY_SEND;assign classify_result_ready=state==CLASSIFY_WAIT;
    assign classify_user=owner;assign classify_stream=frame_stream;
    reg [511:0] ack_data;
    integer lane;
    always @*begin
        ack_data=0;ack_data[23:16]=frame_type==6?8'd8:8'd0;ack_data[31:24]=frame_type;ack_data[39:32]=1;
        if(frame_type==6)for(lane=0;lane<8;lane=lane+1)ack_data[72+lane*8+:8]=ping_payload[63-lane*8-:8];
    end
    assign m_axis_tx_tdata=ack_data;assign m_axis_tx_tkeep=frame_type==6?64'h1ffff:64'h1ff;
    assign m_axis_tx_tvalid=!rst&&state==TX;assign m_axis_tx_tlast=1;assign m_axis_tx_tuser=owner;
    task fail(input [7:0] status,input [7:0] detail,input connection_error,input [31:0] h2_error);
        begin result_status<=status;result_detail<=detail;result_connection_error<=connection_error;
            result_http2_error<=h2_error;faulted<=1;state<=ACK;end
    endtask
    task window(input [3:0] op,input [30:0] stream,input [31:0] amount);
        begin window_req_op<=op;window_req_stream<=stream;window_req_amount<=amount;state<=WINDOW_SEND;end
    endtask
    initial begin if(USER_WIDTH<1||USER_WIDTH>16)$error("Unsupported control owner width");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;event_kind<=0;owner<=0;event_user<=0;frame_active<=0;faulted<=0;payload_seen<=0;
            frame_type<=0;frame_flags<=0;event_type<=0;event_flags<=0;frame_length<=0;event_length<=0;
            frame_stream<=0;event_stream<=0;event_arg0<=0;event_arg1<=0;setting_bytes<=0;ping_payload<=0;
            contexts<=0;streams<=0;windows<=0;work_floor<=0;context_bytes<=0;stream_bytes<=0;window_bytes<=0;
            result_status<=0;result_detail<=0;result_memory_status<=0;result_connection_error<=0;result_http2_error<=0;
            result_frames<=0;result_ack_frames<=0;result_window_updates<=0;window_req_op<=0;window_req_stream<=0;window_req_amount<=0;
            notice_kind<=0;notice_setting<=0;notice_value<=0;notice_payload<=0;cancel_goaway<=0;cancel_stream<=0;cancel_arg0<=0;cancel_arg1<=0;
        end else case(state)
            IDLE:if(start_valid&&start_ready)begin
                owner<=start_user;contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;streams<=cfg_stream_base;stream_bytes<=cfg_stream_bytes;
                windows<=cfg_window_base;window_bytes<=cfg_window_bytes;work_floor<=cfg_work_floor;
                frame_active<=0;faulted<=0;payload_seen<=0;result_status<=0;result_detail<=0;result_memory_status<=0;
                result_connection_error<=0;result_http2_error<=0;result_frames<=0;result_ack_frames<=0;result_window_updates<=0;state<=RUN;
            end
            RUN:if(finish_valid&&finish_ready)begin frame_active<=0;state<=RESULT;end
                else if(s_valid&&!faulted)begin
                    event_kind<=s_kind;event_user<=s_user;event_type<=s_type;event_flags<=s_flags;event_length<=s_length;
                    event_stream<=s_stream;event_arg0<=s_arg0;event_arg1<=s_arg1;state<=CHECK_EVENT;
                end
            CHECK_EVENT:if(event_user!=owner)fail(7,1,1,2);
                else if(event_kind==0)begin
                    if(frame_active||!allowed_type||(event_type==4||event_type==6||event_type==7)&&event_stream!=0||event_type==3&&event_stream==0||
                        event_type==4&&event_flags[0]&&event_length!=0||event_type==6&&event_length!=8||
                        (event_type==3||event_type==8)&&event_length!=4||event_type==7&&event_length<8)fail(4,1,1,1);
                    else begin frame_active<=1;frame_type<=event_type;frame_flags<=event_flags;frame_length<=event_length;frame_stream<=event_stream;
                        setting_bytes<=0;payload_seen<=0;ping_payload<=0;state<=ACK;end
                end else if(!frame_active||!same_frame)fail(7,2,1,2);
                else if(event_kind==4&&frame_type==4&&!frame_flags[0])begin
                    if(event_arg0[31:16]!=0||{1'b0,setting_bytes}+33'd6>frame_length)fail(4,2,1,1);
                    else begin
                        setting_bytes<=setting_bytes+6;
                        if(event_arg0==4)window(3,0,event_arg1);
                        else if(event_arg0==5)window(4,0,event_arg1);
                        else if(event_arg0==1||event_arg0==2||event_arg0==3||event_arg0==6)begin
                            notice_kind<=0;notice_setting<=event_arg0[15:0];notice_value<=event_arg1;notice_payload<=0;state<=NOTICE_SEND;
                        end else state<=ACK;
                    end
                end else if(event_kind==7&&frame_type==8&&!payload_seen)begin payload_seen<=1;window(9,frame_stream,event_arg0);end
                else if(event_kind==5&&frame_type==6&&!payload_seen)begin payload_seen<=1;ping_payload<={event_arg0,event_arg1};state<=ACK;end
                else if((event_kind==8&&frame_type==3||event_kind==6&&frame_type==7)&&!payload_seen)begin
                    payload_seen<=1;cancel_goaway<=frame_type==7;cancel_stream<=frame_stream;cancel_arg0<=event_arg0;cancel_arg1<=event_arg1;state<=CANCEL_SEND;
                end else if(event_kind==3)begin
                    if(frame_type==4&&setting_bytes!=frame_length||frame_type!=4&&!payload_seen)fail(4,3,1,1);
                    else if((frame_type==4||frame_type==6)&&!frame_flags[0])state<=TX;
                    else if((frame_type==4||frame_type==6)&&frame_flags[0])begin
                        notice_kind<=frame_type==4?1:2;notice_setting<=0;notice_value<=0;notice_payload<=ping_payload;state<=NOTICE_SEND;
                    end else state<=ACK;
                end else fail(4,4,1,1);
            WINDOW_SEND:if(window_req_ready)state<=WINDOW_WAIT;
            WINDOW_WAIT:if(window_rsp_valid)begin
                if(window_rsp_op!=window_req_op||window_rsp_user!=owner||window_rsp_stream!=window_req_stream)fail(7,3,1,2);
                else if(window_rsp_status==0)begin result_window_updates<=result_window_updates+1'b1;state<=ACK;end
                else if(window_req_op==9&&window_rsp_status==3&&window_rsp_detail==10)state<=CLASSIFY_SEND;
                else begin result_memory_status<=window_rsp_memory_status;fail(window_rsp_status,window_rsp_detail,window_rsp_connection_error,window_rsp_http2_error);end
            end
            NOTICE_SEND:if(notice_ready)state<=NOTICE_WAIT;
            NOTICE_WAIT:if(notice_result_valid)begin if(notice_status!=0)fail(9,notice_status,1,2);else state<=ACK;end
            CANCEL_SEND:if(cancel_ready)state<=CANCEL_WAIT;
            CANCEL_WAIT:if(cancel_result_valid)begin if(cancel_status!=0)begin result_memory_status<=cancel_memory_status;
                fail(cancel_status,cancel_detail,cancel_connection_error,cancel_http2_error);end else state<=ACK;end
            CLASSIFY_SEND:if(classify_ready)state<=CLASSIFY_WAIT;
            CLASSIFY_WAIT:if(classify_result_valid)begin
                if(classify_status!=0)fail(11,classify_status,1,2);
                else if(!classify_closed)fail(4,5,1,1);else state<=ACK;
            end
            TX:if(m_axis_tx_tready)begin result_ack_frames<=result_ack_frames+1'b1;state<=ACK;end
            ACK:if(s_valid&&s_ready)begin
                if(event_kind==3&&!faulted)begin frame_active<=0;result_frames<=result_frames+1'b1;end
                state<=RUN;
            end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
