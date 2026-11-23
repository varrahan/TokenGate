"""Register raw packet ownership and track actual per-descriptor lookup dispatch."""
import hashlib
import json
from pathlib import Path
import shutil

from rtl_paths import source_path


def main():
    root = Path(__file__).resolve().parents[1]
    original = source_path(root, 'rtl/http2_enveloped_parser_core.v')
    text = original.read_text()
    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    replace('reg rx_active,return_pending,owned_stream_valid,forward_quiet,return_ack_seen,generated_offered;',
        'reg rx_active,return_pending,owned_stream_valid,forward_quiet,return_ack_seen,generated_offered;\n'
        'reg rx_granted,return_lookup_issued;')
    replace('wire lookup_admit=return_pending&&forward_quiet&&!rx_active&&!control_valid&&!journal_recovery_required;',
        'wire lookup_admit=return_pending&&forward_quiet&&!rx_active&&!rx_granted&&!control_valid&&!journal_recovery_required;')
    replace('wire allow_new_rx=!journal_recovery_required&&!response_recovery_required&&!(s_axis_generated_tvalid&&reverse_admit)&&!(r_directory_valid&&lookup_admit);',
        '''// A pending GPU descriptor gets one quiet boundary for its real LOAD.
// The fence ends at its actual request handshake, or a terminal result that
// did not need a LOAD. Raw controls remain available throughout credit waits.
wire allow_new_rx=!journal_recovery_required&&!response_recovery_required&&
    !(s_axis_generated_tvalid&&reverse_admit)&&!(return_pending&&!return_lookup_issued)&&
    !(allow_config&&(control_valid||command_valid||queue_cfg_valid||stream_cfg_valid||cfg_schema_valid||cfg_unlock||queue_cfg_result_valid||stream_cfg_result_valid));''')
    replace('wire allow_config=!return_pending&&!generated_offered&&!shutdown_busy&&!cancel_valid&&!shutdown_recovery_required&&!response_recovery_required;',
        'wire allow_config=!return_pending&&!generated_offered&&!rx_granted&&!shutdown_busy&&!cancel_valid&&!shutdown_recovery_required&&!response_recovery_required;')
    replace('assign f_s_axis_rx_tvalid=s_axis_rx_tvalid&&(rx_active||allow_new_rx);',
        'assign f_s_axis_rx_tvalid=s_axis_rx_tvalid&&(rx_active||rx_granted);')
    replace('assign s_axis_rx_tready=f_s_axis_rx_tready&&(rx_active||allow_new_rx);',
        'assign s_axis_rx_tready=f_s_axis_rx_tready&&(rx_active||rx_granted);')
    replace('rx_active<=0;return_pending<=0;', 'rx_active<=0;rx_granted<=0;return_lookup_issued<=0;return_pending<=0;')
    replace('if(s_axis_rx_tvalid&&s_axis_rx_tready)rx_active<=!s_axis_rx_tlast;',
        '''// Reserve the packet before offering its first beat downstream. The
        // registered owner persists through first-beat stalls and packet gaps;
        // only its real TLAST handshake releases it. Source data/sideband use
        // the normal upstream AXIS stability obligation until that handshake.
        if(!rx_active&&!rx_granted&&s_axis_rx_tvalid&&allow_new_rx)rx_granted<=1;
        if(s_axis_rx_tvalid&&s_axis_rx_tready)begin
            rx_active<=!s_axis_rx_tlast;
            if(s_axis_rx_tlast)rx_granted<=0;
        end
        if((r_directory_valid&&r_directory_ready)||response_result_valid)return_lookup_issued<=1;''')
    replace('return_pending<=1;return_ack_seen<=0;return_user<=s_axis_generated_tuser;return_stream<=generated_stream;',
        'return_pending<=1;return_lookup_issued<=0;return_ack_seen<=0;return_user<=s_axis_generated_tuser;return_stream<=generated_stream;')
    replace('&&tx_idle&&!rx_active&&!s_axis_generated_tvalid', '&&tx_idle&&!rx_active&&!rx_granted&&!s_axis_generated_tvalid')
    previous = root / 'build/experiments/checked-close-address/rtl'
    target = root / 'build/experiments/registered-rx-grant/rtl'
    target.mkdir(parents=True, exist_ok=True)
    for p in previous.glob('*.v'): shutil.copy2(p, target / p.name)
    (target / original.name).write_text(text)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(phase='isolated_registered_rx_grant_generated', original_core_sha256=sha(original),
        previous_overrides={p.name: sha(p) for p in previous.glob('*.v')}, generator_sha256=sha(Path(__file__)),
        generated_sha256={p.name: sha(p) for p in target.glob('*.v')},
        production_rtl_changed=False, full_system_complete=False)
    (target.parent / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
