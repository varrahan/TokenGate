`timescale 1ns/1ps
`default_nettype none
// Durable receive budgets and actual WINDOW_UPDATE retirement. The caller
// holds the connection and actual RPC binding/pool throughout each command.
// RELEASE requires actual consumption; CLOSE requires real buffer/GPU drain.
// FORMAT requires global link/directory/memory drain. No warm-reset replay.
// Separate runtime arenas: 64 bytes/connection and 32 bytes/actual RPC slot.
// 0 FORMAT_CONNECTION, 1 INIT_STREAM, 2 DEBIT_BOTH, 3 RELEASE_BOTH,
// 4 RETURN_CREDIT (stream zero selects connection), 5 CLOSE_STREAM,
// 6 DEBIT_CONNECTION, 7 RELEASE_CONNECTION, 8 READ, 9 RETIRE_CLOSED_RPC.
// Op 9 requires the actual successful directory CLOSE result held by the
// parent; the inactive RPC must still match the captured key/generation.
module http2_receive_credit_store #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,rst,
    input wire req_valid,output wire req_ready,input wire [3:0] req_op,
    input wire req_authority,req_maintenance,input wire [USER_WIDTH-1:0] req_user,
    input wire [30:0] req_stream,input wire [31:0] req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_record_address,input wire [31:0] req_amount,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_rpc_base,cfg_receive_connection_base,cfg_receive_stream_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_rpc_bytes,cfg_receive_connection_bytes,cfg_receive_stream_bytes,
    input wire context_write_busy,input wire [USER_WIDTH-1:0] context_write_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] context_write_address,
    input wire context_write_fault,input wire [USER_WIDTH-1:0] context_write_fault_user,
    input wire [MEMORY_ADDR_WIDTH-1:0] context_write_fault_address,input wire [7:0] context_write_fault_memory_status,
    output wire rsp_valid,input wire rsp_ready,output wire [3:0] rsp_op,
    output wire [USER_WIDTH-1:0] rsp_user,output wire [30:0] rsp_stream,
    output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,
    output reg rsp_connection_error,output reg [31:0] rsp_http2_error,
    output wire [31:0] rsp_connection_available,rsp_stream_available,rsp_connection_pending,rsp_stream_pending,
    output reg rsp_debit_authorized,rsp_wire_retired,output reg [31:0] rsp_update_bytes,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
);
    localparam IDLE=0,GEOMETRY=1,CHECK=2,READ_REQ=3,READ_WAIT=4,RAW_CHECK=5,CONNECTION_CHECK=6,
        RPC_CHECK=7,STREAM_CHECK=8,APPLY=9,WRITE_REQ=10,WRITE_WAIT=11,TX=12,RESULT=13,CONTEXT_WAIT=14;
    localparam RRAW=0,RCONNECTION=1,RRPC=2,RSTREAM=3;
    localparam WINIT_CONNECTION=0,WINIT_STREAM=1,WDEBIT=2,WRELEASE=3,WINTENT=4,WRETIRE=5,WCLOSE=6,WCONNECTION=7;
    localparam [31:0] RAW_MAGIC=32'h48324331,RPC_MAGIC=32'h47525331,
        CONNECTION_MAGIC=32'h48325243,STREAM_MAGIC=32'h48325253;
    reg [3:0] state,operation;reg authority,maintenance;
    reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id;reg [31:0] generation,amount;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,rpcs,connections,streams,work_floor,rpc_address;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,rpc_bytes,connection_bytes,stream_bytes;
    reg [63:0] ends[0:3];reg [63:0] context_full,connection_full,stream_full;
    wire [63:0] bases[0:3];assign bases[0]=contexts;assign bases[1]=rpcs;assign bases[2]=connections;assign bases[3]=streams;
    reg geometry_good;integer a,b,reset_bank;
    always @*begin
        geometry_good=1;
        for(a=0;a<4;a=a+1)begin
            if(bases[a]<work_floor||ends[a]>(64'd1<<MEMORY_ADDR_WIDTH))geometry_good=0;
            for(b=a+1;b<4;b=b+1)if(!(ends[a]<=bases[b]||ends[b]<=bases[a]))geometry_good=0;
        end
    end
    wire [MEMORY_ADDR_WIDTH-1:0] context_address=context_full[MEMORY_ADDR_WIDTH-1:0];
    wire [MEMORY_ADDR_WIDTH-1:0] connection_address=connection_full[MEMORY_ADDR_WIDTH-1:0];
    wire [MEMORY_ADDR_WIDTH-1:0] stream_address=stream_full[MEMORY_ADDR_WIDTH-1:0];
    wire stream_command=stream_id!=0;
    wire rpc_address_good=rpc_address>=rpcs&&{1'b0,rpc_address}+64'd128<=ends[1]&&((rpc_address-rpcs)&127)==0;
    wire config_good=geometry_good&&context_bytes>=256&&context_bytes[7:0]==0&&rpc_bytes>=128&&rpc_bytes[6:0]==0&&
        connection_bytes>=(context_bytes>>2)&&connection_bytes[5:0]==0&&stream_bytes>=(rpc_bytes>>2)&&stream_bytes[4:0]==0&&
        context_full+256<=ends[0]&&connection_full+64<=ends[2]&&(!stream_command||stream_full+32<=ends[3]);
    reg [63:0] raw_header;reg [511:0] connection_record;reg [255:0] rpc_record,stream_record;
    wire [31:0] connection_available=connection_record[95:64],initial_stream=connection_record[127:96];
    wire [31:0] connection_pending=connection_record[159:128],connection_intent=connection_record[191:160];
    wire [31:0] stream_available=stream_record[95:64],stream_pending=stream_record[159:128],stream_intent=stream_record[191:160];
    wire [31:0] stream_limit=stream_record[223:192];wire stream_closed=stream_record[127];
    wire [15:0] owner16=owner;
    wire [31:0] contexts32=contexts,rpcs32=rpcs,connections32=connections,streams32=streams;
    wire [31:0] context_bytes32=context_bytes,rpc_bytes32=rpc_bytes,connection_bytes32=connection_bytes,stream_bytes32=stream_bytes;
    wire connection_good=connection_record[63:0]=={16'd0,owner16,CONNECTION_MAGIC}&&!connection_available[31]&&!initial_stream[31]&&
        {2'd0,connection_available}+{2'd0,connection_pending}+{2'd0,connection_intent}<=34'd65535&&
        connection_record[255:192]=={context_bytes32,contexts32}&&connection_record[319:256]=={rpc_bytes32,rpcs32}&&
        connection_record[383:320]=={connection_bytes32,connections32}&&connection_record[447:384]=={stream_bytes32,streams32}&&connection_record[511:448]==0;
    wire rpc_identity=rpc_record[79:64]==owner16&&rpc_record[127:96]=={1'b0,stream_id}&&rpc_record[255:224]==generation&&generation!=0;
    wire rpc_good=rpc_record[31:0]==RPC_MAGIC&&rpc_record[32]&&rpc_record[63:35]==0&&rpc_identity;
    wire retired_rpc_good=rpc_record[63:0]==0&&rpc_identity;
    wire stream_good=stream_record[63:0]=={generation,STREAM_MAGIC}&&stream_record[126:96]==stream_id&&stream_record[255:224]==0&&
        !stream_available[31]&&!stream_limit[31]&&{2'd0,stream_available}+{2'd0,stream_pending}+{2'd0,stream_intent}<={2'd0,stream_limit};
    wire [33:0] connection_outstanding=34'd65535-{2'd0,connection_available}-{2'd0,connection_pending}-{2'd0,connection_intent};
    wire [33:0] stream_outstanding={2'd0,stream_limit}-{2'd0,stream_available}-{2'd0,stream_pending}-{2'd0,stream_intent};
    wire [31:0] pending_selected=stream_command?stream_pending:connection_pending;
    wire [31:0] update_amount=amount==0||amount>pending_selected?pending_selected:amount;
    wire writer_busy=context_write_busy&&context_write_user==owner&&context_write_address==context_address;
    wire writer_fault=context_write_fault&&context_write_fault_user==owner&&context_write_fault_address==context_address;
    reg raw_read_overlap;
    reg [USER_WIDTH-1:0] recovery_user;
    reg [4*MEMORY_ADDR_WIDTH-1:0] recovery_bases;
    reg [4*(MEMORY_ADDR_WIDTH+1)-1:0] recovery_sizes;
    reg [MEMORY_ADDR_WIDTH-1:0] recovery_connection,recovery_floor;
    wire recovery_scope=owner==recovery_user&&connection_address==recovery_connection&&work_floor==recovery_floor&&
        {contexts,rpcs,connections,streams}==recovery_bases&&{context_bytes,rpc_bytes,connection_bytes,stream_bytes}==recovery_sizes;
    reg [1:0] read_phase;reg [3:0] read_index,read_count,write_index;
    reg [MEMORY_ADDR_WIDTH-1:0] read_address;reg [2:0] write_mode;
    wire [63:0] connection_words[0:7],stream_words[0:3];
    generate for(genvar n=0;n<8;n=n+1)begin: connection_banks assign connection_words[n]=connection_record[n*64+:64];end endgenerate
    generate for(genvar n=0;n<4;n=n+1)begin: stream_banks assign stream_words[n]=stream_record[n*64+:64];end endgenerate
    reg [63:0] write_word;reg [MEMORY_ADDR_WIDTH-1:0] write_address;reg write_last;
    always @*begin
        write_word=0;write_address=connection_address;write_last=1;
        case(write_mode)
            WINIT_CONNECTION:begin
                write_last=write_index==8;write_address=connection_address+((write_index==0||write_index==8)?0:write_index*8);
                write_word=write_index==0?64'd0:write_index==8?connection_words[0]:connection_words[write_index[2:0]];
            end
            WINIT_STREAM:begin
                write_last=write_index==4;write_address=stream_address+((write_index==0||write_index==4)?0:write_index*8);
                write_word=write_index==0?64'd0:write_index==4?stream_words[0]:stream_words[write_index[1:0]];
            end
            WDEBIT:begin write_last=write_index==1;write_address=(write_index==0?connection_address:stream_address)+8;write_word=write_index==0?connection_words[1]:stream_words[1];end
            WRELEASE:begin write_last=write_index==1;write_address=(write_index==0?connection_address:stream_address)+16;write_word=write_index==0?connection_words[2]:stream_words[2];end
            WINTENT:begin write_address=(stream_command?stream_address:connection_address)+16;write_word=stream_command?stream_words[2]:connection_words[2];end
            WRETIRE:begin write_last=write_index==1;write_address=(stream_command?stream_address:connection_address)+(write_index==0?8:16);write_word=stream_command?(write_index==0?stream_words[1]:stream_words[2]):(write_index==0?connection_words[1]:connection_words[2]);end
            WCLOSE:begin write_last=write_index==2;write_address=write_index==0?connection_address+16:stream_address+(write_index==1?8:16);write_word=write_index==0?connection_words[2]:write_index==1?stream_words[1]:stream_words[2];end
            WCONNECTION:begin write_address=connection_address+(operation==6?8:16);write_word=operation==6?connection_words[1]:connection_words[2];end
        endcase
    end
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire [MEMORY_ADDR_WIDTH-1:0] read_word_address=read_address+read_index*8;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==READ_REQ||state==WRITE_REQ),.req_ready(slot_ready),.req_write(state==WRITE_REQ),
        .req_addr(state==WRITE_REQ?write_address:read_word_address),.req_bytes(4'd8),.req_data({8'd0,write_word}),
        .result_valid(slot_valid),.result_ready(state==READ_WAIT||state==WRITE_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign req_ready=!rst&&state==IDLE;assign rsp_valid=state==RESULT;assign rsp_op=operation;assign rsp_user=owner;assign rsp_stream=stream_id;
    assign rsp_connection_available=connection_available;assign rsp_stream_available=stream_command?stream_available:0;
    assign rsp_connection_pending=connection_pending;assign rsp_stream_pending=stream_command?stream_pending:0;
    assign idle=state==IDLE&&slot_idle&&!req_valid;
    reg [511:0] update_packet;
    integer lane;
    always @*begin
        update_packet=0;update_packet[23:16]=4;update_packet[31:24]=8;
        for(lane=0;lane<4;lane=lane+1)begin
            update_packet[40+lane*8+:8]=({1'b0,stream_id}>>(24-8*lane));
            update_packet[72+lane*8+:8]=(rsp_update_bytes>>(24-8*lane));
        end
    end
    assign m_axis_tx_tdata=update_packet;assign m_axis_tx_tkeep=64'h1fff;
    assign m_axis_tx_tvalid=!rst&&state==TX;assign m_axis_tx_tlast=1;assign m_axis_tx_tuser=owner;
    task fail(input [7:0] status,input [7:0] detail,input [31:0] error,input connection_error);
        begin rsp_status<=status;rsp_detail<=detail;rsp_http2_error<=error;rsp_connection_error<=connection_error;rsp_debit_authorized<=0;state<=RESULT;end
    endtask
    task quarantine(input [7:0] detail,input [MEMORY_ADDR_WIDTH-1:0] address,input [7:0] memory_status);
        begin recovery_required<=1;recovery_address<=address;rsp_memory_status<=memory_status;
            recovery_user<=owner;recovery_connection<=connection_address;recovery_floor<=work_floor;
            recovery_bases<={contexts,rpcs,connections,streams};recovery_sizes<={context_bytes,rpc_bytes,connection_bytes,stream_bytes};
            fail(5,detail,2,1);end
    endtask
    task read_words(input [1:0] phase,input [MEMORY_ADDR_WIDTH-1:0] address,input [3:0] count);
        begin read_phase<=phase;read_address<=address;read_count<=count;read_index<=0;state<=READ_REQ;
            if(phase==RRAW)raw_read_overlap<=writer_busy;
        end
    endtask
    task write_words(input [2:0] mode);
        begin write_mode<=mode;write_index<=0;state<=WRITE_REQ;end
    endtask
    initial begin if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<10||MEMORY_ADDR_WIDTH>31)$error("Unsupported receive-credit widths");end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;operation<=0;authority<=0;maintenance<=0;owner<=0;stream_id<=0;generation<=0;amount<=0;
            contexts<=0;rpcs<=0;connections<=0;streams<=0;work_floor<=0;rpc_address<=0;
            context_bytes<=0;rpc_bytes<=0;connection_bytes<=0;stream_bytes<=0;context_full<=0;connection_full<=0;stream_full<=0;
            for(reset_bank=0;reset_bank<4;reset_bank=reset_bank+1)ends[reset_bank]<=0;
            raw_header<=0;connection_record<=0;rpc_record<=0;stream_record<=0;raw_read_overlap<=0;
            read_phase<=0;read_index<=0;read_count<=0;write_index<=0;read_address<=0;write_mode<=0;
            rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;
            rsp_debit_authorized<=0;rsp_wire_retired<=0;rsp_update_bytes<=0;recovery_required<=0;recovery_address<=0;
            recovery_user<=0;recovery_connection<=0;recovery_floor<=0;recovery_bases<=0;recovery_sizes<=0;
        end else begin
            if(writer_busy&&read_phase==RRAW&&(state==READ_REQ||state==READ_WAIT||state==RAW_CHECK))raw_read_overlap<=1;
            case(state)
                IDLE:if(req_valid&&req_ready)begin
                    operation<=req_op;authority<=req_authority;maintenance<=req_maintenance;owner<=req_user;stream_id<=req_stream;
                    generation<=req_generation;amount<=req_amount;rpc_address<=req_record_address;
                    contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;rpcs<=cfg_rpc_base;rpc_bytes<=cfg_rpc_bytes;
                    connections<=cfg_receive_connection_base;connection_bytes<=cfg_receive_connection_bytes;
                    streams<=cfg_receive_stream_base;stream_bytes<=cfg_receive_stream_bytes;work_floor<=cfg_work_floor;
                    rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;
                    rsp_debit_authorized<=0;rsp_wire_retired<=0;rsp_update_bytes<=0;connection_record<=0;stream_record<=0;state<=GEOMETRY;
                end
                GEOMETRY:begin
                    ends[0]<={1'b0,contexts}+{1'b0,context_bytes};ends[1]<={1'b0,rpcs}+{1'b0,rpc_bytes};
                    ends[2]<={1'b0,connections}+{1'b0,connection_bytes};ends[3]<={1'b0,streams}+{1'b0,stream_bytes};
                    context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);
                    connection_full<={1'b0,connections}+({{(64-USER_WIDTH){1'b0}},owner}<<6);
                    stream_full<={1'b0,streams}+(({1'b0,rpc_address}-{1'b0,rpcs})>>2);state<=CHECK;
                end
                CHECK:if(!authority)fail(7,1,2,1);
                    else if(operation==0&&!maintenance)fail(7,2,2,1);
                    else if(operation>9||!config_good)fail(2,1,2,1);
                    else if(recovery_required&&(operation!=0||!recovery_scope))fail(6,1,2,1);
                    else if((operation==1||operation==2||operation==3||operation==5||operation==9)&&!stream_command||
                        (operation==0||operation==6||operation==7)&&stream_command||
                        stream_command&&!rpc_address_good||!stream_command&&(generation!=0||rpc_address!=0))fail(2,2,2,1);
                    else if((operation==2||operation==6)&&amount>24'hffffff||operation!=0&&amount[31])fail(2,3,2,1);
                    else if((operation==1||operation==5||operation==8||operation==9)&&amount!=0)fail(2,6,2,1);
                    else read_words(RRAW,context_address,1);
                READ_REQ:if(slot_ready)state<=READ_WAIT;
                READ_WAIT:if(slot_valid)begin
                    if(slot_status!=0)quarantine(1,read_address+read_index*8,slot_status);
                    else begin
                        case(read_phase)
                            RRAW:raw_header<=slot_data[63:0];
                            RCONNECTION:connection_record[read_index*64+:64]<=slot_data[63:0];
                            RRPC:rpc_record[read_index*64+:64]<=slot_data[63:0];
                            RSTREAM:stream_record[read_index*64+:64]<=slot_data[63:0];
                        endcase
                        if(read_index+1==read_count)case(read_phase)
                            RRAW:state<=RAW_CHECK;RCONNECTION:state<=CONNECTION_CHECK;RRPC:state<=RPC_CHECK;RSTREAM:state<=STREAM_CHECK;
                        endcase else begin read_index<=read_index+1'b1;state<=READ_REQ;end
                    end
                end
                CONTEXT_WAIT:if(writer_fault)quarantine(13,context_address,context_write_fault_memory_status);
                    else if(!writer_busy)read_words(RRAW,context_address,1);
                RAW_CHECK:if(writer_fault)quarantine(13,context_address,context_write_fault_memory_status);
                    else if(writer_busy||raw_read_overlap)state<=CONTEXT_WAIT;
                    else if(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])fail(3,1,2,1);
                    else if(operation==0)begin
                        if(amount[31])fail(2,3,2,1);
                        else begin
                            connection_record<={64'd0,{stream_bytes32,streams32},{connection_bytes32,connections32},
                                {rpc_bytes32,rpcs32},{context_bytes32,contexts32},64'd0,{amount,32'd65535},{16'd0,owner16,CONNECTION_MAGIC}};
                            write_words(WINIT_CONNECTION);
                        end
                    end else read_words(RCONNECTION,connection_address,8);
                CONNECTION_CHECK:if(!connection_good)quarantine(2,connection_address,0);
                    else if(connection_intent!=0)quarantine(3,connection_address+16,0);
                    else if(stream_command)read_words(RRPC,rpc_address,4);
                    else state<=APPLY;
                RPC_CHECK:if(operation==9?!retired_rpc_good:!rpc_good)fail(3,2,2,1);else read_words(RSTREAM,stream_address,4);
                STREAM_CHECK:if(operation==1)begin
                        if(stream_record!=0&&!(stream_record[31:0]==STREAM_MAGIC&&stream_record[63:32]<generation&&stream_closed&&stream_intent==0))fail(3,3,2,1);
                        else begin stream_record<={{32'd0,initial_stream},64'd0,{{1'b0,stream_id},initial_stream},{generation,STREAM_MAGIC}};write_words(WINIT_STREAM);end
                    end else if(!stream_good)quarantine(4,stream_address,0);
                    else if(stream_intent!=0)quarantine(5,stream_address+16,0);
                    else if(stream_closed&&operation!=5&&operation!=8&&operation!=9)fail(3,4,5,1);
                    else state<=APPLY;
                APPLY:case(operation)
                    2,6:if(amount>connection_available)fail(4,1,3,1);
                        else if(operation==2&&amount>stream_available)fail(4,2,3,0);
                        else begin connection_record[95:64]<=connection_available-amount;
                            if(operation==2)begin stream_record[95:64]<=stream_available-amount;write_words(WDEBIT);end else write_words(WCONNECTION);
                        end
                    3,7:if({2'd0,amount}>connection_outstanding||operation==3&&{2'd0,amount}>stream_outstanding)fail(2,4,2,1);
                        else begin connection_record[159:128]<=connection_pending+amount;
                            if(operation==3)begin stream_record[159:128]<=stream_pending+amount;write_words(WRELEASE);end else write_words(WCONNECTION);
                        end
                    4:if(update_amount==0)state<=RESULT;
                        else begin
                            rsp_update_bytes<=update_amount;
                            if(stream_command)begin stream_record[159:128]<=stream_pending-update_amount;stream_record[191:160]<=update_amount;end
                            else begin connection_record[159:128]<=connection_pending-update_amount;connection_record[191:160]<=update_amount;end
                            write_words(WINTENT);
                        end
                    5,9:if(stream_closed)state<=RESULT;
                        else if(stream_outstanding>connection_outstanding)quarantine(6,stream_address,0);
                        else begin connection_record[159:128]<=connection_pending+stream_outstanding[31:0];stream_record[127]<=1;stream_record[159:128]<=0;write_words(WCLOSE);end
                    8:state<=RESULT;
                    default:fail(2,5,2,1);
                endcase
                WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
                WRITE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)quarantine(7,write_address,slot_status);
                    else if(!write_last)begin write_index<=write_index+1'b1;state<=WRITE_REQ;end
                    else if(write_mode==WINTENT)state<=TX;
                    else begin
                        if(operation==0)begin recovery_required<=0;recovery_address<=0;end
                        if(operation==2||operation==6)rsp_debit_authorized<=1;
                        state<=RESULT;
                    end
                end
                TX:if(m_axis_tx_tready)begin
                    rsp_wire_retired<=1;
                    if(stream_command)begin stream_record[95:64]<=stream_available+stream_intent;stream_record[191:160]<=0;end
                    else begin connection_record[95:64]<=connection_available+connection_intent;connection_record[191:160]<=0;end
                    write_words(WRETIRE);
                end
                RESULT:if(rsp_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
