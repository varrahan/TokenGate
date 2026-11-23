"""Bind actual admission/window fault execution to its regenerated RTL and wiring."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--snapshot-name', default='window_commit_admission_final_runner')
    args = parser.parse_args(); assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.snapshot_name)
    root = Path(__file__).resolve().parents[1]; sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    archive = root / 'build/wsl-reports' / ('http2_windowed_admission_' + args.snapshot_name)
    executed = archive / 'execution-sources'; inputs = json.loads((archive / 'inputs.json').read_text())
    report = json.loads((archive / 'report.json').read_text()); accepted = json.loads((archive / 'acceptance.json').read_text())
    snapshot = json.loads((archive / 'snapshot.json').read_text())
    assert report['phase'] == accepted['phase'] == 'passed' and snapshot['exit_code'] == 0
    assert report['input_sha256'] == inputs and report['acceptance_sha256'] == sha(archive / 'acceptance.json')
    assert report['tests'] == 1 and report['failures'] == 0
    for name, digest in inputs.items(): assert sha(executed / name) == digest, name
    xml = ET.parse(archive / 'results.xml'); tests = xml.findall('.//testcase')
    assert len(tests) == 1 and tests[0].attrib['name'] == 'real_admission_waits_for_window_commit_and_recovers_every_phase'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    assert accepted['header_transactions'] == 57 and accepted['actual_init_requests'] == 37
    assert accepted['init_memory_phases'] == accepted['injected_init_faults'] == 16
    assert accepted['double_fault_rollback_cases'] == 1
    assert accepted['memory_commands'] == [505, 1033, 842] and accepted['memory_writes'] == [380, 434, 356]
    assert all(accepted[n] for n in ('sidecar_and_window_acks_before_authority', 'actual_shared_directory_and_windows',
        'held_window_result_blocks_admission', 'trailer_preserves_debited_window', 'inherited_peer_initial_window_verified',
        'configuration_and_candidate_poisoning_verified', 'window_and_scratch_alias_rejected',
        'failed_init_never_publishes_authority', 'actual_rpc_rollback_verified', 'independent_recovery_domains_verified',
        'unaligned_runtime_pool_bases_verified', 'complete_model_prefix_immutable', 'connection_bootstrap_supplied_by_typed_fixture'))
    assert not accepted['full_forward_application_integrated'] and not accepted['full_system_complete']
    dependencies = {**closure('http2_windowed_rpc_admission', executed), **closure('http2_owned_keyed_windows', executed)}
    assert set(dependencies) == {'http2_windowed_rpc_admission', 'memory_command_slot', 'http2_owned_keyed_windows',
        'http2_keyed_send_window_store', 'grpc_pool_locked_stream_store', 'grpc_stream_store'}
    admission = (executed / 'rtl/http2_windowed_rpc_admission.v').read_text()
    assert 'else if(word_index==7)begin if(trailer)publish;else state<=WINDOW_REQ;end' in admission
    assert 'WINDOW_REQ:if(init_ready)state<=WINDOW_WAIT;' in admission
    assert 'WINDOW_WAIT:if(init_result_valid)begin' in admission and 'if(init_status==0)publish;' in admission
    assert 'action<=ACT_CLOSE;control_op<=3;state<=CONTROL_REQ;' in admission
    assert "quarantine(init_recovery_required?init_recovery_address:rpc_address,8'd22,init_memory_status)" in admission
    assert 'assign init_cfg_stream_base=streams;assign init_cfg_stream_bytes=stream_bytes;' in admission
    harness = (executed / 'sim/cocotb_windowed_admission_top.sv').read_text()
    assert len(re.findall(r'http2_owned_keyed_windows\s*#', harness)) == 1
    assert 'assign init_result_valid=win_owner==1&&s_window_rsp_valid;' in harness
    assert '.window_req_op(init_valid?4\'d1:window_req_op)' in harness
    assert '.window_req_generation(init_valid?init_generation:window_req_generation)' in harness
    assert '.cfg_pool_base(control_valid?control_pool_base:host_cfg_pool_base)' in harness
    reference = json.loads((executed / 'build/http2-send-window-fixtures/cases.json').read_text())
    assert reference['original_image_sha256'] == sha(executed / 'build/http2-send-window-fixtures/model.bin')
    assert reference['original_image_sha256'] == sha(root / 'build/scu35/image/external_memory.bin')
    # Regenerate the admission RTL and actual service harness from the frozen
    # original implementation, rather than accepting generated labels alone.
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]
    replay = root / 'build/validation/windowed-admission-generation-replay' / key
    if not replay.exists(): shutil.copytree(executed, replay)
    (replay / 'build/validation').mkdir(parents=True, exist_ok=True)
    for name in ('generate_windowed_rpc_admission.py', 'generate_cocotb_windowed_admission.py'):
        subprocess.run([sys.executable, str(replay / 'tools' / name)], check=True, capture_output=True)
    for name in ('rtl/http2_windowed_rpc_admission.v', 'sim/cocotb_windowed_admission_top.sv'):
        assert sha(replay / name) == inputs[name], ('Regeneration differs', name)
    files = {Path('execution') / name: executed / name for name in inputs}
    files.update({Path('reports') / name: archive / name for name in ('report.json', 'inputs.json', 'snapshot.json',
        'results.xml', 'acceptance.json', 'simulation.log', 'build.log')})
    files[Path('verification/verify_windowed_rpc_admission.py')] = Path(__file__)
    digest = hashlib.sha256(''.join(str(n) + sha(p) for n, p in sorted(files.items())).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/windowed-rpc-admission-evidence' / digest
    for relative, source in files.items():
        target = evidence / relative; target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists(): assert sha(target) == sha(source)
        else: shutil.copy2(source, target)
    result = dict(phase='actual_admission_window_commit_functional_passed', verified_utc=datetime.now(timezone.utc).isoformat(),
        acceptance=accepted, execution_inputs=len(inputs), actual_rtl_modules=list(dependencies),
        exact_rtl_and_harness_regeneration_verified=True, single_actual_directory_verified=True,
        current_primary_differences=[n for n, h in inputs.items() if not (source_path(root, n)).is_file() or sha(source_path(root, n)) != h],
        admission_native_timing_verified=False, complete_forward_application_joined=False,
        automatic_connection_bootstrap_verified=False, raw_control_integrated=False,
        full_system_complete=False, verifier_sha256=sha(Path(__file__)), evidence_folder=str(evidence))
    (root / 'build/validation/windowed-rpc-admission.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
