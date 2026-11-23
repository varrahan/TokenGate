"""Join automatic connection/stream windows to the actual shared return service.

Raw control commit/ACK scheduling remains external. Preserve the original raw
controlled application and all existing standalone return variants.
"""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import MEMORY, add_ports, instance, named_instance, rename


def main():
    root = Path(__file__).resolve().parents[1]; inputs = {}; outputs = {}
    def read(name):
        path = root / ('rtl/' + name + '.v'); inputs[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text()
    def emit(name, source):
        path = root / ('rtl/' + name + '.v'); path.write_text(source)
        outputs[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()

    address = '[MEMORY_ADDR_WIDTH-1:0]'; capacity = '[MEMORY_ADDR_WIDTH:0]'
    callback = [('output', '', 'init_window_req_valid'), ('input', '', 'init_window_req_ready'),
        ('output', '[3:0]', 'init_window_req_op'), ('output', '', 'init_window_req_maintenance'),
        ('output', '[USER_WIDTH-1:0]', 'init_window_req_user'), ('output', '[30:0]', 'init_window_req_stream'),
        ('output', '[31:0]', 'init_window_req_generation'), ('output', address, 'init_window_req_record_address'),
        ('output', '[31:0]', 'init_window_req_amount'), ('input', '', 'init_window_rsp_valid'),
        ('output', '', 'init_window_rsp_ready'), ('input', '[7:0]', 'init_window_rsp_status'),
        ('input', '[7:0]', 'init_window_rsp_detail'), ('input', '[7:0]', 'init_window_rsp_memory_status'),
        ('input', '', 'init_window_recovery_required'), ('input', address, 'init_window_recovery_address')]
    callback += [('output', address, 'init_window_cfg_' + n) for n in ('context_base', 'stream_base', 'window_base', 'work_floor')]
    callback += [('output', capacity, 'init_window_cfg_' + n) for n in ('context_bytes', 'stream_bytes', 'window_bytes')]
    extra = [('input', address, 'cfg_window_base'), ('input', capacity, 'cfg_window_bytes'),
        ('output', '[7:0]', 'header_window_status'), ('output', '[7:0]', 'command_window_status'),
        ('output', '[7:0]', 'command_window_cleanup_status')]
    source = read('http2_controlled_parser_transport')
    source = add_ports(source, 'http2_controlled_parser_transport', extra + callback)
    start, end, params, child = instance(source, 'http2_rpc_admission', 'admission')
    old = {n for _, _, n in ports(read('http2_rpc_admission'), 'http2_rpc_admission')}
    leaf = ports(read('http2_windowed_rpc_admission'), 'http2_windowed_rpc_admission')
    wires = []
    for direction, width, name in leaf:
        if name in old: continue
        if name.startswith('control_pool_'): child[name] = ''
        elif name.startswith('cfg_window_'): child[name] = 'owned_' + name
        elif name == 'result_window_status': child[name] = 'header_window_status'
        else:
            child[name] = 'a_' + name; wires.append(f'wire {width} a_{name};')
    source = source[:start] + '\n'.join(wires) + '\n' + named_instance('http2_windowed_rpc_admission', params, 'admission', child) + source[end:]
    source = rename(source, 'http2_controlled_parser_transport', 'http2_initialized_parser_transport')
    changes = (
        ('reg [1:0] saved_command_op;',
         'reg [MEMORY_ADDR_WIDTH-1:0] owned_cfg_window_base;reg [MEMORY_ADDR_WIDTH:0] owned_cfg_window_bytes;\n'
         '    reg [7:0] window_command_status,window_command_detail,window_command_memory,window_command_cleanup;\n'
         '    reg [1:0] saved_command_op;'),
        ("assign r_command_op=state==CLOSE_SEND?2'd1:saved_command_op;",
         "assign r_command_op=(state==CLOSE_SEND||state==WINDOW_CLOSE_SEND)?2'd1:saved_command_op;"),
        ('CLOSE_SEND=13,CLOSE_WAIT=14;\n    reg [3:0] state;',
         'CLOSE_SEND=13,CLOSE_WAIT=14,WINDOW_OPEN_REQ=15,WINDOW_OPEN_WAIT=16,WINDOW_OPEN_RESULT=17,WINDOW_CLOSE_SEND=18,WINDOW_CLOSE_WAIT=19;\n    reg [4:0] state;'),
        ('assign r_command_valid=state==COMMAND_SEND||state==CLOSE_SEND;',
         'assign r_command_valid=state==COMMAND_SEND||state==CLOSE_SEND||state==WINDOW_CLOSE_SEND;'),
        ('assign rsp_valid=state==COMMAND_WAIT&&r_rsp_valid||state==COMMAND_FAILED;',
         'assign rsp_valid=state==COMMAND_WAIT&&r_rsp_valid&&!(saved_command_op==0&&r_rsp_status==0)||state==COMMAND_FAILED||state==WINDOW_OPEN_RESULT;'),
        ("assign rsp_status=state==COMMAND_FAILED?8'd8:r_rsp_status;",
         "assign rsp_status=state==WINDOW_OPEN_RESULT?(window_command_status==0?8'd0:8'd9):state==COMMAND_FAILED?8'd8:r_rsp_status;"),
        ('assign rsp_detail=state==COMMAND_FAILED?a_result_detail:r_rsp_detail;',
         'assign rsp_detail=state==WINDOW_OPEN_RESULT?window_command_detail:state==COMMAND_FAILED?a_result_detail:r_rsp_detail;'),
        ('assign rsp_memory_status=state==COMMAND_FAILED?a_result_memory_status:r_rsp_memory_status;',
         'assign rsp_memory_status=state==WINDOW_OPEN_RESULT?window_command_memory:state==COMMAND_FAILED?a_result_memory_status:r_rsp_memory_status;'),
        ('assign rsp_http2_error=state==COMMAND_FAILED?a_result_http2_error:r_rsp_http2_error;',
         "assign rsp_http2_error=state==WINDOW_OPEN_RESULT?(window_command_status==0?32'd0:32'd2):state==COMMAND_FAILED?a_result_http2_error:r_rsp_http2_error;"),
        ('assign rsp_user=state==COMMAND_FAILED?a_result_user:r_rsp_user;',
         'assign rsp_user=state==WINDOW_OPEN_RESULT?saved_command_user:state==COMMAND_FAILED?a_result_user:r_rsp_user;'),
        ('assign r_rsp_ready=state==COMMAND_WAIT?rsp_ready:state==CLOSE_WAIT||state==RUN&&!header_pending&&r_rsp_valid;',
         'assign r_rsp_ready=state==COMMAND_WAIT?(saved_command_op==0&&r_rsp_status==0||rsp_ready):state==WINDOW_CLOSE_WAIT||state==CLOSE_WAIT||state==RUN&&!header_pending&&r_rsp_valid;'),
        ('owned_cfg_context_base<=cfg_context_base;',
         'owned_cfg_window_base<=cfg_window_base;owned_cfg_window_bytes<=cfg_window_bytes;\n                owned_cfg_context_base<=cfg_context_base;'),
        ('state<=IDLE;first_valid<=0;',
         'state<=IDLE;owned_cfg_window_base<=0;owned_cfg_window_bytes<=0;window_command_status<=0;window_command_detail<=0;window_command_memory<=0;window_command_cleanup<=0;first_valid<=0;'),
        ('saved_command_op<=command_op;',
         'window_command_status<=0;window_command_detail<=0;window_command_memory<=0;window_command_cleanup<=0;\n                saved_command_op<=command_op;'),
        ('COMMAND_WAIT:if(r_rsp_valid&&rsp_ready)state<=IDLE;',
         'COMMAND_WAIT:if(r_rsp_valid)begin\n'
         '                    if(saved_command_op==0&&r_rsp_status==0)state<=WINDOW_OPEN_REQ;\n'
         '                    else if(rsp_ready)state<=IDLE;\n                end\n'
         '                WINDOW_OPEN_REQ:if(init_window_req_ready)state<=WINDOW_OPEN_WAIT;\n'
         '                WINDOW_OPEN_WAIT:if(init_window_rsp_valid)begin\n'
         '                    window_command_status<=init_window_rsp_status;window_command_detail<=init_window_rsp_detail;\n'
         '                    window_command_memory<=init_window_rsp_memory_status;\n'
         '                    state<=init_window_rsp_status==0?WINDOW_OPEN_RESULT:WINDOW_CLOSE_SEND;\n                end\n'
         '                WINDOW_CLOSE_SEND:if(r_command_ready)state<=WINDOW_CLOSE_WAIT;\n'
         '                WINDOW_CLOSE_WAIT:if(r_rsp_valid)begin window_command_cleanup<=r_rsp_status;state<=WINDOW_OPEN_RESULT;end\n'
         '                WINDOW_OPEN_RESULT:if(rsp_ready)state<=IDLE;'),
    )
    for before, after in changes: source = replace_once(source, before, after)
    assignments = [
        'assign command_window_status=window_command_status;assign command_window_cleanup_status=window_command_cleanup;',
        'wire boot_window=state==WINDOW_OPEN_REQ;',
        'assign init_window_req_valid=boot_window||a_init_valid;',
        'assign init_window_req_op=boot_window?4\'d0:4\'d1;',
        'assign init_window_req_maintenance=boot_window&&saved_grant;',
        'assign init_window_req_user=boot_window?saved_command_user:a_init_user;',
        'assign init_window_req_stream=boot_window?31\'d0:a_init_stream;',
        'assign init_window_req_generation=boot_window?32\'d0:a_init_generation;',
        'assign init_window_req_record_address=boot_window?0:a_init_record_address;',
        'assign init_window_req_amount=0;',
        'assign init_window_rsp_ready=state==WINDOW_OPEN_WAIT||a_init_result_ready;',
        'assign a_init_ready=!boot_window&&init_window_req_ready;',
        'assign a_init_result_valid=state!=WINDOW_OPEN_WAIT&&init_window_rsp_valid;',
        'assign a_init_status=init_window_rsp_status;assign a_init_memory_status=init_window_rsp_memory_status;',
        'assign a_init_recovery_required=init_window_recovery_required;assign a_init_recovery_address=init_window_recovery_address;']
    for name in ('context_base', 'context_bytes', 'window_base', 'window_bytes', 'work_floor'):
        assignments.append(f'assign init_window_cfg_{name}=boot_window?owned_cfg_{name}:a_init_cfg_{name};')
    for name in ('stream_base', 'stream_bytes'):
        assignments.append(f'assign init_window_cfg_{name}=boot_window?owned_{name}:a_init_cfg_{name};')
    source = source.replace('endmodule', '\n'.join(assignments) + '\nendmodule')
    emit('http2_initialized_parser_transport', source)

    # Preserve early GPU collection; only actual LOAD waits for forward quiet.
    scheduled = read('rpc_grpc_keyed_return')
    scheduled = add_ports(scheduled, 'rpc_grpc_keyed_return', [('input', '', 'lookup_admit'),
        ('output', '', 'lookup_waiting'), ('output', '', 'lookup_ready'), ('output', '', 'control_idle')])
    start, end, params, service = instance(scheduled, 'http2_keyed_frame_grants', 'directory_service')
    service.update(lease_valid='directory_valid&&lookup_admit', lease_ready='service_lease_ready')
    scheduled = scheduled[:start] + named_instance('http2_keyed_frame_grants', params, 'directory_service', service) + scheduled[end:]
    scheduled = rename(scheduled, 'rpc_grpc_keyed_return', 'rpc_grpc_initialized_return')
    scheduled = scheduled.replace('endmodule', '''wire service_lease_ready;
reg generic_pending;
assign directory_ready=service_lease_ready&&lookup_admit;
assign lookup_waiting=directory_valid;assign lookup_ready=directory_ready;
assign control_idle=!generic_pending&&!control_req_valid&&!control_rsp_valid;
always @(posedge clk)begin
    if(rst)generic_pending<=0;
    else begin
        if(control_req_valid&&control_req_ready)generic_pending<=1;
        if(control_rsp_valid&&control_rsp_ready)generic_pending<=0;
    end
end
endmodule''')
    emit('rpc_grpc_initialized_return', scheduled)

    core = read('http2_controlled_parser_core')
    original_ports = ports(core, 'http2_controlled_parser_core')
    fake = {n for _, _, n in original_ports if n.startswith('frame_req_') or n == 'frame_grant_bytes'}
    # Remove fake credit ports from the header only; the new return owns them.
    from generate_two_fpga_application import header_end
    header_stop = header_end(core, 'http2_controlled_parser_core')
    body = core[core.index(';', header_stop) + 1:]
    public = [(d, w.replace('22*', '23*') if n in MEMORY else w, n) for d, w, n in original_ports if n not in fake]
    # Some original packed widths are numeric rather than products.
    public = [(d, f'[23*{MEMORY[n][0]}-1:0]' if n in MEMORY else w, n) for d, w, n in public]
    public += extra
    start, end, params, forward = instance(body, 'http2_controlled_parser_transport', 'forward')
    forward.update({n: n for _, _, n in extra})
    forward.update({n: n for _, _, n in callback})
    body = body[:start] + named_instance('http2_initialized_parser_transport', params, 'forward', forward) + body[end:]
    start, end, params, reverse = instance(body, 'rpc_grpc_scheduled_return', 'reverse')
    old_return = ports(read('rpc_grpc_scheduled_return'), 'rpc_grpc_scheduled_return')
    new_return = ports(scheduled, 'rpc_grpc_initialized_return')
    old_names = {n for _, _, n in old_return}; core_names = {n for _, _, n in public}
    window_ports = [p for p in new_return if p[2].startswith('window_')]
    for direction, width, name in new_return:
        if name in MEMORY:
            bits = MEMORY[name][0]; reverse[name] = f'mem_{name[4:]}[20*{bits}+:3*{bits}]'; continue
        if name.startswith('window_'):
            reverse[name] = 'service_' + name
            if name not in core_names: public.append((direction, width, name)); core_names.add(name)
        elif name not in old_names:
            mapped = name if name.startswith('cfg_') or name in ('credit_parked', 'directory_pool_lock_active') else 'response_' + name
            reverse[name] = mapped
            if mapped not in core_names: public.append((direction, width, mapped)); core_names.add(mapped)
    reverse = {n: reverse[n] for _, _, n in new_return}
    for name in ('context_base', 'context_bytes', 'window_base', 'window_bytes'):
        reverse['cfg_' + name] = 'active_' + name
    body = body[:start] + named_instance('rpc_grpc_initialized_return', params, 'reverse', reverse) + body[end:]
    wire_lines = [f'wire {w} {n};' for _, w, n in callback]
    wire_lines += [f'wire {w} service_{n};' for _, w, n in window_ports]
    # Capture an arbiter owner before asserting a service request. A later
    # admission request cannot replace a held external control command.
    wire_lines += ['reg [MEMORY_ADDR_WIDTH-1:0] active_context_base,active_window_base;',
        'reg [MEMORY_ADDR_WIDTH:0] active_context_bytes,active_window_bytes;',
        'always @(posedge clk)begin',
        '    if(rst)begin active_context_base<=0;active_context_bytes<=0;active_window_base<=0;active_window_bytes<=0;end',
        '    else if(command_valid&&command_ready||s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin',
        '        active_context_base<=cfg_context_base;active_context_bytes<=cfg_context_bytes;',
        '        active_window_base<=cfg_window_base;active_window_bytes<=cfg_window_bytes;',
        '    end end', 'reg [2:0] window_owner;',
        'wire forward_window_send=window_owner==1,external_window_send=window_owner==3;',
        'assign service_window_req_valid=forward_window_send?init_window_req_valid:external_window_send&&window_req_valid;',
        'assign init_window_req_ready=forward_window_send&&service_window_req_ready;',
        'assign window_req_ready=external_window_send&&service_window_req_ready;',
        'assign init_window_rsp_valid=window_owner==2&&service_window_rsp_valid;',
        'assign window_rsp_valid=window_owner==4&&service_window_rsp_valid;',
        'assign service_window_rsp_ready=window_owner==2?init_window_rsp_ready:window_owner==4&&window_rsp_ready;',
        'assign init_window_recovery_required=service_window_recovery_required;',
        'assign init_window_recovery_address=service_window_recovery_address;',
        'always @(posedge clk)begin', '    if(rst)window_owner<=0;else case(window_owner)',
        '        0:if(init_window_req_valid)window_owner<=1;else if(window_req_valid)window_owner<=3;',
        '        1:if(init_window_req_valid&&service_window_req_ready)window_owner<=2;',
        '        2:if(service_window_rsp_valid&&init_window_rsp_ready)window_owner<=0;',
        '        3:if(window_req_valid&&service_window_req_ready)window_owner<=4;',
        '        4:if(service_window_rsp_valid&&window_rsp_ready)window_owner<=0;',
        '        default:window_owner<=0;endcase end']
    for direction, _, name in window_ports:
        if name in ('window_req_valid', 'window_req_ready', 'window_rsp_valid', 'window_rsp_ready'): continue
        if direction == 'input':
            wire_lines.append(f'assign service_{name}=forward_window_send?init_{name}:{name};')
        else:
            wire_lines.append(f'assign {name}=service_{name};')
            if name in ('window_rsp_status', 'window_rsp_detail', 'window_rsp_memory_status'):
                wire_lines.append(f'assign init_{name}=service_{name};')
    body = '\n'.join(wire_lines) + '\n' + body
    params = 'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384'
    declaration = ',\n'.join(f'{d} wire {w} {n}' for d, w, n in public)
    core = '`timescale 1ns/1ps\n`default_nettype none\nmodule http2_initialized_parser_core #(\n' + params + '\n)(\n' + declaration + '\n);\n' + body
    emit('http2_initialized_parser_core', core)
    # The original forward directory lane is unused; return owns the sole
    # directory and adds one window lane beside the existing progress client.
    kept = [*range(1, 5), *range(13, 23)]
    app_ports = [(d, f'[14*{MEMORY[n][0]}-1:0]' if n in MEMORY else w, n) for d, w, n in public if not n.startswith('m_axis_tokens_')]
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        'module http2_initialized_parser_application #(\n' + params + '\n)(\n' +
        ',\n'.join(f'{d} wire {w} {n}' for d, w, n in app_ports) + '\n);']
    for name, (bits, direction) in MEMORY.items():
        lines.append(f'wire [23*{bits}-1:0] all_{name};')
        for compact, previous in enumerate(kept):
            left = f'all_{name}[{previous}*{bits}+:{bits}]'; right = f'{name}[{compact}*{bits}+:{bits}]'
            lines.append(f'assign {right}={left};' if direction == 'output' else f'assign {left}={right};')
        if direction == 'input':
            for previous in [0, *range(5, 13)]: lines.append(f'assign all_{name}[{previous}*{bits}+:{bits}]=0;')
    connections = {n: 'all_' + n if n in MEMORY else "1'b0" if n == 'm_axis_tokens_tready'
        else '' if n.startswith('m_axis_tokens_') else n for _, _, n in public}
    lines += [named_instance('http2_initialized_parser_core', '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)', 'core', connections),
        'endmodule', '`default_nettype wire', '']
    emit('http2_initialized_parser_application', '\n'.join(lines))
    result = dict(phase='generated_actual_initialized_parser_join', input_sha256=inputs,
        generated_sha256=outputs, generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parser_memory_clients=14, original_client_mapping=kept, automatic_connection_and_stream_init=True,
        raw_control_commit_integrated=False, full_system_complete=False)
    (root / 'build/validation/http2-initialized-parser-generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Generated actual raw OPEN/admission + shared durable-return window service, fourteen Parser clients')


if __name__ == '__main__':
    main()
