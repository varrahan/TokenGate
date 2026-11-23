`timescale 1ns/1ps
`default_nettype none
// Streaming RFC 7541 string decoding, MSB first, one code bit per enabled
// clock. A synchronous fixed protocol ROM feeds the next branch each cycle.
// Each successful string ends with a separate keep=0/last=1 record. Decoded
// bytes before that marker are tentative; a parent must discard them on error.
module hpack_huffman_decoder #(parameter integer USER_WIDTH=16)(
    input wire clk,input wire rst,
    input wire [7:0] s_data,input wire s_keep,input wire s_valid,output wire s_ready,input wire s_last,input wire [USER_WIDTH-1:0] s_user,
    output reg [7:0] m_data,output reg m_keep,output reg m_valid,input wire m_ready,output reg m_last,output wire [USER_WIDTH-1:0] m_user,
    output wire error_valid,input wire error_ready,output reg [7:0] error_code,output wire [USER_WIDTH-1:0] error_user,output wire idle
);
    localparam IDLE=0,BITS=1,NEXT_BYTE=2,EOF_RECORD=3,FINISH=4,DRAIN=5,ERROR_STATE=6;
    reg [2:0] state,bit_index;
    reg [7:0] byte_value;
    reg byte_last,tail_ones;
    reg [5:0] tail_bits;
    reg [USER_WIDTH-1:0] context_id;
    wire [19:0] branches;
    wire [9:0] edge_value=byte_value[bit_index]?branches[19:10]:branches[9:0];
    wire leaf=edge_value[9];
    wire eos=leaf&&edge_value[8:0]==256;
    wire [5:0] next_tail_bits=leaf?6'd0:tail_bits+1'b1;
    wire next_tail_ones=leaf?1'b1:tail_ones&&byte_value[bit_index];
    wire final_padding_good=next_tail_bits==0||(next_tail_bits<=7&&next_tail_ones);
    wire saved_padding_good=tail_bits==0||(tail_bits<=7&&tail_ones);
    wire advance=!rst&&state==BITS&&(!m_valid||m_ready);
    wire start=!rst&&state==IDLE&&s_valid&&s_ready&&s_keep;
    wire rom_en=start||(advance&&!eos);
    wire [7:0] rom_address=start||leaf?8'd0:edge_value[7:0];
    hpack_huffman_rom codebook(.clk(clk),.en(rom_en),.address(rom_address),.data(branches));
    assign s_ready=!rst&&(state==IDLE||state==NEXT_BYTE||state==DRAIN);
    assign m_user=context_id;
    assign error_valid=state==ERROR_STATE&&!m_valid;
    assign error_user=context_id;
    assign idle=state==IDLE&&!m_valid&&!(s_valid&&s_ready&&(s_keep||s_last));
    task fail(input [7:0] code,input ended);
        begin error_code<=code;state<=ended?ERROR_STATE:DRAIN;end
    endtask
    always @(posedge clk)begin
        if(rst)begin
            state<=IDLE;bit_index<=0;byte_value<=0;byte_last<=0;tail_ones<=1;tail_bits<=0;context_id<=0;
            m_data<=0;m_keep<=0;m_valid<=0;m_last<=0;error_code<=0;
        end else begin
            if(m_valid&&m_ready)m_valid<=0;
            case(state)
                IDLE:if(s_valid&&s_ready&&(s_keep||s_last))begin
                    context_id<=s_user;tail_bits<=0;tail_ones<=1;error_code<=0;
                    if(s_keep)begin byte_value<=s_data;byte_last<=s_last;bit_index<=7;state<=BITS;end
                    else state<=EOF_RECORD;
                end
                BITS:if(advance)begin
                    if(eos)fail(1,byte_last);
                    else if(!leaf&&edge_value[8])fail(4,byte_last);
                    else begin
                        tail_bits<=next_tail_bits;tail_ones<=next_tail_ones;
                        if(leaf)begin m_data<=edge_value[7:0];m_keep<=1;m_valid<=1;m_last<=0;end
                        if(bit_index!=0)bit_index<=bit_index-1'b1;
                        else if(byte_last)begin if(final_padding_good)state<=EOF_RECORD;else fail(2,1'b1);end
                        else state<=NEXT_BYTE;
                    end
                end
                NEXT_BYTE:if(s_valid&&s_ready&&(s_keep||s_last))begin
                    if(s_user!=context_id)fail(3,s_last);
                    else if(s_keep)begin byte_value<=s_data;byte_last<=s_last;bit_index<=7;state<=BITS;end
                    else if(saved_padding_good)state<=EOF_RECORD;else fail(2,1'b1);
                end
                EOF_RECORD:if(!m_valid||m_ready)begin m_data<=0;m_keep<=0;m_valid<=1;m_last<=1;state<=FINISH;end
                FINISH:if(m_valid&&m_ready)state<=IDLE;
                DRAIN:if(s_valid&&s_ready&&s_last)state<=ERROR_STATE;
                ERROR_STATE:if(error_valid&&error_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
