"""Audit actual initialized raw Parser execution without claiming raw-control TX."""
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
    parser=argparse.ArgumentParser();parser.add_argument('--bootstrap-only',action='store_true')
    parser.add_argument('--snapshot-name',default='actual_initialized_raw_hyperframe')
    parser.add_argument('--bootstrap-snapshot',default='actual_initialized_bootstrap_faults');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name in(args.snapshot_name,args.bootstrap_snapshot):assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',name)
    files={};details={}
    selections=[('bootstrap',args.bootstrap_snapshot)]
    if not args.bootstrap_only:selections.append(('full',args.snapshot_name))
    for label,name in selections:
        archive=root/'build/wsl-reports'/('cocotb_two_fpga_initialized_'+name);executed=archive/'execution-sources'
        report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
        snapshot=json.loads((archive/'snapshot.json').read_text())
        assert report['phase']==accepted['phase']=='passed'and report['suite']=='two_fpga_initialized'
        assert snapshot['phase']=='snapshot_run_archived'and snapshot['runner_exit_code']==0
        assert report['tests']==1 and report['failures']==0 and report['acceptance_sha256']==sha(archive/'acceptance.json')
        assert snapshot['execution_report_sha256']==sha(archive/'report.json')
        assert snapshot['snapshot_runner_sha256']==sha(executed/'scripts/run_cocotb_snapshot.py')
        inputs={**report['source_sha256'],**report['fixture_sha256']}
        for relative,digest in inputs.items():
            assert sha(executed/relative)==digest==snapshot['source_and_fixture_sha256'][relative]
            files[Path(label)/'execution'/relative]=executed/relative
        xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
        expected='actual_connection_bootstrap_all_memory_faults_and_cleanup_failure'if label=='bootstrap'else'raw_open_headers_dma_and_actual_durable_return'
        assert len(tests)==1 and tests[0].attrib['name']==expected
        assert not xml.findall('.//failure')and not xml.findall('.//error')
        active=closure('http2_initialized_parser_application',executed)
        token=closure('tokenizer_fpga_memory_subsystem',executed)
        assert len(active)==56 and len(token)==22
        assert {'http2_windowed_rpc_admission','http2_initialized_parser_transport','rpc_grpc_initialized_return',
            'http2_keyed_frame_grants','http2_owned_keyed_windows','grpc_pool_locked_stream_store','grpc_stream_store'}<=active.keys()
        assert not {'bpe_tokenizer_engine','detokenizer_engine'}&active.keys()
        assert {'bpe_tokenizer_engine','detokenizer_engine','external_memory_fabric'}<=token.keys()
        source=(executed/'rtl/http2_initialized_parser_transport.v').read_text()
        assert 'if(saved_command_op==0&&r_rsp_status==0)state<=WINDOW_OPEN_REQ;'in source
        assert 'state<=init_window_rsp_status==0?WINDOW_OPEN_RESULT:WINDOW_CLOSE_SEND;'in source
        assert 'WINDOW_CLOSE_WAIT:if(r_rsp_valid)begin window_command_cleanup<=r_rsp_status;state<=WINDOW_OPEN_RESULT;end'in source
        assert 'assign init_window_req_valid=boot_window||a_init_valid;'in source
        assert "assign init_window_req_op=boot_window?4'd0:4'd1;"in source
        core=(executed/'rtl/http2_initialized_parser_core.v').read_text()
        assert '3:if(window_req_valid&&service_window_req_ready)window_owner<=4;'in core
        assert '.cfg_context_base(active_context_base)'in core and '.cfg_window_base(active_window_base)'in core
        assert '.mem_valid(mem_valid[20*1+:3*1])'in core
        harness=(executed/'sim/cocotb_two_fpga_initialized_top.sv').read_text()
        assert 'external_memory_fabric #(.CLIENTS(14)) p_fabric('in harness
        assert 'tokenizer_fpga_memory_subsystem #'in harness
        actual_directory_parents=[n for n,p in active.items()if re.search(r'\bgrpc_stream_store\s*#\([^;]*\)\s+store\s*\(',p.read_text(),re.S)]
        assert actual_directory_parents==['grpc_pool_locked_stream_store']
        if label=='bootstrap':
            assert accepted['bootstrap_memory_phases']==accepted['injected_bootstrap_faults']==8
            assert accepted['double_fault_cleanup_cases']==1 and accepted['successful_opens']==10
            assert all(accepted[k]for k in('held_public_open_results_verified','raw_close_before_failed_open_result_verified',
                'independent_raw_and_window_recovery_verified','poisoned_open_configuration_verified',
                'actual_shared_directory_and_window_service','complete_parser_model_prefix_immutable','untouched_tokenizer_bank'))
        else:
            assert accepted['messages']==16 and accepted['token_ids']==2828
            assert accepted['response_chunks']==2828 and accepted['response_bytes']==144686
            assert accepted['connection_initializations']==7 and accepted['positive_grants']==accepted['response_data_frames']
            assert accepted['zero_grants']>0 and accepted['peer_window_updates']>=2 and accepted['credit_park_cycles']>0
            assert accepted['hyperframe_version']=='6.1.0'and accepted['full_metadata_window_updates']==[[0,0,101],[0,1,37]]
            assert all(accepted[k]for k in('automatic_connection_windows_verified','actual_admission_window_initialization_verified',
                'independent_credit_model_verified','durable_debits_before_data_verified','separate_memory_banks_verified',
                'actual_dma_ids_returned','model_and_policy_immutable','raw_update_probe_after_packet_commit',
                'raw_controls_applied_by_external_fixture'))
        assert accepted['parser_memory_clients']==14 and not accepted['full_system_complete']
        # Reproduce all four production join modules and the actual harness.
        digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16]
        replay=root/'build/validation/initialized-parser-generation-replay'/digest
        if not replay.exists():shutil.copytree(executed,replay)
        (replay/'build/validation').mkdir(parents=True,exist_ok=True)
        for script,options in(('generate_http2_initialized_parser.py',[]),('generate_two_fpga_harness.py',['--tokenizer-memory','--initialized-parser'])):
            subprocess.run([sys.executable,str(replay/'tools'/script),*options],check=True,capture_output=True)
        generated=['rtl/'+n+'.v'for n in('http2_initialized_parser_transport','http2_initialized_parser_core',
            'http2_initialized_parser_application','rpc_grpc_initialized_return')]+['sim/cocotb_two_fpga_initialized_top.sv']
        for relative in generated:assert sha(replay/relative)==inputs[relative],relative
        details[label]=dict(snapshot=name,acceptance=accepted,execution_sources=len(report['source_sha256']),
            execution_fixtures=len(report['fixture_sha256']),parser_modules=list(active),tokenizer_modules=list(token),
            exact_join_and_harness_regeneration_verified=True,single_actual_directory_verified=True,
            current_primary_differences=[n for n,h in inputs.items()if not(source_path(root, n)).is_file()or sha(source_path(root, n))!=h],
            current_active_rtl_matches=all(sha(source_path(root, p.relative_to(executed)))==sha(p)for p in active.values()))
        for relative in('report.json','acceptance.json','results.xml','simulation.log','build.log','snapshot.json','native-reference.json'):
            files[Path(label)/'reports'/relative]=archive/relative
        files[Path(label)/'execution/scripts/run_cocotb_snapshot.py']=executed/'scripts/run_cocotb_snapshot.py'
    files[Path('verification/verify_initialized_parser.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(p)+sha(files[p])for p in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/initialized-parser-evidence'/key
    for relative,source in files.items():
        target=evidence/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source)
        else:shutil.copy2(source,target)
    result=dict(phase='bootstrap_fault_execution_verified'if args.bootstrap_only else'actual_initialized_parser_full_execution_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),executions=details,parser_memory_clients=14,tokenizer_memory_clients=9,
        automatic_connection_bootstrap_verified=True,complete_data_execution_verified=not args.bootstrap_only,
        raw_control_journal_integrated=False,headers_trailers_tx_verified=False,whole_rpc_image_leases_verified=False,
        complete_parser_native_timing_verified=False,physical_adapters_verified=False,full_system_complete=False,
        verifier_sha256=sha(Path(__file__)),evidence_folder=str(evidence))
    output='initialized-parser-bootstrap.json'if args.bootstrap_only else'initialized-parser.json'
    (root/'build/validation'/output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
