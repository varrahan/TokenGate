"""Preserve the proven window baseline and add retained send-closed state.

The caller commits CLOSE_SEND after the closing frame retires, or while fencing
cancellation. Directory/GPU ownership outlives this directional protocol state.
"""
import hashlib
import json
from pathlib import Path


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'rtl/http2_send_window_store.v'
    text = source.read_text().replace('http2_send_window_store', 'http2_lifecycle_send_window_store')
    for old, new in (
        ('input wire [2:0] req_op', 'input wire [3:0] req_op'),
        ('output wire [2:0] rsp_op', 'output wire [3:0] rsp_op'),
        ('READ_WINDOW=6,CLOSE_CONNECTION=7;', 'READ_WINDOW=6,CLOSE_CONNECTION=7,CLOSE_SEND=8;'),
        ('reg [3:0] state;reg [2:0] op,read_count', 'reg [3:0] state,op;reg [2:0] read_count'),
        ('window_record[126:96]==record_stream&&!window_record[127]&&', 'window_record[126:96]==record_stream&&'),
        ('if(!config_good)finish_error', 'if(op>CLOSE_SEND)finish_error(2,6,2,1);\n                else if(!config_good)finish_error'),
        ('(op==INIT_STREAM||op==RESERVE)&&stream_id==0', '(op==INIT_STREAM||op==RESERVE||op==CLOSE_SEND)&&stream_id==0'),
        ('else begin if(!scanning)rsp_stream_window<=window_record[95:64];state<=CALCULATE;end',
         'else if(scanning&&window_record[127])state<=SCAN_NEXT;\n'
         '                else begin if(!scanning)rsp_stream_window<=window_record[95:64];state<=CALCULATE;end'),
        ('end else if(op==READ_WINDOW)state<=RESULT;',
         'end else if(op==CLOSE_SEND)begin\n'
         '                    if(window_record[127])state<=RESULT;\n'
         '                    else begin window_record[127]<=1;write_words(WSTREAM,0);end\n'
         '                end else if(op==READ_WINDOW)state<=RESULT;\n'
         '                else if(window_record[127]&&op==WINDOW_UPDATE)state<=RESULT;\n'
         '                else if(window_record[127]&&op==RESERVE)finish_error(8,0,5,0);'),
    ):
        text = replace_once(text, old, new)
    text = text.replace('// lifetime (the whole pool for INITIAL_WINDOW). No fixed stream array exists.',
        '// lifetime (the whole pool for INITIAL_WINDOW). No fixed stream array exists.\n'
        '// Window bit 127 persists send closure without retiring the actual RPC.\n'
        '// CLOSE_SEND is idempotent; settings skip these windows; no DATA is granted.')
    target = root / 'rtl/http2_lifecycle_send_window_store.v'
    target.write_text(text)
    owned = root / 'rtl/http2_owned_send_windows.v'
    joined = owned.read_text().replace('http2_owned_send_windows', 'http2_owned_lifecycle_windows')
    joined = joined.replace('http2_send_window_store #(', 'http2_lifecycle_send_window_store #(')
    for name in ('window_req_op', 'window_rsp_op', 'saved_req_op', 'engine_rsp_op'):
        joined = replace_once(joined, '[2:0] ' + name, '[3:0] ' + name)
    joined = joined.replace('send-closed state and image leases remain required.', 'closure scheduling and image leases remain required.')
    joined_target = root / 'rtl/http2_owned_lifecycle_windows.v'
    joined_target.write_text(joined)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(phase='generated_retained_send_closed_windows',
        input_sha256={p.relative_to(root).as_posix(): sha(p) for p in (source, owned, Path(__file__))},
        generated_sha256={p.relative_to(root).as_posix(): sha(p) for p in (target, joined_target)},
        op_width=4, close_send_op=8, window_send_closed_bit=127,
        actual_network_closure_scheduling_integrated=False, full_system_complete=False)
    (root / 'build/validation/lifecycle-send-window-generation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Generated retained send-closed windows and actual-pool-owned variant')


if __name__ == '__main__':
    main()
