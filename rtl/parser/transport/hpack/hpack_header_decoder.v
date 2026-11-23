`timescale 1ns/1ps
`default_nettype none
// Complete HPACK header-block decoding. The caller reassembles CONTINUATION
// and supplies a byte count plus saved per-connection dynamic-table state.
// A header leases scratch pointers until header_ready. Headers are tentative
// until successful completion. Any failure invalidates the compression context.
module hpack_header_decoder #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [31:0] start_bytes,input wire [USER_WIDTH-1:0] start_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_table_base,cfg_scratch_base,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_table_bytes,cfg_scratch_bytes,
    input wire [31:0] cfg_maximum,cfg_allowed_maximum,cfg_used,cfg_entries,cfg_header_list_limit,
    input wire cfg_required_update,input wire [31:0] cfg_required_maximum,
    input wire [7:0] s_data,input wire s_valid,output wire s_ready,input wire [USER_WIDTH-1:0] s_user,
    output wire header_valid,input wire header_ready,output wire [MEMORY_ADDR_WIDTH-1:0] header_name_base,header_value_base,
    output wire [31:0] header_name_bytes,header_value_bytes,output wire [1:0] header_representation,output wire [USER_WIDTH-1:0] header_user,
    output wire completion_valid,input wire completion_ready,output reg [7:0] completion_status,completion_detail,completion_aux,
    output wire [31:0] completion_maximum,completion_used,completion_entries,completion_headers,completion_list_bytes,
    output wire [USER_WIDTH-1:0] completion_user,
    output wire [1:0] mem_valid,input wire [1:0] mem_ready,output wire [1:0] mem_write,
    output wire [2*MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [7:0] mem_bytes,output wire [143:0] mem_data,
    input wire [1:0] mem_rsp_valid,output wire [1:0] mem_rsp_ready,input wire [143:0] mem_rsp_data,input wire [15:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,CHECK=1,REP=2,INTEGER_WAIT=3,SELECT_INDEX=4,STATIC_REQ=5,STATIC_WAIT=6,DYNAMIC_REQ=7,DYNAMIC_WAIT=8,
        COPY_SETUP=9,COPY_READ=10,COPY_READ_WAIT=11,COPY_WRITE=12,COPY_WRITE_WAIT=13,COPY_NEXT=14,RELEASE_LOOKUP=15,
        STRING_START=16,STRING_RUN=17,STRING_WRITE=18,STRING_WRITE_WAIT=19,STRING_RESULT=20,FIELD_DONE=21,
        INSERT_REQ=22,INSERT_WAIT=23,HEADER=24,RESIZE_REQ=25,RESIZE_WAIT=26,FINISH=27,ABORT=28,RESET_CHILDREN=29,RESULT=30;
    reg [4:0] state;
    reg [MEMORY_ADDR_WIDTH-1:0] table_base,scratch_base,copy_name_source,copy_value_source;
    reg [MEMORY_ADDR_WIDTH:0] table_bytes,scratch_bytes,scratch_position;
    reg [31:0] maximum,allowed_maximum,used,entries,list_limit,required_maximum,block_remaining;
    reg [31:0] name_size,value_size,index_value,resize_value,headers_seen,list_bytes,copy_remaining,copy_offset;
    reg [1:0] representation;
    reg [3:0] prefix_bits;
    reg is_update,need_update,seen_field,copy_static,copy_field,dynamic_lease,string_field;
    reg [9:0] static_name_source,static_value_source;
    reg [71:0] transfer_data;
    reg [USER_WIDTH-1:0] context_id;
    wire child_reset=rst||state==RESET_CHILDREN;
    wire [63:0] table_end={1'b0,table_base}+{1'b0,table_bytes};
    wire [63:0] scratch_end={1'b0,scratch_base}+{1'b0,scratch_bytes};
    wire config_good=table_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&scratch_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (table_end<=scratch_base||scratch_end<=table_base)&&maximum<=table_bytes&&allowed_maximum<=table_bytes&&
        used<=maximum&&entries<=(used>>5)&&((used==0)==(entries==0));
    wire [63:0] inflated_size=64'd32+{32'd0,name_size}+{32'd0,value_size};
    wire [63:0] next_list_size={32'd0,list_bytes}+inflated_size;
    wire [63:0] copy_end={1'b0,scratch_position}+{32'd0,copy_remaining};
    wire [3:0] copy_chunk=copy_static?4'd1:copy_remaining>=8?4'd8:copy_remaining[3:0];
    wire [MEMORY_ADDR_WIDTH-1:0] copy_source=(copy_field?copy_value_source:copy_name_source)+copy_offset;
    wire [9:0] static_source=(copy_field?static_value_source:static_name_source)+copy_offset;
    wire [MEMORY_ADDR_WIDTH-1:0] write_address=scratch_base+scratch_position;
    wire int_ready,int_valid,int_last;wire [31:0] int_value;wire [7:0] int_status;
    wire int_input=state==REP||state==INTEGER_WAIT;
    wire [3:0] live_prefix=s_data[7]?4'd7:s_data[6]?4'd6:s_data[5]?4'd5:4'd4;
    hpack_integer_decoder #(.USER_WIDTH(USER_WIDTH)) representation_integer(
        .clk(clk),.rst(child_reset),.s_data(s_data),.s_prefix_bits(state==REP?live_prefix:prefix_bits),
        .s_valid(s_valid&&int_input&&block_remaining!=0),.s_ready(int_ready),.s_block_last(block_remaining==1),.s_user(s_user),
        .rsp_valid(int_valid),.rsp_ready(state==INTEGER_WAIT||state==ABORT),.rsp_value(int_value),.rsp_status(int_status),.rsp_block_last(int_last),.rsp_user(),.idle());
    wire str_ready,str_valid,str_keep,str_last,str_result;wire [7:0] str_data,str_status,str_detail;
    wire str_output_ready=state==ABORT||state==STRING_RUN;
    hpack_string_decoder #(.USER_WIDTH(USER_WIDTH)) strings(
        .clk(clk),.rst(child_reset),.s_data(s_data),.s_valid(s_valid&&state==STRING_RUN&&block_remaining!=0),.s_ready(str_ready),
        .s_block_last(block_remaining==1),.s_user(s_user),.m_data(str_data),.m_keep(str_keep),.m_valid(str_valid),.m_ready(str_output_ready),.m_last(str_last),.m_user(),
        .rsp_valid(str_result),.rsp_ready(state==STRING_RUN||state==STRING_RESULT||state==ABORT),.rsp_status(str_status),.rsp_detail(str_detail),
        .rsp_block_last(),.rsp_encoded_bytes(),.rsp_decoded_bytes(),.rsp_user(),.idle());
    wire static_req_ready,static_valid,static_invalid,static_read_ready,static_byte_valid,static_byte_invalid;
    wire [9:0] static_name_offset,static_value_offset;wire [4:0] static_name_bytes,static_value_bytes;wire [7:0] static_byte_data;
    hpack_static_table #(.USER_WIDTH(USER_WIDTH)) static_table(
        .clk(clk),.rst(child_reset),.req_valid(state==STATIC_REQ),.req_ready(static_req_ready),.req_index(index_value[6:0]),.req_user(context_id),
        .rsp_valid(static_valid),.rsp_ready(state==STATIC_WAIT||state==ABORT),.rsp_invalid(static_invalid),
        .rsp_name_offset(static_name_offset),.rsp_value_offset(static_value_offset),.rsp_name_bytes(static_name_bytes),.rsp_value_bytes(static_value_bytes),.rsp_user(),
        .read_valid(state==COPY_READ&&copy_static),.read_ready(static_read_ready),.read_offset(static_source),
        .byte_valid(static_byte_valid),.byte_ready((state==COPY_READ_WAIT&&copy_static)||state==ABORT),.byte_data(static_byte_data),.byte_invalid(static_byte_invalid));
    wire dt_ready,dt_valid,dt_idle;wire [7:0] dt_status,dt_memory_status;
    wire [31:0] dt_maximum,dt_used,dt_entries,dt_name_size,dt_value_size;wire [MEMORY_ADDR_WIDTH-1:0] dt_name_base,dt_value_base;
    wire dt_response_ready=state==RELEASE_LOOKUP||state==INSERT_WAIT||state==RESIZE_WAIT||state==ABORT;
    hpack_dynamic_table #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.USER_WIDTH(USER_WIDTH)) dynamic_table(
        .clk(clk),.rst(child_reset),.req_valid(state==DYNAMIC_REQ||state==INSERT_REQ||state==RESIZE_REQ),.req_ready(dt_ready),
        .req_op(state==INSERT_REQ?2'd1:state==RESIZE_REQ?2'd2:2'd0),.req_argument(state==RESIZE_REQ?resize_value:index_value-32'd62),
        .req_name_bytes(name_size),.req_value_bytes(value_size),.req_source_base(scratch_base),.req_table_base(table_base),.req_table_bytes(table_bytes),
        .req_maximum(maximum),.req_allowed_maximum(allowed_maximum),.req_used(used),.req_entries(entries),.req_user(context_id),
        .rsp_valid(dt_valid),.rsp_ready(dt_response_ready),.rsp_status(dt_status),.rsp_memory_status(dt_memory_status),
        .rsp_maximum(dt_maximum),.rsp_used(dt_used),.rsp_entries(dt_entries),.rsp_lookup_valid(),.rsp_inserted(),
        .rsp_name_base(dt_name_base),.rsp_value_base(dt_value_base),.rsp_name_bytes(dt_name_size),.rsp_value_bytes(dt_value_size),.rsp_user(),
        .mem_valid(mem_valid[1]),.mem_ready(mem_ready[1]),.mem_write(mem_write[1]),.mem_addr(mem_addr[MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[4+:4]),.mem_data(mem_data[72+:72]),
        .mem_rsp_valid(mem_rsp_valid[1]),.mem_rsp_ready(mem_rsp_ready[1]),.mem_rsp_data(mem_rsp_data[72+:72]),.mem_rsp_status(mem_rsp_status[8+:8]),.idle(dt_idle));
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire slot_request=(state==COPY_READ&&!copy_static)||state==COPY_WRITE||state==STRING_WRITE;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(child_reset),.req_valid(slot_request),.req_ready(slot_ready),.req_write(state!=COPY_READ),
        .req_addr(state==COPY_READ?copy_source:write_address),.req_bytes(state==STRING_WRITE?4'd1:copy_chunk),.req_data(transfer_data),
        .result_valid(slot_valid),.result_ready((state==COPY_READ_WAIT&&!copy_static)||state==COPY_WRITE_WAIT||state==STRING_WRITE_WAIT||state==ABORT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid[0]),.mem_ready(mem_ready[0]),.mem_write(mem_write[0]),.mem_addr(mem_addr[0+:MEMORY_ADDR_WIDTH]),.mem_bytes(mem_bytes[0+:4]),.mem_data(mem_data[0+:72]),
        .mem_rsp_valid(mem_rsp_valid[0]),.mem_rsp_ready(mem_rsp_ready[0]),.mem_rsp_data(mem_rsp_data[0+:72]),.mem_rsp_status(mem_rsp_status[0+:8]),.idle(slot_idle));
    assign start_ready=!rst&&state==IDLE;
    assign s_ready=!rst&&block_remaining!=0&&(state==ABORT?1'b1:int_input?int_ready:state==STRING_RUN?str_ready:1'b0);
    assign header_valid=state==HEADER;
    assign header_name_base=name_size==0?{MEMORY_ADDR_WIDTH{1'b0}}:scratch_base;
    assign header_value_base=value_size==0?{MEMORY_ADDR_WIDTH{1'b0}}:scratch_base+name_size;
    assign header_name_bytes=name_size;assign header_value_bytes=value_size;
    assign header_representation=representation;assign header_user=context_id;
    assign completion_valid=state==RESULT;
    assign completion_maximum=completion_status==0?maximum:32'd0;
    assign completion_used=completion_status==0?used:32'd0;
    assign completion_entries=completion_status==0?entries:32'd0;
    assign completion_headers=completion_status==0?headers_seen:32'd0;
    assign completion_list_bytes=completion_status==0?list_bytes:32'd0;
    assign completion_user=context_id;
    assign idle=state==IDLE&&!(start_valid&&start_ready);
    task fail(input [7:0] status,input [7:0] detail,input [7:0] aux);
        begin completion_status<=status;completion_detail<=detail;completion_aux<=aux;state<=ABORT;end
    endtask
    task after_copy;
        begin if(representation==0)state<=FIELD_DONE;else begin string_field<=1;state<=STRING_START;end end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;table_base<=0;scratch_base<=0;table_bytes<=0;scratch_bytes<=0;scratch_position<=0;
            maximum<=0;allowed_maximum<=0;used<=0;entries<=0;list_limit<=0;required_maximum<=0;block_remaining<=0;
            name_size<=0;value_size<=0;index_value<=0;resize_value<=0;headers_seen<=0;list_bytes<=0;copy_remaining<=0;copy_offset<=0;
            representation<=0;prefix_bits<=0;is_update<=0;need_update<=0;seen_field<=0;copy_static<=0;copy_field<=0;dynamic_lease<=0;string_field<=0;
            copy_name_source<=0;copy_value_source<=0;static_name_source<=0;static_value_source<=0;transfer_data<=0;context_id<=0;
            completion_status<=0;completion_detail<=0;completion_aux<=0;
        end else begin
            if(s_valid&&s_ready)block_remaining<=block_remaining-1'b1;
            case(state)
                IDLE:if(start_valid&&start_ready)begin
                    table_base<=cfg_table_base;table_bytes<=cfg_table_bytes;scratch_base<=cfg_scratch_base;scratch_bytes<=cfg_scratch_bytes;
                    maximum<=cfg_maximum;allowed_maximum<=cfg_allowed_maximum;used<=cfg_used;entries<=cfg_entries;list_limit<=cfg_header_list_limit;
                    need_update<=cfg_required_update||cfg_maximum>cfg_allowed_maximum;
                    required_maximum<=cfg_required_update&&cfg_required_maximum<cfg_allowed_maximum?cfg_required_maximum:cfg_allowed_maximum;
                    block_remaining<=start_bytes;context_id<=start_user;headers_seen<=0;list_bytes<=0;seen_field<=0;dynamic_lease<=0;
                    completion_status<=0;completion_detail<=0;completion_aux<=0;state<=CHECK;
                end
                CHECK:if(!config_good)fail(1,0,0);else state<=block_remaining==0?FINISH:REP;
                REP:if(s_valid&&s_ready)begin
                    prefix_bits<=live_prefix;is_update<=!s_data[7]&&!s_data[6]&&s_data[5];
                    representation<=s_data[7]?2'd0:s_data[6]?2'd1:s_data[4]?2'd3:2'd2;
                    name_size<=0;value_size<=0;scratch_position<=0;state<=INTEGER_WAIT;
                    if(!s_data[7]&&!s_data[6]&&s_data[5])begin if(seen_field)fail(9,1,0);end
                    else begin seen_field<=1;if(need_update)fail(10,0,0);end
                end
                INTEGER_WAIT:if(int_valid)begin
                    if(int_status!=0)fail(2,int_status,0);
                    else if(is_update)begin
                        if(need_update&&int_value>required_maximum)fail(9,2,0);
                        else begin resize_value<=int_value;state<=RESIZE_REQ;end
                    end else if(int_value==0)begin
                        if(representation==0)fail(3,0,0);
                        else begin string_field<=0;state<=STRING_START;end
                    end else begin index_value<=int_value;state<=SELECT_INDEX;end
                end
                SELECT_INDEX:state<=index_value<=61?STATIC_REQ:DYNAMIC_REQ;
                STATIC_REQ:if(static_req_ready)state<=STATIC_WAIT;
                STATIC_WAIT:if(static_valid)begin
                    if(static_invalid)fail(3,8'hfe,0);
                    else begin
                        name_size<={27'd0,static_name_bytes};value_size<=representation==0?{27'd0,static_value_bytes}:32'd0;
                        static_name_source<=static_name_offset;static_value_source<=static_value_offset;
                        copy_field<=0;copy_static<=1;copy_remaining<={27'd0,static_name_bytes};copy_offset<=0;state<=COPY_SETUP;
                    end
                end
                DYNAMIC_REQ:if(dt_ready)state<=DYNAMIC_WAIT;
                DYNAMIC_WAIT:if(dt_valid)begin
                    if(dt_status!=0)fail(3,dt_status,dt_memory_status);
                    else begin
                        dynamic_lease<=1;copy_name_source<=dt_name_base;copy_value_source<=dt_value_base;
                        name_size<=dt_name_size;value_size<=representation==0?dt_value_size:32'd0;
                        copy_field<=0;copy_static<=0;copy_remaining<=dt_name_size;copy_offset<=0;state<=COPY_SETUP;
                    end
                end
                COPY_SETUP:if(copy_end>scratch_bytes)fail(5,0,0);else state<=copy_remaining==0?COPY_NEXT:COPY_READ;
                COPY_READ:if(copy_static?static_read_ready:slot_ready)state<=COPY_READ_WAIT;
                COPY_READ_WAIT:if(copy_static?static_byte_valid:slot_valid)begin
                    if(copy_static?static_byte_invalid:slot_status!=0)fail(6,copy_static?8'hfe:8'd0,copy_static?8'd0:slot_status);
                    else begin transfer_data<=copy_static?{64'd0,static_byte_data}:slot_data;state<=COPY_WRITE;end
                end
                COPY_WRITE:if(slot_ready)state<=COPY_WRITE_WAIT;
                COPY_WRITE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(7,0,slot_status);
                    else begin
                        scratch_position<=scratch_position+copy_chunk;copy_offset<=copy_offset+copy_chunk;copy_remaining<=copy_remaining-copy_chunk;
                        state<=copy_remaining<=copy_chunk?COPY_NEXT:COPY_READ;
                    end
                end
                COPY_NEXT:begin
                    if(representation==0&&!copy_field)begin copy_field<=1;copy_remaining<=value_size;copy_offset<=0;state<=COPY_SETUP;end
                    else if(dynamic_lease)state<=RELEASE_LOOKUP;else after_copy;
                end
                RELEASE_LOOKUP:if(dt_valid)begin dynamic_lease<=0;after_copy;end
                STRING_START:if(block_remaining==0)fail(4,8'hfe,0);else state<=STRING_RUN;
                STRING_RUN:begin
                    if(str_result)begin if(str_status!=0)fail(4,str_status,str_detail);else fail(4,8'hfd,0);end
                    else if(str_valid&&str_output_ready)begin
                        if(str_keep)begin
                            if(scratch_position>=scratch_bytes)fail(5,0,0);
                            else begin transfer_data<={64'd0,str_data};state<=STRING_WRITE;end
                        end else if(str_last)state<=STRING_RESULT;else fail(4,8'hfc,0);
                    end
                end
                STRING_WRITE:if(slot_ready)state<=STRING_WRITE_WAIT;
                STRING_WRITE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(7,0,slot_status);
                    else begin
                        scratch_position<=scratch_position+1'b1;
                        if(string_field)value_size<=value_size+1'b1;else name_size<=name_size+1'b1;
                        state<=STRING_RUN;
                    end
                end
                STRING_RESULT:if(str_result)begin
                    if(str_status!=0)fail(4,str_status,str_detail);
                    else if(!string_field)begin string_field<=1;state<=STRING_START;end
                    else state<=FIELD_DONE;
                end
                FIELD_DONE:if(next_list_size>list_limit)fail(11,0,0);else begin
                    headers_seen<=headers_seen+1'b1;list_bytes<=next_list_size[31:0];state<=representation==1?INSERT_REQ:HEADER;
                end
                INSERT_REQ:if(dt_ready)state<=INSERT_WAIT;
                INSERT_WAIT:if(dt_valid)begin
                    if(dt_status!=0)fail(12,dt_status,dt_memory_status);
                    else begin maximum<=dt_maximum;used<=dt_used;entries<=dt_entries;state<=HEADER;end
                end
                HEADER:if(header_ready)state<=block_remaining==0?FINISH:REP;
                RESIZE_REQ:if(dt_ready)state<=RESIZE_WAIT;
                RESIZE_WAIT:if(dt_valid)begin
                    if(dt_status!=0)fail(9,dt_status,dt_memory_status);
                    else begin maximum<=dt_maximum;used<=dt_used;entries<=dt_entries;need_update<=0;state<=block_remaining==0?FINISH:REP;end
                end
                FINISH:if(need_update)fail(10,0,0);else state<=RESULT;
                ABORT:if(block_remaining==0&&slot_idle&&dt_idle)state<=RESET_CHILDREN;
                RESET_CHILDREN:state<=RESULT;
                RESULT:if(completion_ready)state<=IDLE;
                default:state<=ABORT;
            endcase
            if(state!=ABORT&&s_valid&&s_ready&&s_user!=context_id)fail(8,0,0);
        end
    end
endmodule
`default_nettype wire
