"""Join the real response envelope to raw committed HTTP/2 control and admission."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports,instance,named_instance,rename
from generate_lifecycle_send_windows import replace_once

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];sources=[];targets=[]
    def read(n):
        p=source_path(root, f'rtl/{n}.v');sources.append(p);return p.read_text()
    def emit(n,text):
        p=source_path(root, f'rtl/{n}.v');p.write_text(text);targets.append(p)
    controller=rename(read('http2_stream_shutdown'),'http2_stream_shutdown','http2_enveloped_shutdown')
    failure_ports=[('input','','return_envelope_recovery'),('input','[7:0]','return_envelope_status'),
        ('input','[7:0]','return_envelope_memory_status')]
    controller=add_ports(controller,'http2_enveloped_shutdown',failure_ports)
    old='if(frame_tracking_error)fail(7,2,0,1,2,1);'
    assert controller.count(old)==2
    controller=controller.replace(old,'if(frame_tracking_error)begin\n'
        '                    if(return_envelope_recovery)fail(return_envelope_status,20,return_envelope_memory_status,1,2,1);\n'
        '                    else fail(7,2,0,1,2,1);end ')
    emit('http2_enveloped_shutdown',controller)
    core=rename(read('http2_shutdown_parser_core'),'http2_shutdown_parser_core','http2_enveloped_parser_core')
    response=read('rpc_grpc_http2_return')
    public=[p for p in ports(response,'rpc_grpc_http2_return')if p[0]=='output'and p[2].startswith('envelope_')]
    core=add_ports(core,'http2_enveloped_parser_core',public)
    start,end,params,connections=instance(core,'rpc_grpc_cancellable_return','reverse')
    connections.update({n:n for _,_,n in public})
    for _,_,n in ports(response,'rpc_grpc_http2_return'):
        if n.startswith('freeze_cfg_'):connections[n]='shutdown_owned_'+n[11:]
    core=core[:start]+named_instance('rpc_grpc_http2_return',params,'reverse',connections)+core[end:]
    start,end,params,connections=instance(core,'http2_stream_shutdown','shutdown')
    connections.update(return_envelope_recovery='envelope_recovery_required',return_envelope_status='envelope_error_status',
        return_envelope_memory_status='envelope_error_memory_status')
    core=core[:start]+named_instance('http2_enveloped_shutdown',params,'shutdown',connections)+core[end:]
    core=replace_once(core,'else if(window_req_valid&&!shutdown_recovery_required)window_owner<=3;',
        'else if(window_req_valid&&!shutdown_recovery_required&&!response_recovery_required)window_owner<=3;')
    assert core.count('!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required)')==2
    core=core.replace('!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required)',
        '!cancel_valid&&!shutdown_busy&&!shutdown_recovery_required&&!response_recovery_required)')
    core=replace_once(core,'wire allow_config=!return_pending&&!generated_offered&&!shutdown_busy&&!cancel_valid&&!shutdown_recovery_required;',
        'wire allow_config=!return_pending&&!generated_offered&&!shutdown_busy&&!cancel_valid&&!shutdown_recovery_required&&!response_recovery_required;')
    core=replace_once(core,'wire allow_new_rx=!journal_recovery_required&&',
        'wire allow_new_rx=!journal_recovery_required&&!response_recovery_required&&')
    emit('http2_enveloped_parser_core',core)
    application=rename(read('http2_shutdown_parser_application'),'http2_shutdown_parser_application','http2_enveloped_parser_application')
    application=add_ports(application,'http2_enveloped_parser_application',public)
    start,end,params,connections=instance(application,'http2_shutdown_parser_core','core')
    connections.update({n:n for _,_,n in public})
    application=application[:start]+named_instance('http2_enveloped_parser_core',params,'core',connections)+application[end:]
    emit('http2_enveloped_parser_application',application)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/http2-enveloped-parser-generation.json').write_text(json.dumps(dict(
        phase='generated_raw_rpc_response_envelope',input_sha256={source_relative(p, root).as_posix():sha(p)for p in[*sources,Path(__file__)]},
        generated_sha256={source_relative(p, root).as_posix():sha(p)for p in targets},parser_memory_clients=17,
        typed_raw_reset_carries_envelope_memory_failure=True,full_system_complete=False),indent=2)+'\n')
    print('Generated raw Parser with actual RPC response HEADERS/DATA/trailers and scoped reset ownership')


if __name__=='__main__':main()
