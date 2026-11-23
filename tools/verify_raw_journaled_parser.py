"""Audit real raw control effects, ACK arbitration and the complete Parser closure."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-name',default='actual_raw_journaled_controls_drains')
    parser.add_argument('--full',action='store_true');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.snapshot_name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    archive=root/'build/wsl-reports'/('cocotb_two_fpga_journaled_'+args.snapshot_name);executed=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    snapshot=json.loads((archive/'snapshot.json').read_text());inputs={**report['source_sha256'],**report['fixture_sha256']}
    assert report['phase']==accepted['phase']=='passed'and report['suite']=='two_fpga_journaled'
    assert report['tests']==1 and report['failures']==0 and snapshot['runner_exit_code']==0 and snapshot['phase']=='snapshot_run_archived'
    assert snapshot['execution_report_sha256']==sha(archive/'report.json')and report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert snapshot['snapshot_runner_sha256']==sha(executed/'scripts/run_cocotb_snapshot.py')
    for n,h in inputs.items():assert sha(executed/n)==h==snapshot['source_and_fixture_sha256'][n],n
    xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
    expected='raw_requests_dma_returns_committed_peer_controls_and_ack_tx'if args.full else'raw_packets_commit_real_windows_and_retire_native_acks'
    assert len(tests)==1 and tests[0].attrib['name']==expected and not xml.findall('.//failure')and not xml.findall('.//error')
    p=closure('http2_journaled_parser_application',executed);t=closure('tokenizer_fpga_memory_subsystem',executed)
    assert len(p)==60 and len(t)==22
    assert {'http2_journaled_controls','http2_control_executor','http2_control_journal','axis_frame_arbiter',
        'http2_owned_keyed_windows','grpc_pool_locked_stream_store','grpc_stream_store'}<=p.keys()
    assert not {'bpe_tokenizer_engine','detokenizer_engine'}&p.keys()
    harness=(executed/'sim/cocotb_two_fpga_journaled_top.sv').read_text()
    assert 'external_memory_fabric #(.CLIENTS(15)) p_fabric('in harness and 'tokenizer_fpga_memory_subsystem #'in harness
    transport=(executed/'rtl/http2_journaled_parser_transport.v').read_text()
    assert 'state<=init_window_rsp_status==0?CONTROL_OPEN_SEND:WINDOW_CLOSE_SEND;'in transport
    assert 'CONTROL_PACKET_WAIT:if(ctl_result_valid||ctl_finish_ready)state<=PACKET_START;'in transport
    assert 'assign ctl_finish_commit=p_packet_committed&&!packet_fatal;'in transport
    assert 'state==CONTROL_DRAIN&&!first_valid'in transport and 'control_early_failed?CLOSE_SEND:CONTROL_FINISH_SEND'in transport
    assert 'assign packet_committed=p_packet_committed&&packet_control_error==0;'in transport
    core=(executed/'rtl/http2_journaled_parser_core.v').read_text()
    assert 'axis_frame_arbiter #'in core and '.b_axis_tdata(ack_m_axis_tx_tdata)'in core
    assert '.mem_valid(mem_valid[23*1+:1])'in core
    assert 'assign flow_event_ready=control_drop_events?1\'b1:ctl_flow_ready;'in core
    assert '.s_valid(flow_event_valid&&!control_drop_events)'in core
    assert 'else if(ctl_window_req_valid)window_owner<=5;'in core
    if args.full:
        assert accepted['messages']==16 and accepted['token_ids']==accepted['response_chunks']==2828 and accepted['response_bytes']==144686
        assert accepted['positive_grants']==accepted['response_data_frames']and accepted['native_settings_ack_frames']==9
        assert accepted['connection_initializations']==7 and accepted['stream_initializations']==17 and accepted['zero_grants']>0
        assert all(accepted[n]for n in('raw_control_commit_and_replay_verified','no_fixture_credit_updates','independent_credit_model_verified',
            'durable_debits_before_data_verified','actual_dma_ids_returned','frame_arbitration_verified','separate_memory_banks_verified','model_and_policy_immutable'))
        assert accepted['parser_memory_clients']==15 and accepted['tokenizer_memory_clients']==9
    else:
        assert accepted['raw_control_packets']==13 and accepted['actual_header_bindings']==1 and accepted['native_ack_frames']==8
        assert all(accepted[n]for n in('raw_settings_and_window_updates_applied_by_rtl','partial_settings_do_not_apply','aborted_update_does_not_apply',
            'actual_headers_allocate_stream_window','no_fixture_credit_updates','native_ack_bytes_verified','raw_restore_fault_drained_and_reopened',
            'raw_head_commit_fault_no_duplicate_ack','raw_staging_fault_drains_flow','multi_beat_failed_packets_drained',
            'independent_banks_verified','complete_model_prefix_immutable','tokenizer_bank_untouched'))
        assert accepted['actual_parser_memory_clients']==15 and accepted['actual_tokenizer_memory_clients']==9
    assert accepted['non_window_notice_callbacks_supplied_by_fixture']and not accepted['postcommit_gpu_cancellation_verified']and not accepted['full_system_complete']
    reference=json.loads((executed/'build/bidirectional-fixtures/journaled_control_reference.json').read_text())
    assert reference['generator_sha256']==inputs['tools/generate_raw_journal_control_vectors.py']and reference['packages']['hyperframe']=='6.1.0'
    key=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
    replay=root/'build/validation/raw-journaled-parser-generation-replay'/key
    if not replay.exists():shutil.copytree(executed,replay)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    for script,options in(('generate_http2_journaled_parser.py',[]),('generate_two_fpga_harness.py',['--tokenizer-memory','--journaled-parser']),
        ('generate_raw_journal_control_vectors.py',[])):
        subprocess.run([sys.executable,str(replay/'tools'/script),*options],check=True,capture_output=True)
    generated=['rtl/'+n+'.v'for n in('http2_journaled_parser_transport','http2_journaled_parser_core','http2_journaled_parser_application')]
    generated +=['sim/cocotb_two_fpga_journaled_top.sv','build/bidirectional-fixtures/journaled_control_reference.json']
    for n in generated:assert sha(replay/n)==inputs[n],n
    directory_parents=[n for n,path in p.items()if re.search(r'\bgrpc_stream_store\s*#\([^;]*\)\s+store\s*\(',path.read_text(),re.S)]
    assert directory_parents==['grpc_pool_locked_stream_store']
    files={Path('execution')/n:executed/n for n in inputs}
    files[Path('execution/scripts/run_cocotb_snapshot.py')]=executed/'scripts/run_cocotb_snapshot.py'
    for n in('report.json','snapshot.json','acceptance.json','simulation.log','build.log','results.xml','native-reference.json'):files[Path('reports')/n]=archive/n
    files[Path('verification/verify_raw_journaled_parser.py')]=Path(__file__)
    digest=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/raw-journaled-parser-evidence'/digest
    for n,path in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(path)
        else:shutil.copy2(path,target)
    result=dict(phase='raw_journaled_full_data_execution_verified'if args.full else'raw_journaled_control_fault_execution_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),snapshot=args.snapshot_name,acceptance=accepted,
        execution_sources=len(report['source_sha256']),execution_fixtures=len(report['fixture_sha256']),parser_modules=list(p),tokenizer_modules=list(t),
        exact_join_harness_and_native_reference_regeneration_verified=True,single_actual_directory_verified=True,
        current_primary_differences=[n for n,h in inputs.items()if not(root/n).is_file()or sha(root/n)!=h],
        current_active_rtl_matches=all(sha(root/path.relative_to(executed))==sha(path)for path in p.values()),
        full_data_execution_verified=args.full,non_window_controllers_verified=False,postcommit_gpu_cancellation_verified=False,
        complete_parser_native_timing_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    output='raw-journaled-parser-full.json'if args.full else'raw-journaled-parser-controls.json'
    (root/'build/validation'/output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
