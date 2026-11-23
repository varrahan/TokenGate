"""Isolate a drained semantic-event handoff at the measured payload CE path."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_two_fpga_application import closure


def buffered(source):
    original = source
    # Redirect every original m_* reference, including all original state
    # equations, to the unchanged producer side of the registered handoff.
    names = ('valid', 'ready', 'kind', 'data', 'arg0', 'arg1', 'length', 'type', 'flags', 'stream', 'user')
    for name in names:
        source = re.sub(r'\bm_' + name + r'\b', 'producer_' + name, source)
    header_end = source.index(');')
    header = source[:header_end]
    for name in names:
        header = re.sub(r'\bproducer_' + name + r'\b', 'm_' + name, header)
    header = header.replace('output reg m_', 'output wire m_')
    header = header.replace('output reg [3:0] m_kind', 'output wire [3:0] m_kind')
    header = header.replace('output reg [7:0] m_data', 'output wire [7:0] m_data')
    header = header.replace('output reg [31:0] m_arg0,m_arg1', 'output wire [31:0] m_arg0,m_arg1')
    source = header + source[header_end:]
    insertion = '''
    reg producer_valid;
    wire producer_ready;
    reg [3:0] producer_kind;
    reg [7:0] producer_data;
    reg [31:0] producer_arg0,producer_arg1;
    wire [23:0] producer_length;
    wire [7:0] producer_type,producer_flags;
    wire [30:0] producer_stream;
    wire [USER_WIDTH-1:0] producer_user;
    wire buffer_valid;
    wire event_buffer_empty=!buffer_valid;
    // Capture the full semantic event with its frame/context snapshot. The
    // two payload slots have no downstream-ready path in their D/EN cones.
    axis_pingpong_skid_buffer #(.DATA_WIDTH(147),.KEEP_WIDTH(1),.USER_WIDTH(USER_WIDTH)) semantic_event_buffer(
        .clk(clk),.rst(rst),
        .s_axis_tdata({producer_kind,producer_data,producer_arg0,producer_arg1,
            producer_length,producer_type,producer_flags,producer_stream}),
        .s_axis_tkeep(1'b1),.s_axis_tvalid(producer_valid&&!rst),.s_axis_tready(producer_ready),
        .s_axis_tlast(1'b0),.s_axis_tuser(producer_user),
        .m_axis_tdata({m_kind,m_data,m_arg0,m_arg1,m_length,m_type,m_flags,m_stream}),
        .m_axis_tkeep(),.m_axis_tvalid(buffer_valid),.m_axis_tready(m_ready&&!rst),
        .m_axis_tlast(),.m_axis_tuser(m_user));
    assign m_valid=buffer_valid&&!rst;
'''
    position = source.index(');') + 2
    source = source[:position] + insertion + source[position:]
    edits = [
        ('assign start_ready=!rst&&state==IDLE;',
         'assign start_ready=!rst&&state==IDLE&&event_buffer_empty;'),
        ('assign result_valid=state==RESULT;',
         'assign result_valid=state==RESULT&&event_buffer_empty;'),
        ('assign idle=state==IDLE&&!producer_valid&&!(start_valid&&start_ready);',
         'assign idle=state==IDLE&&!producer_valid&&event_buffer_empty&&!(start_valid&&start_ready);'),
        ('RESULT:if(result_ready)state<=IDLE;',
         'RESULT:if(result_ready&&event_buffer_empty)state<=IDLE;'),
    ]
    for old, new in edits:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    restored = source
    for old, new in reversed(edits):
        assert restored.count(new) == 1
        restored = restored.replace(new, old)
    assert restored.count(insertion) == 1
    restored = restored.replace(insertion, '')
    # Restore the original port declarations before reversing the identifier
    # substitution, making the certificate exact at the byte/text level.
    original_header = original[:original.index(');')]
    restored = original_header + restored[restored.index(');'):]
    for name in names:
        restored = re.sub(r'\bproducer_' + name + r'\b', 'm_' + name, restored)
    assert restored == original
    return source, dict(renamed_internal_outputs=list(names), insertion=insertion,
        replacements=edits, original_port_declarations_preserved_as_wires=True,
        exact_inverse_verified=True)


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    audit = read(root / 'build/validation/frame-owned-quiet-corpus.json')
    native = read(root / 'build/validation/frame-owned-quiet-parser-native.json')
    assert audit['key'] == 'b89b9aea0dd403cb' and audit['full_native_corpus_verified']
    assert native['key'] == 'f9e7e63dced475c3' and not native['timing_met']
    original = root / 'build/experiments/frame-owned-quiet'
    target = root / 'build/experiments/payload-event-buffer'
    target.mkdir(parents=True, exist_ok=False)
    for module, digest in audit['executed_parser_sha256'].items():
        path = original / 'rtl' / (module + '.v')
        assert sha(path) == digest
        destination = target / 'rtl' / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    path = target / 'rtl/http2_payload_decoder.v'
    before = path.read_bytes().decode()
    after, certificate = buffered(before)
    path.write_bytes(after.encode())
    fifo = root / 'build/experiments/frame-event-pingpong/rtl/axis_pingpong_skid_buffer.v'
    fifo_audit = read(root / 'build/validation/frame-event-pingpong.json')
    assert fifo_audit['key'] == '806c3d55fa92d7b8'
    shutil.copy2(fifo, target / 'rtl' / fifo.name)
    dependencies = closure('http2_enveloped_parser_application', target)
    assert len(dependencies) == 77
    for name, path in dependencies.items():
        if name not in ('http2_payload_decoder', 'axis_pingpong_skid_buffer'):
            assert sha(path) == audit['executed_parser_sha256'][name]
    result = dict(phase='payload_event_buffer_generated',
        parent_corpus_audit_key=audit['key'], parent_native_audit_key=native['key'],
        fifo_prior_audit_key=fifo_audit['key'], fifo_sha256=sha(fifo),
        exact_parser_modules=77, semantic_payload_bits=147, semantic_context_bits=16,
        only_changed_existing_module='http2_payload_decoder',
        added_module='axis_pingpong_skid_buffer', source_edit_certificate=certificate,
        semantic_state_and_snapshot_layout_unchanged=True, completion_and_idle_require_buffer_empty=True,
        generator_sha256=sha(Path(__file__)),
        outputs_sha256={'rtl/' + p.name: sha(p) for p in (target / 'rtl').glob('*.v')},
        functional_verified=False, native_timing_verified=False, full_system_complete=False)
    (target / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    print(json.dumps({k: result[k] for k in ('phase', 'exact_parser_modules', 'semantic_payload_bits')}))


if __name__ == '__main__':
    main()
