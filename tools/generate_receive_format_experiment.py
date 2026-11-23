"""Join real global directory FORMAT to acknowledged receive-ledger clearing."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace
from generate_two_fpga_application import instance,named_instance

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/retire-cause/rtl'
    folder=root/'build/experiments/receive-format';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inputs={}
    for p in previous.glob('*.v'):
        inputs[source_relative(p, root).as_posix()]=sha(p);shutil.copy2(p,target/p.name)
    def read(name):
        p=previous/(name+'.v')
        if not p.exists():p=source_path(root, Path('rtl') / (name+'.v'))
        inputs[source_relative(p, root).as_posix()]=sha(p);return p.read_text()
    name='http2_receive_credit_store';text=read(name)
    text=replace(text,'    parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23',
        '    parameter integer ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23')
    text=replace(text,'WCONNECTION=7,WFATAL=8;','WCONNECTION=7,WFATAL=8,WFORMAT_STREAMS=9;')
    text=replace(text,'    reg [MEMORY_ADDR_WIDTH-1:0] read_address;reg [3:0] write_mode;',
        '    reg [MEMORY_ADDR_WIDTH-1:0] format_cursor;\n    reg [MEMORY_ADDR_WIDTH-1:0] read_address;reg [3:0] write_mode;')
    text=replace(text,'            WFATAL:begin',
        "            WFORMAT_STREAMS:begin write_address=format_cursor;write_word=0;write_last={1'b0,format_cursor}+64'd8>=ends[3];end\n            WFATAL:begin")
    text=replace(text,'            read_phase<=0;read_index<=0;',
        '            format_cursor<=0;read_phase<=0;read_index<=0;')
    text=replace(text,'else if(operation==0&&!maintenance)',
        'else if((operation==0||ENABLE_STREAM_FORMAT&&operation==11)&&!maintenance)')
    text=replace(text,'else if(operation>10||!config_good)',
        'else if(operation>(ENABLE_STREAM_FORMAT?11:10)||!config_good)')
    text=replace(text,'else if(recovery_required&&(operation!=0||!recovery_scope))',
        'else if(recovery_required&&((operation!=0&&!(ENABLE_STREAM_FORMAT&&operation==11))||!recovery_scope))')
    text=replace(text,'(operation==0||operation==6||operation==7)&&stream_command',
        '(operation==0||operation==6||operation==7||operation==11)&&stream_command')
    text=replace(text,'(operation==1||operation==5||operation==8||operation==9||operation==10)&&amount!=0',
        '(operation==1||operation==5||operation==8||operation==9||operation==10||operation==11)&&amount!=0')
    text=replace(text,'                    else read_words(RRAW,context_address,1);',
        '                    else if(ENABLE_STREAM_FORMAT&&operation==11)begin format_cursor<=streams;write_words(WFORMAT_STREAMS);end\n'
        '                    else read_words(RRAW,context_address,1);')
    text=replace(text,"else if(!write_last)begin write_index<=write_index+1'b1;state<=WRITE_REQ;end",
        "else if(!write_last)begin\n                        if(write_mode==WFORMAT_STREAMS)format_cursor<=format_cursor+8;\n"
        "                        else write_index<=write_index+1'b1;state<=WRITE_REQ;end")
    text=replace(text,'if(operation==0)begin recovery_required<=0;recovery_address<=0;end',
        'if(operation==0||ENABLE_STREAM_FORMAT&&operation==11)begin recovery_required<=0;recovery_address<=0;end')
    (target/(name+'.v')).write_text(text)
    name='http2_keyed_receive_credit_store';text=read(name)
    text=replace(text,'#(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)',
        '#(parameter integer ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)')
    a,b,params,connections=instance(text,'http2_receive_credit_store','controller')
    text=text[:a]+named_instance('http2_receive_credit_store','.ENABLE_STREAM_FORMAT(ENABLE_STREAM_FORMAT),'+params,'controller',connections)+text[b:]
    (target/(name+'.v')).write_text(text)
    name='http2_receive_flow_controller';text=read(name)
    text=replace(text,'#(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)',
        '#(parameter integer ENABLE_STREAM_FORMAT=0,USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)')
    text=replace(text,'request_is_init<=init_op!=9&&init_op!=10;',
        'request_is_init<=init_op!=9&&init_op!=10&&(!ENABLE_STREAM_FORMAT||init_op!=11);')
    text=replace(text,'if(request_op==0)begin fault_valid<=0;',
        'if(request_op==0||ENABLE_STREAM_FORMAT&&request_op==11)begin fault_valid<=0;')
    (target/(name+'.v')).write_text(text)

    name='http2_enveloped_parser_core';text=read(name)
    declarations='''
// A real successful global directory FORMAT owns receive-ledger initialization.
// The directory result remains held until all actual receive writes retire.
reg rx_format_pending,rx_format_started,rx_format_failed,rx_format_maintenance;
reg [MEMORY_ADDR_WIDTH-1:0] rx_format_context_base,rx_format_rpc_base,rx_format_connection_base,rx_format_stream_base,rx_format_floor;
reg [MEMORY_ADDR_WIDTH:0] rx_format_context_bytes,rx_format_rpc_bytes,rx_format_connection_bytes,rx_format_stream_bytes;
wire rx_format_can_admit=!return_pending&&!generated_offered&&!rx_active&&!rx_granted&&window_owner==0&&
    !response_record_lease_active&&!response_result_retirement_pending&&!payload_lease_active&&!completion_valid&&queued_count==0&&pending_count==0;
wire rx_format_admitting=control_valid&&control_op==4&&rx_format_can_admit;
wire rx_format_waiting=control_valid&&control_op==4&&!rx_format_pending;
wire rx_format_needed=rx_format_pending&&f_control_result_valid&&f_control_result_op==4&&f_control_status==0;
wire rx_format_complete=rx_format_started&&rx_init_result_valid;
wire rx_select_format=rx_format_needed&&!rx_format_started;
wire rx_format_active=rx_format_started&&rx_request_op==11;
always @(posedge clk)begin
    if(rst)begin
        rx_format_pending<=0;rx_format_started<=0;rx_format_failed<=0;rx_format_maintenance<=0;
        rx_format_context_base<=0;rx_format_rpc_base<=0;rx_format_connection_base<=0;rx_format_stream_base<=0;rx_format_floor<=0;
        rx_format_context_bytes<=0;rx_format_rpc_bytes<=0;rx_format_connection_bytes<=0;rx_format_stream_bytes<=0;
    end else begin
        if(control_valid&&control_ready&&control_op==4)begin
            rx_format_pending<=1;rx_format_started<=0;rx_format_maintenance<=control_maintenance&&maintenance_grant;
            rx_format_context_base<=cfg_context_base;rx_format_context_bytes<=cfg_context_bytes;
            rx_format_rpc_base<=cfg_stream_base;rx_format_rpc_bytes<=cfg_stream_bytes;
            rx_format_connection_base<=cfg_receive_connection_base;rx_format_connection_bytes<=cfg_receive_connection_bytes;
            rx_format_stream_base<=cfg_receive_stream_base;rx_format_stream_bytes<=cfg_receive_stream_bytes;
            rx_format_floor<=cfg_work_floor;
        end
        if(rx_select_format&&rx_init_ready)rx_format_started<=1;
        if(control_result_valid&&control_result_ready&&rx_format_pending)begin
            rx_format_pending<=0;rx_format_started<=0;rx_format_failed<=control_status!=0;
        end
    end
end
'''
    text=replace(text,'reg shutdown_control_offered;',declarations+'\nreg shutdown_control_offered;')
    text=replace(text,'shutdown_control_offered||(!local_error_fence',
        'shutdown_control_offered||(!rx_format_pending&&(!rx_format_failed||control_op==4)&&(control_op!=4||rx_format_can_admit)&&!local_error_fence')
    text=replace(text,'assign f_control_maintenance=control_maintenance;',
        'assign f_control_maintenance=control_maintenance&&(control_op!=4||maintenance_grant);')
    text=replace(text,'assign control_result_valid=f_control_result_valid;',
        'assign control_result_valid=f_control_result_valid&&(!rx_format_needed||rx_format_complete);')
    text=replace(text,'assign f_control_result_ready=control_result_ready;',
        'assign f_control_result_ready=control_result_ready&&(!rx_format_needed||rx_format_complete);')
    for field,original in (('status','f_control_status'),('detail','f_control_detail'),('memory_status','f_control_memory_status')):
        received='rx_init_'+field
        text=replace(text,'assign control_'+field+'='+original+';',
            'assign control_'+field+'=rx_format_needed&&rx_format_complete&&rx_init_status!=0?'+received+':'+original+';')
    text=replace(text,'wire reverse_new_admit=owned_stream_valid',
        'wire reverse_new_admit=!rx_format_pending&&!rx_format_failed&&owned_stream_valid')
    text=replace(text,'!rx_granted&&!control_valid&&!journal_recovery_required;',
        '!rx_granted&&(!control_valid||rx_format_waiting)&&!journal_recovery_required;')
    text=replace(text,'&&s_axis_rx_tready)&&!control_valid&&!command_valid&&',
        '&&s_axis_rx_tready)&&(!control_valid||rx_format_waiting)&&!command_valid&&')
    text=replace(text,'wire allow_new_rx=!local_error_fence',
        'wire allow_new_rx=!rx_format_pending&&!rx_format_failed&&!local_error_fence')
    text=replace(text,'wire allow_config=!local_error_fence',
        'wire allow_config=!rx_format_pending&&!rx_format_failed&&!local_error_fence')
    text=replace(text,'else if(window_req_valid&&!local_error_fence',
        'else if(window_req_valid&&!rx_format_admitting&&!rx_format_pending&&!rx_format_failed&&!local_error_fence')
    for signal,value in (
        ('valid',"rx_select_format||rx_select_close||!rx_close_needed&&window_owner==2&&service_window_rsp_valid&&service_window_rsp_status==0&&!rx_init_started"),
        ('op',"rx_select_format?4'd11:rx_select_close?(rx_close_connection_fatal?4'd10:4'd9):rx_admission_op"),
        ('maintenance',"rx_select_format?rx_format_maintenance:rx_select_close?1'b0:rx_admission_maintenance"),
        ('user',"rx_select_format?{USER_WIDTH{1'b0}}:rx_select_close?service_control_rsp_user:rx_admission_user"),
        ('stream',"rx_select_format?31'd0:rx_select_close?service_control_rsp_stream:rx_admission_stream"),
        ('generation',"rx_select_format?32'd0:rx_select_close?service_control_rsp_generation:rx_admission_generation"),
        ('address',"rx_select_format?{MEMORY_ADDR_WIDTH{1'b0}}:rx_select_close?service_control_rsp_address:rx_admission_address")):
        import re
        pattern=r'assign rx_init_'+signal+r'=([^;]+);'
        match=re.search(pattern,text);assert match
        text=replace(text,match[0],'assign rx_init_'+signal+'='+value+';')
    text=replace(text,'assign rx_init_result_ready=rx_initialization_is_close?',
        'assign rx_init_result_ready=rx_format_started?f_control_result_valid&&f_control_result_ready:rx_initialization_is_close?')
    text=replace(text,'if(rx_init_valid&&rx_init_ready)begin rx_initialization_is_close',
        'if(rx_init_valid&&rx_init_ready&&!rx_select_format)begin rx_initialization_is_close')
    for module in ('http2_keyed_receive_credit_store','http2_receive_flow_controller'):
        text=replace(text,module+' #(.USER_WIDTH',module+' #(.ENABLE_STREAM_FORMAT(1),.USER_WIDTH')
    # The format command uses its captured global scope and the real pool lock,
    # never either admission/CLOSE ownership bypass.
    fields={'context_base':'rx_format_context_base','rpc_base':'rx_format_rpc_base',
        'receive_connection_base':'rx_format_connection_base','receive_stream_base':'rx_format_stream_base',
        'work_floor':'rx_format_floor','context_bytes':'rx_format_context_bytes','rpc_bytes':'rx_format_rpc_bytes',
        'receive_connection_bytes':'rx_format_connection_bytes','receive_stream_bytes':'rx_format_stream_bytes'}
    a,b,params,connections=instance(text,'http2_keyed_receive_credit_store','receive_credits')
    for field,register in fields.items():connections['cfg_'+field]='rx_format_active?'+register+':'+connections['cfg_'+field]
    text=text[:a]+named_instance('http2_keyed_receive_credit_store',params,'receive_credits',connections)+text[b:]
    text=replace(text,'receive_request_pool_base=rx_request_is_close?',
        'receive_request_pool_base=rx_format_active?rx_format_rpc_base:rx_request_is_close?')
    text=replace(text,'receive_request_pool_bytes=rx_request_is_close?',
        'receive_request_pool_bytes=rx_format_active?rx_format_rpc_bytes:rx_request_is_close?')
    (target/(name+'.v')).write_text(text)
    result=dict(phase='actual_global_receive_stream_format_generated',generator_sha256=sha(Path(__file__)),
        input_sha256=inputs,generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        actual_memory_acknowledged_clear=True,actual_directory_format_result_held=True,
        actual_pool_lock_required=True,per_connection_open_does_not_clear_other_records=True,
        legacy_stream_format_disabled_by_default=True,actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(target)


if __name__=='__main__':main()
