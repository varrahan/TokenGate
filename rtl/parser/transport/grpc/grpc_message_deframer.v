`timescale 1ns/1ps
`default_nettype none
// One admitted gRPC stream segment. The stream scheduler restores/saves the
// 256-bit progress record; frame and packet boundaries are not message ends.
// Staging is append-only until the owner retires/reclaims the allocation.
module grpc_message_deframer #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,input wire start_valid,output wire start_ready,
    input wire [USER_WIDTH-1:0] start_user,input wire [30:0] start_stream,
    input wire [USER_WIDTH-1:0] start_application,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_buffer_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_buffer_bytes,input wire [31:0] cfg_message_limit,
    input wire cfg_unsupported_encoding,input wire [255:0] cfg_state,
    input wire s_valid,output wire s_ready,input wire [1:0] s_kind,input wire [7:0] s_data,
    input wire [USER_WIDTH-1:0] s_user,input wire [30:0] s_stream,
    output wire message_valid,input wire message_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] message_base,
    output wire [31:0] message_bytes,message_ordinal,
    output wire [USER_WIDTH-1:0] message_user,message_application,output wire [30:0] message_stream,
    input wire finish_valid,output wire result_valid,input wire result_ready,
    output wire [255:0] result_state,output reg [7:0] result_status,result_detail,result_memory_status,
    output wire [USER_WIDTH-1:0] result_user,output wire [30:0] result_stream,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,CHECK=1,RUN=2,WRITE_REQ=3,WRITE_WAIT=4,MESSAGE=5,DRAIN=6,RESULT=7,LENGTH_CHECK=8;
    reg [3:0] state;
    reg [MEMORY_ADDR_WIDTH-1:0] buffer_base;
    reg [MEMORY_ADDR_WIDTH:0] buffer_bytes;
    reg [31:0] message_limit,used,message_offset,length_value,payload_received,ordinal;
    reg [2:0] prefix_count;
    reg ended,ordinal_exhausted,unsupported_encoding,bad_reserved;
    reg [7:0] byte_value;
    reg [USER_WIDTH-1:0] context_id,application_id;
    reg [30:0] stream_id;
    wire [63:0] allocation_end={1'b0,buffer_base}+{1'b0,buffer_bytes};
    wire [63:0] payload_end={32'd0,message_offset}+{32'd0,length_value};
    wire config_good=stream_id!=0&&allocation_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&!bad_reserved&&
        prefix_count<=5&&used<=buffer_bytes&&message_offset<=used&&
        (prefix_count==5?(length_value!=0&&length_value<=message_limit&&payload_end<=buffer_bytes&&payload_received<length_value&&
            {32'd0,used}=={32'd0,message_offset}+payload_received):
            (payload_received==0&&message_offset==used&&(prefix_count!=0||length_value==0)))&&
        (!ended||prefix_count==0)&&(!ordinal_exhausted||ordinal==32'hffffffff&&prefix_count==0);
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire [63:0] write_address={1'b0,buffer_base}+{32'd0,used};
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==WRITE_REQ),.req_ready(slot_ready),.req_write(1'b1),
        .req_addr(write_address[MEMORY_ADDR_WIDTH-1:0]),.req_bytes(4'd1),.req_data({64'd0,byte_value}),
        .result_valid(slot_valid),.result_ready(state==WRITE_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign start_ready=!rst&&state==IDLE;
    assign s_ready=!rst&&(state==RUN||state==DRAIN);
    assign message_valid=state==MESSAGE;
    assign message_base=length_value==0?{MEMORY_ADDR_WIDTH{1'b0}}:buffer_base+message_offset;
    assign message_bytes=length_value;assign message_ordinal=ordinal;
    assign message_user=context_id;assign message_application=application_id;assign message_stream=stream_id;
    assign result_valid=state==RESULT;assign result_user=context_id;assign result_stream=stream_id;
    assign result_state=result_status!=0?256'd0:{64'd0,27'd0,ordinal_exhausted,ended,prefix_count,ordinal,payload_received,length_value,message_offset,used};
    assign idle=state==IDLE&&slot_idle&&!(start_valid&&start_ready);
    task fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status);
        begin result_status<=status;result_detail<=detail;result_memory_status<=memory_status;state<=DRAIN;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;buffer_base<=0;buffer_bytes<=0;message_limit<=0;used<=0;message_offset<=0;length_value<=0;payload_received<=0;ordinal<=0;
            prefix_count<=0;ended<=0;ordinal_exhausted<=0;unsupported_encoding<=0;bad_reserved<=0;byte_value<=0;context_id<=0;application_id<=0;stream_id<=0;
            result_status<=0;result_detail<=0;result_memory_status<=0;
        end else case(state)
            IDLE:if(start_valid&&start_ready)begin
                context_id<=start_user;application_id<=start_application;stream_id<=start_stream;
                buffer_base<=cfg_buffer_base;buffer_bytes<=cfg_buffer_bytes;message_limit<=cfg_message_limit;unsupported_encoding<=cfg_unsupported_encoding;
                {ordinal_exhausted,ended,prefix_count,ordinal,payload_received,length_value,message_offset,used}<=cfg_state[164:0];
                bad_reserved<=cfg_state[255:165]!=0;
                result_status<=0;result_detail<=0;result_memory_status<=0;state<=CHECK;
            end
            CHECK:if(!config_good)fail(13,1,0);else state<=RUN;
            RUN:begin
                if(s_valid&&s_ready)begin
                    if(s_user!=context_id||s_stream!=stream_id)fail(13,2,0);
                    else if(s_kind>1)fail(13,10,0);
                    else if(ended)fail(13,8,0);
                    else if(s_kind==1)begin
                        if(prefix_count!=0)fail(13,4,0);else ended<=1;
                    end else if(prefix_count==0)begin
                        if(ordinal_exhausted)fail(8,9,0);
                        else if(s_data>1)fail(13,7,0);
                        else if(s_data==1)fail(unsupported_encoding?8'd12:8'd13,6,0);
                        else begin prefix_count<=1;length_value<=0;payload_received<=0;message_offset<=used;end
                    end else if(prefix_count<5)begin
                        length_value<={length_value[23:0],s_data};prefix_count<=prefix_count+1'b1;
                        if(prefix_count==4)state<=LENGTH_CHECK;
                    end else begin byte_value<=s_data;state<=WRITE_REQ;end
                end else if(finish_valid)state<=RESULT;
            end
            LENGTH_CHECK:begin
                if(length_value>message_limit||payload_end>buffer_bytes)fail(8,3,0);
                else if(length_value==0)state<=MESSAGE;
                else state<=RUN;
            end
            WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
            WRITE_WAIT:if(slot_valid)begin
                if(slot_status!=0)fail(13,5,slot_status);
                else begin
                    used<=used+1'b1;payload_received<=payload_received+1'b1;
                    state<=payload_received+1'b1==length_value?MESSAGE:RUN;
                end
            end
            MESSAGE:if(message_ready)begin
                prefix_count<=0;length_value<=0;payload_received<=0;message_offset<=used;
                if(ordinal==32'hffffffff)ordinal_exhausted<=1;else ordinal<=ordinal+1'b1;
                state<=RUN;
            end
            DRAIN:if(finish_valid&&slot_idle)state<=RESULT;
            RESULT:if(result_ready)state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
