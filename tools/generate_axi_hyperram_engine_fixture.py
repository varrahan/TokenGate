"""Wire the real AXI frontend to the real word sequencer for protocol tests."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    paths=[root/'rtl/axi_hyperram_bridge.v',root/'rtl/hyperram_transaction_engine.v']
    fp=ports(paths[0].read_text(),'axi_hyperram_bridge');ep=ports(paths[1].read_text(),'hyperram_transaction_engine')
    public=[(d,w.replace('ADDR_WIDTH','23'),n)for d,w,n in fp if n in('clk','rst')or n.startswith('s_axi_')]
    public +=[(d,w,n)for d,w,n in ep if n in('enable','cfg_latency','cfg_fixed_latency')or n.startswith('phy_')]
    public +=[('output','','idle'),('output','[7:0]','memory_detail')]
    assert len({n for _,_,n in public})==len(public)
    lines=['`timescale 1ns/1ps','`default_nettype none','// Passive same-clock test wiring; not a pin-level controller or initialization manager.',
        'module cocotb_axi_hyperram_engine_top #(parameter MEMORY_CLOCK_HZ=200000000)(']
    lines +=[f'    {d} wire {w} {n}{","if i+1<len(public)else""}'for i,(d,w,n)in enumerate(public)]
    lines +=[');','wire frontend_idle,engine_idle;','assign idle=frontend_idle&&engine_idle;']
    for _,w,n in fp:
        if n.startswith('hb_'):lines.append(f'wire {w.replace("ADDR_WIDTH","23")} {n};')
    lines +=['axi_hyperram_bridge #(.ADDR_WIDTH(23)) frontend(',
        ',\n'.join('    .'+n+'('+('frontend_idle'if n=='idle'else n)+')'for _,_,n in fp),');']
    connections={n:n for _,_,n in ep}
    for n in ('valid','ready','write','address','bytes','data','strobes'):connections['cmd_'+n]='hb_cmd_'+n
    connections['cmd_register']="1'b0"
    for n in ('valid','ready','data','error'):connections['rsp_'+n]='hb_rsp_'+n
    connections['rsp_detail']='memory_detail';connections['idle']='engine_idle'
    lines +=['hyperram_transaction_engine #(.MEMORY_CLOCK_HZ(MEMORY_CLOCK_HZ)) engine(',
        ',\n'.join(f'    .{n}({connections[n]})'for _,_,n in ep),');','endmodule','`default_nettype wire','']
    target=root/'sim/cocotb_axi_hyperram_engine_top.sv';target.write_text('\n'.join(lines))
    result=dict(generator_sha256=sha(Path(__file__)),input_sha256={str(p.relative_to(root)).replace('\\','/'):sha(p)for p in paths},
        port_parser_sha256=sha(root/'tools/generate_bidirectional_application.py'),fixture_sha256=sha(target),
        actual_production_modules_connected=True,physical_phy_present=False,full_system_complete=False)
    folder=root/'build/hyperram-engine';folder.mkdir(parents=True,exist_ok=True)
    (folder/'fixture-generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
