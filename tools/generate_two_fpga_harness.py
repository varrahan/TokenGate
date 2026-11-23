"""Connect separate real application tops and two independent memory fabrics."""
import argparse
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY, named_instance

from rtl_paths import source_path


def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--tokenizer-memory', action='store_true')
    arguments.add_argument('--framed-parser', action='store_true')
    arguments.add_argument('--controlled-parser', action='store_true')
    arguments.add_argument('--initialized-parser', action='store_true')
    arguments.add_argument('--journaled-parser', action='store_true')
    arguments.add_argument('--peer-parser', action='store_true')
    arguments.add_argument('--classified-parser', action='store_true')
    arguments.add_argument('--shutdown-parser', action='store_true')
    arguments.add_argument('--enveloped-parser', action='store_true')
    args = arguments.parse_args()
    if args.shutdown_parser or args.enveloped_parser:args.classified_parser=True
    root = Path(__file__).resolve().parents[1]
    def interface(name):
        return ports((source_path(root, Path('rtl') / (name + '.v'))).read_text(), name)
    original = interface('http2_bidirectional_application')
    assert sum((args.framed_parser,args.controlled_parser,args.initialized_parser,args.journaled_parser,args.peer_parser,args.classified_parser))<=1
    parser_top='http2_classified_parser_application' if args.classified_parser else 'http2_peer_parser_application' if args.peer_parser else 'http2_journaled_parser_application' if args.journaled_parser else 'http2_initialized_parser_application' if args.initialized_parser else 'http2_controlled_parser_application' if args.controlled_parser else 'http2_framed_parser_application' if args.framed_parser else 'http2_parser_fpga_application'
    if args.shutdown_parser:parser_top='http2_shutdown_parser_application'
    if args.enveloped_parser:parser_top='http2_enveloped_parser_application'
    parser_count=17 if args.classified_parser else 16 if args.peer_parser else 15 if args.journaled_parser else 14 if args.initialized_parser else 13
    global_count=26 if args.classified_parser else 25 if args.peer_parser else 24 if args.journaled_parser else 23 if args.initialized_parser else 22
    parser = interface(parser_top)
    token_top = 'tokenizer_fpga_memory_subsystem' if args.tokenizer_memory else 'tokenizer_fpga_application'
    tokenizer = interface(token_top)
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
             '// Passive fixture: separate production applications and local fabrics.',
             'module cocotb_two_fpga_classified_top;' if args.classified_parser else 'module cocotb_two_fpga_peer_top;' if args.peer_parser else 'module cocotb_two_fpga_journaled_top;' if args.journaled_parser else 'module cocotb_two_fpga_initialized_top;' if args.initialized_parser else 'module cocotb_two_fpga_controlled_top;' if args.controlled_parser else 'module cocotb_two_fpga_framed_top;' if args.framed_parser else 'module cocotb_two_fpga_memory_top;' if args.tokenizer_memory else 'module cocotb_two_fpga_application_top;',
             'localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    if args.shutdown_parser:lines=[line.replace('module cocotb_two_fpga_classified_top;','module cocotb_two_fpga_shutdown_top;')for line in lines]
    if args.enveloped_parser:lines=[line.replace('module cocotb_two_fpga_classified_top;','module cocotb_two_fpga_enveloped_top;')for line in lines]
    for direction, width, name in original:
        if (args.initialized_parser or args.journaled_parser or args.peer_parser or args.classified_parser) and name in MEMORY:width=f'[{global_count}*{MEMORY[name][0]}-1:0]'
        driven = direction == 'input' and name not in MEMORY
        lines.append(f"{'reg' if driven else 'wire'} {width} {name}{'=0' if driven else ''};")
    for _, width, name in parser:
        if name.startswith('link_'):
            lines.append(f'wire {width} {name};')
    original_names={n for _,_,n in original}
    for direction,width,name in parser:
        if name not in original_names and not name.startswith('link_'):
            driven=direction=='input'
            lines.append(f"{'reg' if driven else 'wire'} {width} {name}{'=0' if driven else ''};")
    for prefix, count in [('p', parser_count), ('t', 9)]:
        for name, (bits, _) in MEMORY.items():
            lines.append(f'wire [{count}*{bits}-1:0] {prefix}_{name};')
        lines.append(f'wire [{count}*8-1:0] {prefix}_fabric_status;wire {prefix}_fabric_idle;')
    for top, prefix, name, public in [(parser_top, 'p', 'dut', parser),
                                      (token_top, 't', 'tokenizer', tokenizer)]:
        connections = {n: prefix + '_' + n if n in MEMORY else n for _, _, n in public}
        if args.tokenizer_memory and prefix == 't':
            connections.update({n: 't_axi_' + n[6:] for _, _, n in public if n.startswith('m_axi_')})
            connections.update(cfg_invalidate_valid="1'b0", cfg_invalidate_ready='', memory_idle='t_fabric_idle')
        lines.append(named_instance(top, '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', name, connections))
    lines.extend([f'wire fabric_idle=p_fabric_idle&&t_fabric_idle;wire [{global_count}*8-1:0] fabric_status;',
        'integer fault_client=-1,fault_target=-1,response_index=0;reg fault_arm=0,fault_injected=0;'])
    parser_clients=[*range(1,5),*range(13,21),0,22,23,24,25] if args.classified_parser else [*range(1,5),*range(13,21),0,22,23] if args.journaled_parser else [*range(1,5),*range(13,21),0,22,23,24] if args.peer_parser else [*range(1,5),*range(13,21),0,22] if args.initialized_parser else [*range(1,5),*range(13,21),0] if args.framed_parser or args.controlled_parser else [*range(5),*range(13,21)]
    clients = [('p', parser_clients), ('t', [*range(5, 13), 21])]
    for prefix, previous_clients in clients:
        for compact, previous in enumerate(previous_clients):
            for name, (bits, _) in MEMORY.items():
                logical = f'{name}[{previous}*{bits}+:{bits}]'
                local = f'{prefix}_{name}[{compact}*{bits}+:{bits}]'
                lines.append(f'assign {local}={logical};' if name == 'mem_rsp_status'
                             else f'assign {logical}={local};')
            lines.append(f'assign fabric_status[{previous}*8+:8]={prefix}_fabric_status[{compact}*8+:8];')
    inputs = dict(arready=1, rdata=64, rresp=2, rlast=1, rvalid=1, awready=1, wready=1, bresp=2, bvalid=1)
    outputs = dict(araddr=23, arlen=8, arsize=3, arburst=2, arvalid=1, rready=1,
                   awaddr=23, awlen=8, awsize=3, awburst=2, awvalid=1,
                   wdata=64, wstrb=8, wlast=1, wvalid=1, bready=1)
    for prefix, count in [('p', parser_count), ('t', 9)]:
        for name, bits in {**inputs, **outputs}.items():
            lines.append(f"{'reg' if name in inputs else 'wire'} {'['+str(bits-1)+':0]' if bits>1 else ''} {prefix}_axi_{name}{'=0' if name in inputs else ''};")
        connections = dict(clk='clk', rst='rst', invalidate_valid="1'b0", invalidate_ready='',
            s_valid=prefix+'_mem_valid', s_ready=prefix+'_mem_ready', s_write=prefix+'_mem_write',
            s_addr=prefix+'_mem_addr', s_bytes=prefix+'_mem_bytes', s_data=prefix+'_mem_data',
            rsp_valid=prefix+'_mem_rsp_valid', rsp_ready=prefix+'_mem_rsp_ready',
            rsp_data=prefix+'_mem_rsp_data', rsp_status=prefix+'_fabric_status', idle=prefix+'_fabric_idle')
        connections.update({'m_axi_'+n: prefix+'_axi_'+n for n in {**inputs, **outputs}})
        if args.tokenizer_memory and prefix == 't':
            # Observe production-owned command wires. Inject the same directed
            # response faults at the application input, outside synthesizable RTL.
            # Read actual arbiter status registers to avoid a forced-net feedback.
            for signal in MEMORY:
                if signal != 'mem_rsp_status':
                    lines.append(f'assign t_{signal}=tokenizer.{signal};')
            lines.extend(['generate for(genvar status_client=0;status_client<9;status_client=status_client+1)begin: tokenizer_status',
                'assign t_fabric_status[status_client*8+:8]=tokenizer.fabric.arbiter.statuses[status_client];',
                'end endgenerate',
                'initial force tokenizer.application.mem_rsp_status=t_mem_rsp_status;'])
        else:
            lines.append(named_instance('external_memory_fabric', f'.CLIENTS({count})', prefix+'_fabric', connections))
    lines.extend([f'generate for(genvar client=0;client<{global_count};client=client+1)begin: fault_ports',
        "assign mem_rsp_status[client*8+:8]=(fault_client==client&&!fault_injected&&response_index==fault_target)?8'h75:fabric_status[client*8+:8];",
        'end endgenerate', 'always @(posedge clk)begin',
        'if(rst||fault_arm)begin response_index<=0;fault_injected<=0;end',
        f'else if(fault_client>=0&&fault_client<{global_count}&&mem_rsp_valid[fault_client]&&mem_rsp_ready[fault_client])begin',
        'if(!fault_injected&&response_index==fault_target)fault_injected<=1;response_index<=response_index+1;',
        'end end', 'endmodule', '`default_nettype wire', ''])
    output = source_path(root, 'sim/cocotb_two_fpga_classified_top.sv' if args.classified_parser else 'sim/cocotb_two_fpga_peer_top.sv' if args.peer_parser else 'sim/cocotb_two_fpga_journaled_top.sv' if args.journaled_parser else 'sim/cocotb_two_fpga_initialized_top.sv' if args.initialized_parser else 'sim/cocotb_two_fpga_controlled_top.sv' if args.controlled_parser else 'sim/cocotb_two_fpga_framed_top.sv' if args.framed_parser else 'sim/cocotb_two_fpga_memory_top.sv' if args.tokenizer_memory else 'sim/cocotb_two_fpga_application_top.sv')
    if args.shutdown_parser:output=root/'sim/cocotb_two_fpga_shutdown_top.sv'
    if args.enveloped_parser:output=root/'sim/cocotb_two_fpga_enveloped_top.sv'
    output.write_text('\n'.join(lines))
    print(f'Generated two-FPGA passive harness with independent {parser_count}/9-client memory fabrics; Tokenizer fabric integrated=' + str(args.tokenizer_memory))


if __name__ == '__main__':
    main()
