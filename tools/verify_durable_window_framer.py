"""Audit executed actual-directory/durable-credit framing and native route."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from generate_two_fpga_application import balanced
from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--functional-only', action='store_true')
    parser.add_argument('--snapshot-name', default='actual_durable_frame_parked_close')
    parser.add_argument('--native-run', default='grpc_durable_framer_scu35_parked_close')
    args = parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', x) for x in (args.snapshot_name, args.native_run))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    archive = root / 'build/wsl-reports' / ('grpc_durable_framer_' + args.snapshot_name)
    executed = archive / 'execution-sources'
    inputs = json.loads((archive / 'inputs.json').read_text())
    report = json.loads((archive / 'report.json').read_text())
    accepted = json.loads((archive / 'acceptance.json').read_text())
    snapshot = json.loads((archive / 'snapshot.json').read_text())
    assert report['phase'] == accepted['phase'] == 'passed' and snapshot['exit_code'] == 0
    assert report['input_sha256'] == inputs and report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    assert report['tests'] == 1 and report['failures'] == 0
    for name, digest in inputs.items(): assert sha(executed / name) == digest
    xml = ET.parse(archive / 'results.xml'); tests = xml.findall('.//testcase')
    assert len(tests) == 1 and tests[0].attrib['name'] == 'actual_durable_grants_partial_frames_and_uncertain_debit'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    assert accepted['exact_native_frames'] == 4 and accepted['application_bytes'] == 20000
    assert accepted['grpc_record_bytes'] == 20005 and accepted['wire_bytes'] == 20041
    assert accepted['grants'] == [1, 2, 16384, 3618] and accepted['reserve_attempts'] == 12
    assert accepted['held_frame_result_cycles'] == 68 and accepted['tx_stall_cycles'] > 0
    for name in ('actual_cached_directory_binding', 'actual_pool_authority', 'both_debits_before_grant',
                 'no_credit_parking_verified', 'unrelated_stream_does_not_retry', 'captured_frame_configuration_verified',
                 'actual_peer_max_frame_enforced', 'uncertain_debit_emits_no_data', 'closed_stream_emits_no_data',
                 'cached_lease_fenced_through_result', 'model_prefix_immutable', 'close_wakes_parked_sender'):
        assert accepted[name], name
    for name in ('raw_http2_control_integrated', 'response_headers_trailers_implemented', 'full_system_complete'):
        assert accepted[name] is False
    dependencies = closure('grpc_durable_window_framer', executed)
    assert set(dependencies) == {'grpc_durable_window_framer', 'http2_owned_lifecycle_windows',
        'http2_lifecycle_send_window_store', 'grpc_pool_locked_stream_store', 'grpc_stream_store',
        'memory_command_slot', 'grpc_http2_response_framer', 'axis_byte_unpacker', 'axis_byte_packer'}
    actual = []
    for name, path in dependencies.items():
        source = re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(), flags=re.S)
        for match in re.finditer(r'\bgrpc_stream_store\s*#\s*\(', source):
            end = balanced(source, source.index('(', match.start()))
            if re.match(r'\s*\w+\s*\(', source[end + 1:]): actual.append(name)
    assert actual == ['grpc_pool_locked_stream_store']
    source = (executed / 'rtl/grpc_durable_window_framer.v').read_text()
    for token in ('frame_generation<=lease_rsp_generation;frame_address<=lease_rsp_address;',
                  '.lease_rsp_ready(lease_rsp_ready&&!frame_active&&!start_valid&&!window_busy&&state==IDLE)',
                  '.frame_grant_bytes(grant_bytes)', 'parked<=owned_window_rsp_status==1;',
                  'owned_window_rsp_op==8', "assign grant_bytes=owned_window_rsp_status==0?owned_window_rsp_grant_bytes:24'd0;"):
        assert token in source, token
    owned = (executed / 'rtl/http2_owned_lifecycle_windows.v').read_text()
    assert '.req_authority(directory_pool_lock_active)' in owned
    assert '.req_valid(state==ISSUE&&directory_pool_lock_active)' in owned
    # Rebuild the exact native reference from its frozen generator, independently
    # of the acceptance JSON or any currently edited vector generator.
    fixture = executed / 'build/http2-durable-framer-fixtures/frames.json'
    reference = json.loads(fixture.read_text())
    generator = executed / 'tools/generate_durable_framer_vectors.py'
    assert reference['phase'] == 'native_durable_framer_reference_passed'
    assert reference['generator_sha256'] == sha(generator)
    replay_key = sha(generator)[:16]
    replay = root / 'build/validation/durable-framer-native-replay' / replay_key
    replay_script = replay / 'tools/generate_durable_framer_vectors.py'
    replay_script.parent.mkdir(parents=True, exist_ok=True)
    (replay / 'build').mkdir(exist_ok=True)
    if replay_script.exists(): assert sha(replay_script) == sha(generator)
    else: shutil.copy2(generator, replay_script)
    completed = subprocess.run([sys.executable, str(replay_script)], check=True, capture_output=True, text=True)
    assert sha(replay / 'build/http2-durable-framer-fixtures/frames.json') == sha(fixture)
    assert [f['payload_bytes'] for f in reference['frames']] == accepted['grants']
    assert sum(len(bytes.fromhex(f['wire_hex'])) for f in reference['frames']) == accepted['wire_bytes']
    model_fixture = executed / 'build/http2-send-window-fixtures'
    model = json.loads((model_fixture / 'cases.json').read_text())
    assert model['original_image_sha256'] == sha(model_fixture / 'model.bin') == sha(root / 'build/scu35/image/external_memory.bin')
    assert model['generator_sha256'] == sha(executed / 'tools/generate_http2_send_window_vectors.py')
    key = hashlib.sha256((model['generator_sha256'] + model['original_image_sha256']).encode()).hexdigest()[:16]
    assert sha(root / 'build/validation/http2-send-window-reference-replay' / key / 'build/http2-send-window-fixtures/cases.json') == sha(model_fixture / 'cases.json')
    files = {Path('execution') / name: executed / name for name in inputs}
    files.update({Path('reports') / name: archive / name for name in
        ('report.json', 'inputs.json', 'snapshot.json', 'results.xml', 'acceptance.json', 'simulation.log', 'build.log')})
    files[Path('verification/verify_durable_window_framer.py')] = Path(__file__)
    files[Path('reference-replay/frames.json')] = replay / 'build/http2-durable-framer-fixtures/frames.json'
    result = dict(phase='durable_credit_framing_functional_passed_native_pending',
        verified_utc=datetime.now(timezone.utc).isoformat(), acceptance=accepted,
        active_rtl_modules=list(dependencies), execution_inputs=len(inputs), native_reference_reproduced=True,
        single_actual_directory_verified=True, actual_cached_binding_and_pool_authority_verified=True,
        current_primary_differences=[n for n, h in inputs.items() if not (source_path(root, n)).is_file() or sha(source_path(root, n)) != h],
        raw_control_integrated=False, response_headers_trailers_verified=False,
        whole_rpc_image_leases_verified=False, independent_clocks_verified=False,
        physical_interfaces_verified=False, full_system_complete=False, verifier_sha256=sha(Path(__file__)))
    if not args.functional_only:
        native = root / 'build/implementation/xcsu35p-sbvb625-2-e' / args.native_run
        frozen = native / 'sources'; provenance = json.loads((native / 'source-provenance.json').read_text())
        for name, record in provenance['files'].items():
            assert sha(frozen / name) == record['sha256'] and (frozen / name).stat().st_size == record['bytes']
        routed_dependencies = closure('grpc_durable_window_framer', frozen)
        assert set(routed_dependencies) == set(dependencies)
        for path in routed_dependencies.values():
            relative = path.relative_to(frozen)
            assert sha(path) == inputs[relative.as_posix()]
            files[Path('native/sources') / relative] = path
        script = (frozen / 'scripts/implement_registered_subsystem.tcl').read_text()
        assert [line.strip() for line in script.splitlines() if line.strip().startswith('set_false_path')] == [
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]',
            'set_false_path -to [all_outputs]']
        log = source_path(root, f'build/{args.native_run}-implementation.log')
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=grpc_durable_window_framer PART=xcsu35p-sbvb625-2-e' in log.read_text()
        assert '0 Critical Warnings and 0 Errors encountered.' in log.read_text() and 'ERROR: [Synth' not in log.read_text()
        area = resources(native / 'routed_utilization.rpt'); clocks = timing(native / 'routed_timing.rpt')
        assert area['luts'] <= 16320 and area['registers'] <= 32640
        assert area['bram36'] + area['bram18'] / 2 <= 48 and area['uram'] == area['dsps'] == 0
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (native / 'route_status.rpt').read_text())
        assert not re.search(r'\|\s*(Error|Critical Warning)\s*\|', (native / 'routed_drc.rpt').read_text())
        met = clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0
        result.update(phase='durable_credit_framing_functional_and_timing_met' if met else 'durable_credit_framing_functional_passed_timing_pending',
            native_run=args.native_run, native_exact_rtl_files=len(routed_dependencies), resources=area,
            timing=clocks, routed_timing_met=met, package_paths_excluded=True, routed_checkpoint_sha256=sha(native / 'routed.dcp'))
        files[Path('native/implementation.log')] = log
        for name in ('source-provenance.json', 'routed_utilization.rpt', 'routed_timing.rpt', 'routed_drc.rpt', 'route_status.rpt'):
            files[Path('native') / name] = native / name
        for name in provenance['files']:
            if not name.startswith('rtl/'): files[Path('native/sources') / name] = frozen / name
    key = hashlib.sha256(''.join(sha(files[p]) for p in sorted(files)).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/durable-window-framer-evidence' / key
    for name, path in files.items():
        target = evidence / name; target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists(): assert sha(target) == sha(path)
        else: shutil.copy2(path, target)
    result['evidence_folder'] = str(evidence)
    (root / 'build/validation/durable-window-framer.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
