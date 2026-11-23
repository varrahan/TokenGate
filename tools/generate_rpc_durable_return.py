"""Connect actual RPC progress authorization to actual durable frame grants.

Keep the tested private framer/progress wrapper intact. The shared directory
and window service never sees its private pre-grant buffer reset.
"""
import argparse
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY, header_end, instance, named_instance

from rtl_paths import source_path, source_relative


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--keyed',action='store_true');args=parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    grant_top='http2_keyed_frame_grants'if args.keyed else'http2_durable_frame_grants'
    return_top='rpc_grpc_keyed_return'if args.keyed else'rpc_grpc_durable_return'
    original_path = source_path(root, 'rtl/grpc_durable_window_framer.v')
    original = original_path.read_text()
    framer_ports = {n for _, _, n in ports((source_path(root, 'rtl/grpc_http2_response_framer.v')).read_text(), 'grpc_http2_response_framer')}
    keep = {'clk', 'rst', 'start_valid', 'start_ready', 'start_user', 'start_stream', 'idle'}
    public = [p for p in ports(original, 'grpc_durable_window_framer') if p[2] not in framer_ports or p[2] in keep]
    public += [('input', '', 'frame_req_valid'), ('output', '', 'frame_req_ready'),
        ('input', '[USER_WIDTH-1:0]', 'frame_req_user'), ('input', '[30:0]', 'frame_req_stream'),
        ('input', '[23:0]', 'frame_req_max_bytes'), ('output', '[23:0]', 'frame_grant_bytes'),
        ('input', '', 'finish_valid'), ('output', '', 'finish_ready'), ('output', '', 'credit_binding_active')]
    body = original[header_end(original, 'grpc_durable_window_framer') + 2:]
    start, end, _, _ = instance(body, 'grpc_http2_response_framer', 'framer')
    body = body[:start] + body[end:]
    for old, new in (
        ('wire owned_idle,framer_idle,framer_start_ready,owned_request_ready,owned_result_valid,owned_result_ready;',
         'wire owned_idle,owned_request_ready,owned_result_valid,owned_result_ready;'),
        ('wire frame_request_valid,frame_request_ready;wire [USER_WIDTH-1:0] frame_request_user;\nwire [30:0] frame_request_stream;wire [23:0] frame_request_maximum,grant_bytes;',
         'wire frame_request_valid=frame_req_valid;wire frame_request_ready;\n'
         'wire [23:0] frame_request_maximum=frame_req_max_bytes;wire [23:0] grant_bytes;\n'
         'assign frame_req_ready=frame_request_ready;assign frame_grant_bytes=grant_bytes;\n'
         'assign credit_binding_active=frame_active;assign finish_ready=state==IDLE&&!window_busy;'),
        ('wire reserve_pending=frame_active&&frame_request_valid&&!parked;',
         'wire reserve_pending=frame_active&&frame_request_valid&&!parked&&frame_req_user==frame_owner&&frame_req_stream==frame_stream;'),
        ('assign start_ready=!rst&&framer_start_ready&&!frame_active&&lease_matches;',
         'assign start_ready=!rst&&!frame_active&&lease_matches;'),
        ('assign idle=owned_idle&&framer_idle&&state==IDLE&&!frame_active&&!start_valid;',
         'assign idle=owned_idle&&state==IDLE&&!frame_active&&!start_valid;'),
        ('.lease_rsp_ready(lease_rsp_ready&&!frame_active&&!start_valid&&!window_busy&&state==IDLE)',
         '.lease_rsp_ready(lease_rsp_ready&&(!frame_active||finish_valid)&&!start_valid&&finish_ready)'),
        ('if(result_valid&&result_ready)begin frame_active<=0;parked<=0;end',
         'if(finish_valid&&finish_ready)begin frame_active<=0;parked<=0;end'),
    ):
        body = once(body, old, new)
    if args.keyed:
        body=once(body,'http2_owned_lifecycle_windows #(', 'http2_owned_keyed_windows #(')
        body=once(body,'owned_window_rsp_op==4||owned_window_rsp_op==8)', 'owned_window_rsp_op==4||owned_window_rsp_op==8||owned_window_rsp_op==9)')
    target = source_path(root, f'rtl/{grant_top}.v')
    target.write_text('\n'.join(['`timescale 1ns/1ps', '`default_nettype none',
        '// Actual cached LOAD/pool grant + durable credit scheduler; frame_req is already authorized.',
        f'module {grant_top} #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');', body]))

    response_path = source_path(root, 'rtl/rpc_grpc_parser_response.v')
    response = ports(response_path.read_text(), 'rpc_grpc_parser_response')
    service = ports(target.read_text(), grant_top)
    control_names = {n: 'control_' + (n[4:] if n.startswith('cfg_') else n)
                     for _, _, n in service if n.startswith(('req_', 'rsp_', 'cfg_pool_'))}
    hidden = {'frame_req_valid', 'frame_req_ready', 'frame_req_user', 'frame_req_stream', 'frame_req_max_bytes', 'frame_grant_bytes'}
    public = [(d, f'[3*{MEMORY[n][0]}-1:0]' if n in MEMORY else w, n)
        for d, w, n in response if (not n.startswith('directory_') or n == 'directory_lease_active') and n not in hidden]
    public += [(d, w, control_names[n]) for d, w, n in service if n in control_names]
    public += [p for p in service if p[2].startswith('window_')]
    public += [('input', '[MEMORY_ADDR_WIDTH-1:0]', 'cfg_context_base'), ('input', '[MEMORY_ADDR_WIDTH:0]', 'cfg_context_bytes'),
        ('input', '[MEMORY_ADDR_WIDTH-1:0]', 'cfg_window_base'), ('input', '[MEMORY_ADDR_WIDTH:0]', 'cfg_window_bytes'),
        ('output', '', 'record_lease_active'), ('output', '', 'directory_recovery_required'),
        ('output', '[MEMORY_ADDR_WIDTH-1:0]', 'directory_recovery_address'), ('output', '', 'credit_parked'),
        ('output', '', 'directory_pool_lock_active'), ('output', '[7:0]', 'result_credit_status'),
        ('output', '[7:0]', 'result_credit_detail'), ('output', '[31:0]', 'result_credit_http2_error'),
        ('output', '', 'result_credit_connection_error')]
    assert len(public) == len({n for _, _, n in public})
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Actual progress-authorized RPC return with durable connection/stream credits.',
        '// Local clients: zero RPC progress; one shared directory; two send windows.',
        f'module {return_top} #(', 'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384,',
        'parameter integer MAX_MESSAGE_BYTES=6*MAX_TEXT_BYTES+46', ')(',
        ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');',
        'wire response_idle,grant_idle,response_recovery,grant_finish_ready,credit_binding_active;',
        'wire child_result_valid,credit_error_valid;wire [7:0] child_memory_status,credit_error_status,credit_error_detail,credit_error_memory_status;',
        'wire [31:0] credit_error_http2_error;wire credit_error_connection_error;',
        'reg [7:0] held_credit_status,held_credit_detail,held_credit_memory_status;',
        'reg [31:0] held_credit_http2_error;reg held_credit_connection_error;',
        'wire [MEMORY_ADDR_WIDTH-1:0] response_recovery_address;',
        'assign result_valid=child_result_valid&&grant_finish_ready;',
        'wire retire=result_valid&&result_ready;',
        'assign result_memory_status=child_memory_status!=0?child_memory_status:held_credit_memory_status;',
        'assign result_credit_status=held_credit_status;assign result_credit_detail=held_credit_detail;',
        'assign result_credit_http2_error=held_credit_http2_error;assign result_credit_connection_error=held_credit_connection_error;',
        'assign recovery_required=response_recovery||directory_recovery_required||window_recovery_required;',
        'assign recovery_address=response_recovery?response_recovery_address:directory_recovery_required?directory_recovery_address:window_recovery_address;',
        'assign idle=response_idle&&grant_idle;',
        'wire frame_req_valid,frame_req_ready;wire [USER_WIDTH-1:0] frame_req_user;',
        'wire [30:0] frame_req_stream;wire [23:0] frame_req_max_bytes,frame_grant_bytes;']
    lines += [f'wire {w} {n};' for _, w, n in response if n.startswith('directory_') and n != 'directory_lease_active']
    lines += [f'wire {w} response_{n};' for _, w, n in response if n in MEMORY]
    for n, (bits, direction) in MEMORY.items():
        lines += [f'wire [2*{bits}-1:0] grant_{n};']
        if direction == 'output': lines += [f'assign {n}={{grant_{n},response_{n}[0+:{bits}]}};']
        else:
            lines += [f"assign response_{n}={{{{{bits}{{1'b0}}}},{n}[0+:{bits}]}};",
                      f'assign grant_{n}={n}[{bits}+:2*{bits}];']
    configs = [(d, w, n) for d, w, n in service if n.startswith('frame_cfg_')]
    lines += [f'reg {w} saved_{n};' for _, w, n in configs]
    connections = {n: 'response_' + n if n in MEMORY else n for _, _, n in response}
    connections.update(idle='response_idle', recovery_required='response_recovery', recovery_address='response_recovery_address',
        result_valid='child_result_valid', result_ready='result_ready&&grant_finish_ready', result_memory_status='child_memory_status')
    lines += [named_instance('rpc_grpc_parser_response',
        '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)',
        'response', connections)]
    lease = dict(lease_valid='directory_valid', lease_ready='directory_ready', lease_user='directory_user', lease_stream='directory_stream',
        lease_pool_base='directory_pool_base', lease_pool_bytes='directory_pool_bytes', lease_rsp_valid='directory_result_valid',
        lease_rsp_ready='directory_result_ready', lease_rsp_status='directory_status', lease_rsp_memory_status='directory_memory_status',
        lease_rsp_address='directory_address', lease_rsp_application='directory_application', lease_rsp_generation='directory_generation',
        lease_rsp_protobuf='directory_protobuf', lease_rsp_unsupported_encoding='directory_unsupported_encoding', lease_active='record_lease_active')
    connections = {n: control_names.get(n, n if n.startswith(('window_', 'credit_error_', 'frame_req_', 'frame_grant_')) else '')
                   for _, _, n in service}
    connections.update(clk='clk', rst='rst', idle='grant_idle', recovery_required='directory_recovery_required',
        recovery_address='directory_recovery_address', directory_pool_lock_active='directory_pool_lock_active',
        credit_error_ready="1'b1", start_valid='frame_req_valid&&!credit_binding_active', start_ready='',
        credit_error_user='', credit_error_stream='',
        start_user='frame_req_user', start_stream='frame_req_stream', finish_valid='retire', finish_ready='grant_finish_ready',
        credit_binding_active='credit_binding_active', credit_parked='credit_parked')
    connections.update(lease)
    connections.update({n: 'saved_' + n for _, _, n in configs})
    connections.update({n: 'grant_' + n for n in MEMORY})
    lines += [named_instance(grant_top, '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)',
        'directory_service', connections)]
    lines += ['always @(posedge clk)begin', '    if(rst)begin',
        '        held_credit_status<=0;held_credit_detail<=0;held_credit_memory_status<=0;held_credit_http2_error<=0;held_credit_connection_error<=0;']
    lines += [f'        saved_{n}<=0;' for _, _, n in configs]
    lines += ['    end else begin', '        if(s_axis_tokens_tvalid&&s_axis_tokens_tready)begin',
        '            held_credit_status<=0;held_credit_detail<=0;held_credit_memory_status<=0;held_credit_http2_error<=0;held_credit_connection_error<=0;']
    lines += [f'            saved_{n}<=cfg_{n.removeprefix("frame_cfg_")};' for _, _, n in configs]
    lines += ['        end', '        if(credit_error_valid)begin',
        '            held_credit_status<=credit_error_status;held_credit_detail<=credit_error_detail;held_credit_memory_status<=credit_error_memory_status;',
        '            held_credit_http2_error<=credit_error_http2_error;held_credit_connection_error<=credit_error_connection_error;',
        '        end', '    end', 'end', 'endmodule', '`default_nettype wire', '']
    joined_path = source_path(root, f'rtl/{return_top}.v'); joined_path.write_text('\n'.join(lines))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    label='rpc-keyed-generation.json'if args.keyed else'rpc-durable-generation.json'
    extra_inputs=[source_path(root, 'rtl/http2_owned_keyed_windows.v'),source_path(root, 'rtl/http2_keyed_send_window_store.v')]if args.keyed else[]
    (root / 'build/validation'/label).write_text(json.dumps(dict(
        phase='generated_actual_progress_authorized_durable_rpc', input_sha256={source_relative(p, root).as_posix(): sha(p)
        for p in (original_path, response_path, Path(__file__),*extra_inputs)}, generated_sha256={source_relative(p, root).as_posix(): sha(p)
        for p in (target, joined_path)}, memory_clients=3, actual_progress_gate_preserved=True,
        key_only_updates_supported=args.keyed,raw_control_integrated=False, full_system_complete=False), indent=2) + '\n')
    print('Generated actual progress-authorized RPC/durable-grant join; three local memory clients')


if __name__ == '__main__':
    main()
