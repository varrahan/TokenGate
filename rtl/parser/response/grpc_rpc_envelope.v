`timescale 1ns/1ps
`default_nettype none
// One accepted GPU descriptor's response envelope. The actual RPC progress
// owner, inverse/serializer, credit service, wire arbiter and LOAD remain live.
// DATA is admitted only after initial HEADERS physically retire and their
// progress commit ACKs. Successful EOS waits for durable trailer intent, wire
// END_STREAM and the final metadata ACK before exposing the GPU terminal.
module grpc_rpc_envelope #(
    parameter integer USER_WIDTH=16
)(
    input wire clk,rst,accept,
    input wire [USER_WIDTH-1:0] accept_user,input wire [30:0] accept_stream,
    input wire rpc_valid,input wire [7:0] rpc_status,input wire rpc_eos,
    input wire [1:0] rpc_format,input wire header_intent,headers_sent,
    input wire framer_result,input wire [7:0] framer_status,
    input wire matching_freeze,input wire wire_fenced,
    output wire data_admit,output wire terminal_admit,output wire private_failed,
    output wire drained,output reg recovery_required,output reg expected_cancelled,
    output reg [7:0] error_status,error_memory_status,
    output wire metadata_req_valid,input wire metadata_req_ready,output wire [2:0] metadata_req_op,
    output wire metadata_private_abort_proof,
    input wire metadata_rsp_valid,output wire metadata_rsp_ready,
    input wire [7:0] metadata_rsp_status,metadata_rsp_memory_status,
    output wire header_req_valid,input wire header_req_ready,
    output wire [1:0] header_req_kind,header_req_encoding,
    output wire [USER_WIDTH-1:0] header_req_user,output wire [30:0] header_req_stream,
    output wire header_abort_valid,input wire header_abort_ready,
    input wire header_result_valid,output wire header_result_ready,
    input wire [7:0] header_result_status,input wire header_result_tx_emitted,
    input wire [1:0] header_result_kind,input wire [6:0] header_result_wire_bytes,
    input wire [USER_WIDTH-1:0] header_result_user,input wire [30:0] header_result_stream,
    output wire header_select,input wire retire,output wire idle,
    output reg [31:0] header_wire_bytes,output reg [1:0] header_frames
);
    localparam IDLE=0,BASE=1,HSTART=2,HWAIT=3,HMSEND=4,HMWAIT=5,
        DATA=6,CANCEL=7,TISEND=8,TIWAIT=9,TSTART=10,TWAIT=11,TMSEND=12,TMWAIT=13,DONE=14;
    reg [3:0] state;reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id;
    reg [1:0] encoding;reg aborted,before_data,abort_offered;
    assign data_admit=state==DATA||state==CANCEL;
    assign terminal_admit=state==DONE;
    assign private_failed=state==DONE&&error_status!=0&&before_data;
    // BASE is not drained: accepting a freeze turns it permanently into CANCEL
    // before announcing drainage, preventing later successful RPC work from
    // starting a header behind the already completed freeze boundary.
    assign drained=state==IDLE||state==DATA||state==CANCEL||state==DONE;
    assign header_select=state==HSTART||state==HWAIT||state==TSTART||state==TWAIT;
    assign header_req_valid=state==HSTART||state==TSTART;
    assign header_req_kind=state==TSTART?2'd1:2'd0;
    assign header_req_encoding=encoding;assign header_req_user=owner;assign header_req_stream=stream_id;
    assign header_abort_valid=(state==HWAIT||state==TWAIT)&&(matching_freeze||abort_offered);
    assign header_result_ready=(state==HWAIT||state==TWAIT)&&(!header_abort_valid||header_abort_ready);
    assign metadata_req_valid=state==HMSEND||state==TISEND||state==TMSEND;
    assign metadata_req_op=state==HMSEND?(aborted?3'd3:3'd0):state==TISEND?3'd1:aborted?3'd4:3'd2;
    assign metadata_private_abort_proof=aborted;
    assign metadata_rsp_ready=state==HMWAIT||state==TIWAIT||state==TMWAIT;
    assign idle=state==IDLE;
    task fail(input [7:0] status,input [7:0] memory_status);
        begin error_status<=status;error_memory_status<=memory_status;recovery_required<=1;state<=DONE;end
    endtask
    wire header_identity=header_result_user==owner&&header_result_stream==stream_id;
    always @(posedge clk)begin
        if(rst)begin state<=IDLE;owner<=0;stream_id<=0;encoding<=0;aborted<=0;before_data<=1;abort_offered<=0;
            recovery_required<=0;expected_cancelled<=0;error_status<=0;error_memory_status<=0;header_wire_bytes<=0;header_frames<=0;end
        else begin
            if(header_abort_valid&&!header_abort_ready)abort_offered<=1;
            if(header_abort_valid&&header_abort_ready)abort_offered<=0;
            case(state)
                IDLE:if(accept)begin
                    owner<=accept_user;stream_id<=accept_stream;before_data<=1;aborted<=0;abort_offered<=0;
                    error_status<=0;error_memory_status<=0;expected_cancelled<=0;header_wire_bytes<=0;header_frames<=0;state<=BASE;
                end
                BASE:if(matching_freeze)state<=CANCEL;
                    else if(rpc_valid)begin
                        if(rpc_status!=0)state<=DONE;
                        else if(rpc_format==1||rpc_format==3)fail(4,0);
                        else begin
                            encoding<=rpc_format==2?2'd1:2'd2;
                            if(header_intent&&!headers_sent)state<=HSTART;
                            else if(headers_sent&&!header_intent)begin before_data<=0;state<=DATA;end
                            else fail(4,0);
                        end
                    end
                HSTART:if(header_req_ready)state<=HWAIT;
                HWAIT:if(header_result_valid&&header_result_ready)begin
                    if(!header_identity||header_result_kind!=0)fail(5,0);
                    else if(header_result_status==0&&header_result_tx_emitted)begin
                        header_wire_bytes<=header_wire_bytes+header_result_wire_bytes;header_frames<=header_frames+1'b1;aborted<=0;state<=HMSEND;end
                    else if(header_result_status==5&&!header_result_tx_emitted&&matching_freeze&&wire_fenced)begin aborted<=1;state<=HMSEND;end
                    else fail(5,0);
                end
                HMSEND:if(metadata_req_ready)state<=HMWAIT;
                HMWAIT:if(metadata_rsp_valid)begin
                    if(metadata_rsp_status!=0)fail(metadata_rsp_status,metadata_rsp_memory_status);
                    else if(aborted)state<=CANCEL;
                    else begin before_data<=0;state<=DATA;end
                end
                DATA:if(framer_result)begin
                    if(framer_status!=0||!rpc_eos)state<=DONE;
                    else if(matching_freeze)begin expected_cancelled<=1;state<=DONE;end
                    else state<=TISEND;
                end
                CANCEL:if(rpc_valid&&rpc_status!=0||framer_result)state<=DONE;
                TISEND:if(metadata_req_ready)state<=TIWAIT;
                TIWAIT:if(metadata_rsp_valid)begin
                    if(metadata_rsp_status!=0)fail(metadata_rsp_status,metadata_rsp_memory_status);else state<=TSTART;
                end
                TSTART:if(header_req_ready)state<=TWAIT;
                TWAIT:if(header_result_valid&&header_result_ready)begin
                    if(!header_identity||header_result_kind!=1)fail(5,0);
                    else if(header_result_status==0&&header_result_tx_emitted)begin
                        header_wire_bytes<=header_wire_bytes+header_result_wire_bytes;header_frames<=header_frames+1'b1;aborted<=0;state<=TMSEND;end
                    else if(header_result_status==5&&!header_result_tx_emitted&&matching_freeze&&wire_fenced)begin
                        aborted<=1;expected_cancelled<=1;state<=TMSEND;end
                    else fail(5,0);
                end
                TMSEND:if(metadata_req_ready)state<=TMWAIT;
                TMWAIT:if(metadata_rsp_valid)begin
                    if(metadata_rsp_status!=0)fail(metadata_rsp_status,metadata_rsp_memory_status);else state<=DONE;
                end
                DONE:if(retire)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
