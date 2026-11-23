"""Wire real directory pool ownership around each durable window transaction."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import MEMORY, named_instance


def main():
    root=Path(__file__).resolve().parents[1]
    directory_path=root/'rtl/grpc_pool_locked_stream_store.v';window_path=root/'rtl/http2_send_window_store.v'
    directory=ports(directory_path.read_text(),'grpc_pool_locked_stream_store')
    windows=ports(window_path.read_text(),'http2_send_window_store')
    pool_names={n for _,_,n in directory if n.startswith(('pool_lock_','pool_unlock_'))}
    public=[p for p in directory if p[2]not in MEMORY and p[2]not in pool_names and p[2]!='idle']
    public += [(d,w,'window_'+n)for d,w,n in windows if n not in MEMORY and n not in('clk','rst','req_authority','idle')]
    public += [('output','','idle'),('output','','window_busy'),('output','[7:0]','window_lock_status'),
               ('output','','directory_pool_lock_active')]
    public += [(d,f'[2*{bits}-1:0]',n)for n,(bits,d)in MEMORY.items()]
    assert len({n for _,_,n in public})==len(public)
    lines=['`timescale 1ns/1ps','`default_nettype none',
        '// Actual directory exclusion + actual durable send-window engine.',
        '// Memory client zero: directory; client one: send-window records.',
        '// Raw control/framer scheduling, send-closed state and image leases remain required.',
        'module http2_owned_send_windows #(parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join(f'    {d} wire {w} {n}'for d,w,n in public),');',
        'localparam IDLE=0,LOCK_SEND=1,LOCK_WAIT=2,ISSUE=3,RESULT=4,LOCK_ERROR=5,UNLOCK=6;',
        'reg [2:0] state;reg [7:0] owned_lock_status;',
        'wire directory_idle,window_engine_idle,engine_req_ready,engine_rsp_valid;',
        'wire lock_ready,lock_result_valid,unlock_ready;wire [7:0] lock_status;']
    captured=[p for p in windows if p[0]=='input'and(p[2].startswith(('req_','cfg_'))and p[2]not in('req_valid','req_authority'))]
    lines += [f'reg {w} saved_{n};'for _,w,n in captured]
    responses=[p for p in windows if p[0]=='output'and p[2].startswith('rsp_')and p[2]!='rsp_valid']
    lines += [f'wire {w} engine_{n};'for _,w,n in responses]
    lines += ['assign window_req_ready=!rst&&state==IDLE;',
        'assign window_rsp_valid=!rst&&(state==LOCK_ERROR||state==RESULT&&engine_rsp_valid);',
        'assign window_busy=state!=IDLE;', 'assign window_lock_status=owned_lock_status;',
        'assign idle=state==IDLE&&directory_idle&&window_engine_idle&&!window_req_valid&&!window_recovery_required&&!recovery_required;']
    errors=dict(rsp_status="8'd7",rsp_detail='owned_lock_status',rsp_http2_error="32'd2",rsp_connection_error="1'b1",
                rsp_op='saved_req_op',rsp_user='saved_req_user',rsp_stream='saved_req_stream')
    lines += [f'assign window_{n}=state==LOCK_ERROR?{errors.get(n,"0")}:engine_{n};'for _,_,n in responses]
    directory_connections={n:n for _,_,n in directory}
    directory_connections.update(idle='directory_idle',pool_lock_valid='state==LOCK_SEND',pool_lock_ready='lock_ready',
        pool_lock_base='saved_cfg_stream_base',pool_lock_bytes='saved_cfg_stream_bytes',pool_lock_result_valid='lock_result_valid',
        pool_lock_result_ready='state==LOCK_WAIT',pool_lock_status='lock_status',pool_lock_active='directory_pool_lock_active',
        pool_unlock_valid='state==UNLOCK',pool_unlock_ready='unlock_ready')
    for n,(bits,_)in MEMORY.items():directory_connections[n]=f'{n}[0*{bits}+:{bits}]'
    lines.append(named_instance('grpc_pool_locked_stream_store','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)',
        'directory',directory_connections))
    window_connections={n:'window_'+n for _,_,n in windows}
    window_connections.update(clk='clk',rst='rst',idle='window_engine_idle',
        req_valid='state==ISSUE&&directory_pool_lock_active',req_ready='engine_req_ready',req_authority='directory_pool_lock_active',
        rsp_valid='engine_rsp_valid',rsp_ready='state==RESULT&&window_rsp_ready')
    window_connections.update({n:'saved_'+n for _,_,n in captured})
    window_connections.update({n:'engine_'+n for _,_,n in responses})
    for n,(bits,_)in MEMORY.items():window_connections[n]=f'{n}[1*{bits}+:{bits}]'
    lines.append(named_instance('http2_send_window_store','.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)',
        'windows',window_connections))
    lines += ['always @(posedge clk)begin','    if(rst)begin state<=IDLE;owned_lock_status<=0;']
    lines += [f'        saved_{n}<=0;'for _,_,n in captured]
    lines += ['    end else case(state)',
        '        IDLE:if(window_req_valid&&window_req_ready)begin', '            owned_lock_status<=0;']
    lines += [f'            saved_{n}<=window_{n};'for _,_,n in captured]
    lines += ['            state<=LOCK_SEND;','        end',
        '        LOCK_SEND:if(lock_ready)state<=LOCK_WAIT;',
        '        LOCK_WAIT:if(lock_result_valid)begin owned_lock_status<=lock_status;state<=lock_status==0?ISSUE:LOCK_ERROR;end',
        '        ISSUE:if(directory_pool_lock_active&&engine_req_ready)state<=RESULT;',
        '        RESULT:if(engine_rsp_valid&&window_rsp_ready)state<=UNLOCK;',
        '        LOCK_ERROR:if(window_rsp_ready)state<=IDLE;',
        '        UNLOCK:if(unlock_ready)state<=IDLE;',
        '        default:state<=IDLE;', '    endcase','end','endmodule','`default_nettype wire','']
    target=root/'rtl/http2_owned_send_windows.v';target.write_text('\n'.join(lines))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/owned-send-windows-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_pool_owned_windows',inputs_sha256={p.relative_to(root).as_posix():sha(p)for p in(directory_path,window_path,Path(__file__))},
        generated_sha256=sha(target),memory_clients=2,authority_from_actual_pool_lock=True,
        actual_network_control_integrated=False,full_system_complete=False),indent=2)+'\n')
    print('Generated actual directory/pool exclusion + durable window engine; two memory clients, internally derived authority')


if __name__=='__main__':
    main()
