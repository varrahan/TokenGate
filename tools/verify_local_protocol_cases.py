"""Verify native/RFC connection-error cleanup on the actual two-FPGA RTL."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    folder = root / 'build/experiments/local-protocol-cases'
    generation = json.loads((folder/'generation.json').read_text())
    baseline = json.loads((root/'build/validation/packer-keep-experiment.json').read_text())
    positive = baseline['executions']['credit_cancel']['acceptance']
    cache, executions = {}, {}

    def checked_closure(top, source, inputs):
        signature = (top,tuple(sorted((n,h) for n,h in inputs.items() if n.startswith('rtl/') and n.endswith('.v'))))
        if signature not in cache:
            cache[signature] = {n:p.relative_to(source) for n,p in closure(top,source).items()}
        return {n:source/p for n,p in cache[signature].items()}

    for name, expected in generation['cases'].items():
        snapshot = 'packer_keep_protocol_' + name
        archive = root/'build/wsl-reports'/('raw_envelope_'+snapshot)
        source = archive/'execution-sources'
        inputs = json.loads((archive/'inputs.json').read_text())
        report = json.loads((archive/'report.json').read_text())
        state = json.loads((archive/'snapshot.json').read_text())
        accepted = json.loads((archive/'acceptance.json').read_text())
        assert state['exit_code'] == 0 and report['phase'] == accepted['phase'] == 'passed'
        assert report['profile'] == state['profile'] == 'duplex' and report['tests'] == 1 and report['failures'] == 0
        assert report['input_sha256'] == inputs and report['acceptance_sha256'] == sha(archive/'acceptance.json')
        for n,h in inputs.items():
            assert sha(source/n) == h, (name,n)
            if n.startswith('native-vendor/'):
                assert sha(root/'.venv312/Lib/site-packages'/n.split('/',1)[1]) == h
        xml = ET.parse(archive/'results.xml')
        assert len(xml.findall('.//testcase')) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        assert inputs['sim/cocotb/test_raw_grpc_duplex.py'] == expected['test_sha256']
        assert inputs['sim/cocotb/local_error_protocol_witness.py'] == generation['input_sha256']['sim/cocotb/local_error_protocol_witness.py']
        for top, label, size in (('http2_enveloped_parser_application','parser',75),('tokenizer_fpga_memory_subsystem','tokenizer',22)):
            dag = checked_closure(top,source,inputs)
            assert len(dag) == size
            assert {n:sha(p) for n,p in dag.items()} == baseline['executed_'+label+'_sha256']
        previous = baseline['executions']['credit_cancel']['inputs_sha256']
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n] == previous[n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        assert accepted['actual_protocol_case'] == name and accepted['invalid_frame_hex'] == expected['invalid_frame_hex']
        assert accepted['actual_connection_http2_error'] == expected['expected_http2_error']
        assert accepted['native_reference_http2_error'] == expected['native_http2_error']
        proof = accepted['local_error_ownership']
        assert proof['actual_goaway_and_host_close_http2_error'] == expected['expected_http2_error']
        assert proof['held_goaway_cycles'] == 17 and proof['held_host_close_cycles'] == 13
        assert proof['wire_retired_clock'] < proof['host_close_retired_clock'] < proof['first_public_packet_result_clock']
        trace = accepted['actual_cancel_trace']
        assert [e['event'] for e in trace] == ['actual_freeze_drained','actual_fatal_close_request',
            'actual_send_closed_write_ack','actual_fatal_close_result_ack','actual_closed_reservation']
        assert all(a['clock'] < b['clock'] for a,b in zip(trace,trace[1:]))
        assert trace[-1]['clock'] < proof['wire_retired_clock']
        assert trace[2]['address'] == 0x7f0008 and trace[2]['data'] == (1<<63)|(1<<32)
        assert [trace[3][n] for n in ('user','stream','generation','address')] == [0,1,1,7232000]
        assert [trace[-1][n] for n in ('status','error','memory_status')] == [8,5,0]
        for key in ('actual_captured_dma_ids','actual_gpu_cancellation_result','actual_closed_reservation_status',
                    'actual_gpu_lease_retained_until_result_ack','actual_no_new_credit_required',
                    'ordinary_host_fatal_opcode_denied_before_memory','actual_goaway_after_gpu_retirement',
                    'actual_reopen_without_global_reset','actual_same_rpc_address','actual_reused_generation',
                    'actual_reopened_dma_ids_returned','actual_reopened_native_response_hex','actual_reopened_successful_close_refund'):
            assert accepted[key] == positive[key], (name,key)
        executions[name] = dict(snapshot=snapshot,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    assert len(executions) == 7
    deviations = [n for n,c in generation['cases'].items() if not c['native_error_code_matches_normative_requirement']]
    assert deviations == generation['known_native_reference_error_code_deviations'] == ['settings_ack_nonempty']
    ack = generation['cases']['settings_ack_nonempty']
    assert ack['native_http2_error'] == 1 and ack['expected_http2_error'] == 6
    assert ack['normative_source'] == 'https://www.rfc-editor.org/rfc/rfc9113.html#section-6.5'
    replay = root/'build/validation/local-protocol-generation-replay'
    paths = set(generation['input_sha256']) | {'tools/generate_local_protocol_cases.py',
        'tools/generate_receive_pool_experiment.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py'}
    assert generation['generator_sha256'] == sha(root/'tools/generate_local_protocol_cases.py')
    for n in paths:
        assert n not in generation['input_sha256'] or sha(source_path(root, n)) == generation['input_sha256'][n]
        destination = replay/n
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source_path(root, n),destination)
    subprocess.run([sys.executable,str(replay/'tools/generate_local_protocol_cases.py')],check=True,capture_output=True,text=True)
    replayed = json.loads((replay/'build/experiments/local-protocol-cases/generation.json').read_text())
    assert replayed == generation
    result = dict(phase='seven_actual_connection_error_cases_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,executed_parser_sha256=baseline['executed_parser_sha256'],
        executed_tokenizer_sha256=baseline['executed_tokenizer_sha256'],baseline_direct_audit_key=baseline['key'],
        exact_parser_modules=75,exact_tokenizer_modules=22,parser_memory_clients=19,tokenizer_memory_clients=9,
        actual_native_zero_window_gpu_cancellation_verified=True,actual_goaway_and_host_close_order_verified=True,
        actual_same_arena_reopen_and_captured_dma_return_verified=True,complete_model_and_native_reference_verified=True,
        normative_settings_ack_frame_size_error_verified=True,native_reference_deviation_explicitly_recorded=deviations,
        generation_sha256=sha(folder/'generation.json'),generator_and_native_case_replay_verified=True,
        stream_error_scope_matrix_verified=False,complete_connection_error_matrix_verified=False,
        physical_transport_close_verified=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence = root/'build/validation/local-protocol-evidence'/key
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),folder/'generation.json',root/'tools/generate_local_protocol_cases.py',root/'sim/cocotb/local_error_protocol_witness.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/local-protocol-cases.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,cases=len(executions),native_reference_deviations=deviations)))


if __name__=='__main__':
    main()
