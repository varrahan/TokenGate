`timescale 1ns/1ps
`default_nettype none
// Host-programmable bidirectional tokenizer. The external PCIe bridge supplies
// AXI-Lite and streams; a board-specific controller terminates the AXI master.
module scu35_tokenizer_mmio_subsystem #(
    parameter integer USER_WIDTH=16,parameter integer MEMORY_ADDR_WIDTH=23,parameter integer CACHE_LOG_LINES=6
)(
    input wire clk,input wire rst,
    input wire [15:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,input wire s_axi_wvalid,output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,output wire s_axi_bvalid,input wire s_axi_bready,
    input wire [15:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire [1:0] s_axi_rresp,output wire s_axi_rvalid,input wire s_axi_rready,
    input wire [127:0] s_axis_text_tdata,input wire [15:0] s_axis_text_tkeep,
    input wire s_axis_text_tvalid,output wire s_axis_text_tready,input wire s_axis_text_tlast,input wire [USER_WIDTH-1:0] s_axis_text_tuser,
    output wire [511:0] m_axis_tokens_tdata,output wire [63:0] m_axis_tokens_tkeep,
    output wire m_axis_tokens_tvalid,input wire m_axis_tokens_tready,output wire m_axis_tokens_tlast,output wire [USER_WIDTH-1:0] m_axis_tokens_tuser,
    output wire completion_valid,input wire completion_ready,output wire completion_failed,output wire [31:0] completion_count,output wire [USER_WIDTH-1:0] completion_user,
    output wire forward_error_valid,input wire forward_error_ready,output wire [7:0] forward_error_stage,forward_error_detail,forward_error_status,output wire [USER_WIDTH-1:0] forward_error_user,
    input wire [31:0] s_axis_generated_tdata,input wire s_axis_generated_tvalid,output wire s_axis_generated_tready,input wire s_axis_generated_tlast,input wire [USER_WIDTH-1:0] s_axis_generated_tuser,
    output wire [127:0] m_axis_text_tdata,output wire [15:0] m_axis_text_tkeep,
    output wire m_axis_text_tvalid,input wire m_axis_text_tready,output wire m_axis_text_tlast,output wire [USER_WIDTH-1:0] m_axis_text_tuser,
    output wire reverse_error_valid,input wire reverse_error_ready,output wire [7:0] reverse_error_code,output wire [USER_WIDTH-1:0] reverse_error_user,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_araddr,output wire [7:0] m_axi_arlen,output wire [2:0] m_axi_arsize,output wire [1:0] m_axi_arburst,output wire m_axi_arvalid,input wire m_axi_arready,
    input wire [63:0] m_axi_rdata,input wire [1:0] m_axi_rresp,input wire m_axi_rlast,input wire m_axi_rvalid,output wire m_axi_rready,
    output wire [MEMORY_ADDR_WIDTH-1:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,output wire m_axi_awvalid,input wire m_axi_awready,
    output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
    input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready,
    output wire idle
);
    wire update_req,commit,abort_update,tables_valid,cfg_unlock,vocabulary_valid,protocol_error,draining;
    wire [31:0] epoch;
    wire cfg_valid,cfg_ready,cfg_rsp_valid,cfg_rsp_ready,cfg_invalidate_valid,cfg_invalidate_ready;
    wire [MEMORY_ADDR_WIDTH-1:0] cfg_addr;wire [3:0] cfg_bytes;wire [71:0] cfg_data;wire [7:0] cfg_rsp_status;
    wire [1:0] cfg_profile;
    wire [MEMORY_ADDR_WIDTH-1:0] cfg_class_base,cfg_hash_base,cfg_node_base,cfg_edge_base;
    wire [31:0] cfg_node_count,cfg_edge_count;
    wire [MEMORY_ADDR_WIDTH-1:0] cfg_work_floor,cfg_scalar_base,cfg_merge_base,cfg_commit_base,directory_base,pool_base;
    wire [MEMORY_ADDR_WIDTH:0] cfg_scalar_bytes,cfg_merge_bytes,cfg_commit_bytes;wire strip_special_tokens;
    tokenizer_mmio #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) registers(
        .clk(clk),.rst(rst),.s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),.s_axi_bresp(s_axi_bresp),.s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),.s_axi_rdata(s_axi_rdata),.s_axi_rresp(s_axi_rresp),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),
        .update_req(update_req),.commit(commit),.abort_update(abort_update),.tables_valid(tables_valid),.cfg_unlock(cfg_unlock),.epoch(epoch),.vocabulary_valid(vocabulary_valid),.protocol_error(protocol_error),.draining(draining),.datapath_idle(idle),
        .cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_bytes(cfg_bytes),.cfg_data(cfg_data),.cfg_rsp_valid(cfg_rsp_valid),.cfg_rsp_ready(cfg_rsp_ready),.cfg_rsp_status(cfg_rsp_status),.cfg_invalidate_valid(cfg_invalidate_valid),.cfg_invalidate_ready(cfg_invalidate_ready),
        .cfg_profile(cfg_profile),.cfg_class_base(cfg_class_base),.cfg_hash_base(cfg_hash_base),.cfg_node_base(cfg_node_base),.cfg_edge_base(cfg_edge_base),.cfg_node_count(cfg_node_count),.cfg_edge_count(cfg_edge_count),
        .cfg_work_floor(cfg_work_floor),.cfg_scalar_base(cfg_scalar_base),.cfg_scalar_bytes(cfg_scalar_bytes),.cfg_merge_base(cfg_merge_base),.cfg_merge_bytes(cfg_merge_bytes),.cfg_commit_base(cfg_commit_base),.cfg_commit_bytes(cfg_commit_bytes),.directory_base(directory_base),.pool_base(pool_base),.strip_special_tokens(strip_special_tokens));
    scu35_tokenizer_subsystem #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.CACHE_LOG_LINES(CACHE_LOG_LINES)) tokenizer(
        .clk(clk),.rst(rst),.update_req(update_req),.commit(commit),.abort_update(abort_update),.tables_valid(tables_valid),.cfg_unlock(cfg_unlock),.epoch(epoch),.vocabulary_valid(vocabulary_valid),.protocol_error(protocol_error),.draining(draining),
        .cfg_valid(cfg_valid),.cfg_ready(cfg_ready),.cfg_addr(cfg_addr),.cfg_bytes(cfg_bytes),.cfg_data(cfg_data),.cfg_rsp_valid(cfg_rsp_valid),.cfg_rsp_ready(cfg_rsp_ready),.cfg_rsp_status(cfg_rsp_status),.cfg_invalidate_valid(cfg_invalidate_valid),.cfg_invalidate_ready(cfg_invalidate_ready),
        .cfg_profile(cfg_profile),.cfg_class_base(cfg_class_base),.cfg_hash_base(cfg_hash_base),.cfg_node_base(cfg_node_base),.cfg_edge_base(cfg_edge_base),.cfg_node_count(cfg_node_count),.cfg_edge_count(cfg_edge_count),
        .cfg_work_floor(cfg_work_floor),.cfg_scalar_base(cfg_scalar_base),.cfg_scalar_bytes(cfg_scalar_bytes),.cfg_merge_base(cfg_merge_base),.cfg_merge_bytes(cfg_merge_bytes),.cfg_commit_base(cfg_commit_base),.cfg_commit_bytes(cfg_commit_bytes),.directory_base(directory_base),.pool_base(pool_base),.strip_special_tokens(strip_special_tokens),
        .s_axis_text_tdata(s_axis_text_tdata),.s_axis_text_tkeep(s_axis_text_tkeep),.s_axis_text_tvalid(s_axis_text_tvalid),.s_axis_text_tready(s_axis_text_tready),.s_axis_text_tlast(s_axis_text_tlast),.s_axis_text_tuser(s_axis_text_tuser),
        .m_axis_tokens_tdata(m_axis_tokens_tdata),.m_axis_tokens_tkeep(m_axis_tokens_tkeep),.m_axis_tokens_tvalid(m_axis_tokens_tvalid),.m_axis_tokens_tready(m_axis_tokens_tready),.m_axis_tokens_tlast(m_axis_tokens_tlast),.m_axis_tokens_tuser(m_axis_tokens_tuser),
        .completion_valid(completion_valid),.completion_ready(completion_ready),.completion_failed(completion_failed),.completion_count(completion_count),.completion_user(completion_user),
        .forward_error_valid(forward_error_valid),.forward_error_ready(forward_error_ready),.forward_error_stage(forward_error_stage),.forward_error_detail(forward_error_detail),.forward_error_status(forward_error_status),.forward_error_user(forward_error_user),
        .s_axis_generated_tdata(s_axis_generated_tdata),.s_axis_generated_tvalid(s_axis_generated_tvalid),.s_axis_generated_tready(s_axis_generated_tready),.s_axis_generated_tlast(s_axis_generated_tlast),.s_axis_generated_tuser(s_axis_generated_tuser),
        .m_axis_text_tdata(m_axis_text_tdata),.m_axis_text_tkeep(m_axis_text_tkeep),.m_axis_text_tvalid(m_axis_text_tvalid),.m_axis_text_tready(m_axis_text_tready),.m_axis_text_tlast(m_axis_text_tlast),.m_axis_text_tuser(m_axis_text_tuser),
        .reverse_error_valid(reverse_error_valid),.reverse_error_ready(reverse_error_ready),.reverse_error_code(reverse_error_code),.reverse_error_user(reverse_error_user),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),.m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),.m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),
        .m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),.m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),.m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),.m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready),.idle(idle));
endmodule
`default_nettype wire
