"""Require a captured private FORMAT grant through the actual window pipeline."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace
from generate_two_fpga_application import instance,named_instance,header_end


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/window-cause/rtl'
    folder=root/'build/experiments/window-authority';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={p.relative_to(root).as_posix():sha(p) for p in previous.glob('*.v')}
    for p in previous.glob('*.v'):shutil.copy2(p,target/p.name)
    name='http2_pipelined_cancel_window_store';text=(previous/(name+'.v')).read_text()
    end=header_end(text,name);text=text[:end]+',\n    input wire req_global_format\n'+text[end:]
    text=replace(text,'    reg recovery_format;','    reg recovery_format,format_authority;')
    text=replace(text,'            format_cursor<=0;', '            format_authority<=0;format_cursor<=0;')
    text=replace(text,'                op<=req_op;authority<=req_authority;',
        '                format_authority<=ENABLE_WINDOW_FORMAT&&req_global_format;op<=req_op;authority<=req_authority;')
    text=replace(text,'                else if(!authority)finish_error(7,1,2,1);',
        '                else if(!authority)finish_error(7,1,2,1);\n'
        '                else if(ENABLE_WINDOW_FORMAT&&op==FORMAT_STREAMS&&!format_authority)finish_error(7,16,2,1);')
    (target/(name+'.v')).write_text(text)
    for name,child,instance_name,connection in (
        ('http2_owned_pipelined_cancel_windows','http2_pipelined_cancel_window_store','windows','saved_req_global_format'),
        ('http2_enveloped_frame_grants','http2_owned_pipelined_cancel_windows','owned','select_control&&window_req_is_global_format'),
        ('rpc_grpc_http2_return','http2_enveloped_frame_grants','directory_service','window_req_is_global_format')):
        text=(previous/(name+'.v')).read_text();end=header_end(text,name)
        text=text[:end]+',\n    input wire window_req_is_global_format\n'+text[end:]
        if name=='http2_owned_pipelined_cancel_windows':
            text=replace(text,'reg  saved_req_maintenance;','reg  saved_req_maintenance;\nreg saved_req_global_format;')
            text=replace(text,'        saved_req_maintenance<=0;', '        saved_req_maintenance<=0;saved_req_global_format<=0;')
            text=replace(text,'            saved_req_maintenance<=window_req_maintenance;',
                '            saved_req_maintenance<=window_req_maintenance;\n            saved_req_global_format<=ENABLE_WINDOW_FORMAT&&window_req_is_global_format;')
        a,b,params,connections=instance(text,child,instance_name)
        connections['req_global_format' if child=='http2_pipelined_cancel_window_store' else 'window_req_is_global_format']=connection
        text=text[:a]+named_instance(child,params,instance_name,connections)+text[b:]
        (target/(name+'.v')).write_text(text)
    name='http2_enveloped_parser_core';text=(previous/(name+'.v')).read_text()
    a,b,params,connections=instance(text,'rpc_grpc_http2_return','reverse')
    connections['window_req_is_global_format']='tx_format_send'
    text=text[:a]+named_instance('rpc_grpc_http2_return',params,'reverse',connections)+text[b:]
    (target/(name+'.v')).write_text(text)
    result=dict(phase='private_window_format_authority_generated',generator_sha256=sha(Path(__file__)),
        input_sha256=inputs,generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        actual_global_transaction_grant_captured=True,external_window_commands_have_no_format_grant=True,
        global_maintenance_bit_alone_insufficient=True,actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(target)


if __name__=='__main__':main()
