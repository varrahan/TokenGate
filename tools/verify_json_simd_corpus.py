"""Verify the complete native corpus on the exact 76-module SIMD Parser."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from verify_native_grpc_corpus_reference import verify_reference
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='json_simd_full_native_corpus_20261122')
    args = parser.parse_args()
    assert args.name.replace('_', '').isalnum()
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    read = lambda path: json.loads(path.read_text())
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + args.name)
    source = archive / 'execution-sources'
    launch_path = root / 'build/validation' / (args.name + '-launch.json')
    launch = read(launch_path)
    assert launch['phase'] == 'completed' and launch['exit_code'] == 0
    inputs, report, snapshot, accepted = (read(archive / name) for name in
        ('inputs.json', 'report.json', 'snapshot.json', 'acceptance.json'))
    assert snapshot['exit_code'] == 0 and report['phase'] == accepted['phase'] == 'passed'
    assert report['profile'] == snapshot['profile'] == 'workload'
    assert report['tests'] == 1 and report['failures'] == 0
    assert inputs == launch['inputs_sha256'] == report['input_sha256']
    assert report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    for name, digest in inputs.items():
        assert sha(source / name) == digest, name
        if name.startswith('native-vendor/'):
            assert sha(root / '.venv312/Lib/site-packages' / name.split('/', 1)[1]) == digest
    xml = ET.parse(archive / 'results.xml')
    assert len(xml.findall('.//testcase')) == 1
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    assert xml.find('.//testcase').attrib['name'] == 'complete_prompt_corpus_uses_native_grpc_and_actual_dma'
    parent_path = root / 'build/validation/progress-format-corpus.json'
    parent = read(parent_path)
    assert parent['key'] == launch['parent_corpus_audit_key'] == '6dd529d376e06926'
    component_path = root / 'build/validation/json-simd-decoder.json'
    component = read(component_path)
    assert component['actual_parallel_consumption_verified'] and component['native_timing_verified']
    generation = read(archive / 'simd-generation.json')
    assert generation['parent_corpus_audit_key'] == parent['key']
    changed = sorted(name for name in inputs if name in parent['inputs_sha256']
                     and inputs[name] != parent['inputs_sha256'][name])
    added = sorted(inputs.keys() - parent['inputs_sha256'].keys())
    assert changed == ['rtl/json_string_normalizer.v', 'rtl/proto_json_decoder.v', 'rtl/speculative_json_fsm.v']
    assert added == ['rtl/axis_compacting_window.v', 'rtl/json_simd_scanner.v']
    assert not parent['inputs_sha256'].keys() - inputs.keys()
    for name in changed + added:
        assert inputs[name] == generation['outputs_sha256'][name]
    parser_modules = closure('http2_enveloped_parser_application', source)
    tokenizer_modules = closure('tokenizer_fpga_memory_subsystem', source)
    assert len(parser_modules) == 76 and len(tokenizer_modules) == 22
    parser_hashes = {name: sha(path) for name, path in parser_modules.items()}
    tokenizer_hashes = {name: sha(path) for name, path in tokenizer_modules.items()}
    assert tokenizer_hashes == parent['executed_tokenizer_sha256']
    assert parser_hashes == {name: generation['outputs_sha256']['rtl/' + name + '.v'] for name in parser_modules}
    pool = accepted['actual_receive_pool_ownership']
    assert pool['receive_grants'] == pool['receive_unlocks'] == pool['ordinary_commands'] == 17
    assert pool['init_commands'] == 17 and pool['close_commands'] == 32
    assert pool['receive_memory_commands'] == pool['receive_memory_acks'] == 1398
    reference = verify_reference(root, source, accepted, parser_memory_clients=19, native_wire_frames=2879)
    assert sha(archive / 'protocol-runner-used.py') == launch['driver_sha256']
    tools = [Path(__file__), root / 'tools/verify_native_grpc_corpus_reference.py',
             root / 'tools/verify_two_fpga_application.py', root / 'tools/generate_two_fpga_application.py',
             root / 'tools/generate_bidirectional_application.py']
    artifacts = {source_relative(path, root).as_posix(): sha(path) for path in
                 [*tools, parent_path, component_path, launch_path, *archive.iterdir()] if path.is_file()}
    result = dict(phase='json_simd_complete_native_corpus_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), snapshot=args.name,
        parent_corpus_audit_key=parent['key'], component_audit_key=component['key'],
        acceptance=accepted, independent_native_reference=reference,
        exact_parser_modules=76, exact_tokenizer_modules=22,
        executed_parser_sha256=parser_hashes, executed_tokenizer_sha256=tokenizer_hashes,
        inputs_sha256=inputs, changed_rtl=changed, added_rtl=added,
        full_native_corpus_verified=True, actual_execution_sources_verified=True,
        protocol_fixture_sources_unchanged=True, tokenizer_sources_unchanged=True,
        full_image_and_native_tokenizer_verified=True,
        latest_31_module_tokenizer_controller_integrated=False,
        full_parser_native_timing_verified=False, full_protocol_matrix_verified=False,
        physical_interfaces_verified=False, sustained_line_rate_verified=False,
        full_system_complete=False, artifacts_sha256=artifacts)
    result['key'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/json-simd-corpus-evidence' / result['key']
    evidence.mkdir(parents=True, exist_ok=False)
    for path in tools + [component_path, launch_path]:
        target = evidence / source_relative(path, root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    output = root / 'build/validation/json-simd-corpus.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    shutil.copy2(output, evidence / 'verified.json')
    print(json.dumps(dict(phase=result['phase'], key=result['key'], calls=16,
                         actual_dma_ids=2828, wire_frames=2879)))


if __name__ == '__main__':
    main()
