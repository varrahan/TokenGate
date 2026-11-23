"""Add a passive memory observer to the executed native idle-RST cleanup case."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/post-commit-retire/sim/rst_idle_stream/test_raw_grpc_duplex.py'
    witness=root/'sim/cocotb/post_retire_memory_witness.py'
    folder=root/'build/experiments/post-retire-memory-trace';folder.mkdir(exist_ok=True)
    text=replace(source.read_text(),'from post_commit_retire_witness import PostCommitRetireWitness',
        'from post_commit_retire_witness import PostCommitRetireWitness\nfrom post_retire_memory_witness import PostRetireMemoryWitness')
    text=replace(text,'    retirement = PostCommitRetireWitness(d,b)',
        '    retirement = PostCommitRetireWitness(d,b)\n    memory_trace = PostRetireMemoryWitness(d)')
    text=replace(text,'retirement.observe()]','retirement.observe(), memory_trace.observe()]')
    text=replace(text,'        actual_post_commit_retirement=retirement.result(True),',
        '        actual_retirement_memory=memory_trace.result(),\n        actual_post_commit_retirement=retirement.result(True),')
    output=folder/'test_raw_grpc_duplex.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),witness_sha256=sha(witness),
        fixture_sha256=sha(output),actual_execution_verified=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(output)


if __name__=='__main__':main()
