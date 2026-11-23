"""Prepare an isolated bounds-cone candidate without editing live RTL."""
import hashlib
import json
from pathlib import Path

from rtl_paths import source_path, source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    source = source_path(root, 'rtl/bpe_external_merge_unit.v')
    original = source.read_text()
    old = """    wire [63:0] index_end=64'd8*address_index+8;
    wire store_good=index_end<=capacity&&byte_address+8<=(64'd1<<MEMORY_ADDR_WIDTH);"""
    new = """    // STORE_CHECK always checks store_index. Keep this bounds cone separate
    // from the state-selected address mux used by memory commands, avoiding
    // state -> address mux -> add/compare -> state feedback on this decision.
    wire [63:0] store_end=64'd8*store_index+8;
    wire store_good=store_end<=capacity&&{1'b0,base}+store_end<=(64'd1<<MEMORY_ADDR_WIDTH);"""
    assert original.count(old) == 1
    candidate = original.replace(old, new)
    output = root / 'build/merge-store-bounds-candidate'
    output.mkdir(exist_ok=False)
    baseline = output / 'baseline-bpe_external_merge_unit.v'
    baseline.write_bytes(source.read_bytes())
    target = output / source.name
    target.write_text(candidate)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(phase='isolated_candidate_prepared', baseline_source=str(source_relative(source, root)),
                  baseline_sha256=sha(source), candidate=str(source_relative(target, root)), candidate_sha256=sha(target),
                  generator_sha256=sha(Path(__file__)), primary_rtl_changed=False,
                  functional_acceptance_verified=False, timing_verified=False)
    (output / 'candidate.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
