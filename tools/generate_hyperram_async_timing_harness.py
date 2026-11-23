"""Place registered timing neighbors in the assembly's actual clock domains."""
import hashlib
import json
from pathlib import Path
from generate_hyperram_cdc_timing_harness import ports


def main():
    root = Path(__file__).resolve().parents[1]
    source = root/'rtl/axi_hyperram_async_controller.v'
    interface = ports(source.read_text(), 'axi_hyperram_async_controller')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    clocks = ('app_clk', 'mem_clk'); resets = ('app_reset', 'mem_reset')
    def domain(name):
        return 'mem' if name.startswith('phy_') or name.endswith('_mem') else 'app'
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
             '// Registered neighbors only; no package timing or physical PHY.',
             'module axi_hyperram_async_controller_timing_harness(']
    for i, (direction, width, name) in enumerate(interface):
        kind = 'wire' if direction == 'input' or name in resets else 'reg'
        lines.append(f'    {direction} {kind} {width} {name}'+(',' if i+1<len(interface) else ''))
    lines += [');', 'wire app_buffered,mem_buffered;',
              'BUFG app_buffer(.I(app_clk),.O(app_buffered));',
              'BUFG mem_buffer(.I(mem_clk),.O(mem_buffered));']
    for direction, width, name in interface:
        if name not in clocks+resets:
            lines.append(f'{"reg" if direction=="input" else "wire"} {width} timing_{name};')
    owner_inputs = ('s_axi_arvalid','s_axi_awvalid','s_axi_wvalid','s_axi_rready','s_axi_bready',
                    'reload_ack_valid','reload_done_ready')
    for clock in ('app','mem'):
        lines.append(f'always @(posedge {clock}_buffered)begin')
        for direction, width, name in interface:
            if name in clocks+resets+owner_inputs+('fifo_errors',) or domain(name)!=clock:
                continue
            lines.append('    '+(f'timing_{name}<={name};' if direction=='input' else f'{name}<=timing_{name};'))
        for bit in ((0,3) if clock=='app' else (1,2)):
            lines.append(f'    fifo_errors[{bit}]<=timing_fifo_errors[{bit}];')
        lines.append('end')
    lines += ['always @(posedge app_buffered or posedge app_reset)begin', '    if(app_reset)begin']
    lines += [f'        timing_{name}<=0;' for name in owner_inputs]
    lines += ['    end else begin']+[f'        timing_{name}<={name};' for name in owner_inputs]+['    end','end']
    mapping = dict(app_clk='app_buffered',mem_clk='mem_buffered',app_reset='app_reset',mem_reset='mem_reset')
    lines += ['axi_hyperram_async_controller core(',
              ',\n'.join(f'    .{name}({mapping.get(name,"timing_"+name)})' for _,_,name in interface),
              ');','endmodule','`default_nettype wire','']
    folder = root/'build/hyperram-async'; folder.mkdir(parents=True,exist_ok=True)
    output = folder/'timing_harness.v'; output.write_text('\n'.join(lines))
    manifest = dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),output_sha256=sha(output),
                    port_parser_sha256=sha(root/'tools/generate_hyperram_cdc_timing_harness.py'),
                    app_clock_period_ns=4,mem_clock_period_ns=5,package_timing_verified=False,
                    domain_map={name:domain(name) for _,_,name in interface if name not in clocks+resets+('fifo_errors',)},
                    fifo_error_bit_domains={'app':[0,3],'mem':[1,2]},full_system_complete=False)
    (folder/'timing-harness-generation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))


if __name__=='__main__':
    main()
