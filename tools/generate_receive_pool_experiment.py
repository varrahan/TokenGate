"""Arbitrate RX against the actual directory pool lock, preserving real owners."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports, instance, named_instance

from rtl_paths import source_path, source_relative


POOL=[('input','','receive_pool_lock_valid'),('output','','receive_pool_lock_ready'),
    ('input','[MEMORY_ADDR_WIDTH-1:0]','receive_pool_lock_base'),('input','[MEMORY_ADDR_WIDTH:0]','receive_pool_lock_bytes'),
    ('output','','receive_pool_result_valid'),('input','','receive_pool_result_ready'),('output','[7:0]','receive_pool_status'),
    ('output','','receive_pool_active'),('input','','receive_pool_unlock_valid'),('output','','receive_pool_unlock_ready'),
    ('output','','receive_admission_lock_active'),('output','[MEMORY_ADDR_WIDTH-1:0]','receive_admission_pool_base'),
    ('output','[MEMORY_ADDR_WIDTH:0]','receive_admission_pool_bytes')]


def replace(text,old,new):
    assert text.count(old)==1,(old,text.count(old));return text.replace(old,new)


def main():
    root=Path(__file__).resolve().parents[1];previous=root/'build/experiments/receive-integration/rtl'
    folder=root/'build/experiments/receive-pool-locked';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    inputs={};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for p in previous.glob('*.v'):shutil.copy2(p,target/p.name);inputs[source_relative(p, root).as_posix()]=sha(p)
    def read(name):
        p=previous/(name+'.v')
        if not p.exists():p=source_path(root, Path('rtl') / (name+'.v'))
        inputs[source_relative(p, root).as_posix()]=sha(p);return p.read_text()
    def emit(name,text):(target/(name+'.v')).write_text(text)
    def change(text,child,inst,extra,feature=False):
        a,b,p,c=instance(text,child,inst);c.update(extra)
        if feature:p='.ENABLE_RECEIVE_POOL(ENABLE_RECEIVE_POOL),'+p
        return text[:a]+named_instance(child,p,inst,c)+text[b:]
    def public(text,name):
        text=add_ports(text,name,POOL)
        return replace(text,'module '+name+' #(','module '+name+' #(parameter integer ENABLE_RECEIVE_POOL=0,')

    name='http2_owned_pipelined_cancel_windows';text=public(read(name),name)
    extra={
        'pool_lock_valid':'shared_lock_valid','pool_lock_ready':'shared_lock_ready',
        'pool_lock_base':'shared_lock_base','pool_lock_bytes':'shared_lock_bytes',
        'pool_lock_result_valid':'shared_result_valid','pool_lock_result_ready':'shared_result_ready',
        'pool_lock_status':'shared_status','pool_unlock_valid':'shared_unlock_valid','pool_unlock_ready':'shared_unlock_ready'}
    text=change(text,'grpc_pool_locked_stream_store','directory',extra)
    body='''
wire shared_lock_valid,shared_lock_ready,shared_result_valid,shared_result_ready,shared_unlock_valid,shared_unlock_ready;
wire [MEMORY_ADDR_WIDTH-1:0] shared_lock_base;wire [MEMORY_ADDR_WIDTH:0] shared_lock_bytes;wire [7:0] shared_status;
assign receive_admission_pool_base=saved_cfg_stream_base;
assign receive_admission_pool_bytes=saved_cfg_stream_bytes;
generate if(ENABLE_RECEIVE_POOL)begin: shared_pool_owners
    directory_pool_lock_arbiter #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) arbiter(
        .clk(clk),.rst(rst),
        .a_lock_valid(state==LOCK_SEND),.a_lock_ready(lock_ready),.a_lock_base(saved_cfg_stream_base),.a_lock_bytes(saved_cfg_stream_bytes),
        .a_result_valid(lock_result_valid),.a_result_ready(state==LOCK_WAIT),.a_status(lock_status),.a_active(receive_admission_lock_active),
        .a_unlock_valid(state==UNLOCK),.a_unlock_ready(unlock_ready),
        .b_lock_valid(receive_pool_lock_valid),.b_lock_ready(receive_pool_lock_ready),.b_lock_base(receive_pool_lock_base),.b_lock_bytes(receive_pool_lock_bytes),
        .b_result_valid(receive_pool_result_valid),.b_result_ready(receive_pool_result_ready),.b_status(receive_pool_status),.b_active(receive_pool_active),
        .b_unlock_valid(receive_pool_unlock_valid),.b_unlock_ready(receive_pool_unlock_ready),
        .m_lock_valid(shared_lock_valid),.m_lock_ready(shared_lock_ready),.m_lock_base(shared_lock_base),.m_lock_bytes(shared_lock_bytes),
        .m_result_valid(shared_result_valid),.m_result_ready(shared_result_ready),.m_status(shared_status),.m_active(directory_pool_lock_active),
        .m_unlock_valid(shared_unlock_valid),.m_unlock_ready(shared_unlock_ready),.idle());
end else begin: original_pool_owner
    assign shared_lock_valid=state==LOCK_SEND;assign lock_ready=shared_lock_ready;
    assign shared_lock_base=saved_cfg_stream_base;assign shared_lock_bytes=saved_cfg_stream_bytes;
    assign lock_result_valid=shared_result_valid;assign shared_result_ready=state==LOCK_WAIT;assign lock_status=shared_status;
    assign shared_unlock_valid=state==UNLOCK;assign unlock_ready=shared_unlock_ready;
    assign receive_pool_lock_ready=0;assign receive_pool_result_valid=0;assign receive_pool_status=0;
    assign receive_pool_active=0;assign receive_pool_unlock_ready=0;assign receive_admission_lock_active=directory_pool_lock_active;
end endgenerate
'''
    emit(name,replace(text,'endmodule\n',body+'\nendmodule\n'))
    for name,child,inst in [('http2_enveloped_frame_grants','http2_owned_pipelined_cancel_windows','owned'),
        ('rpc_grpc_http2_return','http2_enveloped_frame_grants','directory_service')]:
        emit(name,change(public(read(name),name),child,inst,{n:n for _,_,n in POOL},True))

    name='http2_enveloped_parser_core';text=read(name);lines=[]
    for _,w,n in POOL:lines.append('wire '+w+' '+n+';')
    a,b,params,c=instance(text,'rpc_grpc_http2_return','reverse');c.update({n:n for _,_,n in POOL})
    text=text[:a]+named_instance('rpc_grpc_http2_return','.ENABLE_RECEIVE_POOL(1),'+params,'reverse',c)+text[b:]
    a,b,params,c=instance(text,'http2_keyed_receive_credit_store','receive_credits')
    pool_base=c['cfg_rpc_base'];pool_bytes=c['cfg_rpc_bytes']
    lines += ['wire [MEMORY_ADDR_WIDTH-1:0] receive_request_pool_base='+pool_base+';',
        'wire [MEMORY_ADDR_WIDTH:0] receive_request_pool_bytes='+pool_bytes+';',
        'reg [USER_WIDTH-1:0] receive_retirement_user;reg [30:0] receive_retirement_stream;',
        'reg [31:0] receive_retirement_generation;reg [MEMORY_ADDR_WIDTH-1:0] receive_retirement_address;',
        'always @(posedge clk)begin if(rst)begin receive_retirement_user<=0;receive_retirement_stream<=0;receive_retirement_generation<=0;receive_retirement_address<=0;end',
        'else if(rx_init_valid&&rx_init_ready&&rx_select_close)begin receive_retirement_user<=service_control_rsp_user;receive_retirement_stream<=service_control_rsp_stream;receive_retirement_generation<=service_control_rsp_generation;receive_retirement_address<=service_control_rsp_address;end end',
        '''wire receive_admission_owned=window_owner==2&&service_window_rsp_valid&&service_window_rsp_status==0&&receive_admission_lock_active&&
    receive_request_pool_base==receive_admission_pool_base&&receive_request_pool_bytes==receive_admission_pool_bytes&&
    rx_request_op==service_window_rsp_op&&rx_request_user==service_window_rsp_user&&rx_request_stream==service_window_rsp_stream&&
    (rx_request_op!=1||rx_request_generation==rx_admission_generation&&rx_request_address==rx_admission_address);
wire receive_close_owned=rx_close_started&&rx_initialization_is_close&&service_control_rsp_valid&&service_control_rsp_status==0&&service_control_rsp_op==3&&
    receive_request_pool_base==rx_close_cfg_rpc_base&&receive_request_pool_bytes==rx_close_cfg_rpc_bytes&&
    receive_retirement_user==service_control_rsp_user&&receive_retirement_stream==service_control_rsp_stream&&
    receive_retirement_generation==service_control_rsp_generation&&receive_retirement_address==service_control_rsp_address;
''']
    c.update(req_valid='rx_backend_valid',req_ready='rx_backend_ready',req_authority='rx_backend_authority',
        rsp_valid='rx_backend_result_valid',rsp_ready='rx_backend_result_ready')
    for n in ('status','detail','memory_status','http2_error','debit_authorized'):c['rsp_'+n]='rx_backend_'+n
    text=text[:a]+named_instance('http2_keyed_receive_credit_store',params,'receive_credits',c)+text[b:]
    gate=read('http2_receive_pool_gate');gc={}
    mapping=dict(command_valid='rx_request_valid',command_ready='rx_request_ready',command_is_init='rx_request_is_init',command_is_close='rx_request_is_close',
        command_pool_base='receive_request_pool_base',command_pool_bytes='receive_request_pool_bytes',admission_owned='receive_admission_owned',close_owned='receive_close_owned',
        backend_valid='rx_backend_valid',backend_ready='rx_backend_ready',backend_authority='rx_backend_authority',
        backend_result_valid='rx_backend_result_valid',backend_result_ready='rx_backend_result_ready',
        result_valid='rx_result_valid',result_ready='rx_result_ready',idle='receive_pool_gate_idle',
        lock_valid='receive_pool_lock_valid',lock_ready='receive_pool_lock_ready',lock_base='receive_pool_lock_base',lock_bytes='receive_pool_lock_bytes',
        lock_result_valid='receive_pool_result_valid',lock_result_ready='receive_pool_result_ready',lock_status='receive_pool_status',
        lock_active='receive_pool_active',unlock_valid='receive_pool_unlock_valid',unlock_ready='receive_pool_unlock_ready')
    for d,w,n in ports(gate,'http2_receive_pool_gate'):
        if n in ('clk','rst'):gc[n]=n
        elif n in mapping:gc[n]=mapping[n]
        elif n.startswith('backend_'):gc[n]='rx_'+n
        elif n.startswith('result_'):gc[n]='rx_'+n
        else:raise AssertionError(n)
        if gc[n].startswith(('rx_backend_','receive_pool_gate_idle')):lines.append('wire '+w+' '+gc[n]+';')
    lines.append(named_instance('http2_receive_pool_gate','.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)','receive_pool_requester',gc))
    text=replace(text,'assign idle=receive_controller_idle&&','assign idle=receive_pool_gate_idle&&receive_controller_idle&&')
    emit(name,replace(text,'endmodule\n','\n'+'\n'.join(lines)+'\nendmodule\n'))
    read('directory_pool_lock_arbiter')
    sim=folder/'sim';sim.mkdir(exist_ok=True)
    for p in(previous.parent/'sim').glob('*'):
        if p.is_file():
            shutil.copy2(p,sim/p.name);inputs[source_relative(p, root).as_posix()]=sha(p)
    witness=root/'sim/cocotb/receive_pool_witness.py';inputs[source_relative(witness, root).as_posix()]=sha(witness)
    for filename in ('test_raw_grpc_enveloped.py','test_raw_receive_flow.py'):
        p=sim/filename;s=p.read_text()
        s=replace(s,'import cocotb\n','import cocotb\nfrom receive_pool_witness import observe_receive_pool,pool_counts\n')
        marker='b.configure();cocotb.start_soon' if filename=='test_raw_grpc_enveloped.py' else 'b.configure(); cocotb.start_soon'
        s=replace(s,marker,'pool=pool_counts();cocotb.start_soon(observe_receive_pool(d,pool));'+marker)
        s=replace(s,"    Path('acceptance.json').write_text", "    assert pool['receive_grants']==pool['receive_unlocks'] and pool['receive_grants']>0\n    assert pool['receive_memory_commands']==pool['receive_memory_acks']\n    accepted['actual_receive_pool_ownership']=pool\n    Path('acceptance.json').write_text")
        p.write_text(s)
    interleaved=root/'sim/cocotb/test_receive_pool_interleaved.py'
    inputs[source_relative(interleaved, root).as_posix()]=sha(interleaved)
    shutil.copy2(interleaved,sim/'test_raw_grpc_duplex.py')
    report=dict(phase='actual_receive_shared_pool_experiment_generated',input_sha256=inputs,generator_sha256=sha(Path(__file__)),
        generated_sha256={p.name:sha(p)for p in target.glob('*.v')},sim_sha256={p.name:sha(p)for p in sim.glob('*')if p.is_file()},
        external_receive_uses_actual_directory_pool_lock=True,admission_reuses_existing_lock=True,
        close_reuses_actual_held_successful_result=True,ownership_exclusion_runtime_verified=False,
        full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(report,indent=2)+'\n');print(target)


if __name__=='__main__':main()
