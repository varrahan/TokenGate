"""Resolve wire WINDOW_UPDATE keys while holding the actual directory pool."""
import hashlib
import json
from pathlib import Path

from generate_lifecycle_send_windows import replace_once
from generate_registered_window_geometry import registered_geometry

from rtl_paths import source_path, source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    source = source_path(root, 'rtl/http2_lifecycle_send_window_store.v')
    text = source.read_text().replace('http2_lifecycle_send_window_store', 'http2_keyed_send_window_store')
    for old, new in (
        ('CLOSE_SEND=8;', 'CLOSE_SEND=8,WINDOW_UPDATE_KEY=9;'),
        ('wire [15:0] user16=owner;', 'wire [15:0] user16=owner;\n    wire searching=op==WINDOW_UPDATE_KEY&&stream_id!=0;'),
        ('if(op>CLOSE_SEND)', 'if(op>WINDOW_UPDATE_KEY)'),
        ('else if(stream_id!=0&&(!address_good||generation==0))',
         'else if(op==WINDOW_UPDATE_KEY&&(generation!=0||rpc_address!=0))finish_error(2,7,2,1);\n'
         '                else if(op!=WINDOW_UPDATE_KEY&&stream_id!=0&&(!address_good||generation==0))'),
        ('else if(op==WINDOW_UPDATE&&(amount==0||amount[31]))',
         'else if((op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY)&&(amount==0||amount[31]))'),
        ('if(op==WINDOW_UPDATE&&stream_id==0)', 'if((op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY)&&stream_id==0)'),
        ('end else read_words(RRPC,rpc_address,4);',
         'end else if(searching)begin rpc_address<=streams;read_words(RRPC,streams,4);end\n'
         '                    else read_words(RRPC,rpc_address,4);'),
        ('RPC_CHECK:if(scanning&&rpc_record[63:0]==0)', 'RPC_CHECK:if((scanning||searching)&&rpc_record[63:0]==0)'),
        ('else if(!scanning&&!rpc_key)',
         'else if(searching&&(rpc_record[79:64]!=user16||rpc_record[126:96]!=stream_id))state<=SCAN_NEXT;\n'
         '                else if(!scanning&&!searching&&!rpc_key)'),
        ('else if(window_record[127]&&op==WINDOW_UPDATE)',
         'else if(window_record[127]&&(op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY))'),
        ('else if(op==WINDOW_UPDATE)begin', 'else if(op==WINDOW_UPDATE||op==WINDOW_UPDATE_KEY)begin'),
        ('else begin connection_record[127:96]<=amount;rsp_initial_window<=amount;write_words(WCONN,0);end',
         'else if(searching)finish_error(3,10,0,0);\n'
         '                else begin connection_record[127:96]<=amount;rsp_initial_window<=amount;write_words(WCONN,0);end'),
    ):
        text = replace_once(text, old, new)
    text = text.replace('// Window bit 127 persists send closure without retiring the actual RPC.',
        '// WINDOW_UPDATE_KEY accepts only connection/stream/increment; address and generation must be zero.\n'
        '// The actual pool remains owned for lookup, binding validation, debit/update and result ACK.\n'
        '// Missing key status 3/detail 10 is neutral: parent classifies idle versus closed in wire order.\n'
        '// Window bit 127 persists send closure without retiring the actual RPC.')
    text = registered_geometry(text)
    target = source_path(root, 'rtl/http2_keyed_send_window_store.v'); target.write_text(text)
    owned = source_path(root, 'rtl/http2_owned_lifecycle_windows.v')
    joined = owned.read_text().replace('http2_owned_lifecycle_windows', 'http2_owned_keyed_windows')
    joined = joined.replace('http2_lifecycle_send_window_store #(', 'http2_keyed_send_window_store #(')
    joined_target = source_path(root, 'rtl/http2_owned_keyed_windows.v'); joined_target.write_text(joined)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (root / 'build/validation/keyed-send-windows-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_pool_keyed_updates', input_sha256={source_relative(p, root).as_posix(): sha(p)
        for p in (source, owned, Path(__file__))}, generated_sha256={source_relative(p, root).as_posix(): sha(p)
        for p in (target, joined_target)}, update_key_op=9, no_caller_address_or_generation=True,
        raw_control_integrated=False, unknown_stream_wire_classification_integrated=False,
        full_system_complete=False), indent=2) + '\n')
    print('Generated actual-pool key lookup + durable WINDOW_UPDATE, without caller binding metadata')


if __name__ == '__main__':
    main()
