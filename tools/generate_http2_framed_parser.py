"""Join raw Parser ingress and framed return around one directory authority.

Keep the saved baseline intact. The new top still exposes credit reservations
to its parent; a transport ledger, response headers/trailers and physical
interfaces remain required.
"""
import argparse
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import (MEMORY, add_ports, header_end, instance,
    named_instance, opposite, propagate, rename)

from rtl_paths import source_path, source_relative


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--control-fork',action='store_true')
    args=parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    inputs = {}
    outputs = {}

    def read(name):
        path = source_path(root, 'rtl/' + name + '.v')
        inputs[source_relative(path, root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text()

    def emit(name, source):
        path = source_path(root, 'rtl/' + name + '.v')
        path.write_text(source)
        outputs[source_relative(path, root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    transport_name='http2_controlled_parser_transport' if args.control_fork else 'http2_shared_directory_transport'
    core_name='http2_controlled_parser_core' if args.control_fork else 'http2_framed_parser_core'
    top_name='http2_controlled_parser_application' if args.control_fork else 'http2_framed_parser_application'
    flow_public=[p for p in ports(read('http2_controlled_hpack_ingress'),'http2_controlled_hpack_ingress') if p[2].startswith('flow_event_')] if args.control_fork else []

    # Externalize the existing ingress engine's directory transaction interface.
    # Its memory client zero becomes unused; no shadow registry is retained.
    source = read('grpc_ingress_engine')
    start, end, _, connections = instance(source, 'grpc_stream_store', 'registry')
    directory = []
    assignments = []
    for direction, width, name in ports(read('grpc_stream_store'), 'grpc_stream_store'):
        expression = connections[name]
        if name in ('clk', 'rst'):
            continue
        if name in MEMORY:
            if direction == 'output':
                assignments.append(f'assign {expression}=0;')
            continue
        directory.append((opposite(direction), width, 'dir_' + name))
        assignments.append(f'assign dir_{name}={expression};' if direction == 'input'
                           else f'assign {expression}=dir_{name};')
    source = source[:start] + '\n'.join(assignments) + source[end:]
    source = rename(add_ports(source, 'grpc_ingress_engine', directory),
                    'grpc_ingress_engine', 'grpc_external_directory_ingress')
    emit('grpc_external_directory_ingress', source)
    chain = [
        ('grpc_ingress_parser', 'grpc_shared_directory_parser', 'grpc_ingress_engine', 'ingress', 'grpc_external_directory_ingress'),
        ('grpc_prefill_parser_partition', 'grpc_shared_directory_prefill', 'grpc_ingress_parser', 'parser', 'grpc_shared_directory_parser'),
        ('http2_parser_transport_partition', transport_name, 'grpc_prefill_parser_partition', 'prefill', 'grpc_shared_directory_prefill'),
    ]
    for old, new, child, child_name, replacement in chain:
        source = propagate(read(old), old, new, child, child_name, replacement, directory)
        if args.control_fork and new==transport_name:
            source=propagate(source,new,new,'http2_hpack_ingress','transport','http2_controlled_hpack_ingress',flow_public)
        emit(new, source)

    # Schedule only the return LOAD, retaining early GPU descriptor admission.
    # Generic-control idle is local-front quiescence, not global lease release.
    scheduled = read('rpc_grpc_leased_return')
    extra = [('input', '', 'lookup_admit'), ('output', '', 'lookup_waiting'),
             ('output', '', 'lookup_ready'), ('output', '', 'control_idle')]
    scheduled = add_ports(scheduled, 'rpc_grpc_leased_return', extra)
    scheduled = rename(scheduled, 'rpc_grpc_leased_return', 'rpc_grpc_scheduled_return')
    start, end, params, service = instance(scheduled, 'grpc_leased_stream_store', 'directory_service')
    service['lease_valid'] = 'directory_valid&&lookup_admit'
    service['lease_ready'] = 'service_lease_ready'
    scheduled = scheduled[:start] + named_instance('grpc_leased_stream_store', params, 'directory_service', service) + scheduled[end:]
    scheduled = scheduled.replace('endmodule', '''wire service_lease_ready;
reg generic_pending;
assign directory_ready=service_lease_ready&&lookup_admit;
assign lookup_waiting=directory_valid;
assign lookup_ready=directory_ready;
assign control_idle=!generic_pending&&!control_req_valid&&!control_rsp_valid;
always @(posedge clk)begin
    if(rst)generic_pending<=0;
    else begin
        if(control_req_valid&&control_req_ready)generic_pending<=1;
        if(control_rsp_valid&&control_rsp_ready)generic_pending<=0;
    end
end
endmodule''')
    emit('rpc_grpc_scheduled_return', scheduled)

    core = read('http2_parser_partition_core')
    # Use the existing forward link signals and preserve its actual engines.
    start, end, params, forward = instance(core, 'http2_parser_transport_partition', 'forward')
    forward.update({name: name for _, _, name in [*directory,*flow_public]})
    core = core[:start] + named_instance(transport_name, params, 'forward', forward) + core[end:]
    old_return = ports(read('rpc_response_parser_partition'), 'rpc_response_parser_partition')
    new_return = ports(scheduled, 'rpc_grpc_scheduled_return')
    start, end, params, reverse = instance(core, 'rpc_response_parser_partition', 'reverse')
    old_names = {n for _, _, n in old_return}
    core_names = {n for _, _, n in ports(core, 'http2_parser_partition_core')}
    public_extra = list(flow_public)
    for direction, width, name in new_return:
        if name in old_names:
            if name.startswith('m_axis_tx_'):
                reverse[name] = name
            continue
        if name.startswith('control_') and not name.startswith('control_event_'):
            if name == 'control_idle':
                reverse[name] = 'dir_idle'
            elif name in ('control_pool_base', 'control_pool_bytes'):
                reverse[name] = 'dir_cfg_' + name[8:]
            else:
                reverse[name] = 'dir_' + name[8:]
        elif name in ('directory_recovery_required', 'directory_recovery_address'):
            reverse[name] = 'dir_' + name.removeprefix('directory_')
        elif name == 'lookup_admit':
            reverse[name] = 'lookup_admit'
        elif name == 'lookup_waiting':
            reverse[name] = 'r_directory_valid'
        elif name == 'lookup_ready':
            reverse[name] = 'r_directory_ready'
        else:
            mapped = 'response_' + name if name in ('record_lease_active', 'result_progress_committed') else name
            reverse[name] = mapped
            if mapped not in core_names:
                public_extra.append((direction, width, mapped))
    reverse = {n: reverse[n] for _, _, n in new_return}
    core = core[:start] + named_instance('rpc_grpc_scheduled_return', params, 'reverse', reverse) + core[end:]
    start, end, _, _ = instance(core, 'utf8_serialized_chunk', 'response_serializer')
    core = core[:start] + core[end:]
    # Directory ports stay local between forward and reverse components.
    start = core.index('wire  r_directory_valid;')
    end = core.index('assign mem_valid[0+:20]=f_mem_valid;', start)
    control_wires = []
    for direction, width, name in directory:
        control_wires.append(f'wire {width} {name};')
    control_assigns = []
    for _, _, name in ports(read('http2_parser_transport_partition'), 'http2_parser_transport_partition'):
        if name.startswith('control_') and not name.startswith('control_event_'):
            control_assigns.append(f'assign f_{name}={name};' if name in ('control_valid','control_result_ready') or
                name in {n for d, _, n in ports(read('http2_parser_transport_partition'), 'http2_parser_transport_partition') if d=='input'}
                else f'assign {name}=f_{name};')
    control_assigns += ['assign f_queue_cfg_valid=queue_cfg_valid&&allow_config;',
        'assign queue_cfg_ready=f_queue_cfg_ready&&allow_config;',
        'assign f_stream_cfg_valid=stream_cfg_valid&&allow_config;',
        'assign stream_cfg_ready=f_stream_cfg_ready&&allow_config;',
        'assign f_cfg_schema_valid=cfg_schema_valid&&allow_config;',
        'assign cfg_schema_ready=f_cfg_schema_ready&&allow_config;',
        'assign f_command_valid=command_valid&&allow_config;',
        'assign command_ready=f_command_ready&&allow_config;']
    scheduling = '''
wire r_directory_valid,r_directory_ready;
reg rx_active,return_pending,owned_stream_valid,forward_quiet;
reg [MEMORY_ADDR_WIDTH-1:0] pending_stream_base,owned_stream_base;
reg [MEMORY_ADDR_WIDTH:0] pending_stream_bytes,owned_stream_bytes;
wire reverse_input_ready;
wire reverse_admit=owned_stream_valid&&!return_pending&&!cfg_unlock&&!control_valid&&
    !command_valid&&!queue_cfg_valid&&!stream_cfg_valid&&!queue_cfg_result_valid&&!stream_cfg_result_valid;
wire lookup_admit=return_pending&&forward_quiet&&!rx_active&&!control_valid;
wire allow_new_rx=!(s_axis_generated_tvalid&&reverse_admit)&&!(r_directory_valid&&lookup_admit);
wire allow_config=!return_pending;
assign f_s_axis_rx_tvalid=s_axis_rx_tvalid&&(rx_active||allow_new_rx);
assign s_axis_rx_tready=f_s_axis_rx_tready&&(rx_active||allow_new_rx);
assign s_axis_generated_tready=reverse_input_ready&&reverse_admit;
assign cfg_quiescent=f_cfg_quiescent&&!return_pending;
assign idle=f_idle&&response_idle&&!rx_active&&!s_axis_generated_tvalid;
always @(posedge clk)begin
    if(rst)begin
        rx_active<=0;return_pending<=0;owned_stream_valid<=0;forward_quiet<=0;
        pending_stream_base<=0;pending_stream_bytes<=0;owned_stream_base<=0;owned_stream_bytes<=0;
    end else begin
        forward_quiet<=f_idle&&!(s_axis_rx_tvalid&&s_axis_rx_tready)&&!control_valid&&!command_valid&&
            !queue_cfg_valid&&!stream_cfg_valid;
        if(s_axis_rx_tvalid&&s_axis_rx_tready)rx_active<=!s_axis_rx_tlast;
        if(s_axis_generated_tvalid&&s_axis_generated_tready)return_pending<=1;
        if(response_result_valid&&response_result_ready)return_pending<=0;
        if(stream_cfg_valid&&stream_cfg_ready)begin pending_stream_base<=cfg_stream_base;pending_stream_bytes<=cfg_stream_bytes;end
        if(stream_cfg_result_valid&&stream_cfg_status==0)begin owned_stream_base<=pending_stream_base;owned_stream_bytes<=pending_stream_bytes;owned_stream_valid<=1;end
    end
end
'''
    core = core[:start] + '\n'.join(control_wires + control_assigns) + scheduling + core[end:]
    core = add_ports(core, 'http2_parser_partition_core', public_extra)
    core = rename(core, 'http2_parser_partition_core', core_name)
    emit(core_name, core)

    # Preserve the existing thirteen-client external interface: the old
    # directory lane is replaced by the shared service's actual memory lane.
    public = [(d, w, n) for d, w, n in ports(core, core_name) if not n.startswith('m_axis_tokens_')]
    public = [(d, f'[13*{MEMORY[n][0]}-1:0]' if n in MEMORY else w, n) for d, w, n in public]
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Raw ingress + framed return with one shared runtime directory.',
        '// Credit ledger, HEADERS/trailers, image leases and physical adapters remain required.',
        'module '+top_name+' #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384',
        ')(\n' + ',\n'.join(f'{d} wire {w} {n}' for d,w,n in public) + '\n);']
    kept = [*range(1,5), *range(13,22)]
    for name, (bits, direction) in MEMORY.items():
        lines.append(f'wire [22*{bits}-1:0] all_{name};')
        for compact, previous in enumerate(kept):
            a = f'all_{name}[{previous}*{bits}+:{bits}]'
            b = f'{name}[{compact}*{bits}+:{bits}]'
            lines.append(f'assign {b}={a};' if direction=='output' else f'assign {a}={b};')
        if direction=='input':
            for previous in [0,*range(5,13)]:
                lines.append(f'assign all_{name}[{previous}*{bits}+:{bits}]=0;')
    connections = {n: 'all_'+n if n in MEMORY else
        "1'b0" if n=='m_axis_tokens_tready' else '' if n.startswith('m_axis_tokens_') else n
        for _,_,n in ports(core,core_name)}
    lines.append(named_instance(core_name,
        '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)',
        'core', connections))
    lines += ['endmodule','`default_nettype wire','']
    emit(top_name,'\n'.join(lines))
    result = dict(phase='generated_raw_framed_parser_join', inputs_sha256=inputs, generated_sha256=outputs,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parser_memory_clients=13, original_client_mapping=kept,control_fork_integrated=args.control_fork,
        whole_rpc_gpu_image_leases_verified=False, credit_ledger_verified=False, full_system_complete=False)
    (source_path(root, 'build/validation/http2-controlled-parser-generation.json' if args.control_fork else 'build/validation/http2-framed-parser-generation.json')).write_text(json.dumps(result,indent=2)+'\n')
    print('Generated raw framed Parser with one directory authority, thirteen memory clients and independent RX scheduling')


if __name__=='__main__':
    main()
