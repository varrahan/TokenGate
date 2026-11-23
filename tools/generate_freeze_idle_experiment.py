"""Exclude a real freeze transfer from the reverse service's idle indication."""
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    parent_path = root / 'build/validation/progress-format-corpus.json'
    parent = json.loads(parent_path.read_text())
    assert parent['key'] == '6dd529d376e06926'
    original = root / 'build/wsl-reports/raw_envelope_progress_format_full_native_corpus/execution-sources/rtl'
    folder = root / 'build/experiments/freeze-idle'
    target = folder / 'rtl'
    target.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for module, digest in parent['executed_parser_sha256'].items():
        source = original / (module + '.v')
        assert sha(source) == digest
        inputs[source_relative(source, root).as_posix()] = digest
        shutil.copy2(source, target / source.name)
    path = target / 'rpc_grpc_http2_return.v'
    old = 'assign idle=response_idle&&grant_idle&&arb_idle;'
    new = 'assign idle=!(freeze_valid&&freeze_ready)&&response_idle&&grant_idle&&arb_idle;'
    source = path.read_text()
    assert source.count(old) == 1
    updated = source.replace(old, new)
    assert updated.replace(new, old) == source
    stripped = re.sub(r'//[^\n]*|/\*.*?\*/', '', updated, flags=re.S)
    assert len(re.findall(r'(?<!\.)\bidle\b', stripped)) == 2
    path.write_text(updated)
    assert len(closure('http2_enveloped_parser_application', folder)) == 75
    generation = dict(parent_corpus_audit_key=parent['key'],
        generator_sha256=sha(Path(__file__)), inputs_sha256=inputs,
        outputs_sha256={'rtl/' + file.name: sha(file) for file in target.glob('*.v')},
        old_assignment=old, new_assignment=new, only_changed_module='rpc_grpc_http2_return',
        no_internal_idle_feedback=True, no_state_or_handshake_equations_changed=True,
        idle_difference_only_during_actual_freeze_handshake=True,
        scope_comparison_and_immediate_cancellation_unchanged=True,
        native_timing_improvement_verified=False, full_system_complete=False)
    (folder / 'generation.json').write_text(json.dumps(generation, indent=2) + '\n')
    print(json.dumps(dict(experiment=str(folder), exact_parser_modules=75,
                         only_changed_module='rpc_grpc_http2_return')))


if __name__ == '__main__':
    main()
