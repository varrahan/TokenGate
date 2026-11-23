"""Join real RPC progress, header/data/trailer wire sequencing and freeze scope."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports,instance,named_instance,rename
from generate_lifecycle_send_windows import replace_once
from generate_rpc_http2_progress import TRANSPORT_PORTS

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];sources=[];targets=[]
    def read(name):
        p=source_path(root, f'rtl/{name}.v');sources.append(p);return p.read_text()
    def emit(name,text):
        p=source_path(root, f'rtl/{name}.v');p.write_text(text);targets.append(p)
    scope=('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor')
    service=rename(read('http2_fenced_pipelined_grants'),'http2_fenced_pipelined_grants','http2_enveloped_frame_grants')
    service_extra=[('input','','envelope_owned'),('input','','envelope_drained'),
        ('input','[USER_WIDTH-1:0]','envelope_owner'),('input','[30:0]','envelope_stream')]
    service_extra +=[('input','[MEMORY_ADDR_WIDTH:0]'if n.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]','envelope_cfg_'+n)for n in scope]
    service=add_ports(service,'http2_enveloped_frame_grants',service_extra)
    service=replace_once(service,'wire control_allowed=window_req_op!=5&&(!close_control||!control_matches_frame||\n    (saved_frame_match&&!wire_pending&&!tracking_error));',
        '// Window request fields stay stable until their real handshake. Compare\n'
        '// the wide arena scope before allowing a close, rather than placing it\n'
        '// ahead of every downstream request mux and the public idle reduction.\n'
        '// A newly acquired envelope invalidates the comparison for one cycle;\n'
        '// no comparison against the preceding descriptor can authorize a close.\n'
        'reg envelope_scope_compared;reg [6:0] envelope_scope_equal;\n'
        'always @(posedge clk)begin\n'
        '    if(rst)begin envelope_scope_compared<=0;envelope_scope_equal<=0;end\n'
        '    else begin\n'
        '        if(!window_req_valid||!envelope_owned||window_req_ready)envelope_scope_compared<=0;\n'
        '        else envelope_scope_compared<=1;\n'
        '        envelope_scope_equal<={'+','.join('window_cfg_'+n+'==envelope_cfg_'+n for n in reversed(scope))+'};\n'
        '    end\n'
        'end\n'
        'wire control_matches_envelope=envelope_owned&&window_req_user==envelope_owner&&window_req_stream==envelope_stream&&\n'
        '    (&envelope_scope_equal);\n'
        'wire envelope_close_fence=frozen&&frozen_user==envelope_owner&&frozen_stream==envelope_stream&&\n'
        '    envelope_drained&&!wire_pending&&state!=RESERVE&&!tracking_error;\n'
        'wire control_allowed=window_req_op!=5&&(!close_control||\n'
        '    ((!control_matches_frame||saved_frame_match&&!wire_pending&&!tracking_error)&&\n'
        '     (!envelope_owned||envelope_scope_compared&&(!control_matches_envelope||envelope_close_fence))));')
    emit('http2_enveloped_frame_grants',service)
    extra=[('input','','envelope_freeze'),('input','','envelope_wire_fenced'),('output','','envelope_drained'),
        ('output','','envelope_recovery_required'),('output','[7:0]','envelope_error_status'),
        ('output','[7:0]','envelope_error_memory_status'),('output','','data_frame_tx_done')]
    text=rename(read('rpc_grpc_cancel_parser_response'),'rpc_grpc_cancel_parser_response','rpc_grpc_http2_parser_response')
    backend=read('rpc_http2_response_partition');seq=read('grpc_rpc_envelope');headers=read('grpc_response_headers')
    text=add_ports(text,'rpc_grpc_http2_parser_response',extra)
    declarations=[]
    for d,w,n in TRANSPORT_PORTS:declarations.append('wire '+w.replace('reg ','')+' '+n+';')
    declarations +=['wire seq_data_admit,seq_terminal,seq_private_failed,seq_header_select,seq_idle,seq_cancelled;',
        'wire [31:0] seq_header_bytes;wire [1:0] seq_header_frames;',
        'wire [511:0] body_tdata,header_tdata;wire [63:0] body_tkeep,header_tkeep;',
        'wire body_tvalid,body_tready,body_tlast,header_tvalid,header_tready,header_tlast;',
        'wire [USER_WIDTH-1:0] body_tuser,header_tuser;',
        'wire header_req_valid,header_req_ready,header_abort_valid,header_abort_ready,header_result_valid,header_result_ready;',
        'wire [1:0] header_req_kind,header_req_encoding,header_result_kind;',
        'wire [USER_WIDTH-1:0] header_req_user,header_result_user;wire [30:0] header_req_stream,header_result_stream;',
        'wire [7:0] header_result_status;wire header_result_tx_emitted,header_idle;wire [6:0] header_result_wire_bytes;',
        'assign data_frame_tx_done=body_tvalid&&body_tready&&body_tlast;',
        'assign m_axis_tx_tdata=seq_header_select?header_tdata:body_tdata;',
        'assign m_axis_tx_tkeep=seq_header_select?header_tkeep:body_tkeep;',
        'assign m_axis_tx_tvalid=seq_header_select?header_tvalid:body_tvalid&&seq_data_admit;',
        'assign m_axis_tx_tlast=seq_header_select?header_tlast:body_tlast;',
        'assign m_axis_tx_tuser=seq_header_select?header_tuser:body_tuser;',
        'assign header_tready=seq_header_select&&m_axis_tx_tready;',
        'assign body_tready=!seq_header_select&&seq_data_admit&&m_axis_tx_tready;']
    text=replace_once(text,'reg active,kill_ungranted,', '\n'.join(declarations)+'\nreg active,kill_ungranted,')
    text=replace_once(text,'wire accept_guard=!active&&!transport_recovery;',
        'wire accept_guard=!active&&!transport_recovery&&seq_idle&&!envelope_recovery_required&&!rpc_recovery&&!service_abort;')
    text=replace_once(text,'assign frame_req_valid=framer_valid&&authorized;',
        'assign frame_req_valid=framer_valid&&authorized&&seq_data_admit;')
    text=replace_once(text,'wire failed_before_grant=rpc_result_valid&&rpc_status!=0;',
        'wire failed_before_grant=rpc_result_valid&&rpc_status!=0||seq_private_failed;')
    text=replace_once(text,'assign result_valid=active&&rpc_result_valid&&(!directory_requested||release_pending)&&',
        'assign result_valid=active&&rpc_result_valid&&(!directory_requested||release_pending)&&seq_terminal&&!transport_busy&&!transport_retirement_pending&&')
    text=replace_once(text,"assign result_stage=rpc_status!=0?rpc_stage:framer_status!=0?8'd16:8'd0;",
        "assign result_stage=rpc_status!=0?rpc_stage:envelope_error_status!=0?8'd20:seq_cancelled?8'd17:framer_status!=0?8'd16:8'd0;")
    text=replace_once(text,'assign result_status=rpc_status!=0?rpc_status:framer_status;',
        "assign result_status=rpc_status!=0?rpc_status:envelope_error_status!=0?envelope_error_status:seq_cancelled?8'd1:framer_status;")
    text=replace_once(text,"assign result_memory_status=rpc_status!=0?rpc_memory:8'd0;",
        "assign result_memory_status=rpc_status!=0?rpc_memory:envelope_error_memory_status;")
    text=replace_once(text,'assign result_wire_bytes=framer_wire_bytes;assign result_frames=framer_frames;',
        'assign result_wire_bytes=framer_wire_bytes+seq_header_bytes;assign result_frames=framer_frames+seq_header_frames;')
    text=replace_once(text,'assign result_tx_emitted=framer_tx_emitted;',
        'assign result_tx_emitted=framer_tx_emitted||seq_header_frames!=0;')
    text=replace_once(text,'assign result_cancelled=rpc_result_valid&&(rpc_cancelled||rpc_status==0&&expected_closed);',
        'assign result_cancelled=rpc_result_valid&&(rpc_cancelled||rpc_status==0&&(expected_closed||seq_cancelled));')
    text=replace_once(text,'assign recovery_required=rpc_recovery||transport_recovery||transport_failure;',
        'assign recovery_required=rpc_recovery||transport_recovery||transport_failure||envelope_recovery_required;')
    text=replace_once(text,'assign idle=!active&&!kill_ungranted&&rpc_idle&&framer_idle;',
        'assign idle=!active&&!kill_ungranted&&rpc_idle&&framer_idle&&seq_idle&&header_idle;')
    start,end,params,connections=instance(text,'rpc_cancel_response_partition','rpc')
    connections.update({n:n for _,_,n in TRANSPORT_PORTS})
    text=text[:start]+named_instance('rpc_http2_response_partition',params,'rpc',connections)+text[end:]
    start,end,params,connections=instance(text,'grpc_registered_input_framer','framer')
    for _,_,n in ports(read('grpc_registered_input_framer'),'grpc_registered_input_framer'):
        if n.startswith('m_axis_tx_'):connections[n]='body_'+n[10:]
    # The actual framer must see the same grant handshake exposed to the sole
    # scheduler; initial-header metadata cannot accept a hidden DATA grant.
    connections['frame_req_ready']='frame_req_ready&&authorized&&seq_data_admit'
    text=text[:start]+named_instance('grpc_registered_input_framer',params,'framer',connections)+text[end:]
    sc=dict(clk='clk',rst='rst',accept='accept',accept_user='s_axis_tokens_tuser',accept_stream='s_stream',
        rpc_valid='rpc_result_valid&&(!directory_requested||release_pending)',rpc_status='rpc_status',rpc_eos='result_eos',
        rpc_format='transport_result_format',header_intent='transport_header_intent',headers_sent='transport_headers_sent',
        framer_result='framer_result',framer_status='framer_status',matching_freeze='envelope_freeze',wire_fenced='envelope_wire_fenced',
        data_admit='seq_data_admit',terminal_admit='seq_terminal',private_failed='seq_private_failed',drained='envelope_drained',
        recovery_required='envelope_recovery_required',expected_cancelled='seq_cancelled',error_status='envelope_error_status',error_memory_status='envelope_error_memory_status',
        metadata_req_valid='transport_req_valid',metadata_req_ready='transport_req_ready',metadata_req_op='transport_req_op',
        metadata_private_abort_proof='transport_private_abort_proof',metadata_rsp_valid='transport_rsp_valid',metadata_rsp_ready='transport_rsp_ready',
        metadata_rsp_status='transport_rsp_status',metadata_rsp_memory_status='transport_rsp_memory_status',header_select='seq_header_select',
        retire='retire',idle='seq_idle',header_wire_bytes='seq_header_bytes',header_frames='seq_header_frames')
    for _,_,n in ports(seq,'grpc_rpc_envelope'):
        if n.startswith('header_')and n not in sc:sc[n]=n
    hc={n:n for _,_,n in ports(headers,'grpc_response_headers')}
    hc.update(req_grpc_status="32'd0",wire_fenced='envelope_wire_fenced',idle='header_idle')
    for _,_,n in ports(headers,'grpc_response_headers'):
        if n.startswith(('req_','abort_','result_'))and n!='req_grpc_status':hc[n]='header_'+n
        elif n.startswith('m_axis_tx_'):hc[n]='header_'+n[10:]
    end=text.rindex('endmodule');text=text[:end]+named_instance('grpc_rpc_envelope','.USER_WIDTH(USER_WIDTH)','envelope',sc)+'\n'+named_instance('grpc_response_headers','.USER_WIDTH(USER_WIDTH)','headers',hc)+text[end:]
    emit('rpc_grpc_http2_parser_response',text)

    text=rename(read('rpc_grpc_cancellable_return'),'rpc_grpc_cancellable_return','rpc_grpc_http2_return')
    public=[p for p in extra if p[2]!='data_frame_tx_done'and p[0]=='output']
    public +=[('input','[MEMORY_ADDR_WIDTH:0]'if n.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]','freeze_cfg_'+n)for n in scope]
    text=add_ports(text,'rpc_grpc_http2_return',public)
    start,end,params,connections=instance(text,'rpc_grpc_cancel_parser_response','response')
    connections.update({n:n for _,_,n in extra if n!='data_frame_tx_done'and n.startswith('envelope_')})
    connections.update(envelope_freeze='envelope_match_freeze',envelope_wire_fenced='data_wire_paused',data_frame_tx_done='response_data_done')
    text=text[:start]+named_instance('rpc_grpc_http2_parser_response',params,'response',connections)+text[end:]
    wires=['wire response_data_done,envelope_match_freeze,grant_freeze_ready,grant_freeze_drained,grant_release_ready,grant_tracking_error;',
        'wire grant_frozen;reg [USER_WIDTH-1:0] envelope_owner;reg [30:0] envelope_stream;',
        'reg envelope_owned;reg [USER_WIDTH-1:0] envelope_frozen_user;reg [30:0] envelope_frozen_stream;']
    cap=[];reset=[];checks=[];incoming=[]
    for n in scope:
        w='[MEMORY_ADDR_WIDTH:0]'if n.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]'
        wires.append(f'reg {w} envelope_frozen_{n};')
        reset.append(f'envelope_frozen_{n}<=0;');cap.append(f'envelope_frozen_{n}<=freeze_cfg_{n};')
        checks.append(f'envelope_frozen_{n}==saved_frame_cfg_{n}')
        incoming.append(f'freeze_cfg_{n}==saved_frame_cfg_{n}')
    wires +=['wire envelope_saved_match=grant_frozen&&envelope_owned&&envelope_frozen_user==envelope_owner&&envelope_frozen_stream==envelope_stream&&'+ '&&'.join(checks)+';',
        'wire envelope_incoming_match=freeze_valid&&freeze_ready&&envelope_owned&&freeze_user==envelope_owner&&freeze_stream==envelope_stream&&'+'&&'.join(incoming)+';',
        'assign envelope_match_freeze=envelope_saved_match||envelope_incoming_match;',
        'assign freeze_ready=grant_freeze_ready;assign freeze_drained=grant_freeze_drained&&(!envelope_saved_match||envelope_drained);',
        'assign freeze_release_ready=grant_release_ready&&(!envelope_saved_match||envelope_drained);',
        'assign frame_tracking_error=grant_tracking_error||envelope_recovery_required;',
        'always @(posedge clk)begin',
        'if(rst)begin envelope_owner<=0;envelope_stream<=0;envelope_owned<=0;envelope_frozen_user<=0;envelope_frozen_stream<=0;'+''.join(reset)+'end',
        'else begin',
        'if(s_axis_tokens_tvalid&&s_axis_tokens_tready)begin envelope_owner<=s_axis_tokens_tuser;envelope_stream<=s_stream;envelope_owned<=1;end',
        'if(retire)envelope_owned<=0;',
        'if(freeze_valid&&freeze_ready)begin envelope_frozen_user<=freeze_user;envelope_frozen_stream<=freeze_stream;'+''.join(cap)+'end',
        'end end']
    text=replace_once(text,'wire [511:0] data_tdata;', '\n'.join(wires)+'\nwire [511:0] data_tdata;')
    start,end,params,connections=instance(text,'http2_fenced_pipelined_grants','directory_service')
    connections.update(freeze_ready='grant_freeze_ready',freeze_drained='grant_freeze_drained',freeze_active='grant_frozen',
        freeze_release_ready='grant_release_ready',freeze_release_valid='freeze_release_valid&&(!envelope_saved_match||envelope_drained)',
        frame_tracking_error='grant_tracking_error',frame_tx_done='response_data_done')
    connections.update(envelope_owned='envelope_owned',envelope_drained='envelope_drained',envelope_owner='envelope_owner',envelope_stream='envelope_stream')
    connections.update({'envelope_cfg_'+n:'saved_frame_cfg_'+n for n in scope})
    text=text[:start]+named_instance('http2_enveloped_frame_grants',params,'directory_service',connections)+text[end:]
    # A is now every RPC frame, while the scheduler witness remains DATA-only.
    text=replace_once(text,'.a_pause(freeze_binding_valid&&freeze_drained)',
        '.a_pause(envelope_match_freeze&&!frame_wire_pending)')
    text=replace_once(text,'assign control_idle=!generic_pending&&!control_req_valid&&!control_rsp_valid;',
        'assign control_idle=!generic_pending&&!control_req_valid&&!control_rsp_valid;\nassign freeze_active=grant_frozen;')
    emit('rpc_grpc_http2_return',text)
    source_harness=root/'sim/cocotb_rpc_cancel_top.sv';sources.append(source_harness)
    harness=source_harness.read_text().replace('module cocotb_rpc_cancel_top;','module cocotb_rpc_http2_top;')
    start,end,params,connections=instance(harness,'rpc_grpc_cancellable_return','dut')
    existing=set(connections);declarations=[]
    for d,w,n in ports(text,'rpc_grpc_http2_return'):
        if n not in existing:
            connections[n]=n;declarations.append(('reg 'if d=='input'else'wire ')+w+' '+n+('=0'if d=='input'else'')+';')
    harness=harness[:start]+'\n'.join(declarations)+'\n'+named_instance('rpc_grpc_http2_return',params,'dut',connections)+harness[end:]
    path=root/'sim/cocotb_rpc_http2_top.sv';path.write_text(harness);targets.append(path)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/rpc-http2-return-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_rpc_response_envelope',input_sha256={source_relative(p, root).as_posix():sha(p)for p in[*sources,Path(__file__)]},
        generated_sha256={source_relative(p, root).as_posix():sha(p)for p in targets},
        data_wire_witness_separate_from_header_wire=True,header_trailer_progress_uses_actual_rpc_owner=True,
        full_system_complete=False),indent=2)+'\n')
    print('Generated actual RPC initial headers, granted DATA, durable trailers and scoped wire freeze')


if __name__=='__main__':main()
