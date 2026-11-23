"""Join actual cached-directory authority, durable credits and DATA framing."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import named_instance


def main():
    root = Path(__file__).resolve().parents[1]
    owned_path = root / 'rtl/http2_owned_lifecycle_windows.v'
    framer_path = root / 'rtl/grpc_http2_response_framer.v'
    owned = ports(owned_path.read_text(), 'http2_owned_lifecycle_windows')
    framer = ports(framer_path.read_text(), 'grpc_http2_response_framer')
    hidden = {'frame_req_valid', 'frame_req_ready', 'frame_req_user', 'frame_req_stream',
              'frame_req_max_bytes', 'frame_grant_bytes', 'idle', 'clk', 'rst'}
    public = [p for p in owned if p[2] != 'idle'] + [p for p in framer if p[2] not in hidden]
    configs = [(d, w, n) for d, w, n in owned if d == 'input' and n.startswith('window_cfg_')]
    public += [(d, w, n.replace('window_', 'frame_', 1)) for d, w, n in configs]
    public += [('output', '', 'idle'), ('output', '', 'credit_parked'),
               ('output', '', 'credit_error_valid'), ('input', '', 'credit_error_ready')]
    errors = [(d, w, n) for d, w, n in owned if d == 'output' and n in (
        'window_rsp_status', 'window_rsp_detail', 'window_rsp_memory_status',
        'window_rsp_connection_error', 'window_rsp_http2_error', 'window_rsp_user', 'window_rsp_stream')]
    public += [('output', w, n.replace('window_rsp_', 'credit_error_')) for _, w, n in errors]
    assert len(public) == len({n for _, _, n in public})
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// DATA grants are supplied only by acknowledged actual window reservations.',
        '// Actual cached LOAD authority is retained through the public frame result.',
        '// Parent supplies ordered control commands; raw control and HEADERS remain external.',
        'module grpc_durable_window_framer #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23,MAX_MESSAGE_BYTES=65535', ' )(',
        ',\n'.join(f'    {d} wire {w} {n}' for d, w, n in public), ');',
        'localparam IDLE=0,CONTROL=1,RESERVE=2;',
        'reg [1:0] state;reg frame_active,parked;',
        'reg [USER_WIDTH-1:0] frame_owner;reg [30:0] frame_stream;',
        'reg [31:0] frame_generation;reg [MEMORY_ADDR_WIDTH-1:0] frame_address;',
        'wire owned_idle,framer_idle,framer_start_ready,owned_request_ready,owned_result_valid,owned_result_ready;',
        'wire frame_request_valid,frame_request_ready;wire [USER_WIDTH-1:0] frame_request_user;',
        'wire [30:0] frame_request_stream;wire [23:0] frame_request_maximum,grant_bytes;',
        'wire lease_matches=lease_rsp_valid&&lease_rsp_status==0&&lease_rsp_user==start_user&&lease_rsp_stream==start_stream;',
        'wire reserve_pending=frame_active&&frame_request_valid&&!parked;',
        'wire select_control=window_req_valid;',
        'assign start_ready=!rst&&framer_start_ready&&!frame_active&&lease_matches;',
        'assign window_req_ready=!rst&&state==IDLE&&owned_request_ready;',
        'assign window_rsp_valid=state==CONTROL&&owned_result_valid;',
        'assign credit_parked=parked;',
        'assign credit_error_valid=state==RESERVE&&owned_result_valid&&owned_window_rsp_status>1;',
        'assign frame_request_ready=state==RESERVE&&owned_result_valid&&',
        '    (owned_window_rsp_status==0||(owned_window_rsp_status>1&&credit_error_ready));',
        'assign grant_bytes=owned_window_rsp_status==0?owned_window_rsp_grant_bytes:24\'d0;',
        'assign owned_result_ready=state==CONTROL?window_rsp_ready:',
        '    state==RESERVE&&(owned_window_rsp_status==1||frame_request_valid&&frame_request_ready);',
        'assign idle=owned_idle&&framer_idle&&state==IDLE&&!frame_active&&!start_valid;']
    responses = [p for p in owned if p[0] == 'output' and p[2].startswith('window_rsp_') and p[2] != 'window_rsp_valid']
    lines += [f'wire {w} owned_{n};\nassign {n}=owned_{n};' for _, w, n in responses]
    lines += [f'assign {n.replace("window_rsp_", "credit_error_")}=owned_{n};' for _, _, n in errors]
    lines += [f'reg {w} saved_{n.replace("window_", "frame_", 1)};' for _, w, n in configs]
    connections = {n: n for _, _, n in owned}
    connections.update(idle='owned_idle',
        lease_rsp_ready='lease_rsp_ready&&!frame_active&&!start_valid&&!window_busy&&state==IDLE',
        window_req_valid='!rst&&state==IDLE&&(window_req_valid||reserve_pending)',
        window_req_ready='owned_request_ready', window_rsp_valid='owned_result_valid',
        window_rsp_ready='owned_result_ready')
    reserve_fields = dict(window_req_op="4'd5", window_req_maintenance="1'b0", window_req_user='frame_owner',
        window_req_stream='frame_stream', window_req_generation='frame_generation', window_req_record_address='frame_address',
        window_req_amount="{8'd0,frame_request_maximum}")
    for _, _, n in configs:
        reserve_fields[n] = 'saved_' + n.replace('window_', 'frame_', 1)
    connections.update({n: f'select_control?{n}:{value}' for n, value in reserve_fields.items()})
    connections.update({n: 'owned_' + n for _, _, n in responses})
    lines += [named_instance('http2_owned_lifecycle_windows',
        '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', 'owned', connections)]
    connections = {n: n for _, _, n in framer}
    connections.update(start_valid='start_valid&&!frame_active&&lease_matches', start_ready='framer_start_ready', idle='framer_idle',
        frame_req_valid='frame_request_valid', frame_req_ready='frame_request_ready', frame_req_user='frame_request_user',
        frame_req_stream='frame_request_stream', frame_req_max_bytes='frame_request_maximum', frame_grant_bytes='grant_bytes')
    lines += [named_instance('grpc_http2_response_framer',
        '.USER_WIDTH(USER_WIDTH),.MAX_MESSAGE_BYTES(MAX_MESSAGE_BYTES)', 'framer', connections)]
    lines += ['always @(posedge clk)begin', '    if(rst)begin',
        '        state<=IDLE;frame_active<=0;parked<=0;frame_owner<=0;frame_stream<=0;frame_generation<=0;frame_address<=0;']
    lines += [f'        saved_{n.replace("window_", "frame_", 1)}<=0;' for _, _, n in configs]
    lines += ['    end else begin', '        if(start_valid&&start_ready)begin',
        '            frame_active<=1;parked<=0;frame_owner<=lease_rsp_user;frame_stream<=lease_rsp_stream;',
        '            frame_generation<=lease_rsp_generation;frame_address<=lease_rsp_address;']
    lines += [f'            saved_{n.replace("window_", "frame_", 1)}<={n.replace("window_", "frame_", 1)};' for _, _, n in configs]
    lines += ['        end', '        if(result_valid&&result_ready)begin frame_active<=0;parked<=0;end',
        '        case(state)',
        '            IDLE:if(owned_request_ready&&(window_req_valid||reserve_pending))state<=window_req_valid?CONTROL:RESERVE;',
        '            CONTROL:if(owned_result_valid&&window_rsp_ready)begin',
        '                state<=IDLE;',
        '                if(owned_window_rsp_status==0&&owned_window_rsp_user==frame_owner&&',
        '                   (owned_window_rsp_stream==0||owned_window_rsp_stream==frame_stream)&&',
        '                   (owned_window_rsp_op==2||owned_window_rsp_op==3||owned_window_rsp_op==4||owned_window_rsp_op==8))parked<=0;',
        '            end',
        '            RESERVE:if(owned_result_valid&&owned_result_ready)begin state<=IDLE;parked<=owned_window_rsp_status==1;end',
        '            default:state<=IDLE;', '        endcase', '    end', 'end', 'endmodule', '`default_nettype wire', '']
    target = root / 'rtl/grpc_durable_window_framer.v'
    target.write_text('\n'.join(lines))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (root / 'build/validation/durable-window-framer-generation.json').write_text(json.dumps(dict(
        phase='generated_actual_durable_framer', input_sha256={p.relative_to(root).as_posix(): sha(p)
        for p in (owned_path, framer_path, Path(__file__))}, generated_sha256=sha(target),
        actual_cached_binding=True, external_credit_grants=False, raw_control_integrated=False,
        full_system_complete=False), indent=2) + '\n')
    print(f'Generated actual durable-window/framer join: {len(public)} ports, two memory clients')


if __name__ == '__main__':
    main()
