`timescale 1ns/1ps
`default_nettype none
// External HPACK dictionary operation. The caller supplies/saves each
// connection's state; no fixed on-chip connection count or string pool exists.
// Records are newest first: name length32, value length32, 24 zero bytes,
// then name/value octets. Their physical and HPACK-accounted size is identical.
// Insertions move the retained prefix backwards before writing a new head.
// LOOKUP pointers are leased until rsp_ready: the caller copies bytes before
// releasing the response. Any failure invalidates that compression context.
module hpack_dynamic_table #(
    parameter integer MEMORY_ADDR_WIDTH=23,parameter integer USER_WIDTH=16
)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire [1:0] req_op,
    input wire [31:0] req_argument,input wire [31:0] req_name_bytes,req_value_bytes,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_source_base,req_table_base,
    input wire [MEMORY_ADDR_WIDTH:0] req_table_bytes,
    input wire [31:0] req_maximum,req_allowed_maximum,req_used,req_entries,input wire [USER_WIDTH-1:0] req_user,
    output wire rsp_valid,input wire rsp_ready,output reg [7:0] rsp_status,rsp_memory_status,
    output reg [31:0] rsp_maximum,rsp_used,rsp_entries,
    output reg rsp_lookup_valid,rsp_inserted,
    output reg [MEMORY_ADDR_WIDTH-1:0] rsp_name_base,rsp_value_base,
    output reg [31:0] rsp_name_bytes,rsp_value_bytes,output wire [USER_WIDTH-1:0] rsp_user,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,CHECK=1,HEADER_REQ=2,HEADER_WAIT=3,PREPARE=4,COPY_READ=5,COPY_WAIT=6,COPY_WRITE=7,COPY_WWAIT=8,
               NEW_HEADER=9,NEW_HEADER_WAIT=10,SOURCE_READ=11,SOURCE_WAIT=12,PAYLOAD_WRITE=13,PAYLOAD_WAIT=14,RESULT=15,
               MEASURE=16,INSERT_SPACE=17;
    localparam LOOKUP=0,INSERT=1,RESIZE=2;
    reg [4:0] state;
    reg [1:0] op,header_word;
    reg [MEMORY_ADDR_WIDTH-1:0] base,source_base;
    reg [MEMORY_ADDR_WIDTH:0] capacity;
    reg [31:0] argument,name_size,value_size,maximum,allowed_maximum,used,entries;
    reg [31:0] scan_offset,scan_index,available,keep_bytes,keep_entries,move_remaining,payload_offset,payload_remaining;
    reg [71:0] transfer_data;
    reg [USER_WIDTH-1:0] context_id;
    wire [63:0] table_end={1'b0,base}+{1'b0,capacity};
    // Register length arithmetic before capacity/eviction decisions. Keeping
    // sum, subtraction and comparison on one path misses 4 ns after routing.
    reg [63:0] source_length,new_size_wide;
    wire [63:0] source_end=source_base+source_length;
    wire [31:0] new_size=new_size_wide[31:0];
    wire [63:0] entry_size=64'd32+{32'd0,mem_rsp_data[31:0]}+{32'd0,mem_rsp_data[63:32]};
    wire [63:0] entry_end={32'd0,scan_offset}+entry_size;
    wire entry_good=entry_end<=used&&scan_index<entries&&((entry_end==used)==(scan_index+1==entries));
    wire [3:0] copy_chunk=move_remaining>=8?4'd8:move_remaining[3:0];
    // Decrement after durable writes, rather than sum/subtract/compare on the
    // response-state path. Requests cannot underflow the remaining count.
    wire [3:0] source_chunk=payload_remaining>=8?4'd8:payload_remaining[3:0];
    wire [63:0] header_address=base+{32'd0,scan_offset};
    wire [63:0] copy_address=base+{32'd0,move_remaining}-{60'd0,copy_chunk};
    wire [63:0] command_address=state==HEADER_REQ?header_address:
        state==COPY_READ?copy_address:state==COPY_WRITE?copy_address+new_size_wide:
        state==NEW_HEADER?base+64'd8*header_word:state==SOURCE_READ?source_base+{32'd0,payload_offset}:
        base+64'd32+payload_offset;
    assign req_ready=!rst&&state==IDLE;
    assign rsp_valid=state==RESULT;
    assign rsp_user=context_id;
    assign idle=state==IDLE&&!(req_valid&&req_ready);
    assign mem_valid=!rst&&(state==HEADER_REQ||state==COPY_READ||state==COPY_WRITE||state==NEW_HEADER||state==SOURCE_READ||state==PAYLOAD_WRITE);
    assign mem_write=state==COPY_WRITE||state==NEW_HEADER||state==PAYLOAD_WRITE;
    assign mem_addr=command_address[MEMORY_ADDR_WIDTH-1:0];
    assign mem_bytes=state==COPY_READ||state==COPY_WRITE?copy_chunk:state==SOURCE_READ||state==PAYLOAD_WRITE?source_chunk:4'd8;
    assign mem_data=state==NEW_HEADER?(header_word==0?{8'd0,value_size,name_size}:72'd0):transfer_data;
    assign mem_rsp_ready=state==HEADER_WAIT||state==COPY_WAIT||state==COPY_WWAIT||state==NEW_HEADER_WAIT||state==SOURCE_WAIT||state==PAYLOAD_WAIT;
    task complete(input [31:0] new_used,input [31:0] new_entries,input [31:0] new_maximum);
        begin rsp_status<=0;rsp_memory_status<=0;rsp_used<=new_used;rsp_entries<=new_entries;rsp_maximum<=new_maximum;state<=RESULT;end
    endtask
    task fail(input [7:0] status,input [7:0] memory_status);
        begin
            rsp_status<=status;rsp_memory_status<=memory_status;rsp_used<=0;rsp_entries<=0;rsp_maximum<=0;
            rsp_lookup_valid<=0;rsp_inserted<=0;rsp_name_base<=0;rsp_value_base<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;state<=RESULT;
        end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;op<=0;header_word<=0;base<=0;source_base<=0;capacity<=0;argument<=0;name_size<=0;value_size<=0;
            maximum<=0;allowed_maximum<=0;used<=0;entries<=0;scan_offset<=0;scan_index<=0;available<=0;keep_bytes<=0;keep_entries<=0;
            move_remaining<=0;payload_offset<=0;payload_remaining<=0;transfer_data<=0;context_id<=0;source_length<=0;new_size_wide<=0;
            rsp_status<=0;rsp_memory_status<=0;rsp_maximum<=0;rsp_used<=0;rsp_entries<=0;rsp_lookup_valid<=0;rsp_inserted<=0;
            rsp_name_base<=0;rsp_value_base<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;
        end else case(state)
            IDLE:if(req_valid&&req_ready)begin
                op<=req_op;argument<=req_argument;name_size<=req_name_bytes;value_size<=req_value_bytes;source_base<=req_source_base;
                base<=req_table_base;capacity<=req_table_bytes;maximum<=req_maximum;allowed_maximum<=req_allowed_maximum;used<=req_used;entries<=req_entries;context_id<=req_user;
                rsp_lookup_valid<=0;rsp_inserted<=0;rsp_name_base<=0;rsp_value_base<=0;rsp_name_bytes<=0;rsp_value_bytes<=0;
                scan_offset<=0;scan_index<=0;keep_bytes<=0;keep_entries<=0;
                source_length<={32'd0,req_name_bytes}+{32'd0,req_value_bytes};state<=MEASURE;
            end
            MEASURE:begin new_size_wide<=64'd32+source_length;state<=CHECK;end
            CHECK:begin
                if(op>RESIZE||table_end>(64'd1<<MEMORY_ADDR_WIDTH)||allowed_maximum>capacity||maximum>capacity||
                   (op!=RESIZE&&maximum>allowed_maximum)||used>maximum||
                   entries>(used>>5)||((used==0)!=(entries==0)))fail(1,0);
                else if(op==LOOKUP)begin if(argument>=entries)fail(2,0);else state<=HEADER_REQ;end
                else if(op==INSERT)begin
                    if(new_size_wide>maximum)complete(0,0,maximum);
                    else if(source_end>(64'd1<<MEMORY_ADDR_WIDTH)||(source_length!=0&&!(source_end<=base||source_base>=table_end)))fail(3,0);
                    else begin
                        available<=maximum-new_size;
                        state<=INSERT_SPACE;
                    end
                end else begin
                    if(argument>allowed_maximum)fail(3,0);
                    else begin
                        available<=argument;
                        if(used<=argument)begin keep_bytes<=used;keep_entries<=entries;state<=PREPARE;end
                        else if(argument<32)state<=PREPARE;
                        else state<=HEADER_REQ;
                    end
                end
            end
            INSERT_SPACE:begin
                if(used<=available)begin keep_bytes<=used;keep_entries<=entries;state<=PREPARE;end
                else if(available<32)state<=PREPARE;
                else state<=HEADER_REQ;
            end
            HEADER_REQ:if(mem_ready)state<=HEADER_WAIT;
            HEADER_WAIT:if(mem_rsp_valid)begin
                if(mem_rsp_status!=0)fail(4,mem_rsp_status);
                else if(!entry_good)fail(6,0);
                else if(op==LOOKUP)begin
                    if(scan_index==argument)begin
                        rsp_lookup_valid<=1;rsp_name_bytes<=mem_rsp_data[31:0];rsp_value_bytes<=mem_rsp_data[63:32];
                        rsp_name_base<=mem_rsp_data[31:0]==0?0:header_address+32;
                        rsp_value_base<=mem_rsp_data[63:32]==0?0:header_address+32+mem_rsp_data[31:0];
                        complete(used,entries,maximum);
                    end else begin scan_offset<=entry_end[31:0];scan_index<=scan_index+1'b1;state<=HEADER_REQ;end
                end else if(entry_end<=available)begin
                    keep_bytes<=entry_end[31:0];keep_entries<=scan_index+1'b1;
                    if(entry_end==used)state<=PREPARE;else begin scan_offset<=entry_end[31:0];scan_index<=scan_index+1'b1;state<=HEADER_REQ;end
                end else state<=PREPARE;
            end
            PREPARE:begin
                if(op==RESIZE)complete(keep_bytes,keep_entries,argument);
                else if(keep_bytes!=0)begin move_remaining<=keep_bytes;state<=COPY_READ;end
                else begin header_word<=0;state<=NEW_HEADER;end
            end
            COPY_READ:if(mem_ready)state<=COPY_WAIT;
            COPY_WAIT:if(mem_rsp_valid)begin if(mem_rsp_status!=0)fail(4,mem_rsp_status);else begin transfer_data<=mem_rsp_data;state<=COPY_WRITE;end end
            COPY_WRITE:if(mem_ready)state<=COPY_WWAIT;
            COPY_WWAIT:if(mem_rsp_valid)begin
                if(mem_rsp_status!=0)fail(5,mem_rsp_status);
                else if(move_remaining<=8)begin header_word<=0;state<=NEW_HEADER;end
                else begin move_remaining<=move_remaining-copy_chunk;state<=COPY_READ;end
            end
            NEW_HEADER:if(mem_ready)state<=NEW_HEADER_WAIT;
            NEW_HEADER_WAIT:if(mem_rsp_valid)begin
                if(mem_rsp_status!=0)fail(5,mem_rsp_status);
                else if(header_word!=3)begin header_word<=header_word+1'b1;state<=NEW_HEADER;end
                else if(source_length==0)begin rsp_inserted<=1;complete(keep_bytes+new_size,keep_entries+1,maximum);end
                else begin payload_offset<=0;payload_remaining<=source_length[31:0];state<=SOURCE_READ;end
            end
            SOURCE_READ:if(mem_ready)state<=SOURCE_WAIT;
            SOURCE_WAIT:if(mem_rsp_valid)begin if(mem_rsp_status!=0)fail(4,mem_rsp_status);else begin transfer_data<=mem_rsp_data;state<=PAYLOAD_WRITE;end end
            PAYLOAD_WRITE:if(mem_ready)state<=PAYLOAD_WAIT;
            PAYLOAD_WAIT:if(mem_rsp_valid)begin
                if(mem_rsp_status!=0)fail(5,mem_rsp_status);
                else if(payload_remaining<=8)begin rsp_inserted<=1;complete(keep_bytes+new_size,keep_entries+1,maximum);end
                else begin payload_offset<=payload_offset+source_chunk;payload_remaining<=payload_remaining-source_chunk;state<=SOURCE_READ;end
            end
            RESULT:if(rsp_ready)state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
