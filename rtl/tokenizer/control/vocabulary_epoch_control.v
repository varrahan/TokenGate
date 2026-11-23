`timescale 1ns/1ps
`default_nettype none
// Host asserts update_req and waits for cfg_unlock before writing any table.
// Runtime admission stops immediately; already accepted work drains first.
// Validation is performed by the loader, which explicitly commits or aborts.
// An abort keeps traffic disabled until a valid vocabulary is committed.
module vocabulary_epoch_control #(
    parameter integer EPOCH_WIDTH=32
)(
    input wire clk, input wire rst,
    input wire update_req, input wire commit, input wire abort_update,
    input wire tables_valid, input wire datapath_idle,
    output wire admit_sequences, output wire cfg_unlock,
    output reg [EPOCH_WIDTH-1:0] epoch,
    output reg vocabulary_valid, output reg protocol_error,
    output wire draining
);
    localparam LOCKED=0, RUNNING=1, DRAINING=2, LOADING=3;
    reg [1:0] state;
    assign cfg_unlock = state == LOADING;
    assign draining = state == DRAINING;
    assign admit_sequences = state == RUNNING && !update_req;
    always @(posedge clk) begin
        if (rst) begin
            state <= LOCKED;
            epoch <= 0;
            vocabulary_valid <= 0;
            protocol_error <= 0;
        end else begin
            protocol_error <= 0;
            if ((commit || abort_update) && state != LOADING) protocol_error <= 1;
            case (state)
                LOCKED: if (update_req) state <= DRAINING;
                RUNNING: if (update_req) state <= DRAINING;
                DRAINING: if (datapath_idle) begin
                    state <= LOADING;
                    vocabulary_valid <= 0;
                end
                LOADING: begin
                    if (abort_update) state <= LOCKED;
                    else if (commit) begin
                        // The shared idle indication must include pending
                        // external configuration writes and their responses.
                        if (tables_valid && datapath_idle) begin
                            epoch <= epoch+1'b1;
                            vocabulary_valid <= 1;
                            state <= RUNNING;
                        end else protocol_error <= 1;
                    end
                end
                default: state <= LOCKED;
            endcase
        end
    end
endmodule
`default_nettype wire
