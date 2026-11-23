"""Connect windowed admission to one actual shared directory/window service."""
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY, named_instance


def main():
    root=Path(__file__).resolve().parents[1]
    admission=ports((root/'rtl/http2_windowed_rpc_admission.v').read_text(),'http2_windowed_rpc_admission')
    owned=ports((root/'rtl/http2_owned_keyed_windows.v').read_text(),'http2_owned_keyed_windows')
    lines=['`timescale 1ns/1ps','`default_nettype none','module cocotb_windowed_admission_top;',
        'localparam integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;']
    for d,w,n in admission:
        if n in MEMORY:continue
        driven=d=='input'and not n.startswith(('control_','init_'))
        lines.append(f"{'reg'if driven else'wire'} {w} {n}{'=0'if driven else''};")
    for d,w,n in admission:
        if n in MEMORY:lines.append(f'wire {w} a_{n};')
    for n,(bits,d)in MEMORY.items():
        lines += [f"{'reg'if d=='input'else'wire'} [3*{bits}-1:0] {n}{'=0'if d=='input'else''};",f'wire [2*{bits}-1:0] s_{n};']
        if d=='output':lines.append(f'assign {n}={{s_{n},a_{n}}};')
        else:lines += [f'assign a_{n}={n}[0+:{bits}];',f'assign s_{n}={n}[{bits}+:2*{bits}];']
    generic=[p for p in owned if p[2].startswith(('req_','rsp_','cfg_pool_'))]
    for d,w,n in generic:
        lines.append(f"{'reg'if d=='input'else'wire'} {w} host_{n}{'=0'if d=='input'else''};")
        if d=='output'and n not in('req_ready','rsp_valid'):lines.append(f'wire {w} s_{n};\nassign host_{n}=s_{n};')
    window=[p for p in owned if p[2].startswith('window_')]
    for d,w,n in window:
        lines.append(f"{'reg'if d=='input'else'wire'} {w} {n}{'=0'if d=='input'else''};")
        if d=='output'and n.startswith('window_rsp_')and n!='window_rsp_valid':
            lines.append(f'wire {w} s_{n};\nassign {n}=s_{n};')
    lines += ['reg [1:0] dir_owner=0,win_owner=0;',
        'wire s_req_ready,s_rsp_valid,s_window_req_ready,s_window_rsp_valid;',
        'wire directory_recovery_required;wire [22:0] directory_recovery_address;',
        'wire directory_pool_lock_active,service_idle;',
        'assign control_ready=dir_owner==0&&s_req_ready;',
        'assign host_req_ready=dir_owner==0&&!control_valid&&idle&&s_req_ready;',
        'assign control_result_valid=dir_owner==1&&s_rsp_valid;',
        'assign host_rsp_valid=dir_owner==2&&s_rsp_valid;',
        'assign init_ready=win_owner==0&&s_window_req_ready;',
        'assign window_req_ready=win_owner==0&&!init_valid&&s_window_req_ready;',
        'assign init_result_valid=win_owner==1&&s_window_rsp_valid;',
        'assign window_rsp_valid=win_owner==2&&s_window_rsp_valid;',
        'assign init_status=s_window_rsp_status;assign init_memory_status=s_window_rsp_memory_status;',
        'assign init_recovery_required=window_recovery_required;assign init_recovery_address=window_recovery_address;']
    result_map={'rsp_status':'control_status','rsp_memory_status':'control_memory_status',
        'rsp_address':'control_result_address','rsp_buffer_base':'control_result_buffer_base',
        'rsp_buffer_bytes':'control_result_buffer_bytes','rsp_application':'control_result_application',
        'rsp_generation':'control_result_generation','rsp_message_limit':'control_result_message_limit',
        'rsp_protobuf':'control_result_protobuf','rsp_unsupported_encoding':'control_result_unsupported_encoding','rsp_state':'control_result_state'}
    lines += [f'assign {value}=s_{key};'for key,value in result_map.items()]
    lines += [named_instance('http2_windowed_rpc_admission','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)',
        'admission',{n:'a_'+n if n in MEMORY else n for _,_,n in admission})]
    connections={n:'' for _,_,n in owned}
    connections.update(clk='clk',rst='rst',idle='service_idle',recovery_required='directory_recovery_required',
        recovery_address='directory_recovery_address',directory_pool_lock_active='directory_pool_lock_active',lease_valid="1'b0",lease_rsp_ready="1'b0")
    connections.update({n:'s_'+n for n in MEMORY})
    for d,w,n in generic:
        if n=='req_valid':connections[n]='dir_owner==0&&(control_valid||host_req_valid&&idle)'
        elif n=='req_ready':connections[n]='s_req_ready'
        elif n=='rsp_valid':connections[n]='s_rsp_valid'
        elif n=='rsp_ready':connections[n]='dir_owner==1?control_result_ready:dir_owner==2&&host_rsp_ready'
        elif d=='output':connections[n]='s_'+n
        else:
            value='control_'+n.removeprefix('req_')if n.startswith('req_')else'control_pool_'+n.removeprefix('cfg_pool_')
            if n=='req_state':value="256'd0"
            connections[n]=f'control_valid?{value}:host_{n}'
    for d,w,n in window:
        if n=='window_req_valid':connections[n]='win_owner==0&&(init_valid||window_req_valid)'
        elif n=='window_req_ready':connections[n]='s_window_req_ready'
        elif n=='window_rsp_valid':connections[n]='s_window_rsp_valid'
        elif n=='window_rsp_ready':connections[n]='win_owner==1?init_result_ready:win_owner==2&&window_rsp_ready'
        elif d=='output':connections[n]='s_'+n if n.startswith('window_rsp_')else n
        else:
            key=n.removeprefix('window_')
            value={'req_op':"4'd1",'req_maintenance':"1'b0",'req_user':'init_user','req_stream':'init_stream',
                'req_generation':'init_generation','req_record_address':'init_record_address','req_amount':"32'd0"}.get(key,'init_'+key)
            connections[n]=f'init_valid?{value}:{n}'
    # Tie unused lease/config inputs explicitly; output metadata stays unconnected.
    for d,w,n in owned:
        if d=='input'and not connections[n]:connections[n]="'0"
    lines += [named_instance('http2_owned_keyed_windows','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','service',connections),
        'always @(posedge clk)begin',
        '    if(rst)begin dir_owner<=0;win_owner<=0;end else begin',
        '        if(dir_owner==0&&s_req_ready&&(control_valid||host_req_valid&&idle))dir_owner<=control_valid?1:2;',
        '        if(s_rsp_valid&&(dir_owner==1?control_result_ready:dir_owner==2&&host_rsp_ready))dir_owner<=0;',
        '        if(win_owner==0&&s_window_req_ready&&(init_valid||window_req_valid))win_owner<=init_valid?1:2;',
        '        if(s_window_rsp_valid&&(win_owner==1?init_result_ready:win_owner==2&&window_rsp_ready))win_owner<=0;',
        '    end','end','endmodule','`default_nettype wire','']
    (root/'sim/cocotb_windowed_admission_top.sv').write_text('\n'.join(lines))
    print('Generated actual window-commit admission + one shared directory + three memory clients')


if __name__=='__main__':
    main()
