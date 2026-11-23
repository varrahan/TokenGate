`timescale 1ns/1ps
`default_nettype none
// A scoped fatal packet cancels an actually parked return through the real
// freeze, durable send-close and STREAM_CLOSED reservation paths. No invented
// credit/error result or directory retirement; GPU ACK releases its own lease.
module http2_local_return_abort #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(
    input wire clk,rst,input wire req_valid,output wire req_ready,input wire req_authority,
    input wire [USER_WIDTH-1:0] req_user,input wire [30:0] req_stream,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_stream_base,cfg_window_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_stream_bytes,cfg_window_bytes,
    input wire return_pending,
    output wire freeze_valid,input wire freeze_ready,output wire [USER_WIDTH-1:0] freeze_user,
    output wire [30:0] freeze_stream,input wire freeze_drained,freeze_binding_valid,frame_tracking_error,
    input wire [31:0] freeze_generation,input wire [MEMORY_ADDR_WIDTH-1:0] freeze_record_address,
    output wire freeze_release_valid,input wire freeze_release_ready,
    output wire window_valid,input wire window_ready,input wire window_rsp_valid,output wire window_rsp_ready,
    input wire [3:0] window_rsp_op,input wire [USER_WIDTH-1:0] window_rsp_user,input wire [30:0] window_rsp_stream,
    input wire [7:0] window_rsp_status,window_rsp_detail,window_rsp_memory_status,
    input wire window_rsp_binding_valid,window_rsp_send_closed,input wire [31:0] window_rsp_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] window_rsp_record_address,
    output wire [USER_WIDTH-1:0] owned_user,output wire [30:0] owned_stream,
    output wire [MEMORY_ADDR_WIDTH-1:0] owned_context_base,owned_stream_base,owned_window_base,owned_work_floor,
    output wire [MEMORY_ADDR_WIDTH:0] owned_context_bytes,owned_stream_bytes,owned_window_bytes,
    output wire busy,idle,output reg recovery_required,output reg [7:0] status,detail,memory_status
);
    localparam IDLE=0,CHECK=1,FREEZE=2,DRAIN=3,CLOSE_SEND=4,CLOSE_WAIT=5,RELEASE=6,RETIRE=7,FAILED=8;
    reg [3:0] state;reg authority;reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id;
    reg [31:0] generation;reg [MEMORY_ADDR_WIDTH-1:0] address,contexts,streams,windows,work_floor;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,stream_bytes,window_bytes;
    assign req_ready=!rst&&state==IDLE&&!recovery_required;
    assign freeze_valid=!rst&&state==FREEZE;assign freeze_user=owner;assign freeze_stream=stream_id;
    assign freeze_release_valid=!rst&&state==RELEASE;
    assign window_valid=!rst&&state==CLOSE_SEND;assign window_rsp_ready=state==CLOSE_WAIT;
    assign owned_user=owner;assign owned_stream=stream_id;
    assign owned_context_base=contexts;assign owned_context_bytes=context_bytes;
    assign owned_stream_base=streams;assign owned_stream_bytes=stream_bytes;
    assign owned_window_base=windows;assign owned_window_bytes=window_bytes;assign owned_work_floor=work_floor;
    assign busy=state!=IDLE;assign idle=state==IDLE&&!req_valid&&!recovery_required;
    task fail(input [7:0] s,input [7:0] d,input [7:0] mem);
        begin status<=s;detail<=d;memory_status<=mem;recovery_required<=1;state<=FAILED;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;authority<=0;owner<=0;stream_id<=0;generation<=0;address<=0;
            contexts<=0;streams<=0;windows<=0;work_floor<=0;context_bytes<=0;stream_bytes<=0;window_bytes<=0;
            status<=0;detail<=0;memory_status<=0;recovery_required<=0;
        end else case(state)
            IDLE:if(req_valid&&req_ready)begin
                authority<=req_authority;owner<=req_user;stream_id<=req_stream;
                contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;streams<=cfg_stream_base;stream_bytes<=cfg_stream_bytes;
                windows<=cfg_window_base;window_bytes<=cfg_window_bytes;work_floor<=cfg_work_floor;
                generation<=0;address<=0;status<=0;detail<=0;memory_status<=0;state<=CHECK;
            end
            CHECK:if(!authority||stream_id==0||!return_pending)fail(7,1,0);else state<=FREEZE;
            FREEZE:if(frame_tracking_error)fail(7,2,0);else if(freeze_ready)state<=DRAIN;
            DRAIN:if(frame_tracking_error)fail(7,2,0);else if(freeze_drained)begin
                if(!freeze_binding_valid||freeze_generation==0)fail(7,3,0);
                else begin generation<=freeze_generation;address<=freeze_record_address;state<=CLOSE_SEND;end
            end
            CLOSE_SEND:if(window_ready)state<=CLOSE_WAIT;
            CLOSE_WAIT:if(window_rsp_valid)begin
                if(window_rsp_op!=11||window_rsp_user!=owner||window_rsp_stream!=stream_id)fail(7,4,0);
                else if(window_rsp_status!=0)fail(window_rsp_status,window_rsp_detail,window_rsp_memory_status);
                else if(!freeze_drained||frame_tracking_error||!window_rsp_binding_valid||!window_rsp_send_closed||
                    window_rsp_generation!=generation||window_rsp_record_address!=address)fail(7,5,0);
                else state<=RELEASE;
            end
            RELEASE:if(freeze_release_ready)state<=RETIRE;
            RETIRE:if(!return_pending)state<=IDLE;
            FAILED:state<=FAILED;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
