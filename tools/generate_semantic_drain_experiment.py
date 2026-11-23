"""Retain failed-packet ownership through actual matching GPU retirement."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_receive_pool_experiment import replace

from rtl_paths import source_relative


def main():
    root=Path(__file__).resolve().parents[1]
    previous=root/'build/experiments/packer-keep/rtl'
    folder=root/'build/experiments/semantic-drain'
    target=folder/'rtl';target.mkdir(parents=True,exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs={}
    for p in previous.glob('*.v'):
        shutil.copy2(p,target/p.name);inputs[source_relative(p, root).as_posix()]=sha(p)
    path=target/'http2_enveloped_parser_core.v'
    text=path.read_text()
    text=replace(text,
        '!receive_recovery_required&&!response_recovery_required&&!journal_recovery_required&&!shutdown_recovery_required;',
        '!receive_recovery_required&&!response_recovery_required&&!shutdown_recovery_required;')
    text=replace(text,'wire local_error_fence=',
        '// A protocol failure may fence journal replay without an uncertain memory ACK.\n'
        '// Actual closed-context/history reads still authorize GOAWAY; memory and\n'
        '// other uncertain owners remain excluded by local_error_needed above.\n'
        'wire local_error_owned_return=receive_connection_closing&&local_packet_valid&&!local_packet_committed&&\n'
        '    ((return_pending&&local_return_scope_match)||(generated_offered&&s_axis_generated_tuser==receive_connection_user));\n'
        'wire local_error_fence=')
    text=replace(text,'assign packet_result_valid=local_packet_valid&&(',
        'assign packet_result_valid=local_packet_valid&&!local_error_owned_return&&(')
    text=replace(text,'assign local_packet_ready=packet_result_ready&&(',
        'assign local_packet_ready=packet_result_ready&&!local_error_owned_return&&(')
    text=replace(text,'assign local_error_rsp_ready=local_error_started&&local_packet_valid&&packet_result_ready;',
        'assign local_error_rsp_ready=local_error_started&&local_packet_valid&&packet_result_ready&&!local_error_owned_return;')
    path.write_text(text)
    result=dict(phase='semantic_failure_completion_drain_generated',generator_sha256=sha(Path(__file__)),input_sha256=inputs,
        generated_sha256={p.name:sha(p) for p in target.glob('*.v')},
        matching_gpu_completion_barrier=True,journal_protocol_fence_allows_authoritative_goaway=True,
        memory_error_goaway_exclusion_preserved=True,actual_runtime_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(target)


if __name__=='__main__':main()
