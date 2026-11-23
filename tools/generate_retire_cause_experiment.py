"""Preserve an original memory failure when later retirement is rejected."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/pending-idle/rtl'
    folder=root/'build/experiments/retire-cause';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inputs={}
    for p in source.glob('*.v'):
        inputs[source_relative(p, root).as_posix()]=sha(p);shutil.copy2(p,target/p.name)
    path=source/'http2_classified_parser_transport.v'
    text=replace(path.read_text(),'''                        packet_control_error<=p_post_abort_status;packet_control_cause<=p_post_abort_detail;
                        packet_control_memory<=p_post_abort_memory_status;raw_status<=11;
                        raw_detail<=p_post_abort_detail;raw_memory<=p_post_abort_memory_status;raw_h2<=2;''',
        '''                        // A recovery rejection may carry no new memory status.
                        // Keep the original uncertain ACK and its cause rather
                        // than replacing it with the cleanup service's zero.
                        if(packet_control_memory==0&&raw_memory==0)begin
                            packet_control_error<=p_post_abort_status;packet_control_cause<=p_post_abort_detail;
                            packet_control_memory<=p_post_abort_memory_status;
                            raw_detail<=p_post_abort_detail;raw_memory<=p_post_abort_memory_status;
                        end else if(packet_control_memory!=0)begin
                            raw_detail<=packet_control_cause;raw_memory<=packet_control_memory;
                        end
                        raw_status<=11;raw_h2<=2;''')
    (target/path.name).write_text(text)
    result=dict(phase='original_retirement_memory_cause_preservation_generated',generator_sha256=sha(Path(__file__)),
        input_sha256=inputs,generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        only_changed_module_from_idle_guard='http2_classified_parser_transport',
        original_nonzero_memory_cause_retained=True,new_memory_failure_reported_when_no_prior_memory_error=True,
        secondary_retirement_pending_and_recovery_ownership_unchanged=True,
        actual_shutdown_counterexample_replay_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(target)


if __name__=='__main__':main()
