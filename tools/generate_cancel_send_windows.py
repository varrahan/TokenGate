"""Resolve and close actual send windows by wire key under directory ownership."""
import hashlib
import json
from pathlib import Path

from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import add_ports,instance,named_instance

from rtl_paths import source_path, source_relative


def main():
    root=Path(__file__).resolve().parents[1];original=source_path(root, 'rtl/http2_keyed_send_window_store.v')
    text=original.read_text().replace('http2_keyed_send_window_store','http2_cancel_send_window_store')
    metadata=[('output','','rsp_binding_valid'),('output','[MEMORY_ADDR_WIDTH-1:0]','rsp_record_address'),
        ('output','[31:0]','rsp_generation'),('output','','rsp_send_closed')]
    text=add_ports(text,'http2_cancel_send_window_store',metadata)
    for old,new in(
        ('WINDOW_UPDATE_KEY=9;', 'WINDOW_UPDATE_KEY=9,CLOSE_SEND_KEY=10;'),
        ('wire searching=op==WINDOW_UPDATE_KEY&&stream_id!=0;', 'wire searching=(op==WINDOW_UPDATE_KEY||op==CLOSE_SEND_KEY)&&stream_id!=0;'),
        ('if(op>WINDOW_UPDATE_KEY)', 'if(op>CLOSE_SEND_KEY)'),
        ('(op==INIT_STREAM||op==RESERVE||op==CLOSE_SEND)&&stream_id==0)', '(op==INIT_STREAM||op==RESERVE||op==CLOSE_SEND||op==CLOSE_SEND_KEY)&&stream_id==0)'),
        ('else if(op==WINDOW_UPDATE_KEY&&(generation!=0||rpc_address!=0))', 'else if((op==WINDOW_UPDATE_KEY||op==CLOSE_SEND_KEY)&&(generation!=0||rpc_address!=0))'),
        ('else if(op!=WINDOW_UPDATE_KEY&&stream_id!=0&&(!address_good||generation==0))',
         'else if(op==CLOSE_SEND_KEY&&amount!=0)finish_error(2,8,2,1);\n                else if(op!=WINDOW_UPDATE_KEY&&op!=CLOSE_SEND_KEY&&stream_id!=0&&(!address_good||generation==0))'),
        ('end else if(op==CLOSE_SEND)begin', 'end else if(op==CLOSE_SEND||op==CLOSE_SEND_KEY)begin'),
        ('assign idle=state==IDLE&&slot_idle&&!req_valid;',
         'assign idle=state==IDLE&&slot_idle&&!req_valid;\n'
         '    // Publish only a verified, durably closed actual binding. Never a caller guess.\n'
         '    assign rsp_binding_valid=rsp_valid&&rsp_status==0&&(op==CLOSE_SEND||op==CLOSE_SEND_KEY);\n'
         '    assign rsp_record_address=rpc_address;assign rsp_generation=record_generation;\n'
         '    assign rsp_send_closed=rsp_binding_valid&&window_record[127];'),
    ):text=replace_once(text,old,new)
    text=text.replace('// WINDOW_UPDATE_KEY accepts only connection/stream/increment; address and generation must be zero.',
        '// CLOSE_SEND_KEY (10) resolves the real stream and persists send closure without retiring its RPC.\n'
        '// It requires zero caller address, generation and amount; success returns the actual closed binding.\n'
        '// WINDOW_UPDATE_KEY accepts only connection/stream/increment; address and generation must be zero.')
    target=source_path(root, 'rtl/http2_cancel_send_window_store.v');target.write_text(text)
    original_owned=source_path(root, 'rtl/http2_owned_keyed_windows.v');owned=original_owned.read_text()
    owned=owned.replace('http2_owned_keyed_windows','http2_owned_cancel_windows')
    owned=add_ports(owned,'http2_owned_cancel_windows',[(d,w,'window_'+n)for d,w,n in metadata])
    start,end,params,connections=instance(owned,'http2_keyed_send_window_store','windows')
    declarations=[]
    for _,w,n in metadata:
        connections[n]='engine_'+n;declarations +=[f'wire {w} engine_{n};',f'assign window_{n}=state==LOCK_ERROR?0:engine_{n};']
    owned=owned[:start]+'\n'.join(declarations)+'\n'+named_instance('http2_cancel_send_window_store',params,'windows',connections)+owned[end:]
    owned_target=source_path(root, 'rtl/http2_owned_cancel_windows.v');owned_target.write_text(owned)
    grant_path=source_path(root, 'rtl/http2_keyed_frame_grants.v');grant=grant_path.read_text().replace('http2_keyed_frame_grants','http2_cancel_frame_grants')
    grant=add_ports(grant,'http2_cancel_frame_grants',[(d,w,'window_'+n)for d,w,n in metadata])
    start,end,params,connections=instance(grant,'http2_owned_keyed_windows','owned')
    connections.update({'window_'+n:'window_'+n for _,_,n in metadata})
    grant=grant[:start]+named_instance('http2_owned_cancel_windows',params,'owned',connections)+grant[end:]
    grant=replace_once(grant,'owned_window_rsp_op==8||owned_window_rsp_op==9)', 'owned_window_rsp_op==8||owned_window_rsp_op==9||owned_window_rsp_op==10)')
    grant_target=source_path(root, 'rtl/http2_cancel_frame_grants.v');grant_target.write_text(grant)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='generated_actual_keyed_send_closure',input_sha256={str(source_relative(p, root)).replace('\\','/'):sha(p)for p in(original,original_owned,grant_path,Path(__file__))},
        generated_sha256={str(source_relative(p, root)).replace('\\','/'):sha(p)for p in(target,owned_target,grant_target)},
        key_close_op=10,actual_binding_returned_after_commit=True,parked_grant_wakes_on_close=True,
        actual_rst_controller_integrated=False,inflight_wire_frame_drain_integrated=False,full_system_complete=False)
    (root/'build/validation/cancel-send-windows-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated key-only send closure, resolved actual binding and parked-grant wakeup')


if __name__=='__main__':main()
