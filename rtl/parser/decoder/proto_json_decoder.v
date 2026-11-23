`timescale 1ns/1ps
`default_nettype none
// Application-level decoder. Transport reassembly/decryption precedes this
// interface. Per-packet format/context are captured before the burst FIFO.
// Tentative extraction is committed only after complete syntax/UTF-8 success.
module proto_json_decoder #(
    parameter integer USER_WIDTH=16,
    parameter integer FIFO_DEPTH=512,
    parameter integer MAX_TEXT_BYTES=16384,
    parameter integer MAX_FIELD_BYTES=16384,
    parameter integer MAX_JSON_DEPTH=32,
    parameter integer MAX_PROTO_GROUP_DEPTH=16,
    parameter integer SCHEMA_ENTRIES=16,
    parameter integer KEY_BYTES=32,
    parameter integer SCHEMA_INDEX_WIDTH=$clog2(SCHEMA_ENTRIES),
    parameter integer KEY_LENGTH_WIDTH=$clog2(KEY_BYTES+2)
)(
    input wire clk,input wire rst,input wire cfg_protobuf,
    input wire cfg_unlock,input wire cfg_schema_valid,output wire cfg_schema_ready,
    input wire [SCHEMA_INDEX_WIDTH-1:0] cfg_schema_index,
    input wire [KEY_BYTES*8-1:0] cfg_schema_key,
    input wire [KEY_LENGTH_WIDTH-1:0] cfg_schema_key_length,
    input wire cfg_schema_json_enable,input wire [28:0] cfg_schema_field,
    input wire cfg_schema_proto_enable,
    input wire [511:0] s_axis_rx_tdata,input wire [63:0] s_axis_rx_tkeep,
    input wire s_axis_rx_tvalid,output wire s_axis_rx_tready,
    input wire s_axis_rx_tlast,input wire [USER_WIDTH-1:0] s_axis_rx_tuser,
    input wire s_axis_rx_abort,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,
    output wire m_axis_text_tlast,output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire error_valid,input wire error_ready,output reg [7:0] error_code,
    output wire [USER_WIDTH-1:0] error_user,output wire idle
);
    localparam PARSE=0,READ_REQ=1,READ_WAIT=2,EMIT=3,END_MARKER=4,WAIT_TX=5,ERROR_STATE=6;
    localparam integer CW=$clog2(MAX_TEXT_BYTES+1);
    localparam integer OW=$clog2(FIFO_DEPTH+4);
    reg [2:0] state;
    reg [OW-1:0] outstanding;
    reg rx_packet_open,rx_format,schema_quiet;
    reg [USER_WIDTH-1:0] rx_context;
    reg active,feed_done,current_mode,overflow,transport_aborted;
    reg [USER_WIDTH-1:0] context_id;
    reg [CW-1:0] text_count,read_index;
    (* ram_style="block" *) reg [7:0] text_memory[0:MAX_TEXT_BYTES-1];
    reg [7:0] read_byte;
    wire fifo_input_ready;
    wire [511:0] fifo_data;
    wire [63:0] fifo_keep;
    wire [USER_WIDTH+1:0] fifo_user;
    wire fifo_valid,fifo_ready,fifo_last;
    wire schema_programming,schema_idle;
    assign s_axis_rx_tready=fifo_input_ready && !cfg_unlock && !schema_programming;
    rx_framing_fifo #(.USER_WIDTH(USER_WIDTH+2),.DEPTH(FIFO_DEPTH)) rx_fifo (
        .clk(clk),.rst(rst),.s_axis_tdata(s_axis_rx_tdata),.s_axis_tkeep(s_axis_rx_tkeep),
        .s_axis_tvalid(s_axis_rx_tvalid&&!cfg_unlock&&!schema_programming),.s_axis_tready(fifo_input_ready),
        .s_axis_tlast(s_axis_rx_tlast),
        .s_axis_tuser({s_axis_rx_abort,rx_packet_open ? rx_format : cfg_protobuf,rx_packet_open ? rx_context : s_axis_rx_tuser}),
        .m_axis_tdata(fifo_data),.m_axis_tkeep(fifo_keep),.m_axis_tvalid(fifo_valid),
        .m_axis_tready(fifo_ready),.m_axis_tlast(fifo_last),.m_axis_tuser(fifo_user));
    wire [7:0] in_byte,unpack_byte;
    wire in_keep,in_valid,in_ready,in_last,unpack_idle;
    wire unpack_keep,unpack_valid,unpack_ready,unpack_last;
    wire [USER_WIDTH+1:0] in_user,unpack_user;
    axis_byte_unpacker #(.USER_WIDTH(USER_WIDTH+2)) unpacker (
        .clk(clk),.rst(rst),.s_data(fifo_data),.s_keep(fifo_keep),.s_valid(fifo_valid),
        .s_ready(fifo_ready),.s_last(fifo_last),.s_user(fifo_user),
        .m_data(unpack_byte),.m_keep(unpack_keep),.m_valid(unpack_valid),.m_ready(unpack_ready),
        .m_last(unpack_last),.m_user(unpack_user),.idle(unpack_idle));
    // Cut the priority-encoder/data-select path before JSON control logic.
    // Ready is registered through the two-entry occupancy state as well.
    axis_skid_buffer #(.DATA_WIDTH(8),.KEEP_WIDTH(1),.USER_WIDTH(USER_WIDTH+2)) byte_pipeline (
        .clk(clk),.rst(rst),.s_axis_tdata(unpack_byte),.s_axis_tkeep(unpack_keep),
        .s_axis_tvalid(unpack_valid),.s_axis_tready(unpack_ready),
        .s_axis_tlast(unpack_last),.s_axis_tuser(unpack_user),
        .m_axis_tdata(in_byte),.m_axis_tkeep(in_keep),.m_axis_tvalid(in_valid),
        .m_axis_tready(in_ready),.m_axis_tlast(in_last),.m_axis_tuser(in_user));
    wire json_ready,window_ready;
    wire feed_enabled=state==PARSE && !feed_done;
    assign in_ready=feed_enabled && (in_user[USER_WIDTH] ? window_ready : json_ready);
    wire [63:0] window_data;
    wire [3:0] window_count,window_consumed;
    wire window_valid,window_last,window_output_ready,window_idle;
    wire [USER_WIDTH-1:0] window_user;
    axis_byte_window #(.USER_WIDTH(USER_WIDTH)) lookahead (
        .clk(clk),.rst(rst),.s_data(in_byte),.s_keep(in_keep),
        .s_valid(in_valid&&feed_enabled&&in_user[USER_WIDTH]),.s_ready(window_ready),
        .s_last(in_last),.s_user(in_user[USER_WIDTH-1:0]),
        .m_data(window_data),.m_count(window_count),.m_valid(window_valid),
        .m_ready(window_output_ready),.m_consumed(window_consumed),
        .m_last(window_last),.m_user(window_user),.idle(window_idle));
    wire [7:0] key_data;
    wire key_start_valid,key_start_ready,key_valid,key_ready,key_keep,key_last,key_result_valid,key_result_ready;
    wire key_selected,proto_selected;
    wire [28:0] proto_field;
    schema_cam_lut #(.ENTRIES(SCHEMA_ENTRIES),.KEY_BYTES(KEY_BYTES)) schema (
        .clk(clk),.rst(rst),.cfg_unlock(cfg_unlock&&schema_quiet&&outstanding==0&&!rx_packet_open),.cfg_valid(cfg_schema_valid),
        .cfg_ready(cfg_schema_ready),.cfg_index(cfg_schema_index),.cfg_key(cfg_schema_key),
        .cfg_key_length(cfg_schema_key_length),.cfg_json_enable(cfg_schema_json_enable),
        .cfg_field(cfg_schema_field),.cfg_proto_enable(cfg_schema_proto_enable),
        .key_start_valid(key_start_valid),.key_start_ready(key_start_ready),
        .key_valid(key_valid),.key_ready(key_ready),.key_data(key_data),.key_keep(key_keep),.key_last(key_last),
        .key_result_valid(key_result_valid),.key_result_ready(key_result_ready),.json_selected(key_selected),
        .proto_field(proto_field),.proto_selected(proto_selected),.programming(schema_programming),.idle(schema_idle));
    wire [7:0] json_data,json_status,proto_data,proto_status;
    wire json_keep,json_valid,json_last,json_idle,proto_keep,proto_valid,proto_last,proto_idle;
    speculative_json_fsm #(.USER_WIDTH(USER_WIDTH),.MAX_DEPTH(MAX_JSON_DEPTH),.KEY_BYTES(KEY_BYTES)) json_parser (
        .clk(clk),.rst(rst),.s_data(in_byte),.s_keep(in_keep),
        .s_valid(in_valid&&feed_enabled&&!in_user[USER_WIDTH]),.s_ready(json_ready),
        .s_last(in_last),.s_user(in_user[USER_WIDTH-1:0]),
        .key_start_valid(key_start_valid),.key_start_ready(key_start_ready),
        .key_valid(key_valid),.key_ready(key_ready),.key_data(key_data),.key_keep(key_keep),.key_last(key_last),
        .key_result_valid(key_result_valid),.key_result_ready(key_result_ready),.key_selected(key_selected),
        .m_data(json_data),.m_keep(json_keep),.m_valid(json_valid),.m_ready(state==PARSE),
        .m_last(json_last),.m_user(),.packet_status(json_status),.idle(json_idle));
    protobuf_wire_fsm #(.USER_WIDTH(USER_WIDTH),.MAX_FIELD_BYTES(MAX_FIELD_BYTES),.MAX_GROUP_DEPTH(MAX_PROTO_GROUP_DEPTH)) proto_parser (
        .clk(clk),.rst(rst),.s_data(window_data),.s_count(window_count),
        .s_valid(window_valid),.s_ready(window_output_ready),.s_last(window_last),
        .s_user(window_user),.consumed(window_consumed),.field_number(proto_field),.field_selected(proto_selected),
        .m_data(proto_data),.m_keep(proto_keep),.m_valid(proto_valid),.m_ready(state==PARSE),
        .m_last(proto_last),.m_user(),.packet_status(proto_status),.idle(proto_idle));
    wire [7:0] decoded_data=current_mode ? proto_data : json_data;
    wire decoded_keep=current_mode ? proto_keep : json_keep;
    wire decoded_valid=current_mode ? proto_valid : json_valid;
    wire decoded_last=current_mode ? proto_last : json_last;
    wire [7:0] decoded_status=current_mode ? proto_status : json_status;
    wire abort_now=transport_aborted||(in_valid&&in_ready&&in_user[USER_WIDTH+1]);
    wire pack_ready;
    axis_byte_packer #(.USER_WIDTH(USER_WIDTH)) output_packager (
        .clk(clk),.rst(rst),.s_data(read_byte),.s_keep(state==EMIT),
        .s_valid(state==EMIT || state==END_MARKER),.s_ready(pack_ready),
        .s_last(state==END_MARKER),.s_user(context_id),
        .m_data(m_axis_text_tdata),.m_keep(m_axis_text_tkeep),.m_valid(m_axis_text_tvalid),
        .m_ready(m_axis_text_tready),.m_last(m_axis_text_tlast),.m_user(m_axis_text_tuser));
    assign error_valid=state==ERROR_STATE;
    assign error_user=context_id;
    wire retire=(state==ERROR_STATE && error_ready) ||
                (state==WAIT_TX && m_axis_text_tvalid && m_axis_text_tready && m_axis_text_tlast);
    wire admit=s_axis_rx_tvalid && s_axis_rx_tready && !rx_packet_open;
    assign idle=!rst && outstanding==0 && !rx_packet_open && state==PARSE &&
                unpack_idle && !in_valid && window_idle && json_idle && proto_idle && !m_axis_text_tvalid && schema_idle;
    // Register the full empty-pipeline proof before the wide CAM write enable.
    // Immediate admission counters prevent a previous idle proof from allowing
    // a schema change after a new RX packet has entered the burst FIFO.
    always @(posedge clk)if(rst)schema_quiet<=0;else schema_quiet<=idle;
    always @(posedge clk)begin
        if(state==READ_REQ)read_byte<=text_memory[read_index];
        if(!rst && state==PARSE && decoded_valid && decoded_keep && text_count<MAX_TEXT_BYTES)
            text_memory[text_count]<=decoded_data;
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=PARSE;outstanding<=0;rx_packet_open<=0;rx_format<=0;rx_context<=0;
            active<=0;feed_done<=0;current_mode<=0;overflow<=0;transport_aborted<=0;context_id<=0;
            text_count<=0;read_index<=0;error_code<=0;
        end else begin
            case({admit,retire})
                2'b10:outstanding<=outstanding+1'b1;
                2'b01:outstanding<=outstanding-1'b1;
                default:begin end
            endcase
            if(s_axis_rx_tvalid && s_axis_rx_tready)begin
                if(!rx_packet_open)begin rx_format<=cfg_protobuf;rx_context<=s_axis_rx_tuser;end
                rx_packet_open<=!s_axis_rx_tlast;
            end
            if(in_valid && in_ready)begin
                if(!active)begin active<=1;current_mode<=in_user[USER_WIDTH];context_id<=in_user[USER_WIDTH-1:0];end
                if(in_last)feed_done<=1;
                if(in_user[USER_WIDTH+1])transport_aborted<=1;
            end
            case(state)
                PARSE:if(decoded_valid)begin
                    if(decoded_keep)begin
                        if(text_count<MAX_TEXT_BYTES)text_count<=text_count+1'b1;
                        else overflow<=1;
                    end
                    if(decoded_last)begin
                        if(decoded_status!=0 || overflow || abort_now)begin
                            error_code<=abort_now ? 8'h81 : overflow ? 8'h80 : current_mode ? (8'h40|decoded_status) : decoded_status;
                            state<=ERROR_STATE;
                        end else begin read_index<=0;state<=text_count==0 ? END_MARKER : READ_REQ;end
                    end
                end
                READ_REQ:state<=READ_WAIT;
                READ_WAIT:state<=EMIT;
                EMIT:if(pack_ready)begin
                    if(read_index+1==text_count)state<=END_MARKER;
                    else begin read_index<=read_index+1'b1;state<=READ_REQ;end
                end
                END_MARKER:if(pack_ready)state<=WAIT_TX;
                default:begin end
            endcase
            if(retire)begin state<=PARSE;active<=0;feed_done<=0;overflow<=0;transport_aborted<=0;text_count<=0;read_index<=0;end
        end
    end
endmodule
`default_nettype wire
