"""Keep a pending window request out of quiescence before scope authorization."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/post-commit-retire/rtl'
    folder=root/'build/experiments/pending-idle';target=folder/'rtl'
    target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={}
    for source in previous.glob('*.v'):
        inputs[source.relative_to(root).as_posix()]=sha(source)
        shutil.copy2(source,target/source.name)
    source=previous/'http2_enveloped_frame_grants.v'
    old='assign idle=owned_idle&&state==IDLE&&!frame_active&&!start_valid&&!frozen&&!wire_pending&&!tracking_error;'
    new='assign idle=owned_idle&&state==IDLE&&!window_req_valid&&!frame_active&&!start_valid&&!frozen&&!wire_pending&&!tracking_error;'
    text=source.read_text()
    assert text.count('idle')>=2
    candidate=replace(text,old,new)
    (target/source.name).write_text(candidate)
    assert candidate.replace(new,old)==text
    result=dict(phase='pending_request_idle_guard_generated',generator_sha256=sha(Path(__file__)),input_sha256=inputs,
        generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        only_changed_module='http2_enveloped_frame_grants',only_changed_output='idle',
        old_assignment=old,new_assignment=new,no_state_or_handshake_equations_changed=True,
        idle_difference_possible_only_when_window_request_pending=True,
        no_registered_or_stale_quiescence_used=True,actual_joined_behavior_verified=False,
        native_timing_improvement_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
