`timescale 1ns/1ps
`default_nettype none
// Runtime external stream directory. OPEN allocates a free record; LOAD finds
// (connection,stream); SAVE/CLOSE verify the returned address and generation.
// Owns bytes 0..63 of each 128-byte record. No fixed on-chip stream array.
module grpc_stream_store #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,input wire req_valid,output wire req_ready,input wire [2:0] req_op,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes,
    input wire [USER_WIDTH-1:0] req_user,req_application,input wire [30:0] req_stream,input wire [31:0] req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_address,req_buffer_base,input wire [MEMORY_ADDR_WIDTH:0] req_buffer_bytes,
    input wire [31:0] req_message_limit,input wire req_protobuf,req_unsupported_encoding,req_maintenance,input wire [255:0] req_state,
    output wire rsp_valid,input wire rsp_ready,output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,output wire [2:0] rsp_op,
    output wire [MEMORY_ADDR_WIDTH-1:0] rsp_address,rsp_buffer_base,output wire [MEMORY_ADDR_WIDTH:0] rsp_buffer_bytes,
    output wire [USER_WIDTH-1:0] rsp_user,rsp_application,output wire [30:0] rsp_stream,output wire [31:0] rsp_generation,rsp_message_limit,
    output wire rsp_protobuf,rsp_unsupported_encoding,output wire [255:0] rsp_state,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,output wire idle,
    output wire mem_valid,input wire mem_ready,output wire mem_write,output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,output wire [71:0] mem_data,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status
);
    localparam IDLE=0,CHECK=1,LOAD_REQ=2,LOAD_WAIT=3,RECORD_CHECK=4,SCAN_NEXT=5,INVALIDATE_REQ=6,INVALIDATE_WAIT=7,
        WRITE_REQ=8,WRITE_WAIT=9,COMMIT_REQ=10,COMMIT_WAIT=11,RESULT=12,VALIDATE_RECORD=13;
    localparam OPEN=0,LOAD=1,SAVE=2,CLOSE=3,FORMAT=4,RECOVER=5,FIND_CONNECTION=6;
    localparam [31:0] MAGIC=32'h47525331;
    reg [3:0] state;reg [2:0] op,word_index;
    reg [MEMORY_ADDR_WIDTH-1:0] pool_base,address,first_free,requested_address,buffer_base;
    reg [MEMORY_ADDR_WIDTH:0] pool_bytes,buffer_bytes;
    reg found_free,protobuf_mode,unsupported_encoding,maintenance;
    reg [USER_WIDTH-1:0] context_id,application_id;reg [30:0] stream_id;reg [31:0] generation,message_limit;
    reg [255:0] requested_state;reg [511:0] record_data;
    // Keep independent validation results registered before the wide record
    // write enable. Combining all comparisons into that enable creates a long
    // carry/route path even though no external memory operation is outstanding.
    reg [10:0] record_checks;
    function automatic sensible_state;
        input [255:0] value;input [31:0] capacity,limit;
        reg [63:0] payload_end;
        begin
            payload_end={32'd0,value[63:32]}+{32'd0,value[95:64]};
            sensible_state=value[255:165]==0&&value[31:0]<=capacity&&value[63:32]<=value[31:0]&&value[162:160]<=5&&
                (value[162:160]!=1||value[95:64]==0)&&(value[162:160]!=2||value[95:72]==0)&&
                (value[162:160]!=3||value[95:80]==0)&&(value[162:160]!=4||value[95:88]==0)&&
                (value[162:160]==5?(value[95:64]!=0&&value[95:64]<=limit&&payload_end<=capacity&&value[127:96]<value[95:64]&&
                    {32'd0,value[31:0]}=={32'd0,value[63:32]}+value[127:96]):
                    (value[127:96]==0&&value[63:32]==value[31:0]&&(value[162:160]!=0||value[95:64]==0)))&&
                (!value[163]||value[162:160]==0)&&(!value[164]||value[159:128]==32'hffffffff&&value[162:160]==0);
        end
    endfunction
    wire [15:0] user16=context_id,application16=application_id;
    wire [63:0] pool_end={1'b0,pool_base}+{1'b0,pool_bytes};
    wire [63:0] requested_end={1'b0,requested_address}+64'd128;
    wire [63:0] buffer_end={1'b0,buffer_base}+{1'b0,buffer_bytes};
    wire pool_good=pool_bytes>=128&&pool_bytes[6:0]==0&&pool_end<=(64'd1<<MEMORY_ADDR_WIDTH);
    wire address_good=requested_address>=pool_base&&requested_end<=pool_end&&((requested_address-pool_base)&127)==0;
    wire buffer_good=buffer_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (buffer_bytes==0||buffer_end<=pool_base||{1'b0,buffer_base}>=pool_end);
    wire recovery_covered=recovery_address>=pool_base&&{1'b0,recovery_address}+64'd128<=pool_end&&((recovery_address-pool_base)&127)==0;
    wire [63:0] record_buffer_end={32'd0,record_data[159:128]}+{32'd0,record_data[191:160]};
    wire key_matches=record_data[79:64]==user16&&(op==FIND_CONNECTION||record_data[126:96]==stream_id);
    wire buffer_overlaps=buffer_bytes!=0&&record_data[191:160]!=0&&buffer_end>{32'd0,record_data[159:128]}&&{1'b0,buffer_base}<record_buffer_end;
    wire same_message=requested_state[159:128]==record_data[415:384]&&!(requested_state[164]&&!record_data[420]);
    wire prefix_progress=record_data[418:416]==5?
        requested_state[162:160]==5&&requested_state[63:32]==record_data[319:288]&&requested_state[95:64]==record_data[351:320]&&requested_state[127:96]>=record_data[383:352]:
        requested_state[162:160]>=record_data[418:416]&&requested_state[63:32]==record_data[319:288]&&
            (requested_state[162:160]==5||requested_state[31:0]==record_data[287:256]);
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire slot_request=state==LOAD_REQ||state==INVALIDATE_REQ||state==WRITE_REQ||state==COMMIT_REQ;
    wire [MEMORY_ADDR_WIDTH-1:0] command_address=address+(state==LOAD_REQ||state==WRITE_REQ?word_index*8:0);
    wire [63:0] record_word;
    integer record_load_index;
    wire [63:0] record_words[0:7];
    generate for(genvar select_bank=0;select_bank<8;select_bank=select_bank+1)begin: word_select_banks
        assign record_words[select_bank]=record_data[select_bank*64+:64];
    end endgenerate
    assign record_word=record_words[word_index];
    wire [71:0] command_data=state==INVALIDATE_REQ?72'd0:state==WRITE_REQ?{8'd0,record_word}:{8'd0,record_data[63:0]};
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(slot_request),.req_ready(slot_ready),.req_write(state!=LOAD_REQ),.req_addr(command_address),.req_bytes(4'd8),.req_data(command_data),
        .result_valid(slot_valid),.result_ready(state==LOAD_WAIT||state==INVALIDATE_WAIT||state==WRITE_WAIT||state==COMMIT_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign req_ready=!rst&&state==IDLE;assign rsp_valid=state==RESULT;assign rsp_op=op;
    assign rsp_address=address;assign rsp_user=context_id;assign rsp_stream=rsp_status==0&&op==FIND_CONNECTION?record_data[126:96]:stream_id;
    assign rsp_application=rsp_status==0?record_data[80+:USER_WIDTH]:{USER_WIDTH{1'b0}};
    assign rsp_generation=rsp_status==0?record_data[255:224]:32'd0;assign rsp_message_limit=rsp_status==0?record_data[223:192]:32'd0;
    assign rsp_buffer_base=rsp_status==0?record_data[128+:MEMORY_ADDR_WIDTH]:{MEMORY_ADDR_WIDTH{1'b0}};
    assign rsp_buffer_bytes=rsp_status==0?record_data[160+:MEMORY_ADDR_WIDTH+1]:{(MEMORY_ADDR_WIDTH+1){1'b0}};
    assign rsp_protobuf=rsp_status==0&&record_data[33];assign rsp_unsupported_encoding=rsp_status==0&&record_data[34];
    assign rsp_state=rsp_status==0?record_data[511:256]:256'd0;
    assign idle=state==IDLE&&slot_idle&&!(req_valid&&req_ready);
    task fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status);
        begin rsp_status<=status;rsp_detail<=detail;rsp_memory_status<=memory_status;state<=RESULT;end
    endtask
    task memory_failure(input [7:0] status,input [7:0] detail);
        begin recovery_required<=1;recovery_address<=address;fail(status,detail,slot_status);end
    endtask
    task corrupt_record;
        begin recovery_required<=1;recovery_address<=address;fail(9,10,0);end
    endtask
    initial begin if(USER_WIDTH>16||MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>31)$error("Unsupported stream-store widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;op<=0;word_index<=0;pool_base<=0;pool_bytes<=0;address<=0;first_free<=0;requested_address<=0;
            buffer_base<=0;buffer_bytes<=0;found_free<=0;protobuf_mode<=0;unsupported_encoding<=0;maintenance<=0;context_id<=0;application_id<=0;stream_id<=0;
            generation<=0;message_limit<=0;requested_state<=0;record_data<=0;record_checks<=0;rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;recovery_required<=0;recovery_address<=0;
        end else case(state)
            IDLE:if(req_valid&&req_ready)begin
                op<=req_op;pool_base<=cfg_pool_base;pool_bytes<=cfg_pool_bytes;address<=cfg_pool_base;requested_address<=req_address;
                context_id<=req_user;application_id<=req_application;stream_id<=req_stream;generation<=req_generation;
                buffer_base<=req_buffer_base;buffer_bytes<=req_buffer_bytes;message_limit<=req_message_limit;protobuf_mode<=req_protobuf;unsupported_encoding<=req_unsupported_encoding;maintenance<=req_maintenance;
                requested_state<=req_state;record_data<=0;word_index<=0;found_free<=0;first_free<=0;rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;state<=CHECK;
            end
            CHECK:begin
                if(!pool_good)fail(1,0,0);
                else if(op>FIND_CONNECTION)fail(7,0,0);
                else if((op==FORMAT||op==RECOVER)&&!maintenance)fail(7,2,0);
                else if(recovery_required&&!(op==RECOVER&&requested_address==recovery_address&&address_good||op==FORMAT&&recovery_covered))fail(6,0,0);
                else if(op==RECOVER)begin
                    if(!recovery_required||!address_good)fail(7,1,0);else begin address<=requested_address;state<=INVALIDATE_REQ;end
                end else if(op==FORMAT)state<=INVALIDATE_REQ;
                else if(op!=FIND_CONNECTION&&stream_id==0||op==OPEN&&!buffer_good)fail(1,1,0);
                else if(op==SAVE||op==CLOSE)begin if(!address_good)fail(1,2,0);else begin address<=requested_address;state<=LOAD_REQ;end end
                else state<=LOAD_REQ;
            end
            LOAD_REQ:if(slot_ready)state<=LOAD_WAIT;
            LOAD_WAIT:if(slot_valid)begin
                if(slot_status!=0)memory_failure(2,{5'd0,word_index});
                else begin
                    for(record_load_index=0;record_load_index<8;record_load_index=record_load_index+1)
                        if(word_index==record_load_index)record_data[record_load_index*64+:64]<=slot_data[63:0];
                    if(word_index==0)begin
                        if(slot_data[63:0]==0)begin
                            if(op==SAVE||op==CLOSE)fail(3,0,0);
                            else begin if(op==OPEN&&!found_free)begin first_free<=address;found_free<=1;end state<=SCAN_NEXT;end
                        end else if(slot_data[31:0]!=MAGIC||!slot_data[32]||slot_data[63:35]!=0)corrupt_record;
                        else begin word_index<=1;state<=LOAD_REQ;end
                    end else if(word_index==1&&(slot_data[63]||slot_data[62:32]==0))corrupt_record;
                    else if(word_index==1&&(op==LOAD||op==FIND_CONNECTION)&&(slot_data[15:0]!=user16||op==LOAD&&slot_data[62:32]!=stream_id))state<=SCAN_NEXT;
                    else if(word_index==7)state<=VALIDATE_RECORD;
                    else begin word_index<=word_index+1'b1;state<=LOAD_REQ;end
                end
            end
            VALIDATE_RECORD:begin
                record_checks[0]<=sensible_state(requested_state,record_data[191:160],record_data[223:192]);
                record_checks[1]<=requested_state[31:0]>=record_data[287:256];
                record_checks[2]<=requested_state[159:128]>=record_data[415:384];
                record_checks[3]<=!same_message||prefix_progress;
                record_checks[4]<=!record_data[419]||requested_state==record_data[511:256];
                record_checks[5]<=!record_data[420]||requested_state[164]&&requested_state[31:0]==record_data[287:256]&&requested_state[159:128]==record_data[415:384];
                record_checks[6]<=record_buffer_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
                    (record_data[191:160]==0||record_buffer_end<=pool_base||{32'd0,record_data[159:128]}>=pool_end);
                record_checks[7]<=sensible_state(record_data[511:256],record_data[191:160],record_data[223:192]);
                record_checks[8]<=key_matches;record_checks[9]<=record_data[255:224]==generation;
                record_checks[10]<=buffer_overlaps;state<=RECORD_CHECK;
            end
            RECORD_CHECK:begin
                if(!record_checks[6]||!record_checks[7])corrupt_record;
                else if(op==OPEN)begin if(record_checks[8])fail(4,0,0);else if(record_checks[10])fail(1,3,0);else state<=SCAN_NEXT;end
                else if(!record_checks[8]||op!=LOAD&&op!=FIND_CONNECTION&&!record_checks[9])fail(8,0,0);
                else if(op==LOAD||op==FIND_CONNECTION)state<=RESULT;
                else if(op==CLOSE)state<=INVALIDATE_REQ;
                else if(!(&record_checks[5:0]))fail(1,4,0);
                else begin record_data[511:256]<=requested_state;state<=INVALIDATE_REQ;end
            end
            SCAN_NEXT:begin
                if({1'b0,address}+64'd128<pool_end)begin address<=address+128;word_index<=0;state<=LOAD_REQ;end
                else if(op==OPEN&&found_free)begin
                    address<=first_free;record_data<={256'd0,generation,message_limit,{{(31-MEMORY_ADDR_WIDTH){1'b0}},buffer_bytes},{{(32-MEMORY_ADDR_WIDTH){1'b0}},buffer_base},1'b0,stream_id,application16,user16,29'd0,unsupported_encoding,protobuf_mode,1'b1,MAGIC};
                    state<=INVALIDATE_REQ;
                end else fail(op==OPEN?8'd10:8'd3,0,0);
            end
            INVALIDATE_REQ:if(slot_ready)state<=INVALIDATE_WAIT;
            INVALIDATE_WAIT:if(slot_valid)begin
                if(slot_status!=0)memory_failure(5,8);
                else if(op==FORMAT)begin
                    if({1'b0,address}+64'd128<pool_end)begin address<=address+128;state<=INVALIDATE_REQ;end
                    else begin recovery_required<=0;recovery_address<=0;state<=RESULT;end
                end else if(op==CLOSE||op==RECOVER)begin if(op==RECOVER)begin recovery_required<=0;recovery_address<=0;end state<=RESULT;end
                else begin word_index<=op==SAVE?3'd4:3'd1;state<=WRITE_REQ;end
            end
            WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
            WRITE_WAIT:if(slot_valid)begin
                if(slot_status!=0)memory_failure(5,{5'd0,word_index});
                else if(word_index==7)state<=COMMIT_REQ;
                else begin word_index<=word_index+1'b1;state<=WRITE_REQ;end
            end
            COMMIT_REQ:if(slot_ready)state<=COMMIT_WAIT;
            COMMIT_WAIT:if(slot_valid)begin if(slot_status!=0)memory_failure(5,9);else state<=RESULT;end
            RESULT:if(rsp_ready)state<=IDLE;
            default:begin end
        endcase
    end
endmodule
`default_nettype wire
