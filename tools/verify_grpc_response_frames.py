"""Bind actual gRPC DATA-framer execution, native references and routed RTL."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure, resources, timing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-name', default='response_frames_partial_credit')
    parser.add_argument('--native-run', default='grpc_response_frames_scu35_partial_credit')
    parser.add_argument('--functional-only', action='store_true')
    args = parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', name) for name in (args.snapshot_name, args.native_run))
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    archive = root / 'build/wsl-reports' / ('grpc_response_frames_' + args.snapshot_name)
    executed = archive / 'execution-sources'
    inputs = json.loads((archive / 'inputs.json').read_text())
    report = json.loads((archive / 'report.json').read_text())
    acceptance = json.loads((archive / 'acceptance.json').read_text())
    snapshot = json.loads((archive / 'snapshot.json').read_text())
    assert snapshot['exit_code'] == 0 and report['phase'] == acceptance['phase'] == 'passed'
    assert report['tests'] == 1 and report['failures'] == 0 and report['input_sha256'] == inputs
    for name, digest in inputs.items():
        assert sha(executed / name) == digest, ('Executed input changed', name)
    assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    cases = ET.parse(archive / 'results.xml')
    tests = cases.findall('.//testcase')
    assert len(tests) == 1 and tests[0].attrib['name'] == 'records_frames_credit_and_transactional_rejection'
    assert not cases.findall('.//failure') and not cases.findall('.//error')
    fixture = executed / 'build/grpc-response-frame-fixtures/cases.json'
    reference = json.loads(fixture.read_text())
    assert acceptance['native_reference_sha256'] == sha(fixture)
    assert reference['phase'] == 'native_references_passed' and reference['native_oracle'] == 'hyperframe'
    assert reference['generator_sha256'] == sha(executed / 'tools/generate_grpc_response_frame_vectors.py')
    assert (acceptance['cases'], acceptance['valid_cases'], acceptance['rejected_cases'], acceptance['frames']) == (42, 33, 9, 84)
    assert reference['capacity'] == 65535 and reference['native_frames'] == acceptance['frames']
    assert {0, 16378, 16379, 16380, 65535, 65536} <= {len(bytes.fromhex(c['payload'])) for c in reference['cases']}
    assert any(c['status'] == 0 and 1 in c['grant_values'] and len(c['frames']) > 1 for c in reference['cases'])
    assert any(c['status'] == 5 and c['frames'] for c in reference['cases']), 'Missing post-prefix grant-contract failure'
    assert all(acceptance[name] > 0 for name in ('input_stalls', 'output_stalls', 'credit_stalls', 'result_stalls'))
    result = dict(phase='functional_passed_native_pending', verified_utc=datetime.now(timezone.utc).isoformat(),
        top='grpc_http2_response_framer', acceptance=acceptance, execution_inputs_verified=len(inputs),
        input_sha256=inputs, verifier_sha256=sha(Path(__file__)),
        current_primary_differences=[name for name, digest in inputs.items()
            if not (root / name).is_file() or sha(root / name) != digest],
        serializer_rpc_integration_verified=False, response_headers_trailers_verified=False,
        credit_ledger_verified=False, full_http2_transport_verified=False, full_system_complete=False)
    files = {Path('execution') / name: executed / name for name in inputs}
    for name in ('inputs.json', 'report.json', 'results.xml', 'acceptance.json', 'snapshot.json', 'simulation.log', 'build.log'):
        files[Path('reports') / name] = archive / name
    native = root / 'build/implementation/xcsu35p-sbvb625-2-e' / args.native_run
    if not args.functional_only:
        sources = native / 'sources'
        dependencies = closure('grpc_http2_response_framer', sources)
        assert set(dependencies) == {'grpc_http2_response_framer', 'axis_byte_packer', 'axis_byte_unpacker'}
        provenance = json.loads((native / 'source-provenance.json').read_text())
        for name, record in provenance['files'].items():
            assert sha(sources / name) == record['sha256']
        implementation = (sources / 'scripts/implement_registered_subsystem.tcl').read_text()
        assert [line.strip() for line in implementation.splitlines() if line.strip().startswith('set_false_path')] == [
            'set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]', 'set_false_path -to [all_outputs]']
        for path in dependencies.values():
            name = path.relative_to(sources).as_posix()
            assert sha(path) == inputs[name]
            files[Path('native/sources') / name] = path
        for name in provenance['files']:
            if not name.startswith('rtl/'):
                files[Path('native/sources') / name] = sources / name
        native_log = root / ('build/' + args.native_run + '-implementation.log')
        text = native_log.read_text()
        assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=grpc_http2_response_framer PART=xcsu35p-sbvb625-2-e' in text
        assert '0 Critical Warnings and 0 Errors encountered.' in text and 'ERROR: [Synth' not in text
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (native / 'route_status.rpt').read_text())
        clocks = timing(native / 'routed_timing.rpt')
        measured = resources(native / 'routed_utilization.rpt')
        assert 0 < measured['bram36'] + measured['bram18'] / 2 <= 48 and measured['luts'] <= 16320
        assert measured['uram'] == measured['dsps'] == 0
        drc = (native / 'routed_drc.rpt').read_text()
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|', drc, re.M)
        met = clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0
        result.update(phase='functional_passed_native_timing_met' if met else 'functional_passed_native_timing_pending',
            native_run=args.native_run, part='xcsu35p-sbvb625-2-e', routed_timing_met=met, timing=clocks, resources=measured,
            package_paths_excluded=True, routed_checkpoint_sha256=sha(native / 'routed.dcp'),
            drc_checks=int(re.search(r'Checks found:\s*(\d+)', drc)[1]))
        files[Path('native/implementation.log')] = native_log
        for name in ('source-provenance.json', 'routed_utilization.rpt', 'routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt'):
            files[Path('native') / name] = native / name
    files[Path('verification/verify_grpc_response_frames.py')] = Path(__file__)
    key = hashlib.sha256((sha(archive / 'report.json') + sha(Path(__file__)) +
                         ('functional-only' if args.functional_only else sha(native / 'source-provenance.json'))).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/grpc-response-frame-evidence' / key
    for name, source in files.items():
        target = evidence / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert sha(target) == sha(source), ('Immutable evidence changed', name)
        else:
            shutil.copy2(source, target)
    result['evidence_folder'] = str(evidence)
    output = root / 'build/validation/grpc-response-frames.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
