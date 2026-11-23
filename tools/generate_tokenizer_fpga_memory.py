"""Put the actual Tokenizer application and local nine-client fabric in one top."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY, named_instance


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'rtl/tokenizer_fpga_application.v'
    fabric_source = root / 'rtl/external_memory_fabric.v'
    app = ports(source.read_text(), 'tokenizer_fpga_application')
    fabric = ports(fabric_source.read_text(), 'external_memory_fabric')
    public = [(d, w, n) for d, w, n in app if n not in MEMORY]
    public += [('input', '', 'cfg_invalidate_valid'), ('output', '', 'cfg_invalidate_ready'),
               ('output', '', 'memory_idle')]
    public += [(d, w.replace('ADDR_WIDTH', 'MEMORY_ADDR_WIDTH'), n)
               for d, w, n in fabric if n.startswith('m_axi_')]
    assert len({n for _, _, n in public}) == len(public)
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Generated production wiring: real application, arbiter and XPM-backed cache.',
        '// memory_idle is local memory quiescence, not a whole-RPC/GPU image grant.',
        '// Physical memory/PCIe/link adapters and distributed image leases remain required.',
        'module tokenizer_fpga_memory_subsystem #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384,CACHE_LOG_LINES=6',
        ')(', ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');']
    for name, (bits, _) in MEMORY.items():
        lines.append(f'wire [9*{bits}-1:0] {name};')
    app_connections = {n: n for _, _, n in app}
    lines.append(named_instance('tokenizer_fpga_application',
        '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)',
        'application', app_connections))
    connections = dict(clk='clk', rst='rst', invalidate_valid='cfg_invalidate_valid', invalidate_ready='cfg_invalidate_ready',
        s_valid='mem_valid', s_ready='mem_ready', s_write='mem_write', s_addr='mem_addr', s_bytes='mem_bytes', s_data='mem_data',
        rsp_valid='mem_rsp_valid', rsp_ready='mem_rsp_ready', rsp_data='mem_rsp_data', rsp_status='mem_rsp_status', idle='memory_idle')
    connections.update({n: n for _, _, n in fabric if n.startswith('m_axi_')})
    assert set(connections) == {n for _, _, n in fabric}
    lines.append(named_instance('external_memory_fabric',
        '.CLIENTS(9),.ADDR_WIDTH(MEMORY_ADDR_WIDTH),.CACHE_LOG_LINES(CACHE_LOG_LINES)', 'fabric', connections))
    lines += ['endmodule', '`default_nettype wire', '']
    output = root / 'rtl/tokenizer_fpga_memory_subsystem.v'
    output.write_text('\n'.join(lines))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(phase='generated_tokenizer_with_local_memory_fabric', top='tokenizer_fpga_memory_subsystem',
        memory_clients=9, external_axi_data_width=64, cache_log_lines_default=6,
        source_sha256={p.relative_to(root).as_posix(): sha(p) for p in (source, fabric_source, Path(__file__))},
        generated_sha256=sha(output), physical_memory_controller_integrated=False,
        distributed_image_leases_integrated=False, full_system_complete=False)
    (root / 'build/validation/tokenizer-fpga-memory-generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Generated Tokenizer subsystem: actual application + nine-client arbiter/cache + external AXI master')


if __name__ == '__main__':
    main()
