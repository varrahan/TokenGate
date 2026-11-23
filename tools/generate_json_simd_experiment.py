"""Overlay a real eight-lane JSON fast path on the audited full Parser."""
import hashlib
import json
from pathlib import Path
import shutil
from verify_two_fpga_application import closure

from rtl_paths import source_path, source_relative


FRONTEND='''    wire [63:0] window_data;
    wire [3:0] window_count,window_consumed,json_consumed,proto_consumed;
    wire window_valid,window_last,window_idle,json_ready,proto_input_ready;
    wire [USER_WIDTH+1:0] window_user;
    wire feed_enabled=state==PARSE && !feed_done;
    wire [7:0] in_byte=window_data[7:0];
    wire in_keep=window_count!=0,in_valid=window_valid,in_last=window_last;
    wire [USER_WIDTH+1:0] in_user=window_user;
    wire in_ready=feed_enabled&&(window_user[USER_WIDTH]?proto_input_ready:json_ready);
    wire unpack_idle=window_idle;
    assign window_consumed=window_user[USER_WIDTH]?proto_consumed:json_consumed;
    axis_compacting_window #(.INPUT_BYTES(64),.WINDOW_BYTES(8),.USER_WIDTH(USER_WIDTH+2)) input_windows(
        .clk(clk),.rst(rst),.s_data(fifo_data),.s_keep(fifo_keep),.s_valid(fifo_valid),.s_ready(fifo_ready),
        .s_last(fifo_last),.s_user(fifo_user),.m_data(window_data),.m_count(window_count),
        .m_valid(window_valid),.m_ready(in_ready),.m_consumed(window_consumed),
        .m_last(window_last),.m_user(window_user),.idle(window_idle));
'''

SCANNER='''    wire [7:0] s_data=s_window[7:0];
    wire s_keep=s_count!=0;
    wire [7:0] scan_quote,scan_backslash,scan_colon,scan_comma,scan_object_open,scan_object_close;
    wire [7:0] scan_array_open,scan_array_close,scan_whitespace,scan_control,scan_non_ascii,scan_structural,scan_plain;
    wire [3:0] scan_whitespace_count,scan_plain_count;
    wire norm_ascii_discard_ready;
    json_simd_scanner classifier(
        .data(s_window),.count(s_count),.quote(scan_quote),.backslash(scan_backslash),
        .colon(scan_colon),.comma(scan_comma),.object_open(scan_object_open),.object_close(scan_object_close),
        .array_open(scan_array_open),.array_close(scan_array_close),.whitespace(scan_whitespace),
        .control(scan_control),.non_ascii(scan_non_ascii),.structural(scan_structural),.plain_ascii(scan_plain),
        .leading_whitespace(scan_whitespace_count),.leading_plain_ascii(scan_plain_count));
    // Discard only unselected value text whose normalizer is between complete
    // scalars. Quotes, escapes, structural-looking punctuation, controls and
    // non-ASCII bytes always take the existing scalar validation path.
    wire plain_discard=state==STRING&&!str_key&&!str_target&&!raw_escape&&
        norm_ascii_discard_ready&&scan_plain_count!=0;
    assign consumed=!rst&&s_valid&&s_ready&&s_count!=0?
        (state==STRUCT&&scan_whitespace_count!=0?scan_whitespace_count:
         plain_discard?scan_plain_count:state==DRAIN?s_count:4'd1):4'd0;
'''


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    audit_path=root/'build/validation/progress-format-corpus.json';audit=json.loads(audit_path.read_text())
    assert audit['key']=='6dd529d376e06926'
    source=root/'build/wsl-reports/raw_envelope_progress_format_full_native_corpus/execution-sources/rtl'
    output=root/'build/experiments/json-simd';rtl=output/'rtl';rtl.mkdir(parents=True,exist_ok=True)
    inputs={};outputs={}
    for module,digest in audit['executed_parser_sha256'].items():
        path=source/(module+'.v');assert sha(path)==digest
        inputs[source_relative(path, root).as_posix()]=digest;shutil.copy2(path,rtl/path.name)
    def replace_once(text,before,after):
        assert text.count(before)==1,(before[:90],text.count(before));return text.replace(before,after)
    path=rtl/'proto_json_decoder.v';text=path.read_text()
    start=text.index('    wire [7:0] in_byte,unpack_byte;');end=text.index('    wire [7:0] key_data;',start)
    text=text[:start]+FRONTEND+text[end:]
    text=replace_once(text,'localparam integer OW=$clog2(FIFO_DEPTH+4);','localparam integer OW=$clog2(FIFO_DEPTH+12);')
    text=replace_once(text,'.s_data(in_byte),.s_keep(in_keep),\n        .s_valid(in_valid&&feed_enabled&&!in_user[USER_WIDTH]),.s_ready(json_ready),',
        '.s_window(window_data),.s_count(window_count),.consumed(json_consumed),\n        .s_valid(in_valid&&feed_enabled&&!in_user[USER_WIDTH]),.s_ready(json_ready),')
    text=replace_once(text,'.s_valid(window_valid),.s_ready(window_output_ready),.s_last(window_last),',
        '.s_valid(window_valid&&feed_enabled&&window_user[USER_WIDTH]),.s_ready(proto_input_ready),.s_last(window_last),')
    text=replace_once(text,'.s_user(window_user),.consumed(window_consumed),.field_number(proto_field)',
        '.s_user(window_user[USER_WIDTH-1:0]),.consumed(proto_consumed),.field_number(proto_field)')
    path.write_text(text)
    path=rtl/'speculative_json_fsm.v';text=path.read_text()
    text=replace_once(text,'// The SIMD structural fast path remains a separate performance requirement.',
        '// Eight-lane classification accelerates whitespace and validated-discardable ASCII runs.')
    text=replace_once(text,'input wire [7:0] s_data,input wire s_keep,input wire s_valid,output reg s_ready,',
        'input wire [63:0] s_window,input wire [3:0] s_count,output wire [3:0] consumed,\n    input wire s_valid,output reg s_ready,')
    text=replace_once(text,'    wire number_terminal=',SCANNER+'    wire number_terminal=')
    text=text.replace('whitespace(s_data)','scan_whitespace[0]')
    text=replace_once(text,"wire raw_close=s_keep && s_data==8'h22 && !raw_escape;",'wire raw_close=s_keep && scan_quote[0] && !raw_escape;')
    text=replace_once(text,'.s_valid(state==STRING && s_valid && (s_keep||s_last)),.s_ready(norm_ready),',
        '.s_valid(state==STRING && s_valid && (s_keep||s_last) && !plain_discard),.s_ready(norm_ready),')
    text=replace_once(text,'.m_last(norm_last),.m_user(),.packet_status(norm_status));',
        '.m_last(norm_last),.m_user(),.packet_status(norm_status),.ascii_discard_ready(norm_ascii_discard_ready));')
    text=replace_once(text,"else if(s_keep)raw_escape<=s_data==8'h5c ? !raw_escape : 0;",'else if(s_keep)raw_escape<=scan_backslash[0] ? !raw_escape : 0;')
    path.write_text(text)
    path=rtl/'json_string_normalizer.v';text=path.read_text()
    text=replace_once(text,'output wire [7:0] packet_status\n','output wire [7:0] packet_status,output wire ascii_discard_ready\n')
    text=replace_once(text,'    assign packet_status=status;',
        '    assign packet_status=status;\n    assign ascii_discard_ready=!rst&&state==NORMAL&&pending_count==0&&utf8_remaining==0&&status==0;')
    path.write_text(text)
    for name in('axis_compacting_window.v','json_simd_scanner.v'):
        path=source_path(root, Path('rtl') / (name));inputs[source_relative(path, root).as_posix()]=sha(path);shutil.copy2(path,rtl/name)
    for path in sorted(rtl.glob('*.v')):outputs['rtl/'+path.name]=sha(path)
    dependencies=closure('http2_enveloped_parser_application',output)
    assert {'axis_compacting_window','json_simd_scanner','speculative_json_fsm','json_string_normalizer'}<=dependencies.keys()
    result=dict(phase='isolated_json_simd_parser_generated',generator_sha256=sha(Path(__file__)),
        parent_corpus_audit_key=audit['key'],inputs_sha256=inputs,outputs_sha256=outputs,
        exact_parser_modules=len(dependencies),input_bits=512,window_bytes=8,
        actual_parallel_whitespace_consumption=True,actual_parallel_unselected_plain_ascii_consumption=True,
        selected_text_still_scalar=True,normalizer_validation_state_preserved=True,
        parser_public_ports_unchanged=True,primary_parser_rtl_modified=False,
        functional_simulation_verified=False,native_timing_verified=False,full_system_complete=False)
    (output/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key]for key in('phase','exact_parser_modules','input_bits','window_bytes')}))


if __name__=='__main__':main()
