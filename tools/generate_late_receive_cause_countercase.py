"""Capture the actual worker/raw/public tuples at late receive-error loss."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/post-retire-fault-matrix/client_26_ack_0/test_raw_grpc_duplex.py'
    assertion="    assert (value(d,'packet_committed'),value(d,'packet_control_status'),value(d,'packet_control_memory_status'),value(d,'transport_packet_http2_error'))==(0,13,0x75,2)"
    text=replace(source.read_text(),assertion,
        '''    Path('failure.json').write_text(json.dumps(dict(
        actual_cleanup_result=sampled['retirement_result'],
        actual_public_result=[value(d,n) for n in ('packet_committed','packet_control_status','packet_control_memory_status','transport_packet_http2_error')],
        actual_raw_memory=value(d.dut.core.forward,'raw_memory'),
        actual_receive_error=[value(d,n) for n in ('receive_fault_status','receive_fault_detail','receive_fault_memory_status')],
        actual_ack_prefix=memory_fault.result()),indent=2)+'\\n')
'''+assertion)
    folder=root/'build/experiments/late-receive-cause-countercase';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'test_raw_grpc_duplex.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(output),
        actual_execution_verified=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(output)


if __name__=='__main__':main()
