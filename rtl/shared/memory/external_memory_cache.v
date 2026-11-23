`timescale 1ns/1ps
`default_nettype none
// Single-outstanding external-memory client, backed by a direct-mapped BRAM
// cache. Read/write commands address 1..9 arbitrary bytes, little endian.
// AXI4 is 64-bit, single-ID, with 8-beat line refills and byte-strobed writes.
// Status: 0=OK, 1=bad request, 2=RRESP error, 3=burst protocol, 4=BRESP error.
module external_memory_cache #(
    parameter integer ADDR_WIDTH=23,
    parameter integer CACHE_LOG_LINES=6
)(
    input wire clk,input wire rst,
    input wire invalidate_valid,output wire invalidate_ready,
    input wire rd_valid,output wire rd_ready,input wire [ADDR_WIDTH-1:0] rd_addr,input wire [3:0] rd_bytes,
    output wire rd_rsp_valid,input wire rd_rsp_ready,output reg [71:0] rd_rsp_data,output reg [7:0] rd_rsp_status,
    input wire wr_valid,output wire wr_ready,input wire [ADDR_WIDTH-1:0] wr_addr,input wire [3:0] wr_bytes,input wire [71:0] wr_data,
    output wire wr_rsp_valid,input wire wr_rsp_ready,output reg [7:0] wr_rsp_status,
    output wire [ADDR_WIDTH-1:0] m_axi_araddr,output wire [7:0] m_axi_arlen,
    output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,
    output wire m_axi_arvalid,input wire m_axi_arready,
    input wire [63:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rlast,
    input wire m_axi_rvalid,output wire m_axi_rready,
    output wire [ADDR_WIDTH-1:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,
    output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,
    output wire m_axi_awvalid,input wire m_axi_awready,
    output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,output wire m_axi_wlast,
    output wire m_axi_wvalid,input wire m_axi_wready,
    input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
    output wire idle
);
    localparam IDLE=0,LOOKUP=1,CACHE_REQ=2,CACHE_WAIT=3,MISS_AR=4,REFILL=5,
               READ_RESULT=6,WRITE_CHANNELS=7,WRITE_RESP=8,WRITE_RESULT=9;
    localparam integer LINES=2**CACHE_LOG_LINES;
    localparam integer TAG_WIDTH=ADDR_WIDTH-6-CACHE_LOG_LINES;
    reg [3:0] state;
    reg [LINES-1:0] valid_lines;
    reg [TAG_WIDTH-1:0] tags[0:LINES-1];
    reg [ADDR_WIDTH-1:0] read_address,word_address,write_address;
    reg [3:0] read_length,refill_beat;
    reg need_second,second_word;
    reg [63:0] first_word;
    reg [7:0] refill_status;
    reg write_second,write_index,aw_done,w_done;
    reg [127:0] write_payload;
    reg [15:0] write_strobes;
    wire [CACHE_LOG_LINES-1:0] line_index=word_address[CACHE_LOG_LINES+5:6];
    wire [TAG_WIDTH-1:0] line_tag=word_address[ADDR_WIDTH-1:CACHE_LOG_LINES+6];
    wire cache_cfg_ready,cache_rd_ready,cache_rsp_valid;
    wire [63:0] cache_rsp_data;
    programmable_table_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(CACHE_LOG_LINES+3),.READ_LATENCY(2),.MEMORY_PRIMITIVE("block")) cache_words (
        .clk(clk),.rst(rst),.cfg_unlock(state==REFILL),
        .cfg_valid(state==REFILL && m_axi_rvalid && m_axi_rready && refill_beat<8),
        .cfg_ready(cache_cfg_ready),.cfg_addr({line_index,refill_beat[2:0]}),.cfg_data(m_axi_rdata),
        .rd_valid(state==CACHE_REQ),.rd_ready(cache_rd_ready),
        .rd_addr(word_address[CACHE_LOG_LINES+5:3]),.rsp_valid(cache_rsp_valid),.rsp_data(cache_rsp_data));
    wire [ADDR_WIDTH:0] read_end={1'b0,rd_addr}+rd_bytes;
    wire [ADDR_WIDTH:0] write_end={1'b0,wr_addr}+wr_bytes;
    wire read_good=rd_bytes>=1 && rd_bytes<=9 && read_end<=(2**ADDR_WIDTH);
    wire write_good=wr_bytes>=1 && wr_bytes<=9 && write_end<=(2**ADDR_WIDTH);
    wire [ADDR_WIDTH-1:0] write_last_address=write_end-1'b1;
    wire [127:0] joined_words=second_word ? {cache_rsp_data,first_word} : {64'd0,cache_rsp_data};
    wire [127:0] shifted_words=joined_words>>(read_address[2:0]*8);
    wire [71:0] read_mask=72'hffffffffffffffffff>>((9-read_length)*8);
    assign invalidate_ready=!rst && state==IDLE;
    assign wr_ready=!rst && state==IDLE && !invalidate_valid;
    assign rd_ready=!rst && state==IDLE && !invalidate_valid && !wr_valid;
    assign rd_rsp_valid=state==READ_RESULT;
    assign wr_rsp_valid=state==WRITE_RESULT;
    assign idle=state==IDLE;
    assign m_axi_araddr={word_address[ADDR_WIDTH-1:6],6'd0};
    assign m_axi_arlen=7;
    assign m_axi_arsize=3;
    assign m_axi_arburst=1;
    assign m_axi_arvalid=state==MISS_AR;
    assign m_axi_rready=state==REFILL && (refill_beat>=8 || cache_cfg_ready);
    assign m_axi_awaddr=write_address;
    assign m_axi_awlen=write_second ? 1 : 0;
    assign m_axi_awsize=3;
    assign m_axi_awburst=1;
    // AW and W start independently, including W-before-AW slave behavior.
    assign m_axi_awvalid=state==WRITE_CHANNELS && !aw_done;
    assign m_axi_wvalid=state==WRITE_CHANNELS && !w_done;
    assign m_axi_wdata=write_index ? write_payload[127:64] : write_payload[63:0];
    assign m_axi_wstrb=write_index ? write_strobes[15:8] : write_strobes[7:0];
    assign m_axi_wlast=!write_second || write_index;
    assign m_axi_bready=state==WRITE_RESP;
    wire aw_accept=m_axi_awvalid && m_axi_awready;
    wire w_accept=m_axi_wvalid && m_axi_wready;
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;valid_lines<=0;read_address<=0;word_address<=0;write_address<=0;
            read_length<=0;refill_beat<=0;need_second<=0;second_word<=0;first_word<=0;refill_status<=0;
            write_second<=0;write_index<=0;aw_done<=0;w_done<=0;write_payload<=0;write_strobes<=0;
            rd_rsp_data<=0;rd_rsp_status<=0;wr_rsp_status<=0;
        end else case(state)
            IDLE:begin
                if(invalidate_valid)valid_lines<=0;
                else if(wr_valid)begin
                    wr_rsp_status<=0;
                    if(!write_good)begin wr_rsp_status<=1;state<=WRITE_RESULT;end
                    else begin
                        write_address<={wr_addr[ADDR_WIDTH-1:3],3'd0};
                        write_payload<={56'd0,wr_data}<<(wr_addr[2:0]*8);
                        write_strobes<=(16'hffff>>(16-wr_bytes))<<wr_addr[2:0];
                        write_second<=({2'b0,wr_addr[2:0]}+{1'b0,wr_bytes})>5'd8;
                        write_index<=0;aw_done<=0;w_done<=0;
                        valid_lines[wr_addr[CACHE_LOG_LINES+5:6]]<=0;
                        valid_lines[write_last_address[CACHE_LOG_LINES+5:6]]<=0;
                        state<=WRITE_CHANNELS;
                    end
                end else if(rd_valid)begin
                    rd_rsp_data<=0;rd_rsp_status<=0;
                    if(!read_good)begin rd_rsp_status<=1;state<=READ_RESULT;end
                    else begin
                        read_address<=rd_addr;read_length<=rd_bytes;
                        word_address<={rd_addr[ADDR_WIDTH-1:3],3'd0};second_word<=0;first_word<=0;
                        need_second<=({2'b0,rd_addr[2:0]}+{1'b0,rd_bytes})>5'd8;state<=LOOKUP;
                    end
                end
            end
            LOOKUP:if(valid_lines[line_index] && tags[line_index]==line_tag)state<=CACHE_REQ;
                   else begin valid_lines[line_index]<=0;refill_beat<=0;refill_status<=0;state<=MISS_AR;end
            CACHE_REQ:if(cache_rd_ready)state<=CACHE_WAIT;
            CACHE_WAIT:if(cache_rsp_valid)begin
                if(!second_word && need_second)begin first_word<=cache_rsp_data;word_address<=word_address+8;second_word<=1;state<=LOOKUP;end
                else begin rd_rsp_data<=shifted_words[71:0]&read_mask;rd_rsp_status<=0;state<=READ_RESULT;end
            end
            MISS_AR:if(m_axi_arready)state<=REFILL;
            REFILL:if(m_axi_rvalid && m_axi_rready)begin
                if(m_axi_rresp!=0 && refill_status==0)refill_status<=2;
                if(refill_beat>=7 && !m_axi_rlast)refill_status<=3;
                if(m_axi_rlast)begin
                    if(refill_beat!=7 || refill_status==3)begin rd_rsp_status<=3;state<=READ_RESULT;end
                    else if(refill_status!=0 || m_axi_rresp!=0)begin rd_rsp_status<=2;state<=READ_RESULT;end
                    else begin tags[line_index]<=line_tag;valid_lines[line_index]<=1;state<=LOOKUP;end
                end else if(refill_beat<8)refill_beat<=refill_beat+1'b1;
            end
            READ_RESULT:if(rd_rsp_ready)state<=IDLE;
            WRITE_CHANNELS:begin
                if(aw_accept)aw_done<=1;
                if(w_accept)begin if(m_axi_wlast)w_done<=1;else write_index<=1;end
                if((aw_done||aw_accept) && (w_done||(w_accept&&m_axi_wlast)))state<=WRITE_RESP;
            end
            WRITE_RESP:if(m_axi_bvalid)begin wr_rsp_status<=m_axi_bresp==0 ? 0 : 4;state<=WRITE_RESULT;end
            WRITE_RESULT:if(wr_rsp_ready)state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
