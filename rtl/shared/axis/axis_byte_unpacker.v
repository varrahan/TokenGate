`timescale 1ns/1ps
`default_nettype none
// Removes invalid byte lanes while preserving packet end and context.
// End is a separate keep=0 record, so sparse/empty final beats are unambiguous.
module axis_byte_unpacker #(
    parameter integer DATA_WIDTH=512,
    parameter integer USER_WIDTH=16
)(
    input wire clk, input wire rst,
    input wire [DATA_WIDTH-1:0] s_data,
    input wire [DATA_WIDTH/8-1:0] s_keep,
    input wire s_valid, output wire s_ready,
    input wire s_last, input wire [USER_WIDTH-1:0] s_user,
    output wire [7:0] m_data, output wire m_keep,
    output wire m_valid, input wire m_ready,
    output wire m_last, output wire [USER_WIDTH-1:0] m_user,
    output wire idle
);
    localparam integer BYTES=DATA_WIDTH/8;
    reg [DATA_WIDTH-1:0] data_reg;
    reg [BYTES-1:0] keep_reg;
    reg [USER_WIDTH-1:0] user_reg;
    reg valid_reg,last_reg;
    integer first;
    integer i;
    always @* begin
        first=0;
        for(i=BYTES-1;i>=0;i=i-1) if(keep_reg[i]) first=i;
    end
    wire has_byte = |keep_reg;
    assign idle = !valid_reg;
    assign s_ready = !rst && !valid_reg;
    assign m_data = data_reg[first*8 +: 8];
    assign m_keep = has_byte;
    assign m_valid = valid_reg && (has_byte || last_reg);
    assign m_last = !has_byte && last_reg;
    assign m_user = user_reg;
    always @(posedge clk) begin
        if (rst) begin
            valid_reg<=0; last_reg<=0; keep_reg<=0; data_reg<=0; user_reg<=0;
        end else begin
            if (valid_reg && !has_byte && (!last_reg || m_ready)) valid_reg<=0;
            if (m_valid && m_ready && has_byte) keep_reg[first]<=0;
            if (s_valid && s_ready) begin
                data_reg<=s_data; keep_reg<=s_keep; user_reg<=s_user;
                valid_reg<=1; last_reg<=s_last;
            end
        end
    end
endmodule
`default_nettype wire
