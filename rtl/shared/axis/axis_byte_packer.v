`timescale 1ns/1ps
`default_nettype none
// Compacts byte records into AXI beats. A keep=0,last=1 record terminates an
// empty packet, or terminates a previously accumulated packet without a byte.
// A full beat is held until another byte or the end marker identifies TLAST.
module axis_byte_packer #(
    parameter integer DATA_WIDTH=128,
    parameter integer USER_WIDTH=16
)(
    input wire clk, input wire rst,
    input wire [7:0] s_data, input wire s_keep,
    input wire s_valid, output wire s_ready,
    input wire s_last, input wire [USER_WIDTH-1:0] s_user,
    output wire [DATA_WIDTH-1:0] m_data,
    output wire [DATA_WIDTH/8-1:0] m_keep,
    output wire m_valid, input wire m_ready,
    output wire m_last, output wire [USER_WIDTH-1:0] m_user
);
    localparam integer BYTES=DATA_WIDTH/8;
    localparam integer COUNT_WIDTH=$clog2(BYTES+1);
    reg [DATA_WIDTH-1:0] data_reg;
    reg [BYTES-1:0] keep_reg;
    reg [COUNT_WIDTH-1:0] count;
    reg [USER_WIDTH-1:0] user_reg;
    reg end_pending;
    // On a full unterminated buffer, inspect only valid/keep/last to decide
    // whether the next record appends data or supplies the final marker.
    wire full = count == BYTES;
    wire next_byte = s_valid && s_keep;
    assign m_valid = end_pending || (full && next_byte);
    assign m_last = end_pending;
    assign m_data = data_reg;
    assign m_keep = keep_reg;
    assign m_user = user_reg;
    assign s_ready = !rst && !end_pending && (!full ||
                     (!s_keep) || (m_ready && next_byte));
    always @(posedge clk) begin
        if (rst) begin
            data_reg<=0; keep_reg<=0; count<=0; user_reg<=0; end_pending<=0;
        end else begin
            if (m_valid && m_ready) begin
                data_reg<=0; keep_reg<=0; count<=0; end_pending<=0;
            end
            if (s_valid && s_ready) begin
                if (count==0 || (full && s_keep)) user_reg<=s_user;
                if (s_keep) begin
                    if (full) begin
                        data_reg<={{(DATA_WIDTH-8){1'b0}},s_data};
                        keep_reg<={{(BYTES-1){1'b0}},1'b1}; count<=1;
                    end else begin
                        data_reg[count*8 +: 8]<=s_data;
                        keep_reg[count]<=1;
                        count<=count+1'b1;
                    end
                end
                if (s_last) end_pending<=1;
            end
        end
    end
endmodule
`default_nettype wire
