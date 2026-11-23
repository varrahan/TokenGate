"""Connect real receive admission, committed DATA replay and wire retirement."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports, instance, named_instance, MEMORY

from rtl_paths import source_path, source_relative


CONFIG = [('input', '[MEMORY_ADDR_WIDTH-1:0]', 'cfg_receive_connection_base'),
          ('input', '[MEMORY_ADDR_WIDTH:0]', 'cfg_receive_connection_bytes'),
          ('input', '[MEMORY_ADDR_WIDTH-1:0]', 'cfg_receive_stream_base'),
          ('input', '[MEMORY_ADDR_WIDTH:0]', 'cfg_receive_stream_bytes')]
FAULT = [('output', '', 'receive_fault_valid'), ('output', '[7:0]', 'receive_fault_status'),
         ('output', '[7:0]', 'receive_fault_detail'), ('output', '[7:0]', 'receive_fault_memory_status'),
         ('output', '[31:0]', 'receive_fault_http2_error'), ('output', '', 'receive_recovery_required')]
REPLAY = [('output', '', 'receive_replay_valid'), ('input', '', 'receive_replay_ready'),
          ('input', '[7:0]', 'receive_replay_status')] + [
    ('output', w, 'receive_replay_' + n) for w, n in
    [('[3:0]', 'kind'), ('[31:0]', 'arg0'), ('[23:0]', 'length'), ('[7:0]', 'flags'),
     ('[30:0]', 'stream'), ('[USER_WIDTH-1:0]', 'user')]]


def replace(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/registered-envelope-scope/rtl'
    target = root / 'build/experiments/receive-integration/rtl'; target.mkdir(parents=True, exist_ok=True)
    for p in previous.glob('*.v'): shutil.copy2(p, target / p.name)
    inputs = {}
    def source(name):
        p = previous / (name + '.v')
        if not p.exists(): p = source_path(root, Path('rtl') / (name + '.v'))
        inputs[source_relative(p, root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        return p.read_text()
    def save(name, text): (target / (name + '.v')).write_text(text)
    def connect(text, child, inst, extra):
        a, b, params, c = instance(text, child, inst); c.update(extra)
        return text[:a] + named_instance(child, params, inst, c) + text[b:]

    name = 'http2_control_event_fork'; text = source(name)
    text = replace(text, 's_kind==0||s_kind==3||s_kind>=4', 's_kind==0||s_kind==3||s_kind>=4||s_type==0&&s_kind==1')
    save(name, text)
    name = 'http2_control_journal'; text = source(name)
    text = replace(text, 'wire selected_type=s_type==3', 'wire selected_type=s_type==0||s_type==3')
    text = replace(text, 'selected_type&&(s_kind==0||s_kind==3||s_kind>=4&&s_kind<=8)',
        'selected_type&&(s_kind==0||s_kind==3||s_type==0&&s_kind==1||s_type!=0&&s_kind>=4&&s_kind<=8)')
    text = replace(text, '(entry_type==3||entry_type==4', '(entry_type==0||entry_type==3||entry_type==4')
    text = replace(text, '(entry_kind==0||entry_kind==3||entry_kind>=4&&entry_kind<=8)',
        '(entry_kind==0||entry_kind==3||entry_type==0&&entry_kind==1||entry_type!=0&&entry_kind>=4&&entry_kind<=8)')
    save(name, text)
    # Only complete committed DATA metadata reaches this extra consumer. The
    # existing control executor keeps its original non-DATA input and ownership.
    name = 'http2_shutdown_journaled_controls'; text = add_ports(source(name), name, REPLAY)
    text = replace(text, 'wire  j_m_ready;', 'wire j_m_ready,e_input_ready;wire [7:0] e_input_status;')
    text = replace(text, 'wire [7:0] j_consume_status;', '''wire [7:0] j_consume_status;
wire receive_record=j_m_type==0;
assign j_m_ready=receive_record?receive_replay_ready:e_input_ready;
assign j_consume_status=receive_record?receive_replay_status:e_input_status;
assign receive_replay_valid=j_m_valid&&receive_record;
assign receive_replay_kind=j_m_kind;assign receive_replay_arg0=j_m_arg0;
assign receive_replay_length=j_m_length;assign receive_replay_flags=j_m_flags;
assign receive_replay_stream=j_m_stream;assign receive_replay_user=j_m_user;''')
    text = connect(text, 'http2_shutdown_control_executor', 'executor',
                   dict(s_valid='j_m_valid&&!receive_record', s_ready='e_input_ready', s_status='e_input_status'))
    save(name, text)
    for name, child, inst in [('http2_shutdown_peer_controls', 'http2_shutdown_journaled_controls', 'journaled'),
                              ('http2_shutdown_classified_controls', 'http2_shutdown_peer_controls', 'controls')]:
        save(name, connect(add_ports(source(name), name, REPLAY), child, inst, {n:n for _,_,n in REPLAY}))

    name = 'http2_classified_parser_transport'; text = source(name)
    extra = [('input', w, n) for _,w,n in FAULT if n != 'receive_recovery_required']
    extra.append(('output','','receive_data_admit'))
    text = add_ports(text, name, extra)
    text = replace(text,'    wire data_byte=r_event_kind==2&&r_event_type==0;',
        '    assign receive_data_admit=state==RUN&&!header_pending&&!r_block_start_valid&&!router_active;\n    wire data_byte=r_event_kind==2&&r_event_type==0;')
    text = replace(text, 'assign p_s_valid=state==RUN&&!packet_fatal&&',
                   'assign p_s_valid=state==RUN&&!packet_fatal&&!receive_fault_valid&&')
    text = replace(text, 'commit_allowed<=!packet_fatal&&!p_prepared_failed&&',
                   'commit_allowed<=!packet_fatal&&!receive_fault_valid&&!p_prepared_failed&&')
    text = replace(text, 'assign ctl_finish_commit=p_packet_committed&&!packet_fatal;',
                   'assign ctl_finish_commit=p_packet_committed&&!packet_fatal&&!receive_fault_valid;')
    text = replace(text, '            endcase\n        end\n    end', '''            endcase
            // Debit errors block application dispatch immediately. Keep the
            // original scoped cause even when raw framing itself later succeeds.
            if(receive_fault_valid&&control_packet_active)begin
                packet_fatal<=1;commit_allowed<=0;raw_status<=12;
                raw_detail<=receive_fault_detail;raw_memory<=receive_fault_memory_status;
                raw_h2<=receive_fault_http2_error;
            end
        end
    end''')
    save(name, text)

    name = 'http2_enveloped_parser_core'; text = add_ports(source(name), name, CONFIG + FAULT)
    # One extra logical client is compacted into the Parser's local fabric.
    for n,(bits,_) in MEMORY.items():
        text = replace(text, '[' + ('25:0' if bits==1 else str(26*bits-1)+':0') + '] '+n,
            '[27*'+str(bits)+'-1:0] '+n) if isinstance(bits,int) and '[' + ('25:0' if bits==1 else str(26*bits-1)+':0') + '] '+n in text else text
        text = text.replace('[26*'+str(bits)+'-1:0] '+n, '[27*'+str(bits)+'-1:0] '+n)
    extra_lines=[]
    for d,w,n in CONFIG:
        extra_lines.append('reg '+w+' owned_'+n+';')
    extra_lines += ['always @(posedge clk)begin', 'if(rst)begin '+''.join('owned_'+n+'<=0;' for _,_,n in CONFIG)+'end',
        'else if(command_valid&&command_ready||control_valid&&control_ready||s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin '+''.join('owned_'+n+'<='+n+';' for _,_,n in CONFIG)+'end end']
    cp = ports((source_path(root, 'rtl/http2_receive_flow_controller.v')).read_text(), 'http2_receive_flow_controller')
    cc={}; declared=set()
    def wire(w,n):
        if n not in declared: extra_lines.append('wire '+w+' '+n+';'); declared.add(n)
    for d,w,n in cp:
        if n in ('clk','rst'): cc[n]=n
        elif n=='abort_flow': cc[n]='control_drop_events'
        elif n=='admit_data': cc[n]='receive_data_admit';wire(w,cc[n])
        elif n.startswith('fault_'): cc[n]='receive_'+n
        elif n=='idle': cc[n]='receive_controller_idle'; wire(w,cc[n])
        else: cc[n]='rx_'+n; wire(w,cc[n])
    # Real initialization request is captured at send-ledger request acceptance;
    # its held successful response remains owned until the RX ledger also ACKs.
    extra_lines += ['reg rx_init_started,rx_close_started,rx_initialization_is_close;',
        'reg [3:0] rx_admission_op;reg rx_admission_maintenance;',
        'reg [USER_WIDTH-1:0] rx_admission_user;reg [30:0] rx_admission_stream;reg [31:0] rx_admission_generation;',
        'reg [MEMORY_ADDR_WIDTH-1:0] rx_admission_address;',
        "wire rx_close_needed=service_control_rsp_valid&&service_control_rsp_status==0&&service_control_rsp_op==3;",
        'wire rx_admission_complete=rx_init_started&&rx_init_result_valid&&!rx_initialization_is_close;',
        'wire rx_close_complete=rx_close_started&&rx_init_result_valid&&rx_initialization_is_close;',
        'wire rx_close_gate=!rx_close_needed||rx_close_complete;',
        'wire rx_select_close=rx_close_needed&&!rx_close_started;',
        'assign rx_init_valid=rx_select_close||!rx_close_needed&&window_owner==2&&service_window_rsp_valid&&service_window_rsp_status==0&&!rx_init_started;',
        "assign rx_init_op=rx_select_close?4'd9:rx_admission_op;",
        "assign rx_init_maintenance=rx_select_close?1'b0:rx_admission_maintenance;",
        'assign rx_init_user=rx_select_close?service_control_rsp_user:rx_admission_user;',
        'assign rx_init_stream=rx_select_close?service_control_rsp_stream:rx_admission_stream;',
        'assign rx_init_generation=rx_select_close?service_control_rsp_generation:rx_admission_generation;',
        'assign rx_init_address=rx_select_close?service_control_rsp_address:rx_admission_address;',
        'assign rx_init_result_ready=rx_initialization_is_close?service_control_rsp_valid&&service_control_rsp_ready:window_owner==2&&service_window_rsp_valid&&init_window_rsp_ready;',
        'always @(posedge clk)begin if(rst)begin rx_init_started<=0;rx_close_started<=0;rx_initialization_is_close<=0;rx_admission_op<=0;rx_admission_maintenance<=0;rx_admission_user<=0;rx_admission_stream<=0;rx_admission_generation<=0;rx_admission_address<=0;end else begin',
        'if(rx_init_valid&&rx_init_ready)begin rx_initialization_is_close<=rx_select_close;if(rx_select_close)rx_close_started<=1;else rx_init_started<=1;end',
        'if(window_owner==2&&service_window_rsp_valid&&service_window_rsp_ready)rx_init_started<=0;',
        'if(service_control_rsp_valid&&service_control_rsp_ready)rx_close_started<=0;',
        'if(init_window_req_valid&&init_window_req_ready)begin rx_admission_op<=init_window_req_op;rx_admission_maintenance<=init_window_req_maintenance;rx_admission_user<=init_window_req_user;rx_admission_stream<=init_window_req_stream;rx_admission_generation<=init_window_req_generation;rx_admission_address<=init_window_req_record_address;end end end']
    text = replace(text, 'assign init_window_rsp_valid=window_owner==2&&service_window_rsp_valid;',
        'assign init_window_rsp_valid=window_owner==2&&service_window_rsp_valid&&(service_window_rsp_status!=0||rx_admission_complete);')
    text = replace(text, 'window_owner==2?init_window_rsp_ready:',
        'window_owner==2?init_window_rsp_ready&&(service_window_rsp_status!=0||rx_admission_complete):')
    text = replace(text, '2:if(service_window_rsp_valid&&init_window_rsp_ready)window_owner<=0;',
        '2:if(service_window_rsp_valid&&service_window_rsp_ready)window_owner<=0;')
    for n in ('status','detail','memory_status'):
        text = replace(text, 'assign init_window_rsp_'+n+'=service_window_rsp_'+n+';',
            'assign init_window_rsp_'+n+'=service_window_rsp_status!=0?service_window_rsp_'+n+':rx_init_'+n+';')
    # A physically applied failed CLOSE never authorizes a refund. For an
    # acknowledged successful CLOSE, keep the real result and pool owner held
    # until op9 validates the inactive tuple and the connection update retires.
    text=replace(text,'assign dir_rsp_valid=shutdown_dir_owner==2&&service_control_rsp_valid;',
        'assign dir_rsp_valid=shutdown_dir_owner==2&&service_control_rsp_valid&&rx_close_gate;')
    text=replace(text,'assign shutdown_directory_rsp_valid=shutdown_dir_owner==4&&service_control_rsp_valid;',
        'assign shutdown_directory_rsp_valid=shutdown_dir_owner==4&&service_control_rsp_valid&&rx_close_gate;')
    text=replace(text,'assign service_control_rsp_ready=shutdown_dir_owner==2?dir_rsp_ready:shutdown_dir_owner==4&&shutdown_directory_rsp_ready;',
        'assign service_control_rsp_ready=rx_close_gate&&(shutdown_dir_owner==2?dir_rsp_ready:shutdown_dir_owner==4&&shutdown_directory_rsp_ready);')
    text=replace(text,'2:if(service_control_rsp_valid&&dir_rsp_ready)shutdown_dir_owner<=0;',
        '2:if(service_control_rsp_valid&&service_control_rsp_ready)shutdown_dir_owner<=0;')
    text=replace(text,'4:if(service_control_rsp_valid&&shutdown_directory_rsp_ready)shutdown_dir_owner<=0;',
        '4:if(service_control_rsp_valid&&service_control_rsp_ready)shutdown_dir_owner<=0;')
    for n in ('status','detail','memory_status'):
        wire('[7:0]','rx_directory_'+n)
        extra_lines.append('assign rx_directory_'+n+'=rx_close_needed?rx_init_'+n+':service_control_rsp_'+n+';')
        text=replace(text,'assign dir_rsp_'+n+'=service_control_rsp_'+n+';', 'assign dir_rsp_'+n+'=rx_directory_'+n+';')
    text=connect(text,'http2_enveloped_shutdown','shutdown',{'directory_rsp_'+n:'rx_directory_'+n for n in ('status','detail','memory_status')})
    close_config=[('cfg_context_base','[MEMORY_ADDR_WIDTH-1:0]'),('cfg_context_bytes','[MEMORY_ADDR_WIDTH:0]'),
        ('cfg_rpc_base','[MEMORY_ADDR_WIDTH-1:0]'),('cfg_rpc_bytes','[MEMORY_ADDR_WIDTH:0]'),('cfg_work_floor','[MEMORY_ADDR_WIDTH-1:0]')]+[(n,w) for _,w,n in CONFIG]
    for n,w in close_config: extra_lines.append('reg '+w+' rx_close_'+n+';')
    for n,w in close_config:
        if n.startswith('cfg_receive_'): rhs='owned_'+n
        elif n=='cfg_rpc_base':rhs='service_control_pool_base'
        elif n=='cfg_rpc_bytes':rhs='service_control_pool_bytes'
        else:
            extra_lines.append('reg '+w+' rx_external_'+n+';')
            rhs='shutdown_dir_owner==3?shutdown_owned_'+n[4:]+':rx_external_control_live?rx_external_'+n+':ctl_'+n
        extra_lines.append('wire '+w+' rx_next_close_'+n+'='+rhs+';')
    external=[n for n,_ in close_config if not n.startswith(('cfg_receive_','cfg_rpc_'))]
    extra_lines += ['reg rx_external_control_live;',
        'always @(posedge clk)begin if(rst)begin rx_external_control_live<=0;'+''.join('rx_close_'+n+'<=0;' for n,_ in close_config)+''.join('rx_external_'+n+'<=0;' for n in external)+'end else begin',
        'if(control_valid&&control_ready)begin rx_external_control_live<=1;'+''.join('rx_external_'+n+'<='+n+';' for n in external)+'end',
        'if(control_result_valid&&control_result_ready)rx_external_control_live<=0;',
        "if(service_control_req_valid&&service_control_req_ready&&service_control_req_op==3)begin "+''.join('rx_close_'+n+'<=rx_next_close_'+n+';' for n,_ in close_config)+'end end end']
    # New pre-dispatch consumer preserves the same actual journal input ACK.
    text = replace(text, "assign flow_event_ready=control_drop_events?1'b1:ctl_flow_ready;",
        "assign flow_event_ready=control_drop_events?1'b1:rx_s_ready;")
    for d,w,n in cp:
        if n.startswith('s_'):
            target_name='flow_event_'+n[2:] if n!='s_valid' else 'flow_event_valid&&!control_drop_events'
            if n=='s_ready': continue
            extra_lines.append('assign rx_'+n+'='+target_name+';')
    replay_connections={n:'rx_replay_'+n[len('receive_replay_'):] for _,_,n in REPLAY}
    mapping={n:'rx_m_'+n[2:] for n in ('s_valid','s_ready','s_kind','s_data','s_arg0','s_arg1','s_length','s_type','s_flags','s_stream','s_user')}
    mapping.update(replay_connections)
    text = connect(text,'http2_shutdown_classified_controls','controls',mapping)
    # Existing tx arbiter remains in place. A new actual-wire packet arbiter
    # acknowledges neither input until its selected final output handshakes.
    a,b,p,c=instance(text,'rpc_grpc_http2_return','reverse')
    for n in list(c):
        if n.startswith('m_axis_tx_'):
            w=next(w for _,w,x in ports(source('rpc_grpc_http2_return'),'rpc_grpc_http2_return') if x==n)
            wire(w,'ordinary_'+n);c[n]='ordinary_'+n
    text=text[:a]+named_instance('rpc_grpc_http2_return',p,'reverse',c)+text[b:]
    bc={}; bp=ports((source_path(root, 'rtl/http2_keyed_receive_credit_store.v')).read_text(),'http2_keyed_receive_credit_store')
    for d,w,n in bp:
        if n in ('clk','rst') or n.startswith('context_write_'): bc[n]=n
        elif n.startswith('m_axis_tx_'): bc[n]='rx_'+n;wire(w,bc[n])
        elif n in MEMORY:
            bits=MEMORY[n][0];bc[n]=n+'[26*'+str(bits)+'+:'+str(bits)+']'
        elif n=='req_authority': bc[n]="1'b1"
        elif n.startswith('req_'): bc[n]='rx_request_'+{'valid':'valid','ready':'ready','record_address':'address'}.get(n[4:],n[4:])
        elif n.startswith('cfg_receive_'): bc[n]='rx_request_is_close?rx_close_'+n+':owned_'+n
        elif n=='cfg_rpc_base': bc[n]='rx_request_is_close?rx_close_'+n+':rx_request_is_init?init_window_cfg_stream_base:ctl_cfg_stream_base'
        elif n=='cfg_rpc_bytes': bc[n]='rx_request_is_close?rx_close_'+n+':rx_request_is_init?init_window_cfg_stream_bytes:ctl_cfg_stream_bytes'
        elif n.startswith('cfg_'): bc[n]='rx_request_is_close?rx_close_'+n+':rx_request_is_init?init_window_'+n+':ctl_'+n
        elif n.startswith('rsp_'):
            match='rx_result_'+n[4:];bc[n]=match if any(x==match for _,_,x in [('','','rx_'+a) for _,_,a in cp]) else ''
        elif n=='recovery_required':bc[n]='receive_recovery_required'
        elif n in ('recovery_address','idle'):bc[n]=''
        else: raise AssertionError(n)
    extra_lines.append(named_instance('http2_keyed_receive_credit_store','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','receive_credits',bc))
    extra_lines.append(named_instance('http2_receive_flow_controller','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','receive_flow',cc))
    ap=ports((source_path(root, 'rtl/axis_frame_arbiter.v')).read_text(),'axis_frame_arbiter'); ac={}
    for d,w,n in ap:
        if n in('clk','rst'): ac[n]=n
        elif n.startswith('a_axis_'): ac[n]='ordinary_m_axis_tx_'+n[7:]
        elif n.startswith('b_axis_'): ac[n]='rx_m_axis_tx_'+n[7:]
        elif n.startswith('m_axis_'):ac[n]='m_axis_tx_'+n[7:]
        elif n=='idle':ac[n]='receive_wire_idle';wire(w,ac[n])
        else:raise AssertionError(n)
    extra_lines.append(named_instance('axis_frame_arbiter','.DATA_WIDTH(512),.USER_WIDTH(USER_WIDTH)','receive_wire',ac))
    text=connect(text,'http2_classified_parser_transport','forward',dict({n:n for _,_,n in FAULT if n!='receive_recovery_required'},receive_data_admit='receive_data_admit'))
    text=replace(text,'wire allow_new_rx=!journal_recovery_required&&','wire allow_new_rx=!receive_recovery_required&&!receive_fault_valid&&!journal_recovery_required&&')
    text=replace(text,'assign idle=f_idle&&response_idle&&journal_idle&&tx_idle&&','assign idle=receive_controller_idle&&receive_wire_idle&&f_idle&&response_idle&&journal_idle&&tx_idle&&')
    # Strip duplicate wire declarations for initialized capture registers above.
    text=replace(text,'endmodule\n','\n'+'\n'.join(extra_lines)+'\nendmodule\n')
    save(name,text)
    name='http2_enveloped_parser_application'; text=add_ports(source(name),name,CONFIG+FAULT)
    text=re.sub(r'\[17\*([^\]]+)-1:0\]',r'[18*\1-1:0]',text)
    text=re.sub(r'\[26\*([^\]]+)-1:0\]',r'[27*\1-1:0]',text)
    for n,(bits,d) in MEMORY.items():
        l=f'all_{n}[26*{bits}+:{bits}]';r=f'{n}[17*{bits}+:{bits}]'
        text=replace(text,'endmodule\n',('assign '+r+'='+l+';\n' if d=='output' else 'assign '+l+'='+r+';\n')+'endmodule\n')
    text=connect(text,'http2_enveloped_parser_core','core',{n:n for _,_,n in CONFIG+FAULT}); save(name,text)
    # Passive fixture gets one real Parser fabric client and typed config ports.
    fixture=(root/'sim/cocotb_two_fpga_enveloped_top.sv').read_text()
    fixture=re.sub(r'\[17\*([^\]]+)-1:0\]',r'[18*\1-1:0]',fixture)
    fixture=re.sub(r'\[26\*([^\]]+)-1:0\]',r'[27*\1-1:0]',fixture)
    fixture=fixture.replace('.CLIENTS(17)', '.CLIENTS(18)').replace('client<26','client<27').replace('fault_client<26','fault_client<27')
    declarations='\n'.join(('reg' if d=='input' else 'wire')+' '+w+' '+n+('=0' if d=='input' else '')+';' for d,w,n in CONFIG+FAULT)
    fixture=replace(fixture,'reg  clk=0;',declarations+'\nreg  clk=0;')
    fixture=connect(fixture,'http2_enveloped_parser_application','dut',{n:n for _,_,n in CONFIG+FAULT})
    # Extend existing compact/global mapping by the new client at its end.
    for n,(bits,d) in MEMORY.items():
        old_l=f'{n}[25*{bits}+:{bits}]'; old_r=f'p_{n}[16*{bits}+:{bits}]'
        old = f'assign {old_r}={old_l};' if n=='mem_rsp_status' else f'assign {old_l}={old_r};'
        new=old.replace('[25*','[26*').replace('[16*','[17*')
        fixture=replace(fixture,old,old+'\n'+new)
    fixture=replace(fixture,'assign fabric_status[25*8+:8]=p_fabric_status[16*8+:8];',
        'assign fabric_status[25*8+:8]=p_fabric_status[16*8+:8];\nassign fabric_status[26*8+:8]=p_fabric_status[17*8+:8];')
    sim=target.parent/'sim';sim.mkdir(exist_ok=True);(sim/'cocotb_two_fpga_enveloped_top.sv').write_text(fixture)
    test=(root/'sim/cocotb/test_raw_grpc_enveloped.py').read_text()
    test=replace(test,'parser_memory_clients=17,','parser_memory_clients=len(d.p_mem_valid),')
    for types in ('[1]','[1,0,1]'):
        old='[packet[3]for packet in b.wire[before:]]=='+types+"and not value(d,'response_recovery_required')"
        test=replace(test,old,'[packet[3]for packet in b.wire[before:]if packet[3]!=8]=='+types+"and not value(d,'response_recovery_required')")
    (sim/'test_raw_grpc_enveloped.py').write_text(test)
    from generate_receive_commit_test import generate
    generate(root,sim/'test_raw_receive_flow.py')
    for n in ('http2_receive_flow_controller','http2_keyed_receive_credit_store','http2_receive_credit_store'):source(n)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(phase='receive_integration_experiment_generated',input_sha256=inputs,generator_sha256=sha(Path(__file__)),
        generated_sha256={p.name:sha(p) for p in target.glob('*.v')},harness_sha256=sha(sim/'cocotb_two_fpga_enveloped_top.sv'),
        test_overlay_sha256=sha(sim/'test_raw_grpc_enveloped.py'),
        padding_overlay_sha256=sha(sim/'test_raw_receive_flow.py'),padding_generator_sha256=sha(root/'tools/generate_receive_commit_test.py'),
        parser_memory_clients=18,logical_clients=27,application_reclamation_integrated=False,close_refund_integrated=True,actual_close_refund_verified=False,full_system_complete=False)
    (target.parent/'generation.json').write_text(json.dumps(report,indent=2)+'\n');print(target)


if __name__=='__main__': main()
