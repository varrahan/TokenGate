"""Bind the three-file arithmetic experiment to actual proof and RPC execution."""
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

from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports, rename
from verify_two_fpga_application import closure, resources, timing

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proof', default='checked_close_address_algebra')
    parser.add_argument('--rpc', default='checked_close_address_matrix')
    parser.add_argument('--raw', help='Require direct experimental raw/native-client/reset execution')
    parser.add_argument('--raw-return-faults', help='Require all 20 direct raw return-metadata fault phases')
    parser.add_argument('--raw-shutdown-faults', help='Require all 41 direct raw shutdown fault phases')
    parser.add_argument('--native-run', default='parser_au15p_checked_close_address')
    args = parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', n) for n in (args.proof, args.rpc, args.raw, args.raw_return_faults, args.raw_shutdown_faults, args.native_run) if n)
    root = Path(__file__).resolve().parents[1]; files = {}
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    def record(archive, prefix):
        inputs = json.loads((archive / 'inputs.json').read_text())
        report = json.loads((archive / 'report.json').read_text())
        snapshot = json.loads((archive / 'snapshot.json').read_text())
        assert report['phase'] == 'passed' and snapshot['exit_code'] == 0
        assert report['input_sha256'] == inputs
        source = archive / 'execution-sources'
        for n, h in inputs.items():
            assert sha(source / n) == h, n
            files[Path(prefix) / 'execution' / n] = source / n
        for n in ('inputs.json', 'report.json', 'snapshot.json'):
            files[Path(prefix) / 'reports' / n] = archive / n
        return source, inputs, report, snapshot
    previous_path = root / 'build/validation/registered-close-scope-experiment.json'
    previous = json.loads(previous_path.read_text())
    assert previous['phase'] == 'registered_close_scope_rpc_and_formal_verified'
    assert previous['verifier_sha256'] == sha(root / 'tools/verify_registered_close_scope_experiment.py')
    assert previous['raw_native_calls_and_reset_on_experiment_verified']
    assert previous['raw_shutdown_fault_matrix_on_experiment_verified'] and previous['raw_return_fault_matrix_on_experiment_verified']
    previous_source = Path(previous['evidence_folder']) / 'rpc/execution'
    previous_inputs = json.loads((Path(previous['evidence_folder']) / 'rpc/reports/inputs.json').read_text())
    files[Path('baseline/registered-close-scope-experiment.json')] = previous_path
    rpc = root / 'build/wsl-reports' / ('rpc_http2_' + args.rpc)
    source, inputs, report, snapshot = record(rpc, 'rpc')
    changed = ['rtl/grpc_response_headers.v', 'rtl/rpc_grpc_http2_return.v', 'rtl/rpc_http2_response_partition.v']
    assert sorted(snapshot['isolated_rtl_overrides']) == changed
    acceptance = json.loads((rpc / 'acceptance.json').read_text())
    assert report['tests'] == 1 and report['failures'] == 0
    assert acceptance == previous['rpc_acceptance'] and report['acceptance_sha256'] == sha(rpc / 'acceptance.json')
    xml = ET.parse(rpc / 'results.xml'); cases = xml.findall('.//testcase')
    assert len(cases) == 1 and cases[0].attrib['name'] == 'actual_rpc_native_client_headers_data_trailers_and_commit_faults'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    properties = {p.attrib['name']: p.attrib['value'] for p in cases[0].findall('properties/property')}
    assert properties['sim_time_unit'] == 'ns' and float(properties['sim_time_duration']) == previous['matrix_simulation_time_ns']
    dag = closure('rpc_grpc_http2_return', source); assert len(dag) == 20
    differences = []
    for p in dag.values():
        n = p.relative_to(source).as_posix()
        if inputs[n] != previous_inputs[n]: differences.append(n)
        if n not in changed: assert inputs[n] == sha(source_path(root, n)), n
    assert differences == ['rtl/rpc_http2_response_partition.v']
    for n, h in inputs.items():
        if n.startswith(('build/rpc-grpc-fixtures/', 'build/grpc-header-fixtures/', 'native-vendor/')):
            assert h == previous_inputs[n], n
    assert inputs['sim/cocotb/test_rpc_http2_return.py'] == previous_inputs['sim/cocotb/test_rpc_http2_return.py']
    for n in ('acceptance.json', 'simulation.log', 'build.log', 'results.xml'):
        files[Path('rpc/reports') / n] = rpc / n

    proof = root / 'build/wsl-reports' / ('rpc_backend_equivalence_' + args.proof)
    executed, proof_inputs, proof_report, _ = record(proof, 'formal')
    assert proof_inputs['rtl/gold_input.v'] == previous_inputs['rtl/rpc_http2_response_partition.v'] == sha(source_path(root, 'rtl/rpc_http2_response_partition.v'))
    assert proof_inputs['rtl/gate_input.v'] == inputs['rtl/rpc_http2_response_partition.v']
    assert proof_inputs['rtl/memory_command_slot.v'] == inputs['rtl/memory_command_slot.v']
    for n, h in proof_report['generated_sha256'].items(): assert sha(proof / n) == h, n
    spec = importlib.util.spec_from_file_location('frozen_backend_equivalence', executed / 'scripts/run_rpc_backend_equivalence.py')
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    original = (executed / 'rtl/gold_input.v').read_text(); gate = (executed / 'rtl/gate_input.v').read_text()
    public = ports(original, runner.TOP); assert public == ports(gate, runner.TOP)
    if proof_report['proof_engine'] == 'algebra':
        assert proof_report['actual_address_comparison_equivalence_verified']
        assert not proof_report['full_backend_public_output_equivalence_verified']
        assert not proof_report['unbounded_post_reset_public_output_equivalence']
        assert proof_report['memory_address_width'] == 23 and proof_report['yosys_exit_code'] == 0
        assert 'SAT proof finished - no model found: SUCCESS!' in (proof / 'yosys.log').read_text()
        assert 'assume(' not in (proof / 'miter.v').read_text()
        for n, text in runner.address_models(original, gate).items():
            assert text == (proof / n).read_text(), n
        for n in proof_report['generated_sha256']:
            files[Path('formal/reports') / n] = proof / n
    else:
        assert proof_report['unbounded_post_reset_public_output_equivalence'] and proof_report['actual_memory_command_slot_included']
        assert proof_report['memory_command_slot_observation_wires_only']
        assert proof_report['memory_address_width'] == 23 and proof_report['yosys_exit_code'] == 0
        if proof_report['proof_engine'] == 'sat':
            assert 'Induction step proven: SUCCESS!' in (proof / 'yosys.log').read_text()
        else:
            assert proof_report['proof_engine'] == 'smtbmc'
            assert proof_report['base_exit_code'] == proof_report['induction_exit_code'] == 0
            for label, extra in (('base', []), ('induction', ['-i'])):
                assert 'Status: PASSED' in (proof / (label + '.log')).read_text()
                assert proof_report['smtbmc_commands'][label] == ['yosys-smtbmc', '-s', 'z3', '-t', '6', '--noprogress', '--timeout', '60', *extra, 'model.smt2']
                files[Path('formal/reports') / (label + '.log')] = proof / (label + '.log')
            files[Path('formal/reports/model.smt2')] = proof / 'model.smt2'
        assert sum(d == 'output' for d, _, _ in public) == proof_report['actual_public_outputs'] == 72
        private = runner.private_registers(original, {n for _, _, n in public})
        assert private == runner.private_registers(gate, {n for _, _, n in public})
        assert sorted(private) == proof_report['actual_private_register_equality_lemmas']
        helpers = [('output', w, 'formal_' + n) for n, w in sorted(private.items())]
        helpers += [('output', '[63:0]', 'formal_bound'), ('output', '', 'formal_early_closed')]
        helpers += runner.SLOT_HELPERS
        for label, text, bound in (('gold', original, 'checked_stream_end'), ('gate', gate, 'checked_stream_last')):
            assignments = ['assign formal_' + n + '=' + n + ';' for n in sorted(private)]
            assignments += ['assign formal_bound=' + bound + ';', 'assign formal_early_closed=early_closed;']
            assignments += ['assign formal_slot_' + n + '=slot_' + n + ';' for n in ('data', 'status', 'ready', 'valid', 'idle')]
            observed = add_ports(text, runner.TOP, helpers).replace('metadata(\n', 'metadata(\n        .formal_state(formal_slot_state),\n')
            observed = observed.replace('endmodule', '\n'.join(assignments) + '\nendmodule')
            assert rename(observed, runner.TOP, 'backend_' + label) == (proof / (label + '.v')).read_text()
        observed_slot = add_ports((executed / 'rtl/memory_command_slot.v').read_text(), 'memory_command_slot', [('output', '[1:0]', 'formal_state')])
        observed_slot = observed_slot.replace('endmodule', 'assign formal_state=state;\nendmodule')
        assert observed_slot == (proof / 'memory_command_slot.v').read_text()
        miter = (proof / 'miter.v').read_text()
        assert miter.count('assume(') == 1 and 'reg initialized=0;' in miter and 'initialized<=1;' in miter
        assert 'if(!initialized)assume(rst);' in miter and 'if(initialized)begin' in miter
        outputs = [p for p in public if p[0] == 'output'] + helpers
        for d, _, n in public + helpers:
            for label in ('gold', 'gate'):
                assert f'.{n}({n if d == "input" else label + "_" + n})' in miter
        for _, _, n in outputs:
            if n != 'formal_bound': assert f'assert(gold_{n}==gate_{n});' in miter
        for label in ('gold', 'gate'):
            assert f'backend_{label} #(.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH),.MAX_TEXT_BYTES(MAX_TEXT_BYTES)) {label}(' in miter
        expected = 'read_verilog -formal -sv memory_command_slot.v gold.v gate.v miter.v\nprep -top backend_equivalence -flatten\ntechmap\nopt -full\nabc -g simple\nopt_clean\nsat -seq 1 -tempinduct -maxsteps 8 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n'
        if proof_report['proof_engine'] == 'smtbmc':
            expected = 'read_verilog -formal -sv memory_command_slot.v gold.v gate.v miter.v\nprep -top backend_equivalence -flatten\ndffunmap\nwrite_smt2 -wires model.smt2\n'
        assert (proof / 'proof.ys').read_text() == expected
        for n in ('gold.v', 'gate.v', 'miter.v', 'memory_command_slot.v', 'proof.ys', 'yosys.log'):
            files[Path('formal/reports') / n] = proof / n

    replay = root / 'build/validation/checked-close-address-generation-replay'
    for n, p in {'tools/generate_checked_close_address_experiment.py': source / 'tools/generate_checked_close_address_experiment.py',
                 'rtl/rpc_http2_response_partition.v': previous_source / 'rtl/rpc_http2_response_partition.v',
                 **{'build/experiments/registered-close-scope/rtl/' + Path(n).name: previous_source / n for n in changed[:2]}}.items():
        q = replay / n; q.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, q)
    subprocess.run([sys.executable, str(replay / 'tools/generate_checked_close_address_experiment.py')], check=True, capture_output=True, text=True)
    for n in changed: assert sha(replay / 'build/experiments/checked-close-address/rtl' / Path(n).name) == inputs[n]

    raw_records = {}
    profiles = [('native', args.raw, 'test_raw_grpc_enveloped.py', 'native_calls_return_actual_dma_ids_and_complete_grpc'),
                ('return-faults', args.raw_return_faults, 'test_raw_grpc_return_faults.py', 'raw_admitted_return_metadata_faults_keep_real_ownership'),
                ('shutdown-faults', args.raw_shutdown_faults, 'test_raw_shutdown_faults.py', 'raw_shutdown_memory_failures_preserve_quarantine_and_ownership')]
    for profile, name, test_file, test_name in profiles:
        if not name: continue
        raw = root / 'build/wsl-reports' / ('raw_envelope_' + name)
        raw_source, raw_inputs, raw_report, raw_snapshot = record(raw, 'raw/' + profile)
        assert raw_report['profile'] == raw_snapshot['profile'] == profile
        assert sorted(raw_snapshot['isolated_rtl_overrides']) == changed
        raw_acceptance = json.loads((raw / 'acceptance.json').read_text())
        assert raw_report['tests'] == 1 and raw_report['failures'] == 0 and raw_report['acceptance_sha256'] == sha(raw / 'acceptance.json')
        assert raw_acceptance == previous['raw_executions'][profile]['acceptance']
        baseline_source = Path(previous['evidence_folder']) / 'raw' / profile / 'execution'
        assert raw_inputs['sim/cocotb/' + test_file] == sha(baseline_source / 'sim/cocotb' / test_file) == sha(root / 'sim/cocotb' / test_file)
        for n, h in raw_inputs.items():
            if n.startswith(('build/bidirectional-fixtures/', 'native-vendor/')): assert h == sha(baseline_source / n), n
        raw_xml = ET.parse(raw / 'results.xml'); raw_cases = raw_xml.findall('.//testcase')
        assert len(raw_cases) == 1 and raw_cases[0].attrib['name'] == test_name
        assert not raw_xml.findall('.//failure') and not raw_xml.findall('.//error')
        for top, count in (('http2_enveloped_parser_application', 68), ('tokenizer_fpga_memory_subsystem', 22)):
            raw_dag = closure(top, raw_source); assert len(raw_dag) == count
            for p in raw_dag.values():
                n = p.relative_to(raw_source).as_posix()
                assert raw_inputs[n] == (inputs[n] if n in changed else sha(source_path(root, n))), n
        for n in ('acceptance.json', 'simulation.log', 'build.log', 'results.xml'):
            files[Path('raw') / profile / 'reports' / n] = raw / n
        raw_records[profile] = raw_acceptance

    part = 'xcau15p-ffvb676-2-e'; top = 'http2_enveloped_parser_application'
    folder = root / 'build/implementation' / part / args.native_run
    log = source_path(root, 'build/' + args.native_run + '-implementation.log')
    native = dict(phase='not_yet_verified', run=args.native_run, timing_met=False)
    log_bytes = log.read_bytes() if log.is_file() else b''; log_text = log_bytes.decode()
    routed = f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART={part}' in log_text
    synthesized = 'synth_design completed successfully' in log_text and 'Command: opt_design' in log_text
    if routed or synthesized:
        assert args.raw, 'Native source binding requires the direct experimental raw integration execution'
        assert '0 Critical Warnings and 0 Errors encountered.' in log_text
        assert f'synth_design -top {top}_timing_harness -part {part} -mode out_of_context' in log_text
        provenance = json.loads((folder / 'source-provenance.json').read_text()); frozen = folder / 'sources'
        for n, r in provenance['files'].items(): assert sha(frozen / n) == r['sha256'], n
        raw_source = root / 'build/wsl-reports' / ('raw_envelope_' + args.raw) / 'execution-sources'
        native_dag = closure(top, frozen); assert len(native_dag) == 68
        assert not {'bpe_tokenizer_engine', 'detokenizer_engine', 'token_packager'} & native_dag.keys()
        for p in native_dag.values():
            n = p.relative_to(frozen).as_posix(); assert sha(p) == sha(raw_source / n), n
            files[Path('native/sources') / n] = p
        exceptions = [s.strip() for s in (frozen / 'scripts/implement_registered_subsystem.tcl').read_text().splitlines() if s.strip().startswith('set_false_path')]
        assert exceptions == ['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]', 'set_false_path -to [all_outputs]']
        suffix = 'routed' if routed else 'synthesis'
        clocks = timing(folder / (suffix + '_timing.rpt')); area = resources(folder / (suffix + '_utilization.rpt'))
        row = next(s for s in (folder / (suffix + '_utilization.rpt')).read_text().splitlines() if re.match(r'\|\s*' + top + r'_timing_harness\s*\|', s))
        cells = [s.strip() for s in row.split('|')[1:-1]]
        total = dict(luts=int(cells[2]), registers=int(cells[6]), bram36=int(cells[7]), bram18=int(cells[8]), uram=int(cells[9]), dsps=int(cells[10]))
        assert total['luts'] <= 77760 and total['registers'] <= 155520
        assert total['bram36'] + total['bram18'] / 2 <= 144 and total['dsps'] <= 576 and total['uram'] == 0
        checkpoint = folder / ('routed.dcp' if routed else 'synthesized.dcp')
        with ZipFile(checkpoint) as archive: metadata_bytes = archive.read('dcp.xml')
        metadata = {n.tag: n.attrib.get('Name') for n in ET.fromstring(metadata_bytes)}
        assert metadata['Part'] == part and metadata['Top'] == top + '_timing_harness' and metadata['OutOfContext'] == '1'
        reports = ['source-provenance.json', suffix + '_timing.rpt', suffix + '_utilization.rpt']
        if routed:
            assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (folder / 'route_status.rpt').read_text())
            assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|', (folder / 'routed_drc.rpt').read_text(), re.M)
            reports += ['route_status.rpt', 'routed_drc.rpt']
        for n in reports: files[Path('native') / n] = folder / n
        captured = root / 'build/validation/native-log-snapshots' / hashlib.sha256(log_bytes).hexdigest()
        captured.parent.mkdir(parents=True, exist_ok=True)
        if captured.exists(): assert captured.read_bytes() == log_bytes
        else: captured.write_bytes(log_bytes)
        files[Path('native/implementation.log')] = captured
        native = dict(phase='native_route_verified' if routed else 'native_synthesis_verified', run=args.native_run,
            top=top, part=part, resources=area, total_harness_resources=total, timing=clocks, routed=routed,
            checkpoint_sha256=sha(checkpoint), checkpoint_metadata=metadata,
            exact_experimental_parser_modules_verified=68, native_resource_capacity_verified=True,
            registered_neighbors=True, package_paths_excluded=True, physical_interfaces_verified=False,
            timing_met=routed and clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0 and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0)
    files[Path('verification') / Path(__file__).name] = Path(__file__)
    key = hashlib.sha256(''.join(str(n) + sha(files[n]) for n in sorted(files)).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/checked-close-address-evidence' / key
    for n, p in files.items():
        q = evidence / n; q.parent.mkdir(parents=True, exist_ok=True)
        if q.exists(): assert sha(q) == sha(p)
        else: shutil.copy2(p, q)
    result = dict(phase='checked_close_address_rpc_and_arithmetic_cone_verified' if proof_report['proof_engine']=='algebra' else 'checked_close_address_rpc_and_backend_equivalence_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), changed_modules=[Path(n).stem for n in changed],
        actual_rpc_acceptance=acceptance, matrix_simulation_time_ns=float(properties['sim_time_duration']),
        actual_formal_proof=proof_report, full_backend_public_output_equivalence_verified=proof_report['proof_engine']!='algebra',
        only_initial_reset_assumed=proof_report['proof_engine']!='algebra',
        arithmetic_cone_requires_no_environment_assumptions=proof_report['proof_engine']=='algebra',
        complete_model_and_native_oracle_inputs_match_audited_baseline=True, exact_generation_replayed=True,
        raw_native_direct_execution_verified=bool(args.raw), raw_executions=raw_records,
        raw_shutdown_faults_direct_on_three_file_experiment_verified=bool(args.raw_shutdown_faults),
        raw_return_faults_direct_on_three_file_experiment_verified=bool(args.raw_return_faults),
        full_native_corpus_direct_on_three_file_experiment_verified=False,
        production_rtl_unchanged=True, native=native, native_routed_timing_verified=native['timing_met'], physical_interfaces_verified=False,
        full_system_complete=False, evidence_folder=str(evidence), verifier_sha256=sha(Path(__file__)))
    (root / 'build/validation/checked-close-address-experiment.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'matrix_simulation_time_ns', 'raw_native_direct_execution_verified', 'evidence_folder')}, indent=2))


if __name__ == '__main__':
    main()
