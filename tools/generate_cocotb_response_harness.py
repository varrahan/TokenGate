"""Passive generated-token response harness with actual cache/fabric."""
import argparse
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];source=(root/'rtl/generated_response_chunk.v').read_text()
    header=re.search(r'module\s+generated_response_chunk\s*#\(.*?\)\s*\((.*?)\);',source,re.S)[1]
    ports=[];direction=width=None
    for declaration in re.sub(r'//[^\n]*','',header).split(','):
        match=re.fullmatch(r'\s*(?:(input|output)\s+(?:wire|reg)\s*(\[[^\]]+\])?\s*)?(\w+)\s*',declaration)
        if not match:raise ValueError(declaration)
        new_direction,new_width,name=match.groups()
        if new_direction is not None:direction,width=new_direction,new_width or''
        ports.append((direction,width,name))
    lines=['`timescale 1ns/1ps','`default_nettype none','module cocotb_generated_response_top;',
           '    localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    for direction,width,name in ports:
        driven=direction=='input'and name not in('mem_rd_ready','mem_rsp_valid','mem_rsp_data','mem_rsp_status')
        lines.append(f"    {'reg'if driven else'wire'} {width} {name}{'=0'if driven else''};")
    inputs={'arready':1,'rdata':64,'rresp':2,'rlast':1,'rvalid':1,'awready':1,'wready':1,'bresp':2,'bvalid':1}
    outputs={'araddr':23,'arlen':8,'arsize':3,'arburst':2,'arvalid':1,'rready':1,'awaddr':23,'awlen':8,'awsize':3,
             'awburst':2,'awvalid':1,'wdata':64,'wstrb':8,'wlast':1,'wvalid':1,'bready':1}
    for name,bits in{**inputs,**outputs}.items():
        lines.append(f"    {'reg'if name in inputs else'wire'} {'['+str(bits-1)+':0]'if bits>1 else''} m_axi_{name}{'=0'if name in inputs else''};")
    lines.extend(['    wire fabric_idle;wire [71:0] normal_data;wire [7:0] normal_status;',
        '    reg [2:0] fault_mode=0;integer fault_target=0,response_index=0;reg fault_arm=0,fault_injected=0;',
        '    wire injecting=fault_mode!=0&&!fault_injected&&response_index==fault_target;',
        "    assign mem_rsp_status=injecting&&fault_mode==1 ? 8'h75:normal_status;",
        "    assign mem_rsp_data=injecting&&fault_mode==2 ? {8'd0,16'd8,32'hfffffff0,14'd0,1'b1,1'b0}:",
        "        injecting&&fault_mode==3 ? normal_data&~72'd2:injecting&&fault_mode==4 ? normal_data|72'd4:",
        "        injecting&&fault_mode==5 ? {8'd0,16'd65535,32'd0,14'd0,1'b1,1'b0}:",
        "        injecting&&fault_mode==6 ? {8'd0,16'd40,32'd70001,14'd0,1'b1,1'b0}:normal_data;",
        '    generated_response_chunk dut(.*);',
        '    external_memory_fabric #(.CLIENTS(1)) fabric(',
        "        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),",
        "        .s_valid(mem_rd_valid),.s_ready(mem_rd_ready),.s_write(1'b0),.s_addr(mem_rd_addr),.s_bytes(mem_rd_bytes),.s_data(72'd0),",
        '        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(normal_data),.rsp_status(normal_status),',
        ',\n'.join([f'        .m_axi_{name}(m_axi_{name})'for name in{**outputs,**inputs}]+['        .idle(fabric_idle)']),
        '    );',
        '    always @(posedge clk)begin',
        '        if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end',
        '        else if(mem_rsp_valid&&mem_rsp_ready)begin',
        '            if(injecting)fault_injected<=1;',
        '            response_index<=response_index+1;',
        '        end',
        '    end','endmodule','`default_nettype wire',''])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text('\n'.join(lines))
    print(f'Generated passive response harness with {len(ports)} public ports and actual cache/fabric')


if __name__=='__main__':main()
