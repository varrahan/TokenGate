"""Replay shutdown recovery using the same durable send-window arena."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'sim/cocotb/test_raw_shutdown_faults.py'
    text=source.read_text()
    start=text.index('    # Global reset restarts the admission generation counter.')
    end=text.index('    b.closed.clear();b.configure();',start)
    text=text[:start]+'''    # Reuse the exact same durable arena. Production FORMAT/OPEN must
    # establish reusable state; this fixture never clears memory itself.
'''+text[end:]
    text=replace(text,'from test_raw_shutdown_controls import Bench',
        'from test_raw_shutdown_controls import Bench\nfrom retained_window_witness import RetainedWindowWitness')
    text=replace(text,'    for worker in(b.ready_driver(),b.observe(),b.actual_observer()):',
        '    window_retention=RetainedWindowWitness(d,b)\n    for worker in(b.ready_driver(),b.observe(),b.actual_observer(),window_retention.observe()):')
    text=replace(text,'fresh_disjoint_window_arena_per_global_reset=True',
        'fresh_disjoint_window_arena_per_global_reset=False')
    text=replace(text,'retained_window_arena_warm_reset_verified=False',
        'retained_window_arena_warm_reset_verified=True')
    folder=root/'build/experiments/retained-window-reset';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (folder/'generation.json').write_text(json.dumps(dict(generator_sha256=sha(Path(__file__)),
        source_sha256=sha(source),fixture_sha256=sha(output),actual_execution_verified=False,
        witness_sha256=sha(root/'sim/cocotb/retained_window_witness.py'),
        retained_window_arena=0x7f0000,no_bfm_memory_writes_added=True),indent=2)+'\n')
    print(output)


if __name__=='__main__':main()
