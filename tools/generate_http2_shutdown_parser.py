"""Join committed resets to the actual RPC/window/directory/peer owners."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import MEMORY,header_end,instance,named_instance

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];sources=[];targets=[]
    def read(n):
        p=source_path(root, f'rtl/{n}.v');sources.append(p);return p.read_text()
    def emit(n,text):
        p=source_path(root, f'rtl/{n}.v');p.write_text(text);targets.append(p)
    core=read('http2_classified_parser_core');cp=ports(read('http2_shutdown_classified_controls'),'http2_shutdown_classified_controls')
    rp=ports(read('rpc_grpc_cancellable_return'),'rpc_grpc_cancellable_return')
    sp=ports(read('http2_stream_shutdown'),'http2_stream_shutdown')
    public=[('output'if n in('cancel_ready','cancel_result_valid','cancel_status')else d,w,n)for d,w,n in ports(core,'http2_classified_parser_core')]
    public += [('output','','response_result_cancelled'),('output','','response_result_retirement_pending'),
        ('output','','shutdown_busy'),('output','','shutdown_recovery_required'),('output','','reset_processed'),
        ('output','[31:0]','resets_processed'),('output','[31:0]','goaways_processed'),
        ('output','[7:0]','shutdown_status'),('output','[7:0]','shutdown_detail'),('output','[7:0]','shutdown_memory_status')]
    public +=[p for p in cp if p[2].startswith('peer_goaway_')]
    stop=header_end(core,'http2_classified_parser_core');body=core[core.index(';',stop)+1:]
    declarations=[];declared={n for _,_,n in public}
    def wire(w,n):
        if n not in declared:declarations.append(f'wire {w} {n};');declared.add(n)
    start,end,params,old=instance(body,'http2_classified_peer_controls','controls')
    cc={}
    for d,w,n in cp:
        if n in old:cc[n]=old[n]
        elif n in declared:cc[n]=n
        else:wire(w,n);cc[n]=n
    body=body[:start]+named_instance('http2_shutdown_classified_controls',params,'controls',cc)+body[end:]
    start,end,_,_=instance(body,'axis_frame_arbiter','tx_arbiter');body=body[:start]+'assign tx_idle=response_idle;\n'+body[end:]
    start,end,params,old=instance(body,'rpc_grpc_initialized_return','reverse');rc=dict(old)
    for d,w,n in rp:
        if n not in rc:wire(w,'shutdown_return_'+n);rc[n]='shutdown_return_'+n
    rc['result_cancelled']='response_result_cancelled';rc['result_retirement_pending']='response_result_retirement_pending'
    for _,_,n in rp:
        if n.startswith('m_axis_tx_'):rc[n]=n
        elif n.startswith('b_axis_'):rc[n]='ack_m_axis_tx_'+n[7:]
    # The actual generic directory port has one owner through its response.
    # A callback CLOSE cannot go around the production cached LOAD or pool lock.
    dirports=[p for p in rp if p[2].startswith(('control_req_','control_rsp_','control_pool_'))]
    directory=[]
    shutdown_values=dict(control_req_op="3'd3",control_pool_base='shutdown_owned_stream_base',control_pool_bytes='shutdown_owned_stream_bytes',
        control_req_user='shutdown_close_user',control_req_stream='shutdown_close_stream',control_req_generation='shutdown_directory_generation',control_req_address='shutdown_directory_address')
    for d,w,n in dirports:
        wire(w,'service_'+n);rc[n]='service_'+n
        if n=='control_req_valid':directory.append('assign service_control_req_valid=shutdown_dir_owner==1?dir_req_valid:shutdown_dir_owner==3&&shutdown_directory_valid;')
        elif n=='control_req_ready':directory +=['assign dir_req_ready=shutdown_dir_owner==1&&service_control_req_ready;',
            'assign shutdown_directory_ready=shutdown_dir_owner==3&&service_control_req_ready;']
        elif n=='control_rsp_valid':directory +=['assign dir_rsp_valid=shutdown_dir_owner==2&&service_control_rsp_valid;',
            'assign shutdown_directory_rsp_valid=shutdown_dir_owner==4&&service_control_rsp_valid;']
        elif n=='control_rsp_ready':directory.append('assign service_control_rsp_ready=shutdown_dir_owner==2?dir_rsp_ready:shutdown_dir_owner==4&&shutdown_directory_rsp_ready;')
        elif d=='input':directory.append(f'assign service_{n}=shutdown_dir_owner==3?{shutdown_values.get(n,"0")}:{old[n]};')
        else:directory.append(f'assign {old[n]}=service_{n};')
    wire('','service_directory_idle');rc['control_idle']='service_directory_idle'
    directory +=['reg [2:0] shutdown_dir_owner;',
        'assign dir_idle=service_directory_idle&&shutdown_dir_owner==0&&!shutdown_directory_valid;',
        'always @(posedge clk)begin if(rst)shutdown_dir_owner<=0;else case(shutdown_dir_owner)',
        '0:if(shutdown_directory_valid)shutdown_dir_owner<=3;else if(dir_req_valid&&!shutdown_busy)shutdown_dir_owner<=1;',
        '1:if(dir_req_valid&&service_control_req_ready)shutdown_dir_owner<=2;',
        '2:if(service_control_rsp_valid&&dir_rsp_ready)shutdown_dir_owner<=0;',
        '3:if(shutdown_directory_valid&&service_control_req_ready)shutdown_dir_owner<=4;',
        '4:if(service_control_rsp_valid&&shutdown_directory_rsp_ready)shutdown_dir_owner<=0;',
        'default:shutdown_dir_owner<=0;endcase end']
    # Four typed owners share the same real window service, with no copied ledger.
    for d,w,n in rp:
        if n.startswith(('window_rsp_binding_','window_rsp_record_address','window_rsp_generation','window_rsp_send_closed')):
            wire(w,'service_'+n);rc[n]='service_'+n
    body=body[:start]+named_instance('rpc_grpc_cancellable_return',params,'reverse',rc)+body[end:]
    body=replace_once(body,'reg [2:0] window_owner;', 'reg [3:0] window_owner;\nwire shutdown_window_send=window_owner==7;')
    body=replace_once(body,'assign service_window_req_valid=forward_window_send?',
        'assign service_window_req_valid=shutdown_window_send?shutdown_close_valid:forward_window_send?')
    body=replace_once(body,'assign service_window_rsp_ready=window_owner==2?',
        'assign service_window_rsp_ready=window_owner==8?shutdown_close_rsp_ready:window_owner==2?')
    body=replace_once(body,'else if(ctl_window_req_valid)window_owner<=5;',
        'else if(shutdown_close_valid)window_owner<=7;else if(ctl_window_req_valid)window_owner<=5;')
    # Quarantine applies to all new public work, including when a directory or
    # peer fault leaves the window engine healthy. Already selected window
    # owners still retain VALID and their response ownership until retirement.
    body=replace_once(body,'else if(window_req_valid)window_owner<=3;',
        'else if(window_req_valid&&!shutdown_recovery_required)window_owner<=3;')
    body=replace_once(body,'        default:window_owner<=0;endcase end', '''        7:if(shutdown_close_valid&&service_window_req_ready)window_owner<=8;
        8:if(service_window_rsp_valid&&shutdown_close_rsp_ready)window_owner<=0;
        default:window_owner<=0;endcase end''')
    wm=dict(window_req_op="4'd10",window_req_maintenance="1'b0",window_req_user='shutdown_close_user',window_req_stream='shutdown_close_stream',
        window_req_generation='0',window_req_record_address='0',window_req_amount='0')
    for name in('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'):
        wm['window_cfg_'+name]='shutdown_owned_'+name
    for n,v in wm.items():body=replace_once(body,f'assign service_{n}=forward_window_send?',f'assign service_{n}=shutdown_window_send?{v}:forward_window_send?')
    directory +=['assign shutdown_close_ready=shutdown_window_send&&service_window_req_ready;',
        'assign shutdown_close_rsp_valid=window_owner==8&&service_window_rsp_valid;']
    # Preserve a previously offered external directory command until accepted.
    body=replace_once(body,'assign f_control_valid=control_valid;\nassign control_ready=f_control_ready;', '''reg shutdown_control_offered;
wire shutdown_control_admit=shutdown_control_offered||(!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required);
assign f_control_valid=control_valid&&shutdown_control_admit;
assign control_ready=f_control_ready&&shutdown_control_admit;
always @(posedge clk)begin
if(rst)shutdown_control_offered<=0;
else if(f_control_valid)shutdown_control_offered<=!f_control_ready;
end''')
    body=replace_once(body,'reg rx_active,return_pending,owned_stream_valid,forward_quiet;',
        'reg rx_active,return_pending,owned_stream_valid,forward_quiet,return_ack_seen,generated_offered;\n'
        'reg [USER_WIDTH-1:0] return_user;reg [30:0] return_stream;')
    body=replace_once(body,'wire reverse_admit=owned_stream_valid', 'wire reverse_new_admit=owned_stream_valid')
    body=replace_once(body,'wire lookup_admit=return_pending',
        'wire reverse_admit=generated_offered||(reverse_new_admit&&!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required);\nwire lookup_admit=return_pending')
    body=replace_once(body,'wire allow_config=!return_pending;',
        'wire allow_config=!return_pending&&!generated_offered&&!shutdown_busy&&!cancel_valid&&!shutdown_recovery_required;')
    body=replace_once(body,'assign cfg_quiescent=f_cfg_quiescent&&!return_pending;',
        'assign cfg_quiescent=f_cfg_quiescent&&allow_config;')
    body=replace_once(body,'assign idle=f_idle&&response_idle&&journal_idle&&tx_idle&&!rx_active&&!s_axis_generated_tvalid;',
        'assign idle=f_idle&&response_idle&&journal_idle&&tx_idle&&!rx_active&&!s_axis_generated_tvalid&&!shutdown_busy&&!shutdown_recovery_required&&shutdown_dir_owner==0;')
    body=replace_once(body,'rx_active<=0;return_pending<=0;owned_stream_valid<=0;forward_quiet<=0;',
        'rx_active<=0;return_pending<=0;owned_stream_valid<=0;forward_quiet<=0;return_ack_seen<=0;generated_offered<=0;return_user<=0;return_stream<=0;')
    body=replace_once(body,'if(s_axis_generated_tvalid&&s_axis_generated_tready)return_pending<=1;\n        if(response_result_valid&&response_result_ready)return_pending<=0;', '''if(s_axis_generated_tvalid&&reverse_admit)generated_offered<=!reverse_input_ready;
        if(s_axis_generated_tvalid&&s_axis_generated_tready)begin
            return_pending<=1;return_ack_seen<=0;return_user<=s_axis_generated_tuser;return_stream<=generated_stream;
        end
        if(response_result_valid&&response_result_ready)return_ack_seen<=1;
        if(return_ack_seen&&!response_record_lease_active&&!response_result_retirement_pending)begin return_pending<=0;return_ack_seen<=0;end''')
    # Snapshot the actual return's window scope. Same user/stream in a different
    # arena is not authority to wait for, close or fabricate its private LOAD.
    scope=['reg shutdown_return_scope_match;'];checks=[]
    scope_decl=[];scope_rst=[];scope_cap=[]
    for name in('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor'):
        w='[MEMORY_ADDR_WIDTH:0]'if name.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]'
        scope_decl.append(f'reg {w} return_scope_{name};');scope_rst.append(f'return_scope_{name}<=0;')
        scope_cap.append(f'return_scope_{name}<={old["cfg_"+name]};');checks.append(f'return_scope_{name}==shutdown_owned_{name}')
    directory +=scope_decl+['assign shutdown_scope_match='+ '&&'.join(checks)+';',
        'always @(posedge clk)begin if(rst)begin '+''.join(scope_rst)+'end else if(s_axis_generated_tvalid&&s_axis_generated_tready)begin '+''.join(scope_cap)+'end end']
    # Connect every callback to actual typed services and retain all source/ACK owners.
    sc={};mapping=dict(req_valid='cancel_valid&&ctl_history_fence',req_ready='shutdown_request_ready',req_goaway='cancel_goaway',req_user='cancel_user',
        req_stream='cancel_stream',req_arg0='cancel_arg0',req_arg1='cancel_arg1',history_fence='ctl_history_fence',
        rsp_valid='cancel_result_valid',rsp_ready='cancel_result_ready',rsp_status='cancel_status',rsp_detail='cancel_detail',
        rsp_memory_status='cancel_memory_status',rsp_connection_error='cancel_connection_error',rsp_http2_error='cancel_http2_error',
        rsp_user='',rsp_stream='',busy='shutdown_busy',idle='',recovery_required='shutdown_recovery_required',
        reset_processed='reset_processed',resets_processed='resets_processed',goaways_processed='goaways_processed',
        return_key_valid='return_pending',return_scope_match='shutdown_scope_match',return_user='return_user',return_stream='return_stream')
    for d,w,n in sp:
        if n in('clk','rst'):sc[n]=n
        elif n in mapping:sc[n]=mapping[n]
        elif n.startswith('cfg_'):sc[n]='ctl_'+n
        elif n.startswith('owned_'):wire(w,'shutdown_'+n);sc[n]='shutdown_'+n
        elif n.startswith(('freeze_','frame_tracking_')):sc[n]='shutdown_return_'+n
        elif n in('close_rsp_valid','close_rsp_ready','directory_rsp_valid','directory_rsp_ready'):wire(w,'shutdown_'+n);sc[n]='shutdown_'+n
        elif n.startswith('close_rsp_'):sc[n]='service_window_rsp_record_address'if n=='close_rsp_address'else'service_window_rsp_'+n[10:]
        elif n.startswith('close_'):wire(w,'shutdown_'+n);sc[n]='shutdown_'+n
        elif n.startswith('directory_rsp_'):sc[n]='service_control_rsp_'+n[14:]
        elif n.startswith('directory_'):wire(w,'shutdown_'+n);sc[n]='shutdown_'+n
        elif n.startswith('classify_'):sc[n]='shutdown_'+n
        elif n.startswith('peer_'):
            sc[n]={'peer_valid':'goaway_req_valid','peer_ready':'goaway_req_ready','peer_last_stream':'goaway_last_stream','peer_error':'goaway_error'}.get(n,'goaway_'+n[5:])
        else:raise AssertionError(n)
    for _,w,n in sp:
        value=sc[n]
        if value and value.startswith('shutdown_')and re_identifier(value):wire(w,value)
    directory +=['assign cancel_ready=shutdown_request_ready&&ctl_history_fence;',
        'assign shutdown_status=cancel_status;assign shutdown_detail=cancel_detail;assign shutdown_memory_status=cancel_memory_status;',
        'assign goaway_user=shutdown_close_user;assign shutdown_classify_user=shutdown_close_user;assign shutdown_classify_stream=shutdown_close_stream;',
        named_instance('http2_stream_shutdown','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','shutdown',sc)]
    params='parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,FIFO_DEPTH=16,MAX_TEXT_BYTES=16384,MAX_FIELD_BYTES=16384'
    def declaration(name,ps):return '`timescale 1ns/1ps\n`default_nettype none\nmodule '+name+' #(\n'+params+'\n)(\n'+',\n'.join(f'{d} wire {w} {n}'for d,w,n in ps)+'\n);\n'
    text=declaration('http2_shutdown_parser_core',public)+'\n'.join(declarations+directory)+'\n'+body
    emit('http2_shutdown_parser_core',text)
    ap=[(d,f'[17*{MEMORY[n][0]}-1:0]'if n in MEMORY else w,n)for d,w,n in public if not n.startswith('m_axis_tokens_')]
    lines=[declaration('http2_shutdown_parser_application',ap)];kept=[*range(1,5),*range(13,26)]
    for n,(bits,d)in MEMORY.items():
        lines.append(f'wire [26*{bits}-1:0] all_{n};')
        for compact,old_index in enumerate(kept):
            left=f'all_{n}[{old_index}*{bits}+:{bits}]';right=f'{n}[{compact}*{bits}+:{bits}]'
            lines.append(f'assign {right}={left};'if d=='output'else f'assign {left}={right};')
        if d=='input':
            for index in[0,*range(5,13)]:lines.append(f'assign all_{n}[{index}*{bits}+:{bits}]=0;')
    ac={n:'all_'+n if n in MEMORY else"1'b0"if n=='m_axis_tokens_tready'else''if n.startswith('m_axis_tokens_')else n for _,_,n in public}
    lines +=[named_instance('http2_shutdown_parser_core','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.FIFO_DEPTH(FIFO_DEPTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES),.MAX_FIELD_BYTES(MAX_FIELD_BYTES)','core',ac),'endmodule','`default_nettype wire','']
    emit('http2_shutdown_parser_application','\n'.join(lines))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/http2-shutdown-parser-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_raw_shutdown_join',input_sha256={source_relative(p, root).as_posix():sha(p)for p in[*sources,Path(__file__)]},
        generated_sha256={source_relative(p, root).as_posix():sha(p)for p in targets},parser_memory_clients=17,
        external_cancel_fixture_removed=True,actual_callback_retirement_verified=False,full_system_complete=False),indent=2)+'\n')
    print('Generated raw shutdown Parser with actual shared return, directory, history and peer owners')


def re_identifier(value):return value.replace('_','').isalnum()


if __name__=='__main__':main()
