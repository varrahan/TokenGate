`timescale 1ns/1ps
`default_nettype none
// One runtime read port and a quiesced configuration write port.
// cfg_unlock is asserted only after the datapath has drained.
module programmable_table_ram #(
    parameter integer DATA_WIDTH=64,
    parameter integer ADDR_WIDTH=16,
    parameter integer READ_LATENCY=3,
    parameter MEMORY_PRIMITIVE="ultra"
)(
    input wire clk, input wire rst,
    input wire cfg_unlock,
    input wire cfg_valid, output wire cfg_ready,
    input wire [ADDR_WIDTH-1:0] cfg_addr,
    input wire [DATA_WIDTH-1:0] cfg_data,
    input wire rd_valid, output wire rd_ready,
    input wire [ADDR_WIDTH-1:0] rd_addr,
    output wire rsp_valid, output wire [DATA_WIDTH-1:0] rsp_data
);
    reg [READ_LATENCY-1:0] pending;
    wire write_en = cfg_valid && cfg_ready;
    wire read_en = rd_valid && rd_ready;
    assign cfg_ready = !rst && cfg_unlock && !(|pending);
    assign rd_ready = !rst && !cfg_unlock;
    assign rsp_valid = pending[READ_LATENCY-1];
    integer i;
    always @(posedge clk) begin
        if (rst) pending <= 0;
        else begin
            pending[0] <= read_en;
            for (i=1;i<READ_LATENCY;i=i+1) pending[i] <= pending[i-1];
        end
    end
`ifdef PARSER_PORTABLE_SIM
    // Functional no-ECC simulation backend for open-source Linux simulators.
    // It preserves the wrapper's uninitialized storage, synchronous read,
    // READ_LATENCY pipeline, reset value and quiesced-write contract.
`ifdef SYNTHESIS
    initial $error("PARSER_PORTABLE_SIM is not a synthesis configuration");
`endif
    reg [DATA_WIDTH-1:0] portable_memory[0:2**ADDR_WIDTH-1];
    reg [DATA_WIDTH-1:0] portable_pipe[0:READ_LATENCY-1];
    integer portable_stage;
    assign rsp_data=portable_pipe[READ_LATENCY-1];
    always @(posedge clk)begin
        if(write_en)portable_memory[cfg_addr]<=cfg_data;
        if(rst)for(portable_stage=0;portable_stage<READ_LATENCY;portable_stage=portable_stage+1)portable_pipe[portable_stage]<=0;
        else begin
            if(read_en)portable_pipe[0]<=portable_memory[rd_addr];
            for(portable_stage=1;portable_stage<READ_LATENCY;portable_stage=portable_stage+1)portable_pipe[portable_stage]<=portable_pipe[portable_stage-1];
        end
    end
`else
    xpm_memory_spram #(
        .ADDR_WIDTH_A(ADDR_WIDTH),
        .AUTO_SLEEP_TIME(0),.BYTE_WRITE_WIDTH_A(DATA_WIDTH),
        .CASCADE_HEIGHT(1),.ECC_MODE("no_ecc"),
        .MEMORY_INIT_FILE("none"),.MEMORY_INIT_PARAM("0"),
        .MEMORY_OPTIMIZATION("true"),.MEMORY_PRIMITIVE(MEMORY_PRIMITIVE),
        .MEMORY_SIZE(DATA_WIDTH*(2**ADDR_WIDTH)),.MESSAGE_CONTROL(0),
        .READ_DATA_WIDTH_A(DATA_WIDTH),.READ_LATENCY_A(READ_LATENCY),
        .READ_RESET_VALUE_A("0"),.RST_MODE_A("SYNC"),.SIM_ASSERT_CHK(1),
        .USE_MEM_INIT(0),.WAKEUP_TIME("disable_sleep"),
        .WRITE_DATA_WIDTH_A(DATA_WIDTH),.WRITE_MODE_A("no_change")
    ) memory (
        .clka(clk),.rsta(rst),.ena(write_en || read_en),.regcea(1'b1),
        .wea(write_en),.addra(write_en ? cfg_addr : rd_addr),.dina(cfg_data),
        .douta(rsp_data),.sleep(1'b0),.injectsbiterra(1'b0),.injectdbiterra(1'b0),
        .sbiterra(),.dbiterra());
`endif
endmodule
`default_nettype wire
