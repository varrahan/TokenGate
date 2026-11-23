"""Reuse actual owned-GPU drain stimulus with both-ledger passive observation."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/receive-format/drain/test_raw_shutdown_faults.py'
    text=replace(source.read_text(),'from receive_format_witness import ReceiveFormatWitness',
        'from window_format_witness import WindowFormatWitness as ReceiveFormatWitness')
    folder=root/'build/experiments/window-format/drain';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(output),
        witness_sha256=sha(root/'sim/cocotb/window_format_witness.py'),actual_execution_verified=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(output)


if __name__=='__main__':main()
