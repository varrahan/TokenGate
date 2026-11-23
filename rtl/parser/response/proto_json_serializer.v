`timescale 1ns/1ps
`default_nettype none
// Application message serializer. HTTP/HTTP2/gRPC transport framing is a
// separate required layer. Formats: 0=JSON delta, 1=SSE delta, 2=Protobuf.
// Length-delimited Protobuf requires buffering a complete text message before
// emitting its header. Oversize messages are drained and reported, not clipped.
module proto_json_serializer #(
    parameter integer MAX_TEXT_BYTES=16384,
    parameter integer USER_WIDTH=16,
    parameter integer ABORT_SUPPORT=0
)(
    input wire clk,input wire rst,
    input wire [1:0] cfg_format,input wire [28:0] cfg_protobuf_field,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,
    input wire s_axis_text_tlast,input wire [USER_WIDTH-1:0] s_axis_text_tuser,
    input wire s_axis_text_abort,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,
    output wire m_axis_tx_tlast,output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output reg error_valid,input wire error_ready,
    output reg [7:0] error_code,output reg [USER_WIDTH-1:0] error_user,
    output wire idle
);
    localparam integer CW=$clog2(MAX_TEXT_BYTES+1);
    localparam COLLECT=0,PREFIX=1,PROTO_HEADER=2,PAY_REQ=3,PAY_WAIT=4,
               PAY_SEND=5,PAY_EMPTY=6,PAY_DRAIN=7,FOOTER=8,FINAL=9,
               WAIT_TX=10,DROP=11,ERROR_WAIT=12;
    localparam [263:0] JSON_PREFIX="{\"choices\":[{\"delta\":{\"content\":\"";
    localparam [47:0] SSE_PREFIX="data: ";
    localparam [39:0] JSON_SUFFIX="\"}}]}";
    reg [3:0] state;
    (* ram_style="block" *) reg [7:0] text_memory[0:MAX_TEXT_BYTES-1];
    reg [7:0] read_byte;
    reg [CW-1:0] byte_count,payload_index;
    reg [5:0] template_index;
    reg [1:0] format_mode;
    reg [USER_WIDTH-1:0] context_id;
    reg packet_open,header_length;
    reg [63:0] header_value;
    wire [7:0] in_byte;
    wire in_keep,in_valid,in_ready,in_last,unpack_idle,input_ready;
    wire [USER_WIDTH-1:0] in_user;
    wire [USER_WIDTH:0] unpack_user;
    wire in_abort=ABORT_SUPPORT&&unpack_user[USER_WIDTH];
    assign in_user=unpack_user[USER_WIDTH-1:0];
    wire [1:0] selected_format=packet_open ? format_mode : cfg_format;
    reg [28:0] field_number;
    wire invalid_config=selected_format==3 || (selected_format==2 &&
                        (packet_open ? field_number : cfg_protobuf_field)==0);
    wire allow_input=state==COLLECT || state==DROP;
    assign s_axis_text_tready=input_ready && allow_input;
    axis_byte_unpacker #(.DATA_WIDTH(128),.USER_WIDTH(USER_WIDTH+1)) input_bytes (
        .clk(clk),.rst(rst),.s_data(s_axis_text_tdata),.s_keep(s_axis_text_tkeep),
        .s_valid(s_axis_text_tvalid&&allow_input),.s_ready(input_ready),
        .s_last(s_axis_text_tlast),.s_user({ABORT_SUPPORT?s_axis_text_abort:1'b0,s_axis_text_tuser}),
        .m_data(in_byte),.m_keep(in_keep),.m_valid(in_valid),.m_ready(in_ready),
        .m_last(in_last),.m_user(unpack_user),.idle(unpack_idle));
    assign in_ready=state==COLLECT || state==DROP;
    wire [7:0] esc_byte;
    wire esc_keep,esc_valid,esc_ready,esc_last,esc_input_ready;
    json_escape_encoder #(.USER_WIDTH(USER_WIDTH)) escape_encoder (
        .clk(clk),.rst(rst),.s_data(read_byte),.s_keep(state==PAY_SEND),
        .s_valid(format_mode!=2 && (state==PAY_SEND || state==PAY_EMPTY)),
        .s_ready(esc_input_ready),.s_last(state==PAY_EMPTY || payload_index+1==byte_count),
        .s_user(context_id),.m_data(esc_byte),.m_keep(esc_keep),
        .m_valid(esc_valid),.m_ready(esc_ready),.m_last(esc_last),.m_user());
    wire pack_ready;
    reg [7:0] pack_byte;
    reg pack_keep,pack_valid,pack_last;
    wire json_payload=format_mode!=2 && (state==PAY_REQ || state==PAY_WAIT ||
                      state==PAY_SEND || state==PAY_EMPTY || state==PAY_DRAIN);
    assign esc_ready=json_payload && (!esc_keep || pack_ready);
    integer json_index;
    always @* begin
        pack_byte=0;pack_keep=1;pack_valid=0;pack_last=0;json_index=template_index;
        case(state)
            PREFIX: begin
                pack_valid=1;
                if(format_mode==1 && template_index<6)
                    pack_byte=SSE_PREFIX[(5-template_index)*8+:8];
                else begin
                    if(format_mode==1)json_index=template_index-6;
                    pack_byte=JSON_PREFIX[(32-json_index)*8+:8];
                end
            end
            PROTO_HEADER: begin pack_valid=1;pack_byte={(header_value>=128),header_value[6:0]};end
            PAY_REQ,PAY_WAIT,PAY_SEND,PAY_EMPTY,PAY_DRAIN: begin
                if(format_mode==2) begin pack_valid=state==PAY_SEND;pack_byte=read_byte;end
                else begin pack_valid=esc_valid&&esc_keep;pack_byte=esc_byte;end
            end
            FOOTER: begin
                pack_valid=1;
                if(template_index<5)pack_byte=JSON_SUFFIX[(4-template_index)*8+:8];
                else pack_byte=8'h0a;
            end
            FINAL: begin pack_valid=1;pack_keep=0;pack_last=1;end
            default: begin end
        endcase
    end
    axis_byte_packer #(.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)) packet_builder (
        .clk(clk),.rst(rst),.s_data(pack_byte),.s_keep(pack_keep),.s_valid(pack_valid),
        .s_ready(pack_ready),.s_last(pack_last),.s_user(context_id),
        .m_data(m_axis_tx_tdata),.m_keep(m_axis_tx_tkeep),.m_valid(m_axis_tx_tvalid),
        .m_ready(m_axis_tx_tready),.m_last(m_axis_tx_tlast),.m_user(m_axis_tx_tuser));
    assign idle=state==COLLECT && !packet_open && unpack_idle && !m_axis_tx_tvalid;
    always @(posedge clk) begin
        if(state==PAY_REQ)read_byte<=text_memory[payload_index];
        if(!rst && state==COLLECT && in_valid && in_ready && in_keep &&
           byte_count<MAX_TEXT_BYTES && !invalid_config)text_memory[byte_count]<=in_byte;
    end
    always @(posedge clk) begin
        if(rst)begin
            state<=COLLECT;byte_count<=0;payload_index<=0;template_index<=0;
            format_mode<=0;context_id<=0;packet_open<=0;header_length<=0;
            header_value<=0;field_number<=0;error_valid<=0;error_code<=0;error_user<=0;
        end else begin
            if(error_valid && error_ready)error_valid<=0;
            if(s_axis_text_tvalid && s_axis_text_tready && !packet_open)begin
                context_id<=s_axis_text_tuser;format_mode<=cfg_format;
                field_number<=cfg_protobuf_field;packet_open<=1;
            end
            case(state)
                COLLECT: if(in_valid && in_ready)begin
                    if((in_last&&in_abort)||in_user!=context_id||invalid_config || (in_keep && byte_count==MAX_TEXT_BYTES))begin
                        error_valid<=1;error_code<=in_last&&in_abort?4:in_user!=context_id?3:invalid_config ? 2 : 1;error_user<=context_id;
                        state<=in_last ? ERROR_WAIT : DROP;
                    end else begin
                        if(in_keep)byte_count<=byte_count+1'b1;
                        if(in_last)begin
                            template_index<=0;payload_index<=0;
                            if(selected_format==2)begin
                                header_value<={32'd0,(packet_open ? field_number : cfg_protobuf_field),3'b010};
                                header_length<=0;state<=PROTO_HEADER;
                            end else state<=PREFIX;
                        end
                    end
                end
                PREFIX: if(pack_ready)begin
                    if(template_index==(format_mode==1 ? 38 : 32))
                        state<=byte_count==0 ? PAY_EMPTY : PAY_REQ;
                    else template_index<=template_index+1'b1;
                end
                PROTO_HEADER: if(pack_ready)begin
                    if(header_value>=128)header_value<=header_value>>7;
                    else if(!header_length)begin header_length<=1;header_value<=byte_count;end
                    else state<=byte_count==0 ? FINAL : PAY_REQ;
                end
                PAY_REQ:state<=PAY_WAIT;
                PAY_WAIT:state<=PAY_SEND;
                PAY_SEND: if(format_mode==2 ? pack_ready : esc_input_ready)begin
                    if(payload_index+1==byte_count)state<=format_mode==2 ? FINAL : PAY_DRAIN;
                    else begin payload_index<=payload_index+1'b1;state<=PAY_REQ;end
                end
                PAY_EMPTY: if(esc_input_ready)state<=PAY_DRAIN;
                PAY_DRAIN:begin end
                FOOTER:if(pack_ready)begin
                    if(template_index==(format_mode==1 ? 6 : 4))state<=FINAL;
                    else template_index<=template_index+1'b1;
                end
                FINAL:if(pack_ready)state<=WAIT_TX;
                WAIT_TX:if(m_axis_tx_tvalid && m_axis_tx_tready && m_axis_tx_tlast)begin
                    byte_count<=0;packet_open<=0;state<=COLLECT;
                end
                DROP:if(in_valid && in_last)state<=ERROR_WAIT;
                ERROR_WAIT:if(!error_valid || error_ready)begin byte_count<=0;packet_open<=0;state<=COLLECT;end
                default:state<=COLLECT;
            endcase
            if(json_payload && esc_valid && esc_ready && esc_last)begin
                template_index<=0;state<=FOOTER;
            end
        end
    end
endmodule
`default_nettype wire
