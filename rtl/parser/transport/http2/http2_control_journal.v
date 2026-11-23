`timescale 1ns/1ps
`default_nettype none
// Connection-owned tentative control log. The parent holds actual connection
// ownership, validates disjoint work arenas, and supplies packet commit only
// after raw/HPACK/admission success. Consumer READY acknowledges a durable
// effect; consume_status != 0 quarantines without replay/refund. Maintenance
// FORMAT requires connection/GPU/memory fences. It never repairs live RPCs.
// Context bytes 216..255: header, head/tail, slot, arena, packet sequence.
// Records are 32 bytes; one ring record stays empty. Partial control frames
// survive packet commit, and no record is released until its complete frame
// has been scanned. Raw-control interpretation and ACK transmission are separate.
module http2_control_journal #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire start_format,start_maintenance,start_authority,
    input wire [USER_WIDTH-1:0] start_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_journal_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_journal_bytes,cfg_slot_bytes,
    input wire s_valid,output wire s_ready,input wire [3:0] s_kind,input wire [7:0] s_data,
    input wire [31:0] s_arg0,s_arg1,input wire [23:0] s_length,input wire [7:0] s_type,s_flags,
    input wire [30:0] s_stream,input wire [USER_WIDTH-1:0] s_user,
    input wire finish_valid,output wire finish_ready,input wire finish_commit,
    output wire m_valid,input wire m_ready,input wire [7:0] consume_status,
    output wire [3:0] m_kind,output wire [7:0] m_data,output wire [31:0] m_arg0,m_arg1,
    output wire [23:0] m_length,output wire [7:0] m_type,m_flags,
    output wire [30:0] m_stream,output wire [USER_WIDTH-1:0] m_user,
    output wire result_valid,input wire result_ready,output reg [7:0] result_status,result_detail,result_memory_status,
    output wire [USER_WIDTH-1:0] result_user,output reg result_committed,
    output reg [31:0] result_records,result_frames,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire idle,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status
);
    localparam IDLE=0,GEOMETRY=1,CHECK=2,READ_REQ=3,READ_WAIT=4,RAW_CHECK=5,ROOT_CHECK=6,
        RUN=7,WRITE_REQ=8,WRITE_WAIT=9,SCAN=10,RECORD_CHECK=11,EMIT=12,RESULT=13;
    localparam RRAW=0,RROOT=1,RSCAN=2,RREPLAY=3;
    localparam WRECORD=0,WROOT=1;
    localparam [31:0] RAW_MAGIC=32'h48324331,ROOT_MAGIC=32'h48324a31,ENTRY_MAGIC=32'h48324a45;
    reg [3:0] state;reg [1:0] read_mode;reg write_mode,formatting,maintenance,authority,after_root_replay;
    reg [USER_WIDTH-1:0] owner,recovery_owner;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,journal,work_floor,context_address,slot_address,read_address,recovery_context;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,journal_bytes,slot_bytes;
    reg [63:0] context_full,context_limit,contexts_end,journal_end,slot_full,slot_limit,raw_header;
    reg [319:0] root_record;reg [255:0] entry_record;
    reg [31:0] head,tail,working_tail,cursor,frame_end,write_offset;
    reg [2:0] word_index,read_last;
    reg scan_active;reg [7:0] scan_type,scan_flags;reg [23:0] scan_length;reg [30:0] scan_stream;
    wire [15:0] owner16=owner;
    wire [31:0] journal32=journal,journal_bytes32=journal_bytes,slot32=slot_address,slot_bytes32=slot_bytes;
    wire config_good=context_bytes>=256&&context_bytes[7:0]==0&&slot_bytes>=64&&slot_bytes[4:0]==0&&
        contexts>=work_floor&&journal>=work_floor&&contexts_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        journal_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&context_limit<=contexts_end&&slot_limit<=journal_end&&
        (contexts_end<=journal||journal_end<=contexts);
    wire root_good=root_record[63:0]=={16'd0,owner16,ROOT_MAGIC}&&root_record[319:288]==0&&
        root_record[127:96]<slot_bytes&&root_record[95:64]<slot_bytes&&root_record[100:96]==0&&root_record[68:64]==0&&
        root_record[191:128]=={slot_bytes32,slot32}&&root_record[255:192]=={journal_bytes32,journal32};
    function [31:0] advance(input [31:0] offset);
        begin advance={1'b0,offset}+33'd32=={1'b0,slot_bytes}?32'd0:offset+32'd32;end
    endfunction
    wire selected_type=s_type==3||s_type==4||s_type==6||s_type==7||s_type==8;
    wire selected=selected_type&&(s_kind==0||s_kind==3||s_kind>=4&&s_kind<=8);
    wire [31:0] next_tail=advance(working_tail),next_cursor=advance(cursor);
    wire [3:0] entry_kind=entry_record[3:0];
    wire [7:0] entry_type=entry_record[19:12],entry_flags=entry_record[27:20];
    wire [30:0] entry_stream=entry_record[58:28];wire [23:0] entry_length=entry_record[167:144];
    wire entry_good=entry_record[63:59]==0&&entry_record[191:168]==0&&entry_record[143:128]==owner16&&
        entry_record[223:192]==ENTRY_MAGIC&&entry_record[255:224]==cursor&&
        (entry_type==3||entry_type==4||entry_type==6||entry_type==7||entry_type==8)&&
        (entry_kind==0||entry_kind==3||entry_kind>=4&&entry_kind<=8);
    wire entry_frame=entry_type==scan_type&&entry_flags==scan_flags&&entry_length==scan_length&&entry_stream==scan_stream;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire [63:0] root_words[0:4],entry_words[0:3];
    generate for(genvar i=0;i<5;i=i+1)begin: roots assign root_words[i]=root_record[i*64+:64];end endgenerate
    generate for(genvar i=0;i<4;i=i+1)begin: entries assign entry_words[i]=entry_record[i*64+:64];end endgenerate
    wire [63:0] write_word=write_mode==WRECORD?entry_words[word_index]:word_index==0?64'd0:word_index==5?root_record[63:0]:root_words[word_index];
    wire [MEMORY_ADDR_WIDTH-1:0] write_address=write_mode==WRECORD?slot_address+write_offset+word_index*8:
        context_address+216+((word_index==0||word_index==5)?0:word_index*8);
    wire [MEMORY_ADDR_WIDTH-1:0] command_address=state==WRITE_REQ?write_address:read_address+word_index*8;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==READ_REQ||state==WRITE_REQ),.req_ready(slot_ready),.req_write(state==WRITE_REQ),
        .req_addr(command_address),.req_bytes(4'd8),.req_data(state==WRITE_REQ?{8'd0,write_word}:72'd0),
        .result_valid(slot_valid),.result_ready(state==READ_WAIT||state==WRITE_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign start_ready=!rst&&state==IDLE;assign s_ready=!rst&&state==RUN&&!finish_valid;
    assign finish_ready=!rst&&state==RUN;assign result_valid=state==RESULT;assign result_user=owner;
    assign m_valid=!rst&&state==EMIT;assign m_kind=entry_kind;assign m_data=entry_record[11:4];
    assign m_type=entry_type;assign m_flags=entry_flags;assign m_stream=entry_stream;assign m_length=entry_length;
    assign m_arg0=entry_record[95:64];assign m_arg1=entry_record[127:96];assign m_user=owner;
    assign idle=state==IDLE&&slot_idle&&!start_valid;
    task fail(input [7:0] status,input [7:0] detail);
        begin result_status<=status;result_detail<=detail;result_committed<=0;state<=RESULT;end
    endtask
    task quarantine(input [7:0] status,input [7:0] detail,input [MEMORY_ADDR_WIDTH-1:0] address);
        begin recovery_required<=1;recovery_address<=address;recovery_context<=context_address;recovery_owner<=owner;fail(status,detail);end
    endtask
    task load(input [1:0] mode,input [MEMORY_ADDR_WIDTH-1:0] address,input [2:0] last);
        begin read_mode<=mode;read_address<=address;read_last<=last;word_index<=0;state<=READ_REQ;end
    endtask
    task save_root(input replay);
        begin write_mode<=WROOT;word_index<=0;after_root_replay<=replay;state<=WRITE_REQ;end
    endtask
    integer bank;
    initial begin if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<10||MEMORY_ADDR_WIDTH>31)$error("Unsupported journal widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;read_mode<=0;write_mode<=0;formatting<=0;maintenance<=0;authority<=0;after_root_replay<=0;owner<=0;recovery_owner<=0;
            contexts<=0;journal<=0;work_floor<=0;context_address<=0;slot_address<=0;read_address<=0;recovery_context<=0;
            context_bytes<=0;journal_bytes<=0;slot_bytes<=0;context_full<=0;context_limit<=0;contexts_end<=0;journal_end<=0;slot_full<=0;slot_limit<=0;
            raw_header<=0;root_record<=0;entry_record<=0;head<=0;tail<=0;working_tail<=0;cursor<=0;frame_end<=0;write_offset<=0;word_index<=0;read_last<=0;
            scan_active<=0;scan_type<=0;scan_flags<=0;scan_length<=0;scan_stream<=0;
            result_status<=0;result_detail<=0;result_memory_status<=0;result_committed<=0;result_records<=0;result_frames<=0;
            recovery_required<=0;recovery_address<=0;
        end else case(state)
            IDLE:if(start_valid&&start_ready)begin
                owner<=start_user;formatting<=start_format;maintenance<=start_maintenance;authority<=start_authority;
                contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;journal<=cfg_journal_base;journal_bytes<=cfg_journal_bytes;
                slot_bytes<=cfg_slot_bytes;work_floor<=cfg_work_floor;
                result_status<=0;result_detail<=0;result_memory_status<=0;result_committed<=0;result_records<=0;result_frames<=0;state<=GEOMETRY;
            end
            GEOMETRY:begin
                context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);
                context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;
                contexts_end<={1'b0,contexts}+{1'b0,context_bytes};journal_end<={1'b0,journal}+{1'b0,journal_bytes};
                slot_full<={1'b0,journal}+{{(64-USER_WIDTH){1'b0}},owner}*{1'b0,slot_bytes};
                slot_limit<={1'b0,journal}+({{(64-USER_WIDTH){1'b0}},owner}+64'd1)*{1'b0,slot_bytes};state<=CHECK;
            end
            CHECK:begin
                context_address<=context_full[MEMORY_ADDR_WIDTH-1:0];slot_address<=slot_full[MEMORY_ADDR_WIDTH-1:0];
                if(!config_good)fail(2,1);
                else if(!authority||formatting&&!maintenance)fail(7,1);
                else if(recovery_required&&!(formatting&&maintenance&&owner==recovery_owner&&context_full==recovery_context))fail(6,1);
                else load(RRAW,context_full[MEMORY_ADDR_WIDTH-1:0],0);
            end
            READ_REQ:if(slot_ready)state<=READ_WAIT;
            READ_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin result_memory_status<=slot_status;quarantine(5,1,read_address+word_index*8);end
                else begin
                    case(read_mode)
                        RRAW:raw_header<=slot_data[63:0];
                        RROOT:for(bank=0;bank<5;bank=bank+1)if(word_index==bank)root_record[bank*64+:64]<=slot_data[63:0];
                        default:for(bank=0;bank<4;bank=bank+1)if(word_index==bank)entry_record[bank*64+:64]<=slot_data[63:0];
                    endcase
                    if(word_index==read_last)state<=read_mode==RRAW?RAW_CHECK:read_mode==RROOT?ROOT_CHECK:RECORD_CHECK;
                    else begin word_index<=word_index+1'b1;state<=READ_REQ;end
                end
            end
            RAW_CHECK:if(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])fail(3,1);
                else if(formatting)begin
                    root_record<={64'd0,{journal_bytes32,journal32},{slot_bytes32,slot32},64'd0,{16'd0,owner16,ROOT_MAGIC}};
                    head<=0;tail<=0;working_tail<=0;save_root(0);
                end else load(RROOT,context_address+216,4);
            ROOT_CHECK:if(!root_good)quarantine(3,2,context_address+216);
                else begin head<=root_record[95:64];tail<=root_record[127:96];working_tail<=root_record[127:96];state<=RUN;end
            RUN:if(finish_valid&&finish_ready)begin
                if(!finish_commit)state<=RESULT;
                else begin
                    root_record[127:96]<=working_tail;root_record[287:256]<=root_record[287:256]+1'b1;tail<=working_tail;
                    save_root(1);
                end
            end else if(s_valid&&s_ready)begin
                if(s_user!=owner)quarantine(4,1,context_address+216);
                else if(selected)begin
                    if(next_tail==head)quarantine(4,2,context_address+216);
                    else begin
                        entry_record<={{working_tail,ENTRY_MAGIC},{24'd0,s_length,owner16},{s_arg1,s_arg0},{5'd0,s_stream,s_flags,s_type,s_data,s_kind}};
                        write_offset<=working_tail;write_mode<=WRECORD;word_index<=0;state<=WRITE_REQ;
                    end
                end
            end
            WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
            WRITE_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin result_memory_status<=slot_status;quarantine(5,2,write_address);end
                else if(write_mode==WRECORD&&word_index==3)begin working_tail<=next_tail;state<=RUN;end
                else if(write_mode==WROOT&&word_index==5)begin
                    if(formatting)begin recovery_required<=0;recovery_address<=0;state<=RESULT;end
                    else if(after_root_replay)begin cursor<=head;scan_active<=0;state<=SCAN;end
                    else state<=RESULT;
                end else begin word_index<=word_index+1'b1;state<=WRITE_REQ;end
            end
            SCAN:if(cursor==tail)begin result_committed<=1;state<=RESULT;end
                else load(RSCAN,slot_address+cursor,3);
            RECORD_CHECK:if(!entry_good)quarantine(3,3,slot_address+cursor);
                else if(read_mode==RREPLAY)state<=EMIT;
                else if(entry_kind==0)begin
                    if(scan_active)quarantine(3,4,slot_address+cursor);
                    else begin scan_active<=1;scan_type<=entry_type;scan_flags<=entry_flags;scan_length<=entry_length;scan_stream<=entry_stream;
                        cursor<=next_cursor;state<=SCAN;end
                end else if(!scan_active||!entry_frame)quarantine(3,5,slot_address+cursor);
                else if(entry_kind==3)begin frame_end<=next_cursor;cursor<=head;load(RREPLAY,slot_address+head,3);end
                else begin cursor<=next_cursor;state<=SCAN;end
            EMIT:if(m_ready)begin
                if(consume_status!=0)quarantine(8,consume_status,slot_address+cursor);
                else begin
                    result_records<=result_records+1'b1;
                    if(next_cursor==frame_end)begin
                        result_frames<=result_frames+1'b1;head<=frame_end;root_record[95:64]<=frame_end;save_root(1);
                    end else begin cursor<=next_cursor;load(RREPLAY,slot_address+next_cursor,3);end
                end
            end
            RESULT:if(result_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
