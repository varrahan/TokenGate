"""Move the closed-record upper-bound arithmetic to the existing CHECK cycle."""
import hashlib
import json
from pathlib import Path
import shutil


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root / 'build/experiments/registered-close-scope/rtl'
    source = root / 'rtl/rpc_http2_response_partition.v'
    text = source.read_text()
    assert text.count('checked_stream_end') == 4
    old = 'wire closed_address_good=closed_address>=streams&&{1\'b0,closed_address}+128<=checked_stream_end&&((closed_address-streams)&127)==0;'
    new = 'wire closed_address_good=closed_address>=streams&&{1\'b0,closed_address}<=checked_stream_last&&closed_address[6:0]==streams[6:0];'
    assert text.count(old) == 1
    text = text.replace(old, new)
    assert text.count('checked_stream_end<=stream_end;') == 1
    text = text.replace('checked_stream_end<=stream_end;', 'checked_stream_last<=stream_end-64\'d128;')
    text = text.replace('checked_stream_end', 'checked_stream_last')
    start = text.index('    // CHECK already validates the captured pool.')
    end = text.index('    reg [63:0] checked_stream_last;', start)
    text = text[:start] + '''    // CHECK validates at least one complete 128-byte record. Capture the
    // last legal record start there, removing address+128 from the live
    // acknowledged-close path. Relative alignment uses equal low seven bits.
    // DREQ still starts on the same edge and observes later actual closes.
''' + text[end:]
    target = root / 'build/experiments/checked-close-address/rtl'
    target.mkdir(parents=True, exist_ok=True)
    (target / source.name).write_text(text)
    for name in ('grpc_response_headers.v', 'rpc_grpc_http2_return.v'):
        shutil.copy2(previous / name, target / name)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(phase='isolated_checked_close_address_generated',
        source_sha256=sha(source), generator_sha256=sha(Path(__file__)),
        previous_overrides={p.name: sha(p) for p in previous.glob('*.v')},
        generated_sha256={p.name: sha(p) for p in target.glob('*.v')},
        production_rtl_changed=False, functional_equivalence_verified=False,
        routed_timing_verified=False, full_system_complete=False)
    (target.parent / 'generation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
