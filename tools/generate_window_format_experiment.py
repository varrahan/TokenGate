"""Join actual global directory/RX FORMAT to acknowledged send-window clearing."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_receive_pool_experiment import replace
from generate_two_fpga_application import instance,named_instance,header_end


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/receive-format/rtl'
    folder=root/'build/experiments/window-format';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={p.relative_to(root).as_posix():sha(p) for p in previous.glob('*.v')}
    for p in previous.glob('*.v'):shutil.copy2(p,target/p.name)
    name='http2_pipelined_cancel_window_store';text=(previous/(name+'.v')).read_text()
    text=replace(text,'parameter integer ENABLE_LOCAL_FATAL=0,','parameter integer ENABLE_LOCAL_FATAL=0,parameter integer ENABLE_WINDOW_FORMAT=0,')
    text=replace(text,'FATAL_CLOSE_SEND_KEY=11;','FATAL_CLOSE_SEND_KEY=11,FORMAT_STREAMS=12;')
    text=replace(text,'WRESERVE=5,WCLOSE=6;','WRESERVE=5,WCLOSE=6,WFORMAT_STREAMS=7;')
    declarations='''
    reg [MEMORY_ADDR_WIDTH-1:0] format_cursor,recovery_floor;
    reg [3*MEMORY_ADDR_WIDTH-1:0] recovery_bases;
    reg [3*(MEMORY_ADDR_WIDTH+1)-1:0] recovery_sizes;
    reg recovery_format;
    wire format_recovery_scope={contexts,streams,windows}==recovery_bases&&
        {context_bytes,stream_bytes,window_bytes}==recovery_sizes&&work_floor==recovery_floor;
'''
    text=replace(text,'    reg [63:0] raw_header;',declarations+'    reg [63:0] raw_header;')
    text=replace(text,'wire [63:0] write_word=write_mode==WINIT_CONN?',
        "wire [63:0] write_word=write_mode==WFORMAT_STREAMS?64'd0:write_mode==WINIT_CONN?")
    text=replace(text,'write_address=write_mode==WINIT_CONN?',
        'write_address=write_mode==WFORMAT_STREAMS?format_cursor:write_mode==WINIT_CONN?')
    text=replace(text,'wire write_last=write_mode==WINIT_CONN?',
        "wire write_last=write_mode==WFORMAT_STREAMS?({1'b0,format_cursor}+64'd8>=windows_end):write_mode==WINIT_CONN?")
    text=replace(text,'recovery_owner<=owner;\n            finish_error',
        'recovery_owner<=owner;\n            recovery_format<=ENABLE_WINDOW_FORMAT&&op==FORMAT_STREAMS;\n'
        '            recovery_bases<={contexts,streams,windows};recovery_sizes<={context_bytes,stream_bytes,window_bytes};recovery_floor<=work_floor;\n            finish_error')
    text=replace(text,'            recovery_context<=0;recovery_owner<=0;',
        '            format_cursor<=0;recovery_floor<=0;recovery_bases<=0;recovery_sizes<=0;recovery_format<=0;\n            recovery_context<=0;recovery_owner<=0;')
    text=replace(text,'if(op>(ENABLE_LOCAL_FATAL?FATAL_CLOSE_SEND_KEY:CLOSE_SEND_KEY))',
        'if(op>(ENABLE_WINDOW_FORMAT?FORMAT_STREAMS:ENABLE_LOCAL_FATAL?FATAL_CLOSE_SEND_KEY:CLOSE_SEND_KEY))')
    text=replace(text,'else if(recovery_required&&!(maintenance&&(op==INIT_CONNECTION||op==CLOSE_CONNECTION)&&owner==recovery_owner&&context_full==recovery_context))',
        'else if(recovery_required&&!(ENABLE_WINDOW_FORMAT&&op==FORMAT_STREAMS?maintenance&&format_recovery_scope:!recovery_format&&maintenance&&(op==INIT_CONNECTION||op==CLOSE_CONNECTION)&&owner==recovery_owner&&context_full==recovery_context))')
    text=replace(text,'else if((op==INIT_CONNECTION||op==CLOSE_CONNECTION)&&(!maintenance||stream_id!=0))',
        'else if(ENABLE_WINDOW_FORMAT&&op==FORMAT_STREAMS&&(!maintenance||owner!=0||stream_id!=0||generation!=0||rpc_address!=0||amount!=0))finish_error(7,15,2,1);\n'
        '                else if((op==INIT_CONNECTION||op==CLOSE_CONNECTION)&&(!maintenance||stream_id!=0))')
    text=replace(text,'else if(op==CLOSE_CONNECTION)write_words(WCLOSE,0);',
        'else if(ENABLE_WINDOW_FORMAT&&op==FORMAT_STREAMS)begin format_cursor<=windows;write_words(WFORMAT_STREAMS,0);end\n'
        '                else if(op==CLOSE_CONNECTION)write_words(WCLOSE,0);')
    text=replace(text,'if(op==INIT_CONNECTION||op==CLOSE_CONNECTION)begin recovery_required<=0;recovery_address<=0;end',
        'if(op==INIT_CONNECTION||op==CLOSE_CONNECTION||ENABLE_WINDOW_FORMAT&&op==FORMAT_STREAMS)begin recovery_required<=0;recovery_address<=0;recovery_format<=0;end')
    text=replace(text,"end else begin write_index<=write_index+1'b1;state<=WRITE_REQ;end",
        "end else begin if(write_mode==WFORMAT_STREAMS)format_cursor<=format_cursor+8;else write_index<=write_index+1'b1;state<=WRITE_REQ;end")
    (target/(name+'.v')).write_text(text)
    for name,child,instance_name in (
        ('http2_owned_pipelined_cancel_windows','http2_pipelined_cancel_window_store','windows'),
        ('http2_enveloped_frame_grants','http2_owned_pipelined_cancel_windows','owned'),
        ('rpc_grpc_http2_return','http2_enveloped_frame_grants','directory_service')):
        text=(previous/(name+'.v')).read_text()
        text=replace(text,'parameter integer ENABLE_LOCAL_FATAL=0,','parameter integer ENABLE_LOCAL_FATAL=0,parameter integer ENABLE_WINDOW_FORMAT=0,')
        a,b,params,connections=instance(text,child,instance_name)
        text=text[:a]+named_instance(child,'.ENABLE_WINDOW_FORMAT(ENABLE_WINDOW_FORMAT),'+params,instance_name,connections)+text[b:]
        if name=='rpc_grpc_http2_return':
            end=header_end(text,name)
            text=text[:end]+',\n    output wire window_format_recovery_only\n'+text[end:]
            text=replace(text,'assign recovery_required=',
                'assign window_format_recovery_only=ENABLE_WINDOW_FORMAT&&window_recovery_required&&!response_recovery&&!directory_recovery_required&&!frame_tracking_error&&!child_result_valid&&!result_ack_pending;\nassign recovery_required=')
        (target/(name+'.v')).write_text(text)
    name='http2_enveloped_parser_core';text=(previous/(name+'.v')).read_text()
    declarations='''
// Global FORMAT retains both ledger results until its public acknowledgement.
reg tx_format_started,tx_format_error_owned;
reg [MEMORY_ADDR_WIDTH-1:0] tx_format_window_base;
reg [MEMORY_ADDR_WIDTH:0] tx_format_window_bytes;
wire tx_format_needed=rx_format_needed&&rx_format_complete&&rx_init_status==0&&!tx_format_started;
wire tx_format_send=window_owner==11;
wire tx_format_complete=tx_format_started&&window_owner==12&&service_window_rsp_valid;
wire global_format_complete=rx_format_complete&&(rx_init_status!=0||tx_format_complete);
wire window_format_recovery_only;
always @(posedge clk)begin
    if(rst)begin tx_format_started<=0;tx_format_error_owned<=0;tx_format_window_base<=0;tx_format_window_bytes<=0;end
    else begin
        if(control_valid&&control_ready&&control_op==4)begin
            tx_format_started<=0;tx_format_window_base<=cfg_window_base;tx_format_window_bytes<=cfg_window_bytes;
        end
        if(tx_format_send&&service_window_req_valid&&service_window_req_ready)tx_format_started<=1;
        if(control_result_valid&&control_result_ready&&rx_format_pending)begin
            tx_format_started<=0;
            if(tx_format_complete)tx_format_error_owned<=service_window_rsp_status!=0&&service_window_recovery_required;
            else if(control_status==0)tx_format_error_owned<=0;
        end
    end
end
'''
    text=replace(text,'reg shutdown_control_offered;',declarations+'\nreg shutdown_control_offered;')
    text=replace(text,'0:if(local_abort_window_valid)window_owner<=9;',
        "0:if(tx_format_needed)window_owner<=11;else if(local_abort_window_valid)window_owner<=9;")
    text=replace(text,'        default:window_owner<=0;',
        '        11:if(service_window_req_valid&&service_window_req_ready)window_owner<=12;\n'
        '        12:if(service_window_rsp_valid&&service_window_rsp_ready)window_owner<=0;\n        default:window_owner<=0;')
    text=replace(text,'assign service_window_req_valid=',"assign service_window_req_valid=tx_format_send?1'b1:")
    text=replace(text,'assign service_window_rsp_ready=',
        'assign service_window_rsp_ready=window_owner==12?f_control_result_valid&&f_control_result_ready:')
    values=dict(op="4'd12",maintenance='rx_format_maintenance',user="{USER_WIDTH{1'b0}}",stream="31'd0",
        generation="32'd0",record_address="{MEMORY_ADDR_WIDTH{1'b0}}",amount="32'd0")
    for signal,value in values.items():
        text=replace(text,'assign service_window_req_'+signal+'=', 'assign service_window_req_'+signal+'=tx_format_send?'+value+':')
    values=dict(context_base='rx_format_context_base',context_bytes='rx_format_context_bytes',
        stream_base='rx_format_rpc_base',stream_bytes='rx_format_rpc_bytes',
        window_base='tx_format_window_base',window_bytes='tx_format_window_bytes',work_floor='rx_format_floor')
    for signal,value in values.items():
        text=replace(text,'assign service_window_cfg_'+signal+'=', 'assign service_window_cfg_'+signal+'=tx_format_send?'+value+':')
    for signal in ('control_result_valid','f_control_result_ready'):
        match=re.search(r'assign '+signal+r'=([^;]+);',text);assert match
        text=replace(text,match[0],match[0].replace('||rx_format_complete','||global_format_complete'))
    for field in ('status','detail','memory_status'):
        text=replace(text,'?rx_init_'+field+':f_control_'+field+';',
            '?rx_init_'+field+':rx_format_needed&&tx_format_complete&&service_window_rsp_status!=0?service_window_rsp_'+field+':f_control_'+field+';')
    # Only the actual private FORMAT failure can authorize recovery of the
    # window-only quarantine. Unrelated response/directory errors stay fenced.
    match=re.search(r'wire shutdown_control_admit=([^;]+);',text);assert match
    text=replace(text,match[0],match[0].replace('!response_recovery_required',
        '(!response_recovery_required||control_op==4&&tx_format_error_owned&&window_format_recovery_only)'))
    a,b,params,connections=instance(text,'rpc_grpc_http2_return','reverse')
    connections['window_format_recovery_only']='window_format_recovery_only'
    text=text[:a]+named_instance('rpc_grpc_http2_return','.ENABLE_WINDOW_FORMAT(1),'+params,'reverse',connections)+text[b:]
    (target/(name+'.v')).write_text(text)
    result=dict(phase='actual_global_receive_and_send_window_format_generated',generator_sha256=sha(Path(__file__)),
        input_sha256=inputs,generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        feature_disabled_by_default=True,actual_memory_ack_required=True,actual_shared_pool_lock_required=True,
        actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(target)


if __name__=='__main__':main()
