"""Bind exact semantic-event RTL, induction, corpus, fences and fault evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_payload_event_buffer import buffered
from run_frame_fifo_equivalence_wsl import cones, miter, observe
from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    candidate = root / 'build/experiments/payload-event-buffer'
    parent = root / 'build/experiments/frame-owned-quiet'
    generation = read(candidate / 'generation.json')
    parent_audit = read(root / 'build/validation/frame-owned-quiet-corpus.json')
    native = read(root / 'build/validation/frame-owned-quiet-parser-native.json')
    assert parent_audit['key'] == generation['parent_corpus_audit_key'] == 'b89b9aea0dd403cb'
    assert native['key'] == generation['parent_native_audit_key'] == 'f9e7e63dced475c3'
    assert native['exact_core_modules'] == 76 and native['exact_tested_source_digests_verified']
    assert not native['timing_met'] and native['setup_slack_ns'] == -1.533
    for name, digest in generation['outputs_sha256'].items():
        assert sha(candidate / name) == digest, name
    old = (parent / 'rtl/http2_payload_decoder.v').read_bytes().decode()
    assert sha(parent / 'rtl/http2_payload_decoder.v') == parent_audit['executed_parser_sha256']['http2_payload_decoder']
    updated, certificate = buffered(old)
    assert (candidate / 'rtl/http2_payload_decoder.v').read_bytes() == updated.encode()
    assert json.loads(json.dumps(certificate)) == generation['source_edit_certificate']
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', candidate).items()}
    assert len(parser) == 77 and set(parser) - set(parent_audit['executed_parser_sha256']) == {'axis_pingpong_skid_buffer'}
    assert {n for n in parent_audit['executed_parser_sha256'] if parser[n] != parent_audit['executed_parser_sha256'][n]} == {'http2_payload_decoder'}
    assert sha(candidate / 'generate_payload_event_buffer.py') == generation['generator_sha256']
    prior = read(root / 'build/validation/frame-event-pingpong.json')
    assert prior['key'] == '806c3d55fa92d7b8'
    assert parser['axis_pingpong_skid_buffer'] == prior['executed_parser_sha256']['axis_pingpong_skid_buffer']
    formal = root / 'build/wsl-reports/payload_event_fifo_equivalence_20261122'
    proof = read(formal / 'report.json')
    assert proof['passed'] and proof['parent_generation_sha256'] == sha(candidate / 'generation.json')
    assert proof['candidate_sha256'] == parser['axis_pingpong_skid_buffer']
    assert proof['baseline_sha256'] == parser['axis_skid_buffer']
    assert len(proof['proofs']) == 1
    row = proof['proofs'][0]
    assert (row['data_width'], row['keep_width'], row['user_width']) == (147, 1, 16)
    folder = formal / 'd147_k1_u16'
    assert (folder / 'miter.sv').read_text() == miter(147, 1, 16)
    assert sha(folder / 'proof.log') == row['proof_log_sha256'] and sha(folder / 'netlist.json') == row['netlist_sha256']
    assert 'Induction step proven: SUCCESS!' in (folder / 'proof.log').read_text()
    assert cones(read(folder / 'netlist.json')) == row['payload_register_cones']
    wide = '[DATA_WIDTH+KEEP_WIDTH+USER_WIDTH:0]'
    for module, original, observed, signals in (
        ('axis_skid_buffer', 'baseline-original.v', 'baseline.v', [('[1:0]', 'count'), (wide, 'head_payload'), (wide, 'tail_payload')]),
        ('axis_pingpong_skid_buffer', 'candidate-original.v', 'candidate.v', [('[1:0]', 'count'), (wide, 'slot0_payload'), (wide, 'slot1_payload'), ('', 'read_slot'), ('', 'write_slot')])):
        assert sha(formal / original) == parser[module]
        assert (folder / observed).read_text() == observe((formal / original).read_text(), module, signals)
    assert sha(formal / 'run_frame_fifo_equivalence_wsl.py') == proof['driver_sha256']
    archive = root / 'build/wsl-reports/payload_event_buffer_units_20261122'
    report = read(archive / 'report.json')
    assert report['passed'] and report['phase'] == 'payload_event_buffer_semantic_transport_corpus_verified'
    assert report['generation_sha256'] == sha(candidate / 'generation.json')
    assert sha(archive / 'run_payload_event_buffer_units_wsl.py') == report['driver_sha256']
    for name, digest in report['reference_sha256'].items():
        assert sha(archive / 'reference' / name) == digest
    tb = (archive / 'tb_http2_connections.sv').read_bytes().decode()
    for old, new in reversed(report['testbench_edits']):
        assert tb.count(new) == 1
        tb = tb.replace(new, old)
    assert hashlib.sha256(tb.encode()).hexdigest() == report['original_testbench_sha256']
    for revision, record in report['revisions'].items():
        assert record['phase'] == 'passed'
        for name, digest in record['inputs_sha256'].items():
            assert sha(archive / revision / name) == digest
        assert (archive / revision / 'tb_http2_connections.sv').read_bytes() == (archive / 'tb_http2_connections.sv').read_bytes()
        assert sha(archive / revision / 'simulate.log') == record['simulation_log_sha256']
        log = (archive / revision / 'simulate.log').read_text()
        assert not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):', log, re.M)
        assert record['summary'] == [2208, 123013, 84, 442, 30]
        expected_payload = parent_audit['executed_parser_sha256']['http2_payload_decoder'] if revision == 'baseline' else parser['http2_payload_decoder']
        assert record['inputs_sha256']['rtl/http2_payload_decoder.v'] == expected_payload
    actual = report['revisions']['candidate']
    assert actual['buffer_full_cycles'] > 100 and actual['completion_fence_cycles'] > 0
    result = dict(phase='payload_event_buffer_semantic_evidence_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), exact_parser_modules=77,
        parent_corpus_audit_key=parent_audit['key'], parent_native_audit_key=native['key'],
        semantic_payload_bits=147, semantic_context_bits=16, source_edit_replay_verified=True,
        executed_parser_sha256=parser, semantic_packets=2208, exact_semantic_events=123013,
        protocol_failures=84, controls=442, injected_connection_memory_faults=30,
        unbounded_fifo_induction_verified=True, initial_reset_required=True, arbitrary_later_resets=True,
        input_stability_assumptions=False, two_state_formal=True,
        downstream_ready_excluded_from_payload_register_next_state_cones=True,
        completion_fence_cycles=actual['completion_fence_cycles'], buffer_full_cycles=actual['buffer_full_cycles'],
        semantic_state_and_snapshot_layout_unchanged=True, portable_memory_backend=True,
        full_application_corpus_verified=False, full_protocol_matrix_verified=False,
        open_rpc_credit_fixed=False, native_timing_verified=False, full_system_complete=False,
        generation_sha256=sha(candidate / 'generation.json'), unit_report_sha256=sha(archive / 'report.json'),
        formal_report_sha256=sha(formal / 'report.json'), verifier_sha256=sha(Path(__file__)))
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/payload-event-buffer-units-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    for path in (Path(__file__), root / 'tools/generate_payload_event_buffer.py', root / 'tools/run_frame_fifo_equivalence_wsl.py'):
        shutil.copy2(path, evidence / path.name)
    for destination in (evidence / 'audit.json', root / 'build/validation/payload-event-buffer-units.json'):
        destination.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'key', 'exact_parser_modules')}))


if __name__ == '__main__':
    main()
