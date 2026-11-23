"""Isolate the measured keyed-window config arithmetic behind one register stage."""
import hashlib
import json
from pathlib import Path

from generate_lifecycle_send_windows import replace_once

from rtl_paths import source_path


def registered_geometry(text):
    if 'RESULT=12,GEOMETRY=13;' in text:
        assert 'reg [63:0] contexts_end,streams_end,windows_end,context_full,context_limit;' in text
        assert 'context_limit<=contexts_end' in text and 'state<=GEOMETRY;' in text
        return text
    text = replace_once(text, 'WRITE_WAIT=11,RESULT=12;', 'WRITE_WAIT=11,RESULT=12,GEOMETRY=13;')
    text = replace_once(text,
        "    wire [63:0] contexts_end={1'b0,contexts}+{1'b0,context_bytes};\n"
        "    wire [63:0] streams_end={1'b0,streams}+{1'b0,stream_bytes};\n"
        "    wire [63:0] windows_end={1'b0,windows}+{1'b0,window_bytes};\n"
        "    wire [63:0] context_full={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);",
        '    // Retain full-width bounds; arithmetic and config/error fanout use separate clocks.\n'
        '    reg [63:0] contexts_end,streams_end,windows_end,context_full,context_limit;')
    text = replace_once(text, 'context_full+256<=contexts_end', 'context_limit<=contexts_end')
    text = replace_once(text,
        'recovery_context<=0;recovery_owner<=0;raw_header<=0;',
        'contexts_end<=0;streams_end<=0;windows_end<=0;context_full<=0;context_limit<=0;\n'
        '            recovery_context<=0;recovery_owner<=0;raw_header<=0;')
    text = replace_once(text, '                state<=CHECK;\n            end\n            CHECK:begin',
        '                state<=GEOMETRY;\n            end\n'
        '            GEOMETRY:begin\n'
        "                contexts_end<={1'b0,contexts}+{1'b0,context_bytes};\n"
        "                streams_end<={1'b0,streams}+{1'b0,stream_bytes};\n"
        "                windows_end<={1'b0,windows}+{1'b0,window_bytes};\n"
        "                context_full<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8);\n"
        "                context_limit<={1'b0,contexts}+({{(64-USER_WIDTH){1'b0}},owner}<<8)+64'd256;\n"
        '                state<=CHECK;\n            end\n            CHECK:begin')
    return text


def main():
    root = Path(__file__).resolve().parents[1]
    source = source_path(root, 'rtl/http2_keyed_send_window_store.v')
    text = registered_geometry(source.read_text())
    target = root / 'build/rtl-experiments/keyed_registered_geometry/http2_keyed_send_window_store.v'
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(phase='isolated_registered_geometry_candidate', source_sha256=sha(source),
        candidate_sha256=sha(target), generator_sha256=sha(Path(__file__)),
        additional_command_cycles=1, bounds_width_bits=64, primary_rtl_changed=False,
        actual_native_trigger='rpc_grpc_keyed_scu35_initial setup WNS -0.165 ns',
        clock_period_ns=4, simulation_passed=False, native_timing_verified=False)
    (target.parent / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
