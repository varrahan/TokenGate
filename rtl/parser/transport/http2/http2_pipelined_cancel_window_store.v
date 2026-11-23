`timescale 1ns/1ps
`default_nettype none
// Durable outbound windows over runtime-sized external pools. The caller owns
// actual directory authority and excludes RPC binding mutations for the command
// lifetime (the whole pool for INITIAL_WINDOW). No fixed stream array exists.
// CLOSE_SEND_KEY (10) resolves the real stream and persists send closure without retiring its RPC.
// It requires zero caller address, generation and amount; success returns the actual closed binding.
// WINDOW_UPDATE_KEY accepts only connection/stream/increment; address and generation must be zero.
// The actual pool remains owned for lookup, binding validation, debit/update and result ACK.
// Missing key status 3/detail 10 is neutral: parent classifies idle versus closed in wire order.
// Window bit 127 persists send closure without retiring the actual RPC.
// CLOSE_SEND is idempotent; settings skip these windows; no DATA is granted.
// RESERVE publishes a grant only after BOTH debits acknowledge. NO_CREDIT is a
// completed operation, so its caller can process incoming WINDOW_UPDATE traffic.
// Reset and maintenance require the connection/GPU/memory ownership fence.
module http2_pipelined_cancel_window_store #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire [3:0] req_op,
    input wire req_authority,req_maintenance,input wire [USER_WIDTH-1:0] req_user,
    input wire [30:0] req_stream,input wire [31:0] req_generation,
    input wire [MEMORY_ADDR_WIDTH-1:0] req_record_address,input wire [31:0] req_amount,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_stream_base,cfg_window_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_stream_bytes,cfg_window_bytes,
    output wire rsp_valid,input wire rsp_ready,output wire [3:0] rsp_op,
    output wire [USER_WIDTH-1:0] rsp_user,output wire [30:0] rsp_stream,
    output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,
    output reg rsp_connection_error,output reg [31:0] rsp_http2_error,
    output reg [23:0] rsp_grant_bytes,output reg [31:0] rsp_connection_window,rsp_initial_window,
    output reg [31:0] rsp_stream_window,output reg [23:0] rsp_max_frame_bytes,
    output reg [31:0] rsp_affected_streams,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire idle,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status
,
    output wire  rsp_binding_valid,
    output wire [MEMORY_ADDR_WIDTH-1:0] rsp_record_address,
    output wire [31:0] rsp_generation,
    output wire  rsp_send_closed
);
    localparam IDLE=0,CHECK=1,READ_REQ=2,READ_WAIT=3,RAW_CHECK=4,CONN_CHECK=5,
        RPC_CHECK=6,WINDOW_CHECK=7,CALCULATE=8,SCAN_NEXT=9,WRITE_REQ=10,WRITE_WAIT=11,RESULT=12,GEOMETRY=13,RESERVE_APPLY=14;
    localparam INIT_CONNECTION=0,INIT_STREAM=1,WINDOW_UPDATE=2,INITIAL_WINDOW=3,
        MAX_FRAME=4,RESERVE=5,READ_WINDOW=6,CLOSE_CONNECTION=7,CLOSE_SEND=8,WINDOW_UPDATE_KEY=9,CLOSE_SEND_KEY=10;
    localparam RRAW=0,RCONN=1,RRPC=2,RWINDOW=3;
    localparam WINIT_CONN=0,WINIT_STREAM=1,WCONN=2,WMAX=3,WSTREAM=4,WRESERVE=5,WCLOSE=6;
    localparam [31:0] RAW_MAGIC=32'h48324331,RPC_MAGIC=32'h47525331,
        CONN_MAGIC=32'h48324357,STREAM_MAGIC=32'h48325357;
    reg [3:0] state,op;reg [2:0] read_count,read_index,write_index,write_mode;
    reg [1:0] read_phase;reg authority,maintenance,scanning,after_write_scan;
    reg [USER_WIDTH-1:0] owner;reg [30:0] stream_id,record_stream;
    reg [31:0] generation,amount,record_generation;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,streams,windows,work_floor,context_address,rpc_address,window_address,read_address;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,stream_bytes,window_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] recovery_context;reg [USER_WIDTH-1:0] recovery_owner;
    reg [63:0] raw_header;reg [383:0] connection_record;reg [255:0] rpc_record;reg [127:0] window_record;
    reg signed [32:0] initial_delta;
    reg [23:0] pending_grant;
    wire [15:0] user16=owner;
    wire searching=(op==WINDOW_UPDATE_KEY||op==CLOSE_SEND_KEY)&&stream_id!=0;
    // Retain full-width bounds; arithmetic and config/error fanout use separate clocks.
    reg [63:0] contexts_end,streams_end,windows_end,context_full,context_limit;
    wire config_good=context_bytes>=256&&context_bytes[7:0]==0&&stream_bytes>=128&&stream_bytes[6:0]==0&&
        window_bytes>=(stream_bytes>>3)&&window_bytes[3:0]==0&&
        contexts>=work_floor&&streams>=work_floor&&windows>=work_floor&&
        contexts_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&streams_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&windows_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        context_limit<=contexts_end&&
        (contexts_end<=streams||streams_end<=contexts)&&(contexts_end<=windows||windows_end<=contexts)&&
        (streams_end<=windows||windows_end<=streams);
    wire address_good=rpc_address>=streams&&{1'b0,rpc_address}+128<=streams_end&&((rpc_address-streams)&127)==0;
    wire [31:0] contexts32=contexts,context_bytes32=context_bytes,streams32=streams,stream_bytes32=stream_bytes,windows32=windows,window_bytes32=window_bytes;
    wire connection_good=connection_record[31:0]==CONN_MAGIC&&connection_record[47:32]==user16&&connection_record[63:48]==0&&
        !connection_record[95]&&!connection_record[127]&&connection_record[159:128]>=16384&&connection_record[159:128]<=24'hffffff&&connection_record[191:160]==0&&
        connection_record[255:192]=={stream_bytes32,streams32}&&connection_record[319:256]=={window_bytes32,windows32}&&
        connection_record[383:320]=={context_bytes32,contexts32};
    wire rpc_good=rpc_record[31:0]==RPC_MAGIC&&rpc_record[32]&&rpc_record[63:35]==0&&!rpc_record[127]&&rpc_record[255:224]!=0;
    wire rpc_key=rpc_record[79:64]==user16&&rpc_record[126:96]==stream_id&&rpc_record[255:224]==generation;
    wire current_window=window_record[31:0]==STREAM_MAGIC&&window_record[63:32]==record_generation;
    wire window_binding=window_record[126:96]==record_stream&&window_record[95:64]!=32'h80000000;
    wire signed [33:0] old_stream_window={{2{window_record[95]}},window_record[95:64]};
    wire signed [33:0] adjusted_window=old_stream_window+{initial_delta[32],initial_delta};
    wire signed [33:0] incremented_window=old_stream_window+$signed({3'd0,amount[30:0]});
    wire [32:0] incremented_connection={1'b0,connection_record[95:64]}+{2'b0,amount[30:0]};
    wire [31:0] requested_limit=amount<connection_record[159:128]?amount:connection_record[159:128];
    wire [31:0] connection_limit=requested_limit<connection_record[95:64]?requested_limit:connection_record[95:64];
    wire [31:0] grant_limit=connection_limit<window_record[95:64]?connection_limit:window_record[95:64];
    // Keep the three-way credit minimum off the paired debit carry chains.
    // The actual pool grant and every record remain owned across this stage.
    reg [31:0] selected_grant;
    wire [63:0] connection_words[0:5];
    generate for(genvar i=0;i<6;i=i+1)begin: connection_word_banks
        assign connection_words[i]=connection_record[i*64+:64];
    end endgenerate
    wire [63:0] init_connection_word=write_index==0?64'd0:write_index==6?connection_record[63:0]:connection_words[write_index];
    wire [63:0] write_word=write_mode==WINIT_CONN?init_connection_word:
        write_mode==WINIT_STREAM?(write_index==0?64'd0:write_index==1?window_record[127:64]:window_record[63:0]):
        write_mode==WCONN?connection_record[127:64]:write_mode==WMAX?connection_record[191:128]:
        write_mode==WSTREAM?window_record[127:64]:write_mode==WRESERVE?(write_index==0?window_record[127:64]:connection_record[127:64]):64'd0;
    wire [MEMORY_ADDR_WIDTH-1:0] write_address=write_mode==WINIT_CONN?context_address+168+((write_index==0||write_index==6)?0:write_index*8):
        write_mode==WINIT_STREAM?window_address+(write_index==1?8:0):
        write_mode==WCONN?context_address+176:write_mode==WMAX?context_address+184:
        write_mode==WSTREAM?window_address+8:write_mode==WRESERVE?(write_index==0?window_address+8:context_address+176):context_address+168;
    wire write_last=write_mode==WINIT_CONN?write_index==6:write_mode==WINIT_STREAM?write_index==2:
        write_mode==WRESERVE?write_index==1:1'b1;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire [MEMORY_ADDR_WIDTH-1:0] command_address=state==WRITE_REQ?write_address:read_address+read_index*8;
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==READ_REQ||state==WRITE_REQ),.req_ready(slot_ready),.req_write(state==WRITE_REQ),
        .req_addr(command_address),.req_bytes(4'd8),.req_data({8'd0,write_word}),
        .result_valid(slot_valid),.result_ready(state==READ_WAIT||state==WRITE_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    assign req_ready=!rst&&state==IDLE;assign rsp_valid=state==RESULT;assign rsp_op=op;assign rsp_user=owner;assign rsp_stream=stream_id;
    assign idle=state==IDLE&&slot_idle&&!req_valid;
    // Publish only a verified, durably closed actual binding. Never a caller guess.
    assign rsp_binding_valid=rsp_valid&&rsp_status==0&&(op==CLOSE_SEND||op==CLOSE_SEND_KEY);
    assign rsp_record_address=rpc_address;assign rsp_generation=record_generation;
    assign rsp_send_closed=rsp_binding_valid&&window_record[127];
    task finish_error(input [7:0] status,input [7:0] detail,input [31:0] error,input connection_error);
        begin rsp_status<=status;rsp_detail<=detail;rsp_http2_error<=error;rsp_connection_error<=connection_error;rsp_grant_bytes<=0;state<=RESULT;end
    endtask
    task quarantine(input [7:0] status,input [7:0] detail,input [31:0] error,input [MEMORY_ADDR_WIDTH-1:0] address);
        begin recovery_required<=1;recovery_address<=address;recovery_context<=context_address;recovery_owner<=owner;
            finish_error(status,detail,error,1);end
    endtask
    task read_words(input [1:0] phase,input [MEMORY_ADDR_WIDTH-1:0] address,input [2:0] count);
        begin read_phase<=phase;read_address<=address;read_count<=count;read_index<=0;state<=READ_REQ;
            case(phase)RRAW:raw_header<=0;RCONN:connection_record<=0;RRPC:rpc_record<=0;RWINDOW:window_record<=0;endcase
        end
    endtask
    task write_words(input [2:0] mode,input continue_scan);
        begin write_mode<=mode;write_index<=0;after_write_scan<=continue_scan;state<=WRITE_REQ;end
    endtask
    initial begin if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<10||MEMORY_ADDR_WIDTH>31)$error("Unsupported window-store widths");end
    integer bank;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;op<=0;read_count<=0;read_index<=0;write_index<=0;write_mode<=0;read_phase<=0;
            authority<=0;maintenance<=0;scanning<=0;after_write_scan<=0;owner<=0;stream_id<=0;record_stream<=0;
            generation<=0;amount<=0;record_generation<=0;contexts<=0;streams<=0;windows<=0;work_floor<=0;
            context_address<=0;rpc_address<=0;window_address<=0;read_address<=0;context_bytes<=0;stream_bytes<=0;window_bytes<=0;
            contexts_end<=0;streams_end<=0;windows_end<=0;context_full<=0;context_limit<=0;
            recovery_context<=0;recovery_owner<=0;raw_header<=0;connection_record<=0;rpc_record<=0;window_record<=0;initial_delta<=0;pending_grant<=0;
            rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;
            rsp_grant_bytes<=0;rsp_connection_window<=0;rsp_initial_window<=0;rsp_stream_window<=0;rsp_max_frame_bytes<=0;rsp_affected_streams<=0;
            recovery_required<=0;recovery_address<=0;selected_grant<=0;
        end else case(state)
            IDLE:if(req_valid&&req_ready)begin
                op<=req_op;authority<=req_authority;maintenance<=req_maintenance;owner<=req_user;stream_id<=req_stream;generation<=req_generation;
                amount<=req_amount;rpc_address<=req_record_address;contexts<=cfg_context_base;context_bytes<=cfg_context_bytes;
                streams<=cfg_stream_base;stream_bytes<=cfg_stream_bytes;windows<=cfg_window_base;window_bytes<=cfg_window_bytes;work_floor<=cfg_work_floor;
                scanning<=0;after_write_scan<=0;pending_grant<=0;rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;
                rsp_connection_error<=0;rsp_http2_error<=0;rsp_grant_bytes<=0;rsp_connection_window<=0;rsp_initial_window<=0;rsp_stream_window<=0;rsp_max_frame_bytes<=0;rsp_affected_streams<=0;
                state<=GEOMETRY;
            end
            GEOMETRY:begin
                contexts_end<={1'b0,contexts}+{1'b0,context_bytes};
                streams_end<={1'b0,streams}+{1'b0,stream_bytes};
                windows_end<={1'b0,windows}+{1'b0,window_bytes};
                context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);
                context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;
                state<=CHECK;
            end
            CHECK:begin
                context_address<=context_full[MEMORY_ADDR_WIDTH-1:0];
                if(op>CLOSE_SEND_KEY)finish_error(2,6,2,1);
                else if(!config_good)finish_error(2,1,2,1);
                else if(!authority)finish_error(7,1,2,1);
                else if(recovery_required&&!(maintenance&&(op==INIT_CONNECTION||op==CLOSE_CONNECTION)&&owner==recovery_owner&&context_full==recovery_context))finish_error(6,1,2,1);
                else if((op==INIT_CONNECTION||op==CLOSE_CONNECTION)&&(!maintenance||stream_id!=0))finish_error(7,2,2,1);
                else if((op==INITIAL_WINDOW||op==MAX_FRAME)&&stream_id!=0||
                        (op==INIT_STREAM||op==RESERVE||op==CLOSE_SEND||op==CLOSE_SEND_KEY)&&stream_id==0)finish_error(2,2,2,1);
                else if((op==WINDOW_UPDATE_KEY||op==CLOSE_SEND_KEY)&&(generation!=0||rpc_address!=0))finish_error(2,7,2,1);
                else if(op==CLOSE_SEND_KEY&&amount!=0)finish_error(2,8,2,1);
                else if(op!=WINDOW_UPDATE_KEY&&op!=CLOSE_SEND_KEY&&stream_id!=0&&(!address_good||generation==0))finish_error(2,3,2,1);
                else if((op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY)&&(amount==0||amount[31]))finish_error(4,1,amount==0?32'd1:32'd3,stream_id==0);
                else if(op==INITIAL_WINDOW&&amount[31])finish_error(4,2,3,1);
                else if(op==MAX_FRAME&&(amount<16384||amount>24'hffffff))finish_error(4,3,1,1);
                else if(op==RESERVE&&amount==0)finish_error(2,4,2,1);
                else if(op==CLOSE_CONNECTION)write_words(WCLOSE,0);
                else read_words(RRAW,context_full[MEMORY_ADDR_WIDTH-1:0],1);
            end
            READ_REQ:if(slot_ready)state<=READ_WAIT;
            READ_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin rsp_memory_status<=slot_status;quarantine(5,1,2,read_address+read_index*8);end
                else begin
                    case(read_phase)
                        RRAW:raw_header<=slot_data[63:0];
                        RCONN:for(bank=0;bank<6;bank=bank+1)if(read_index==bank)connection_record[bank*64+:64]<=slot_data[63:0];
                        RRPC:for(bank=0;bank<4;bank=bank+1)if(read_index==bank)rpc_record[bank*64+:64]<=slot_data[63:0];
                        RWINDOW:for(bank=0;bank<2;bank=bank+1)if(read_index==bank)window_record[bank*64+:64]<=slot_data[63:0];
                    endcase
                    if(read_index+1==read_count)case(read_phase)RRAW:state<=RAW_CHECK;RCONN:state<=CONN_CHECK;RRPC:state<=RPC_CHECK;RWINDOW:state<=WINDOW_CHECK;endcase
                    else begin read_index<=read_index+1'b1;state<=READ_REQ;end
                end
            end
            RAW_CHECK:if(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])finish_error(3,1,2,1);
                else if(op==INIT_CONNECTION)begin
                    connection_record<={{context_bytes32,contexts32},{window_bytes32,windows32},{stream_bytes32,streams32},64'd16384,{32'd65535,32'd65535},{16'd0,user16,CONN_MAGIC}};
                    rsp_connection_window<=65535;rsp_initial_window<=65535;rsp_max_frame_bytes<=16384;write_words(WINIT_CONN,0);
                end else read_words(RCONN,context_address+168,6);
            CONN_CHECK:if(!connection_good)quarantine(3,2,2,context_address+168);
                else begin
                    rsp_connection_window<=connection_record[95:64];rsp_initial_window<=connection_record[127:96];rsp_max_frame_bytes<=connection_record[151:128];
                    if((op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY)&&stream_id==0)begin
                        if(incremented_connection>33'h07fffffff)finish_error(4,4,3,1);
                        else begin connection_record[95:64]<=incremented_connection[31:0];rsp_connection_window<=incremented_connection[31:0];write_words(WCONN,0);end
                    end else if(op==MAX_FRAME)begin connection_record[159:128]<=amount;rsp_max_frame_bytes<=amount[23:0];write_words(WMAX,0);end
                    else if(op==READ_WINDOW&&stream_id==0)state<=RESULT;
                    else if(op==INITIAL_WINDOW)begin
                        initial_delta<=$signed({1'b0,amount})-$signed({1'b0,connection_record[127:96]});
                        scanning<=1;rpc_address<=streams;read_words(RRPC,streams,4);
                    end else if(searching)begin rpc_address<=streams;read_words(RRPC,streams,4);end
                    else read_words(RRPC,rpc_address,4);
                end
            RPC_CHECK:if((scanning||searching)&&rpc_record[63:0]==0)state<=SCAN_NEXT;
                else if(!rpc_good)quarantine(3,3,2,rpc_address);
                else if(scanning&&rpc_record[79:64]!=user16)state<=SCAN_NEXT;
                else if(searching&&(rpc_record[79:64]!=user16||rpc_record[126:96]!=stream_id))state<=SCAN_NEXT;
                else if(!scanning&&!searching&&!rpc_key)finish_error(3,4,2,0);
                else begin
                    record_generation<=rpc_record[255:224];record_stream<=rpc_record[126:96];
                    window_address<=windows+((rpc_address-streams)>>3);
                    read_words(RWINDOW,windows+((rpc_address-streams)>>3),2);
                end
            WINDOW_CHECK:if(window_record[63:0]!=0&&window_record[31:0]!=STREAM_MAGIC)quarantine(3,5,2,window_address);
                else if(current_window&&!window_binding)quarantine(3,6,2,window_address);
                else if(op==INIT_STREAM)begin
                    if(current_window)finish_error(3,7,2,0);
                    else begin window_record<={{1'b0,record_stream,connection_record[127:96]},{record_generation,STREAM_MAGIC}};
                        rsp_stream_window<=connection_record[127:96];write_words(WINIT_STREAM,0);end
                end else if(!current_window)begin if(scanning)state<=SCAN_NEXT;else finish_error(3,8,2,0);end
                else if(scanning&&window_record[127])state<=SCAN_NEXT;
                else begin if(!scanning)rsp_stream_window<=window_record[95:64];state<=CALCULATE;end
            CALCULATE:if(scanning)begin
                    if(adjusted_window>34'sh07fffffff)quarantine(4,5,3,window_address+8);
                    else if(adjusted_window< -34'sh07fffffff)quarantine(3,9,2,window_address+8);
                    else begin window_record[95:64]<=adjusted_window[31:0];write_words(WSTREAM,1);end
                end else if(op==CLOSE_SEND||op==CLOSE_SEND_KEY)begin
                    if(window_record[127])state<=RESULT;
                    else begin window_record[127]<=1;write_words(WSTREAM,0);end
                end else if(op==READ_WINDOW)state<=RESULT;
                else if(window_record[127]&&(op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY))state<=RESULT;
                else if(window_record[127]&&op==RESERVE)finish_error(8,0,5,0);
                else if(op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY)begin
                    if(incremented_window>34'sh07fffffff)finish_error(4,6,3,0);
                    else begin window_record[95:64]<=incremented_window[31:0];rsp_stream_window<=incremented_window[31:0];write_words(WSTREAM,0);end
                end else if(op==RESERVE)begin
                    if(old_stream_window<=0||connection_record[95:64]==0)finish_error(1,0,0,0);
                    else begin
selected_grant<=grant_limit;state<=RESERVE_APPLY;
                    end
                end else finish_error(2,5,2,1);
            RESERVE_APPLY:begin
                pending_grant<=selected_grant[23:0];
                window_record[95:64]<=window_record[95:64]-selected_grant;
                connection_record[95:64]<=connection_record[95:64]-selected_grant;
                rsp_stream_window<=window_record[95:64]-selected_grant;
                rsp_connection_window<=connection_record[95:64]-selected_grant;
                write_words(WRESERVE,0);
            end
            SCAN_NEXT:if({1'b0,rpc_address}+128<streams_end)begin rpc_address<=rpc_address+128;read_words(RRPC,rpc_address+128,4);end
                else if(searching)finish_error(3,10,0,0);
                else begin connection_record[127:96]<=amount;rsp_initial_window<=amount;write_words(WCONN,0);end
            WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
            WRITE_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin rsp_memory_status<=slot_status;quarantine(5,2,2,write_address);end
                else if(write_last)begin
                    if(after_write_scan)begin rsp_affected_streams<=rsp_affected_streams+1'b1;state<=SCAN_NEXT;end
                    else begin
                        if(op==RESERVE)rsp_grant_bytes<=pending_grant;
                        if(op==INIT_CONNECTION||op==CLOSE_CONNECTION)begin recovery_required<=0;recovery_address<=0;end
                        state<=RESULT;
                    end
                end else begin write_index<=write_index+1'b1;state<=WRITE_REQ;end
            end
            RESULT:if(rsp_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
