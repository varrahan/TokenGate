"""Distinguish pre-existing errors from actual late-cleanup receive faults."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/window-format/rtl'
    folder=root/'build/experiments/window-cause';target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={source_relative(p, root).as_posix():sha(p) for p in previous.glob('*.v')}
    for p in previous.glob('*.v'):shutil.copy2(p,target/p.name)
    name='http2_classified_parser_transport';text=(previous/(name+'.v')).read_text()
    declaration='    reg [7:0] prior_abort_control_error,prior_abort_control_cause,prior_abort_control_memory,prior_abort_raw_detail,prior_abort_raw_memory;\n'
    text=replace(text,'    reg [7:0] command_control_error,',declaration+'    reg [7:0] command_control_error,')
    text=replace(text,'packet_control_memory<=0;control_packet_active<=0;control_early_failed<=0;',
        'packet_control_memory<=0;control_packet_active<=0;control_early_failed<=0;\n'
        '            prior_abort_control_error<=0;prior_abort_control_cause<=0;prior_abort_control_memory<=0;prior_abort_raw_detail<=0;prior_abort_raw_memory<=0;')
    text=replace(text,'                POST_ABORT_SEND:if(p_post_abort_ready)state<=POST_ABORT_WAIT;',
        '''                POST_ABORT_SEND:if(p_post_abort_ready)begin
                    // Sample before cleanup can raise the shared receive fault.
                    prior_abort_control_error<=packet_control_error;
                    prior_abort_control_cause<=packet_control_cause;
                    prior_abort_control_memory<=packet_control_memory;
                    prior_abort_raw_detail<=raw_detail;prior_abort_raw_memory<=raw_memory;
                    state<=POST_ABORT_WAIT;
                end''')
    text=replace(text,'''                        // A recovery rejection may carry no new memory status.
                        // Keep the original uncertain ACK and its cause rather
                        // than replacing it with the cleanup service's zero.
                        if(packet_control_memory==0&&raw_memory==0)begin
                            packet_control_error<=p_post_abort_status;packet_control_cause<=p_post_abort_detail;
                            packet_control_memory<=p_post_abort_memory_status;
                            raw_detail<=p_post_abort_detail;raw_memory<=p_post_abort_memory_status;
                        end else if(packet_control_memory!=0)begin
                            raw_detail<=packet_control_cause;raw_memory<=packet_control_memory;
                        end''',
        '''                        // A new cleanup receive error also updates raw_memory
                        // asynchronously. It must not masquerade as an earlier
                        // cause and suppress its own public control error.
                        if(prior_abort_control_memory!=0)begin
                            packet_control_error<=prior_abort_control_error;packet_control_cause<=prior_abort_control_cause;
                            packet_control_memory<=prior_abort_control_memory;
                            raw_detail<=prior_abort_control_cause;raw_memory<=prior_abort_control_memory;
                        end else if(prior_abort_raw_memory!=0)begin
                            packet_control_error<=prior_abort_control_error!=0?prior_abort_control_error:p_post_abort_status;
                            packet_control_cause<=prior_abort_raw_detail;packet_control_memory<=prior_abort_raw_memory;
                            raw_detail<=prior_abort_raw_detail;raw_memory<=prior_abort_raw_memory;
                        end else begin
                            packet_control_error<=p_post_abort_status;packet_control_cause<=p_post_abort_detail;
                            packet_control_memory<=p_post_abort_memory_status;
                            raw_detail<=p_post_abort_detail;raw_memory<=p_post_abort_memory_status;
                        end''')
    (target/(name+'.v')).write_text(text)
    result=dict(phase='cleanup_receive_memory_cause_capture_generated',generator_sha256=sha(Path(__file__)),
        input_sha256=inputs,generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        only_changed_module='http2_classified_parser_transport',
        original_causes_sampled_before_actual_cleanup_request=True,actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(target)


if __name__=='__main__':main()
