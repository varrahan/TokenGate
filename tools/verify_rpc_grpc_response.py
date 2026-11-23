"""Audit actual split RPC-to-DATA execution and the Parser return implementation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import xml.etree.ElementTree as ET
from hyperframe.frame import DataFrame, Frame

from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-name')
    parser.add_argument('--native-run')
    parser.add_argument('--leased-directory', action='store_true')
    parser.add_argument('--durable-return', action='store_true')
    parser.add_argument('--keyed-return', action='store_true')
    parser.add_argument('--functional-only', action='store_true')
    args = parser.parse_args()
    assert not(args.keyed_return and args.durable_return)
    if args.keyed_return:args.durable_return=True
    assert not (args.leased_directory and args.durable_return)
    args.snapshot_name = args.snapshot_name or ('rpc_keyed_registered_geometry' if args.keyed_return else 'actual_rpc_durable_metrics' if args.durable_return else 'rpc_leased_zero_credit_initial' if args.leased_directory else 'rpc_grpc_retirement_metrics')
    args.native_run = args.native_run or ('rpc_grpc_keyed_scu35_registered_geometry' if args.keyed_return else 'rpc_grpc_durable_scu35_initial' if args.durable_return else 'rpc_grpc_leased_scu35_initial' if args.leased_directory else 'rpc_grpc_parser_scu35_retirement_initial')
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', value) for value in (args.snapshot_name, args.native_run))
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    suite = 'rpc_keyed' if args.keyed_return else 'rpc_durable' if args.durable_return else 'rpc_leased' if args.leased_directory else 'rpc_grpc'
    top = 'rpc_grpc_keyed_return' if args.keyed_return else 'rpc_grpc_durable_return' if args.durable_return else 'rpc_grpc_leased_return' if args.leased_directory else 'rpc_grpc_parser_response'
    archive = root / 'build/wsl-reports' / ('cocotb_' + suite + '_' + args.snapshot_name)
    executed = archive / 'execution-sources'
    report = json.loads((archive / 'report.json').read_text())
    accepted = json.loads((archive / 'acceptance.json').read_text())
    snapshot = json.loads((archive / 'snapshot.json').read_text())
    assert report['suite'] == suite and report['phase'] == accepted['phase'] == 'passed'
    assert report['tests'] == 1 and report['failures'] == 0 and not report.get('changed_inputs')
    assert snapshot['phase'] == 'snapshot_run_archived' and snapshot['runner_exit_code'] == 0
    assert snapshot['execution_report_sha256'] == sha(archive / 'report.json')
    assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    assert snapshot['snapshot_runner_sha256'] == sha(executed / 'scripts/run_cocotb_snapshot.py')
    xml = ET.parse(archive / 'results.xml')
    tests = xml.findall('.//testcase')
    test_name = 'actual_keyed_rpc_progress_credit_and_data' if args.keyed_return else 'actual_rpc_progress_then_durable_credit_and_data' if args.durable_return else 'cached_authority_and_directory_progress_under_zero_credit' if args.leased_directory else 'bound_tokens_to_credit_granted_data_and_retirement'
    assert len(tests) == 1 and tests[0].attrib['name'] == test_name
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    inputs = {**report['source_sha256'], **report['fixture_sha256']}
    for name, digest in inputs.items():
        assert sha(executed / name) == digest == snapshot['source_and_fixture_sha256'][name], name
    fixture = executed / 'build/rpc-grpc-fixtures'
    frames = json.loads((fixture / 'frame_cases.json').read_text())
    reference = json.loads((fixture / 'rpc_cases.json').read_text())
    model_manifest = json.loads((fixture / 'model_manifest.json').read_text())
    assert frames['phase'] == 'native_references_passed'
    assert frames['generator_sha256'] == sha(executed / 'tools/generate_rpc_grpc_vectors.py')
    assert reference['generator_sha256'] == sha(executed / 'tools/generate_rpc_response_vectors.py')
    assert frames['model_image_sha256'] == reference['model_image_sha256'] == model_manifest['image_sha256'] == sha(fixture / 'memory.bin')
    # Decode all frozen ordinary/capacity frame patterns independently of the
    # stimulus generator and simulator's byte comparisons.
    decoded_patterns = 0
    for key, pattern in frames['frames'].items():
        stream, encoded_body = key.split(':', 1)
        body = bytes.fromhex(encoded_body)
        assert pattern['complete'] and pattern['body'] == encoded_body
        record = b'\0' + len(body).to_bytes(4, 'big') + body
        reconstructed = bytearray()
        assert len(pattern['frames']) == len(pattern['grants']) == len(pattern['maxima'])
        for encoded, grant, maximum in zip(pattern['frames'], pattern['grants'], pattern['maxima']):
            assert maximum == min(16384, len(record) - len(reconstructed))
            assert 0 < grant <= maximum
            wire = bytes.fromhex(encoded)
            frame, size = Frame.parse_frame_header(memoryview(wire[:9]))
            assert isinstance(frame, DataFrame) and frame.stream_id == int(stream)
            assert not set(frame.flags) and size == grant and len(wire) == size + 9
            frame.parse_body(memoryview(wire[9:]))
            assert frame.serialize() == wire
            reconstructed.extend(frame.data)
        assert bytes(reconstructed) == record
        decoded_patterns += 1
    # Independently prove the extension retained every original populated slot,
    # all original pool bytes and every other byte of the complete model image.
    original_file = root / 'build/scu35/image/external_memory.bin'
    assert sha(original_file) == frames['original_complete_image_sha256'] == reference['original_complete_image_sha256']
    original = original_file.read_bytes()
    candidate = bytearray((fixture / 'memory.bin').read_bytes())
    assert len(original) == len(candidate) == 8388608
    directory, pool = reference['layout']['directory_base'], reference['layout']['pool_base']
    assert reference['capacity_tokens'] == [120000, 120001]
    for token, length in zip(reference['capacity_tokens'], (16384, 16385)):
        offset = directory + token * 8
        assert struct.unpack_from('<Q', original, offset)[0] == 0
        assert struct.unpack_from('<Q', candidate, offset)[0] == 2 | 900000 << 16 | length << 48
        candidate[offset:offset + 8] = original[offset:offset + 8]
    assert bytes(candidate) == original, 'The fixture changed original model bytes outside empty test entries'
    assert candidate[pool + 900000:pool + 916385] == bytes(16385)
    for region in model_manifest['regions']:
        data = (fixture / 'memory.bin').read_bytes()[region['base']:region['base'] + region['bytes']]
        assert hashlib.sha256(data).hexdigest() == region['sha256']
    assert (accepted['cases'], accepted['successes'], accepted['rejections'], accepted['injected_faults']) == (185, 110, 75, 23 if args.durable_return else 21)
    if not args.durable_return:
        assert accepted['capacity_cases'] == 4 and accepted['transport_quarantine_cases'] == 3
        assert accepted['baseline_rpc_matrix']['cases'] == 178 and accepted['clock_cycles'] > accepted['baseline_rpc_matrix']['clock_cycles']
        assert accepted['pre_grant_buffer_reset_cycles'] > 0
    assert accepted['complete_model_prefix_immutable']
    assert accepted['frame_grants'] == accepted['framed_wire_frames'] + 2
    assert accepted['directory_held_through_public_ack_verified']
    if not args.durable_return:
        assert accepted['durable_progress_before_wire_verified']
        assert accepted['network_connection_context_verified'] and accepted['separate_parser_and_inverse_instances_verified']
    assert all(accepted[name] > 0 for name in (('credit_park_cycles', 'tx_stall_cycles', 'result_stall_cycles', 'blocked_control_cycles') if args.durable_return else ('credit_stall_cycles', 'tx_stall_cycles', 'result_stall_cycles', 'blocked_control_cycles')))
    parser_dependencies = closure(top, executed)
    inverse_dependencies = closure('inverse_tokenizer_partition', executed)
    assert len(parser_dependencies) == (16 if args.durable_return else 13 if args.leased_directory else 10) and 'detokenizer_engine' not in parser_dependencies and 'bpe_tokenizer_engine' not in parser_dependencies
    assert {'rpc_response_parser_partition', 'utf8_serialized_chunk', 'grpc_http2_response_framer'} <= parser_dependencies.keys()
    assert 'detokenizer_engine' in inverse_dependencies and 'proto_json_serializer' not in inverse_dependencies
    if args.leased_directory:
        assert {'rpc_grpc_leased_return','grpc_leased_stream_store','grpc_stream_store'} <= parser_dependencies.keys()
        assert accepted['leased_directory_integrated'] and accepted['single_shared_directory_authority_verified']
        assert (accepted['zero_credit_control_transactions'],accepted['held_result_control_transactions'],accepted['protected_busy_responses']) == (13,3,7)
        assert accepted['busy_reason_counts'] == {'1':2,'2':1,'3':1,'4':1,'5':1,'6':1}
        assert accepted['cached_lease_snapshot_coherent'] and accepted['same_generation_saves_under_lease'] == accepted['post_retirement_close_allowed'] == 1
        assert accepted['backend_idle_while_lease_active_cycles'] > 0
        harness=(executed/'sim/cocotb_rpc_leased_top.sv').read_text()
        assert 'grpc_stream_store registry(' not in harness and 'rpc_grpc_leased_return #' in harness
    if args.durable_return:
        assert accepted['baseline_rpc_matrix']['cases'] == 178
        assert accepted['capacity_cases'] == 4 and accepted['transport_quarantine_cases'] == 3
        assert len(accepted['commands']) == len(accepted['writes']) == 5
        assert accepted['commands'][4] == accepted['window_memory_commands']
        assert accepted['writes'][4] == accepted['window_memory_writes']
        assert all(a >= b for a, b in zip(accepted['commands'], accepted['baseline_rpc_matrix']['commands']))
        assert accepted['pre_grant_buffer_reset_cycles'] > 0
        assert accepted['post_commit_credit_fault_cases'] == 2
        assert accepted['durable_positive_grants'] == accepted['framed_wire_frames'] == 449
        assert accepted['extended_configuration_poison_cases'] == accepted['cases']
        assert accepted['reserve_attempts'] > accepted['durable_positive_grants']
        assert accepted['window_memory_commands'] > accepted['window_memory_writes'] > 2 * accepted['durable_positive_grants']
        assert all(accepted[name] for name in ('actual_cached_directory_and_pool_authority','actual_durable_window_grants',
            'all_progress_acks_before_reservation','both_debits_before_data','private_rejection_does_not_reset_directory'))
        assert not accepted['raw_http2_control_integrated']
        assert ({'http2_keyed_frame_grants','http2_owned_keyed_windows','http2_keyed_send_window_store',
            'grpc_pool_locked_stream_store','grpc_stream_store'} if args.keyed_return else
            {'http2_durable_frame_grants','http2_owned_lifecycle_windows','http2_lifecycle_send_window_store',
            'grpc_pool_locked_stream_store','grpc_stream_store'}) <= parser_dependencies.keys()
        harness=(executed/('sim/cocotb_rpc_keyed_top.sv'if args.keyed_return else'sim/cocotb_rpc_durable_top.sv')).read_text()
        assert 'grpc_stream_store registry(' not in harness and 'external_memory_fabric #(.CLIENTS(5))' in harness
        source=(executed/f'rtl/{top}.v').read_text()
        assert '.rst(rst)' in source and '.rst(rst||kill_ungranted)' not in source
        assert '.start_valid(frame_req_valid&&!credit_binding_active)' in source
        assert '.finish_valid(retire)' in source and '.lease_rsp_ready(directory_result_ready)' in source
        assert 'assign result_valid=child_result_valid&&grant_finish_ready;' in source
        assert 'saved_frame_cfg_context_base<=cfg_context_base;' in source
        child=(executed/'rtl/rpc_grpc_parser_response.v').read_text()
        assert 'assign frame_req_valid=framer_valid&&authorized;' in child
        assert 'wire authorized=rpc_result_valid&&rpc_status==0&&directory_requested&&release_pending&&!kill_ungranted;' in child
        if args.keyed_return:
            assert accepted['actual_keyed_window_update_commands']
            assert accepted['key_only_window_updates']==2*(accepted['durable_positive_grants']-1)==896
            keyed=(executed/'rtl/http2_keyed_frame_grants.v').read_text()
            assert 'owned_window_rsp_op==9' in keyed
            assert '.req_authority(directory_pool_lock_active)' in (executed/'rtl/http2_owned_keyed_windows.v').read_text()
    result = dict(phase='functional_passed_native_pending', verified_utc=datetime.now(timezone.utc).isoformat(),
        top=top, acceptance=accepted, execution_sources=len(report['source_sha256']),
        execution_fixtures=len(report['fixture_sha256']), parser_rtl_modules=list(parser_dependencies),
        inverse_rtl_modules=list(inverse_dependencies), original_populated_model_preserved=True,
        independently_decoded_native_frame_patterns=decoded_patterns,
        verifier_sha256=sha(Path(__file__)), current_primary_differences=[name for name, digest in inputs.items()
            if not (source_path(root, name)).is_file() or sha(source_path(root, name)) != digest],
        shared_leased_directory_integrated=args.leased_directory or args.durable_return, complete_forward_application_joined=False,
        actual_http2_window_update_ingress_verified=False, headers_trailers_verified=False, credit_ledger_verified=args.durable_return,
        actual_progress_authorized_durable_return_verified=args.durable_return,
        key_only_window_update_commands_verified=args.keyed_return,
        independent_memory_banks_verified=False, independent_clock_domains_verified=False,
        distributed_image_leases_verified=False, physical_adapters_verified=False, full_system_complete=False)
    result['current_primary_rtl_differences'] = [name for name in result['current_primary_differences'] if name.startswith('rtl/')]
    files = {Path('execution') / name: executed / name for name in inputs}
    files[Path('model/original_complete_image.bin')] = original_file
    files[Path('verification/run_cocotb_snapshot.py')] = executed / 'scripts/run_cocotb_snapshot.py'
    files[Path('verification/verify_rpc_grpc_response.py')] = Path(__file__)
    for name in ('report.json', 'acceptance.json', 'results.xml', 'build.log', 'simulation.log', 'snapshot.json', 'native-reference.json'):
        files[Path('reports') / name] = archive / name
    native = root / 'build/implementation/xcsu35p-sbvb625-2-e' / args.native_run
    if not args.functional_only:
        sources = native / 'sources'
        provenance = json.loads((native / 'source-provenance.json').read_text())
        for name, record in provenance['files'].items():
            assert sha(sources / name) == record['sha256']
        native_dependencies = closure(top, sources)
        assert set(native_dependencies) == set(parser_dependencies)
        for path in native_dependencies.values():
            name = path.relative_to(sources).as_posix()
            assert sha(path) == report['source_sha256'][name]
            files[Path('native/sources') / name] = path
        result['native_active_rtl_matches_primary'] = all(
            (source_path(root, path.relative_to(sources))).is_file() and sha(source_path(root, path.relative_to(sources))) == sha(path)
            for path in native_dependencies.values())
        implementation = (sources / 'scripts/implement_registered_subsystem.tcl').read_text()
        assert [line.strip() for line in implementation.splitlines() if line.strip().startswith('set_false_path')] == [
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]', 'set_false_path -to [all_outputs]']
        log = source_path(root, 'build/' + args.native_run + '-implementation.log')
        text = log.read_text()
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP='+top+' PART=xcsu35p-sbvb625-2-e' in text
        assert '0 Critical Warnings and 0 Errors encountered.' in text and 'ERROR: [Synth' not in text
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (native / 'route_status.rpt').read_text())
        measured, clocks = resources(native / 'routed_utilization.rpt'), timing(native / 'routed_timing.rpt')
        if args.leased_directory or args.durable_return:
            rows=[[cell.strip()for cell in line.split('|')[1:-1]]for line in (native/'routed_utilization.rpt').read_text().splitlines()if line.startswith('|')]
            stores=[row for row in rows if len(row)>1 and row[1]=='grpc_stream_store'and not row[0].startswith('(')]
            assert len(stores)==1,('Actual directory instances',stores)
        assert measured['luts'] <= 16320 and measured['bram36'] + measured['bram18'] / 2 <= 48
        assert measured['bram36'] + measured['bram18'] / 2 >= 28 and measured['uram'] == measured['dsps'] == 0
        drc = (native / 'routed_drc.rpt').read_text()
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|', drc, re.M)
        met = clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0
        result.update(phase='functional_passed_native_timing_met' if met else 'functional_passed_native_timing_pending',
            native_run=args.native_run, native_exact_rtl_files=len(native_dependencies), part='xcsu35p-sbvb625-2-e',
            timing=clocks, resources=measured, routed_timing_met=met, package_paths_excluded=True,
            routed_checkpoint_sha256=sha(native / 'routed.dcp'), drc_checks=int(re.search(r'Checks found:\s*(\d+)', drc)[1]))
        files[Path('native/implementation.log')] = log
        for name in ('source-provenance.json', 'routed_utilization.rpt', 'routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt'):
            files[Path('native') / name] = native / name
        for name in provenance['files']:
            if not name.startswith('rtl/'):
                files[Path('native/sources') / name] = sources / name
    key = hashlib.sha256((sha(archive / 'report.json') + sha(Path(__file__)) +
        ('functional-only' if args.functional_only else sha(native / 'source-provenance.json'))).encode()).hexdigest()[:16]
    label='rpc-grpc-keyed-return' if args.keyed_return else 'rpc-grpc-durable-return' if args.durable_return else 'rpc-grpc-leased-return' if args.leased_directory else 'rpc-grpc-return'
    evidence = source_path(root, Path('build/validation/'+label+'-evidence') / (key))
    for name, source in files.items():
        target = evidence / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert sha(target) == sha(source), ('Immutable evidence changed', name)
        else:
            shutil.copy2(source, target)
    result['evidence_folder'] = str(evidence)
    (source_path(root, 'build/validation/'+label+'.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
