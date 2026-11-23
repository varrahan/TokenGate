"""Generate a cached response lease around the actual external stream store."""
import hashlib
import json
from pathlib import Path

from generate_bidirectional_application import ports
from generate_two_fpga_application import named_instance

from rtl_paths import source_path, source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    base = source_path(root, 'rtl/grpc_stream_store.v')
    public = ports(base.read_text(), 'grpc_stream_store')
    responses = [(d, w, n) for d, w, n in public if n.startswith('rsp_') and d == 'output']
    command = [(d, w, n) for d, w, n in public if d == 'input' and (n.startswith('req_') and n != 'req_valid' or n.startswith('cfg_pool_'))]
    extra = [('input', '', 'lease_valid'), ('output', '', 'lease_ready'),
        ('input', '[USER_WIDTH-1:0]', 'lease_user'), ('input', '[30:0]', 'lease_stream'),
        ('input', '[MEMORY_ADDR_WIDTH-1:0]', 'lease_pool_base'), ('input', '[MEMORY_ADDR_WIDTH:0]', 'lease_pool_bytes'),
        ('input', '', 'lease_rsp_ready'), ('output', '', 'lease_active')]
    extra += [(d, w, 'lease_' + n) for d, w, n in responses]
    declarations = [f"    {d} {'reg' if d=='output' and (n.startswith('rsp_') or n.startswith('lease_rsp_')) else 'wire'} {w} {n}"
                    for d, w, n in public + extra]
    lines = ['`timescale 1ns/1ps', '`default_nettype none',
        '// One response-engine lease, not a fixed limit on live RPC records.',
        '// Cache a real LOAD and release the backend while preserving record authority.',
        '// Status 11 is a local lease/pool conflict; no backend memory command is issued.',
        'module grpc_leased_stream_store #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23', ')(', ',\n'.join(declarations), ');',
        'localparam IDLE=0,CHECK_GUARDS=1,DECIDE=2,SEND=3,WAIT_RESULT=4;',
        'reg [2:0] state;reg pending_lease,prefer_lease;reg [4:0] guards;',
        'reg [MEMORY_ADDR_WIDTH-1:0] held_pool_base;',
        'reg [MEMORY_ADDR_WIDTH:0] held_pool_bytes;',
        'wire backend_ready,backend_idle;']
    lines += [f'reg {w} pending_{n};' for _, w, n in command]
    lines += [f'wire {w} backend_{n};' for _, w, n in responses]
    lines += [
        'wire control_candidate=req_valid&&!rsp_valid;',
        'wire lease_candidate=lease_valid&&!lease_rsp_valid;',
        'assign req_ready=!rst&&state==IDLE&&!rsp_valid&&(!lease_candidate||!prefer_lease);',
        'assign lease_ready=!rst&&state==IDLE&&!lease_rsp_valid&&(!control_candidate||prefer_lease);',
        'wire control_accept=req_valid&&req_ready,lease_accept=lease_valid&&lease_ready;',
        'assign lease_active=lease_rsp_valid&&lease_rsp_status==0;',
        'assign idle=state==IDLE&&backend_idle&&!rsp_valid&&!lease_rsp_valid&&!req_valid&&!lease_valid;',
        'wire [63:0] pending_record_end={1\'b0,pending_req_address}+64\'d128;',
        'wire [63:0] held_record_end={1\'b0,lease_rsp_address}+64\'d128;',
        'wire [63:0] pending_pool_end={1\'b0,pending_cfg_pool_base}+{1\'b0,pending_cfg_pool_bytes};',
        'wire record_overlaps={1\'b0,pending_req_address}<held_record_end&&{1\'b0,lease_rsp_address}<pending_record_end;',
        'wire pool_overlaps={1\'b0,pending_cfg_pool_base}<held_record_end&&{1\'b0,lease_rsp_address}<pending_pool_end;',
        'wire same_pool=pending_cfg_pool_base==held_pool_base&&pending_cfg_pool_bytes==held_pool_bytes;',
        'wire same_binding=pending_req_address==lease_rsp_address&&pending_req_user==lease_rsp_user&&',
        '    pending_req_stream==lease_rsp_stream&&pending_req_generation==lease_rsp_generation;',
        'reg [7:0] conflict;',
        'always @*begin',
        '    conflict=0;',
        '    if(guards[0])begin',
        '        if(pending_req_op==3&&guards[1])conflict=1;',
        '        else if(pending_req_op==4&&guards[2])conflict=2;',
        '        else if(pending_req_op==5&&guards[1])conflict=3;',
        '        else if(pending_req_op==2&&guards[1]&&!(guards[3]&&guards[4]))conflict=4;',
        '        else if(pending_req_op==0&&guards[2]&&!guards[3])conflict=5;',
        '        else if(pending_req_op<=6&&!guards[3])conflict=6;',
        '    end', 'end']
    connections = {n: n for _, _, n in public}
    connections.update(req_valid='state==SEND', req_ready='backend_ready', rsp_ready='!rst&&state==WAIT_RESULT', idle='backend_idle')
    connections.update({n: 'pending_' + n for _, _, n in command})
    connections.update({n: 'backend_' + n for _, _, n in responses})
    lines.append(named_instance('grpc_stream_store', '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', 'store', connections))
    lines += ['always @(posedge clk)begin', '    if(rst)begin',
              '        state<=IDLE;pending_lease<=0;prefer_lease<=0;guards<=0;held_pool_base<=0;held_pool_bytes<=0;']
    lines += ['        pending_' + n + '<=0;' for _, _, n in command]
    lines += ['        ' + n + '<=0;lease_' + n + '<=0;' for _, _, n in responses]
    lines += ['    end else begin', '        if(rsp_valid&&rsp_ready)rsp_valid<=0;',
        '        if(lease_rsp_valid&&lease_rsp_ready)lease_rsp_valid<=0;', '        case(state)',
        '            IDLE:if(control_accept||lease_accept)begin',
        '                pending_lease<=lease_accept;prefer_lease<=control_accept;']
    lease_values = dict(req_op="3'd1", req_user='lease_user', req_stream='lease_stream',
                        cfg_pool_base='lease_pool_base', cfg_pool_bytes='lease_pool_bytes')
    for _, _, name in command:
        lines.append(f"                pending_{name}<=lease_accept?{lease_values.get(name, '0')}:{name};")
    lines += ['                state<=lease_accept?SEND:CHECK_GUARDS;', '            end',
        '            CHECK_GUARDS:begin',
        '                guards<={same_binding,same_pool,pool_overlaps,record_overlaps,lease_active};state<=DECIDE;',
        '            end', '            DECIDE:if(conflict!=0)begin']
    echoes = dict(rsp_valid="1'b1", rsp_status="8'd11", rsp_detail='conflict', rsp_op='pending_req_op',
                  rsp_address='pending_req_address', rsp_user='pending_req_user', rsp_stream='pending_req_stream')
    lines += [f"                {n}<={echoes.get(n, '0')};" for _, _, n in responses]
    lines += ['                state<=IDLE;', '            end else state<=SEND;',
        '            SEND:if(backend_ready)state<=WAIT_RESULT;',
        '            WAIT_RESULT:if(backend_rsp_valid)begin', '                if(pending_lease)begin']
    lines += [f'                    lease_{n}<=backend_{n};' for _, _, n in responses]
    lines += ['                    held_pool_base<=pending_cfg_pool_base;held_pool_bytes<=pending_cfg_pool_bytes;',
        '                end else begin']
    lines += [f'                    {n}<=backend_{n};' for _, _, n in responses]
    lines += ['                end', '                state<=IDLE;', '            end',
        '            default:state<=IDLE;', '        endcase', '    end', 'end', 'endmodule', '`default_nettype wire', '']
    target = source_path(root, 'rtl/grpc_leased_stream_store.v')
    target.write_text('\n'.join(lines))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (root / 'build/validation/leased-stream-store-generation.json').write_text(json.dumps(dict(
        phase='generated_cached_directory_lease', inputs_sha256={source_relative(p, root).as_posix(): sha(p) for p in (base, Path(__file__))},
        generated_sha256=sha(target), cached_response_leases=1, live_rpc_records='runtime external pool',
        whole_rpc_gpu_image_leases_verified=False, full_system_complete=False), indent=2) + '\n')
    print('Generated cached directory lease with independent control results and physical record/pool fences')


if __name__ == '__main__':
    main()
