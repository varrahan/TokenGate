`timescale 1ns/1ps
`default_nettype none
// External per-connection framing state. Record stride reserves room for the
// full transport context; this unit owns only bytes 0..31. No host transaction
// is needed per packet. Control OPEN/CLOSE/UPDATE is serialized with packets.
module http2_connection_ingress #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,parameter integer RECORD_SHIFT=8,
    parameter integer AUX_STATE=0,parameter integer AUX_BITS=256,parameter integer AUX_UPDATE=0,
    parameter [AUX_BITS-1:0] AUX_UPDATE_MASK=0
)(
    input wire clk,input wire rst,input wire admit_packets,
    input wire [MEMORY_ADDR_WIDTH-1:0] cfg_context_base,input wire [MEMORY_ADDR_WIDTH:0] cfg_context_bytes,
    input wire command_valid,output wire command_ready,input wire [1:0] command_op,input wire [USER_WIDTH-1:0] command_user,
    input wire command_server_role,command_allow_push,input wire [23:0] command_max_frame_bytes,
    input wire [AUX_BITS-1:0] command_aux_initial,
    input wire [511:0] s_axis_rx_tdata,input wire [63:0] s_axis_rx_tkeep,input wire s_axis_rx_tvalid,output wire s_axis_rx_tready,
    input wire s_axis_rx_tlast,input wire [USER_WIDTH-1:0] s_axis_rx_tuser,
    output wire event_valid,input wire event_ready,output wire [1:0] event_kind,output wire [7:0] event_data,
    output wire [23:0] event_length,output wire [7:0] event_type,event_flags,output wire [30:0] event_stream,
    output wire event_payload_last,output wire [31:0] event_error,output wire [USER_WIDTH-1:0] event_user,
    output wire rsp_valid,input wire rsp_ready,output reg rsp_is_command,output reg [1:0] rsp_command_op,
    output reg [7:0] rsp_status,rsp_detail,rsp_memory_status,output reg [31:0] rsp_http2_error,output wire [USER_WIDTH-1:0] rsp_user,
    output reg recovery_required,output reg [MEMORY_ADDR_WIDTH-1:0] recovery_address,
    output wire mem_valid,input wire mem_ready,output wire mem_write,output wire [MEMORY_ADDR_WIDTH-1:0] mem_addr,
    output wire [3:0] mem_bytes,output wire [71:0] mem_data,input wire mem_rsp_valid,output wire mem_rsp_ready,
    input wire [71:0] mem_rsp_data,input wire [7:0] mem_rsp_status,output wire idle,
    output wire aux_start_valid,input wire aux_start_ready,output wire [AUX_BITS-1:0] aux_restore,
    output wire [USER_WIDTH-1:0] aux_user,output wire aux_server_role,output wire aux_finish_valid,
    input wire aux_result_valid,output wire aux_result_ready,input wire [AUX_BITS-1:0] aux_save,
    input wire aux_failed,input wire [31:0] aux_error,input wire [7:0] aux_detail
);
    localparam IDLE=0,CHECK=1,LOAD_REQ=2,LOAD_WAIT=3,CHECK_RECORD=4,CORE_START=5,CORE_RUN=6,
        INVALIDATE_REQ=7,INVALIDATE_WAIT=8,STATE_REQ=9,STATE_WAIT=10,COMMIT_REQ=11,COMMIT_WAIT=12,ACK_CORE=13,DRAIN=14,RESULT=15;
    localparam [31:0] MAGIC=32'h48324331;
    localparam integer AUX_WORDS=AUX_BITS/64,LOAD_LAST=AUX_STATE?3+AUX_WORDS:3,SAVE_LAST=AUX_STATE?2+AUX_WORDS:2;
    localparam integer INDEX_WIDTH=$clog2(LOAD_LAST+1);
    reg [3:0] state;
    reg [MEMORY_ADDR_WIDTH-1:0] record_address;
    reg address_good;
    reg [INDEX_WIDTH-1:0] word_index;
    reg [63:0] record_header;
    reg [159:0] reader_state;
    reg [AUX_BITS-1:0] auxiliary_state,requested_aux;
    reg aux_started;
    reg reserved_bad;
    reg requested_role,requested_push;
    reg [23:0] requested_maximum;
    reg [USER_WIDTH-1:0] context_id;
    reg [511:0] first_data;
    reg [63:0] first_keep;
    reg first_valid,first_last,input_closed,core_owned;
    wire [USER_WIDTH-1:0] incoming_user=command_valid?command_user:s_axis_rx_tuser;
    wire [63:0] incoming_address={1'b0,cfg_context_base}+({{(64-USER_WIDTH){1'b0}},incoming_user}<<RECORD_SHIFT);
    wire [63:0] pool_end={1'b0,cfg_context_base}+{1'b0,cfg_context_bytes};
    wire incoming_good=pool_end<=(64'd1<<MEMORY_ADDR_WIDTH)&&incoming_address+(64'd1<<RECORD_SHIFT)<=pool_end;
    wire [7:0] header_flags=record_header[39:32];
    wire header_good=record_header[31:0]==MAGIC&&header_flags[0]&&header_flags[7:4]==0&&record_header[63:40]>=16384&&!reserved_bad;
    wire slot_ready,slot_valid,slot_idle;wire [71:0] slot_data;wire [7:0] slot_status;
    wire request_write=state!=LOAD_REQ;
    wire slot_request=state==LOAD_REQ||state==INVALIDATE_REQ||state==STATE_REQ||state==COMMIT_REQ;
    wire [MEMORY_ADDR_WIDTH-1:0] request_address=record_address+(state==LOAD_REQ?word_index*8:state==STATE_REQ?8+word_index*8:0);
    // Decode word selection once. A variable part-select with a subtracted
    // index builds a wide barrel selector/update network for the whole record.
    // Constant word slices expose one shared enable per 64-bit register bank.
    reg [63:0] auxiliary_word;
    integer auxiliary_load_index;
    wire [63:0] auxiliary_words[0:AUX_WORDS-1];
    wire [INDEX_WIDTH-1:0] auxiliary_index=word_index-3'd3;
    generate for(genvar select_bank=0;select_bank<AUX_WORDS;select_bank=select_bank+1)begin: word_select_banks
        assign auxiliary_words[select_bank]=auxiliary_state[select_bank*64+:64];
    end endgenerate
    always @*begin
        auxiliary_word=64'd0;
        if(word_index>=3&&word_index<AUX_WORDS+3)auxiliary_word=auxiliary_words[auxiliary_index];
    end
    wire [63:0] state_word=word_index==0?reader_state[63:0]:word_index==1?reader_state[127:64]:word_index==2?{32'd0,reader_state[159:128]}:auxiliary_word;
    wire [71:0] request_data=state==INVALIDATE_REQ?72'd0:state==STATE_REQ?{8'd0,state_word}:{8'd0,record_header};
    memory_command_slot #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) memory_slot(
        .clk(clk),.rst(rst),.req_valid(slot_request),.req_ready(slot_ready),.req_write(request_write),.req_addr(request_address),.req_bytes(4'd8),.req_data(request_data),
        .result_valid(slot_valid),.result_ready(state==LOAD_WAIT||state==INVALIDATE_WAIT||state==STATE_WAIT||state==COMMIT_WAIT),.result_data(slot_data),.result_status(slot_status),
        .mem_valid(mem_valid),.mem_ready(mem_ready),.mem_write(mem_write),.mem_addr(mem_addr),.mem_bytes(mem_bytes),.mem_data(mem_data),
        .mem_rsp_valid(mem_rsp_valid),.mem_rsp_ready(mem_rsp_ready),.mem_rsp_data(mem_rsp_data),.mem_rsp_status(mem_rsp_status),.idle(slot_idle));
    wire core_start_ready,core_rx_ready,core_completion_valid,core_completion_failed,core_idle;
    wire [31:0] core_error;wire [7:0] core_detail;wire [159:0] core_state;
    http2_axis_ingress #(.USER_WIDTH(USER_WIDTH)) framing(
        .clk(clk),.rst(rst),.start_valid(state==CORE_START&&(!AUX_STATE||aux_started)),.start_ready(core_start_ready),.start_fresh(header_flags[3]),.start_user(context_id),
        .cfg_state(reader_state),.cfg_max_frame_bytes(record_header[63:40]),.cfg_server_role(header_flags[1]),.cfg_allow_push(header_flags[2]),
        .s_axis_rx_tdata(first_valid?first_data:s_axis_rx_tdata),.s_axis_rx_tkeep(first_valid?first_keep:s_axis_rx_tkeep),
        .s_axis_rx_tvalid(state==CORE_RUN&&(first_valid||(!input_closed&&s_axis_rx_tvalid))),.s_axis_rx_tready(core_rx_ready),
        .s_axis_rx_tlast(first_valid?first_last:s_axis_rx_tlast),.s_axis_rx_tuser(first_valid?context_id:s_axis_rx_tuser),
        .event_valid(event_valid),.event_ready(event_ready),.event_kind(event_kind),.event_data(event_data),.event_length(event_length),.event_type(event_type),.event_flags(event_flags),
        .event_stream(event_stream),.event_payload_last(event_payload_last),.event_error(event_error),.event_user(event_user),
        .completion_valid(core_completion_valid),.completion_ready(state==ACK_CORE),.completion_failed(core_completion_failed),.completion_error(core_error),.completion_detail(core_detail),
        .completion_state(core_state),.completion_user(),.idle(core_idle));
    assign command_ready=!rst&&state==IDLE;
    assign aux_start_valid=AUX_STATE&&state==CORE_START&&!aux_started;
    assign aux_restore=AUX_STATE?auxiliary_state:{AUX_BITS{1'b0}};assign aux_user=context_id;assign aux_server_role=header_flags[1];
    assign aux_finish_valid=AUX_STATE&&state==CORE_RUN&&core_completion_valid;
    assign aux_result_ready=aux_finish_valid&&aux_result_valid;
    assign s_axis_rx_tready=!rst&&(state==IDLE?admit_packets&&!command_valid&&!recovery_required:
        state==CORE_RUN?!first_valid&&!input_closed&&core_rx_ready:state==DRAIN&&!input_closed);
    assign rsp_valid=state==RESULT;
    assign rsp_user=context_id;
    assign idle=state==IDLE&&slot_idle&&core_idle&&!command_valid&&!(s_axis_rx_tvalid&&s_axis_rx_tready);
    task finish;
        begin state<=core_owned?ACK_CORE:(rsp_is_command||input_closed?RESULT:DRAIN);first_valid<=0;end
    endtask
    task fail(input [7:0] status,input [7:0] detail,input [7:0] memory_status);
        begin rsp_status<=status;rsp_detail<=detail;rsp_memory_status<=memory_status;if(!rsp_is_command)rsp_http2_error<=2;finish;end
    endtask
    task memory_failure(input [7:0] status,input [7:0] detail);
        begin recovery_required<=1;recovery_address<=record_address;fail(status,detail,slot_status);end
    endtask
    initial begin
        if(USER_WIDTH>32||MEMORY_ADDR_WIDTH>31||RECORD_SHIFT<(AUX_STATE?6:5)||RECORD_SHIFT>MEMORY_ADDR_WIDTH)$error("Unsupported connection-record widths");
        if(AUX_BITS<64||AUX_BITS%64!=0||AUX_STATE&&(32+AUX_BITS/8>(1<<RECORD_SHIFT)))$error("Auxiliary state does not fit its record");
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;record_address<=0;address_good<=0;word_index<=0;record_header<=0;reader_state<=0;auxiliary_state<=0;requested_aux<=0;aux_started<=0;reserved_bad<=0;requested_role<=0;requested_push<=0;requested_maximum<=0;
            context_id<=0;first_data<=0;first_keep<=0;first_valid<=0;first_last<=0;input_closed<=0;core_owned<=0;
            rsp_is_command<=0;rsp_command_op<=0;rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_http2_error<=0;recovery_required<=0;recovery_address<=0;
        end else begin
            case(state)
                IDLE:begin
                    if(command_valid&&command_ready||s_axis_rx_tvalid&&s_axis_rx_tready)begin
                        context_id<=incoming_user;record_address<=incoming_address[MEMORY_ADDR_WIDTH-1:0];address_good<=incoming_good;
                        requested_role<=command_server_role;requested_push<=command_allow_push;requested_maximum<=command_max_frame_bytes;
                        rsp_is_command<=command_valid;rsp_command_op<=command_op;rsp_status<=0;rsp_detail<=0;rsp_memory_status<=0;rsp_http2_error<=0;
                        core_owned<=0;reserved_bad<=0;word_index<=0;reader_state<=0;auxiliary_state<=command_valid?command_aux_initial:{AUX_BITS{1'b0}};
                        requested_aux<=command_aux_initial;aux_started<=0;state<=CHECK;
                        if(!command_valid)begin first_data<=s_axis_rx_tdata;first_keep<=s_axis_rx_tkeep;first_last<=s_axis_rx_tlast;first_valid<=1;input_closed<=s_axis_rx_tlast;end
                        else begin first_valid<=0;input_closed<=1;end
                    end
                end
                CHECK:begin
                    if(!address_good)fail(1,0,0);
                    else if(rsp_is_command&&rsp_command_op==3)fail(7,0,0);
                    else if(recovery_required&&!(rsp_is_command&&rsp_command_op<=1&&record_address==recovery_address))fail(6,0,0);
                    else if(rsp_is_command&&rsp_command_op==0)begin
                        if(requested_maximum<16384)fail(1,1,0);
                        else begin record_header<={requested_maximum,4'd0,1'b1,requested_push,requested_role,1'b1,MAGIC};reader_state<=0;state<=INVALIDATE_REQ;end
                    end else if(rsp_is_command&&rsp_command_op==1)state<=INVALIDATE_REQ;
                    else if(rsp_is_command&&rsp_command_op==2&&requested_maximum<16384)fail(1,1,0);
                    else state<=LOAD_REQ;
                end
                LOAD_REQ:if(slot_ready)state<=LOAD_WAIT;
                LOAD_WAIT:if(slot_valid)begin
                    if(slot_status!=0)memory_failure(2,word_index);
                    else begin
                        case(word_index)
                            0:record_header<=slot_data[63:0];
                            1:reader_state[63:0]<=slot_data[63:0];
                            2:reader_state[127:64]<=slot_data[63:0];
                            3:begin reader_state[159:128]<=slot_data[31:0];reserved_bad<=slot_data[63:32]!=0;end
                            default:for(auxiliary_load_index=0;auxiliary_load_index<AUX_WORDS;auxiliary_load_index=auxiliary_load_index+1)
                                if(word_index==auxiliary_load_index+4)auxiliary_state[auxiliary_load_index*64+:64]<=slot_data[63:0];
                        endcase
                        if(word_index==LOAD_LAST||(rsp_is_command&&!AUX_UPDATE))state<=CHECK_RECORD;else begin word_index<=word_index+1'b1;state<=LOAD_REQ;end
                    end
                end
                CHECK_RECORD:begin
                    if(!header_good)fail(3,0,0);
                    else if(rsp_is_command)begin
                        record_header<={requested_maximum,header_flags[7:3],requested_push,header_flags[1:0],MAGIC};
                        if(AUX_UPDATE)auxiliary_state<=(auxiliary_state&~AUX_UPDATE_MASK)|(requested_aux&AUX_UPDATE_MASK);
                        state<=AUX_UPDATE?INVALIDATE_REQ:COMMIT_REQ;
                    end else state<=CORE_START;
                end
                CORE_START:begin
                    if(aux_start_valid&&aux_start_ready)aux_started<=1;
                    if(core_start_ready&&(!AUX_STATE||aux_started))begin core_owned<=1;state<=CORE_RUN;end
                end
                CORE_RUN:begin
                    if(first_valid&&core_rx_ready)first_valid<=0;
                    if(s_axis_rx_tvalid&&s_axis_rx_tready&&s_axis_rx_tlast)input_closed<=1;
                    if(core_completion_valid&&(!AUX_STATE||aux_result_valid))begin
                        reader_state<=core_state;if(AUX_STATE)auxiliary_state<=aux_save;record_header[35]<=0;
                        if(core_completion_failed)begin rsp_status<=4;rsp_detail<=core_detail;rsp_http2_error<=core_error;end
                        else if(AUX_STATE&&aux_failed)begin rsp_status<=4;rsp_detail<=aux_detail;rsp_http2_error<=aux_error;end
                        state<=INVALIDATE_REQ;
                    end
                end
                INVALIDATE_REQ:if(slot_ready)state<=INVALIDATE_WAIT;
                INVALIDATE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)memory_failure(5,0);
                    else if(rsp_is_command&&rsp_command_op==1)begin
                        if(recovery_required&&record_address==recovery_address)recovery_required<=0;finish;
                    end else if(rsp_status!=0)finish;
                    else begin word_index<=0;state<=STATE_REQ;end
                end
                STATE_REQ:if(slot_ready)state<=STATE_WAIT;
                STATE_WAIT:if(slot_valid)begin
                    if(slot_status!=0)memory_failure(5,word_index+8'd1);
                    else if(word_index==SAVE_LAST)state<=COMMIT_REQ;else begin word_index<=word_index+1'b1;state<=STATE_REQ;end
                end
                COMMIT_REQ:if(slot_ready)state<=COMMIT_WAIT;
                COMMIT_WAIT:if(slot_valid)begin
                    if(slot_status!=0)memory_failure(5,SAVE_LAST+2);
                    else begin
                        if(rsp_is_command&&rsp_command_op==0&&recovery_required&&record_address==recovery_address)recovery_required<=0;
                        finish;
                    end
                end
                ACK_CORE:if(core_completion_valid)begin core_owned<=0;state<=RESULT;end
                DRAIN:begin
                    first_valid<=0;
                    if(input_closed)state<=RESULT;
                    else if(s_axis_rx_tvalid&&s_axis_rx_tready&&s_axis_rx_tlast)begin input_closed<=1;state<=RESULT;end
                end
                RESULT:if(rsp_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
