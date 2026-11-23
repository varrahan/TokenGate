"""Register grant selection before the paired durable credit subtractions."""
import hashlib
import json
from pathlib import Path

from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import rename


def main():
    root=Path(__file__).resolve().parents[1];outputs=[];sources=[]
    source=root/'rtl/http2_cancel_send_window_store.v';sources.append(source);text=source.read_text()
    text=rename(text,'http2_cancel_send_window_store','http2_pipelined_cancel_window_store')
    text=replace_once(text,'GEOMETRY=13;', 'GEOMETRY=13,RESERVE_APPLY=14;')
    text=replace_once(text,'wire [31:0] grant_limit=connection_limit<window_record[95:64]?connection_limit:window_record[95:64];',
        '''wire [31:0] grant_limit=connection_limit<window_record[95:64]?connection_limit:window_record[95:64];
    // Keep the three-way credit minimum off the paired debit carry chains.
    // The actual pool grant and every record remain owned across this stage.
    reg [31:0] selected_grant;''')
    text=replace_once(text,'recovery_required<=0;recovery_address<=0;\n        end else case(state)',
        'recovery_required<=0;recovery_address<=0;selected_grant<=0;\n        end else case(state)')
    old='''                        pending_grant<=grant_limit[23:0];window_record[95:64]<=window_record[95:64]-grant_limit;
                        connection_record[95:64]<=connection_record[95:64]-grant_limit;
                        rsp_stream_window<=window_record[95:64]-grant_limit;rsp_connection_window<=connection_record[95:64]-grant_limit;
                        write_words(WRESERVE,0);'''
    text=replace_once(text,old,'selected_grant<=grant_limit;state<=RESERVE_APPLY;')
    text=replace_once(text,'            SCAN_NEXT:if(','''            RESERVE_APPLY:begin
                pending_grant<=selected_grant[23:0];
                window_record[95:64]<=window_record[95:64]-selected_grant;
                connection_record[95:64]<=connection_record[95:64]-selected_grant;
                rsp_stream_window<=window_record[95:64]-selected_grant;
                rsp_connection_window<=connection_record[95:64]-selected_grant;
                write_words(WRESERVE,0);
            end
            SCAN_NEXT:if(''')
    target=root/'rtl/http2_pipelined_cancel_window_store.v';target.write_text(text);outputs.append(target)
    variants=(('http2_owned_cancel_windows','http2_owned_pipelined_cancel_windows',
        'http2_cancel_send_window_store','http2_pipelined_cancel_window_store'),
        ('http2_fenced_frame_grants','http2_fenced_pipelined_grants',
        'http2_owned_cancel_windows','http2_owned_pipelined_cancel_windows'),
        ('grpc_cancellable_registered_framer','grpc_cancellable_pipelined_framer',
        'http2_fenced_frame_grants','http2_fenced_pipelined_grants'))
    for old_name,new_name,old_child,new_child in variants:
        source=root/f'rtl/{old_name}.v';sources.append(source);text=rename(source.read_text(),old_name,new_name)
        text=replace_once(text,old_child+' #(',new_child+' #(')
        target=root/f'rtl/{new_name}.v';target.write_text(text);outputs.append(target)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/pipelined-cancel-framer-generation.json').write_text(json.dumps(dict(
        phase='generated_registered_credit_selection_and_message_input',
        input_sha256={p.relative_to(root).as_posix():sha(p)for p in[*sources,Path(__file__)]},
        generated_sha256={p.relative_to(root).as_posix():sha(p)for p in outputs},
        minimum_registered_before_debit=True,memory_transaction_order_unchanged=True,
        pool_and_cached_load_ownership_preserved=True,full_system_complete=False),indent=2)+'\n')
    print('Generated registered grant minimum with the actual owned wire/framer path')


if __name__=='__main__':main()
