`timescale 1ns/1ps
`default_nettype none
// Internal maintenance after every committed descriptor has retired and no
// producer/replay lease remains. The caller fences new packet/config admission.
// The actual directory pool lock is held across payload movement, metadata
// commit and receive-credit retirement. No host request can assert this proof.
module grpc_payload_reclaimer #(
    parameter integer MEMORY_ADDR_WIDTH=23,USER_WIDTH=16
)(
    input wire clk,rst,
    input wire start_valid,output wire start_ready,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base,cfg_payload_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes,cfg_payload_bytes,cfg_slot_bytes,
    output wire lock_valid,input wire lock_ready,
    output wire [MEMORY_ADDR_WIDTH-1:0] lock_base,output wire [MEMORY_ADDR_WIDTH:0] lock_bytes,
    input wire lock_result_valid,output wire lock_result_ready,input wire [7:0] lock_status,
    input wire lock_active,output wire unlock_valid,input wire unlock_ready,
    output wire credit_valid,input wire credit_ready,output wire [3:0] credit_op,
    output wire [USER_WIDTH-1:0] credit_user,output wire [30:0] credit_stream,
    output wire [31:0] credit_generation,credit_amount,
    output wire [MEMORY_ADDR_WIDTH-1:0] credit_address,
    input wire credit_result_valid,output wire credit_result_ready,
    input wire [7:0] credit_status,credit_detail,credit_memory_status,
    output wire memory_owner,credit_owner,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,
    output wire [71:0] mem_data,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire result_valid,input wire result_ready,
    output reg [7:0] result_status,result_detail,result_memory_status,
    output reg recovery_required,output wire [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire busy,idle
);
    localparam IDLE=0,CHECK=1,LOCK_SEND=2,LOCK_WAIT=3,READ_REQ=4,READ_WAIT=5,
        VALIDATE=6,INVALIDATE_REQ=7,INVALIDATE_WAIT=8,COPY_READ_REQ=9,COPY_READ_WAIT=10,
        COPY_WRITE_REQ=11,COPY_WRITE_WAIT=12,STATE_WRITE_REQ=13,STATE_WRITE_WAIT=14,
        COMMIT_REQ=15,COMMIT_WAIT=16,CREDIT_SEND=17,CREDIT_WAIT=18,NEXT_RECORD=19,
        UNLOCK=20,RESULT=21,QUARANTINE=22;
    reg [4:0] state;
    reg [MEMORY_ADDR_WIDTH-1:0] pool_base,payload_base,work_floor,record_address,payload_cursor;
    reg [MEMORY_ADDR_WIDTH:0] pool_bytes,payload_bytes,slot_bytes;
    reg [2:0] word_index;
    reg [1:0] credit_step;
    reg [511:0] record_data;
    reg [31:0] cut_bytes,copy_bytes,copy_offset,refund_bytes;
    reg [63:0] copy_data;
    reg result_acked,held_lock;
    wire [63:0] pool_end={1'b0,pool_base}+{1'b0,pool_bytes};
    wire [63:0] payload_end={1'b0,payload_base}+{1'b0,payload_bytes};
    wire [63:0] slot_end={1'b0,payload_cursor}+{1'b0,slot_bytes};
    wire geometry_good=pool_bytes>=128&&pool_bytes[6:0]==0&&slot_bytes!=0&&
        pool_base>=work_floor&&payload_base>=work_floor&&
        pool_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&payload_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        (pool_end<={1'b0,payload_base}||payload_end<={1'b0,pool_base});
    wire [255:0] progress=record_data[511:256];
    wire [32:0] completed_count={1'b0,progress[159:128]}+progress[164];
    wire [32:0] reclaimed_count=progress[197:165];
    wire [63:0] message_end={32'd0,progress[63:32]}+{32'd0,progress[95:64]};
    wire progress_good=progress[255:198]==0&&reclaimed_count<=completed_count&&
        progress[31:0]<=record_data[191:160]&&progress[63:32]<=progress[31:0]&&progress[162:160]<=5&&
        (progress[162:160]!=1||progress[95:64]==0)&&
        (progress[162:160]!=2||progress[95:72]==0)&&
        (progress[162:160]!=3||progress[95:80]==0)&&
        (progress[162:160]!=4||progress[95:88]==0)&&
        (progress[162:160]==5?(progress[95:64]!=0&&progress[95:64]<=record_data[223:192]&&
            message_end<=record_data[191:160]&&progress[127:96]<progress[95:64]&&
            {32'd0,progress[31:0]}=={32'd0,progress[63:32]}+progress[127:96]):
            (progress[127:96]==0&&progress[63:32]==progress[31:0]&&
                (progress[162:160]!=0||progress[95:64]==0)))&&
        (!progress[163]||progress[162:160]==0)&&
        (!progress[164]||progress[159:128]==32'hffffffff&&progress[162:160]==0);
    wire record_good=record_data[31:0]==32'h47525331&&record_data[32]&&record_data[63:35]==0&&
        !record_data[127]&&record_data[126:96]!=0&&record_data[255:224]!=0&&
        {48'd0,record_data[79:64]}<(64'd1<<USER_WIDTH)&&
        record_data[159:128]=={{(32-MEMORY_ADDR_WIDTH){1'b0}},payload_cursor}&&
        record_data[191:160]=={{(31-MEMORY_ADDR_WIDTH){1'b0}},slot_bytes}&&
        payload_cursor>=payload_base&&slot_end<=payload_end&&progress_good;
    wire [63:0] complete_delta={31'd0,completed_count}-{31'd0,reclaimed_count};
    wire [63:0] refund_value={32'd0,progress[63:32]}+complete_delta*64'd5;
    wire refund_good=refund_value<=65535&&(complete_delta!=0||progress[63:32]==0);
    wire [31:0] remaining=copy_bytes-copy_offset;
    wire [3:0] chunk_bytes=remaining>=8?4'd8:remaining[3:0];
    wire slot_ready,slot_valid,slot_idle;
    wire [71:0] slot_data;wire [7:0] slot_status;
    wire direct_request=state==READ_REQ&&payload_cursor>=payload_base&&slot_end<=payload_end||state==INVALIDATE_REQ||state==COPY_READ_REQ||
        state==COPY_WRITE_REQ||state==STATE_WRITE_REQ||state==COMMIT_REQ;
    wire copying=state==COPY_READ_REQ||state==COPY_READ_WAIT||state==COPY_WRITE_REQ||state==COPY_WRITE_WAIT;
    wire [63:0] command_address=copying?
        {1'b0,payload_cursor}+{32'd0,copy_offset}+(state==COPY_READ_REQ||state==COPY_READ_WAIT?{32'd0,cut_bytes}:64'd0):
        {1'b0,record_address}+(state==READ_REQ||state==READ_WAIT||state==STATE_WRITE_REQ||state==STATE_WRITE_WAIT?word_index*8:0);
    wire [63:0] words[0:7];
    generate for(genvar bank=0;bank<8;bank=bank+1)begin:record_words
        assign words[bank]=record_data[bank*64+:64];
    end endgenerate
    wire [71:0] command_data=state==INVALIDATE_REQ?72'd0:state==COPY_WRITE_REQ?{8'd0,copy_data}:
        state==STATE_WRITE_REQ?{8'd0,words[word_index]}:{8'd0,record_data[63:0]};
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(direct_request),.req_ready(slot_ready),
        .req_write(state!=READ_REQ&&state!=COPY_READ_REQ),.req_addr(command_address[MEMORY_ADDR_WIDTH-1:0]),
        .req_bytes(copying?chunk_bytes:4'd8),.req_data(command_data),
        .result_valid(slot_valid),.result_ready(state==READ_WAIT||state==INVALIDATE_WAIT||state==COPY_READ_WAIT||
            state==COPY_WRITE_WAIT||state==STATE_WRITE_WAIT||state==COMMIT_WAIT),
        .result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign start_ready=!rst&&state==IDLE&&!recovery_required;
    assign busy=state!=IDLE||recovery_required;
    assign idle=state==IDLE&&!start_valid&&!recovery_required&&slot_idle;
    assign lock_valid=!rst&&state==LOCK_SEND;
    assign lock_base=pool_base;assign lock_bytes=pool_bytes;
    assign lock_result_ready=!rst&&state==LOCK_WAIT;
    assign unlock_valid=!rst&&state==UNLOCK;
    assign credit_owner=state==CREDIT_SEND||state==CREDIT_WAIT;
    assign memory_owner=busy&&!credit_owner;
    assign credit_valid=!rst&&state==CREDIT_SEND;
    assign credit_result_ready=!rst&&state==CREDIT_WAIT;
    assign credit_op=credit_step==0?4'd3:4'd4;
    assign credit_user=record_data[64+:USER_WIDTH];
    assign credit_stream=credit_step==2?31'd0:record_data[126:96];
    assign credit_generation=credit_step==2?32'd0:record_data[255:224];
    assign credit_address=credit_step==2?{MEMORY_ADDR_WIDTH{1'b0}}:record_address;
    assign credit_amount=credit_step==0?refund_bytes:32'd0;
    assign result_valid=!rst&&(state==RESULT||state==QUARANTINE&&!result_acked);
    assign recovery_address=record_address;
    task fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status);
        begin result_status<=status;result_detail<=detail;result_memory_status<=memory_status;
            recovery_required<=1;result_acked<=0;state<=QUARANTINE;end
    endtask
    initial begin
        if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>31)$error("Unsupported reclaim geometry");
    end
    integer load_bank;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;pool_base<=0;pool_bytes<=0;payload_base<=0;payload_bytes<=0;slot_bytes<=0;work_floor<=0;
            record_address<=0;payload_cursor<=0;word_index<=0;credit_step<=0;record_data<=0;
            cut_bytes<=0;copy_bytes<=0;copy_offset<=0;copy_data<=0;refund_bytes<=0;
            result_status<=0;result_detail<=0;result_memory_status<=0;recovery_required<=0;result_acked<=0;held_lock<=0;
        end else begin
            // Loss of the actual held pool proof never permits further work.
            // A compliant lock owner retains it until explicit unlock/reset.
            if(held_lock&&!lock_active&&state!=QUARANTINE)fail(6,0,0);
            else case(state)
                IDLE:if(start_valid&&start_ready)begin
                    pool_base<=cfg_pool_base;pool_bytes<=cfg_pool_bytes;payload_base<=cfg_payload_base;
                    payload_bytes<=cfg_payload_bytes;slot_bytes<=cfg_slot_bytes;work_floor<=cfg_work_floor;
                    record_address<=cfg_pool_base;payload_cursor<=cfg_payload_base;word_index<=0;record_data<=0;
                    result_status<=0;result_detail<=0;result_memory_status<=0;result_acked<=0;state<=CHECK;
                end
                CHECK:if(!geometry_good)fail(1,0,0);else state<=LOCK_SEND;
                LOCK_SEND:if(lock_ready)state<=LOCK_WAIT;
                LOCK_WAIT:if(lock_result_valid)begin
                    if(lock_status!=0)fail(7,lock_status,0);
                    else begin held_lock<=1;state<=READ_REQ;end
                end
                READ_REQ:if(payload_cursor<payload_base||slot_end>payload_end)fail(1,1,0);
                    else if(slot_ready)state<=READ_WAIT;
                READ_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(2,{5'd0,word_index},slot_status);
                    else begin
                        for(load_bank=0;load_bank<8;load_bank=load_bank+1)
                            if(word_index==load_bank)record_data[load_bank*64+:64]<=slot_data[63:0];
                        if(word_index==0&&slot_data[63:0]==0)state<=NEXT_RECORD;
                        else if(word_index==7)state<=VALIDATE;
                        else begin word_index<=word_index+1'b1;state<=READ_REQ;end
                    end
                end
                VALIDATE:begin
                    if(!record_good)fail(3,0,0);
                    else if(progress[163])state<=NEXT_RECORD; // Existing CLOSE handles a remote-ended RPC.
                    else if(!refund_good)fail(3,1,0);
                    else if(refund_value==0)state<=NEXT_RECORD;
                    else begin
                        refund_bytes<=refund_value[31:0];cut_bytes<=progress[63:32];
                        copy_bytes<=progress[127:96];copy_offset<=0;
                        record_data[287:256]<=progress[127:96];record_data[319:288]<=0;
                        record_data[453:421]<=completed_count;
                        state<=INVALIDATE_REQ;
                    end
                end
                INVALIDATE_REQ:if(slot_ready)state<=INVALIDATE_WAIT;
                INVALIDATE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(4,8,slot_status);
                    else if(copy_bytes!=0&&cut_bytes!=0)state<=COPY_READ_REQ;
                    else begin word_index<=4;state<=STATE_WRITE_REQ;end
                end
                COPY_READ_REQ:if(slot_ready)state<=COPY_READ_WAIT;
                COPY_READ_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(2,8,slot_status);
                    else begin copy_data<=slot_data[63:0];state<=COPY_WRITE_REQ;end
                end
                COPY_WRITE_REQ:if(slot_ready)state<=COPY_WRITE_WAIT;
                COPY_WRITE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(4,9,slot_status);
                    else if(remaining<=8)begin word_index<=4;state<=STATE_WRITE_REQ;end
                    else begin copy_offset<=copy_offset+8;state<=COPY_READ_REQ;end
                end
                STATE_WRITE_REQ:if(slot_ready)state<=STATE_WRITE_WAIT;
                STATE_WRITE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(4,{5'd0,word_index},slot_status);
                    else if(word_index==7)state<=COMMIT_REQ;
                    else begin word_index<=word_index+1'b1;state<=STATE_WRITE_REQ;end
                end
                COMMIT_REQ:if(slot_ready)state<=COMMIT_WAIT;
                COMMIT_WAIT:if(slot_valid)begin
                    if(slot_status!=0)fail(4,10,slot_status);
                    else begin credit_step<=0;state<=CREDIT_SEND;end
                end
                CREDIT_SEND:if(credit_ready)state<=CREDIT_WAIT;
                CREDIT_WAIT:if(credit_result_valid)begin
                    if(credit_status!=0)fail(5,credit_detail,credit_memory_status);
                    else if(credit_step==2)state<=NEXT_RECORD;
                    else begin credit_step<=credit_step+1'b1;state<=CREDIT_SEND;end
                end
                NEXT_RECORD:if({1'b0,record_address}+128<pool_end)begin
                    if(slot_end+{1'b0,slot_bytes}>payload_end)fail(1,2,0);
                    else begin record_address<=record_address+128;payload_cursor<=payload_cursor+slot_bytes;
                        word_index<=0;record_data<=0;state<=READ_REQ;end
                end else state<=UNLOCK;
                UNLOCK:if(unlock_ready)begin held_lock<=0;state<=RESULT;end
                RESULT:if(result_ready)state<=IDLE;
                QUARANTINE:if(result_ready)result_acked<=1;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
