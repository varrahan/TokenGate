"""Audit the real Tokenizer/fabric route and full two-FPGA snapshot execution."""
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
    parser.add_argument('--native-run', default='tokenizer_fpga_scu35_memory_fabric_initial')
    parser.add_argument('--snapshot-name', default='tokenizer_memory_fabric_initial')
    parser.add_argument('--native-only', action='store_true')
    args = parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', value) for value in (args.native_run, args.snapshot_name))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    native = root / 'build/implementation/xcsu35p-sbvb625-2-e' / args.native_run
    source_root = native / 'sources'
    dependencies = closure('tokenizer_fpga_memory_subsystem', source_root)
    assert {'tokenizer_fpga_application', 'bpe_tokenizer_engine', 'detokenizer_engine', 'inverse_tokenizer_partition',
            'external_memory_fabric', 'external_memory_arbiter', 'external_memory_cache', 'programmable_table_ram'} <= dependencies.keys()
    assert 'http2_frame_reader' not in dependencies and 'proto_json_serializer' not in dependencies
    provenance = json.loads((native / 'source-provenance.json').read_text())
    for name, record in provenance['files'].items():
        path = source_root / name
        assert path.stat().st_size == record['bytes'] and sha(path) == record['sha256'], ('Native frozen input changed', name)
    for path in set(dependencies.values()):
        assert path.relative_to(source_root).as_posix() in provenance['files']
    harness = (source_root / 'timing_harness.v').read_text()
    assert re.search(r'\btokenizer_fpga_memory_subsystem\s+#\s*\(', harness)
    implementation = (source_root / 'scripts/implement_registered_subsystem.tcl').read_text()
    exceptions = [line.strip() for line in implementation.splitlines() if line.strip().startswith('set_false_path')]
    assert exceptions == ['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]',
                          'set_false_path -to [all_outputs]'], ('Unexpected timing exceptions', exceptions)
    log = root / f'build/{args.native_run}-implementation.log'
    text = log.read_text()
    assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP=tokenizer_fpga_memory_subsystem PART=xcsu35p-sbvb625-2-e' in text
    assert '0 Critical Warnings and 0 Errors encountered.' in text
    assert 'Found timing loop' not in text and 'ERROR: [Synth' not in text
    assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (native / 'route_status.rpt').read_text())
    measured = resources(native / 'routed_utilization.rpt')
    clocks = timing(native / 'routed_timing.rpt')
    assert measured['bram36'] or measured['bram18'], 'Native integrated cache must contain real block RAM'
    assert measured['uram'] == 0
    lut_fit = measured['luts'] <= 16320
    bram_fit = measured['bram36'] + measured['bram18'] / 2 <= 48
    assert lut_fit and bram_fit, ('Integrated Tokenizer exceeds SCU35 capacity', measured)
    met = clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0
    drc = (native / 'routed_drc.rpt').read_text()
    drc_rows = re.findall(r'^\|\s*([\w-]+)\s*\|\s*(Warning|Error|Critical Warning|Advisory)\s*\|[^\n]*?\|\s*(\d+)\s*\|', drc, re.M)
    checks = [dict(rule=rule, severity=severity, checks=int(count)) for rule, severity, count in drc_rows]
    assert sum(c['checks'] for c in checks) == int(re.search(r'Checks found:\s*(\d+)', drc)[1])
    assert not any(c['severity'] in ('Error', 'Critical Warning') for c in checks)
    current_rtl_changes = [path.relative_to(source_root).as_posix() for path in set(dependencies.values())
                           if not (root / path.relative_to(source_root)).is_file() or sha(root / path.relative_to(source_root)) != sha(path)]
    result = dict(phase='native_tokenizer_memory_timing_met' if met else 'native_tokenizer_memory_timing_pending',
        verified_utc=datetime.now(timezone.utc).isoformat(), top='tokenizer_fpga_memory_subsystem', part='xcsu35p-sbvb625-2-e',
        native_run=args.native_run, native_exact_rtl_files=len(set(dependencies.values())), exact_rtl_modules=list(dependencies),
        native_source_provenance_sha256=sha(native / 'source-provenance.json'), routed_checkpoint_sha256=sha(native / 'routed.dcp'),
        verifier_sha256=sha(Path(__file__)), native_report_sha256={name: sha(native / name) for name in
            ('routed_utilization.rpt', 'routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt')},
        resources=measured, timing=clocks, routed_timing_met=met, lut_fit=lut_fit, bram_fit=bram_fit,
        reported_drc_checks=checks, native_memory_fabric_included=True, native_memory_clients=9,
        current_primary_rtl_differences=current_rtl_changes, package_paths_excluded=True,
        physical_memory_controller_verified=False, pcie_adapter_verified=False, physical_link_verified=False,
        distributed_image_leases_verified=False, full_http2_transport_verified=False,
        sustained_throughput_verified=False, full_system_complete=False)
    if args.native_only:
        output = root / 'build/validation/tokenizer-fpga-memory-native.json'
    else:
        reports = root / 'build/wsl-reports' / ('cocotb_two_fpga_memory_' + args.snapshot_name)
        executed = reports / 'execution-sources'
        report = json.loads((reports / 'report.json').read_text())
        acceptance = json.loads((reports / 'acceptance.json').read_text())
        snapshot = json.loads((reports / 'snapshot.json').read_text())
        assert snapshot['phase'] == 'snapshot_run_archived' and snapshot['runner_exit_code'] == 0
        assert snapshot['execution_report_sha256'] == sha(reports / 'report.json')
        assert snapshot['source_and_fixture_sha256']['build/bidirectional-reference-validation.json'] == sha(reports / 'native-reference.json')
        assert snapshot['snapshot_runner_sha256'] == sha(executed / 'scripts/run_cocotb_snapshot.py')
        assert report['suite'] == 'two_fpga_memory' and report['phase'] == acceptance['phase'] == 'passed'
        assert report['tests'] == 1 and report['failures'] == 0 and not report.get('changed_inputs')
        assert report['acceptance_sha256'] == sha(reports / 'acceptance.json')
        xml = ET.parse(reports / 'results.xml')
        cases = xml.findall('.//testcase')
        assert len(cases) == 1 and cases[0].attrib['name'] == 'tokenizer_memory_raw_requests_and_actual_dma_returns'
        assert not xml.findall('.//failure') and not xml.findall('.//error')
        for name, digest in {**report['source_sha256'], **report['fixture_sha256']}.items():
            assert snapshot['source_and_fixture_sha256'][name] == digest
            assert sha(executed / name) == digest, ('Executed source changed', name)
            if name.startswith('rtl/'):
                assert sha(source_root / name) == digest, ('Native/simulation RTL differs', name)
        assert all(report['source_sha256'][path.relative_to(source_root).as_posix()] == sha(path)
                   for path in set(dependencies.values()))
        assert (acceptance['packets'], acceptance['headers'], acceptance['messages'], acceptance['token_ids'],
                acceptance['response_chunks'], acceptance['response_bytes']) == (38, 21, 16, 2828, 2828, 144686)
        assert (acceptance['packet_aborts'], acceptance['connection_opens'], acceptance['memory_faults'],
                acceptance['response_rejections'], acceptance['response_memory_faults']) == (4, 7, 2, 4, 1)
        assert acceptance['tokenizer_memory_fabric_integrated'] and acceptance['separate_memory_banks_verified']
        assert acceptance['full_model_bytes'] == 8388608 and acceptance['model_and_policy_immutable']
        assert acceptance['mid_packet_gpu_admissions'] and acceptance['continued_rx_beats']
        oracle = json.loads((reports / 'native-reference.json').read_text())
        assert oracle['phase'] == 'passed' and oracle['native_token_ids'] == 2828 and oracle['complete_model_prefix_matches_image']
        oracle_verifier = executed / 'tools/verify_http2_prefill_references.py'
        assert snapshot['source_and_fixture_sha256']['tools/verify_http2_prefill_references.py'] == sha(oracle_verifier)
        assert oracle['verifier_sha256'] == sha(oracle_verifier), 'Native oracle verifier changed'
        for name, digest in report['fixture_sha256'].items():
            assert oracle['fixture_sha256'][Path(name).name] == digest
        key = hashlib.sha256((sha(reports / 'report.json') + sha(native / 'source-provenance.json') + sha(Path(__file__))).encode()).hexdigest()[:16]
        evidence = root / 'build/validation/tokenizer-fpga-memory-evidence' / key
        files = {Path('execution') / name: executed / name for name in {**report['source_sha256'], **report['fixture_sha256']}}
        files.update({Path('reports') / name: reports / name for name in ('report.json', 'acceptance.json', 'results.xml', 'simulation.log', 'build.log', 'snapshot.json', 'native-reference.json')})
        for name in ('source-provenance.json', 'routed_utilization.rpt', 'routed_timing.rpt', 'route_status.rpt', 'routed_drc.rpt'):
            files[Path('native') / name] = native / name
        files[Path('native/implementation.log')] = log
        files[Path('verification/verify_http2_prefill_references.py')] = oracle_verifier
        files[Path('verification/run_cocotb_snapshot.py')] = executed / 'scripts/run_cocotb_snapshot.py'
        files[Path('verification/verify_tokenizer_fpga_memory.py')] = Path(__file__)
        for path in set(dependencies.values()):
            files[Path('native/sources') / path.relative_to(source_root)] = path
        for name in provenance['files']:
            if not name.startswith('rtl/'):
                files[Path('native/sources') / name] = source_root / name
        for name, source in files.items():
            target = evidence / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                assert sha(target) == sha(source), ('Immutable evidence differs', name)
            else:
                shutil.copy2(source, target)
        result.update(phase='functional_passed_tokenizer_memory_timing_met' if met else 'functional_passed_tokenizer_memory_timing_pending',
            functional_acceptance_verified=True, acceptance=acceptance, sources_verified=len(report['source_sha256']),
            fixtures_verified=len(report['fixture_sha256']), evidence_folder=str(evidence),
            execution_archive_primary_differences=snapshot['current_primary_changed_inputs'],
            execution_current_primary_differences=[name for name,digest in {**report['source_sha256'],**report['fixture_sha256']}.items()
                if not (root/name).is_file() or sha(root/name)!=digest], verifier_sha256=sha(Path(__file__)))
        output = root / 'build/validation/tokenizer-fpga-memory.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
