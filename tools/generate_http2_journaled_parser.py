"""Join raw packet commit, persistent controls, shared windows and wire TX arbitration."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import MEMORY,add_ports,header_end,instance,named_instance,rename

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];inputs={};outputs={}
    def read(name):
        path=source_path(root, Path('rtl') / (name+'.v'));inputs[source_relative(path, root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest();return path.read_text()
    def emit(name,source):
        path=source_path(root, Path('rtl') / (name+'.v'));path.write_text(source);outputs[source_relative(path, root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    addr='[MEMORY_ADDR_WIDTH-1:0]';size='[MEMORY_ADDR_WIDTH:0]'
    extra=[('input',addr,'cfg_control_journal_base'),('input',size,'cfg_control_journal_bytes'),('input',size,'cfg_control_slot_bytes'),
        ('output','[7:0]','command_control_status'),('output','[7:0]','packet_control_status'),
        ('output','[7:0]','packet_control_detail'),('output','[7:0]','packet_control_memory_status')]
    lifecycle=[('output','','ctl_start_valid'),('input','','ctl_start_ready'),('output','','ctl_start_format'),
        ('output','','ctl_start_maintenance'),('output','[USER_WIDTH-1:0]','ctl_start_user'),
        ('output','','ctl_finish_valid'),('input','','ctl_finish_ready'),('output','','ctl_finish_commit'),
        ('input','','ctl_result_valid'),('output','','ctl_result_ready'),('input','[7:0]','ctl_result_status'),
        ('input','[7:0]','ctl_result_detail'),('input','[7:0]','ctl_result_memory_status'),('output','','control_drop_events')]
    for n in('context_base','stream_base','window_base','work_floor','journal_base'):lifecycle.append(('output',addr,'ctl_cfg_'+n))
    for n in('context_bytes','stream_bytes','window_bytes','journal_bytes','slot_bytes'):lifecycle.append(('output',size,'ctl_cfg_'+n))
    source=read('http2_initialized_parser_transport');source=add_ports(source,'http2_initialized_parser_transport',extra+lifecycle)
    source=rename(source,'http2_initialized_parser_transport','http2_journaled_parser_transport')
    replacements=(
        ('reg [7:0] window_command_status,window_command_detail,window_command_memory,window_command_cleanup;',
         'reg [7:0] window_command_status,window_command_detail,window_command_memory,window_command_cleanup;\n'
         '    reg [MEMORY_ADDR_WIDTH-1:0] owned_control_journal_base;reg [MEMORY_ADDR_WIDTH:0] owned_control_journal_bytes,owned_control_slot_bytes;\n'
         '    reg [7:0] command_control_error,command_control_detail,command_control_memory,packet_control_error,packet_control_cause,packet_control_memory;\n'
         '    reg control_packet_active,control_early_failed;'),
        ('WINDOW_CLOSE_SEND=18,WINDOW_CLOSE_WAIT=19;',
         'WINDOW_CLOSE_SEND=18,WINDOW_CLOSE_WAIT=19,CONTROL_OPEN_SEND=20,CONTROL_OPEN_WAIT=21,CONTROL_PACKET_SEND=22,CONTROL_PACKET_WAIT=23,CONTROL_DRAIN=24,CONTROL_FINISH_SEND=25,CONTROL_FINISH_WAIT=26;'),
        ('assign packet_committed=p_packet_committed;', 'assign packet_committed=p_packet_committed&&packet_control_error==0;'),
        ('assign packet_status=p_packet_status;', "assign packet_status=packet_control_error!=0?8'd11:p_packet_status;"),
        ('assign packet_detail=p_packet_detail;', 'assign packet_detail=packet_control_error!=0?packet_control_cause:p_packet_detail;'),
        ('assign packet_memory_status=p_packet_memory_status;', 'assign packet_memory_status=packet_control_memory!=0?packet_control_memory:p_packet_memory_status;'),
        ("assign rsp_status=state==WINDOW_OPEN_RESULT?(window_command_status==0?8'd0:8'd9)",
         "assign rsp_status=state==WINDOW_OPEN_RESULT?(command_control_error!=0?8'd10:window_command_status==0?8'd0:8'd9)"),
        ('assign rsp_detail=state==WINDOW_OPEN_RESULT?window_command_detail:',
         'assign rsp_detail=state==WINDOW_OPEN_RESULT?(command_control_error!=0?command_control_detail:window_command_detail):'),
        ('assign rsp_memory_status=state==WINDOW_OPEN_RESULT?window_command_memory:',
         'assign rsp_memory_status=state==WINDOW_OPEN_RESULT?(command_control_memory!=0?command_control_memory:window_command_memory):'),
        ("state==WINDOW_OPEN_RESULT?(window_command_status==0?32'd0:32'd2)",
         "state==WINDOW_OPEN_RESULT?(window_command_status==0&&command_control_error==0?32'd0:32'd2)"),
        ('state==RUN&&!first_valid&&r_s_axis_rx_tready);',
         'state==RUN&&!first_valid&&r_s_axis_rx_tready||state==CONTROL_DRAIN&&!first_valid);'),
        ('owned_cfg_window_base<=cfg_window_base;owned_cfg_window_bytes<=cfg_window_bytes;',
         'owned_control_journal_base<=cfg_control_journal_base;owned_control_journal_bytes<=cfg_control_journal_bytes;owned_control_slot_bytes<=cfg_control_slot_bytes;\n'
         '                owned_cfg_window_base<=cfg_window_base;owned_cfg_window_bytes<=cfg_window_bytes;'),
        ('state<=IDLE;owned_cfg_window_base<=0;',
         'state<=IDLE;owned_control_journal_base<=0;owned_control_journal_bytes<=0;owned_control_slot_bytes<=0;\n'
         '            command_control_error<=0;command_control_detail<=0;command_control_memory<=0;packet_control_error<=0;packet_control_cause<=0;packet_control_memory<=0;control_packet_active<=0;control_early_failed<=0;\n'
         '            owned_cfg_window_base<=0;'),
        ('if(stream_cfg_valid&&stream_cfg_ready)begin pending_stream_base<=cfg_stream_base;',
         'if(ctl_result_valid&&ctl_result_ready&&state!=CONTROL_OPEN_WAIT&&state!=CONTROL_FINISH_WAIT)begin\n'
         '                packet_control_error<=ctl_result_status;packet_control_cause<=ctl_result_detail;packet_control_memory<=ctl_result_memory_status;\n'
         "                control_early_failed<=1;packet_fatal<=1;raw_status<=11;raw_detail<=ctl_result_detail;raw_memory<=ctl_result_memory_status;raw_h2<=2;\n            end\n"
         '            if(stream_cfg_valid&&stream_cfg_ready)begin pending_stream_base<=cfg_stream_base;'),
        ('window_command_status<=0;window_command_detail<=0;window_command_memory<=0;window_command_cleanup<=0;\n                saved_command_op<=command_op;',
         'window_command_status<=0;window_command_detail<=0;window_command_memory<=0;window_command_cleanup<=0;\n'
         '                command_control_error<=0;command_control_detail<=0;command_control_memory<=0;\n                saved_command_op<=command_op;'),
        ('raw_h2<=0;state<=PACKET_START;',
         'raw_h2<=0;packet_control_error<=0;packet_control_cause<=0;packet_control_memory<=0;control_packet_active<=1;control_early_failed<=0;state<=CONTROL_PACKET_SEND;'),
        ('state<=init_window_rsp_status==0?WINDOW_OPEN_RESULT:WINDOW_CLOSE_SEND;',
         'state<=init_window_rsp_status==0?CONTROL_OPEN_SEND:WINDOW_CLOSE_SEND;'),
        ('PACKET_START:if(p_packet_start_ready)state<=RUN;',
         'CONTROL_OPEN_SEND:if(ctl_start_ready)state<=CONTROL_OPEN_WAIT;\n'
         '                CONTROL_OPEN_WAIT:if(ctl_result_valid)begin\n'
         '                    command_control_error<=ctl_result_status;command_control_detail<=ctl_result_detail;command_control_memory<=ctl_result_memory_status;\n'
         '                    state<=ctl_result_status==0?WINDOW_OPEN_RESULT:WINDOW_CLOSE_SEND;end\n'
         '                CONTROL_PACKET_SEND:if(ctl_start_ready)state<=CONTROL_PACKET_WAIT;\n'
         '                CONTROL_PACKET_WAIT:if(ctl_result_valid||ctl_finish_ready)state<=PACKET_START;\n'
         '                PACKET_START:if(p_packet_start_ready)state<=control_early_failed?CONTROL_DRAIN:RUN;\n'
         '                CONTROL_DRAIN:begin\n'
         '                    if(first_valid)begin first_valid<=0;if(first_last)state<=PREPARE;end\n'
         '                    else if(s_axis_rx_tvalid&&s_axis_rx_tready&&s_axis_rx_tlast)state<=PREPARE;end'),
        ('commit_allowed<=!packet_fatal&&!p_prepared_failed;',
         'commit_allowed<=!packet_fatal&&!p_prepared_failed&&!(ctl_result_valid&&ctl_result_status!=0);'),
        ('WAIT_PACKET:if(p_packet_result_valid)state<=p_packet_committed?PACKET_RESULT:CLOSE_SEND;',
         'WAIT_PACKET:if(p_packet_result_valid)state<=control_early_failed?CLOSE_SEND:CONTROL_FINISH_SEND;\n'
         '                CONTROL_FINISH_SEND:if(control_early_failed)state<=CLOSE_SEND;else if(ctl_finish_ready)state<=CONTROL_FINISH_WAIT;\n'
         '                CONTROL_FINISH_WAIT:if(ctl_result_valid)begin\n'
         '                    packet_control_error<=ctl_result_status;packet_control_cause<=ctl_result_detail;packet_control_memory<=ctl_result_memory_status;\n'
         '                    if(ctl_result_status!=0)begin packet_fatal<=1;raw_status<=11;raw_detail<=ctl_result_detail;raw_memory<=ctl_result_memory_status;raw_h2<=2;end\n'
         '                    state<=ctl_result_status==0&&p_packet_committed?PACKET_RESULT:CLOSE_SEND;end'),
        ('PACKET_RESULT:if(p_packet_result_valid&&packet_result_ready)state<=IDLE;',
         'PACKET_RESULT:if(p_packet_result_valid&&packet_result_ready)begin control_packet_active<=0;state<=IDLE;end'),
    )
    for old,new in replacements:source=replace_once(source,old,new)
    additions=['assign command_control_status=command_control_error;',
        'assign packet_control_status=packet_control_error;assign packet_control_detail=packet_control_cause;assign packet_control_memory_status=packet_control_memory;',
        'assign control_drop_events=control_early_failed;',
        'assign ctl_start_valid=state==CONTROL_OPEN_SEND||state==CONTROL_PACKET_SEND;',
        'assign ctl_start_format=state==CONTROL_OPEN_SEND;assign ctl_start_maintenance=state==CONTROL_OPEN_SEND&&saved_grant;',
        'assign ctl_start_user=state==CONTROL_OPEN_SEND?saved_command_user:packet_owner;',
        'assign ctl_finish_valid=state==CONTROL_FINISH_SEND&&!control_early_failed;',
        'assign ctl_finish_commit=p_packet_committed&&!packet_fatal;',
        'assign ctl_result_ready=state==CONTROL_OPEN_WAIT||state==CONTROL_FINISH_WAIT||control_packet_active&&!control_early_failed;']
    for n in('context_base','context_bytes','window_base','window_bytes','work_floor'):additions.append(f'assign ctl_cfg_{n}=owned_cfg_{n};')
    for n in('stream_base','stream_bytes'):additions.append(f'assign ctl_cfg_{n}=owned_{n};')
    for n in('journal_base','journal_bytes','slot_bytes'):additions.append(f'assign ctl_cfg_{n}=owned_control_{n};')
    source=source.replace('endmodule','\n'.join(additions)+'\nendmodule');emit('http2_journaled_parser_transport',source)

    core=read('http2_initialized_parser_core');old_name='http2_initialized_parser_core'
    original_ports=ports(core,old_name);public=[(d,f'[24*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in original_ports]
    public=[('output'if n=='flow_event_ready'else d,w,n)for d,w,n in public]
    public += extra
    cp=ports(read('http2_journaled_controls'),'http2_journaled_controls');names={n for _,_,n in public}
    for d,w,n in cp:
        if n.startswith(('notice_','cancel_','classify_')):
            assert n not in names;public.append((d,w,n));names.add(n)
        elif n.startswith('control_'):
            public.append((d,w,'journal_'+n))
    public += [('output','','journal_recovery_required'),('output',addr,'journal_recovery_address')]
    stop=header_end(core,old_name);body=core[core.index(';',stop)+1:]
    start,end,params,forward=instance(body,'http2_initialized_parser_transport','forward')
    forward.update({n:n for _,_,n in extra+lifecycle})
    body=body[:start]+named_instance('http2_journaled_parser_transport',params,'forward',forward)+body[end:]
    start,end,params,reverse=instance(body,'rpc_grpc_initialized_return','reverse')
    for _,_,n in ports(read('rpc_grpc_initialized_return'),'rpc_grpc_initialized_return'):
        if n.startswith('m_axis_tx_'):reverse[n]='return_'+n
    body=body[:start]+named_instance('rpc_grpc_initialized_return',params,'reverse',reverse)+body[end:]
    # Add committed controls as a third owner of the existing window front.
    for old,new in(
        ('external_window_send&&window_req_valid;', 'control_window_send?ctl_window_req_valid:external_window_send&&window_req_valid;'),
        ('assign service_window_rsp_ready=window_owner==2?init_window_rsp_ready:window_owner==4&&window_rsp_ready;',
         'assign service_window_rsp_ready=window_owner==2?init_window_rsp_ready:window_owner==6?ctl_window_rsp_ready:window_owner==4&&window_rsp_ready;'),
        ('0:if(init_window_req_valid)window_owner<=1;else if(window_req_valid)window_owner<=3;',
         '0:if(init_window_req_valid)window_owner<=1;else if(ctl_window_req_valid)window_owner<=5;else if(window_req_valid)window_owner<=3;'),
        ('4:if(service_window_rsp_valid&&window_rsp_ready)window_owner<=0;',
         '4:if(service_window_rsp_valid&&window_rsp_ready)window_owner<=0;\n'
         '        5:if(ctl_window_req_valid&&service_window_req_ready)window_owner<=6;\n'
         '        6:if(service_window_rsp_valid&&ctl_window_rsp_ready)window_owner<=0;'),
        ('assign idle=f_idle&&response_idle&&!rx_active&&!s_axis_generated_tvalid;',
         'assign idle=f_idle&&response_idle&&journal_idle&&tx_idle&&!rx_active&&!s_axis_generated_tvalid;'),
        ('wire reverse_admit=owned_stream_valid&&!return_pending&&!cfg_unlock&&!control_valid&&',
         'wire reverse_admit=owned_stream_valid&&!return_pending&&!cfg_unlock&&!control_valid&&!journal_recovery_required&&'),
        ('wire lookup_admit=return_pending&&forward_quiet&&!rx_active&&!control_valid;',
         'wire lookup_admit=return_pending&&forward_quiet&&!rx_active&&!control_valid&&!journal_recovery_required;'),
        ('wire allow_new_rx=!(s_axis_generated_tvalid&&reverse_admit)&&!(r_directory_valid&&lookup_admit);',
         'wire allow_new_rx=!journal_recovery_required&&!(s_axis_generated_tvalid&&reverse_admit)&&!(r_directory_valid&&lookup_admit);'),
    ):body=replace_once(body,old,new)
    for d,w,n in cp:
        if n.startswith('window_')and d=='output'and n not in('window_req_valid','window_rsp_ready'):
            body=replace_once(body,f'forward_window_send?init_{n}:{n};',f'forward_window_send?init_{n}:control_window_send?ctl_{n}:{n};')
    lines=[f'wire {w} {n};'for _,w,n in lifecycle]
    lines += ['wire control_window_send=window_owner==5;','wire journal_idle,tx_idle;',
        'assign ctl_window_req_ready=control_window_send&&service_window_req_ready;',
        'assign ctl_window_rsp_valid=window_owner==6&&service_window_rsp_valid;',
        'assign flow_event_ready=control_drop_events?1\'b1:ctl_flow_ready;', 'wire ctl_flow_ready;']
    for d,w,n in cp:
        if n.startswith('window_'):lines.append(f'wire {w} ctl_{n};')
    for d,w,n in cp:
        if n.startswith('window_rsp_')and d=='input'and n!='window_rsp_valid':lines.append(f'assign ctl_{n}=service_{n};')
    cc={}
    for d,w,n in cp:
        if n in('clk','rst'):cc[n]=n
        elif n in MEMORY:
            bits=MEMORY[n][0];cc[n]=f'{n}[23*{bits}+:{bits}]'
        elif n.startswith('start_'):
            cc[n]="1'b1"if n=='start_authority'else'ctl_'+n
        elif n.startswith('cfg_'):cc[n]='ctl_'+n
        elif n.startswith('finish_')or n in('result_valid','result_ready','result_status','result_detail','result_memory_status'):cc[n]='ctl_'+n
        elif n.startswith('s_'):cc[n]='flow_event_valid&&!control_drop_events'if n=='s_valid'else'ctl_flow_ready'if n=='s_ready'else'flow_event_'+n[2:]
        elif n.startswith('window_'):cc[n]='ctl_'+n
        elif n.startswith(('notice_','cancel_','classify_')):cc[n]=n
        elif n.startswith('control_'):cc[n]='journal_'+n
        elif n=='recovery_required':cc[n]='journal_recovery_required'
        elif n=='recovery_address':cc[n]='journal_recovery_address'
        elif n=='idle':cc[n]='journal_idle'
        elif n.startswith('m_axis_tx_'):cc[n]='ack_'+n
        else:cc[n]=''
    for _,w,n in cp:
        if n.startswith('m_axis_tx_'):lines +=[f'wire {w} ack_{n};',f'wire {w} return_{n};']
    lines.append(named_instance('http2_journaled_controls','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','controls',cc))
    txp=ports(read('axis_frame_arbiter'),'axis_frame_arbiter');tc={}
    for _,_,n in txp:
        tc[n]='return_m_axis_tx_'+n[7:]if n.startswith('a_axis_')else'ack_m_axis_tx_'+n[7:]if n.startswith('b_axis_')else'm_axis_tx_'+n[7:]if n.startswith('m_axis_')else'tx_idle'if n=='idle'else n
    lines.append(named_instance('axis_frame_arbiter','.DATA_WIDTH(512),.KEEP_WIDTH(64),.USER_WIDTH(USER_WIDTH)','tx_arbiter',tc))
    params='parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384'
    generated='`timescale 1ns/1ps\n`default_nettype none\nmodule http2_journaled_parser_core #(\n'+params+'\n)(\n'+',\n'.join(f'{d} wire {w} {n}'for d,w,n in public)+'\n);\n'+'\n'.join(lines)+'\n'+body
    emit('http2_journaled_parser_core',generated)
    kept=[*range(1,5),*range(13,24)]
    ap=[(d,f'[15*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in public if not n.startswith('m_axis_tokens_')]
    lines=['`timescale 1ns/1ps','`default_nettype none','module http2_journaled_parser_application #(\n'+params+'\n)(\n'+',\n'.join(f'{d} wire {w} {n}'for d,w,n in ap)+'\n);']
    for n,(bits,d)in MEMORY.items():
        lines.append(f'wire [24*{bits}-1:0] all_{n};')
        for compact,old in enumerate(kept):
            left=f'all_{n}[{old}*{bits}+:{bits}]';right=f'{n}[{compact}*{bits}+:{bits}]'
            lines.append(f'assign {right}={left};'if d=='output'else f'assign {left}={right};')
        if d=='input':
            for old in[0,*range(5,13)]:lines.append(f'assign all_{n}[{old}*{bits}+:{bits}]=0;')
    connections={n:'all_'+n if n in MEMORY else"1'b0"if n=='m_axis_tokens_tready'else''if n.startswith('m_axis_tokens_')else n for _,_,n in public}
    lines +=[named_instance('http2_journaled_parser_core','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)','core',connections),'endmodule','`default_nettype wire','']
    emit('http2_journaled_parser_application','\n'.join(lines))
    (root/'build/validation/http2-journaled-parser-generation.json').write_text(json.dumps(dict(phase='generated_raw_committed_control_join',
        input_sha256=inputs,generated_sha256=outputs,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        parser_memory_clients=15,single_external_window_service=True,post_commit_gpu_cancellation_complete=False,
        non_window_controllers_complete=False,full_system_complete=False),indent=2)+'\n')
    print('Generated raw journal/ACK Parser with fifteen clients and the existing shared window service')


if __name__=='__main__':main()
