"""Integrate the qualified compactor behind actual DMA ACK and pool ownership."""
import hashlib
import json
from pathlib import Path
import shutil

from verify_two_fpga_application import closure


CORE_DECLARATIONS = '''
// Private payload reclamation; these are never host authority inputs.
wire reclaim_candidate,rc_start,rc_start_ready,rc_busy,rc_idle,rc_memory_owner,rc_credit_owner;
reg rc_pending;
wire rc_recovery,rc_result_valid;wire [7:0] rc_status,rc_detail,rc_memory_status;
wire [MEMORY_ADDR_WIDTH-1:0] rc_recovery_address;
wire rc_lock_valid,rc_lock_ready,rc_lock_result_valid,rc_lock_result_ready,rc_lock_active,rc_unlock_valid,rc_unlock_ready;
wire [7:0] rc_lock_status;wire [MEMORY_ADDR_WIDTH-1:0] rc_lock_base;wire [MEMORY_ADDR_WIDTH:0] rc_lock_bytes;
wire rc_gate_lock_valid,rc_gate_lock_ready,rc_gate_result_valid,rc_gate_result_ready,rc_gate_active,rc_gate_unlock_valid,rc_gate_unlock_ready;
wire [7:0] rc_gate_status;wire [MEMORY_ADDR_WIDTH-1:0] rc_gate_base;wire [MEMORY_ADDR_WIDTH:0] rc_gate_bytes;
wire rc_lock_arbiter_idle;
wire rc_credit_valid,rc_credit_ready,rc_credit_result_ready;
wire [3:0] rc_credit_op;wire [USER_WIDTH-1:0] rc_credit_user;wire [30:0] rc_credit_stream;
wire [31:0] rc_credit_generation,rc_credit_amount;wire [MEMORY_ADDR_WIDTH-1:0] rc_credit_address;
wire rc_backend_ready,rc_backend_result_valid,rc_backend_idle,rc_backend_recovery;
wire rc_flow_fault_valid;wire [7:0] rc_flow_fault_status,rc_flow_fault_detail,rc_flow_fault_memory_status;
wire [31:0] rc_flow_fault_http2_error;
wire rc_mem_valid,rc_mem_ready,rc_mem_write,rc_mem_rsp_valid,rc_mem_rsp_ready;
wire [MEMORY_ADDR_WIDTH-1:0] rc_mem_addr;wire [3:0] rc_mem_bytes;wire [71:0] rc_mem_data,rc_mem_rsp_data;wire [7:0] rc_mem_rsp_status;
wire rc_rx_mem_valid,rc_rx_mem_ready,rc_rx_mem_write,rc_rx_mem_rsp_valid,rc_rx_mem_rsp_ready;
wire [MEMORY_ADDR_WIDTH-1:0] rc_rx_mem_addr;wire [3:0] rc_rx_mem_bytes;wire [71:0] rc_rx_mem_data,rc_rx_mem_rsp_data;wire [7:0] rc_rx_mem_rsp_status;
reg [MEMORY_ADDR_WIDTH-1:0] rc_live_payload_base,rc_live_floor;
reg [MEMORY_ADDR_WIDTH:0] rc_live_payload_bytes,rc_live_slot_bytes;
reg [MEMORY_ADDR_WIDTH-1:0] rc_pool_base,rc_payload_base,rc_floor,rc_context_base,rc_receive_connection_base,rc_receive_stream_base;
reg [MEMORY_ADDR_WIDTH:0] rc_pool_bytes,rc_payload_bytes,rc_slot_bytes,rc_context_bytes,rc_receive_connection_bytes,rc_receive_stream_bytes;
wire rc_ack=completion_valid&&completion_ready&&completion_status==0&&reclaim_candidate;
wire rc_fence=rc_pending||rc_busy||rc_ack;
'''


CORE_BODY = '''
// Existing offers already reserved by rx_granted/generated_offered retain
// their original promise. Only new admission/configuration is fenced.
always @(posedge clk)begin
    if(rst)begin
        rc_pending<=0;rc_live_payload_base<=0;rc_live_payload_bytes<=0;rc_live_slot_bytes<=0;rc_live_floor<=0;
        rc_pool_base<=0;rc_pool_bytes<=0;rc_payload_base<=0;rc_payload_bytes<=0;rc_slot_bytes<=0;rc_floor<=0;
        rc_context_base<=0;rc_context_bytes<=0;rc_receive_connection_base<=0;rc_receive_connection_bytes<=0;
        rc_receive_stream_base<=0;rc_receive_stream_bytes<=0;
    end else begin
        if(s_axis_rx_tvalid&&s_axis_rx_tready&&!rx_active)begin
            rc_live_payload_base<=cfg_payload_base;rc_live_payload_bytes<=cfg_payload_bytes;
            rc_live_slot_bytes<=cfg_payload_slot_bytes;rc_live_floor<=cfg_work_floor;
        end
        if(rc_ack)begin
            rc_pending<=1;
            if(!rc_pending&&!rc_busy)begin
                rc_pool_base<=owned_stream_base;rc_pool_bytes<=owned_stream_bytes;
                rc_payload_base<=rc_live_payload_base;rc_payload_bytes<=rc_live_payload_bytes;
                rc_slot_bytes<=rc_live_slot_bytes;rc_floor<=rc_live_floor;
                rc_context_base<=active_context_base;rc_context_bytes<=active_context_bytes;
                rc_receive_connection_base<=owned_cfg_receive_connection_base;
                rc_receive_connection_bytes<=owned_cfg_receive_connection_bytes;
                rc_receive_stream_base<=owned_cfg_receive_stream_base;
                rc_receive_stream_bytes<=owned_cfg_receive_stream_bytes;
            end
        end
        if(rc_start&&rc_start_ready)rc_pending<=0;
    end
end
assign rc_start=rc_pending&&!rc_busy&&queued_count==0&&pending_count==0&&!retirement_pending&&
    !payload_lease_active&&!completion_valid&&f_idle&&!rx_active&&!rx_granted&&
    receive_controller_idle&&receive_pool_gate_idle&&rc_backend_idle&&
    !shutdown_busy&&!cancel_valid&&!receive_fault_valid&&!receive_recovery_required&&
    !journal_recovery_required&&!response_recovery_required;
directory_pool_lock_arbiter #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) reclaim_pool_arbiter(
    .clk(clk),.rst(rst),
    .a_lock_valid(rc_gate_lock_valid),.a_lock_ready(rc_gate_lock_ready),.a_lock_base(rc_gate_base),.a_lock_bytes(rc_gate_bytes),
    .a_result_valid(rc_gate_result_valid),.a_result_ready(rc_gate_result_ready),.a_status(rc_gate_status),
    .a_active(rc_gate_active),.a_unlock_valid(rc_gate_unlock_valid),.a_unlock_ready(rc_gate_unlock_ready),
    .b_lock_valid(rc_lock_valid),.b_lock_ready(rc_lock_ready),.b_lock_base(rc_lock_base),.b_lock_bytes(rc_lock_bytes),
    .b_result_valid(rc_lock_result_valid),.b_result_ready(rc_lock_result_ready),.b_status(rc_lock_status),
    .b_active(rc_lock_active),.b_unlock_valid(rc_unlock_valid),.b_unlock_ready(rc_unlock_ready),
    .m_lock_valid(receive_pool_lock_valid),.m_lock_ready(receive_pool_lock_ready),
    .m_lock_base(receive_pool_lock_base),.m_lock_bytes(receive_pool_lock_bytes),
    .m_result_valid(receive_pool_result_valid),.m_result_ready(receive_pool_result_ready),.m_status(receive_pool_status),
    .m_active(receive_pool_active),.m_unlock_valid(receive_pool_unlock_valid),.m_unlock_ready(receive_pool_unlock_ready),
    .idle(rc_lock_arbiter_idle));
grpc_payload_reclaimer #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) payload_reclaimer(
    .clk(clk),.rst(rst),.start_valid(rc_start),.start_ready(rc_start_ready),
    .cfg_pool_base(rc_pool_base),.cfg_pool_bytes(rc_pool_bytes),.cfg_payload_base(rc_payload_base),
    .cfg_payload_bytes(rc_payload_bytes),.cfg_slot_bytes(rc_slot_bytes),.cfg_work_floor(rc_floor),
    .lock_valid(rc_lock_valid),.lock_ready(rc_lock_ready),.lock_base(rc_lock_base),.lock_bytes(rc_lock_bytes),
    .lock_result_valid(rc_lock_result_valid),.lock_result_ready(rc_lock_result_ready),.lock_status(rc_lock_status),
    .lock_active(rc_lock_active),.unlock_valid(rc_unlock_valid),.unlock_ready(rc_unlock_ready),
    .credit_valid(rc_credit_valid),.credit_ready(rc_credit_ready),.credit_op(rc_credit_op),
    .credit_user(rc_credit_user),.credit_stream(rc_credit_stream),.credit_generation(rc_credit_generation),
    .credit_address(rc_credit_address),.credit_amount(rc_credit_amount),
    .credit_result_valid(rc_backend_result_valid&&rc_credit_owner),.credit_result_ready(rc_credit_result_ready),
    .credit_status(rx_backend_status),.credit_detail(rx_backend_detail),.credit_memory_status(rx_backend_memory_status),
    .memory_owner(rc_memory_owner),.credit_owner(rc_credit_owner),
    .mem_valid(rc_mem_valid),.mem_ready(rc_mem_ready),.mem_write(rc_mem_write),.mem_addr(rc_mem_addr),
    .mem_bytes(rc_mem_bytes),.mem_data(rc_mem_data),.mem_rsp_valid(rc_mem_rsp_valid),.mem_rsp_ready(rc_mem_rsp_ready),
    .mem_rsp_data(rc_mem_rsp_data),.mem_rsp_status(rc_mem_rsp_status),
    .result_valid(rc_result_valid),.result_ready(1'b1),.result_status(rc_status),.result_detail(rc_detail),
    .result_memory_status(rc_memory_status),.recovery_required(rc_recovery),.recovery_address(rc_recovery_address),
    .busy(rc_busy),.idle(rc_idle));
assign rx_backend_ready=!rc_credit_owner&&rc_backend_ready;
assign rc_credit_ready=rc_credit_owner&&rc_backend_ready;
assign rx_backend_result_valid=!rc_credit_owner&&rc_backend_result_valid;
// The memory slot is shared only at its idle boundary; the receive backend
// is idle at start and direct memory is drained before credit_owner asserts.
assign mem_valid[26]=rc_memory_owner?rc_mem_valid:rc_rx_mem_valid;
assign mem_write[26]=rc_memory_owner?rc_mem_write:rc_rx_mem_write;
assign mem_addr[26*MEMORY_ADDR_WIDTH+:MEMORY_ADDR_WIDTH]=rc_memory_owner?rc_mem_addr:rc_rx_mem_addr;
assign mem_bytes[26*4+:4]=rc_memory_owner?rc_mem_bytes:rc_rx_mem_bytes;
assign mem_data[26*72+:72]=rc_memory_owner?rc_mem_data:rc_rx_mem_data;
assign mem_rsp_ready[26]=rc_memory_owner?rc_mem_rsp_ready:rc_rx_mem_rsp_ready;
assign rc_mem_ready=rc_memory_owner&&mem_ready[26];assign rc_rx_mem_ready=!rc_memory_owner&&mem_ready[26];
assign rc_mem_rsp_valid=rc_memory_owner&&mem_rsp_valid[26];assign rc_rx_mem_rsp_valid=!rc_memory_owner&&mem_rsp_valid[26];
assign rc_mem_rsp_data=mem_rsp_data[26*72+:72];assign rc_rx_mem_rsp_data=mem_rsp_data[26*72+:72];
assign rc_mem_rsp_status=mem_rsp_status[26*8+:8];assign rc_rx_mem_rsp_status=mem_rsp_status[26*8+:8];
assign receive_recovery_required=rc_backend_recovery||rc_recovery;
assign receive_fault_valid=rc_flow_fault_valid||rc_recovery;
assign receive_fault_status=rc_recovery?rc_status:rc_flow_fault_status;
assign receive_fault_detail=rc_recovery?rc_detail:rc_flow_fault_detail;
assign receive_fault_memory_status=rc_recovery?rc_memory_status:rc_flow_fault_memory_status;
assign receive_fault_http2_error=rc_recovery?32'd2:rc_flow_fault_http2_error;
'''


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    parent = read(root / 'build/validation/frame-owned-quiet-corpus.json')
    unit = read(root / 'build/validation/payload-reclaimer-units.json')
    assert parent['key'] == 'b89b9aea0dd403cb' and unit['key'] == 'f16cf89cd799c1fb'
    assert sha(root / 'rtl/grpc_payload_reclaimer.v') == unit['actual_reclaimer_rtl_sha256']
    folder = root / 'build/experiments/open-rpc-reclaim'
    folder.mkdir(parents=True, exist_ok=False)
    texts, originals, newlines, certificates = {}, {}, {}, {}
    for module, digest in parent['executed_parser_sha256'].items():
        path = root / 'build/experiments/frame-owned-quiet/rtl' / (module + '.v')
        assert sha(path) == digest
        raw = path.read_bytes()
        originals[module] = raw
        newlines[module] = '\r\n' if b'\r\n' in raw else '\n'
        texts[module] = raw.decode().replace('\r\n', '\n')
        certificates[module] = []
    def change(module, old, new):
        assert texts[module].count(old) == 1, (module, old, texts[module].count(old))
        texts[module] = texts[module].replace(old, new)
        certificates[module].append(dict(old=old, new=new))
    def insert(module, addition):
        end = texts[module].index(');') + 2
        before = texts[module][:end]
        change(module, before, before + addition)
    def port(module):
        end = texts[module].index(');')
        before = texts[module][:end]
        change(module, before, before + ',\n    output wire payload_reclaimable\n')
    def append(module, addition):
        change(module, 'endmodule\n`default_nettype wire', addition + '\nendmodule\n`default_nettype wire')
    module = 'grpc_message_deframer'
    change(module, 'reg [2:0] prefix_count;', 'reg [2:0] prefix_count;\n    reg [32:0] reclaimed_count;')
    change(module, "{64'd0,27'd0,ordinal_exhausted,ended,prefix_count,ordinal,payload_received,length_value,message_offset,used}",
        "{58'd0,reclaimed_count,ordinal_exhausted,ended,prefix_count,ordinal,payload_received,length_value,message_offset,used}")
    change(module, 'prefix_count<=0;ended<=0;', 'prefix_count<=0;reclaimed_count<=0;ended<=0;')
    change(module, 'bad_reserved<=cfg_state[255:165]!=0;',
        "reclaimed_count<=cfg_state[197:165];\n                bad_reserved<=cfg_state[255:198]!=0||cfg_state[197:165]>({1'b0,cfg_state[159:128]}+cfg_state[164]);")
    module = 'grpc_stream_store'
    change(module, 'sensible_state=value[255:165]==0&&',
        "sensible_state=value[255:198]==0&&value[197:165]<=({1'b0,value[159:128]}+value[164])&&")
    change(module, 'record_checks[0]<=sensible_state(requested_state,record_data[191:160],record_data[223:192]);',
        'record_checks[0]<=sensible_state(requested_state,record_data[191:160],record_data[223:192])&&requested_state[197:165]==record_data[453:421];')
    module = 'grpc_shared_directory_parser'
    port(module)
    insert(module, '\n    reg descriptor_remote_ended;\n')
    change(module, 'lookup_status<=0;lookup_memory<=0;', 'descriptor_remote_ended<=1;lookup_status<=0;lookup_memory<=0;')
    change(module, 'lookup_status<=engine_control_status;', 'descriptor_remote_ended<=engine_control_result_state[163];lookup_status<=engine_control_status;')
    append(module, '\n    assign payload_reclaimable=state==RESULT&&!descriptor_remote_ended&&status==0;\n')
    for module, old in (('grpc_shared_directory_prefill', '.payload_lease_active(payload_lease_active),'),
                        ('http2_classified_parser_transport', '.payload_lease_active(p_payload_lease_active),')):
        port(module)
        change(module, old, old + '\n    .payload_reclaimable(payload_reclaimable),')
    module = 'http2_enveloped_parser_core'
    insert(module, CORE_DECLARATIONS)
    change(module, '.payload_lease_active(payload_lease_active),',
        '.payload_lease_active(payload_lease_active),\n    .payload_reclaimable(reclaim_candidate),')
    for prefix in ('wire allow_new_rx=', 'wire allow_config=', 'wire reverse_new_admit='):
        change(module, prefix, prefix + '!rc_fence&&')
    change(module, 'assign idle=local_abort_idle&&', 'assign idle=!rc_fence&&rc_idle&&rc_lock_arbiter_idle&&local_abort_idle&&')
    # Change only the existing backend instance, retaining all ordinary routes.
    text = texts[module]
    start = text.index('http2_keyed_receive_credit_store #')
    end = text.index('\n);', start) + 3
    original_backend = text[start:end]
    backend = original_backend
    replacements = {'req_valid': 'rc_credit_owner?rc_credit_valid:rx_backend_valid',
        'req_ready': 'rc_backend_ready', 'req_op': 'rc_credit_owner?rc_credit_op:rx_request_op',
        'req_authority': 'rc_credit_owner?rc_lock_active:rx_backend_authority',
        'req_maintenance': "rc_credit_owner?1'b0:rx_request_maintenance",
        'req_user': 'rc_credit_owner?rc_credit_user:rx_request_user',
        'req_stream': 'rc_credit_owner?rc_credit_stream:rx_request_stream',
        'req_generation': 'rc_credit_owner?rc_credit_generation:rx_request_generation',
        'req_record_address': 'rc_credit_owner?rc_credit_address:rx_request_address',
        'req_amount': 'rc_credit_owner?rc_credit_amount:rx_request_amount',
        'rsp_valid': 'rc_backend_result_valid',
        'rsp_ready': 'rc_credit_owner?rc_credit_result_ready:rx_backend_result_ready',
        'recovery_required': 'rc_backend_recovery', 'idle': 'rc_backend_idle',
        'req_keyed': "rc_credit_owner?1'b0:rx_request_keyed"}
    import re
    configs = {'context_base': 'rc_context_base', 'context_bytes': 'rc_context_bytes',
        'rpc_base': 'rc_pool_base', 'rpc_bytes': 'rc_pool_bytes', 'work_floor': 'rc_floor',
        'receive_connection_base': 'rc_receive_connection_base', 'receive_connection_bytes': 'rc_receive_connection_bytes',
        'receive_stream_base': 'rc_receive_stream_base', 'receive_stream_bytes': 'rc_receive_stream_bytes'}
    for name, value in configs.items():
        match = re.search(r'\.' + 'cfg_' + name + r'\(([^\n]*)\),', backend)
        assert match
        replacements['cfg_' + name] = 'rc_credit_owner?' + value + ':' + match[1]
    for name in ('valid', 'ready', 'write', 'addr', 'bytes', 'data', 'rsp_valid', 'rsp_ready', 'rsp_data', 'rsp_status'):
        replacements['mem_' + name] = 'rc_rx_mem_' + name
    for name, value in replacements.items():
        pattern = r'\.' + name + r'\(([^\n]*)\)'
        assert len(re.findall(pattern, backend)) == 1, name
        backend = re.sub(pattern, lambda m: '.' + name + '(' + value + ')', backend)
    change(module, original_backend, backend)
    # Give the existing receive requester one input of a real two-owner lock
    # arbiter; the reclaimer uses the other. No synthetic lock response exists.
    start = texts[module].index('http2_receive_pool_gate #')
    end = texts[module].index('\n);', start) + 3
    old_gate = texts[module][start:end]
    gate = old_gate
    for name, signal in dict(lock_valid='rc_gate_lock_valid', lock_ready='rc_gate_lock_ready', lock_base='rc_gate_base',
        lock_bytes='rc_gate_bytes', lock_result_valid='rc_gate_result_valid', lock_result_ready='rc_gate_result_ready',
        lock_status='rc_gate_status', lock_active='rc_gate_active', unlock_valid='rc_gate_unlock_valid', unlock_ready='rc_gate_unlock_ready').items():
        gate, count = re.subn(r'\.' + name + r'\([^\n]*\)', '.' + name + '(' + signal + ')', gate)
        assert count == 1
    change(module, old_gate, gate)
    for name in ('valid', 'status', 'detail', 'memory_status', 'http2_error'):
        change(module, '.fault_' + name + '(receive_fault_' + name + ')', '.fault_' + name + '(rc_flow_fault_' + name + ')')
    append(module, CORE_BODY)
    output = folder / 'rtl'
    output.mkdir()
    changed = []
    for module, text in texts.items():
        restored = text
        for edit in reversed(certificates[module]):
            assert restored.count(edit['new']) == 1
            restored = restored.replace(edit['new'], edit['old'])
        assert restored.replace('\n', newlines[module]).encode() == originals[module], module
        raw = text.replace('\n', newlines[module]).encode()
        (output / (module + '.v')).write_bytes(raw)
        if raw != originals[module]:
            changed.append(module)
    shutil.copy2(root / 'rtl/grpc_payload_reclaimer.v', output / 'grpc_payload_reclaimer.v')
    modules = closure('http2_enveloped_parser_application', folder)
    assert len(modules) == 77
    result = dict(phase='open_rpc_reclaim_integration_generated', parent_corpus_audit_key=parent['key'],
        component_audit_key=unit['key'], exact_parser_modules=77, changed_existing_modules=sorted(changed),
        added_module='grpc_payload_reclaimer', source_edit_certificate={n: e for n, e in certificates.items() if e},
        original_newlines={n: newlines[n] for n in changed},
        unchanged_public_memory_interface=True, saved_reclaimed_count_bits=[197, 165],
        requires_actual_successful_dma_completion_ack=True, requires_all_descriptor_retirement_and_no_payload_lease=True,
        shared_actual_pool_lock=True, actual_receive_credit_backend=True,
        outputs_sha256={'rtl/' + p.name: sha(p) for p in output.glob('*.v')},
        generator_sha256=sha(Path(__file__)), application_credit_fixed=False,
        full_protocol_verified=False, native_timing_verified=False, full_system_complete=False)
    (folder / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    print(json.dumps({k: result[k] for k in ('phase', 'exact_parser_modules', 'changed_existing_modules')}))


if __name__ == '__main__':
    main()
