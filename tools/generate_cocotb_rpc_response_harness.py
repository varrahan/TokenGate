"""Passive RPC return fixture: actual directory and four-client shared fabric."""
import argparse
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    header=re.search(r'module\s+rpc_generated_response\s*#\(.*?\)\s*\((.*?)\);',(root/'rtl/rpc_generated_response.v').read_text(),re.S)[1]
    ports=[];direction=width=None
    for declaration in re.sub(r'//[^\n]*','',header).split(','):
        match=re.fullmatch(r'\s*(?:(input|output)\s+(?:wire|reg)\s*(\[[^\]]+\])?\s*)?(\w+)\s*',declaration)
        if not match:raise ValueError(declaration)
        new_direction,new_width,name=match.groups()
        if new_direction is not None:direction,width=new_direction,new_width or ''
        ports.append((direction,width,name))
    lines=['`timescale 1ns/1ps','`default_nettype none','module cocotb_rpc_response_top;',
           'localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    for direction,width,name in ports:
        driven=direction=='input'and not name.startswith('directory_')and name not in('mem_ready','mem_rsp_valid','mem_rsp_data','mem_rsp_status')
        lines.append(f"{'reg' if driven else 'wire'} {width} {name}{'=0' if driven else ''};")
    inputs={'arready':1,'rdata':64,'rresp':2,'rlast':1,'rvalid':1,'awready':1,'wready':1,'bresp':2,'bvalid':1}
    outputs={'araddr':23,'arlen':8,'arsize':3,'arburst':2,'arvalid':1,'rready':1,'awaddr':23,'awlen':8,'awsize':3,
             'awburst':2,'awvalid':1,'wdata':64,'wstrb':8,'wlast':1,'wvalid':1,'bready':1}
    for name,bits in {**inputs,**outputs}.items():
        lines.append(f"{'reg' if name in inputs else 'wire'} {'['+str(bits-1)+':0]' if bits>1 else ''} m_axi_{name}{'=0' if name in inputs else ''};")
    lines.extend('''
reg host_valid=0;wire host_ready;reg [2:0] host_op=0;
reg [22:0] host_pool_base=0,host_address=0,host_buffer_base=0;
reg [23:0] host_pool_bytes=0,host_buffer_bytes=0;
reg [15:0] host_user=0,host_application=0;reg [30:0] host_stream=0;
reg [31:0] host_generation=0,host_message_limit=0;
reg host_protobuf=0,host_encoding=0,host_maintenance=0;
wire host_result_valid;reg host_result_ready=0;wire [7:0] host_status;
wire [22:0] host_result_address;wire store_recovery,store_idle;
reg host_selected=0;
wire store_ready,store_valid;wire [7:0] store_status,store_memory;
wire [22:0] store_address;wire [15:0] store_application;wire [31:0] store_generation;
wire store_protobuf,store_encoding;
wire [3:0] all_valid,all_ready,all_write,all_rsp_valid,all_rsp_ready;
wire [91:0] all_addr;wire [15:0] all_bytes;wire [287:0] all_data,normal_rsp_data;
wire [31:0] normal_rsp_status;
wire [287:0] fault_rsp_data=normal_rsp_data;
reg fault_arm=0,fault_enable=0;reg [1:0] fault_client=0;
integer fault_target=0,response_index=0;reg fault_injected=0;
wire injecting=fault_enable&&!fault_injected&&response_index==fault_target;
wire [31:0] fault_rsp_status=injecting?
    (normal_rsp_status&~(32'hff<<(fault_client*8)))|(32'h75<<(fault_client*8)):normal_rsp_status;
reg program_valid=0,program_write=0;wire program_ready;
reg [22:0] program_address=0;reg [3:0] program_bytes=8;reg [71:0] program_data=0;
wire program_result_valid;reg program_result_ready=0;wire [71:0] program_result_data;wire [7:0] program_status;
wire fabric_idle;
rpc_generated_response dut(.*);
assign all_valid[1:0]=mem_valid;assign mem_ready=all_ready[1:0];assign all_write[1:0]=mem_write;
assign all_addr[45:0]=mem_addr;assign all_bytes[7:0]=mem_bytes;assign all_data[143:0]=mem_data;
assign mem_rsp_valid=all_rsp_valid[1:0];assign all_rsp_ready[1:0]=mem_rsp_ready;
assign mem_rsp_data=fault_rsp_data[143:0];assign mem_rsp_status=fault_rsp_status[15:0];
assign directory_ready=store_ready;
assign directory_result_valid=store_valid&&!host_selected;
assign directory_status=store_status;assign directory_memory_status=store_memory;
assign directory_address=store_address;assign directory_application=store_application;
assign directory_generation=store_generation;assign directory_protobuf=store_protobuf;
assign directory_unsupported_encoding=store_encoding;
assign host_ready=store_ready&&!directory_valid&&idle;
assign host_result_valid=store_valid&&host_selected;assign host_status=store_status;
assign host_result_address=store_address;
grpc_stream_store registry(
    .clk(clk),.rst(rst),.req_valid(directory_valid||host_valid&&idle),.req_ready(store_ready),
    .req_op(directory_valid?3'd1:host_op),
    .cfg_pool_base(directory_valid?directory_pool_base:host_pool_base),.cfg_pool_bytes(directory_valid?directory_pool_bytes:host_pool_bytes),
    .req_user(directory_valid?directory_user:host_user),.req_application(host_application),
    .req_stream(directory_valid?directory_stream:host_stream),.req_generation(host_generation),
    .req_address(host_address),.req_buffer_base(host_buffer_base),.req_buffer_bytes(host_buffer_bytes),
    .req_message_limit(host_message_limit),.req_protobuf(host_protobuf),.req_unsupported_encoding(host_encoding),.req_maintenance(host_maintenance),.req_state(256'd0),
    .rsp_valid(store_valid),.rsp_ready(host_selected?host_result_ready:directory_result_ready),
    .rsp_status(store_status),.rsp_detail(),.rsp_memory_status(store_memory),.rsp_op(),.rsp_address(store_address),
    .rsp_buffer_base(),.rsp_buffer_bytes(),.rsp_user(),.rsp_application(store_application),.rsp_stream(),
    .rsp_generation(store_generation),.rsp_message_limit(),.rsp_protobuf(store_protobuf),.rsp_unsupported_encoding(store_encoding),.rsp_state(),
    .recovery_required(store_recovery),.recovery_address(),.idle(store_idle),
    .mem_valid(all_valid[2]),.mem_ready(all_ready[2]),.mem_write(all_write[2]),.mem_addr(all_addr[46+:23]),.mem_bytes(all_bytes[8+:4]),.mem_data(all_data[144+:72]),
    .mem_rsp_valid(all_rsp_valid[2]),.mem_rsp_ready(all_rsp_ready[2]),.mem_rsp_data(fault_rsp_data[144+:72]),.mem_rsp_status(fault_rsp_status[16+:8]));
assign all_valid[3]=program_valid;assign program_ready=all_ready[3];assign all_write[3]=program_write;
assign all_addr[69+:23]=program_address;assign all_bytes[12+:4]=program_bytes;assign all_data[216+:72]=program_data;
assign program_result_valid=all_rsp_valid[3];assign all_rsp_ready[3]=program_result_ready;
assign program_result_data=fault_rsp_data[216+:72];assign program_status=fault_rsp_status[24+:8];
external_memory_fabric #(.CLIENTS(4)) fabric(
    .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),
    .s_valid(all_valid),.s_ready(all_ready),.s_write(all_write),.s_addr(all_addr),.s_bytes(all_bytes),.s_data(all_data),
    .rsp_valid(all_rsp_valid),.rsp_ready(all_rsp_ready),.rsp_data(normal_rsp_data),.rsp_status(normal_rsp_status),
'''.strip().splitlines())
    lines.append(',\n'.join([f'.m_axi_{name}(m_axi_{name})'for name in {**outputs,**inputs}]+['.idle(fabric_idle)'])+');')
    lines.extend('''
always @(posedge clk)begin
    if(rst)host_selected<=0;
    else if((directory_valid||host_valid&&idle)&&store_ready)host_selected<=!directory_valid;
    if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end
    else if(all_rsp_valid[fault_client]&&all_rsp_ready[fault_client])begin
        if(injecting)fault_injected<=1;
        response_index<=response_index+1;
    end
end
endmodule
`default_nettype wire
'''.strip().splitlines())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text('\n'.join(lines)+'\n')
    print(f'Generated RPC response harness: {len(ports)} ports, real directory, four fabric clients')


if __name__=='__main__':main()
