`timescale 1ns/1ps
`default_nettype none
// Transactional application message -> uncompressed gRPC record -> HTTP/2 DATA.
// A frame grant reserves connection AND stream credit for frame_grant_bytes,
// in 1..frame_req_max_bytes. Partial grants avoid small-window deadlock.
// Headers/trailers, credit accounting, RPC/image leases and a physical/TCP
// adapter belong to the parent transport. DATA never carries END_STREAM:
// the gRPC trailer block must close the stream. Reset requires a fenced
// connection/link reset; it does not refund already-reserved credits.
module grpc_http2_response_framer #(
    parameter integer USER_WIDTH=16,parameter integer MAX_MESSAGE_BYTES=65535
)(
    input wire clk,input wire rst,
    input wire start_valid,output wire start_ready,input wire [USER_WIDTH-1:0] start_user,
    input wire [30:0] start_stream,input wire [23:0] cfg_peer_max_frame_bytes,
    input wire [511:0] s_axis_message_tdata,input wire [63:0] s_axis_message_tkeep,
    input wire s_axis_message_tvalid,output wire s_axis_message_tready,
    input wire s_axis_message_tlast,input wire [USER_WIDTH-1:0] s_axis_message_tuser,
    input wire s_axis_message_abort,
    output wire frame_req_valid,input wire frame_req_ready,
    output wire [USER_WIDTH-1:0] frame_req_user,output wire [30:0] frame_req_stream,
    output wire [23:0] frame_req_max_bytes,input wire [23:0] frame_grant_bytes,
    output wire [511:0] m_axis_tx_tdata,output wire [63:0] m_axis_tx_tkeep,
    output wire m_axis_tx_tvalid,input wire m_axis_tx_tready,output wire m_axis_tx_tlast,
    output wire [USER_WIDTH-1:0] m_axis_tx_tuser,
    output wire result_valid,input wire result_ready,output wire [7:0] result_status,
    output wire [USER_WIDTH-1:0] result_user,output wire [30:0] result_stream,
    output wire [31:0] result_message_bytes,result_wire_bytes,result_frames,
    output wire result_tx_emitted,output wire idle
);
    localparam IDLE=0,COLLECT=1,PLAN=2,CREDIT=3,HEADER=4,PREFIX=5,
        READ_REQ=6,READ_WAIT=7,PAYLOAD=8,DRAIN_FRAME=9,RESULT=10;
    localparam integer ADDRESS_WIDTH=MAX_MESSAGE_BYTES<=1?1:$clog2(MAX_MESSAGE_BYTES);
    reg [3:0] state,header_index;
    reg [USER_WIDTH-1:0] owner;
    reg [30:0] stream_id;
    reg [23:0] maximum,frame_limit,frame_length,frame_left;
    reg [31:0] message_bytes,remaining,record_index,payload_index,wire_bytes,frames;
    reg [7:0] status,read_byte;
    reg tx_emitted;
    (* ram_style="block" *) reg [7:0] message_memory[0:MAX_MESSAGE_BYTES-1];
    wire [7:0] input_byte;
    wire input_keep,input_valid,input_last,input_ready,unpack_ready,unpack_idle;
    wire [USER_WIDTH:0] input_user;
    assign input_ready=state==COLLECT;
    assign s_axis_message_tready=state==COLLECT&&unpack_ready;
    axis_byte_unpacker #(.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH+1)) input_bytes(
        .clk(clk),.rst(rst),.s_data(s_axis_message_tdata),.s_keep(s_axis_message_tkeep),
        .s_valid(s_axis_message_tvalid&&state==COLLECT),.s_ready(unpack_ready),
        .s_last(s_axis_message_tlast),.s_user({s_axis_message_abort,s_axis_message_tuser}),
        .m_data(input_byte),.m_keep(input_keep),.m_valid(input_valid),.m_ready(input_ready),
        .m_last(input_last),.m_user(input_user),.idle(unpack_idle));
    wire [7:0] input_failure=input_user[USER_WIDTH]?8'd4:
        input_user[USER_WIDTH-1:0]!=owner?8'd3:
        input_keep&&message_bytes==MAX_MESSAGE_BYTES?8'd2:8'd0;
    wire pack_ready;
    reg [7:0] pack_byte;
    wire pack_valid=state==HEADER||state==PREFIX||state==PAYLOAD;
    wire pack_last=state!=HEADER&&frame_left==1;
    always @*begin
        pack_byte=0;
        case(state)
            HEADER:case(header_index)
                0:pack_byte=frame_length[23:16];
                1:pack_byte=frame_length[15:8];
                2:pack_byte=frame_length[7:0];
                3:pack_byte=0; // DATA
                4:pack_byte=0; // No padding, no END_STREAM.
                5:pack_byte={1'b0,stream_id[30:24]};
                6:pack_byte=stream_id[23:16];
                7:pack_byte=stream_id[15:8];
                8:pack_byte=stream_id[7:0];
                default:pack_byte=0;
            endcase
            PREFIX:case(record_index)
                0:pack_byte=0; // Uncompressed gRPC message.
                1:pack_byte=message_bytes[31:24];
                2:pack_byte=message_bytes[23:16];
                3:pack_byte=message_bytes[15:8];
                4:pack_byte=message_bytes[7:0];
                default:pack_byte=0;
            endcase
            PAYLOAD:pack_byte=read_byte;
            default:pack_byte=0;
        endcase
    end
    axis_byte_packer #(.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)) output_bytes(
        .clk(clk),.rst(rst),.s_data(pack_byte),.s_keep(1'b1),.s_valid(pack_valid),
        .s_ready(pack_ready),.s_last(pack_last),.s_user(owner),
        .m_data(m_axis_tx_tdata),.m_keep(m_axis_tx_tkeep),.m_valid(m_axis_tx_tvalid),
        .m_ready(m_axis_tx_tready),.m_last(m_axis_tx_tlast),.m_user(m_axis_tx_tuser));
    assign start_ready=!rst&&state==IDLE&&unpack_idle;
    assign frame_req_valid=!rst&&state==CREDIT;
    assign frame_req_user=owner;assign frame_req_stream=stream_id;assign frame_req_max_bytes=frame_limit;
    assign result_valid=state==RESULT;assign result_status=status;
    assign result_user=owner;assign result_stream=stream_id;
    assign result_message_bytes=status==0?message_bytes:32'd0;
    assign result_wire_bytes=wire_bytes;assign result_frames=frames;assign result_tx_emitted=tx_emitted;
    assign idle=state==IDLE&&unpack_idle&&!m_axis_tx_tvalid;
    initial begin
        if(MAX_MESSAGE_BYTES<1||MAX_MESSAGE_BYTES>32'hfffffff0||USER_WIDTH<1)$error("Unsupported framer capacity");
    end
    always @(posedge clk)begin
        if(state==READ_REQ)read_byte<=message_memory[payload_index[ADDRESS_WIDTH-1:0]];
        if(!rst&&state==COLLECT&&input_valid&&input_ready&&input_keep&&status==0&&input_failure==0)
            message_memory[message_bytes[ADDRESS_WIDTH-1:0]]<=input_byte;
    end
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;header_index<=0;owner<=0;stream_id<=0;maximum<=0;frame_limit<=0;frame_length<=0;frame_left<=0;
            message_bytes<=0;remaining<=0;record_index<=0;payload_index<=0;wire_bytes<=0;frames<=0;status<=0;tx_emitted<=0;
        end else begin
            if(m_axis_tx_tvalid&&m_axis_tx_tready)tx_emitted<=1;
            case(state)
                IDLE:if(start_valid&&start_ready)begin
                    owner<=start_user;stream_id<=start_stream;maximum<=cfg_peer_max_frame_bytes;
                    status<=start_stream==0||cfg_peer_max_frame_bytes<16384?8'd1:8'd0;
                    message_bytes<=0;record_index<=0;payload_index<=0;wire_bytes<=0;frames<=0;tx_emitted<=0;
                    state<=COLLECT;
                end
                COLLECT:if(input_valid&&input_ready)begin
                    if(status==0&&input_failure!=0)status<=input_failure;
                    if(status==0&&input_failure==0&&input_keep)message_bytes<=message_bytes+1'b1;
                    if(input_last)begin
                        if(status!=0||input_failure!=0)state<=RESULT;
                        else begin remaining<=message_bytes+5+(input_keep?1:0);state<=PLAN;end
                    end
                end
                PLAN:begin
                    frame_limit<=remaining<=maximum?remaining[23:0]:maximum;
                    state<=CREDIT;
                end
                CREDIT:if(frame_req_ready)begin
                    if(frame_grant_bytes==0||frame_grant_bytes>frame_limit)begin status<=5;state<=RESULT;end
                    else begin frame_length<=frame_grant_bytes;frame_left<=frame_grant_bytes;header_index<=0;state<=HEADER;end
                end
                HEADER:if(pack_ready)begin
                    if(header_index==8)state<=record_index<5?PREFIX:READ_REQ;
                    else header_index<=header_index+1'b1;
                end
                PREFIX,PAYLOAD:if(pack_ready)begin
                    record_index<=record_index+1'b1;remaining<=remaining-1'b1;frame_left<=frame_left-1'b1;
                    if(state==PAYLOAD)payload_index<=payload_index+1'b1;
                    if(frame_left==1)state<=DRAIN_FRAME;
                    else if(state==PREFIX&&record_index<4)state<=PREFIX;
                    else state<=READ_REQ;
                end
                READ_REQ:state<=READ_WAIT;
                READ_WAIT:state<=PAYLOAD;
                DRAIN_FRAME:if(m_axis_tx_tvalid&&m_axis_tx_tready&&m_axis_tx_tlast)begin
                    frames<=frames+1'b1;wire_bytes<=wire_bytes+9+frame_length;
                    state<=remaining==0?RESULT:PLAN;
                end
                RESULT:if(result_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
