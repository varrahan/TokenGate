"""Independently audit the narrow fence wiring and strict full-pair elaboration.

The result is an assembly check, not a claim of distributed maintenance or a
new end-to-end functional run. Existing live RPCs retain their old epochs.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    parent = root / 'build/experiments/joint-schema-capacity-success-v1'
    archive = root / 'build/wsl-reports/rpc_admission_fence_v1_elaboration'
    source = archive / 'execution-sources'
    generation = read(archive / 'generation.json')
    report = read(archive / 'report.json')
    original = read(parent / 'generation.json')
    assert sha(parent / 'generation.json') == generation['parent_generation_sha256'] == '8c8cda100f609ae96c5ef2e739bfe49e5b33659b55a0bfc1cbad7ac96758a9fe'
    assert generation['parent_generation'] == original
    assert report['phase'] == 'elaborated_independent_audit_pending' and report['exit_code'] == 0
    assert report['generation_sha256'] == sha(archive / 'generation.json')
    assert report['inputs_sha256'] == generation['outputs_sha256']
    for name, digest in generation['outputs_sha256'].items():
        assert sha(source / name) == digest, name
    for name, digest in original['outputs_sha256'].items():
        assert sha(parent / name) == digest, name
    # Normative edits are stated here independently of the generator and its
    # certificates. No arbitrary replacement list is accepted as authority.
    passthrough = [
        ('input wire  admit_messages,', 'input wire  admit_messages,\ninput wire  admit_new_rpcs,'),
        ('.admit_messages(admit_messages),', '.admit_messages(admit_messages),\n    .admit_new_rpcs(admit_new_rpcs),')]
    expected = {name: list(passthrough) for name in (
        'http2_enveloped_parser_application', 'http2_enveloped_parser_core', 'http2_schema_mmio_application')}
    expected['http2_classified_parser_transport'] = [passthrough[0],
        ('assign a_admit_new=admit_messages&&!packet_fatal;',
         'assign a_admit_new=admit_messages&&admit_new_rpcs&&!packet_fatal;')]
    expected['two_fpga_hyperram_application'] = [
        ('input wire  parser_admit_messages,', 'input wire  parser_admit_messages,\n    input wire  parser_admit_new_rpcs,'),
        ('.admit_messages(parser_admit_messages),', '.admit_messages(parser_admit_messages),\n    .admit_new_rpcs(parser_admit_new_rpcs),')]
    expected = {'joint/rtl/' + name + '.v': edits for name, edits in expected.items()}
    expected['joint_hyperram_grpc_tb.sv'] = [
        ('reg  parser_admit_messages=0;', 'reg  parser_admit_messages=0;\nreg  parser_admit_new_rpcs=1;'),
        ('.parser_admit_messages(parser_admit_messages),', '.parser_admit_messages(parser_admit_messages),\n.parser_admit_new_rpcs(parser_admit_new_rpcs),')]
    assert set(generation['source_edit_certificates']) == set(expected)
    for name, edits in expected.items():
        old = (parent / name).read_bytes().decode()
        new = (source / name).read_bytes().decode()
        if '\r\n' in old:
            edits = [(a.replace('\n', '\r\n'), b.replace('\n', '\r\n')) for a, b in edits]
        certificate = generation['source_edit_certificates'][name]
        assert certificate['replacements'] == [list(p) for p in edits]
        assert certificate['before_sha256'] == sha(parent / name)
        assert certificate['after_sha256'] == sha(source / name)
        inverse = new
        for before, after in reversed(edits):
            assert inverse.count(after) == 1
            inverse = inverse.replace(after, before)
        assert inverse == old, name
        if name.startswith('joint/rtl/'):
            module = Path(name).stem
            added = 'parser_admit_new_rpcs' if module.startswith('two_fpga') else 'admit_new_rpcs'
            expected_occurrences = 2 if module in ('http2_classified_parser_transport', 'two_fpga_hyperram_application') else 3
            assert new.count(added) == expected_occurrences, (name, new.count(added))
            old_ports = ports(old, module)
            new_ports = ports(new, module)
            assert [p for p in new_ports if p[2] != added] == old_ports
            assert [p for p in new_ports if p[2] == added] == [('input', '', added)]
    changed = {name for name, digest in original['outputs_sha256'].items() if sha(source / name) != digest}
    assert changed == set(expected)
    assert set(generation['outputs_sha256']) == set(original['outputs_sha256']) | {'generate_rpc_admission_fence.py'}
    assert sha(source / 'generate_rpc_admission_fence.py') == generation['generator_sha256']
    parser = {n: sha(p) for n, p in closure('http2_schema_mmio_application', source / 'joint').items()}
    tokenizer = {n: sha(p) for n, p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem', source / 'joint').items()}
    assert len(parser) == 79 and len(tokenizer) == 31
    assert parser == generation['canonical_parser_sha256']
    assert tokenizer == generation['canonical_tokenizer_sha256'] == original['canonical_tokenizer_sha256']
    transport = (source / 'joint/rtl/http2_classified_parser_transport.v').read_text()
    assert transport.count('.admit_new(a_admit_new)') == 1
    assert 'assign p_admit_messages=admit_messages;' in transport
    assert 'state==IDLE&&admit_packets&&admit_messages&&!command_valid' in transport
    admission = (source / 'joint/rtl/http2_windowed_rpc_admission.v').read_text()
    assert 'allow_new<=admit_new;' in admission
    assert admission.index('else if(trailer)begin') < admission.index('else if(!allow_new)begin')
    assert 'else if(!allow_new)begin error_result(4,1,0,7);state<=RESULT;end' in admission
    assert sha(source / 'joint/rtl/http2_windowed_rpc_admission.v') == original['outputs_sha256']['joint/rtl/http2_windowed_rpc_admission.v']
    command = report['command']
    assert '--json-only' in command and '--flatten' in command and '--assert' in command
    assert not any(s in ' '.join(command) for s in ('--bbox', 'DONESPIN', 'DISABLE_ASSERT'))
    assert report['simulator_binary_sha256'] == '16ef0287751c10ec74f56643c45552652cc325d4b758fe8fd42c2cbe5bd471b3'
    for name, digest in report['artifacts_sha256'].items():
        assert sha(archive / name) == digest
    checks = report['vendor_elaboration_checks']
    assert checks['all_eight_instantiated_memories_have_ecc_disabled']
    assert checks['normal_global_startup_retained'] and checks['lowered_fatal_stop_nodes'] >= 300
    log = (archive / 'elaboration.log').read_text()
    assert '%Error' not in log
    assert not any('admit_new_rpcs' in line and ('PINMISSING' in line or 'PINNOTFOUND' in line or 'UNDRIVEN' in line) for line in log.splitlines())
    key = hashlib.sha256(json.dumps(dict(inputs=generation['outputs_sha256'], artifacts=report['artifacts_sha256'],
        verifier=sha(Path(__file__))), sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/rpc-admission-fence-evidence' / key
    evidence.mkdir(parents=True, exist_ok=False)
    for name in expected:
        p = evidence / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, p)
    shutil.copy2(Path(__file__), evidence / Path(__file__).name)
    shutil.copy2(archive / 'generation.json', evidence / 'generation.json')
    shutil.copy2(archive / 'report.json', evidence / 'elaboration-report.json')
    result = dict(key=key, verified_utc=datetime.now(timezone.utc).isoformat(),
        assembly_and_strict_elaboration_verified=True, exact_inverse_verified=True,
        parser_modules=79, tokenizer_modules=31, new_rpc_fence_has_one_admission_consumer=True,
        packet_message_and_return_admission_unchanged=True,
        admitted_begin_keeps_its_sampled_decision=True,
        existing_trailers_bypass_new_rpc_denial=True,
        vendor_sources_images_vectors_and_original_assertions_unchanged=True,
        full_pair_runtime_with_fence_transitions_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False, timing_verified=False, full_system_complete=False,
        generation_sha256=sha(archive / 'generation.json'), elaboration_report_sha256=sha(archive / 'report.json'),
        executed_parser_sha256=parser, executed_tokenizer_sha256=tokenizer)
    text = json.dumps(result, indent=2) + '\n'
    (evidence / 'audit.json').write_text(text)
    (root / 'build/validation/rpc-admission-fence.json').write_text(text)
    print(json.dumps({k: result[k] for k in ('key', 'assembly_and_strict_elaboration_verified', 'whole_rpc_gpu_maintenance_authority_verified')}))


if __name__ == '__main__':
    main()
