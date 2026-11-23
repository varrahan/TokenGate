"""Bind actual duplex counterexamples and the isolated fix to frozen executions."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from verify_two_fpga_application import closure, resources, timing
from verify_native_grpc_corpus_reference import verify_reference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duplex', default='context_commit_guard_duplex_final')
    parser.add_argument('--native', default='context_commit_guard_native')
    parser.add_argument('--return-faults', default='context_commit_guard_return_faults')
    parser.add_argument('--shutdown-faults')
    parser.add_argument('--duplex-faults')
    parser.add_argument('--rpc')
    parser.add_argument('--workload')
    parser.add_argument('--receive-counterexample')
    parser.add_argument('--registered-envelope-scope', action='store_true')
    parser.add_argument('--scope-proof')
    parser.add_argument('--native-run', default='parser_au15p_context_commit_guard')
    args = parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', n) for n in vars(args).values() if isinstance(n, str) and n)
    assert bool(args.scope_proof) == args.registered_envelope_scope
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    experiment = 'registered-envelope-scope' if args.registered_envelope_scope else 'context-commit-guard'
    generated = root / 'build/experiments' / experiment / 'rtl'
    overrides = {'rtl/' + p.name: sha(p) for p in generated.glob('*.v')}
    assert len(overrides) == 10
    baseline_file = root / 'build/validation/checked-close-address-experiment.json'
    baseline = json.loads(baseline_file.read_text())
    assert baseline['verifier_sha256'] == sha(root / 'tools/verify_checked_close_address_experiment.py')
    assert baseline['raw_shutdown_faults_direct_on_three_file_experiment_verified']
    assert baseline['raw_return_faults_direct_on_three_file_experiment_verified']
    baseline_source = root / 'build/wsl-reports/raw_envelope_checked_close_address_native/execution-sources'
    records = {}
    scope_proof = None
    if args.scope_proof:
        archive = root / 'build/wsl-reports' / ('envelope_scope_equivalence_' + args.scope_proof)
        frozen = archive / 'execution-sources'
        proof_inputs = json.loads((archive / 'inputs.json').read_text())
        scope_proof = json.loads((archive / 'report.json').read_text())
        assert scope_proof['phase'] == 'passed' and scope_proof['yosys_exit_code'] == 0
        assert json.loads((archive / 'snapshot.json').read_text())['exit_code'] == 0
        assert scope_proof['unbounded_post_reset_saved_scope_equivalence']
        assert scope_proof['simultaneous_captures_and_retirement_unconstrained']
        assert not scope_proof['whole_module_equivalence_verified']
        assert scope_proof['input_sha256'] == proof_inputs
        for n, h in proof_inputs.items(): assert sha(frozen / n) == h, n
        assert proof_inputs['rtl/gold_input.v'] == sha(root / 'build/experiments/context-commit-guard/rtl/rpc_grpc_http2_return.v')
        assert proof_inputs['rtl/gate_input.v'] == overrides['rtl/rpc_grpc_http2_return.v']
        for n, h in scope_proof['generated_sha256'].items(): assert sha(archive / n) == h, n
        spec = importlib.util.spec_from_file_location('frozen_envelope_scope', frozen / 'scripts/run_envelope_scope_equivalence.py')
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        for label in ('gold', 'gate'):
            text, _ = runner.model((frozen / ('rtl/' + label + '_input.v')).read_text(), label)
            assert text == (archive / (label + '.v')).read_text()
        miter = (archive / 'miter.v').read_text()
        assert miter.count('assume(') == 1 and 'if(!initialized)assume(rst);' in miter
        assert 'assert(gold_value==gate_value);assert(gold_observed==gate_observed);' in miter
        assert 'Induction step proven: SUCCESS!' in (archive / 'yosys.log').read_text()
        assert (archive / 'proof.ys').read_text() == 'read_verilog -formal gold.v gate.v miter.v\nprep -top envelope_equivalence -flatten\nsat -seq 1 -tempinduct -maxsteps 8 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n'
        scope_proof = dict(report=scope_proof, archive=str(archive), input_sha256=proof_inputs,
            files_sha256={p.name: sha(p) for p in archive.iterdir() if p.is_file()})

    def read(name, profile, passed=True):
        is_rpc = profile == 'rpc'
        archive = root / 'build/wsl-reports' / (('rpc_http2_' if is_rpc else 'raw_envelope_') + name)
        source = archive / 'execution-sources'
        inputs = json.loads((archive / 'inputs.json').read_text())
        report = json.loads((archive / 'report.json').read_text())
        snapshot = json.loads((archive / 'snapshot.json').read_text())
        assert report['input_sha256'] == inputs
        if not is_rpc: assert report['profile'] == snapshot['profile'] == profile
        for n, h in inputs.items(): assert sha(source / n) == h, (name, n)
        xml = ET.parse(archive / 'results.xml')
        cases = xml.findall('.//testcase'); assert len(cases) == 1
        assert snapshot['exit_code'] == (0 if passed else 1)
        accepted = None
        if passed:
            assert report['phase'] == 'passed' and report['tests'] == 1 and report['failures'] == 0
            assert not xml.findall('.//failure') and not xml.findall('.//error')
            assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
            accepted = json.loads((archive / 'acceptance.json').read_text())
            assert accepted['phase'] == 'passed' and not accepted['full_system_complete']
            assert set(snapshot['isolated_rtl_overrides']) == set(overrides)
        else:
            assert report['phase'] == 'failed' and xml.findall('.//failure')
        targets = [('rpc_grpc_http2_return', 20)] if is_rpc else [('http2_enveloped_parser_application', 68), ('tokenizer_fpga_memory_subsystem', 22)]
        for top, count in targets:
            dag = closure(top, source); assert len(dag) == count
            if passed:
                for p in dag.values():
                    n = p.relative_to(source).as_posix()
                    assert inputs[n] == overrides.get(n, sha(root / n)), (name, n)
        for n, h in inputs.items():
            if n.startswith(('build/bidirectional-fixtures/', 'native-vendor/')):
                assert h == sha(baseline_source / n), (name, n)
        files = {p.name: sha(p) for p in archive.iterdir() if p.is_file()}
        records[name] = dict(archive=str(archive), profile=profile, input_sha256=inputs,
            report_sha256=files, test_name=cases[0].attrib['name'], acceptance=accepted)
        return archive, source, inputs, accepted

    if args.rpc:
        archive, _, inputs, accepted = read(args.rpc, 'rpc')
        assert accepted == baseline['actual_rpc_acceptance']
        assert inputs['sim/cocotb/test_rpc_http2_return.py'] == sha(root / 'sim/cocotb/test_rpc_http2_return.py')
        reference = root / 'build/wsl-reports/rpc_http2_checked_close_address_matrix/execution-sources'
        for n, h in inputs.items():
            if n.startswith(('build/rpc-grpc-fixtures/', 'build/grpc-header-fixtures/')): assert h == sha(reference / n)
        properties = {p.attrib['name']: p.attrib['value'] for p in ET.parse(archive / 'results.xml').findall('.//property')}
        assert properties['sim_time_unit'] == 'ns' and float(properties['sim_time_duration']) == 522354

    # These two archives are actual failures, not inferred source hazards.
    archive, source, _, _ = read('actual_duplex_first_offer_baseline', 'duplex', False)
    failure = json.loads((archive / 'failure.json').read_text())
    assert failure['phase'] == 'axis_promise_violation' and failure['probe'] == 'raw'
    assert failure['valid'] == failure['ready'] == 0 and failure['observed'] is None
    assert sha(source / 'rtl/http2_enveloped_parser_core.v') == sha(root / 'rtl/http2_enveloped_parser_core.v')
    archive, _, _, _ = read('registered_rx_grant_actual_writer_trace', 'duplex', False)
    failure = json.loads((archive / 'failure.json').read_text())
    assert failure['phase'] == 'duplex_gpu_error'
    torn = [c for c in failure['counters']['raw_header_checks'] if c['header'] == 0]
    assert len(torn) == 1 and torn[0]['writer_state'] == 10 and not torn[0]['writer_recovery']
    assert torn[0]['address'] == torn[0]['writer_address'] and torn[0]['owner'] == torn[0]['writer_user']

    profiles = [('native', args.native, 'test_raw_grpc_enveloped.py'),
                ('return-faults', args.return_faults, 'test_raw_grpc_return_faults.py'),
                ('shutdown-faults', args.shutdown_faults, 'test_raw_shutdown_faults.py')]
    for profile, name, test in profiles:
        if not name: continue
        _, _, inputs, accepted = read(name, profile)
        assert accepted == baseline['raw_executions'][profile]
        assert inputs['sim/cocotb/' + test] == sha(root / 'sim/cocotb' / test)

    _, source, duplex_inputs, accepted = read(args.duplex, 'duplex')
    assert duplex_inputs['sim/cocotb/test_raw_grpc_duplex.py'] == sha(root / 'sim/cocotb/test_raw_grpc_duplex.py')
    assert accepted['actual_gpu_descriptors'] == accepted['actual_native_completed_grpc_calls'] == 2
    assert accepted['actual_native_ping_acks'] == 7 and accepted['lookup_streams'] == [1, 3]
    assert accepted['raw_held_cycles'] > 0 and accepted['gpu_handshakes'] == 2
    for n in ('actual_downstream_axis_promises_verified', 'byte_exact_rpc_responses_verified',
              'pending_lookup_precedes_later_raw_packets', 'complete_model_prefix_immutable'):
        assert accepted[n], n
    checks = accepted['raw_header_checks']
    index = next(i for i, c in enumerate(checks) if c['header'] == 0)
    assert checks[index]['writer_state'] == 10
    assert any(c['header'] & 0xffffffff == 0x48324331 and c['header'] >> 32 & 1 for c in checks[index + 1:])
    assert not accepted['forward_dma_workload_verified']

    if args.duplex_faults:
        _, _, inputs, faults = read(args.duplex_faults, 'duplex-faults')
        assert faults['context_write_ack_fault_cases'] == 21 and faults['actual_memory_error'] == 0x75
        assert inputs['sim/cocotb/test_raw_grpc_duplex.py'] == sha(root / 'sim/cocotb/test_raw_grpc_duplex.py')
        assert inputs['sim/cocotb/test_raw_grpc_duplex_faults.py'] == sha(root / 'sim/cocotb/test_raw_grpc_duplex_faults.py')
        cases = faults['actual_context_commit_write_faults']
        assert [c['fault_phase'] for c in cases] == list(range(21))
        for case in cases:
            assert case['actual_error'] == 0x75 and case['lookup_streams'] == [1, 3]
            for n in ('credit_error_propagated', 'held_gpu_result_retained_actual_load',
                      'actual_load_released_after_gpu_ack', 'no_failed_stream_data_granted',
                      'actual_memory_owners_drained', 'cold_memory_initialization'): assert case[n]
            assert case['final_recovery']['windows'] or case['final_recovery']['header'] == 0

    corpus = None
    if args.workload:
        archive, workload_source, inputs, accepted = read(args.workload, 'workload')
        assert records[args.workload]['test_name'] == 'complete_prompt_corpus_uses_native_grpc_and_actual_dma'
        assert inputs['sim/cocotb/test_raw_grpc_workload.py'] == sha(root / 'sim/cocotb/test_raw_grpc_workload.py')
        for n in ('sim/cocotb_two_fpga_enveloped_top.sv', 'sim/cocotb/test_raw_grpc_enveloped.py',
                  'sim/cocotb/test_raw_shutdown_controls.py', 'sim/cocotb/test_raw_peer_controls.py',
                  'sim/cocotb/test_http2_prefill.py', 'sim/cocotb/test_two_fpga_application.py'):
            assert inputs[n] == sha(root / n), n
        corpus = verify_reference(root, workload_source, accepted)

    if args.receive_counterexample:
        archive, receive_source, inputs, _ = read(args.receive_counterexample, 'receive-flow', False)
        assert records[args.receive_counterexample]['test_name'] == 'native_padding_credit_replenishment_allows_next_real_prompt'
        assert inputs['sim/cocotb/test_raw_receive_flow.py'] == sha(root / 'sim/cocotb/test_raw_receive_flow.py')
        for top in ('http2_enveloped_parser_application', 'tokenizer_fpga_memory_subsystem'):
            for p in closure(top, receive_source).values():
                n = p.relative_to(receive_source).as_posix()
                assert inputs[n] == overrides.get(n, sha(root / n)), n
        failure = json.loads((archive / 'failure.json').read_text())
        assert failure['phase'] == 'receive_credit_starvation'
        assert failure['native_padding_payload_bytes'] == 65535
        assert failure['native_connection_credit'] == failure['native_stream_and_connection_credit'] == 0
        assert failure['actual_raw_packets'] == 8 and failure['actual_forward_dma_ids'] == 0
        assert failure['actual_window_update_frames'] == 0 and failure['actual_wire_types'] == [4, 4]
        assert failure['no_application_payload_or_gpu_work'] and not failure['full_system_complete']

    # Recreate both layered generators from their actual primary inputs.
    replay = root / 'build/validation/context-commit-generation-replay'
    paths = ['tools/generate_registered_rx_grant_experiment.py', 'tools/generate_context_commit_guard_experiment.py',
             'rtl/http2_enveloped_parser_core.v', 'rtl/http2_connection_ingress.v',
             'rtl/http2_controlled_hpack_ingress.v', 'rtl/http2_classified_parser_transport.v',
             'rtl/http2_enveloped_frame_grants.v', 'rtl/http2_owned_pipelined_cancel_windows.v',
             'rtl/http2_pipelined_cancel_window_store.v']
    paths += ['build/experiments/checked-close-address/rtl/' + n for n in
              ('grpc_response_headers.v', 'rpc_grpc_http2_return.v', 'rpc_http2_response_partition.v')]
    for n in paths:
        p = replay / n; p.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(root / n, p)
    for script in paths[:2]:
        subprocess.run([sys.executable, str(replay / script)], check=True, capture_output=True, text=True)
    if args.registered_envelope_scope:
        script = 'tools/generate_registered_envelope_scope_experiment.py'
        shutil.copy2(source / script, replay / script)
        assert sha(source / script) == sha(root / script)
        subprocess.run([sys.executable, str(replay / script)], check=True, capture_output=True, text=True)
    for n, h in overrides.items():
        assert sha(replay / 'build/experiments' / experiment / n) == h
        assert sha(source / n) == h

    top = 'http2_enveloped_parser_application'; part = 'xcau15p-ffvb676-2-e'
    native = dict(run=args.native_run, phase='not_yet_verified', routed=False, timing_met=False)
    folder = root / 'build/implementation' / part / args.native_run
    log = root / ('build/' + args.native_run + '-implementation.log')
    if (folder / 'source-provenance.json').is_file():
        frozen = folder / 'sources'
        provenance = json.loads((folder / 'source-provenance.json').read_text())
        for n, data in provenance['files'].items(): assert sha(frozen / n) == data['sha256'], n
        dag = closure(top, frozen); assert len(dag) == 68
        for p in dag.values():
            n = p.relative_to(frozen).as_posix()
            assert sha(p) == overrides.get(n, sha(root / n)), n
        exceptions = [s.strip() for s in (frozen / 'scripts/implement_registered_subsystem.tcl').read_text().splitlines() if s.strip().startswith('set_false_path')]
        assert exceptions == ['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]', 'set_false_path -to [all_outputs]']
        log_bytes = log.read_bytes(); log_text = log_bytes.decode()
        captured = root / 'build/validation/native-log-snapshots' / hashlib.sha256(log_bytes).hexdigest()
        captured.parent.mkdir(parents=True, exist_ok=True)
        if captured.exists(): assert captured.read_bytes() == log_bytes
        else: captured.write_bytes(log_bytes)
        native.update(phase='native_sources_frozen_not_completed', exact_parser_modules_verified=68,
            source_provenance_sha256=sha(folder / 'source-provenance.json'), captured_log=str(captured),
            synthesis_license_observed="Got license for feature 'Synthesis' and/or device 'xcau15p'" in log_text)
        routed = f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART={part}' in log_text
        synthesized = 'synth_design completed successfully' in log_text and 'Command: opt_design' in log_text
        if routed or synthesized:
            assert '0 Critical Warnings and 0 Errors encountered.' in log_text
            suffix = 'routed' if routed else 'synthesis'
            area = resources(folder / (suffix + '_utilization.rpt'))
            clocks = timing(folder / (suffix + '_timing.rpt'))
            row = next(s for s in (folder / (suffix + '_utilization.rpt')).read_text().splitlines() if re.match(r'\|\s*' + top + r'_timing_harness\s*\|', s))
            cells = [s.strip() for s in row.split('|')[1:-1]]
            total = dict(luts=int(cells[2]), registers=int(cells[6]), bram36=int(cells[7]), bram18=int(cells[8]), uram=int(cells[9]), dsps=int(cells[10]))
            assert total['luts'] <= 77760 and total['registers'] <= 155520 and total['uram'] == 0
            assert total['bram36'] + total['bram18'] / 2 <= 144 and total['dsps'] <= 576
            checkpoint = folder / ('routed.dcp' if routed else 'synthesized.dcp')
            with ZipFile(checkpoint) as package: metadata_xml = package.read('dcp.xml')
            metadata = {n.tag: n.attrib.get('Name') for n in ET.fromstring(metadata_xml)}
            assert metadata['Part'] == part and metadata['Top'] == top + '_timing_harness' and metadata['OutOfContext'] == '1'
            reports = ['source-provenance.json', suffix + '_timing.rpt', suffix + '_utilization.rpt']
            if routed:
                assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (folder / 'route_status.rpt').read_text())
                assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|', (folder / 'routed_drc.rpt').read_text(), re.M)
                reports += ['route_status.rpt', 'routed_drc.rpt']
            native.update(phase='native_route_verified' if routed else 'native_synthesis_verified', routed=routed,
                resources=area, total_harness_resources=total, timing=clocks, checkpoint_metadata=metadata,
                checkpoint_sha256=sha(checkpoint), reports_sha256={n: sha(folder / n) for n in reports},
                native_resource_capacity_verified=True, package_paths_excluded=True,
                timing_met=routed and clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0)
    result = dict(phase='isolated_registered_envelope_scope_verified' if args.registered_envelope_scope else 'isolated_context_commit_guard_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        actual_axis_withdrawal_counterexample_verified=True, actual_torn_context_counterexample_verified=True,
        exact_parser_modules_verified=68, exact_tokenizer_modules_verified=22,
        override_sha256=overrides, baseline_audit_sha256=sha(baseline_file),
        executions=records, generator_replay_verified=True,
        direct_native_calls_verified=True, direct_return_metadata_faults_verified=True,
        direct_shutdown_faults_verified=bool(args.shutdown_faults),
        direct_concurrent_context_write_faults_verified=bool(args.duplex_faults),
        direct_full_rpc_matrix_verified=bool(args.rpc),
        actual_saved_scope_projection_equivalence=scope_proof,
        receive_credit_starvation_counterexample_verified=bool(args.receive_counterexample),
        receive_flow_control_verified=False,
        production_rtl_unchanged=True, full_native_corpus_on_variant_verified=corpus is not None,
        independent_native_corpus_reference=corpus,
        native=native, native_routed_timing_verified=native['timing_met'], physical_interfaces_verified=False, full_system_complete=False,
        verifier_sha256=sha(Path(__file__)), corpus_reference_verifier_sha256=sha(root / 'tools/verify_native_grpc_corpus_reference.py'))
    payload = json.dumps(result, sort_keys=True).encode()
    key = hashlib.sha256(payload).hexdigest()[:16]
    folder = root / 'build/validation' / (experiment + '-evidence') / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    shutil.copy2(root / 'tools/verify_native_grpc_corpus_reference.py', folder / 'verify_native_grpc_corpus_reference.py')
    result['evidence_folder'] = str(folder)
    (root / 'build/validation' / (experiment + '-experiment.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, concurrent_faults=bool(args.duplex_faults),
        shutdown_faults=bool(args.shutdown_faults), full_system_complete=False)))


if __name__ == '__main__': main()
