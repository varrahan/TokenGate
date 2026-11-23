"""Observe the captured private grant in the existing full-model scenarios."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'build/experiments/window-authority';files={}
    for name,source in (
        ('sim',root/'build/experiments/window-format/sim/test_raw_shutdown_faults.py'),
        ('drain',root/'build/experiments/window-format/drain/test_raw_shutdown_faults.py'),
        ('external',root/'build/experiments/window-authority-case/test_raw_shutdown_faults.py')):
        text=replace(source.read_text(),'from window_format_witness import WindowFormatWitness as ReceiveFormatWitness',
            'from private_window_format_witness import PrivateWindowFormatWitness as ReceiveFormatWitness')
        output=folder/name/'test_raw_shutdown_faults.py';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(text)
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        files[name]=dict(source=str(source_relative(source, root)),source_sha256=sha(source),fixture_sha256=sha(output))
    result=dict(generator_sha256=sha(Path(__file__)),files=files,
        witness_sha256=sha(root/'sim/cocotb/private_window_format_witness.py'),
        base_witness_sha256=sha(root/'sim/cocotb/window_format_witness.py'),actual_execution_verified=False)
    (folder/'case-generation.json').write_text(json.dumps(result,indent=2)+'\n');print(folder)


if __name__=='__main__':main()
