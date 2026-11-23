"""Join actual failed packets, connection history, GOAWAY and host close ACK."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_bidirectional_application import ports
from generate_receive_pool_experiment import replace
from generate_two_fpga_application import add_ports, instance, named_instance, MEMORY

from rtl_paths import source_path, source_relative


CLOSE = [('output', '', 'transport_close_valid'), ('input', '', 'transport_close_ready'),
    ('output', '[USER_WIDTH-1:0]', 'transport_close_user'),
    ('output', '[31:0]', 'transport_close_http2_error'), ('output', '[30:0]', 'transport_close_last_stream'),
    ('output', '[7:0]', 'transport_close_status'), ('output', '[7:0]', 'transport_close_detail'),
    ('output', '[7:0]', 'transport_close_memory_status')]


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/receive-fatal'
    folder = root / 'build/experiments/local-error'
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

    def connect(text, child, inst, extra):
        a, b, params, c = instance(text, child, inst)
        c.update(extra)
        return text[:a] + named_instance(child, params, inst, c) + text[b:]

    def extend(text, old, new):
        return re.sub(r'\[' + str(old) + r'\*([^\]]+)-1:0\]', '[' + str(new) + r'*\1-1:0]', text)

    name = 'http2_classified_parser_transport'
    text = add_ports(read(name), name, [('input', '', 'connection_failure_drained')])
    text = replace(text, 'assign p_prepare_valid=state==PREPARE;',
        'assign p_prepare_valid=state==PREPARE&&(!packet_fatal&&!receive_fault_valid&&!control_early_failed||connection_failure_drained);')
    text = replace(text, 'PREPARE:if(p_prepare_ready)state<=PREPARED;', 'PREPARE:if(p_prepare_valid&&p_prepare_ready)state<=PREPARED;')
    emit(name, text)
    name = 'http2_enveloped_parser_core'
    text = extend(add_ports(read(name), name, CLOSE), 27, 28)
    additions = []
    fields = [('valid', ''), ('ready', ''), ('committed', ''), ('status', '[7:0]'), ('detail', '[7:0]'),
        ('memory_status', '[7:0]'), ('user', '[USER_WIDTH-1:0]'), ('tag', '[31:0]')]
    binding = {}
    for n, w in fields:
        public = 'packet_result_' + n if n in ('valid', 'ready') else 'packet_' + n
        binding[public] = 'local_packet_' + n
        additions.append('wire ' + w + ' local_packet_' + n + ';')
    text = connect(text, 'http2_classified_parser_transport', 'forward', binding)
    text = connect(text, 'http2_classified_parser_transport', 'forward', {'connection_failure_drained':'local_error_drained'})
    text = replace(text, 'wire allow_new_rx=!receive_recovery_required&&', 'wire allow_new_rx=!local_error_fence&&!receive_recovery_required&&')
    text = replace(text, 'wire allow_config=!return_pending&&', 'wire allow_config=!local_error_fence&&!return_pending&&')
    text = replace(text, 'reverse_new_admit&&!cancel_valid&&', 'reverse_new_admit&&!local_error_fence&&!cancel_valid&&')
    text = replace(text, 'shutdown_control_offered||(!cancel_valid&&', 'shutdown_control_offered||(!local_error_fence&&!cancel_valid&&')
    text = replace(text, 'assign idle=receive_pool_gate_idle&&', 'assign idle=local_error_idle&&local_error_wire_idle&&receive_pool_gate_idle&&')
    # Preserve every already offered ordinary beat. Error TX starts only after
    # the actual existing response and outer receive wire owners are drained.
    a, b, params, c = instance(text, 'axis_frame_arbiter', 'receive_wire')
    for n in c:
        if n.startswith('m_axis_'):
            c[n] = 'pre_error_' + c[n]
    text = text[:a] + named_instance('axis_frame_arbiter', params, 'receive_wire', c) + text[b:]
    for prefix in ('pre_error_', 'local_error_'):
        for n, w in [('tdata', '[511:0]'), ('tkeep', '[63:0]'), ('tvalid', ''), ('tready', ''), ('tlast', ''), ('tuser', '[USER_WIDTH-1:0]')]:
            additions.append('wire ' + w + ' ' + prefix + 'm_axis_tx_' + n + ';')
    additions.append('''
wire local_error_idle,local_error_wire_idle,local_error_busy,local_error_rsp_valid,local_error_rsp_ready,local_error_req_ready;
wire [7:0] local_error_status,local_error_detail,local_error_memory_status;
reg local_error_started;
wire local_error_needed=local_packet_valid&&!local_packet_committed&&transport_packet_http2_error!=0&&
    local_packet_memory_status==0&&transport_packet_memory_status==0&&packet_control_memory_status==0&&
    !receive_recovery_required&&!response_recovery_required&&!journal_recovery_required&&!shutdown_recovery_required;
wire local_error_fence=local_error_started||local_error_needed||receive_connection_closing;
wire local_error_authority=receive_connection_closing&&local_packet_user==receive_connection_user&&
    receive_connection_context_base==active_context_base&&receive_connection_context_bytes==active_context_bytes;
wire local_error_drained=!return_pending&&!generated_offered&&!response_record_lease_active&&(response_idle||response_recovery_required)&&
    receive_wire_idle&&(tx_idle||response_recovery_required)&&!shutdown_busy&&!cancel_valid;
assign packet_result_valid=local_packet_valid&&(!local_error_needed||local_error_started&&local_error_rsp_valid);
assign local_packet_ready=packet_result_ready&&(!local_error_needed||local_error_started&&local_error_rsp_valid);
assign local_error_rsp_ready=local_error_started&&local_packet_valid&&packet_result_ready;
assign packet_committed=local_packet_committed;
assign packet_status=local_error_started&&local_error_status!=0?8'd15:local_packet_status;
assign packet_detail=local_error_started&&local_error_status!=0?local_error_detail:local_packet_detail;
assign packet_memory_status=local_error_started&&local_error_memory_status!=0?local_error_memory_status:local_packet_memory_status;
assign packet_user=local_packet_user;assign packet_tag=local_packet_tag;
always @(posedge clk)begin
    if(rst)local_error_started<=0;
    else begin
        if(local_error_needed&&!local_error_started&&local_error_req_ready)local_error_started<=1;
        if(local_packet_valid&&local_packet_ready)local_error_started<=0;
    end
end
''')
    component = read('http2_local_error_response')
    mapping = dict(clk='clk', rst='rst', req_valid='local_error_needed&&!local_error_started', req_ready='local_error_req_ready',
        req_authority='local_error_authority', req_user='local_packet_user', req_http2_error='transport_packet_http2_error',
        cfg_context_base='receive_connection_context_base', cfg_context_bytes='receive_connection_context_bytes', cfg_work_floor='ctl_cfg_work_floor',
        history_fence='local_packet_valid&&local_error_authority', peer_drained='local_error_drained',
        rsp_valid='local_error_rsp_valid', rsp_ready='local_error_rsp_ready', rsp_status='local_error_status',
        rsp_detail='local_error_detail', rsp_memory_status='local_error_memory_status', busy='local_error_busy', idle='local_error_idle')
    for _, _, n in CLOSE:
        mapping[n] = n
    for d, w, n in ports(component, 'http2_local_error_response'):
        if n in MEMORY:
            bits = MEMORY[n][0]
            mapping[n] = n + '[27*' + str(bits) + '+:' + str(bits) + ']'
        elif n.startswith('m_axis_tx_'):
            mapping[n] = 'local_error_' + n
        assert n in mapping, n
    additions.append(named_instance('http2_local_error_response', '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', 'local_error', mapping))
    c = dict(clk='clk', rst='rst', idle='local_error_wire_idle')
    for _, _, n in ports(read('axis_frame_arbiter'), 'axis_frame_arbiter'):
        if n.startswith('a_axis_'):
            c[n] = 'pre_error_m_axis_tx_' + n[7:]
        elif n.startswith('b_axis_'):
            c[n] = 'local_error_m_axis_tx_' + n[7:]
        elif n.startswith('m_axis_'):
            c[n] = 'm_axis_tx_' + n[7:]
    additions.append(named_instance('axis_frame_arbiter', '.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)', 'local_error_wire', c))
    emit(name, replace(text, 'endmodule\n', '\n'.join(additions) + '\nendmodule\n'))
    name = 'http2_enveloped_parser_application'
    text = extend(extend(add_ports(read(name), name, CLOSE), 18, 19), 27, 28)
    text = connect(text, 'http2_enveloped_parser_core', 'core', {n: n for _, _, n in CLOSE})
    for n, (bits, direction) in MEMORY.items():
        left, right = f'all_{n}[27*{bits}+:{bits}]', f'{n}[18*{bits}+:{bits}]'
        additions_line = 'assign ' + (right + '=' + left if direction == 'output' else left + '=' + right) + ';\n'
        text = replace(text, 'endmodule\n', additions_line + 'endmodule\n')
    emit(name, text)
    sim = folder / 'sim'
    sim.mkdir(exist_ok=True)
    for p in (previous / 'sim').glob('*'):
        if p.is_file():
            shutil.copy2(p, sim / p.name)
            inputs[source_relative(p, root).as_posix()] = sha(p)
    fixture = (sim / 'cocotb_two_fpga_enveloped_top.sv').read_text()
    fixture = extend(extend(fixture, 18, 19), 27, 28)
    fixture = fixture.replace('.CLIENTS(18)', '.CLIENTS(19)').replace('client<27', 'client<28').replace('fault_client<27', 'fault_client<28')
    declarations = '\n'.join(('reg' if d == 'input' else 'wire') + ' ' + w + ' ' + n + ('=1' if d == 'input' else '') + ';' for d, w, n in CLOSE)
    fixture = replace(fixture, 'reg  clk=0;', declarations + '\nreg  clk=0;')
    fixture = connect(fixture, 'http2_enveloped_parser_application', 'dut', {n: n for _, _, n in CLOSE})
    for n, (bits, direction) in MEMORY.items():
        left, right = f'{n}[26*{bits}+:{bits}]', f'p_{n}[17*{bits}+:{bits}]'
        old = 'assign ' + (right + '=' + left if n == 'mem_rsp_status' else left + '=' + right) + ';'
        fixture = replace(fixture, old, old + '\n' + old.replace('[26*', '[27*').replace('[17*', '[18*'))
    fixture = replace(fixture, 'assign fabric_status[26*8+:8]=p_fabric_status[17*8+:8];',
        'assign fabric_status[26*8+:8]=p_fabric_status[17*8+:8];\nassign fabric_status[27*8+:8]=p_fabric_status[18*8+:8];')
    (sim / 'cocotb_two_fpga_enveloped_top.sv').write_text(fixture)
    error_test = root / 'sim/cocotb/test_raw_receive_errors.py'
    inputs[source_relative(error_test, root).as_posix()] = sha(error_test)
    text = error_test.read_text()
    text = replace(text, 'from test_two_fpga_application import SeparateMemory',
        'from test_two_fpga_application import SeparateMemory\nfrom local_error_witness import LocalErrorWitness')
    text = replace(text, '    b = Bench(d, layout, memory, reverse)',
        '    b = Bench(d, layout, memory, reverse)\n    local_error = LocalErrorWitness(d,b)')
    text = replace(text, '(b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated())',
        '(b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(),local_error.observe(),local_error.hold_and_close())')
    text = replace(text, '    # Keep the complete protocol acceptance assertion strict',
        "    actual['local_error_ownership']=local_error.result()\n    # Keep the complete protocol acceptance assertion strict")
    (sim / error_test.name).write_text(text)
    drain_test = root / 'sim/cocotb/test_local_error_gpu_drain.py'
    inputs[source_relative(drain_test, root).as_posix()] = sha(drain_test)
    shutil.copy2(drain_test,sim/'test_raw_grpc_duplex.py')
    witness = root / 'sim/cocotb/local_error_witness.py'
    inputs[source_relative(witness, root).as_posix()] = sha(witness)
    fault_witness = root / 'sim/cocotb/local_error_fault_witness.py'
    inputs[source_relative(fault_witness, root).as_posix()] = sha(fault_witness)
    for fault in (0, 1):
        changed = replace(text, 'from local_error_witness import LocalErrorWitness',
            'from local_error_fault_witness import LocalErrorFaultWitness as LocalErrorWitness')
        changed = replace(changed, 'local_error = LocalErrorWitness(d,b)', f'local_error = LocalErrorWitness(d,b,{fault})')
        changed = replace(changed, '    before = len(b.wire)',
            f'    b.set(fault_client=27,fault_target={fault},fault_arm=1)\n    await cycles(d)\n    b.set(fault_arm=0)\n    before = len(b.wire)')
        changed = replace(changed, "result['packet_status'] == 4", "result['packet_status'] == 15 and value(d,'packet_memory_status')==0x75")
        changed = replace(changed, 'assert observed_goaway == [native_goaway], actual', 'assert observed_goaway == [], actual')
        changed = replace(changed, 'actual_connection_fatal_goaway_without_credit_refund=True,', 'actual_history_read_fault_prevents_untrusted_goaway=True,')
        destination = sim / ('fault-' + str(fault)) / error_test.name
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(changed)
    report = dict(phase='actual_local_error_response_generated', input_sha256=inputs,
        generator_sha256=sha(Path(__file__)), generated_sha256={p.name: sha(p) for p in target.glob('*.v')},
        sim_sha256={p.name: sha(p) for p in sim.glob('*') if p.is_file()},
        fault_test_sha256={p.relative_to(sim).as_posix():sha(p) for p in sim.glob('fault-*/*.py')},
        parser_memory_clients=19, logical_memory_clients=28, actual_highwater_read=True,
        packet_result_waits_for_wire_and_transport_close=True,
        active_gpu_credit_wait_abort_verified=False, physical_transport_close_verified=False, full_system_complete=False)
    (folder / 'generation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
