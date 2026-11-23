`timescale 1ns/1ps
`default_nettype none
// Durable per-connection non-window SETTINGS and local SETTINGS/PING tracking.
// The parent owns the actual connection throughout each request and keeps this
// arena disjoint from every other runtime arena. FORMAT requires drained GPU,
// directory, memory and link ownership. Reset requires the same global fence.
// TX is the actual wire retirement interface, not admission to an output queue.
// After TX, an uncertain memory commit quarantines instead of retransmitting.
// Ops: 0 FORMAT, 1 READ, 2 SEND_EMPTY_SETTINGS, 3 SEND_PING,
//      4 PEER_SETTING, 5 PEER_SETTINGS_ACK, 6 PEER_PING_ACK.
module http2_shutdown_peer_state #(
    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23
)(
    input wire clk,input wire rst,
    input wire req_valid,output wire req_ready,input wire [3:0] req_op,
    input wire req_authority,req_maintenance,input wire [USER_WIDTH-1:0] req_user,
    input wire [15:0] req_setting,input wire [31:0] req_value,input wire [63:0] req_payload,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,cfg_peer_base,cfg_work_floor,
    input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,cfg_peer_bytes,
    output wire rsp_valid,input wire rsp_ready,output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,
    output reg rsp_connection_error,output reg [31:0] rsp_http2_error,
    output wire [3:0] rsp_op,output wire [USER_WIDTH-1:0] rsp_user,
    output reg rsp_wire_retired,rsp_ack_matched,
    output wire [31:0] rsp_header_table_size,rsp_max_concurrent_streams,rsp_max_header_list_size,
    output wire rsp_enable_push,rsp_ping_pending,
    output wire [31:0] rsp_settings_pending,rsp_settings_acks,rsp_ping_acks,
    output wire [63:0] rsp_ping_payload,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire mem_valid,input wire mem_ready,output wire mem_write,
    output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,output wire [3:0] mem_bytes,output wire [71:0] mem_data,
    input wire mem_rsp_valid,output wire mem_rsp_ready,input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,
    output wire idle
,
    output wire  rsp_goaway_received,
    output wire [30:0] rsp_goaway_last_stream,
    output wire [31:0] rsp_goaway_error
);
    localparam IDLE=0,GEOMETRY=1,CHECK=2,RAW_REQ=3,RAW_WAIT=4,RAW_CHECK=5,
        LOAD_REQ=6,LOAD_WAIT=7,RECORD_CHECK=8,APPLY=9,TX=10,WRITE_REQ=11,WRITE_WAIT=12,RESULT=13;
    localparam [31:0] RAW_MAGIC=32'h48324331,PEER_MAGIC=32'h48325031;
    reg [3:0] state,operation;reg authority,maintenance,server_role;
    reg [USER_WIDTH-1:0] owner,recovery_owner;
    reg [15:0] setting;reg [31:0] amount;reg [63:0] payload,raw_header;
    reg [MEMORY_ADDR_WIDTH-1:0] contexts,peers,work_floor,context_address,peer_address;
    reg [MEMORY_ADDR_WIDTH:0] context_bytes,peer_bytes;
    reg [MEMORY_ADDR_WIDTH-1:0] recovery_context,recovery_peer;
    reg [MEMORY_ADDR_WIDTH:0] recovery_peer_bytes;
    reg [63:0] context_full,context_limit,contexts_end,peer_full,peer_limit,peers_end;
    reg [511:0] record_data;reg [3:0] word_index;
    wire [15:0] owner16=owner;
    wire [31:0] peers32=peers,peer_bytes32=peer_bytes,context32=context_address,peer32=peer_address;
    wire config_good=context_bytes>=256&&peer_bytes>=64&&contexts>=work_floor&&peers>=work_floor&&
        contexts_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&peers_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&
        context_limit<=contexts_end&&peer_limit<=peers_end&&
        (contexts_end<={1'b0,peers}||peers_end<={1'b0,contexts});
    wire record_good=record_data[31:0]==PEER_MAGIC&&record_data[47:32]==owner16&&
        record_data[63:51]==0&&record_data[48]==server_role&&
        record_data[127:64]=={peer_bytes32,peers32}&&record_data[191:128]=={context32,peer32}&&
        (record_data[50]||record_data[319:289]==0&&record_data[479:448]==0);
    assign req_ready=!rst&&state==IDLE;assign rsp_valid=state==RESULT;
    assign rsp_op=operation;assign rsp_user=owner;assign idle=state==IDLE&&!req_valid;
    assign rsp_header_table_size=record_data[223:192];assign rsp_max_concurrent_streams=record_data[255:224];
    assign rsp_max_header_list_size=record_data[287:256];assign rsp_enable_push=record_data[288];
    assign rsp_settings_pending=record_data[351:320];assign rsp_settings_acks=record_data[383:352];
    assign rsp_ping_pending=record_data[49];assign rsp_ping_payload=record_data[447:384];
    assign rsp_ping_acks=record_data[511:480];
    assign rsp_goaway_received=record_data[50];assign rsp_goaway_last_stream=record_data[319:289];
    assign rsp_goaway_error=record_data[479:448];
    reg [511:0] tx_data;integer lane,bank,select_word;
    always @*begin
        tx_data=0;tx_data[23:16]=operation==3?8'd8:8'd0;tx_data[31:24]=operation==3?8'd6:8'd4;
        if(operation==3)for(lane=0;lane<8;lane=lane+1)tx_data[72+lane*8+:8]=payload[63-lane*8-:8];
    end
    assign m_axis_tx_tdata=tx_data;assign m_axis_tx_tkeep=operation==3?64'h1ffff:64'h1ff;
    assign m_axis_tx_tvalid=!rst&&state==TX;assign m_axis_tx_tlast=1;assign m_axis_tx_tuser=owner;
    wire slot_ready,slot_valid;wire [71:0] slot_data;wire [7:0] slot_status;
    reg [63:0] write_word;
    always @*begin
        write_word=0;
        if(state==WRITE_REQ)begin
            if(word_index==8)write_word=record_data[63:0];
            else if(word_index!=0)for(select_word=1;select_word<8;select_word=select_word+1)
                if(word_index==select_word)write_word=record_data[select_word*64+:64];
        end
    end
    wire [MEMORY_ADDR_WIDTH-1:0] slot_address=state==RAW_REQ?context_address:
        peer_address+(state==WRITE_REQ&&word_index==8?0:word_index*8);
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(state==RAW_REQ||state==LOAD_REQ||state==WRITE_REQ),.req_ready(slot_ready),
        .req_write(state==WRITE_REQ),.req_addr(slot_address),.req_bytes(4'd8),.req_data({8'd0,write_word}),
        .result_valid(slot_valid),.result_ready(state==RAW_WAIT||state==LOAD_WAIT||state==WRITE_WAIT),
        .result_data(slot_data),.result_status(slot_status),.mem_valid(mem_valid),.mem_ready(mem_ready),
        .mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle());
    task fail(input [7:0] status,input [7:0] detail);
        begin rsp_status<=status;rsp_detail<=detail;state<=RESULT;end
    endtask
    task quarantine(input [7:0] status,input [7:0] detail,input [MEMORY_ADDR_WIDTH-1:0] address);
        begin recovery_required<=1;recovery_address<=address;recovery_owner<=owner;
            recovery_context<=context_address;recovery_peer<=peer_address;recovery_peer_bytes<=peer_bytes;fail(status,detail);end
    endtask
    task save;
        begin word_index<=0;state<=WRITE_REQ;end
    endtask
    task protocol_error;
        begin rsp_connection_error<=1;rsp_http2_error<=1;fail(4,1);end
    endtask
    initial begin
        if(USER_WIDTH<1||USER_WIDTH>16||MEMORY_ADDR_WIDTH<8||MEMORY_ADDR_WIDTH>30)$error("Unsupported peer-state widths");
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;operation<=0;authority<=0;maintenance<=0;server_role<=0;owner<=0;recovery_owner<=0;
            setting<=0;amount<=0;payload<=0;raw_header<=0;contexts<=0;peers<=0;work_floor<=0;
            context_address<=0;peer_address<=0;context_bytes<=0;peer_bytes<=0;recovery_context<=0;recovery_peer<=0;recovery_peer_bytes<=0;
            context_full<=0;context_limit<=0;contexts_end<=0;peer_full<=0;peer_limit<=0;peers_end<=0;record_data<=0;word_index<=0;
            rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;
            rsp_wire_retired<=0;rsp_ack_matched<=0;recovery_required<=0;recovery_address<=0;
        end else case(state)
            IDLE:if(req_valid&&req_ready)begin
                operation<=req_op;authority<=req_authority;maintenance<=req_maintenance;owner<=req_user;
                setting<=req_setting;amount<=req_value;payload<=req_payload;contexts<=cfg_context_base;
                peers<=cfg_peer_base;work_floor<=cfg_work_floor;context_bytes<=cfg_context_bytes;peer_bytes<=cfg_peer_bytes;
                rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_connection_error<=0;rsp_http2_error<=0;
                rsp_wire_retired<=0;rsp_ack_matched<=0;record_data<=0;word_index<=0;state<=GEOMETRY;
            end
            GEOMETRY:begin
                context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);
                context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;
                contexts_end<={1'b0,contexts}+{1'b0,context_bytes};
                peer_full<={1'b0,peers}+({{(64-USER_WIDTH){1'b0}},owner}<<6);
                peer_limit<={1'b0,peers}+({{(64-USER_WIDTH){1'b0}},owner}<<6)+64'd64;
                peers_end<={1'b0,peers}+{1'b0,peer_bytes};state<=CHECK;
            end
            CHECK:begin
                context_address<=context_full[MEMORY_ADDR_WIDTH-1:0];peer_address<=peer_full[MEMORY_ADDR_WIDTH-1:0];
                if(!config_good)fail(2,1);
                else if(!authority||operation==0&&!maintenance)fail(7,1);
                else if(recovery_required&&!(operation==0&&maintenance&&owner==recovery_owner&&
                    context_full==recovery_context&&peer_full==recovery_peer&&peer_bytes==recovery_peer_bytes))fail(6,1);
                else if(operation>7)fail(9,1);else state<=RAW_REQ;
            end
            RAW_REQ:if(slot_ready)state<=RAW_WAIT;
            RAW_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin rsp_memory_status<=slot_status;quarantine(5,1,context_address);end
                else begin raw_header<=slot_data[63:0];state<=RAW_CHECK;end
            end
            RAW_CHECK:if(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])fail(3,1);
                else begin
                    server_role<=raw_header[33];
                    if(operation==0)begin
                        record_data<=0;record_data[63:0]<={14'd0,1'b0,raw_header[33],owner16,PEER_MAGIC};
                        record_data[127:64]<={peer_bytes32,peers32};record_data[191:128]<={context32,peer32};
                        record_data[255:192]<={32'hffffffff,32'd4096};record_data[319:256]<={31'd0,raw_header[33],32'hffffffff};save;
                    end else begin word_index<=0;state<=LOAD_REQ;end
                end
            LOAD_REQ:if(slot_ready)state<=LOAD_WAIT;
            LOAD_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin rsp_memory_status<=slot_status;quarantine(5,2,peer_address+word_index*8);end
                else begin
                    for(bank=0;bank<8;bank=bank+1)if(word_index==bank)record_data[bank*64+:64]<=slot_data[63:0];
                    if(word_index==7)state<=RECORD_CHECK;else begin word_index<=word_index+1'b1;state<=LOAD_REQ;end
                end
            end
            RECORD_CHECK:if(!record_good)quarantine(3,2,peer_address);else state<=APPLY;
            APPLY:case(operation)
                1:state<=RESULT;
                2:if(record_data[351:320]==32'hffffffff)fail(8,1);else state<=TX;
                3:if(record_data[49])fail(8,2);else state<=TX;
                4:case(setting)
                    1:begin record_data[223:192]<=amount;save;end
                    2:if(amount>1||!server_role&&amount!=0)protocol_error;
                        else begin record_data[288]<=amount[0];save;end
                    3:begin record_data[255:224]<=amount;save;end
                    6:begin record_data[287:256]<=amount;save;end
                    4,5:fail(9,2); // The shared window engine is their sole owner.
                    default:state<=RESULT;
                endcase
                5:if(record_data[351:320]==0)state<=RESULT;
                    else begin record_data[351:320]<=record_data[351:320]-1'b1;
                        record_data[383:352]<=record_data[383:352]+1'b1;rsp_ack_matched<=1;save;end
                6:if(!record_data[49]||record_data[447:384]!=payload)state<=RESULT;
                    else begin record_data[49]<=0;record_data[511:480]<=record_data[511:480]+1'b1;rsp_ack_matched<=1;save;end
                7:begin
                    // Last-Stream-ID concerns streams initiated by this endpoint.
                    // It is never a cutoff for the opposite-direction RPC pool.
                    // Retain the lower bound if a peer repeats GOAWAY with a
                    // larger ID; a prior retry boundary cannot be expanded.
                    record_data[50]<=1;
                    if(!record_data[50]||amount[30:0]<record_data[319:289])record_data[319:289]<=amount[30:0];
                    record_data[479:448]<=payload[31:0];save;
                end
                default:fail(9,1);
            endcase
            TX:if(m_axis_tx_tready)begin
                rsp_wire_retired<=1;
                if(operation==2)record_data[351:320]<=record_data[351:320]+1'b1;
                else begin record_data[49]<=1;record_data[447:384]<=payload;end
                save;
            end
            WRITE_REQ:if(slot_ready)state<=WRITE_WAIT;
            WRITE_WAIT:if(slot_valid)begin
                if(slot_status!=0)begin rsp_memory_status<=slot_status;
                    quarantine(5,3,peer_address+(word_index==8?0:word_index*8));end
                else if(word_index==8)begin
                    if(operation==0)begin recovery_required<=0;recovery_address<=0;end
                    state<=RESULT;
                end else begin word_index<=word_index+1'b1;state<=WRITE_REQ;end
            end
            RESULT:if(rsp_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
