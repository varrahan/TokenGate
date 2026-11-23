`timescale 1ns/1ps
`default_nettype none
// Admission before semantic dispatch; padding release after complete committed
// journal replay. Application bytes require a separate actual reclamation hook.
// The parent retains connection/RPC-pool configuration throughout each owner.
module http2_receive_flow_controller #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(
    input wire clk,rst,input wire abort_flow,admit_data,
    input wire init_valid,output wire init_ready,input wire [3:0] init_op,
    input wire init_maintenance,input wire [USER_WIDTH-1:0] init_user,
    input wire [30:0] init_stream,input wire [31:0] init_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] init_address,
    output wire init_result_valid,input wire init_result_ready,
    output wire [7:0] init_status,init_detail,init_memory_status,
    input wire s_valid,output wire s_ready,input wire [3:0] s_kind,input wire [7:0] s_data,
    input wire [31:0] s_arg0,s_arg1,input wire [23:0] s_length,input wire [7:0] s_type,s_flags,
    input wire [30:0] s_stream,input wire [USER_WIDTH-1:0] s_user,
    output wire m_valid,input wire m_ready,output reg [3:0] m_kind,output reg [7:0] m_data,
    output reg [31:0] m_arg0,m_arg1,output reg [23:0] m_length,output reg [7:0] m_type,m_flags,
    output reg [30:0] m_stream,output reg [USER_WIDTH-1:0] m_user,
    input wire replay_valid,output wire replay_ready,input wire [3:0] replay_kind,
    input wire [31:0] replay_arg0,input wire [23:0] replay_length,input wire [7:0] replay_flags,
    input wire [30:0] replay_stream,input wire [USER_WIDTH-1:0] replay_user,
    output wire [7:0] replay_status,
    output wire request_valid,input wire request_ready,output reg [3:0] request_op,
    output reg request_keyed,request_maintenance,output reg [USER_WIDTH-1:0] request_user,
    output reg [30:0] request_stream,output reg [31:0] request_generation,request_amount,
    output reg [MEMORY_ADDR_WIDTH-1:0] request_address,output reg request_is_init,request_is_close,
    input wire result_valid,output wire result_ready,input wire [7:0] result_status,result_detail,result_memory_status,
    input wire [31:0] result_http2_error,input wire result_debit_authorized,
    output reg fault_valid,output reg [7:0] fault_status,fault_detail,fault_memory_status,
    output reg [31:0] fault_http2_error,output wire idle
);
    localparam IDLE=0,SEND=1,WAIT=2,FLOW=3,INIT_RESULT=4,REPLAY_RESULT=5;
    localparam INITIALIZE=0,DEBIT=1,RELEASE=2,UPDATE_STREAM=3,UPDATE_CONNECTION=4,RETIRE_UPDATE=5;
    reg [2:0] state,operation;
    reg [7:0] status,detail,memory_status;
    reg frame_active,body_seen;
    reg [23:0] frame_length;reg [31:0] content_length;
    reg [7:0] frame_flags;reg [30:0] frame_stream;reg [USER_WIDTH-1:0] frame_user;
    wire frame_matches=frame_active&&replay_length==frame_length&&replay_flags==frame_flags&&
        replay_stream==frame_stream&&replay_user==frame_user;
    wire [31:0] discarded={8'd0,frame_length}-content_length;
    wire padding_good=body_seen&&content_length<={8'd0,frame_length}&&
        (frame_flags[3]?(discarded>=1&&discarded<=256):discarded==0);
    assign init_ready=!rst&&state==IDLE;
    assign init_result_valid=!rst&&state==INIT_RESULT;
    assign init_status=status;assign init_detail=detail;assign init_memory_status=memory_status;
    assign s_ready=!rst&&state==FLOW&&m_ready;
    assign m_valid=!rst&&state==FLOW&&!abort_flow;
    assign request_valid=!rst&&state==SEND;
    assign result_ready=!rst&&state==WAIT;
    assign replay_ready=!rst&&(state==REPLAY_RESULT||state==IDLE&&!init_valid&&!s_valid&&replay_kind!=3);
    assign replay_status=state==REPLAY_RESULT?status:0;
    assign idle=state==IDLE&&!init_valid&&!s_valid&&!replay_valid&&!frame_active;
    task remember_fault(input [7:0] s,input [7:0] d,input [7:0] mem,input [31:0] h2);
        begin
            if(!fault_valid)begin fault_valid<=1;fault_status<=s;fault_detail<=d;
                fault_memory_status<=mem;fault_http2_error<=h2==0?32'd2:h2;end
        end
    endtask
    task command(input [3:0] op,input [31:0] amount);
        begin request_op<=op;request_amount<=amount;state<=SEND;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;operation<=0;status<=0;detail<=0;memory_status<=0;
            request_op<=0;request_keyed<=0;request_maintenance<=0;request_user<=0;request_stream<=0;
            request_generation<=0;request_amount<=0;request_address<=0;request_is_init<=0;request_is_close<=0;
            m_kind<=0;m_data<=0;m_arg0<=0;m_arg1<=0;m_length<=0;m_type<=0;m_flags<=0;m_stream<=0;m_user<=0;
            frame_active<=0;body_seen<=0;frame_length<=0;content_length<=0;frame_flags<=0;frame_stream<=0;frame_user<=0;
            fault_valid<=0;fault_status<=0;fault_detail<=0;fault_memory_status<=0;fault_http2_error<=0;
        end else case(state)
            IDLE:begin
                status<=0;detail<=0;memory_status<=0;
                if(init_valid)begin
                    request_is_init<=init_op!=9;request_is_close<=init_op==9;request_keyed<=0;request_maintenance<=init_maintenance;
                    request_user<=init_user;request_stream<=init_stream;request_generation<=init_generation;request_address<=init_address;
                    operation<=INITIALIZE;command(init_op,init_op==0?32'd65535:32'd0);
                end else if(s_valid&&(s_type!=0||s_kind!=0||admit_data))begin
                    m_kind<=s_kind;m_data<=s_data;m_arg0<=s_arg0;m_arg1<=s_arg1;m_length<=s_length;
                    m_type<=s_type;m_flags<=s_flags;m_stream<=s_stream;m_user<=s_user;
                    if(s_type==0&&s_kind==0&&!fault_valid)begin
                        request_is_init<=0;request_is_close<=0;request_keyed<=1;request_maintenance<=0;request_user<=s_user;
                        request_stream<=s_stream;request_generation<=0;request_address<=0;
                        operation<=DEBIT;command(2,{8'd0,s_length});
                    end else state<=FLOW;
                end else if(replay_valid)begin
                    if(replay_kind==0&&replay_ready)begin
                        frame_active<=1;body_seen<=0;frame_length<=replay_length;frame_flags<=replay_flags;
                        frame_stream<=replay_stream;frame_user<=replay_user;content_length<=0;
                        if(frame_active)remember_fault(8,30,0,2);
                    end else if(replay_kind==1&&replay_ready)begin
                        body_seen<=1;content_length<=replay_arg0;
                        if(!frame_matches||body_seen)remember_fault(8,31,0,2);
                    end else if(replay_kind==3)begin
                        if(!frame_matches||!padding_good||fault_valid)begin
                            status<=8;detail<=32;remember_fault(8,32,0,2);state<=REPLAY_RESULT;
                        end else if(discarded==0)state<=REPLAY_RESULT;
                        else begin
                            request_is_init<=0;request_is_close<=0;request_keyed<=1;request_maintenance<=0;request_user<=frame_user;
                            request_stream<=frame_stream;request_generation<=0;request_address<=0;
                            operation<=RELEASE;command(3,discarded);
                        end
                    end else if(replay_ready)remember_fault(8,33,0,2);
                end
            end
            SEND:if(request_ready)state<=WAIT;
            WAIT:if(result_valid)begin
                status<=result_status;detail<=result_detail;memory_status<=result_memory_status;
                if(result_status!=0||operation==DEBIT&&!result_debit_authorized)begin
                    if(result_status==0)begin status<=8;detail<=34;remember_fault(8,34,0,2);end
                    else remember_fault(result_status,result_detail,result_memory_status,result_http2_error);
                    state<=operation==INITIALIZE||operation==RETIRE_UPDATE?INIT_RESULT:operation==DEBIT?FLOW:REPLAY_RESULT;
                end else case(operation)
                    INITIALIZE:begin
                        if(request_op==0)begin fault_valid<=0;fault_status<=0;fault_detail<=0;fault_memory_status<=0;fault_http2_error<=0;frame_active<=0;body_seen<=0;end
                        if(request_op==9)begin operation<=RETIRE_UPDATE;request_stream<=0;request_generation<=0;request_address<=0;command(4,0);end
                        else state<=INIT_RESULT;
                    end
                    DEBIT:state<=FLOW;
                    RELEASE:begin operation<=UPDATE_STREAM;command(4,0);end
                    UPDATE_STREAM:begin operation<=UPDATE_CONNECTION;request_keyed<=0;request_stream<=0;request_generation<=0;request_address<=0;command(4,0);end
                    RETIRE_UPDATE:state<=INIT_RESULT;
                    default:state<=REPLAY_RESULT;
                endcase
            end
            // The journal's explicit early-abort fence releases tentative
            // semantic events only; no memory command or wire offer is pending.
            FLOW:if(abort_flow||m_ready&&s_valid)state<=IDLE;
            INIT_RESULT:if(init_result_ready)state<=IDLE;
            REPLAY_RESULT:if(replay_valid)begin frame_active<=0;body_seen<=0;state<=IDLE;end
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
