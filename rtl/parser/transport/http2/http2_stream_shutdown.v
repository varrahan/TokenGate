`timescale 1ns/1ps
`default_nettype none
// Committed server-side RST/GOAWAY owner. There are no local memory or shadow
// directory entries. All mutations/results come from the actual shared owners.
// The parent retains its committed admission fence through response retirement.
module http2_stream_shutdown #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,rst,input wire req_valid,output wire req_ready,
    input wire req_goaway,input wire [USER_WIDTH-1:0] req_user,
    input wire [30:0] req_stream,input wire [31:0] req_arg0,req_arg1,
    input wire history_fence,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_stream_base,cfg_window_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_stream_bytes,cfg_window_bytes,
    output wire rsp_valid,input wire rsp_ready,
    output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,
    output reg rsp_connection_error,output reg [31:0] rsp_http2_error,
    output wire [USER_WIDTH-1:0] rsp_user,output wire [30:0] rsp_stream,
    output reg recovery_required,output wire busy,output wire idle,
    output reg reset_processed,output reg [31:0] resets_processed,goaways_processed,
    input wire return_key_valid,return_scope_match,input wire [USER_WIDTH-1:0] return_user,input wire [30:0] return_stream,
    output wire freeze_valid,input wire freeze_ready,output wire [USER_WIDTH-1:0] freeze_user,
    output wire [30:0] freeze_stream,input wire freeze_drained,input wire frame_tracking_error,
    output wire freeze_release_valid,input wire freeze_release_ready,
    output wire close_valid,input wire close_ready,output wire [USER_WIDTH-1:0] close_user,
    output wire [30:0] close_stream,
    input wire close_rsp_valid,output wire close_rsp_ready,
    input wire [3:0] close_rsp_op,input wire [USER_WIDTH-1:0] close_rsp_user,input wire [30:0] close_rsp_stream,
    input wire [7:0] close_rsp_status,close_rsp_detail,close_rsp_memory_status,
    input wire close_rsp_connection_error,input wire [31:0] close_rsp_http2_error,
    input wire close_rsp_binding_valid,close_rsp_send_closed,input wire [31:0] close_rsp_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] close_rsp_address,
    output wire directory_valid,input wire directory_ready,
    output wire [31:0] directory_generation,output wire [MEMORY_ADDR_WIDTH-1:0] directory_address,
    input wire directory_rsp_valid,output wire directory_rsp_ready,
    input wire [7:0] directory_rsp_status,directory_rsp_detail,directory_rsp_memory_status,
    input wire [2:0] directory_rsp_op,input wire [USER_WIDTH-1:0] directory_rsp_user,
    input wire [30:0] directory_rsp_stream,
    input wire [31:0] directory_rsp_generation,input wire [MEMORY_ADDR_WIDTH-1:0] directory_rsp_address,
    output wire classify_valid,input wire classify_ready,input wire classify_rsp_valid,
    output wire classify_rsp_ready,input wire [7:0] classify_rsp_status,classify_rsp_detail,classify_rsp_memory_status,
    input wire classify_rsp_closed,input wire [USER_WIDTH-1:0] classify_rsp_user,input wire [30:0] classify_rsp_stream,
    output wire peer_valid,input wire peer_ready,output wire [30:0] peer_last_stream,
    output wire [31:0] peer_error,input wire peer_rsp_valid,output wire peer_rsp_ready,
    input wire [7:0] peer_rsp_status,peer_rsp_detail,peer_rsp_memory_status,
    input wire peer_rsp_connection_error,input wire [31:0] peer_rsp_http2_error,
    input wire [3:0] peer_rsp_op,input wire [USER_WIDTH-1:0] peer_rsp_user,
    output wire [MEMORY_ADDR_WIDTH-1:0] owned_context_base,owned_stream_base,owned_window_base,owned_work_floor,
    output wire [MEMORY_ADDR_WIDTH:0] owned_context_bytes,owned_stream_bytes,owned_window_bytes
);
    localparam IDLE=0,CHECK=1,FREEZE=2,DRAIN=3,CLOSE_SEND=4,CLOSE_WAIT=5,
        RELEASE=6,RETIRE=7,DIRECTORY_SEND=8,DIRECTORY_WAIT=9,
        CLASSIFY_SEND=10,CLASSIFY_WAIT=11,PEER_SEND=12,PEER_WAIT=13,RESULT=14;
    reg [3:0] state;reg goaway,binding,missing,fence_lost;
    reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id;reg [31:0] arg0,arg1,generation;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,streams,windows,work_floor,address;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,stream_bytes,window_bytes;
    assign req_ready=!rst&&state==IDLE&&!recovery_required;
    assign rsp_valid=state==RESULT;assign rsp_user=owner;assign rsp_stream=stream_id;
    assign busy=state!=IDLE;assign idle=state==IDLE&&!req_valid&&!recovery_required;
    wire fence_bad=fence_lost||!history_fence;
    assign freeze_valid=!rst&&state==FREEZE;assign freeze_user=owner;assign freeze_stream=stream_id;
    assign freeze_release_valid=!rst&&state==RELEASE;
    assign close_valid=!rst&&state==CLOSE_SEND;assign close_rsp_ready=state==CLOSE_WAIT;
    assign close_user=owner;assign close_stream=stream_id;
    assign directory_valid=!rst&&state==DIRECTORY_SEND;assign directory_rsp_ready=state==DIRECTORY_WAIT;
    assign directory_generation=generation;assign directory_address=address;
    assign classify_valid=!rst&&state==CLASSIFY_SEND;assign classify_rsp_ready=state==CLASSIFY_WAIT;
    assign peer_valid=!rst&&state==PEER_SEND;assign peer_rsp_ready=state==PEER_WAIT;
    assign peer_last_stream=arg0[30:0];assign peer_error=arg1;
    assign owned_context_base=contexts;assign owned_context_bytes=context_bytes;
    assign owned_stream_base=streams;assign owned_stream_bytes=stream_bytes;
    assign owned_window_base=windows;assign owned_window_bytes=window_bytes;assign owned_work_floor=work_floor;
    wire matching_return=return_key_valid&&return_scope_match&&return_user==owner&&return_stream==stream_id;
    task fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status,
        input connection_error,input [31:0] http2_error,input quarantine);
        begin rsp_status<=status;rsp_detail<=detail;rsp_memory_status<=memory_status;
            rsp_connection_error<=connection_error;rsp_http2_error<=http2_error;
            if(quarantine)recovery_required<=1;state<=RESULT;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;goaway<=0;binding<=0;missing<=0;fence_lost<=0;owner<=0;stream_id<=0;arg0<=0;arg1<=0;generation<=0;address<=0;
            contexts<=0;streams<=0;windows<=0;work_floor<=0;context_bytes<=0;stream_bytes<=0;window_bytes<=0;
            rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;
            recovery_required<=0;reset_processed<=0;resets_processed<=0;goaways_processed<=0;
        end else begin
            reset_processed<=0;
            if(state!=IDLE&&state!=RESULT&&!history_fence)fence_lost<=1;
            // An already offered request is an owned promise even if the outer
            // fence is lost. Drain it and report quarantine at its response.
            if(fence_bad&&(state==CHECK||state==DRAIN||state==RETIRE))
                fail(7,1,0,1,2,1);
            else case(state)
                IDLE:if(req_valid&&req_ready)begin
                    owner<=req_user;stream_id<=req_stream;goaway<=req_goaway;arg0<=req_arg0;arg1<=req_arg1;
                    contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;streams<=cfg_stream_base;stream_bytes<=cfg_stream_bytes;
                    windows<=cfg_window_base;window_bytes<=cfg_window_bytes;work_floor<=cfg_work_floor;
                    generation<=0;address<=0;binding<=0;missing<=0;fence_lost<=!history_fence;
                    rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;state<=CHECK;
                end
                CHECK:if(fence_lost||!history_fence)fail(7,1,0,1,2,1);
                    else if(goaway)begin
                        if(stream_id!=0)fail(4,1,0,1,1,0);
                        else state<=PEER_SEND;
                    end else if(stream_id==0)fail(4,1,0,1,1,0);else state<=FREEZE;
                FREEZE:if(frame_tracking_error)fail(7,2,0,1,2,1);else if(freeze_ready)state<=DRAIN;
                DRAIN:if(frame_tracking_error)fail(7,2,0,1,2,1);else if(freeze_drained)state<=CLOSE_SEND;
                CLOSE_SEND:if(close_ready)state<=CLOSE_WAIT;
                CLOSE_WAIT:if(close_rsp_valid)begin
                    if(close_rsp_op!=10||close_rsp_user!=owner||close_rsp_stream!=stream_id)fail(7,3,0,1,2,1);
                    else if(close_rsp_status==0)begin
                        if(fence_bad||!freeze_drained||frame_tracking_error||!close_rsp_binding_valid||!close_rsp_send_closed||close_rsp_generation==0)
                            fail(7,4,0,1,2,1);
                        else begin
                            binding<=1;generation<=close_rsp_generation;address<=close_rsp_address;
                            // Processing completes at this durable actual close ACK.
                            // Matching positive promises were drained before it, and
                            // freeze has prevented later dispatch since acceptance.
                            reset_processed<=1;resets_processed<=resets_processed+1'b1;state<=RELEASE;
                        end
                    end else if(close_rsp_status==3&&close_rsp_detail==10&&close_rsp_memory_status==0)begin missing<=1;state<=RELEASE;end
                    else fail(close_rsp_status,close_rsp_detail,close_rsp_memory_status,1,
                        close_rsp_http2_error!=0?close_rsp_http2_error:32'd2,1);
                end
                RELEASE:if(freeze_release_ready)begin
                    if(fence_bad)fail(7,1,0,1,2,1);else state<=missing?CLASSIFY_SEND:RETIRE;
                end
                RETIRE:if(!matching_return)state<=DIRECTORY_SEND;
                DIRECTORY_SEND:if(directory_ready)state<=DIRECTORY_WAIT;
                DIRECTORY_WAIT:if(directory_rsp_valid)begin
                    if(directory_rsp_op!=3||directory_rsp_user!=owner||directory_rsp_stream!=stream_id)fail(7,5,0,1,2,1);
                    else if(directory_rsp_status!=0)fail(directory_rsp_status,directory_rsp_detail,directory_rsp_memory_status,1,2,1);
                    else if(directory_rsp_generation!=generation||directory_rsp_address!=address)fail(7,5,0,1,2,1);
                    else if(fence_lost||!history_fence)fail(7,1,0,1,2,1);else state<=RESULT;
                end
                CLASSIFY_SEND:if(classify_ready)state<=CLASSIFY_WAIT;
                CLASSIFY_WAIT:if(classify_rsp_valid)begin
                    if(fence_bad)fail(7,1,0,1,2,1);
                    else if(classify_rsp_user!=owner||classify_rsp_stream!=stream_id)fail(7,6,0,1,2,1);
                    else if(classify_rsp_status!=0)fail(classify_rsp_status,classify_rsp_detail,classify_rsp_memory_status,1,2,1);
                    else if(!classify_rsp_closed)fail(4,2,0,1,1,0);
                    else begin reset_processed<=1;resets_processed<=resets_processed+1'b1;state<=RESULT;end
                end
                PEER_SEND:if(peer_ready)state<=PEER_WAIT;
                PEER_WAIT:if(peer_rsp_valid)begin
                    if(peer_rsp_op!=7||peer_rsp_user!=owner)fail(7,7,0,1,2,1);
                    else if(peer_rsp_status!=0)fail(peer_rsp_status,peer_rsp_detail,peer_rsp_memory_status,
                        peer_rsp_connection_error,peer_rsp_http2_error,peer_rsp_memory_status!=0||peer_rsp_status==6);
                    else if(fence_lost||!history_fence)fail(7,1,0,1,2,1);
                    else begin goaways_processed<=goaways_processed+1'b1;state<=RESULT;end
                end
                RESULT:if(rsp_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
