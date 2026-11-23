"""Join actual Parser-side RPC/serializer ownership to DATA framing."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import instance, named_instance

from rtl_paths import source_path, source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    rpc_path = source_path(root, 'rtl/rpc_response_parser_partition.v')
    core_path = source_path(root, 'rtl/http2_parser_partition_core.v')
    app_path = source_path(root, 'rtl/http2_parser_fpga_application.v')
    rpc = ports(rpc_path.read_text(), 'rpc_response_parser_partition')
    serializer_public = [p for p in ports(app_path.read_text(), 'http2_parser_fpga_application') if p[2].startswith('link_s_')]
    public = [p for p in rpc if p[2] != 'local_tx_accepted'] + serializer_public
    public += [('input', '[23:0]', 'cfg_peer_max_frame_bytes'),
        ('output', '', 'frame_req_valid'), ('input', '', 'frame_req_ready'),
        ('output', '[USER_WIDTH-1:0]', 'frame_req_user'), ('output', '[30:0]', 'frame_req_stream'),
        ('output', '[23:0]', 'frame_req_max_bytes'), ('input', '[23:0]', 'frame_grant_bytes'),
        ('output', '[31:0]', 'result_serialized_bytes'), ('output', '[31:0]', 'result_wire_bytes'),
        ('output', '[31:0]', 'result_frames'), ('output', '', 'result_progress_committed')]
    assert len({p[2] for p in public}) == len(public)
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// Actual Parser-side RPC controller, Unicode/serializer and gRPC DATA framing.',
        '// Remote inverse/BPE remain on Tokenizer. Credit ledger and HEADERS/trailers remain external.',
        'module rpc_grpc_parser_response #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_TEXT_BYTES=16384,',
        'parameter integer MAX_MESSAGE_BYTES=6*MAX_TEXT_BYTES+46',
        ')(', ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');',
        'reg active,kill_ungranted,directory_requested,release_pending,transport_recovery;',
        'reg [USER_WIDTH-1:0] owner;',
        'reg [MEMORY_ADDR_WIDTH-1:0] held_address,transport_recovery_address;',
        'wire rpc_ready,rpc_result_valid,rpc_directory_ready,rpc_lease,rpc_idle,rpc_recovery,rpc_buffered;',
        'wire [7:0] rpc_stage,rpc_status,rpc_memory;',
        'wire [31:0] rpc_bytes;',
        'wire [MEMORY_ADDR_WIDTH-1:0] rpc_recovery_address;',
        'wire [511:0] raw_data;wire [63:0] raw_keep;wire raw_valid,raw_ready,raw_last;',
        'wire [USER_WIDTH-1:0] raw_user;',
        'wire framer_start_ready,framer_valid,framer_result,framer_idle,framer_tx_emitted,framer_message_ready;',
        'wire [7:0] framer_status;',
        'wire [31:0] framer_message_bytes,framer_wire_bytes,framer_frames;',
        'wire accept_guard=!active&&!transport_recovery;',
        'assign s_axis_tokens_tready=!rst&&accept_guard&&rpc_ready&&framer_start_ready;',
        'wire accept=s_axis_tokens_tvalid&&s_axis_tokens_tready;',
        'wire authorized=rpc_result_valid&&rpc_status==0&&directory_requested&&release_pending&&!kill_ungranted;',
        '// Durable progress commits before credit reservation or any wire output.',
        'assign frame_req_valid=framer_valid&&authorized;',
        'assign raw_ready=active&&!kill_ungranted&&framer_message_ready;',
        'wire failed_before_grant=rpc_result_valid&&rpc_status!=0;',
        'assign result_valid=active&&rpc_result_valid&&(!directory_requested||release_pending)&&',
        '    (failed_before_grant?kill_ungranted&&framer_idle:framer_result);',
        'wire retire=result_valid&&result_ready;',
        '// The real LOAD is acknowledged only with public retirement, even though',
        '// the child has already completed its local RELEASE -> RESULT transition.',
        'assign directory_result_ready=retire&&directory_requested&&release_pending;',
        'assign directory_lease_active=active&&directory_requested;',
        'assign result_stage=rpc_status!=0?rpc_stage:framer_status!=0?8\'d16:8\'d0;',
        'assign result_status=rpc_status!=0?rpc_status:framer_status;',
        'assign result_memory_status=rpc_status!=0?rpc_memory:8\'d0;',
        'assign result_bytes=result_status==0?rpc_bytes:32\'d0;',
        'assign result_serialized_bytes=framer_message_bytes;',
        'assign result_wire_bytes=framer_wire_bytes;assign result_frames=framer_frames;',
        'assign result_tx_emitted=framer_tx_emitted;',
        'assign result_progress_committed=rpc_result_valid&&rpc_status==0;',
        'wire transport_failure=active&&rpc_result_valid&&rpc_status==0&&framer_result&&framer_status!=0;',
        'assign recovery_required=rpc_recovery||transport_recovery||transport_failure;',
        'assign recovery_address=rpc_recovery?rpc_recovery_address:',
        '    transport_failure?held_address:transport_recovery_address;',
        'assign idle=!active&&!kill_ungranted&&rpc_idle&&framer_idle;',
        'always @(posedge clk)begin',
        '    if(rst)begin active<=0;kill_ungranted<=0;directory_requested<=0;release_pending<=0;',
        '        owner<=0;held_address<=0;transport_recovery<=0;transport_recovery_address<=0;end',
        '    else begin',
        '        if(accept)begin active<=1;owner<=s_axis_tokens_tuser;kill_ungranted<=0;directory_requested<=0;release_pending<=0;held_address<=0;end',
        '        if(active&&directory_valid&&directory_ready)directory_requested<=1;',
        '        if(active&&directory_requested&&directory_result_valid)held_address<=directory_address;',
        '        if(active&&rpc_directory_ready&&directory_result_valid)release_pending<=1;',
        '        // No grant is permitted until child success. A failed child therefore',
        '        // has no wire bytes or reserved credits; its private buffer can reset',
        '        // without resetting a connection or releasing the actual directory LOAD.',
        '        if(active&&failed_before_grant)kill_ungranted<=1;',
        '        if(transport_failure)begin transport_recovery<=1;transport_recovery_address<=held_address;end',
        '        if(retire)begin active<=0;kill_ungranted<=0;directory_requested<=0;release_pending<=0;end',
        '    end', 'end']
    connections = {n: n for _, _, n in rpc}
    connections.update(s_axis_tokens_tvalid='s_axis_tokens_tvalid&&accept_guard&&framer_start_ready', s_axis_tokens_tready='rpc_ready',
        m_axis_tx_tdata='', m_axis_tx_tkeep='', m_axis_tx_tvalid='', m_axis_tx_tready='raw_ready',
        m_axis_tx_tlast='', m_axis_tx_tuser='', result_valid='rpc_result_valid', result_ready='retire',
        result_stage='rpc_stage', result_status='rpc_status', result_memory_status='rpc_memory', result_bytes='rpc_bytes',
        result_tx_emitted='rpc_buffered', recovery_required='rpc_recovery', recovery_address='rpc_recovery_address',
        directory_result_ready='rpc_directory_ready', directory_lease_active='rpc_lease', idle='rpc_idle',
        local_tx_accepted='raw_valid&&raw_ready')
    lines.append(named_instance('rpc_response_parser_partition',
        '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)', 'rpc', connections))
    _, _, parameters, serializer = instance(core_path.read_text(), 'utf8_serialized_chunk', 'response_serializer')
    serializer.update(m_axis_tx_tdata='raw_data', m_axis_tx_tkeep='raw_keep', m_axis_tx_tvalid='raw_valid',
                      m_axis_tx_tready='raw_ready', m_axis_tx_tlast='raw_last', m_axis_tx_tuser='raw_user')
    lines.append(named_instance('utf8_serialized_chunk', parameters, 'serializer', serializer))
    lines += [named_instance('grpc_http2_response_framer',
        '.USER_WIDTH(USER_WIDTH),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)', 'framer', dict(
            clk='clk', rst='rst||kill_ungranted', start_valid='accept', start_ready='framer_start_ready',
            start_user='s_axis_tokens_tuser', start_stream='s_stream', cfg_peer_max_frame_bytes='cfg_peer_max_frame_bytes',
            s_axis_message_tdata='raw_data', s_axis_message_tkeep='raw_keep', s_axis_message_tvalid='raw_valid&&active&&!kill_ungranted',
            s_axis_message_tready='framer_message_ready', s_axis_message_tlast='raw_last', s_axis_message_tuser='owner',
            s_axis_message_abort='raw_user!=result_application', frame_req_valid='framer_valid', frame_req_ready='frame_req_ready&&authorized',
            frame_req_user='frame_req_user', frame_req_stream='frame_req_stream', frame_req_max_bytes='frame_req_max_bytes', frame_grant_bytes='frame_grant_bytes',
            m_axis_tx_tdata='m_axis_tx_tdata', m_axis_tx_tkeep='m_axis_tx_tkeep', m_axis_tx_tvalid='m_axis_tx_tvalid', m_axis_tx_tready='m_axis_tx_tready',
            m_axis_tx_tlast='m_axis_tx_tlast', m_axis_tx_tuser='m_axis_tx_tuser', result_valid='framer_result', result_ready='retire',
            result_status='framer_status', result_user='', result_stream='', result_message_bytes='framer_message_bytes',
            result_wire_bytes='framer_wire_bytes', result_frames='framer_frames', result_tx_emitted='framer_tx_emitted', idle='framer_idle')),
        'endmodule', '`default_nettype wire', '']
    target = source_path(root, 'rtl/rpc_grpc_parser_response.v')
    target.write_text('\n'.join(lines))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(phase='generated_parser_rpc_and_data_framing',
        inputs_sha256={source_relative(p, root).as_posix(): sha(p) for p in (rpc_path, core_path, app_path, Path(__file__))},
        generated_sha256=sha(target), full_transport_verified=False, distributed_image_leases_verified=False)
    (root / 'build/validation/rpc-grpc-parser-generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Generated actual Parser RPC/serializer/DATA-framer join with public-retirement LOAD fencing')


if __name__ == '__main__':
    main()
