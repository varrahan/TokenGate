`timescale 1ns/1ps
`default_nettype none
// Raw frame events -> semantic events. State is per connection, handed off at
// DMA packet boundaries. Fields/data remain tentative until packet success.
module http2_payload_decoder #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire cfg_server_role,input wire [255:0] cfg_state,
    input wire s_valid,output wire s_ready,input wire [1:0] s_kind,input wire [7:0] s_data,
    input wire [23:0] s_length,input wire [7:0] s_type,s_flags,input wire [30:0] s_stream,
    input wire s_payload_last,input wire [31:0] s_error,input wire [USER_WIDTH-1:0] s_user,
    output reg m_valid,input wire m_ready,output reg [3:0] m_kind,output reg [7:0] m_data,
    output reg [31:0] m_arg0,m_arg1,output wire [23:0] m_length,output wire [7:0] m_type,m_flags,
    output wire [30:0] m_stream,output wire [USER_WIDTH-1:0] m_user,
    input wire finish_valid,output wire result_valid,input wire result_ready,
    output wire [255:0] result_state,output reg result_failed,output reg [31:0] result_error,output reg [7:0] result_detail,
    output wire idle
);
    localparam IDLE=0,CHECK=1,RUN=2,BODY_BEGIN=3,DRAIN=4,FINISH=5,RESULT=6;
    reg [2:0] state;
    reg frame_active,pad_seen,body_started,server_role,bad_reserved;
    reg [7:0] frame_type,flags,pad;
    reg [30:0] stream_id;
    reg [23:0] length,received;
    reg [63:0] control_shift;
    reg [2:0] control_count;
    reg [USER_WIDTH-1:0] context_id;
    wire body_frame=frame_type==0||frame_type==1||frame_type==5||frame_type==9;
    wire padded=(frame_type==0||frame_type==1||frame_type==5)&&flags[3];
    wire [2:0] prefix_bytes=frame_type==1&&flags[5]?3'd5:frame_type==5?3'd4:3'd0;
    wire [24:0] body_start=(padded?25'd1:25'd0)+prefix_bytes;
    wire [24:0] body_limit={1'b0,length}-{17'd0,pad};
    wire [24:0] content_length=body_limit-body_start;
    wire config_good=!bad_reserved&&control_count<=5&&(!frame_active||
        (received<=length&&(!padded||pad_seen||received==0)&&(!pad_seen||!body_frame||body_limit>=body_start)&&
         (!body_frame||!pad_seen||received<body_start||body_started)));
    wire [63:0] shifted={control_shift[55:0],s_data};
    wire [31:0] setting_value=shifted[31:0];wire [15:0] setting_id=shifted[47:32];
    wire bad_push_setting=setting_id==2&&(setting_value>1||(!server_role&&setting_value==1));
    wire bad_window_setting=setting_id==4&&setting_value[31];
    wire bad_frame_setting=setting_id==5&&(setting_value<16384||setting_value>24'hffffff);
    wire output_space=!m_valid||m_ready;
    assign start_ready=!rst&&state==IDLE;
    assign s_ready=!rst&&((state==RUN&&output_space)||(state==DRAIN));
    assign result_valid=state==RESULT;
    assign result_state=result_failed?256'd0:{83'd0,body_started,pad_seen,control_count,control_shift,pad,received,length,stream_id,flags,frame_type,frame_active};
    assign m_length=length;assign m_type=frame_type;assign m_flags=flags;assign m_stream=stream_id;assign m_user=context_id;
    assign idle=state==IDLE&&!m_valid&&!(start_valid&&start_ready);
    task emit(input [3:0] kind,input [7:0] data,input [31:0] arg0,input [31:0] arg1);
        begin m_valid<=1;m_kind<=kind;m_data<=data;m_arg0<=arg0;m_arg1<=arg1;end
    endtask
    task fail(input [31:0] error,input [7:0] detail);
        begin result_failed<=1;result_error<=error;result_detail<=detail;emit(11,0,error,0);state<=DRAIN;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;frame_active<=0;pad_seen<=0;body_started<=0;server_role<=0;bad_reserved<=0;frame_type<=0;flags<=0;pad<=0;stream_id<=0;length<=0;received<=0;
            control_shift<=0;control_count<=0;context_id<=0;m_valid<=0;m_kind<=0;m_data<=0;m_arg0<=0;m_arg1<=0;result_failed<=0;result_error<=0;result_detail<=0;
        end else begin
            if(m_valid&&m_ready)m_valid<=0;
            case(state)
                IDLE:if(start_valid&&start_ready)begin
                    {body_started,pad_seen,control_count,control_shift,pad,received,length,stream_id,flags,frame_type,frame_active}<=cfg_state[172:0];
                    bad_reserved<=cfg_state[255:173]!=0;server_role<=cfg_server_role;context_id<=start_user;
                    result_failed<=0;result_error<=0;result_detail<=0;state<=CHECK;
                end
                CHECK:if(!config_good)begin result_failed<=1;result_error<=2;result_detail<=1;state<=DRAIN;end else state<=RUN;
                RUN:begin
                    if(s_valid&&s_ready)begin
                        if(s_user!=context_id)fail(2,2);
                        else if(s_kind==0)begin
                            if(frame_active)fail(2,3);
                            else begin
                                frame_active<=1;frame_type<=s_type;flags<=s_flags;stream_id<=s_stream;length<=s_length;received<=0;pad<=0;body_started<=0;
                                control_shift<=0;control_count<=0;pad_seen<=!((s_type==0||s_type==1||s_type==5)&&s_flags[3]);emit(0,0,0,0);
                                if((s_type==0||s_type==1||s_type==5)&&s_flags[3]&&s_length==0)begin
                                    // FRAME_BEGIN has not been visible yet; replace it with the error.
                                    result_failed<=1;result_error<=6;result_detail<=4;emit(11,0,6,0);state<=DRAIN;
                                end else if((s_type==0||s_type==1||s_type==9)&&!(s_type!=9&&s_flags[3])&&!(s_type==1&&s_flags[5]))state<=BODY_BEGIN;
                            end
                        end else if(s_kind==3)begin
                            if(frame_active)fail(2,3);else begin
                                frame_type<=s_type;flags<=s_flags;stream_id<=s_stream;length<=s_length;
                                emit(11,0,s_error,{1'b0,s_stream});
                            end
                        end else if(!frame_active||s_type!=frame_type||s_flags!=flags||s_stream!=stream_id||s_length!=length)fail(2,5);
                        else if(s_kind==1)begin
                            if(received>=length||s_payload_last!=(received+25'd1=={1'b0,length}))fail(2,6);
                            else begin
                                received<=received+1'b1;
                                if(body_frame)begin
                                    if(!pad_seen)begin
                                        pad<=s_data;pad_seen<=1;
                                        if({17'd0,s_data}+body_start>{1'b0,length})fail(1,7);
                                        else if(prefix_bytes==0)state<=BODY_BEGIN;
                                    end else if(received<body_start)begin
                                        control_shift<=shifted;
                                        if(received+25'd1==body_start)begin
                                            if(frame_type==5&&shifted[30:0]==0)fail(1,8);
                                            else begin
                                                if(frame_type==1)emit(9,0,shifted[39:8],{24'd0,shifted[7:0]}+1'b1);
                                                state<=BODY_BEGIN;
                                            end
                                        end
                                    end else if(received<body_limit)begin
                                        if(!body_started)fail(2,9);else emit(2,s_data,0,0);
                                    end
                                    // Received padding is ignored; RFC 9113 allows not checking zero fill.
                                end else begin
                                    if(frame_type!=7||received<8)control_shift<=shifted;
                                    case(frame_type)
                                        4:begin
                                            if(control_count==5)begin
                                                control_count<=0;
                                                if(bad_push_setting||bad_frame_setting)fail(1,10);
                                                else if(bad_window_setting)fail(3,10);
                                                else emit(4,0,{16'd0,setting_id},setting_value);
                                            end else control_count<=control_count+1'b1;
                                        end
                                        6:if(received==7)emit(5,0,shifted[63:32],shifted[31:0]);
                                        7:if(received==7)emit(6,0,{1'b0,shifted[62:32]},shifted[31:0]);
                                        8:if(received==3)begin
                                            if(shifted[30:0]==0)begin if(stream_id==0)fail(1,11);else emit(11,0,1,{1'b0,stream_id});end
                                            else emit(7,0,{1'b0,shifted[30:0]},0);
                                        end
                                        3:if(received==3)emit(8,0,shifted[31:0],0);
                                        2:if(received==4)emit(9,0,shifted[39:8],{24'd0,shifted[7:0]}+1'b1);
                                        default:begin end
                                    endcase
                                end
                            end
                        end else if(s_kind==2)begin
                            if(received!=length||body_frame&&!body_started||frame_type==4&&control_count!=0)fail(2,12);
                            else begin frame_active<=0;emit(3,0,0,0);end
                        end else fail(2,13);
                    end else if(finish_valid&&output_space)state<=FINISH;
                end
                BODY_BEGIN:if(output_space)begin
                    emit(1,0,{7'd0,content_length},frame_type==5?{1'b0,control_shift[30:0]}:32'd0);body_started<=1;state<=RUN;
                end
                DRAIN:if(finish_valid&&!m_valid)state<=FINISH;
                FINISH:if(!m_valid)state<=RESULT;
                RESULT:if(result_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
