"""Break the sparse-byte selection path before the DATA message BRAM."""
import hashlib
import json
from pathlib import Path

from generate_lifecycle_send_windows import replace_once
from generate_two_fpga_application import instance,named_instance,rename


def main():
    root=Path(__file__).resolve().parents[1]
    original=root/'rtl/grpc_http2_response_framer.v';text=original.read_text()
    text=rename(text,'grpc_http2_response_framer','grpc_registered_input_framer')
    text=replace_once(text,'wire [USER_WIDTH:0] input_user;', '''wire [USER_WIDTH:0] input_user;
    // Register data, keep, end marker and abort/context together. Sparse-lane
    // selection no longer feeds the message BRAM in the same clock interval.
    wire [7:0] unpacked_data;
    wire unpacked_keep,unpacked_valid,unpacked_last,unpacked_ready;
    wire [USER_WIDTH:0] unpacked_user;''')
    start,end,params,connections=instance(text,'axis_byte_unpacker','input_bytes')
    connections.update(m_data='unpacked_data',m_keep='unpacked_keep',m_valid='unpacked_valid',
        m_ready='unpacked_ready',m_last='unpacked_last',m_user='unpacked_user')
    stage=dict(clk='clk',rst='rst',s_axis_tdata='unpacked_data',s_axis_tkeep='unpacked_keep',
        s_axis_tvalid='unpacked_valid',s_axis_tready='unpacked_ready',s_axis_tlast='unpacked_last',s_axis_tuser='unpacked_user',
        m_axis_tdata='input_byte',m_axis_tkeep='input_keep',m_axis_tvalid='input_valid',m_axis_tready='input_ready',
        m_axis_tlast='input_last',m_axis_tuser='input_user')
    text=text[:start]+named_instance('axis_byte_unpacker',params,'input_bytes',connections)+'\n'+named_instance(
        'axis_skid_buffer','.DATA_WIDTH(8),.KEEP_WIDTH(1),.USER_WIDTH(USER_WIDTH+1)','input_stage',stage)+text[end:]
    text=replace_once(text,'assign start_ready=!rst&&state==IDLE&&unpack_idle;',
        'assign start_ready=!rst&&state==IDLE&&unpack_idle&&!input_valid;')
    text=replace_once(text,'assign idle=state==IDLE&&unpack_idle&&!m_axis_tx_tvalid;',
        'assign idle=state==IDLE&&unpack_idle&&!input_valid&&!m_axis_tx_tvalid;')
    framer=root/'rtl/grpc_registered_input_framer.v';framer.write_text(text)
    parent=root/'rtl/grpc_cancellable_window_framer.v'
    joined=rename(parent.read_text(),'grpc_cancellable_window_framer','grpc_cancellable_registered_framer')
    joined=replace_once(joined,'grpc_http2_response_framer #(', 'grpc_registered_input_framer #(')
    target=root/'rtl/grpc_cancellable_registered_framer.v';target.write_text(joined)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(phase='generated_registered_byte_input_framer',
        input_sha256={p.relative_to(root).as_posix():sha(p)for p in(original,parent,root/'rtl/axis_skid_buffer.v',Path(__file__))},
        generated_sha256={p.relative_to(root).as_posix():sha(p)for p in(framer,target)},
        sparse_lane_mux_registered_before_message_bram=True,data_keep_last_context_abort_registered_together=True,
        existing_framer_and_cancellation_variants_preserved=True,full_system_complete=False)
    (root/'build/validation/registered-input-framer-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Generated registered byte input and actual cancellation/framer variant')


if __name__=='__main__':main()
