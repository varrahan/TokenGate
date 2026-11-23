"""Retire real closed RPCs on a closing connection without issuing credit."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace
from generate_two_fpga_application import add_ports, instance, named_instance


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/receive-pool-locked'
    folder = root / 'build/experiments/receive-fatal'
    target = folder / 'rtl'
    target.mkdir(parents=True, exist_ok=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    inputs = {}
    for p in (previous / 'rtl').glob('*.v'):
        shutil.copy2(p, target / p.name)
        inputs[p.relative_to(root).as_posix()] = sha(p)

    def read(name):
        p = previous / 'rtl' / (name + '.v')
        if not p.exists():
            p = root / 'rtl' / (name + '.v')
        inputs[p.relative_to(root).as_posix()] = sha(p)
        return p.read_text()

    def emit(name, text):
        (target / (name + '.v')).write_text(text)

    closing_ports = [('output', '', 'receive_connection_closing'),
        ('output', '[USER_WIDTH-1:0]', 'receive_connection_user'),
        ('output', '[MEMORY_ADDR_WIDTH-1:0]', 'receive_connection_context_base'),
        ('output', '[MEMORY_ADDR_WIDTH:0]', 'receive_connection_context_bytes'),
        ('output', '[MEMORY_ADDR_WIDTH-1:0]', 'receive_connection_rpc_base'),
        ('output', '[MEMORY_ADDR_WIDTH:0]', 'receive_connection_rpc_bytes')]
    name = 'http2_classified_parser_transport'
    text = add_ports(read(name), name, closing_ports)
    text = replace(text, "assign packet_status=packet_control_error!=0?8'd11:p_packet_status;",
        "assign packet_status=packet_control_error!=0?8'd11:raw_status!=0?raw_status:p_packet_status;")
    text = replace(text, 'assign packet_detail=packet_control_error!=0?packet_control_cause:p_packet_detail;',
        'assign packet_detail=packet_control_error!=0?packet_control_cause:raw_status!=0?raw_detail:p_packet_detail;')
    text = replace(text, 'assign packet_memory_status=packet_control_memory!=0?packet_control_memory:p_packet_memory_status;',
        'assign packet_memory_status=packet_control_memory!=0?packet_control_memory:raw_memory!=0?raw_memory:p_packet_memory_status;')
    witness = '''
// The real packet owner has selected connection-fatal rollback/close. This
// witness spans actual prefill rollback and its held directory CLOSE results.
assign receive_connection_closing=control_packet_active&&(packet_fatal||receive_fault_valid||control_early_failed||
    !commit_allowed&&(state==DECISION||state==WAIT_PACKET||state==CONTROL_FINISH_SEND||state==CONTROL_FINISH_WAIT)||
    state==CLOSE_SEND||state==CLOSE_WAIT);
assign receive_connection_user=packet_owner;
assign receive_connection_context_base=owned_cfg_context_base;
assign receive_connection_context_bytes=owned_cfg_context_bytes;
assign receive_connection_rpc_base=owned_stream_base;
assign receive_connection_rpc_bytes=owned_stream_bytes;
'''
    emit(name, replace(text, 'endmodule\n', witness + '\nendmodule\n'))
    name = 'http2_enveloped_parser_core'
    text = read(name)
    a, b, params, connections = instance(text, 'http2_classified_parser_transport', 'forward')
    connections.update({n: n for _, _, n in closing_ports})
    text = text[:a] + named_instance('http2_classified_parser_transport', params, 'forward', connections) + text[b:]
    text = replace(text, "assign rx_init_op=rx_select_close?4'd9:rx_admission_op;",
        "assign rx_init_op=rx_select_close?(rx_close_connection_fatal?4'd10:4'd9):rx_admission_op;")
    declarations = '\n'.join('wire ' + w + ' ' + n + ';' for _, w, n in closing_ports)
    fatal_scope = '''
reg rx_close_connection_fatal;
always @(posedge clk)begin
    if(rst)rx_close_connection_fatal<=0;
    else if(service_control_req_valid&&service_control_req_ready&&service_control_req_op==3)
        rx_close_connection_fatal<=receive_connection_closing&&service_control_req_user==receive_connection_user&&
            rx_next_close_cfg_context_base==receive_connection_context_base&&rx_next_close_cfg_context_bytes==receive_connection_context_bytes&&
            service_control_pool_base==receive_connection_rpc_base&&service_control_pool_bytes==receive_connection_rpc_bytes;
end
'''
    emit(name, replace(text, 'endmodule\n', declarations + fatal_scope + '\nendmodule\n'))
    name = 'http2_receive_flow_controller'
    text = read(name)
    text = replace(text, 'request_is_init<=init_op!=9;request_is_close<=init_op==9;',
        'request_is_init<=init_op!=9&&init_op!=10;request_is_close<=init_op==9||init_op==10;')
    # Only ordinary active-connection retirement (op 9) schedules RETURN_CREDIT.
    assert text.count('if(request_op==9)begin') == 1
    emit(name, text)
    name = 'http2_receive_credit_store'
    text = read(name)
    text = replace(text, '// Op 9 requires',
        '// Op 10 retires a matching inactive RPC under actual connection-close\n// ownership: close the stream ledger without credit release or network output.\n// Op 9 requires')
    text = replace(text, 'WCLOSE=6,WCONNECTION=7;', 'WCLOSE=6,WCONNECTION=7,WFATAL=8;')
    text = replace(text, 'reg [2:0] write_mode;', 'reg [3:0] write_mode;')
    text = replace(text, 'task write_words(input [2:0] mode);', 'task write_words(input [3:0] mode);')
    text = replace(text, '            WCONNECTION:begin',
        '            WFATAL:begin write_last=write_index==1;write_address=stream_address+(write_index==0?8:16);write_word=write_index==0?stream_words[1]:stream_words[2];end\n            WCONNECTION:begin')
    text = replace(text, 'operation>9||!config_good', 'operation>10||!config_good')
    text = replace(text, 'operation==5||operation==9)&&!stream_command', 'operation==5||operation==9||operation==10)&&!stream_command')
    text = replace(text, '(operation==1||operation==5||operation==8||operation==9)&&amount!=0',
        '(operation==1||operation==5||operation==8||operation==9||operation==10)&&amount!=0')
    text = replace(text, 'raw_header[31:0]!=RAW_MAGIC||!raw_header[32]',
        '(operation==10?raw_header!=0&&(raw_header[31:0]!=RAW_MAGIC||!raw_header[32]):raw_header[31:0]!=RAW_MAGIC||!raw_header[32])')
    text = replace(text, 'operation==9?!retired_rpc_good:!rpc_good', '(operation==9||operation==10)?!retired_rpc_good:!rpc_good')
    text = replace(text, 'operation!=5&&operation!=8&&operation!=9)', 'operation!=5&&operation!=8&&operation!=9&&operation!=10)')
    text = replace(text, '                    5,9:if(stream_closed)', '''                    10:if(stream_closed)state<=RESULT;
                        else begin stream_record[127]<=1;stream_record[159:128]<=0;write_words(WFATAL);end
                    5,9:if(stream_closed)''')
    emit(name, text)
    sim = folder / 'sim'
    sim.mkdir(exist_ok=True)
    for p in (previous / 'sim').glob('*'):
        if p.is_file():
            shutil.copy2(p, sim / p.name)
            inputs[p.relative_to(root).as_posix()] = sha(p)
    report = dict(phase='actual_closing_connection_retirement_generated', input_sha256=inputs,
        generator_sha256=sha(Path(__file__)), generated_sha256={p.name: sha(p) for p in target.glob('*.v')},
        sim_sha256={p.name: sha(p) for p in sim.glob('*') if p.is_file()},
        closing_scope_from_actual_packet_owner=True, fatal_retirement_refunds_connection=False,
        local_error_goaway_implemented=False, full_system_complete=False)
    (folder / 'generation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
