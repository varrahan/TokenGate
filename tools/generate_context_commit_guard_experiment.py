"""Isolate the actual raw-context commit witness and scoped window-reader guard."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from rtl_paths import source_path, source_relative


FIELDS = [('context_write_busy', ''), ('context_write_user', '[USER_WIDTH-1:0] '),
          ('context_write_address', '[MEMORY_ADDR_WIDTH-1:0] '),
          ('context_write_fault', ''), ('context_write_fault_user', '[USER_WIDTH-1:0] '),
          ('context_write_fault_address', '[MEMORY_ADDR_WIDTH-1:0] '),
          ('context_write_fault_memory_status', '[7:0] ')]


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/registered-rx-grant/rtl'
    target = root / 'build/experiments/context-commit-guard/rtl'
    target.mkdir(parents=True, exist_ok=True)
    originals = {}
    for p in previous.glob('*.v'):
        shutil.copy2(p, target / p.name)

    def source(name):
        p = previous / (name + '.v')
        if not p.is_file(): p = source_path(root, Path('rtl') / (name + '.v'))
        originals[name] = p
        return p.read_text()

    def replace(text, old, new):
        assert text.count(old) == 1, old
        return text.replace(old, new)

    def ports(text, direction):
        start = text.index(')(\n', text.index('module ')) + 3
        return text[:start] + ''.join('    ' + direction + ' wire ' + width + name + ',\n' for name, width in FIELDS) + text[start:]

    def connect(text, instance):
        marker = re.search(r'\b' + re.escape(instance) + r'\(\s*\n', text)
        assert marker, instance
        return text[:marker.end()] + ''.join('    .' + n + '(' + n + '),\n' for n, _ in FIELDS) + text[marker.end():]

    def feature(text):
        start = text.index('#(') + 2
        return text[:start] + 'parameter integer ENABLE_CONTEXT_GUARD=0,\n' + text[start:]

    def child_feature(text, module, value):
        return replace(text, module + ' #(', module + ' #(.ENABLE_CONTEXT_GUARD(' + value + '),')

    def save(name, text): (target / (name + '.v')).write_text(text)

    name = 'http2_connection_ingress'
    text = ports(source(name), 'output')
    text = replace(text, '    reg [3:0] state;', '''    reg [USER_WIDTH-1:0] fault_user;
    reg [7:0] fault_memory_status;
    // Busy covers the invalidation request through the real final write ACK.
    // Fault identity survives subsequent requests until validated recovery.
    assign context_write_busy=state>=INVALIDATE_REQ&&state<=COMMIT_WAIT;
    assign context_write_user=context_id;
    assign context_write_address=record_address;
    assign context_write_fault=recovery_required;
    assign context_write_fault_user=fault_user;
    assign context_write_fault_address=recovery_address;
    assign context_write_fault_memory_status=fault_memory_status;
    reg [3:0] state;''')
    text = replace(text, 'begin recovery_required<=1;recovery_address<=record_address;fail(status,detail,slot_status);end',
        'begin recovery_required<=1;recovery_address<=record_address;fault_user<=context_id;fault_memory_status<=slot_status;fail(status,detail,slot_status);end')
    text = replace(text, 'state<=IDLE;record_address<=0;', 'state<=IDLE;fault_user<=0;fault_memory_status<=0;record_address<=0;')
    save(name, text)

    for name, child in [('http2_controlled_hpack_ingress', 'scheduler'),
                        ('http2_classified_parser_transport', 'transport')]:
        save(name, connect(ports(source(name), 'output'), child))

    chain = [('rpc_grpc_http2_return', 'http2_enveloped_frame_grants', 'directory_service'),
             ('http2_enveloped_frame_grants', 'http2_owned_pipelined_cancel_windows', 'owned'),
             ('http2_owned_pipelined_cancel_windows', 'http2_pipelined_cancel_window_store', 'windows')]
    for name, child, instance in chain:
        save(name, connect(child_feature(feature(ports(source(name), 'input')), child, 'ENABLE_CONTEXT_GUARD'), instance))

    name = 'http2_pipelined_cancel_window_store'
    text = feature(ports(source(name), 'input'))
    text = replace(text, 'GEOMETRY=13,RESERVE_APPLY=14;', 'GEOMETRY=13,RESERVE_APPLY=14,CONTEXT_COMMIT_WAIT=15;')
    text = replace(text, '    reg [63:0] raw_header;', '''    reg raw_read_overlap;
    wire writer_matches=ENABLE_CONTEXT_GUARD&&context_write_user==owner&&context_write_address==context_address;
    wire writer_busy=writer_matches&&context_write_busy;
    wire writer_fault=ENABLE_CONTEXT_GUARD&&context_write_fault&&context_write_fault_user==owner&&context_write_fault_address==context_address;
    reg [63:0] raw_header;''')
    text = replace(text, 'begin read_phase<=phase;read_address<=address;read_count<=count;read_index<=0;state<=READ_REQ;',
        'begin read_phase<=phase;read_address<=address;read_count<=count;read_index<=0;state<=READ_REQ;\n            if(phase==RRAW)raw_read_overlap<=writer_busy;')
    text = replace(text, 'recovery_required<=0;recovery_address<=0;selected_grant<=0;',
        'recovery_required<=0;recovery_address<=0;selected_grant<=0;raw_read_overlap<=0;')
    text = replace(text, '        end else case(state)', '''        end else begin
        // A save can finish between the memory read and RAW_CHECK. Retain
        // that overlap, discard the torn snapshot, and issue a fresh read.
        if(writer_busy&&read_phase==RRAW&&(state==READ_REQ||state==READ_WAIT||state==RAW_CHECK))raw_read_overlap<=1;
        case(state)''')
    text = replace(text, '            RAW_CHECK:if(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])finish_error(3,1,2,1);', '''            CONTEXT_COMMIT_WAIT:begin
                if(writer_fault)begin rsp_memory_status<=context_write_fault_memory_status;quarantine(5,13,2,context_address);end
                else if(!writer_busy)read_words(RRAW,context_address,1);
            end
            RAW_CHECK:if(writer_fault)begin rsp_memory_status<=context_write_fault_memory_status;quarantine(5,13,2,context_address);end
                else if(writer_busy||raw_read_overlap)state<=CONTEXT_COMMIT_WAIT;
                else if(raw_header[31:0]!=RAW_MAGIC||!raw_header[32])finish_error(3,1,2,1);''')
    text = replace(text, '        endcase\n    end\nendmodule', '        endcase\n        end\n    end\nendmodule')
    save(name, text)

    name = 'http2_enveloped_parser_core'
    text = source(name)
    pos = text.index(');', text.index('module ')) + 2
    text = text[:pos] + '\n' + ''.join('wire ' + width + field + ';\n' for field, width in FIELDS) + text[pos:]
    text = connect(connect(text, 'forward'), 'reverse')
    text = child_feature(text, 'rpc_grpc_http2_return', '1')
    save(name, text)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(phase='isolated_context_commit_guard_generated',
        previous_overrides={p.name: sha(p) for p in previous.glob('*.v')},
        changed_inputs={n: dict(path=str(source_relative(p, root)), sha256=sha(p)) for n, p in originals.items()},
        generated_sha256={p.name: sha(p) for p in target.glob('*.v')},
        generator_sha256=sha(Path(__file__)), production_rtl_changed=False, full_system_complete=False)
    (target.parent / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(target)


if __name__ == '__main__': main()
