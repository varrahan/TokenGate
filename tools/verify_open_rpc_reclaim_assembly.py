"""Qualify the exact private reclamation wiring, without claiming a runtime fix."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/experiments/open-rpc-reclaim'
    generation = read(folder / 'generation.json')
    parent = read(root / 'build/validation/frame-owned-quiet-corpus.json')
    component = read(root / 'build/validation/payload-reclaimer-units.json')
    assert generation['parent_corpus_audit_key'] == parent['key'] == 'b89b9aea0dd403cb'
    assert generation['component_audit_key'] == component['key'] == 'f16cf89cd799c1fb'
    assert sha(folder / 'generate_open_rpc_reclaim.py') == generation['generator_sha256']
    expected_changes = {'grpc_message_deframer', 'grpc_stream_store', 'grpc_shared_directory_parser',
        'grpc_shared_directory_prefill', 'http2_classified_parser_transport', 'http2_enveloped_parser_core'}
    assert set(generation['changed_existing_modules']) == set(generation['source_edit_certificate']) == expected_changes
    for name, digest in generation['outputs_sha256'].items():
        assert sha(folder / name) == digest, name
    for name, digest in parent['executed_parser_sha256'].items():
        path = folder / 'rtl' / (name + '.v')
        if name not in expected_changes:
            assert sha(path) == digest
            continue
        text = path.read_bytes().decode().replace('\r\n', '\n')
        for edit in reversed(generation['source_edit_certificate'][name]):
            assert text.count(edit['new']) == 1
            text = text.replace(edit['new'], edit['old'])
        raw = text.replace('\n', generation['original_newlines'][name]).encode()
        assert hashlib.sha256(raw).hexdigest() == digest, name
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', folder).items()}
    assert len(parser) == 77 and set(parser) - set(parent['executed_parser_sha256']) == {'grpc_payload_reclaimer'}
    assert parser['grpc_payload_reclaimer'] == component['actual_reclaimer_rtl_sha256']
    assert parser['memory_command_slot'] == component['actual_memory_slot_sha256']
    before = root / 'build/experiments/frame-owned-quiet/rtl/http2_enveloped_parser_core.v'
    core = folder / 'rtl/http2_enveloped_parser_core.v'
    assert ports(core.read_text(), 'http2_enveloped_parser_core') == ports(before.read_text(), 'http2_enveloped_parser_core')
    source = core.read_text()
    for guard in (
        'wire rc_ack=completion_valid&&completion_ready&&completion_status==0&&reclaim_candidate;',
        'wire rc_fence=rc_pending||rc_busy||rc_ack;',
        'wire allow_new_rx=!rc_fence&&', 'wire allow_config=!rc_fence&&',
        'wire reverse_new_admit=!rc_fence&&',
        'assign rc_start=rc_pending&&!rc_busy&&queued_count==0&&pending_count==0&&!retirement_pending&&',
        '!payload_lease_active&&!completion_valid&&f_idle&&!rx_active&&!rx_granted&&',
        'receive_controller_idle&&receive_pool_gate_idle&&rc_backend_idle&&',
        '.req_authority(rc_credit_owner?rc_lock_active:rx_backend_authority)',
        '.req_keyed(rc_credit_owner?1\'b0:rx_request_keyed)',
        '.m_lock_valid(receive_pool_lock_valid)', '.m_active(receive_pool_active)',
        '.lock_active(rc_lock_active)', '.recovery_required(rc_recovery)',
        'assign receive_recovery_required=rc_backend_recovery||rc_recovery;',
        'assign mem_valid[26]=rc_memory_owner?rc_mem_valid:rc_rx_mem_valid;'):
        assert source.count(guard) == 1, guard
    assert '.a_active(rc_gate_active)' in source and '.b_active(rc_lock_active)' in source
    assert 'assign s_axis_generated_tready=reverse_input_ready&&reverse_admit;' in source
    assert 'wire reverse_admit=generated_offered||' in source
    assert 'assign f_s_axis_rx_tvalid=s_axis_rx_tvalid&&(rx_active||rx_granted);' in source
    # The flag originates in the real validated descriptor's saved directory
    # state, then travels only outward through production hierarchy.
    parsed = (folder / 'rtl/grpc_shared_directory_parser.v').read_text()
    assert 'descriptor_remote_ended<=engine_control_result_state[163];' in parsed
    assert 'assign payload_reclaimable=state==RESULT&&!descriptor_remote_ended&&status==0;' in parsed
    for module in ('grpc_shared_directory_prefill', 'http2_classified_parser_transport'):
        assert '.payload_reclaimable(payload_reclaimable)' in (folder / 'rtl' / (module + '.v')).read_text()
    assert '.payload_reclaimable(reclaim_candidate)' in source
    decoder = (folder / 'rtl/grpc_message_deframer.v').read_text()
    store = (folder / 'rtl/grpc_stream_store.v').read_text()
    assert "{58'd0,reclaimed_count,ordinal_exhausted,ended,prefix_count,ordinal,payload_received,length_value,message_offset,used}" in decoder
    assert 'reclaimed_count<=cfg_state[197:165];' in decoder
    assert 'requested_state[197:165]==record_data[453:421]' in store
    result = dict(phase='open_rpc_reclaim_private_assembly_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), parent_corpus_audit_key=parent['key'],
        component_audit_key=component['key'], exact_parser_modules=77,
        source_edit_inverse_verified=True, exact_original_line_endings_restored=True,
        executed_parser_sha256=parser, hardware_dma_ack_hook_wiring_verified=True,
        actual_directory_pool_lock_wiring_verified=True, actual_receive_backend_wiring_verified=True,
        no_new_public_authority_inputs=True, public_core_ports_unchanged=True,
        actual_partial_body_movement_component_qualified=True,
        saved_reclaimed_ordinal_bits=[197, 165], ordinary_save_preserves_reclaimed_ordinal=True,
        existing_reserved_raw_and_gpu_offers_preserved=True,
        application_credit_fixed=False, full_application_runtime_verified=False,
        full_protocol_matrix_verified=False, native_vendor_runtime_verified=False,
        whole_system_retained_reset_verified=False, native_timing_verified=False, full_system_complete=False,
        generation_sha256=sha(folder / 'generation.json'), verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/open-rpc-reclaim-assembly-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    shutil.copy2(folder / 'generate_open_rpc_reclaim.py', evidence / 'generate_open_rpc_reclaim.py')
    for destination in (evidence / 'audit.json', root / 'build/validation/open-rpc-reclaim-assembly.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'application_credit_fixed')}))


if __name__ == '__main__':
    main()
