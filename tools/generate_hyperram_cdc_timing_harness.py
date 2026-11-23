"""Registered neighbors in each real clock domain, with reset-owner wiring."""
import hashlib
import json
import re
from pathlib import Path


def ports(source,module):
    match=re.search(r'module\s+'+re.escape(module)+r'\s*(?:#\(.*?\)\s*)?\((.*?)\);',source,re.S)
    assert match,'Missing complete module header'
    header=re.sub(r'//[^\n]*','',match[1]);result=[];direction=None;width=''
    for declaration in header.split(','):
        item=re.fullmatch(r'\s*(?:(input|output)\s+(?:wire|reg)\s*(\[[^\]]+\])?\s*)?(\w+)\s*',declaration)
        assert item, declaration
        if item[1]is not None:direction,width=item[1],item[2]or''
        assert direction
        result.append((direction,width,item[3]))
    assert len({n for _,_,n in result})==len(result)
    return result


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'rtl/hyperram_clock_bridge.v';interface=ports(source.read_text(),'hyperram_clock_bridge')
    lines=['`timescale 1ns/1ps','`default_nettype none','// Timing neighbors only; no package/board timing claim.',
        'module hyperram_clock_bridge_timing_harness(']
    for i,(d,w,n)in enumerate(interface):
        kind='wire'if d=='input'or n in('app_reset','mem_reset')else'reg'
        lines.append(f'    {d} {kind} {w} {n}{","if i+1<len(interface)else""}')
    lines +=[');','wire app_buffered,mem_buffered;',
        'BUFG app_buffer(.I(app_clk),.O(app_buffered));','BUFG mem_buffer(.I(mem_clk),.O(mem_buffered));']
    for d,w,n in interface:
        if n not in('app_clk','mem_clk','app_reset','mem_reset'):
            lines.append(f'{"reg"if d=="input"else"wire"} {w} timing_{n};')
    for domain in ('app','mem'):
        selected=[]
        for d,w,n in interface:
            if n in('app_clk','mem_clk','app_reset','mem_reset','fifo_errors'):continue
            actual='app'if n=='reset_request'or n.startswith('s_')else'mem'
            if actual==domain:selected.append((d,n))
        lines.append(f'always @(posedge {domain}_buffered)begin')
        for d,n in selected:
            if n not in('s_cmd_valid','s_rsp_ready','m_cmd_ready','m_rsp_valid'):
                lines.append(f'    '+(f'timing_{n}<={n};'if d=='input'else f'{n}<=timing_{n};'))
        for bit in ((0,3)if domain=='app'else(1,2)):lines.append(f'    fifo_errors[{bit}]<=timing_fifo_errors[{bit}];')
        lines.append('end')
        owner=[n for d,n in selected if n in('s_cmd_valid','s_rsp_ready','m_cmd_ready','m_rsp_valid')]
        lines +=[f'always @(posedge {domain}_buffered or posedge {domain}_reset)begin',f'    if({domain}_reset)begin']
        lines +=[f'        timing_{n}<=0;'for n in owner]
        lines +=['    end else begin']+[f'        timing_{n}<={n};'for n in owner]+['    end','end']
    mapping={'app_clk':'app_buffered','mem_clk':'mem_buffered','app_reset':'app_reset','mem_reset':'mem_reset'}
    lines +=['hyperram_clock_bridge core(',
        ',\n'.join(f'    .{n}({mapping.get(n,"timing_"+n)})'for _,_,n in interface),');','endmodule','`default_nettype wire','']
    folder=root/'build/hyperram-cdc';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'timing_harness.v';output.write_text('\n'.join(lines))
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),output_sha256=sha(output),
        standalone_port_parser=True,
        clock_periods_ns=dict(app=4,mem=5),metadata_crossing_waivers_added=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
