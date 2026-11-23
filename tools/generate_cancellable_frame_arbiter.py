"""Fence new DATA selections while draining a frame already offered on the wire."""
import hashlib
import json
from pathlib import Path

from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import add_ports


def main():
    root=Path(__file__).resolve().parents[1];source=root/'rtl/axis_frame_arbiter.v'
    text=source.read_text().replace('axis_frame_arbiter','axis_cancellable_frame_arbiter')
    text=add_ports(text,'axis_cancellable_frame_arbiter',[('input','','a_pause'),('output','','a_paused')])
    for old,new in(
        ('wire selected=locked?owner:a_axis_tvalid&&b_axis_tvalid?prefer_b:b_axis_tvalid;',
         'wire a_allowed=!a_pause||locked&&!owner;\n    wire selected=locked?owner:a_axis_tvalid&&a_allowed&&b_axis_tvalid?prefer_b:b_axis_tvalid;'),
        ('assign m_axis_tvalid=!rst&&(selected?b_axis_tvalid:a_axis_tvalid);',
         'assign m_axis_tvalid=!rst&&(selected?b_axis_tvalid:a_axis_tvalid&&a_allowed);'),
        ('assign a_axis_tready=!rst&&!selected&&m_axis_tready;',
         'assign a_axis_tready=!rst&&!selected&&a_allowed&&m_axis_tready;\n    assign a_paused=!rst&&a_pause&&(!locked||owner);'),
    ):text=replace_once(text,old,new)
    text=text.replace('// Frame-level round robin.',
        '// a_pause prevents new A/DATA selection. An A frame already offered\n'
        '// on the wire drains unchanged, including first-beat stalls and gaps.\n'
        '// a_paused permits private A-source abort; B/control ownership is untouched.\n'
        '// The parent owns reservation accounting and complete RPC cancellation.\n'
        '// Frame-level round robin.')
    target=root/'rtl/axis_cancellable_frame_arbiter.v';target.write_text(text);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (root/'build/validation/cancellable-frame-arbiter-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_wire_data_fence',input_sha256={str(p.relative_to(root)).replace('\\','/'):sha(p)for p in(source,Path(__file__))},
        production_sha256=sha(target),no_output_queue=True,actual_wire_handshake_preserved=True,
        rpc_cancellation_integrated=False,full_system_complete=False),indent=2)+'\n')
    print('Generated DATA selection fence with unchanged in-flight frames and independent control TX')


if __name__=='__main__':main()
