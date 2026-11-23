"""Bind a Parser variant's native implementation to its executed RTL."""
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
from zipfile import ZipFile

from verify_two_fpga_application import closure, resources, timing


def main():
    parser = argparse.ArgumentParser()
    variant_args = parser.add_mutually_exclusive_group()
    variant_args.add_argument('--local-error', action='store_true',
        help='Verify the 74-module GOAWAY/history/GPU-drain variant')
    variant_args.add_argument('--local-cancel', action='store_true',
        help='Verify the 75-module scoped fatal GPU-return cancellation variant')
    variant_args.add_argument('--packer-keep', action='store_true',
        help='Verify the formally equivalent packet-packer candidate')
    variant_args.add_argument('--post-commit-retire', action='store_true',
        help='Verify the actual late-control-error directory retirement variant')
    variant_args.add_argument('--pending-idle', action='store_true',
        help='Verify the pending-window-request idle guard candidate')
    variant_args.add_argument('--receive-format', action='store_true',
        help='Verify global receive-ledger initialization and explicit FORMAT recovery')
    parser.add_argument('--tokenizer', action='store_true', help='Verify the packer candidate on SCU35 Tokenizer')
    args = parser.parse_args()
    if args.tokenizer and not args.packer_keep:
        parser.error('--tokenizer requires --packer-keep')
    variant = 'receive-format' if args.receive_format else 'pending-idle' if args.pending_idle else 'post-commit-retire' if args.post_commit_retire else 'packer-keep' if args.packer_keep else 'local-cancel' if args.local_cancel else 'local-error' if args.local_error else 'receive-pool'
    artifact = variant + ('-tokenizer' if args.tokenizer else '')
    phase = artifact.replace('-', '_')
    modules = 22 if args.tokenizer else 75 if args.local_cancel or args.packer_keep or args.post_commit_retire or args.pending_idle or args.receive_format else 74 if args.local_error else 73
    top = 'tokenizer_fpga_memory_subsystem' if args.tokenizer else 'http2_enveloped_parser_application'
    part = 'xcsu35p-sbvb625-2-e' if args.tokenizer else 'xcau15p-ffvb676-2-e'
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    direct_path = root / ('build/validation/' + variant + '-experiment.json')
    direct_bytes = direct_path.read_bytes()
    direct = json.loads(direct_bytes)
    assert direct['phase'] == ('actual_global_receive_format_and_shutdown_verified' if args.receive_format else 'pending_window_idle_guard_joined_verified' if args.pending_idle else 'actual_post_commit_retirement_directed_verified' if args.post_commit_retire else 'packer_keep_formal_and_joined_verified' if args.packer_keep else 'actual_local_credit_cancel_and_reopen_verified' if args.local_cancel else
        'actual_local_error_goaway_close_and_gpu_drain_verified' if args.local_error else 'actual_receive_pool_direct_verified')
    run = ('tokenizer_scu35_packer_keep' if args.tokenizer else 'parser_au15p_packer_keep') if args.packer_keep else 'parser_au15p_local_credit_cancel' if args.local_cancel else 'parser_au15p_local_error_drain' if args.local_error else 'parser_au15p_receive_pool_locked'
    if args.post_commit_retire:run='parser_au15p_post_commit_retire'
    if args.pending_idle:run='parser_au15p_pending_idle'
    if args.receive_format:run='parser_au15p_receive_format_serial'
    folder = root / 'build/implementation' / part / run
    frozen = folder / 'sources'
    provenance = json.loads((folder / 'source-provenance.json').read_text())
    for name, h in provenance['files'].items():
        assert sha(frozen / name) == h['sha256'], name
    dag = closure(top, frozen)
    assert len(dag) == modules
    hashes = {n: sha(p) for n, p in dag.items()}
    assert hashes == direct['executed_tokenizer_sha256' if args.tokenizer else 'executed_parser_sha256']
    output = root / ('build/validation/' + artifact + '-native-harness-replay.v')
    subprocess.run([sys.executable, str(frozen / 'tools/generate_parser_timing_harness.py'),
        '--source', str(frozen / 'rtl' / (top + '.v')),
        '--top', top,
        '--harness-top', top + '_timing_harness',
        '--output', str(output)], check=True, capture_output=True, text=True)
    assert sha(output) == sha(frozen / 'timing_harness.v')
    exceptions = [s.strip() for s in (frozen / 'scripts/implement_registered_subsystem.tcl').read_text().splitlines()
        if s.strip().startswith('set_false_path')]
    assert exceptions == ['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]',
                          'set_false_path -to [all_outputs]']
    log = root / 'build' / (run + '-implementation.log')
    log_bytes = log.read_bytes()
    text = log_bytes.decode()
    captured = root / 'build/validation/native-log-snapshots' / hashlib.sha256(log_bytes).hexdigest()
    captured.parent.mkdir(parents=True, exist_ok=True)
    if not captured.exists():
        captured.write_bytes(log_bytes)
    assert 'synth_design completed successfully' in text and 'ERROR:' not in text
    routed = 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE' in text
    suffix = 'routed' if routed else 'synthesis'
    checkpoint = folder / ('routed.dcp' if routed else 'synthesized.dcp')
    with ZipFile(checkpoint) as package:
        metadata = {n.tag: n.attrib.get('Name') for n in ET.fromstring(package.read('dcp.xml'))}
    assert metadata['Part'] == part
    assert metadata['Top'] == top + '_timing_harness' and metadata['OutOfContext'] == '1'
    area = resources(folder / (suffix + '_utilization.rpt'))
    clocks = timing(folder / (suffix + '_timing.rpt'))
    row = next(s for s in (folder / (suffix + '_utilization.rpt')).read_text().splitlines()
        if re.match(r'\|\s*' + re.escape(top + '_timing_harness') + r'\s*\|', s))
    cells = [s.strip() for s in row.split('|')[1:-1]]
    total = dict(luts=int(cells[2]), registers=int(cells[6]), bram36=int(cells[7]),
        bram18=int(cells[8]), uram=int(cells[9]), dsps=int(cells[10]))
    assert total['luts'] <= (16320 if args.tokenizer else 77760) and total['registers'] <= (32640 if args.tokenizer else 155520)
    assert total['bram36'] + total['bram18'] / 2 <= (48 if args.tokenizer else 144) and total['uram'] == 0
    if args.tokenizer:
        assert total['dsps'] == 4  # Same four DSPs as the already routed SCU35 baseline.
    else:
        assert total['dsps'] <= 576
    reports = {suffix + '_utilization.rpt', suffix + '_timing.rpt'}
    if routed:
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:', (folder / 'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|', (folder / 'routed_drc.rpt').read_text(), re.M)
        reports |= {'route_status.rpt', 'routed_drc.rpt'}
    result = dict(phase=phase + ('_native_route_verified' if routed else '_native_synthesis_verified'),
        verified_utc=datetime.now(timezone.utc).isoformat(), run=run, top=top, part=part, direct_audit_key=direct['key'],
        direct_audit_sha256=hashlib.sha256(direct_bytes).hexdigest(),
        source_provenance_sha256=sha(folder / 'source-provenance.json'),
        captured_log=str(captured), checkpoint_metadata=metadata, checkpoint_sha256=sha(checkpoint),
        registered_all_current_ports_verified=True, timing_harness_sha256=sha(frozen / 'timing_harness.v'),
        only_package_path_exceptions_verified=True, resources=area, total_harness_resources=total,
        timing=clocks, reports_sha256={n: sha(folder / n) for n in sorted(reports)},
        routed=routed, timing_met=routed and clocks['setup_wns_ns'] >= 0 and clocks['hold_whs_ns'] >= 0
            and clocks['setup_failing_endpoints'] == clocks['hold_failing_endpoints'] == 0,
        physical_board_timing_verified=False, full_system_complete=False, verifier_sha256=sha(Path(__file__)))
    result['frozen_tokenizer_sha256' if args.tokenizer else 'frozen_parser_sha256'] = hashes
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / ('build/validation/' + artifact + '-native-evidence') / key
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'verified.json').write_text(json.dumps(result, indent=2) + '\n')
    (evidence / 'direct-audit.json').write_bytes(direct_bytes)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    result.update(key=key, evidence_folder=str(evidence))
    (root / ('build/validation/' + artifact + '-native-experiment.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(phase=result['phase'], key=key, resources=area, timing=clocks, timing_met=result['timing_met'])))


if __name__ == '__main__':
    main()
