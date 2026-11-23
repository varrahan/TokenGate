`timescale 1ns/1ps
`default_nettype none
module cocotb_generated_response_top;
    localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;
    reg  clk=0;
    reg  rst=0;
    reg [31:0] s_axis_tokens_tdata=0;
    reg [3:0] s_axis_tokens_tkeep=0;
    reg  s_axis_tokens_tvalid=0;
    wire  s_axis_tokens_tready;
    reg  s_axis_tokens_tlast=0;
    reg [USER_WIDTH-1:0] s_axis_tokens_tuser=0;
    reg  lease_valid=0;
    reg [USER_WIDTH-1:0] lease_user=0;
    reg [USER_WIDTH-1:0] lease_application=0;
    reg [30:0] lease_stream=0;
    reg [31:0] lease_generation=0;
    reg [31:0] lease_model_epoch=0;
    reg [31:0] lease_schema_epoch=0;
    reg [31:0] cfg_active_model_epoch=0;
    reg [MEMORY_ADDR_WIDTH-1:0] cfg_directory_base=0;
    reg [MEMORY_ADDR_WIDTH-1:0] cfg_pool_base=0;
    reg [MEMORY_ADDR_WIDTH:0] cfg_directory_bytes=0;
    reg [MEMORY_ADDR_WIDTH:0] cfg_pool_bytes=0;
    reg  cfg_strip_special=0;
    reg  cfg_replace_invalid=0;
    reg [1:0] cfg_format=0;
    reg [28:0] cfg_protobuf_field=0;
    reg [23:0] carry_in=0;
    reg [1:0] carry_in_count=0;
    wire [511:0] m_axis_tx_tdata;
    wire [63:0] m_axis_tx_tkeep;
    wire  m_axis_tx_tvalid;
    reg  m_axis_tx_tready=0;
    wire  m_axis_tx_tlast;
    wire [USER_WIDTH-1:0] m_axis_tx_tuser;
    wire  result_valid;
    reg  result_ready=0;
    wire [7:0] result_stage;
    wire [7:0] result_status;
    wire [7:0] result_memory_status;
    wire [23:0] carry_out;
    wire [1:0] carry_out_count;
    wire [31:0] result_bytes;
    wire [USER_WIDTH-1:0] result_user;
    wire [USER_WIDTH-1:0] result_application;
    wire [30:0] result_stream;
    wire [31:0] result_generation;
    wire [31:0] result_model_epoch;
    wire [31:0] result_schema_epoch;
    wire  result_eos;
    wire  mem_rd_valid;
    wire  mem_rd_ready;
    wire [MEMORY_ADDR_WIDTH-1:0] mem_rd_addr;
    wire [3:0] mem_rd_bytes;
    wire  mem_rsp_valid;
    wire  mem_rsp_ready;
    wire [71:0] mem_rsp_data;
    wire [7:0] mem_rsp_status;
    wire  idle;
    reg  m_axi_arready=0;
    reg [63:0] m_axi_rdata=0;
    reg [1:0] m_axi_rresp=0;
    reg  m_axi_rlast=0;
    reg  m_axi_rvalid=0;
    reg  m_axi_awready=0;
    reg  m_axi_wready=0;
    reg [1:0] m_axi_bresp=0;
    reg  m_axi_bvalid=0;
    wire [22:0] m_axi_araddr;
    wire [7:0] m_axi_arlen;
    wire [2:0] m_axi_arsize;
    wire [1:0] m_axi_arburst;
    wire  m_axi_arvalid;
    wire  m_axi_rready;
    wire [22:0] m_axi_awaddr;
    wire [7:0] m_axi_awlen;
    wire [2:0] m_axi_awsize;
    wire [1:0] m_axi_awburst;
    wire  m_axi_awvalid;
    wire [63:0] m_axi_wdata;
    wire [7:0] m_axi_wstrb;
    wire  m_axi_wlast;
    wire  m_axi_wvalid;
    wire  m_axi_bready;
    wire fabric_idle;wire [71:0] normal_data;wire [7:0] normal_status;
    reg [2:0] fault_mode=0;integer fault_target=0,response_index=0;reg fault_arm=0,fault_injected=0;
    wire injecting=fault_mode!=0&&!fault_injected&&response_index==fault_target;
    assign mem_rsp_status=injecting&&fault_mode==1 ? 8'h75:normal_status;
    assign mem_rsp_data=injecting&&fault_mode==2 ? {8'd0,16'd8,32'hfffffff0,14'd0,1'b1,1'b0}:
        injecting&&fault_mode==3 ? normal_data&~72'd2:injecting&&fault_mode==4 ? normal_data|72'd4:
        injecting&&fault_mode==5 ? {8'd0,16'd65535,32'd0,14'd0,1'b1,1'b0}:
        injecting&&fault_mode==6 ? {8'd0,16'd40,32'd70001,14'd0,1'b1,1'b0}:normal_data;
    generated_response_chunk dut(.*);
    external_memory_fabric #(.CLIENTS(1)) fabric(
        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),
        .s_valid(mem_rd_valid),.s_ready(mem_rd_ready),.s_write(1'b0),.s_addr(mem_rd_addr),.s_bytes(mem_rd_bytes),.s_data(72'd0),
        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(normal_data),.rsp_status(normal_status),
        .m_axi_araddr(m_axi_araddr),
        .m_axi_arlen(m_axi_arlen),
        .m_axi_arsize(m_axi_arsize),
        .m_axi_arburst(m_axi_arburst),
        .m_axi_arvalid(m_axi_arvalid),
        .m_axi_rready(m_axi_rready),
        .m_axi_awaddr(m_axi_awaddr),
        .m_axi_awlen(m_axi_awlen),
        .m_axi_awsize(m_axi_awsize),
        .m_axi_awburst(m_axi_awburst),
        .m_axi_awvalid(m_axi_awvalid),
        .m_axi_wdata(m_axi_wdata),
        .m_axi_wstrb(m_axi_wstrb),
        .m_axi_wlast(m_axi_wlast),
        .m_axi_wvalid(m_axi_wvalid),
        .m_axi_bready(m_axi_bready),
        .m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),
        .m_axi_rresp(m_axi_rresp),
        .m_axi_rlast(m_axi_rlast),
        .m_axi_rvalid(m_axi_rvalid),
        .m_axi_awready(m_axi_awready),
        .m_axi_wready(m_axi_wready),
        .m_axi_bresp(m_axi_bresp),
        .m_axi_bvalid(m_axi_bvalid),
        .idle(fabric_idle)
    );
    always @(posedge clk)begin
        if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end
        else if(mem_rsp_valid&&mem_rsp_ready)begin
            if(injecting)fault_injected<=1;
            response_index<=response_index+1;
        end
    end
endmodule
`default_nettype wire
