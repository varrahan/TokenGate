"""Add an independent new-RPC fence to the full native-memory composition.

This prepares the drain phase of distributed image maintenance. It does not
grant image writes, infer GPU completion, or replace durable RPC recovery.
"""
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def replacements():
    common = [
        ('input wire  admit_messages,',
         'input wire  admit_messages,\ninput wire  admit_new_rpcs,'),
        ('.admit_messages(admit_messages),',
         '.admit_messages(admit_messages),\n    .admit_new_rpcs(admit_new_rpcs),'),
    ]
    result = {name: list(common) for name in (
        'http2_enveloped_parser_application', 'http2_enveloped_parser_core',
        'http2_schema_mmio_application')}
    result['http2_classified_parser_transport'] = [common[0],
        ('assign a_admit_new=admit_messages&&!packet_fatal;',
         'assign a_admit_new=admit_messages&&admit_new_rpcs&&!packet_fatal;')]
    result['two_fpga_hyperram_application'] = [
        ('input wire  parser_admit_messages,',
         'input wire  parser_admit_messages,\n    input wire  parser_admit_new_rpcs,'),
        ('.admit_messages(parser_admit_messages),',
         '.admit_messages(parser_admit_messages),\n    .admit_new_rpcs(parser_admit_new_rpcs),')]
    return result


def apply(original, edits):
    updated = original
    for before, after in edits:
        assert updated.count(before) == 1, before
        updated = updated.replace(before, after)
    inverse = updated
    for before, after in reversed(edits):
        assert inverse.count(after) == 1, after
        inverse = inverse.replace(after, before)
    assert inverse == original
    return updated


def main():
    root = Path(__file__).resolve().parents[1]
    parent = root / 'build/experiments/joint-schema-capacity-success-v1'
    target = root / 'build/experiments/rpc-admission-fence-v1'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = json.loads((parent / 'generation.json').read_text())
    assert sha(parent / 'generation.json') == '8c8cda100f609ae96c5ef2e739bfe49e5b33659b55a0bfc1cbad7ac96758a9fe'
    target.mkdir(parents=True, exist_ok=False)
    for name, digest in manifest['outputs_sha256'].items():
        assert sha(parent / name) == digest, name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(parent / name, destination)
    certificates = {}
    for module, edits in replacements().items():
        name = 'joint/rtl/' + module + '.v'
        p = target / name
        original = p.read_bytes().decode()
        # Retain each source's line endings and all bytes outside these edits.
        if '\r\n' in original:
            edits = [(before.replace('\n', '\r\n'), after.replace('\n', '\r\n')) for before, after in edits]
        updated = apply(original, edits)
        old_ports = ports(original, module)
        new_ports = ports(updated, module)
        added = 'parser_admit_new_rpcs' if module.startswith('two_fpga') else 'admit_new_rpcs'
        assert [p for p in new_ports if p[2] != added] == old_ports
        assert [p for p in new_ports if p[2] == added] == [('input', '', added)]
        p.write_bytes(updated.encode())
        certificates[name] = dict(before_sha256=sha(parent / name), after_sha256=sha(p), replacements=edits)
    name = 'joint_hyperram_grpc_tb.sv'
    p = target / name
    edits = [
        ('reg  parser_admit_messages=0;',
         'reg  parser_admit_messages=0;\nreg  parser_admit_new_rpcs=1;'),
        ('.parser_admit_messages(parser_admit_messages),',
         '.parser_admit_messages(parser_admit_messages),\n.parser_admit_new_rpcs(parser_admit_new_rpcs),')]
    original = p.read_bytes().decode()
    p.write_bytes(apply(original, edits).encode())
    certificates[name] = dict(before_sha256=sha(parent / name), after_sha256=sha(p), replacements=edits)
    parser = closure('http2_schema_mmio_application', target / 'joint')
    tokenizer = closure('tokenizer_chiplet__tokenizer_hyperram_subsystem', target / 'joint')
    assert len(parser) == 79 and len(tokenizer) == 31
    assert {n: sha(p) for n, p in tokenizer.items()} == manifest['canonical_tokenizer_sha256']
    changed = {n for n, h in manifest['outputs_sha256'].items() if sha(target / n) != h}
    assert changed == set(certificates)
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    result = dict(phase='generated_awaiting_independent_audit', parent_generation_sha256=sha(parent / 'generation.json'),
        parent_generation=manifest, source_edit_certificates=certificates,
        parser_modules=79, tokenizer_modules=31,
        canonical_parser_sha256={n: sha(p) for n, p in parser.items()},
        canonical_tokenizer_sha256={n: sha(p) for n, p in tokenizer.items()},
        initial_testbench_fence_is_open=True,
        original_traffic_images_and_assertions_preserved=True,
        whole_rpc_gpu_maintenance_authority_verified=False,
        functional_runtime_verified=False, timing_verified=False, full_system_complete=False,
        generator_sha256=sha(Path(__file__)))
    result['outputs_sha256'] = {p.relative_to(target).as_posix(): sha(p) for p in target.rglob('*') if p.is_file()}
    (target / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'parser_modules', 'tokenizer_modules')}))


if __name__ == '__main__':
    main()
