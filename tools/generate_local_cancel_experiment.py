"""Cancel scoped credit-parked returns using real freeze and fatal send close."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_bidirectional_application import ports
from generate_receive_pool_experiment import replace
from generate_two_fpga_application import add_ports, instance, named_instance

from rtl_paths import source_path, source_relative


CLOSING = [('input', '', 'connection_closing_valid'), ('input', '[USER_WIDTH-1:0]', 'connection_closing_user')]
CLOSING += [('input', w, 'connection_closing_' + n) for n, w in (
    ('context_base', '[MEMORY_ADDR_WIDTH-1:0]'), ('context_bytes', '[MEMORY_ADDR_WIDTH:0]'),
    ('stream_base', '[MEMORY_ADDR_WIDTH-1:0]'), ('stream_bytes', '[MEMORY_ADDR_WIDTH:0]'),
    ('window_base', '[MEMORY_ADDR_WIDTH-1:0]'), ('window_bytes', '[MEMORY_ADDR_WIDTH:0]'), ('work_floor', '[MEMORY_ADDR_WIDTH-1:0]'))]


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/local-error'
    folder = root / 'build/experiments/local-cancel'
    target = folder / 'rtl'
    target.mkdir(parents=True, exist_ok=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {}
    for p in (previous / 'rtl').glob('*.v'):
        shutil.copy2(p, target / p.name)
        inputs[source_relative(p, root).as_posix()] = sha(p)

    def read(name):
        p = previous / 'rtl' / (name + '.v')
        if not p.exists():
            p = source_path(root, Path('rtl') / (name + '.v'))
        inputs[source_relative(p, root).as_posix()] = sha(p)
        return p.read_text()

    def emit(name, text):
        (target / (name + '.v')).write_text(text)

    def connect(text, child, inst, extra, params_prefix=''):
        a, b, params, c = instance(text, child, inst)
        c.update(extra)
        return text[:a] + named_instance(child, params_prefix + params, inst, c) + text[b:]

    def feature(text, name):
        return replace(text, 'module ' + name + ' #(', 'module ' + name + ' #(parameter integer ENABLE_LOCAL_FATAL=0,')

    name = 'http2_pipelined_cancel_window_store'
    text = feature(add_ports(read(name), name, [('input', '', 'req_connection_closing')]), name)
    text = replace(text, 'CLOSE_SEND_KEY=10;', 'CLOSE_SEND_KEY=10,FATAL_CLOSE_SEND_KEY=11;')
    text = re.sub(r'\bop==CLOSE_SEND_KEY\b', '(op==CLOSE_SEND_KEY||op==FATAL_CLOSE_SEND_KEY)', text)
    text = text.replace('op!=CLOSE_SEND_KEY', 'op!=CLOSE_SEND_KEY&&op!=FATAL_CLOSE_SEND_KEY')
    text = replace(text, 'if(op>CLOSE_SEND_KEY)', 'if(op>(ENABLE_LOCAL_FATAL?FATAL_CLOSE_SEND_KEY:CLOSE_SEND_KEY))')
    text = replace(text, 'reg authority,maintenance,scanning,after_write_scan;', 'reg authority,maintenance,scanning,after_write_scan,closing_authority;')
    text = replace(text, 'authority<=0;maintenance<=0;', 'authority<=0;closing_authority<=0;maintenance<=0;')
    text = replace(text, 'authority<=req_authority;', 'authority<=req_authority;closing_authority<=ENABLE_LOCAL_FATAL&&req_connection_closing;')
    text = replace(text, 'else if(!authority)finish_error(7,1,2,1);',
        'else if(!authority)finish_error(7,1,2,1);\n                else if(op==FATAL_CLOSE_SEND_KEY&&!closing_authority)finish_error(7,14,2,1);')
    text = replace(text, 'raw_header[31:0]!=RAW_MAGIC||!raw_header[32]',
        '(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])&&!(closing_authority&&raw_header==0&&(op==FATAL_CLOSE_SEND_KEY||op==RESERVE))')
    text = replace(text, 'else if(op==RESERVE)begin\n',
        'else if(op==RESERVE&&closing_authority)finish_error(7,14,2,1);\n                else if(op==RESERVE)begin\n')
    emit(name, text)
    name = 'http2_owned_pipelined_cancel_windows'
    text = feature(add_ports(read(name), name, CLOSING), name)
    text = connect(text, 'http2_pipelined_cancel_window_store', 'windows', {'req_connection_closing':'saved_req_connection_closing'}, '.ENABLE_LOCAL_FATAL(ENABLE_LOCAL_FATAL),')
    capture = 'ENABLE_LOCAL_FATAL&&connection_closing_valid&&window_req_user==connection_closing_user&&' + '&&'.join(
        'window_cfg_' + n + '==connection_closing_' + n for n in ('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'))
    text = replace(text, 'if(rst)begin state<=IDLE;', 'if(rst)begin saved_req_connection_closing<=0;state<=IDLE;')
    text = replace(text, 'IDLE:if(window_req_valid&&window_req_ready)begin',
        'IDLE:if(window_req_valid&&window_req_ready)begin\n            saved_req_connection_closing<=' + capture + ';')
    emit(name, replace(text, 'endmodule\n', 'reg saved_req_connection_closing;\nendmodule\n'))
    name = 'http2_enveloped_frame_grants'
    text = feature(add_ports(read(name), name, CLOSING), name)
    text = connect(text, 'http2_owned_pipelined_cancel_windows', 'owned', {n:n for _,_,n in CLOSING}, '.ENABLE_LOCAL_FATAL(ENABLE_LOCAL_FATAL),')
    text = replace(text, 'window_req_op==8||window_req_op==10;', 'window_req_op==8||window_req_op==10||window_req_op==11;')
    text = replace(text, 'owned_window_rsp_op==9||owned_window_rsp_op==10)', 'owned_window_rsp_op==9||owned_window_rsp_op==10||owned_window_rsp_op==11)')
    emit(name, text)
    name = 'rpc_grpc_http2_return'
    text = feature(add_ports(read(name), name, CLOSING), name)
    text = connect(text, 'http2_enveloped_frame_grants', 'directory_service', {n:n for _,_,n in CLOSING}, '.ENABLE_LOCAL_FATAL(ENABLE_LOCAL_FATAL),')
    text = replace(text, 'window_req_op==8||window_req_op==10)', 'window_req_op==8||window_req_op==10||window_req_op==11)')
    emit(name, text)
    name = 'http2_enveloped_parser_core'
    text = read(name)
    declarations = []
    closing = dict(connection_closing_valid='receive_connection_closing&&(window_owner==0||window_owner==9)', connection_closing_user='receive_connection_user',
        connection_closing_context_base='receive_connection_context_base', connection_closing_context_bytes='receive_connection_context_bytes',
        connection_closing_stream_base='receive_connection_rpc_base', connection_closing_stream_bytes='receive_connection_rpc_bytes',
        connection_closing_window_base='active_window_base', connection_closing_window_bytes='active_window_bytes', connection_closing_work_floor='ctl_cfg_work_floor')
    a, b, params, r = instance(text, 'rpc_grpc_http2_return', 'reverse')
    r.update(closing)
    freeze = {}
    for n in ('freeze_valid','freeze_ready','freeze_user','freeze_stream','freeze_active','freeze_drained','freeze_binding_valid',
              'freeze_record_address','freeze_generation','freeze_release_valid','freeze_release_ready'):
        freeze[n] = r[n]
        r[n] = 'local_shared_' + n
        w = next(w for _,w,p in ports(read('rpc_grpc_http2_return'), 'rpc_grpc_http2_return') if p==n)
        declarations.append('wire ' + w + ' ' + r[n] + ';')
    freeze_cfg = {}
    for n in ('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'):
        p = 'freeze_cfg_' + n
        freeze_cfg[n] = r[p]
        r[p] = '(local_freeze_owner==1?' + r[p] + ':local_abort_owned_' + n + ')'
    text = text[:a] + named_instance('rpc_grpc_http2_return', '.ENABLE_LOCAL_FATAL(1),' + params, 'reverse', r) + text[b:]
    text = replace(text, 'assign idle=local_error_idle&&', 'assign idle=local_abort_idle&&local_error_idle&&')
    text = replace(text, 'wire local_error_fence=local_error_started||', 'wire local_error_fence=local_abort_busy||local_abort_recovery_required||local_error_started||')
    text = replace(text, 'receive_wire_idle&&(tx_idle||response_recovery_required)&&!shutdown_busy&&!cancel_valid;',
        'receive_wire_idle&&(tx_idle||response_recovery_required)&&!shutdown_busy&&!cancel_valid&&(!local_abort_busy||local_abort_recovery_required);')
    text = replace(text, 'wire shutdown_window_send=window_owner==7;', 'wire local_abort_window_send=window_owner==9;\nwire shutdown_window_send=window_owner==7;')
    text = replace(text, '0:if(init_window_req_valid)window_owner<=1;', '0:if(local_abort_window_valid)window_owner<=9;else if(init_window_req_valid)window_owner<=1;')
    text = replace(text, 'else if(window_req_valid&&!shutdown_recovery_required&&!response_recovery_required)window_owner<=3;',
        'else if(window_req_valid&&!local_error_fence&&!shutdown_recovery_required&&!response_recovery_required)window_owner<=3;')
    text = replace(text, '        default:window_owner<=0;endcase end',
        '        9:if(local_abort_window_valid&&service_window_req_ready)window_owner<=10;\n        10:if(service_window_rsp_valid&&local_abort_window_rsp_ready)window_owner<=0;\n        default:window_owner<=0;endcase end')
    text = replace(text, 'assign service_window_req_valid=', 'assign service_window_req_valid=local_abort_window_send?local_abort_window_valid:')
    text = replace(text, 'assign service_window_rsp_ready=', 'assign service_window_rsp_ready=window_owner==10?local_abort_window_rsp_ready:')
    for n, value in dict(op="4'd11", maintenance="1'b0", user='local_abort_owned_user', stream='local_abort_owned_stream', generation='0', record_address='0', amount='0').items():
        text = replace(text, 'assign service_window_req_' + n + '=', 'assign service_window_req_' + n + '=local_abort_window_send?' + value + ':')
    for n in ('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'):
        text = replace(text, 'assign service_window_cfg_' + n + '=',
            'assign service_window_cfg_' + n + '=local_abort_window_send?local_abort_owned_' + n + ':')
    f = dict(receive_fault_valid='receive_fault_valid||local_abort_recovery_required', receive_fault_http2_error="local_abort_recovery_required?32'd2:receive_fault_http2_error")
    for suffix in ('status','detail','memory_status'):
        f['receive_fault_' + suffix] = 'local_abort_recovery_required?local_abort_' + suffix + ':receive_fault_' + suffix
    text = connect(text, 'http2_classified_parser_transport', 'forward', f)
    control = read('http2_local_return_abort')
    c = {}
    for d, w, n in ports(control, 'http2_local_return_abort'):
        if n in ('clk','rst','return_pending'):
            c[n] = n
        elif n == 'req_valid':
            c[n] = 'receive_connection_closing&&return_pending&&credit_parked&&local_return_scope_match&&!shutdown_busy&&!cancel_valid'
        elif n == 'req_authority':
            c[n] = 'receive_connection_closing&&local_return_scope_match'
        elif n in ('req_user','req_stream'):
            c[n] = 'return_' + n[4:]
        elif n.startswith('cfg_'):
            c[n] = 'return_scope_' + n[4:]
        elif n.startswith('window_rsp_') and n not in ('window_rsp_ready','window_rsp_valid'):
            c[n] = 'service_' + n
        elif n == 'frame_tracking_error':
            c[n] = 'shutdown_return_frame_tracking_error'
        else:
            c[n] = 'local_abort_' + n
            declarations.append('wire ' + w + ' ' + c[n] + ';')
    declarations.append(named_instance('http2_local_return_abort', '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', 'local_return_abort', c))
    body = '''
wire local_return_scope_match=return_user==receive_connection_user&&return_scope_context_base==receive_connection_context_base&&
    return_scope_context_bytes==receive_connection_context_bytes&&return_scope_stream_base==receive_connection_rpc_base&&
    return_scope_stream_bytes==receive_connection_rpc_bytes&&return_scope_window_base==active_window_base&&
    return_scope_window_bytes==active_window_bytes&&return_scope_work_floor==ctl_cfg_work_floor;
assign local_abort_window_ready=local_abort_window_send&&service_window_req_ready;
assign local_abort_window_rsp_valid=window_owner==10&&service_window_rsp_valid;
reg [1:0] local_freeze_owner;reg local_freeze_granted;
always @(posedge clk)begin
    if(rst)begin local_freeze_owner<=0;local_freeze_granted<=0;end
    else if(local_freeze_owner==0)begin
        if(A_VALID)local_freeze_owner<=1;
        else if(local_abort_freeze_valid)local_freeze_owner<=2;
    end else begin
        if(local_shared_freeze_valid&&local_shared_freeze_ready)local_freeze_granted<=1;
        if(local_shared_freeze_release_valid&&local_shared_freeze_release_ready)begin local_freeze_owner<=0;local_freeze_granted<=0;end
    end
end
assign local_shared_freeze_valid=!local_freeze_granted&&(local_freeze_owner==1?A_VALID:local_freeze_owner==2&&local_abort_freeze_valid);
assign A_READY=local_freeze_owner==1&&!local_freeze_granted&&local_shared_freeze_ready;
assign local_abort_freeze_ready=local_freeze_owner==2&&!local_freeze_granted&&local_shared_freeze_ready;
assign local_shared_freeze_user=local_freeze_owner==1?A_USER:local_abort_freeze_user;
assign local_shared_freeze_stream=local_freeze_owner==1?A_STREAM:local_abort_freeze_stream;
assign A_ACTIVE=local_freeze_owner==1&&local_freeze_granted&&local_shared_freeze_active;
assign A_DRAINED=local_freeze_owner==1&&local_freeze_granted&&local_shared_freeze_drained;
assign local_abort_freeze_drained=local_freeze_owner==2&&local_freeze_granted&&local_shared_freeze_drained;
assign A_BINDING=local_freeze_owner==1&&local_freeze_granted&&local_shared_freeze_binding_valid;
assign local_abort_freeze_binding_valid=local_freeze_owner==2&&local_freeze_granted&&local_shared_freeze_binding_valid;
assign A_ADDRESS=local_shared_freeze_record_address;assign local_abort_freeze_record_address=local_shared_freeze_record_address;
assign A_GENERATION=local_shared_freeze_generation;assign local_abort_freeze_generation=local_shared_freeze_generation;
assign local_shared_freeze_release_valid=local_freeze_granted&&(local_freeze_owner==1?A_RELEASE:local_abort_freeze_release_valid);
assign A_RELEASE_READY=local_freeze_owner==1&&local_freeze_granted&&local_shared_freeze_release_ready;
assign local_abort_freeze_release_ready=local_freeze_owner==2&&local_freeze_granted&&local_shared_freeze_release_ready;
'''
    for key, port in dict(VALID='freeze_valid',READY='freeze_ready',USER='freeze_user',STREAM='freeze_stream',ACTIVE='freeze_active',
        DRAINED='freeze_drained',BINDING='freeze_binding_valid',ADDRESS='freeze_record_address',GENERATION='freeze_generation',
        RELEASE_READY='freeze_release_ready',RELEASE='freeze_release_valid').items():
        body = re.sub(r'\bA_' + key + r'\b', freeze[port], body)
    declarations.append(body)
    emit(name, replace(text, 'endmodule\n', '\n'.join(declarations) + '\nendmodule\n'))
    sim = folder / 'sim'
    sim.mkdir(exist_ok=True)
    for p in (previous / 'sim').rglob('*'):
        if p.is_file():
            dest = sim / p.relative_to(previous / 'sim')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            inputs[source_relative(p, root).as_posix()] = sha(p)
    held = sim / 'held-trailer/test_raw_grpc_duplex.py'
    held.parent.mkdir(exist_ok=True)
    shutil.copy2(sim / 'test_raw_grpc_duplex.py', held)
    test = root / 'sim/cocotb/test_local_error_credit_stall.py'
    inputs[source_relative(test, root).as_posix()] = sha(test)
    shutil.copy2(test, sim / 'test_raw_grpc_duplex.py')
    for phase in range(14):
        destination = sim / ('close-fault-' + str(phase)) / 'test_raw_grpc_duplex.py'
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(replace(test.read_text(), 'FAULT_TARGET = None', 'FAULT_TARGET = ' + str(phase)))
    interleaved = root / 'sim/cocotb/test_receive_pool_interleaved.py'
    inputs[source_relative(interleaved, root).as_posix()] = sha(interleaved)
    destination = sim / 'interleaved/test_raw_grpc_duplex.py'
    destination.parent.mkdir(exist_ok=True)
    shutil.copy2(interleaved, destination)
    workload = root / 'sim/cocotb/test_raw_grpc_workload.py'
    inputs[source_relative(workload, root).as_posix()] = sha(workload)
    text = replace(workload.read_text(), 'import cocotb\n', 'import cocotb\nfrom receive_pool_witness import observe_receive_pool,pool_counts\n')
    text = replace(text, '    await cycles(d,5);b.set(rst=0)',
        '    pool=pool_counts();cocotb.start_soon(observe_receive_pool(d,pool))\n    await cycles(d,5);b.set(rst=0)')
    text = replace(text, 'parser_memory_clients=17,', 'parser_memory_clients=len(d.p_mem_valid),')
    text = replace(text, "    Path('acceptance.json').write_text", "    assert pool['receive_grants']==pool['receive_unlocks'] and pool['receive_grants']>0\n    assert pool['receive_memory_commands']==pool['receive_memory_acks']\n    accepted['actual_receive_pool_ownership']=pool\n    Path('acceptance.json').write_text")
    (sim / 'test_raw_grpc_workload.py').write_text(text)
    report = dict(phase='scoped_local_credit_wait_cancel_generated', input_sha256=inputs,
        generator_sha256=sha(Path(__file__)), generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        sim_sha256={p.relative_to(sim).as_posix():sha(p) for p in sim.rglob('*') if p.is_file()},
        actual_pool_owned_fatal_close=True, actual_freeze_ownership_arbiter=True,
        synthetic_credit_error=False, actual_runtime_verified=False, full_system_complete=False)
    (folder / 'generation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
