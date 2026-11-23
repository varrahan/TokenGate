"""Expose the real raw-prefill top and shared fabric to Python-owned BFMs."""
import argparse
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    source=(root/'rtl/http2_grpc_prefill.v').read_text()
    match=re.search(r'module\s+http2_grpc_prefill\s*#\((.*?)\)\s*\((.*?)\);',source,re.S)
    if not match:raise ValueError('Cannot identify complete prefill interface')
    header=re.sub(r'//[^\n]*','',match[2]);ports=[];direction=width=None
    for declaration in header.split(','):
        port=re.fullmatch(r'\s*(?:(input|output)\s+(?:wire|reg)\s*(\[[^\]]+\])?\s*)?(\w+)\s*',declaration)
        if not port:raise ValueError(f'Unsupported declaration: {declaration}')
        new_direction,new_width,name=port.groups()
        if new_direction is not None:direction,width=new_direction,new_width or ''
        if direction is None:raise ValueError('Missing direction')
        ports.append((direction,width,name))
    if len({p[2]for p in ports})!=len(ports):raise ValueError('Duplicate port')
    lines=['`timescale 1ns/1ps','`default_nettype none',
           '// No HDL stimulus or scoreboard: cocotb owns the clock and all host traffic.',
           'module cocotb_http2_prefill_top;',
           '    localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    fabric_driven={'mem_ready','mem_rsp_valid','mem_rsp_data','mem_rsp_status'}
    for direction,width,name in ports:
        python_driven=direction=='input'and name not in fabric_driven
        lines.append(f"    {'reg'if python_driven else'wire'} {width} {name}{'=0'if python_driven else''};")
    lines.extend(['    wire fabric_idle;',
                  '    wire [159:0] fabric_status;',
                  '    integer fault_client=-1,fault_target=-1,response_index=0;',
                  '    reg fault_arm=0,fault_injected=0;',
                  '    http2_grpc_prefill #(.MAX_TEXT_BYTES(16384),.MAX_FIELD_BYTES(16384)) dut(.*);'])
    inputs={'arready':1,'rdata':64,'rresp':2,'rlast':1,'rvalid':1,'awready':1,'wready':1,'bresp':2,'bvalid':1}
    outputs={'araddr':23,'arlen':8,'arsize':3,'arburst':2,'arvalid':1,'rready':1,
             'awaddr':23,'awlen':8,'awsize':3,'awburst':2,'awvalid':1,'wdata':64,'wstrb':8,'wlast':1,'wvalid':1,'bready':1}
    for name,bits in {**inputs,**outputs}.items():
        width=f'[{bits-1}:0]'if bits>1 else''
        lines.append(f"    {'reg'if name in inputs else'wire'} {width} m_axi_{name}{'=0'if name in inputs else''};")
    lines.extend(['    external_memory_fabric #(.CLIENTS(20)) fabric(',
        "        .clk(clk),.rst(rst),.invalidate_valid(1'b0),.invalidate_ready(),",
        '        .s_valid(mem_valid),.s_ready(mem_ready),.s_write(mem_write),.s_addr(mem_addr),.s_bytes(mem_bytes),.s_data(mem_data),',
        '        .rsp_valid(mem_rsp_valid),.rsp_ready(mem_rsp_ready),.rsp_data(mem_rsp_data),.rsp_status(fabric_status),',
        ',\n'.join([f'        .m_axi_{name}(m_axi_{name})'for name in {**outputs,**inputs}]+['        .idle(fabric_idle)']),
        '    );',
        '    generate for(genvar client=0;client<20;client=client+1)begin: fault_ports',
        "        assign mem_rsp_status[client*8+:8]=(fault_client==client&&!fault_injected&&response_index==fault_target)?8'h75:fabric_status[client*8+:8];",
        '    end endgenerate',
        '    always @(posedge clk)begin',
        '        if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end',
        '        else if(fault_client>=0&&fault_client<20&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin',
        "            if(!fault_injected&&response_index==fault_target)fault_injected<=1;",
        '            response_index<=response_index+1;',
        '        end',
        '    end','endmodule','`default_nettype wire',''])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text('\n'.join(lines))
    print(f'Generated cocotb raw-prefill harness: {len(ports)} public ports, actual twenty-client fabric')


if __name__=='__main__':main()
