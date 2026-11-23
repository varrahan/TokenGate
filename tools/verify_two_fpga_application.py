"""Bind separate application acceptance to the real per-device RTL closures."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from generate_two_fpga_application import balanced


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def closure(top, source_root=ROOT):
    modules = {}
    for path in (source_root / 'rtl').glob('*.v'):
        source = re.sub(r'//[^\n]*|/\*.*?\*/', '', path.read_text(), flags=re.S)
        for name in re.findall(r'\bmodule\s+(\w+)', source):
            assert name not in modules, ('Duplicate module', name)
            modules[name] = (path, source)
    visited = set()
    pending = [top]
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        _, source = modules[name]
        for child in modules:
            found = bool(re.search(r'\b' + child + r'\s+\w+\s*\(', source))
            if not found:
                for match in re.finditer(r'\b' + child + r'\s*#\s*\(', source):
                    end = balanced(source, source.index('(', match.start()))
                    if re.match(r'\s*\w+\s*\(', source[end + 1:]):
                        found = True
                        break
            if found and child not in visited:
                pending.append(child)
    return {name: modules[name][0] for name in sorted(visited)}


def resources(path):
    row = next(line for line in path.read_text().splitlines() if re.match(r'\|\s+core\s+\|', line))
    cells = [c.strip() for c in row.split('|')[1:-1]]
    return dict(luts=int(cells[2]), registers=int(cells[6]), bram36=int(cells[7]),
                bram18=int(cells[8]), uram=int(cells[9]), dsps=int(cells[10]))


def timing(path):
    source = path.read_text()
    match = re.search(r'WNS\(ns\).*?\n[-\s]+\n\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)', source, re.S)
    assert match, path
    assert re.search(r'checking no_clock \(0\)', source)
    assert re.search(r'checking unconstrained_internal_endpoints \(0\)', source)
    assert re.search(r'checking loops \(0\)', source)
    assert re.search(r'^axis_clk\s+\{0\.000\s+2\.000\}\s+4\.000\s+250\.000', source, re.M)
    return dict(setup_wns_ns=float(match[1]), hold_whs_ns=float(match[5]),
                setup_failing_endpoints=int(match[3]), hold_failing_endpoints=int(match[7]))


def inspect_native(label, top, part, run, available_luts):
    folder = ROOT / 'build/implementation' / part / run
    provenance = json.loads((folder / 'source-provenance.json').read_text())
    dependencies = closure(top)
    if label == 'parser':
        assert {'http2_parser_transport_partition', 'rpc_response_parser_partition',
                'utf8_serialized_chunk', 'proto_json_serializer'} <= dependencies.keys()
        assert not ({'bpe_tokenizer_engine', 'detokenizer_engine', 'token_packager'} & dependencies.keys())
    else:
        assert {'bpe_tokenizer_engine', 'detokenizer_engine', 'token_packager', 'inverse_tokenizer_partition'} <= dependencies.keys()
        assert not ({'utf8_serialized_chunk', 'proto_json_serializer', 'grpc_stream_store', 'http2_frame_reader'} & dependencies.keys())
    for path in set(dependencies.values()):
        name = path.relative_to(ROOT).as_posix()
        assert sha(path) == sha(folder / 'sources' / name) == provenance['files'][name]['sha256'], (label, name)
    logs = [ROOT / f'build/{run}-implementation.log', ROOT / f'build/{run}-route-resume.log']
    logs = [p for p in logs if p.is_file()]
    text = '\n'.join(p.read_text() for p in logs)
    assert '0 Critical Warnings and 0 Errors encountered.' in text
    assert 'Found timing loop' not in text and 'ERROR: [Synth' not in text
    routed = (folder / 'routed_timing.rpt').is_file()
    suffix = 'routed' if routed else 'synthesis'
    assert f'REGISTERED_SUBSYSTEM_{"ROUTE" if routed else "SYNTHESIS"}_COMPLETE TOP={top} PART={part}' in text
    measured = resources(folder / (suffix + '_utilization.rpt'))
    clocks = timing(folder / (suffix + '_timing.rpt'))
    assert measured['luts'] <= available_luts, (label, 'over capacity', measured)
    files = {Path('native') / label / p.name: p for p in logs}
    for name in ('source-provenance.json', suffix + '_utilization.rpt', suffix + '_timing.rpt'):
        files[Path('native') / label / name] = folder / name
    if routed:
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (folder / 'route_status.rpt').read_text())
        drc_text = (folder / 'routed_drc.rpt').read_text()
        drc_rows = re.findall(r'^\|\s*([\w-]+)\s*\|\s*(Warning|Error|Critical Warning|Advisory)\s*\|[^\n]*?\|\s*(\d+)\s*\|', drc_text, re.M)
        drc_checks = [dict(rule=rule, severity=severity, checks=int(count)) for rule, severity, count in drc_rows]
        declared = int(re.search(r'Checks found:\s*(\d+)', drc_text)[1])
        assert sum(row['checks'] for row in drc_checks) == declared
        assert not any(row['severity'] in ('Error', 'Critical Warning') for row in drc_checks)
        for name in ('route_status.rpt', 'routed_drc.rpt'):
            files[Path('native') / label / name] = folder / name
    for path in set(dependencies.values()):
        relative = path.relative_to(ROOT)
        files[Path('native') / label / 'sources' / relative] = folder / 'sources' / relative
    result = dict(top=top, part=part, native_run=run, resources=measured, available_luts=available_luts,
        native_lut_fit=True, routed=routed, timing=clocks,
        routed_timing_met=routed and clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0
            and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0,
        exact_rtl_modules_verified=list(dependencies), exact_rtl_files_verified=len(set(dependencies.values())),
        dependency_files_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in set(dependencies.values())},
        source_provenance_sha256=sha(folder / 'source-provenance.json'),
        checkpoint_sha256=sha(folder / ('routed.dcp' if routed else 'synthesized.dcp')),
        includes_local_memory_fabric=False, physical_io_and_clock_crossing_verified=False)
    if routed:
        result['reported_drc_checks'] = drc_checks
    refinement = folder / 'sources/refinement-base.txt'
    if refinement.is_file():
        record = dict(line.split('=', 1) for line in refinement.read_text().splitlines())
        assert record['rtl_changed'] == record['clock_changed'] == '0'
        original = folder.parent / record['base_run'] / 'routed.dcp'
        result['refined_from'] = dict(native_run=record['base_run'], routed_checkpoint_sha256=sha(original))
        files[Path('native') / label / 'refinement-base.txt'] = refinement
        files[Path('native') / label / 'refine_registered_route.tcl'] = folder / 'sources/scripts/refine_registered_route.tcl'
    return result, files


def inspect_blocked_parser(run, crash_log):
    """Record actual missing native evidence; never turn a failed run into fit."""
    part = 'xcau15p-ffvb676-2-e'
    folder = ROOT / 'build/implementation' / part / run
    top = 'http2_parser_fpga_application'
    dependencies = closure(top)
    assert 'bpe_tokenizer_engine' not in dependencies and 'proto_json_serializer' in dependencies
    provenance = json.loads((folder / 'source-provenance.json').read_text())
    files = {}
    for path in set(dependencies.values()):
        relative = path.relative_to(ROOT)
        assert sha(path) == sha(folder / 'sources' / relative) == provenance['files'][relative.as_posix()]['sha256']
        files[Path('native/parser/sources') / relative] = folder / 'sources' / relative
    log = ROOT / f'build/{run}-implementation.log'
    text = log.read_text()
    assert 'Synthesis finished with 0 errors, 0 critical warnings' in text
    assert 'Finished Parsing XDC File' in text and 'REGISTERED_SUBSYSTEM_SYNTHESIS_COMPLETE' not in text
    assert not (folder / 'synthesized.dcp').exists() and not (folder / 'routed.dcp').exists()
    events_file = ROOT / 'build/validation/au15p-code-integrity-events.json'
    events = json.loads(events_file.read_text(encoding='utf-8-sig'))
    if isinstance(events, dict):
        events = [events]
    assert any(event['Id'] == 3077 and 'kintexuplus.dll' in event['Message'] and
               'Enterprise signing level requirements' in event['Message'] for event in events)
    crash = ROOT / crash_log
    assert 'EXCEPTION_ACCESS_VIOLATION' in crash.read_text()
    library = Path('C:/AMDDesignTools/2025.2/Vivado/lib/win64.o/veam/kintexuplus/kintexuplus.dll')
    for source in (log, crash, folder / 'source-provenance.json', events_file):
        files[Path('native/parser') / source.name] = source
    result = dict(top=top, part=part, native_run=run, phase='blocked_by_windows_code_integrity',
        resources=None, native_lut_fit=None, routed=False, routed_timing_met=False,
        blocked_library=str(library), blocked_library_sha256=sha(library),
        code_integrity_event_ids=[3077], code_integrity_evidence_sha256=sha(events_file),
        source_provenance_sha256=sha(folder / 'source-provenance.json'),
        exact_rtl_modules_verified=list(dependencies), exact_rtl_files_verified=len(set(dependencies.values())),
        dependency_files_sha256={p.relative_to(ROOT).as_posix(): sha(p) for p in set(dependencies.values())},
        includes_local_memory_fabric=False, physical_io_and_clock_crossing_verified=False)
    return result, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--parser-run', default='parser_fpga_au15p_logical_partition_tx_witness')
    parser.add_argument('--tokenizer-run', default='tokenizer_fpga_scu35_logical_partition_initial')
    parser.add_argument('--record-parser-code-integrity-block', action='store_true')
    parser.add_argument('--parser-crash-log', default='hs_err_pid21880.log')
    args = parser.parse_args()
    if args.record_parser_code_integrity_block:
        p, files = inspect_blocked_parser(args.parser_run, args.parser_crash_log)
    else:
        p, files = inspect_native('parser', 'http2_parser_fpga_application', 'xcau15p-ffvb676-2-e', args.parser_run, 77760)
    t, token_files = inspect_native('tokenizer', 'tokenizer_fpga_application', 'xcsu35p-sbvb625-2-e', args.tokenizer_run, 16320)
    files.update(token_files)
    generated_file = ROOT / 'build/validation/two-fpga-generated.json'
    generated = json.loads(generated_file.read_text())
    assert generated['generator_sha256'] == sha(ROOT / 'tools/generate_two_fpga_application.py')
    for name, digest in {**generated['source_sha256'], **generated['generated_sha256']}.items():
        assert sha(ROOT / name) == digest, ('Generated partition changed', name)
    assert generated['parser_memory_clients_original'] == [*range(5), *range(13, 21)]
    assert generated['tokenizer_memory_clients_original'] == [*range(5, 13), 21]
    native = dict(parser=p, tokenizer=t)
    result = dict(phase='native_application_partitions_verified', verified_utc=datetime.now(timezone.utc).isoformat(),
        native=native, separate_physical_devices_verified=False, physical_link_implemented=False,
        independent_clock_domains_verified=False, distributed_image_leases_verified=False,
        response_transport_framing_verified=False, complete_http2_transport_verified=False,
        full_system_fit_verified=False, full_system_complete=False)
    if args.native_only:
        if args.record_parser_code_integrity_block:
            result['phase'] = 'tokenizer_native_verified_parser_implementation_blocked'
        output = ROOT / 'build/validation/two-fpga-native.json'
    else:
        reports = ROOT / 'build/wsl-reports/cocotb_two_fpga'
        report = json.loads((reports / 'report.json').read_text())
        acceptance = json.loads((reports / 'acceptance.json').read_text())
        assert report['suite'] == 'two_fpga' and report['phase'] == acceptance['phase'] == 'passed'
        assert report['tests'] == 1 and report['failures'] == 0 and not report.get('changed_inputs')
        assert report['acceptance_sha256'] == sha(reports / 'acceptance.json')
        xml = ET.parse(reports / 'results.xml')
        assert len(xml.findall('.//testcase')) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        assert xml.find('.//testcase').attrib['name'] == 'separate_fpgas_raw_requests_and_actual_dma_returns'
        for name, digest in {**report['source_sha256'], **report['fixture_sha256']}.items():
            assert sha(ROOT / name) == digest, ('Execution input changed', name)
            files[Path(name)] = ROOT / name
        assert len(report['fixture_sha256']) == 7
        assert (acceptance['packets'], acceptance['headers'], acceptance['messages'], acceptance['token_ids'],
                acceptance['response_chunks'], acceptance['response_bytes']) == (38, 21, 16, 2828, 2828, 144686)
        assert (acceptance['packet_aborts'], acceptance['connection_opens'], acceptance['memory_faults'],
                acceptance['response_rejections'], acceptance['response_memory_faults']) == (4, 7, 2, 4, 1)
        assert acceptance['separate_parser_and_tokenizer_applications_verified'] and acceptance['separate_memory_banks_verified']
        assert (acceptance['parser_memory_clients'], acceptance['tokenizer_memory_clients']) == (13, 9)
        assert all(acceptance[n] for n in ('parser_axi_refills', 'parser_axi_writes', 'tokenizer_axi_refills',
            'tokenizer_axi_writes', 'mid_packet_gpu_admissions', 'continued_rx_beats', 'registered_schedule_owned_cycles'))
        assert acceptance['full_model_bytes'] == 8388608 and acceptance['model_and_policy_immutable']
        assert not acceptance['physical_link_implemented'] and not acceptance['full_system_complete']
        oracle_file = ROOT / 'build/bidirectional-reference-validation.json'
        oracle = json.loads(oracle_file.read_text())
        assert oracle['phase'] == 'passed' and oracle['native_token_ids'] == 2828 and oracle['complete_model_prefix_matches_image']
        assert oracle['verifier_sha256'] == sha(ROOT / 'tools/verify_http2_prefill_references.py')
        assert oracle['model_image_sha256'] == sha(ROOT / 'build/scu35/image/external_memory.bin')
        for name, digest in report['fixture_sha256'].items():
            if Path(name).name != 'response_reference.json':
                assert oracle['fixture_sha256'][Path(name).name] == digest
        files[Path('native-reference.json')] = oracle_file
        for name in ('report.json', 'acceptance.json', 'results.xml', 'simulation.log', 'build.log'):
            files[Path('reports') / name] = reports / name
        files[Path('partition-generation.json')] = generated_file
        files[Path('verification/verify_two_fpga_application.py')] = Path(__file__)
        key = hashlib.sha256((sha(reports / 'report.json') + p['source_provenance_sha256'] +
                              t['source_provenance_sha256'] + sha(Path(__file__))).encode()).hexdigest()[:16]
        evidence = ROOT / 'build/validation/two-fpga-application-evidence' / key
        for relative, source in files.items():
            target = evidence / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                assert sha(target) == sha(source), ('Immutable evidence differs', relative)
            else:
                shutil.copy2(source, target)
        result.update(phase='functional_passed_parser_implementation_blocked' if args.record_parser_code_integrity_block
                      else 'functional_passed_application_timing_met' if p['routed_timing_met'] and t['routed_timing_met']
                      else 'functional_passed_application_timing_pending',
            separate_application_acceptance_verified=True, separate_memory_banks_verified=True,
            sources_verified=len(report['source_sha256']), fixtures_verified=len(report['fixture_sha256']),
            acceptance=acceptance, evidence_folder=str(evidence), verifier_sha256=sha(Path(__file__)))
        output = ROOT / 'build/validation/two-fpga-application.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
