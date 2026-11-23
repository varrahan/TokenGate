"""Extract actual engine instances into separate logical FPGA applications.

No algorithm or state machine is substituted. The emitted ports expose the
existing synchronous control/data dependencies; a physical link must transport
them with ordered commands/results, credits, image leases and reset recovery.
"""
import hashlib
import json
from pathlib import Path
import re

from generate_bidirectional_application import ports

from rtl_paths import source_path, source_relative


ROOT = Path(__file__).resolve().parents[1]
MEMORY = dict(mem_valid=(1, 'output'), mem_ready=(1, 'input'),
              mem_write=(1, 'output'), mem_addr=('MEMORY_ADDR_WIDTH', 'output'),
              mem_bytes=(4, 'output'), mem_data=(72, 'output'),
              mem_rsp_valid=(1, 'input'), mem_rsp_ready=(1, 'output'),
              mem_rsp_data=(72, 'input'), mem_rsp_status=(8, 'input'))
sources = {}
generated = {}


def read(name):
    path = source_path(ROOT, Path('rtl') / (name + '.v'))
    sources[source_relative(path, ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path.read_text()


def balanced(source, start):
    assert source[start] == '('
    depth = 1
    for end in range(start + 1, len(source)):
        if source[end] == '(':
            depth += 1
        elif source[end] == ')':
            depth -= 1
            if not depth:
                return end
    raise ValueError('Unclosed parenthesis')


def instance(source, module, name):
    for match in re.finditer(r'\b' + re.escape(module) + r'\s*#\s*\(', source):
        parameter_start = source.index('(', match.start())
        parameter_end = balanced(source, parameter_start)
        tail = re.match(r'\s*' + re.escape(name) + r'\s*\(', source[parameter_end + 1:])
        if tail:
            start = parameter_end + 1 + tail.end() - 1
            end = balanced(source, start)
            assert source[end + 1:].lstrip().startswith(';')
            stop = source.index(';', end) + 1
            body = source[start + 1:end]
            connections = {}
            offset = 0
            while offset < len(body):
                connection = re.match(r'\s*,?\s*\.(\w+)\s*\(', body[offset:])
                if connection is None:
                    assert not body[offset:].strip(), body[offset:]
                    break
                opening = offset + connection.end() - 1
                closing = balanced(body, opening)
                assert connection[1] not in connections
                connections[connection[1]] = body[opening + 1:closing].strip()
                offset = closing + 1
            return match.start(), stop, source[parameter_start + 1:parameter_end], connections
    raise ValueError((module, name, 'instance missing'))


def header_end(source, module):
    match = re.search(r'\bmodule\s+' + re.escape(module) + r'\s*#\(', source)
    parameter_end = balanced(source, source.index('(', match.start()))
    return balanced(source, source.index('(', parameter_end + 1))


def add_ports(source, module, extra):
    end = header_end(source, module)
    return source[:end] + ',\n' + ',\n'.join(
        f'    {direction} wire {width} {name}' for direction, width, name in extra) + '\n' + source[end:]


def rename(source, old, new):
    return re.sub(r'\bmodule\s+' + re.escape(old) + r'\b', 'module ' + new, source, count=1)


def emit(name, source):
    source = source.replace('`default_nettype none',
        '`default_nettype none\n// Generated logical partition. Physical transport is not implemented here.', 1)
    path = source_path(ROOT, Path('rtl') / (name + '.v'))
    path.write_text(source)
    generated[source_relative(path, ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()


def named_instance(module, params, name, connections):
    return f'{module} #({params}) {name}(\n' + ',\n'.join(
        f'    .{key}({value})' for key, value in connections.items()) + '\n);'


def propagate(source, module, new_module, child, child_name, new_child, extra):
    start, end, params, connections = instance(source, child, child_name)
    assert not (set(connections) & {p[2] for p in extra})
    connections.update({name: name for _, _, name in extra})
    source = source[:start] + named_instance(new_child, params, child_name, connections) + source[end:]
    source = add_ports(source, module, extra)
    return rename(source, module, new_module)


def opposite(direction):
    return 'input' if direction == 'output' else 'output'


def main():
    # Forward engines move together. Their 32-bit token stream stays local.
    source = read('grpc_prefill_datapath')
    extra_f = []
    tokenizer_instances = []
    internal = dict(s_token='token_data', s_keep="token_keep==4'hf", s_valid='token_valid',
                    s_ready='token_ready', s_sequence_last='token_last', s_user='token_user')
    token_wires = dict(m_axis_tokens_tdata='token_data', m_axis_tokens_tkeep='token_keep',
                       m_axis_tokens_tvalid='token_valid', m_axis_tokens_tready='token_ready',
                       m_axis_tokens_tlast='token_last', m_axis_tokens_tuser='token_user')
    for child, child_name, prefix in [('bpe_tokenizer_engine', 'tokenizer', 'bpe'),
                                       ('token_packager', 'packager', 'pack')]:
        start, end, params, connections = instance(source, child, child_name)
        remote = {}
        assignments = []
        for direction, width, name in ports(read(child), child):
            expression = connections[name]
            if name in ('clk', 'rst'):
                remote[name] = name
            elif name in MEMORY:
                bits, _ = MEMORY[name]
                remote[name] = f'{name}[0+:{8}*{bits}]'
                if direction == 'output':
                    assignments.append(f'assign {expression}=0;')
            elif child_name == 'tokenizer' and name in token_wires:
                remote[name] = token_wires[name]
            elif child_name == 'packager' and name in internal:
                remote[name] = internal[name]
            elif child_name == 'packager' and name.startswith('m_axis_tokens_'):
                remote[name] = name
                if direction == 'output':
                    assignments.append(f'assign {expression}=0;')
            else:
                boundary = 'link_f_' + prefix + '_' + name
                extra_f.append((opposite(direction), width, boundary))
                remote[name] = boundary
                assignments.append(f'assign {boundary}={expression};' if direction == 'input'
                                   else f'assign {expression}={boundary};')
        source = source[:start] + '\n'.join(assignments) + source[end:]
        tokenizer_instances.append(named_instance(child, params, child_name, remote))
    source = add_ports(source, 'grpc_prefill_datapath', extra_f)
    source = rename(source, 'grpc_prefill_datapath', 'grpc_prefill_parser_partition')
    emit('grpc_prefill_parser_partition', source)
    forward = propagate(read('http2_grpc_prefill'), 'http2_grpc_prefill', 'http2_parser_transport_partition',
                        'grpc_prefill_datapath', 'prefill', 'grpc_prefill_parser_partition', extra_f)
    emit('http2_parser_transport_partition', forward)

    # Guarded inverse lookup/control move to Tokenizer. UTF-8/carry handling
    # and serialization stay on Parser, using the existing start/result fence.
    source = read('generated_response_chunk')
    start, end, serializer_params, serializer_connections = instance(source, 'utf8_serialized_chunk', 'response')
    serializer_remote = {}
    extra_s = []
    assignments = []
    for direction, width, name in ports(read('utf8_serialized_chunk'), 'utf8_serialized_chunk'):
        expression = serializer_connections[name]
        if name in ('clk', 'rst') or name.startswith('m_axis_tx_'):
            serializer_remote[name] = name
        elif expression:
            boundary = 'link_s_' + name
            extra_s.append((opposite(direction), width, boundary))
            serializer_remote[name] = boundary
            assignments.append(f'assign {boundary}={expression};' if direction == 'input'
                               else f'assign {expression}={boundary};')
        else:
            serializer_remote[name] = ''
    source = source[:start] + '\n'.join(assignments) + source[end:]
    source = add_ports(source, 'generated_response_chunk', extra_s)
    source = rename(source, 'generated_response_chunk', 'inverse_tokenizer_partition')
    # TX belongs to the Parser's serializer, so this remote child has no TX ports.
    for direction, width, name in ports(read('generated_response_chunk'), 'generated_response_chunk'):
        if name.startswith('m_axis_tx_'):
            source = re.sub(r'\b' + direction + r'\s+wire\s*' + re.escape(width) + r'\s*' + name + r'\s*,', '', source, count=1)
    emit('inverse_tokenizer_partition', source)

    source = read('rpc_generated_response')
    start, end, inverse_params, connections = instance(source, 'generated_response_chunk', 'response')
    extra_r = []
    inverse_remote = {}
    assignments = []
    mem_map = dict(mem_rd_valid='mem_valid[8]', mem_rd_ready='mem_ready[8]',
                   mem_rd_addr='mem_addr[8*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]', mem_rd_bytes='mem_bytes[32+:4]',
                   mem_rsp_valid='mem_rsp_valid[8]', mem_rsp_ready='mem_rsp_ready[8]',
                   mem_rsp_data='mem_rsp_data[576+:72]', mem_rsp_status='mem_rsp_status[64+:8]')
    for direction, width, name in ports(read('generated_response_chunk'), 'generated_response_chunk'):
        expression = connections[name]
        if name in ('clk', 'rst'):
            inverse_remote[name] = name
        elif name.startswith('m_axis_tx_'):
            if direction == 'output':
                assignments.append(f'assign {expression}=0;')
        elif name.startswith('mem_'):
            inverse_remote[name] = mem_map[name]
            if direction == 'output':
                assignments.append(f'assign {expression}=0;')
        elif expression:
            boundary = 'link_r_' + name
            extra_r.append((opposite(direction), width, boundary))
            inverse_remote[name] = boundary
            assignments.append(f'assign {boundary}={expression};' if direction == 'input'
                               else f'assign {expression}={boundary};')
        else:
            inverse_remote[name] = ''
    source = source[:start] + '\n'.join(assignments) + source[end:]
    # The serializer is local to Parser. Preserve the RPC controller's durable
    # "bytes escaped" witness without returning the whole TX stream via Tokenizer.
    source = source.replace('if(m_axis_tx_tvalid&&m_axis_tx_tready)result_tx_emitted<=1;',
                            'if(local_tx_accepted)result_tx_emitted<=1;')
    source = add_ports(source, 'rpc_generated_response', extra_r + [('input', '', 'local_tx_accepted')])
    source = rename(source, 'rpc_generated_response', 'rpc_response_parser_partition')
    emit('rpc_response_parser_partition', source)

    parser = propagate(read('http2_bidirectional_application'), 'http2_bidirectional_application', 'http2_parser_partition_core',
                       'http2_grpc_prefill', 'forward', 'http2_parser_transport_partition', extra_f)
    parser = propagate(parser, 'http2_parser_partition_core', 'http2_parser_partition_core',
                       'rpc_generated_response', 'reverse', 'rpc_response_parser_partition', extra_r)
    parser_s = [(opposite(direction), width, name) for direction, width, name in extra_s]
    parser = add_ports(parser, 'http2_parser_partition_core', parser_s)
    start, end, params, connections = instance(parser, 'rpc_response_parser_partition', 'reverse')
    connections['local_tx_accepted'] = 'm_axis_tx_tvalid&&m_axis_tx_tready'
    for name in connections:
        if name.startswith('m_axis_tx_'):
            connections[name] = name if name.endswith('tready') else ''
    parser = parser[:start] + named_instance('rpc_response_parser_partition', params, 'reverse', connections) + parser[end:]
    parser = parser.replace('endmodule', named_instance('utf8_serialized_chunk', serializer_params, 'response_serializer', serializer_remote) + '\nendmodule')
    emit('http2_parser_partition_core', parser)

    # Compact the Parser's actual memory clients; engine clients never leave
    # the Tokenizer as memory transactions. Host token data belongs there too.
    original_ports = ports(read('http2_bidirectional_application'), 'http2_bidirectional_application')
    parser_public = [port for port in original_ports if not port[2].startswith('m_axis_tokens_')]
    parser_public += [*extra_f, *extra_r, *parser_s]
    memory_widths = {name: f'[13*{bits}-1:0]' for name, (bits, _) in MEMORY.items()}
    parser_public = [(d, memory_widths.get(n, w), n) for d, w, n in parser_public]
    declarations = ['wire [22*' + str(bits) + '-1:0] all_' + name + ';' for name, (bits, _) in MEMORY.items()]
    kept_clients = [*range(5), *range(13, 21)]
    for compact, previous in enumerate(kept_clients):
        for name, (bits, direction) in MEMORY.items():
            a = f'all_{name}[{previous}*{bits}+:{bits}]'
            b = f'{name}[{compact}*{bits}+:{bits}]'
            declarations.append(f'assign {b}={a};' if direction == 'output' else f'assign {a}={b};')
    for previous in [*range(5, 13), 21]:
        for name, (bits, direction) in MEMORY.items():
            if direction == 'input':
                declarations.append(f'assign all_{name}[{previous}*{bits}+:{bits}]=0;')
    connections = {name: 'all_' + name if name in MEMORY else
                   "1'b0" if name == 'm_axis_tokens_tready' else '' if name.startswith('m_axis_tokens_') else name
                   for _, _, name in original_ports}
    connections.update({name: name for _, _, name in [*extra_f, *extra_r, *parser_s]})
    parameters = 'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384'
    params = '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)'
    def module(name, public, body, parameters=parameters):
        return '`timescale 1ns/1ps\n`default_nettype none\nmodule ' + name + ' #(\n' + parameters + '\n)(\n' + ',\n'.join(
            f'    {d} wire {w} {n}' for d, w, n in public) + '\n);\n' + '\n'.join(body) + '\nendmodule\n`default_nettype wire\n'
    emit('http2_parser_fpga_application', module('http2_parser_fpga_application', parser_public,
         declarations + [named_instance('http2_parser_partition_core', params, 'core', connections)]))

    token_public = [('input', '', 'clk'), ('input', '', 'rst')]
    token_public += [(opposite(d), w, n) for d, w, n in [*extra_f, *extra_r]] + extra_s
    token_public += [p for p in original_ports if p[2].startswith('m_axis_tokens_')]
    token_public += [(direction, f'[9*{bits}-1:0]', name) for name, (bits, direction) in MEMORY.items()]
    inverse_remote.update({name: name for _, _, name in extra_s})
    body = ['wire [31:0] token_data;wire [3:0] token_keep;wire token_valid,token_ready,token_last;wire [USER_WIDTH-1:0] token_user;',
            *tokenizer_instances, named_instance('inverse_tokenizer_partition', inverse_params, 'inverse', inverse_remote),
            "assign mem_write[8]=0;assign mem_data[576+:72]=0;"]
    emit('tokenizer_fpga_application', module('tokenizer_fpga_application', token_public, body))

    manifest = dict(phase='generated_logical_partitions', source_sha256=sources, generated_sha256=generated,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parser_top='http2_parser_fpga_application', tokenizer_top='tokenizer_fpga_application',
        parser_memory_clients_original=kept_clients, tokenizer_memory_clients_original=[*range(5, 13), 21],
        boundary_ports=[dict(parser_direction=d, width=w, name=n) for d, w, n in [*extra_f, *extra_r, *parser_s]],
        physical_link_implemented=False, independent_clock_domains_verified=False,
        distributed_image_leases_verified=False, full_system_complete=False)
    output = ROOT / 'build/validation/two-fpga-generated.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Generated separate Parser/Tokenizer applications: {len(extra_f)} forward, {len(extra_r)} inverse, {len(extra_s)} serializer boundary signals; 13/9 local memory clients')


if __name__ == '__main__':
    main()
