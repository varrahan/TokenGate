"""Bind extended protocol results to original fixtures and one bootstrap edit.

This does not label the modified fixtures unchanged. The inverse edit must
reconstruct the original bytes, including every assertion and traffic vector.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import WindowUpdateFrame
import tiktoken

from verify_two_fpga_application import closure


PROFILES = dict(receive_flow='receive-flow', receive_errors='receive-errors',
    duplex='duplex', duplex_faults='duplex-faults', return_faults='return-faults')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='+', required=True, choices=tuple(PROFILES))
    ap.add_argument('--candidate',choices=('frame-event-buffer','frame-owned-quiet','payload-event-buffer','open-rpc-reclaim','rpc-completion-flags','rpc-success-predicate-v2','receive-capacity-v4'),default='frame-event-buffer')
    ap.add_argument('--capacity-fault-link-pause',action='store_true')
    args = ap.parse_args()
    success=args.candidate=='rpc-success-predicate-v2'
    capacity=args.candidate=='receive-capacity-v4'
    if args.capacity_fault_link_pause:assert capacity and 'duplex_faults' in args.cases
    flags=args.candidate=='rpc-completion-flags' or success;payload=args.candidate=='payload-event-buffer' or flags;reclaim=args.candidate=='open-rpc-reclaim' or capacity
    quiet=args.candidate in ('frame-owned-quiet','open-rpc-reclaim') or payload or capacity
    assert len(set(args.cases)) == len(args.cases)
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    parent = read(root/'build/validation/json-simd-corpus.json')
    units = read(root/'build/validation'/('receive-capacity-v4-assembly.json' if capacity else 'rpc-success-predicate.json' if success else 'rpc-completion-flags.json' if flags else 'open-rpc-reclaim-assembly.json' if reclaim else 'payload-event-buffer-units.json' if payload else 'frame-owned-quiet-formal.json' if quiet else 'frame-event-buffer-units.json'))
    if flags:assert units['full_production_response_subtree_induction_verified'] and units['actual_initial_reset_base_verified']
    generation=read(root/'build/experiments'/args.candidate/'generation.json')
    if reclaim:assert units['key']==('69a29b3c155b339f' if capacity else 'ad1b6bc9beebcaf5') and units['source_edit_inverse_verified']
    if capacity:
        driver=root/'tools/run_frame_event_buffer_protocol_wsl.py'
        module=ast.parse(driver.read_text())
        helpers={}
        for helper in ('capacity_extended_barrier_edits','capacity_fault_link_top_edits','capacity_fault_link_fixture_edits'):
            node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==helper)
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(driver),'exec'),helpers)
    assert parent['key'] == '2509134d2630b47e'
    original = root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    # Both implementations reject the same stale bootstrap before any packet
    # is offered. Preserve that counterexample instead of relabeling it passed.
    bootstrap_failures = {}
    failed_inputs = {}
    for name in ('frame_event_buffer_duplex_20261122', 'frame_event_before_duplex_20261122'):
        archive = root/'build/wsl-reports'/('raw_envelope_'+name)
        inputs = read(archive/'inputs.json')
        assert read(archive/'snapshot.json')['exit_code'] == 1
        assert read(archive/'report.json')['phase'] == 'failed'
        for path, digest in inputs.items():
            assert sha(archive/'execution-sources'/path) == digest, (name, path)
        xml = ET.parse(archive/'results.xml')
        failures = xml.findall('.//failure')
        assert len(failures) == 1 and "('directory', 4, 2)" in failures[0].text
        stops = xml.findall(".//property[@name='sim_time_stop']")
        assert len(stops) == 1 and float(stops[0].attrib['value']) == 1138.0
        failed_inputs[name] = inputs
        bootstrap_failures[name] = dict(phase='failed', format_operation=4, status=2,
            failure_time_ns=1138, xml_sha256=sha(archive/'results.xml'),
            report_sha256=sha(archive/'report.json'), inputs_sha256=inputs)
    before = failed_inputs['frame_event_before_duplex_20261122']
    after = failed_inputs['frame_event_buffer_duplex_20261122']
    assert before == parent['inputs_sha256']
    assert before.keys() == after.keys()
    assert [n for n in before if before[n] != after[n]] == ['rtl/http2_axis_ingress.v']
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root/'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    references = read(original/'build/bidirectional-fixtures/reference_cases.json')
    prompt = bytes.fromhex(references['cases'][0]['prompt_utf8_hex']).decode()
    ids = encoding.encode(prompt)
    assert ids == references['cases'][0]['token_ids'] == [15339, 1917]
    expected_proto = bytearray()
    for token in ids:
        raw = encoding.decode_single_token_bytes(token)
        record_payload = b'\x8a\x01' + bytes([len(raw)]) + raw
        expected_proto.extend(b'\0' + len(record_payload).to_bytes(4, 'big') + record_payload)
    executions = {}
    artifacts = {Path(__file__)}
    for case in args.cases:
        link_pause=args.capacity_fault_link_pause and case=='duplex_faults'
        name = args.candidate.replace('-','_') + '_' + case + ('_init_credit_textlink_20261122' if link_pause else '_init_credit_20261122' if capacity else '_init_20261122')
        launch_path = root/'build/validation'/(name+'-launch.json')
        launch = read(launch_path)
        archive = root/'build/wsl-reports'/('raw_envelope_'+name)
        source = archive/'execution-sources'
        inputs = read(archive/'inputs.json')
        report = read(archive/'report.json')
        snapshot = read(archive/'snapshot.json')
        accepted = read(archive/'acceptance.json')
        assert launch['phase'] == 'completed' and launch['exit_code'] == 0
        assert snapshot['exit_code'] == 0 and snapshot['profile'] == report['profile'] == PROFILES[case]
        assert report['phase'] == accepted['phase'] == 'passed'
        assert report['tests'] == 1 and report['failures'] == 0
        assert inputs == launch['inputs_sha256'] == report['input_sha256']
        assert sha(archive/'acceptance.json') == report['acceptance_sha256']
        assert set(inputs) == set(parent['inputs_sha256'])|({'rtl/axis_pingpong_skid_buffer.v'} if payload else {'rtl/grpc_payload_reclaimer.v'} if reclaim else set())
        for path, digest in inputs.items():
            assert sha(source/path) == digest, (case, path)
        edit = launch['fixture_initialization_edit']
        assert launch['protocol_fixture_sources_unchanged'] is False
        assert launch['parser_variant'] == 'buffered'
        assert edit['old'] == 'await b.directory(4)'
        assert edit['new'] == 'b.response_configuration(0); await b.directory(4)'
        old = (original/edit['path']).read_bytes()
        new = (source/edit['path']).read_bytes()
        assert sha(original/edit['path']) == edit['old_sha256'] == parent['inputs_sha256'][edit['path']]
        if link_pause:
            e=launch['fixture_fault_link_edit'];top=launch['fixture_fault_link_top_edit']
            assert e['path']==edit['path'] and e['exact_inverse_verified']
            assert sha(source/e['path'])==e['new_sha256']
            initialized=old.decode().replace(edit['old'],edit['new'])
            settled,_=helpers['capacity_extended_barrier_edits'](initialized,case)
            expected,replacements=helpers['capacity_fault_link_fixture_edits'](settled)
            assert new.decode()==expected and e['replacements']==[list(r) for r in replacements]
            new=settled.encode();assert hashlib.sha256(new).hexdigest()==e['old_sha256']
            assert top['path']=='sim/cocotb_two_fpga_enveloped_top.sv' and top['exact_inverse_verified']
            prior=(original/top['path']).read_bytes().decode()
            expected,replacements=helpers['capacity_fault_link_top_edits'](prior)
            assert (source/top['path']).read_bytes().decode()==expected
            assert top['replacements']==[list(r) for r in replacements]
            assert top['old_sha256']==parent['inputs_sha256'][top['path']]
            assert top['new_sha256']==sha(source/top['path'])
        else:
            assert not launch.get('fixture_fault_link_edit') and not launch.get('fixture_fault_link_top_edit')
        if capacity:
            credit_edit=launch['fixture_extended_credit_edit']
            assert credit_edit['path']==edit['path'] and credit_edit['exact_inverse_verified']
            initialized=old.decode().replace(edit['old'],edit['new'])
            expected,replacements=helpers['capacity_extended_barrier_edits'](initialized,case)
            assert new.decode()==expected and credit_edit['replacements']==[list(r) for r in replacements]
            assert hashlib.sha256(initialized.encode()).hexdigest()==edit['new_sha256']==credit_edit['old_sha256']
            assert hashlib.sha256(new).hexdigest()==credit_edit['new_sha256']
            restored=new.decode()
            for prior,updated in reversed(replacements):
                assert restored.count(updated)==1;restored=restored.replace(updated,prior)
            assert restored==initialized
            new=restored.encode()
        else:
            assert sha(source/edit['path']) == edit['new_sha256']
        assert new.count(edit['new'].encode()) == 1
        assert new.replace(edit['new'].encode(), edit['old'].encode()) == old
        changed = {n for n in parent['inputs_sha256'] if inputs[n] != parent['inputs_sha256'][n]}
        assert changed == {'rtl/http2_axis_ingress.v', edit['path']}|({'sim/cocotb_two_fpga_enveloped_top.sv'} if link_pause else set())|({'rtl/http2_enveloped_frame_grants.v'} if quiet else set())|({'rtl/http2_payload_decoder.v'} if payload else set())|({'rtl/rpc_http2_response_partition.v'} if flags else set())|({'rtl/rpc_grpc_http2_parser_response.v'} if success else set())|({'rtl/'+n+'.v' for n in generation['changed_existing_modules']} if reclaim else set())
        parser = {n: sha(p) for n,p in closure('http2_enveloped_parser_application', source).items()}
        tokenizer = {n: sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem', source).items()}
        assert parser == units['executed_parser_sha256' if quiet else 'candidate_parser_sha256'] and len(parser) == (77 if payload or reclaim else 76)
        assert tokenizer == parent['executed_tokenizer_sha256'] and len(tokenizer) == 22
        assert sha(archive/'protocol-runner-used.py') == launch['driver_sha256']
        assert sha(archive/'frame-event-buffer-generation.json') == launch['generation_sha256']
        xml = ET.parse(archive/'results.xml')
        tests = xml.findall('.//testcase')
        assert len(tests) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        assert accepted['complete_model_prefix_immutable'] is True
        capacity_admissions=None
        if capacity:
            layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
            assert layout[14]==384 and layout[18]==131072
            capacity_admissions=read(archive/'capacity_extended_admission_wires.json')
            expected_streams={'receive_flow':[1],'receive_errors':[1],'duplex':[1,3],
                'duplex_faults':[1,3]*21,'return_faults':[1]*21}[case]
            assert [r['stream'] for r in capacity_admissions]==expected_streams
            for r in capacity_admissions:
                assert r['first']==(r['stream']==1)
                assert r['stream_credit']==layout[18]+5 and r['connection_credit']==3*(layout[18]+5)
                expected_pairs=[(r['stream'],layout[18]+5-65535)]+([(0,3*(layout[18]+5)-65535)] if r['first'] else [])
                expected_wire=[]
                for stream,amount in expected_pairs:
                    f=WindowUpdateFrame(stream);f.window_increment=amount;expected_wire.append(f.serialize().hex())
                assert r['actual_wire']==expected_wire
                assert r['wire_after']-r['wire_before']==len(expected_wire)
        if case == 'receive_flow':
            assert accepted['native_padding_payload_bytes'] == 65535
            assert accepted['actual_window_update_frames'] == (514 if capacity else 512)
            assert accepted['actual_dma_ids_returned'] == ids
            assert accepted['native_complete_grpc_calls'] == 1
        elif case == 'receive_errors':
            client = H2Connection(H2Configuration(client_side=True))
            client.initiate_connection()
            events = [event for raw in accepted['actual_wire_hex'] for event in client.receive_data(bytes.fromhex(raw))]
            assert len(events) == 1 and type(events[0]).__name__ == 'ConnectionTerminated'
            assert events[0].last_stream_id == 1 and int(events[0].error_code) == 1
            assert accepted['actual_goaway'] == [accepted['independent_native_goaway']] == [[1, 1]]
            assert accepted['actual_forward_dma_ids'] == 0
            assert accepted['actual_reopen_without_global_reset']
            assert accepted['actual_reopened_dma_ids_returned'] == ids
            assert bytes.fromhex(accepted['actual_reopened_native_response_hex']) == expected_proto
            assert accepted['actual_reopened_successful_close_refund']
            assert accepted['actual_connection_fatal_goaway_without_credit_refund']
        elif case == 'duplex':
            assert accepted['lookup_streams'] == [1, 3]
            assert accepted['raw_held_cycles'] > 0 and accepted['gpu_handshakes'] == 2
            assert accepted['actual_native_completed_grpc_calls'] == 2
            assert accepted['actual_native_ping_acks'] == 7
            assert accepted['byte_exact_rpc_responses_verified']
            assert accepted['pending_lookup_precedes_later_raw_packets']
        elif case == 'duplex_faults':
            assert accepted['context_write_ack_fault_cases'] == 21
            faults = accepted['actual_context_commit_write_faults']
            assert [f['fault_phase'] for f in faults] == list(range(21))
            for fault in faults:
                assert fault['actual_error'] == 0x75
                assert fault['lookup_streams'] == [1, 3]
                for flag in ('credit_error_propagated', 'held_gpu_result_retained_actual_load',
                    'actual_load_released_after_gpu_ack', 'no_failed_stream_data_granted', 'actual_memory_owners_drained'):
                    assert fault[flag] is True, (case, fault['fault_phase'], flag)
                grants = fault['grant_trace']
                assert [g['frame_req_stream'] for g in grants] == [1, 3]
                assert grants[0]['frame_grant_bytes'] == 48
                assert grants[1]['frame_grant_bytes'] == 0
                assert grants[1]['owned_window_rsp_memory_status'] == 0x75
                if link_pause:
                    witness=fault['capacity_fault_link_pause']
                    assert witness['pause_cycles']>0 and witness['held_cycles']>=0
                    assert witness['actual_fault_ack']==1 and witness['link_released'] is True
            assert accepted['actual_memory_error'] == 0x75
            assert accepted['actual_directory_owner_retained_until_gpu_ack']
        elif case == 'return_faults':
            faults = accepted['actual_return_metadata_faults']
            assert [f['phase'] for f in faults] == list(range(20))
            assert [f['memory_commands'] for f in faults] == list(range(1, 21))
            for phase, fault in enumerate(faults):
                assert fault['wire_types'] == ([] if phase < 5 else [1] if phase < 10 else [1, 0] if phase < 15 else [1, 0, 1])
                assert fault['gpu_stage'] == (5 if phase < 5 else 20)
            assert accepted['actual_gpu_descriptors_accepted'] == 21
            assert accepted['actual_memory_error'] == 0x75
            assert accepted['successful_gpu_return_after_explicit_root_reinitialization']
        executions[case] = dict(snapshot=name, test_name=tests[0].attrib['name'], acceptance=accepted,
            fixture_initialization_edit=edit, exact_fixture_inverse_verified=True,
            all_original_traffic_vectors_and_assertions_preserved=True, inputs_sha256=inputs)
        if capacity:
            executions[case].update(fixture_capacity_edit=credit_edit,actual_verified_initial_grants=capacity_admissions)
            if link_pause:executions[case].update(fixture_fault_link_edit=e,fixture_fault_link_top_edit=top,
                original_fault_overlap_enforced_by_real_link_backpressure=True)
        artifacts.update([launch_path, *[p for p in archive.iterdir() if p.is_file()]])
    result = dict(phase=args.candidate.replace('-','_')+'_extended_protocol_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_corpus_audit_key=parent['key'], unit_audit_key=units['key'], executions=executions,
        all_five_extended_suites_verified=set(args.cases)==set(PROFILES),
        unchanged_bootstrap_counterexamples=bootstrap_failures,
        exact_parser_modules=77 if payload or reclaim else 76, exact_tokenizer_modules=22, executed_parser_sha256=units['executed_parser_sha256' if quiet else 'candidate_parser_sha256'],
        executed_tokenizer_sha256=parent['executed_tokenizer_sha256'],
        protocol_fixture_sources_unchanged=False, fixture_initialization_only=not capacity,
        fixture_initial_capacity_settlement_and_geometry_expectations=capacity,
        fixture_fault_overlap_uses_real_link_backpressure=args.capacity_fault_link_pause,
        all_original_traffic_vectors_and_assertions_preserved=True, portable_memory_backend=True,
        latest_31_module_tokenizer_controller_integrated=False, native_timing_verified=False,
        full_protocol_matrix_verified=False, physical_interfaces_verified=False, full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p) for p in sorted(artifacts)})
    result['key'] = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    audit_name=args.candidate+'-extended'
    target = root/'build/validation'/(audit_name+'-evidence')/result['key']
    target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation'/(audit_name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'], key=result['key'], cases=list(executions))))


if __name__ == '__main__':
    main()
