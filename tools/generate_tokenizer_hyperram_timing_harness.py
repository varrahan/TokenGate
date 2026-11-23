"""Registered neighbors around the actual integrated Tokenizer and controller."""
import argparse
import hashlib
import json
from pathlib import Path
from generate_hyperram_cdc_timing_harness import ports


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--simulation',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'build/validation'/args.simulation/'sources/rtl/tokenizer_hyperram_subsystem.v'
    interface=ports(source.read_text(),'tokenizer_hyperram_subsystem')
    clocks=('app_clk','mem_clk');resets=('app_reset','mem_reset','application_reset')
    def domain(name):return 'mem'if name.startswith('phy_')or name.endswith('_mem')else'app'
    def owner(name):return name.endswith(('valid','ready'))or name=='link_f_bpe_admit_sequences'
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Neighbors preserve real clock domains; external package paths are excluded.',
        'module tokenizer_hyperram_timing_harness(']
    for i,(direction,width,name)in enumerate(interface):
        width=width.replace('USER_WIDTH','16')
        lines.append(f'    {direction} '+('wire'if direction=='input'or name in resets else'reg')+f' {width} {name}'+(','if i+1<len(interface)else''))
    lines += [');','wire app_buffered,mem_buffered;',
        'BUFG app_buffer(.I(app_clk),.O(app_buffered));','BUFG mem_buffer(.I(mem_clk),.O(mem_buffered));']
    for direction,width,name in interface:
        if name not in clocks+resets:
            lines.append(('reg'if direction=='input'else'wire')+f' {width.replace("USER_WIDTH","16")} timing_{name};')
    for clock in('app','mem'):
        selected=[(d,n)for d,_,n in interface if n not in clocks+resets+('fifo_errors',)and domain(n)==clock]
        lines.append(f'always @(posedge {clock}_buffered)begin')
        for direction,name in selected:
            if direction=='input'and owner(name):continue
            lines.append('    '+(f'timing_{name}<={name};'if direction=='input'else f'{name}<=timing_{name};'))
        for bit in((0,3)if clock=='app'else(1,2)):lines.append(f'    fifo_errors[{bit}]<=timing_fifo_errors[{bit}];')
        lines.append('end')
        owned=[name for direction,name in selected if direction=='input'and owner(name)]
        if owned:
            lines += [f'always @(posedge {clock}_buffered or posedge {clock}_reset)begin',f'    if({clock}_reset)begin']
            lines += [f'        timing_{name}<=0;'for name in owned]
            lines += ['    end else begin']+[f'        timing_{name}<={name};'for name in owned]+['    end','end']
    mapping=dict(app_clk='app_buffered',mem_clk='mem_buffered',app_reset='app_reset',mem_reset='mem_reset',application_reset='application_reset')
    lines += ['tokenizer_hyperram_subsystem core(',
        ',\n'.join(f'    .{name}({mapping.get(name,"timing_"+name)})'for _,_,name in interface),');','endmodule','`default_nettype wire','']
    folder=root/'build/tokenizer-hyperram';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'timing_harness.v';target.write_text('\n'.join(lines))
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),output_sha256=sha(target),
        simulation=args.simulation,domain_map={name:domain(name)for _,_,name in interface if name not in clocks+resets+('fifo_errors',)},
        owner_input_registers=[name for d,_,name in interface if d=='input'and owner(name)],
        fifo_error_bit_domains={'app':[0,3],'mem':[1,2]},clock_periods_ns=dict(app=4,mem=5),package_timing_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(ports=len(interface),output_sha256=result['output_sha256'])))


if __name__=='__main__':main()
