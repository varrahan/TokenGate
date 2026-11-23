"""One production Parser return partition and one shared, leased directory."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY, named_instance

from rtl_paths import source_path, source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    response_path = source_path(root, 'rtl/rpc_grpc_parser_response.v')
    service_path = source_path(root, 'rtl/grpc_leased_stream_store.v')
    response = ports(response_path.read_text(), 'rpc_grpc_parser_response')
    service = ports(service_path.read_text(), 'grpc_leased_stream_store')
    control_names = {n: 'control_' + (n[4:] if n.startswith('cfg_') else n)
        for _, _, n in service if n.startswith(('req_', 'rsp_', 'cfg_pool_'))}
    public = [p for p in response if not p[2].startswith('directory_') or p[2]=='directory_lease_active']
    public += [(d, w, control_names[n]) for d, w, n in service if n in control_names]
    public += [('output', '', 'record_lease_active'), ('output', '', 'directory_recovery_required'),
               ('output', '[MEMORY_ADDR_WIDTH-1:0]', 'directory_recovery_address')]
    assert len({n for _, _, n in public}) == len(public)
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Actual Parser return and its single shared directory authority.',
        '// Memory lane 0: RPC progress; lane 1: directory. Inverse stays remote.',
        'module rpc_grpc_leased_return #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384,',
        'parameter integer MAX_MESSAGE_BYTES=6*MAX_TEXT_BYTES+46', ')(',
        ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');',
        'wire response_idle,directory_idle,response_recovery;',
        'wire [MEMORY_ADDR_WIDTH-1:0] response_recovery_address;',
        'assign idle=response_idle&&directory_idle;',
        'assign recovery_required=response_recovery||directory_recovery_required;',
        'assign recovery_address=response_recovery?response_recovery_address:directory_recovery_address;']
    lines += [f'wire {w} {n};' for _, w, n in response if n.startswith('directory_') and n!='directory_lease_active']
    lines += [f'wire {w} response_{n};' for _, w, n in response if n in MEMORY]
    lines += [f'wire {w} directory_{n};' for _, w, n in service if n.startswith('mem_')]
    for name, (bits, direction) in MEMORY.items():
        if direction == 'output':
            lines.append(f'assign {name}={{directory_{name},response_{name}[0+:{bits}]}};')
        else:
            lines.append(f"assign response_{name}={{{{{bits}{{1'b0}}}},{name}[0+:{bits}]}};")
            lines.append(f'assign directory_{name}={name}[{bits}+:{bits}];')
    connections = {n: 'response_' + n if n in MEMORY else n for _, _, n in response}
    connections.update(idle='response_idle', recovery_required='response_recovery', recovery_address='response_recovery_address')
    lines.append(named_instance('rpc_grpc_parser_response',
        '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)',
        'response', connections))
    lease = dict(lease_valid='directory_valid', lease_ready='directory_ready', lease_user='directory_user', lease_stream='directory_stream',
        lease_pool_base='directory_pool_base', lease_pool_bytes='directory_pool_bytes', lease_rsp_valid='directory_result_valid',
        lease_rsp_ready='directory_result_ready', lease_rsp_status='directory_status', lease_rsp_memory_status='directory_memory_status',
        lease_rsp_address='directory_address', lease_rsp_application='directory_application', lease_rsp_generation='directory_generation',
        lease_rsp_protobuf='directory_protobuf', lease_rsp_unsupported_encoding='directory_unsupported_encoding', lease_active='record_lease_active')
    connections = {n: control_names.get(n, '') for _, _, n in service}
    connections.update(clk='clk', rst='rst', idle='directory_idle', recovery_required='directory_recovery_required', recovery_address='directory_recovery_address')
    connections.update({n: 'directory_' + n for _, _, n in service if n.startswith('mem_')})
    connections.update(lease)
    lines.append(named_instance('grpc_leased_stream_store', '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)',
                               'directory_service', connections))
    lines += ['endmodule', '`default_nettype wire', '']
    target = source_path(root, 'rtl/rpc_grpc_leased_return.v')
    target.write_text('\n'.join(lines))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (root / 'build/validation/rpc-grpc-leased-generation.json').write_text(json.dumps(dict(
        phase='generated_return_with_shared_leased_directory', inputs_sha256={source_relative(p, root).as_posix(): sha(p)
            for p in (response_path, service_path, Path(__file__))}, generated_sha256=sha(target),
        local_memory_clients=2, inverse_is_remote=True, full_transport_verified=False), indent=2) + '\n')
    print('Generated actual Parser return + shared cached-lease directory; two local memory clients')


if __name__ == '__main__':
    main()
