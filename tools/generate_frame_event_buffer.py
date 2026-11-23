"""Cut the measured reverse-to-reader ready path with a drained event FIFO."""
import hashlib
import json
from pathlib import Path
import shutil

from verify_two_fpga_application import closure

from rtl_paths import source_relative


def buffered(source):
    changes=[]
    def change(old,new):
        nonlocal source
        assert source.count(old)==1,(old,source.count(old))
        source=source.replace(old,new);changes.append(dict(old=old,new=new))
    change('    reg accepting;', '''    reg accepting;
    wire reader_event_valid,reader_event_ready,buffer_event_valid;
    wire [1:0] reader_event_kind;
    wire [7:0] reader_event_data,reader_event_type,reader_event_flags;
    wire [23:0] reader_event_length;
    wire [30:0] reader_event_stream;
    wire reader_event_payload_last;
    wire [31:0] reader_event_error;
    wire [USER_WIDTH-1:0] reader_event_user;
    wire reader_completion_valid,reader_completion_ready;
    wire event_buffer_empty=!buffer_event_valid;
    // Every event carries its complete frame/context snapshot. Neither ready
    // nor valid/data has a combinational path across this registered handoff.
    axis_skid_buffer #(.DATA_WIDTH(114),.KEEP_WIDTH(1),.USER_WIDTH(USER_WIDTH)) event_buffer(
        .clk(clk),.rst(rst),
        .s_axis_tdata({reader_event_kind,reader_event_data,reader_event_length,reader_event_type,
            reader_event_flags,reader_event_stream,reader_event_payload_last,reader_event_error}),
        .s_axis_tkeep(1'b1),.s_axis_tvalid(reader_event_valid&&!rst),.s_axis_tready(reader_event_ready),
        .s_axis_tlast(1'b0),.s_axis_tuser(reader_event_user),
        .m_axis_tdata({event_kind,event_data,event_length,event_type,event_flags,event_stream,event_payload_last,event_error}),
        .m_axis_tkeep(),.m_axis_tvalid(buffer_event_valid),.m_axis_tready(event_ready&&!rst),
        .m_axis_tlast(),.m_axis_tuser(event_user));
    assign event_valid=buffer_event_valid&&!rst;
    // The connection owner may save state/finish payload only after every
    // buffered event has reached the original consumer. Reader RESULT holds
    // the final state stable while this drain and the public result ACK wait.
    assign completion_valid=reader_completion_valid&&event_buffer_empty;
    assign reader_completion_ready=completion_ready&&event_buffer_empty;''')
    change('assign start_ready=core_ready&&unpack_idle&&!accepting;',
           'assign start_ready=core_ready&&unpack_idle&&!accepting&&event_buffer_empty;')
    change('assign idle=core_idle&&unpack_idle&&!accepting;',
           'assign idle=core_idle&&unpack_idle&&!accepting&&event_buffer_empty;')
    change('.start_valid(start_valid&&unpack_idle&&!accepting)',
           '.start_valid(start_valid&&unpack_idle&&!accepting&&event_buffer_empty)')
    for suffix in ('valid','ready','kind','data','length','type','flags','stream','payload_last','error','user'):
        change('.event_'+suffix+'(event_'+suffix+')','.event_'+suffix+'(reader_event_'+suffix+')')
    change('.completion_valid(completion_valid)', '.completion_valid(reader_completion_valid)')
    change('.completion_ready(completion_ready)', '.completion_ready(reader_completion_ready)')
    inverse=source
    for row in reversed(changes):
        assert inverse.count(row['new'])==1
        inverse=inverse.replace(row['new'],row['old'])
    return source,inverse,changes


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    audit=json.loads((root/'build/validation/json-simd-corpus.json').read_text())
    assert audit['key']=='2509134d2630b47e' and audit['full_native_corpus_verified']
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    folder=root/'build/experiments/frame-event-buffer';folder.mkdir(parents=True,exist_ok=False)
    target=folder/'rtl';target.mkdir()
    inputs={}
    for name,digest in audit['executed_parser_sha256'].items():
        path=original/'rtl'/(name+'.v');assert sha(path)==digest
        shutil.copy2(path,target/path.name);inputs[source_relative(path, root).as_posix()]=digest
    path=target/'http2_axis_ingress.v';old=path.read_text()
    updated,restored,certificate=buffered(old);assert restored==old
    path.write_bytes(updated.encode())
    modules=closure('http2_enveloped_parser_application',folder);assert len(modules)==76
    result=dict(phase='frame_event_buffer_generated',parent_corpus_audit_key=audit['key'],
        generator_sha256=sha(Path(__file__)),inputs_sha256=inputs,
        outputs_sha256={'rtl/'+p.name:sha(p) for p in target.glob('*.v')},
        only_changed_module='http2_axis_ingress',exact_parser_modules=76,event_payload_bits=114,event_context_bits=16,
        two_registered_slots=True,completion_and_idle_require_event_buffer_empty=True,
        no_reader_state_or_snapshot_layout_changed=True,source_edit_certificate=certificate,
        full_protocol_verified=False,native_timing_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    print(json.dumps({k:result[k] for k in ('phase','exact_parser_modules','only_changed_module','event_payload_bits')}))


if __name__=='__main__':main()
