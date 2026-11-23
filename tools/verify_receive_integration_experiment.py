"""Bind the actual 71-module receive join to native and passive commit witnesses."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import tiktoken
from verify_native_grpc_corpus_reference import varint
from verify_two_fpga_application import closure, resources, timing


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--native',default='receive_integration_header_admission_fence')
    parser.add_argument('--padding',default='receive_integration_actual_commit_witnesses')
    parser.add_argument('--native-run',default='parser_au15p_receive_integration')
    args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',n) for n in vars(args).values())
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    generation=json.loads((root/'build/experiments/receive-integration/generation.json').read_text())
    overrides={'rtl/'+n:h for n,h in generation['generated_sha256'].items()};assert len(overrides)==16
    records={};dags={};sources={}
    for label,name,profile,test in (
        ('native',args.native,'native','native_calls_return_actual_dma_ids_and_complete_grpc'),
        ('padding',args.padding,'receive-flow','native_padding_credit_replenishment_allows_next_real_prompt')):
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources';sources[label]=source
        inputs=json.loads((archive/'inputs.json').read_text());report=json.loads((archive/'report.json').read_text())
        snapshot=json.loads((archive/'snapshot.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
        assert report['phase']==accepted['phase']=='passed' and snapshot['exit_code']==0
        assert report['profile']==snapshot['profile']==profile and report['tests']==1 and report['failures']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():
            assert sha(source/n)==h,(name,n)
            if n.startswith('native-vendor/'):
                assert sha(root/'.venv312/Lib/site-packages'/n.split('/',1)[1])==h,n
        xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
        assert len(cases)==1 and cases[0].attrib['name']==test and not xml.findall('.//failure') and not xml.findall('.//error')
        dag=closure('http2_enveloped_parser_application',source);tokenizer=closure('tokenizer_fpga_memory_subsystem',source)
        assert (len(dag),len(tokenizer))==(71,22)
        assert {'http2_receive_flow_controller','http2_keyed_receive_credit_store','http2_receive_credit_store'}<=dag.keys()
        assert 'detokenizer_engine'not in dag and 'detokenizer_engine'in tokenizer
        for p in [*dag.values(),*tokenizer.values()]:
            n=p.relative_to(source).as_posix();assert inputs[n]==overrides.get(n,sha(root/n)),n
        assert (accepted['parser_memory_clients'],accepted['tokenizer_memory_clients'])==(18,9)
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete']is False
        fixture=source/'build/bidirectional-fixtures';layout=list(map(int,(fixture/'layout.txt').read_text().split()))
        manifest=json.loads((fixture/'fixture_manifest.json').read_text())
        loaded=b''.join(int(word,16).to_bytes(8,'little')for word in (fixture/'memory.mem').read_text().splitlines())
        original=root/'build/scu35/image/external_memory.bin'
        assert sha(original)=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
        assert len(loaded)==original.stat().st_size==8388608 and hashlib.sha256(loaded).hexdigest()==manifest['loaded_image_sha256']
        assert layout[6]==6903552 and loaded[:layout[6]]==original.read_bytes()[:layout[6]]
        harness=(source/'sim/cocotb_two_fpga_enveloped_top.sv').read_text()
        assert 'external_memory_fabric #(.CLIENTS(18)) p_fabric('in harness and 'client<27'in harness
        assert inputs['sim/cocotb_two_fpga_enveloped_top.sv']==generation['harness_sha256']
        records[label]=dict(snapshot=name,archive=str(archive),input_sha256=inputs,acceptance=accepted,
            files_sha256={p.name:sha(p)for p in archive.iterdir()if p.is_file()})
        dags[label]={n:sha(p)for n,p in dag.items()}
    assert dags['native']==dags['padding']
    n=records['native']['acceptance'];p=records['padding']['acceptance']
    assert tuple(n[k]for k in('actual_raw_packets','actual_header_bindings','native_complete_grpc_calls','actual_forward_dma_ids',
        'actual_gpu_descriptors_accepted','actual_captured_dma_ids_returned','additional_generated_control_case_descriptors','native_wire_frames'))==(11,6,2,6,8,4,4,16)
    for k in('normal_call_generated_input_is_captured_forward_dma','actual_response_headers_and_grpc_status_verified',
        'actual_raw_rst_drains_offered_initial_header','actual_raw_rst_drains_offered_final_trailer',
        'ordinary_prompt_after_reset_without_global_reset','actual_header_commit_failure_propagates_through_raw_reset',
        'failed_header_commit_never_processes_reset'):assert n[k],k
    fixture=sources['native']/'build/bidirectional-fixtures'
    reference=json.loads((fixture/'reference_cases.json').read_text())['cases'][0]
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache');encoding=tiktoken.get_encoding('cl100k_base')
    assert len(encoding._mergeable_ranks)==100256
    ids=encoding.encode_ordinary(bytes.fromhex(reference['prompt_utf8_hex']).decode())
    assert ids==reference['token_ids']==[15339,1917]
    for stream,mode in(('1',0),('3',2)):
        expected=[]
        for token in ids:
            raw=encoding.decode_single_token_bytes(token)
            body=json.dumps({'choices':[{'delta':{'content':raw.decode()}}]},ensure_ascii=False,separators=(',',':')).encode() if mode==0 else varint(17<<3|2)+varint(len(raw))+raw
            expected.append((b'\0'+len(body).to_bytes(4,'big')+body).hex())
        assert n['expected_response_records'][stream]==expected
    for k in('native_window_updates_received','actual_header_initialization_before_public_binding',
        'actual_both_budget_debit_before_application_dispatch','actual_committed_frame_padding_release',
        'actual_intent_wire_available_clear_result_order_verified',
        'actual_successful_close_inactive_binding_and_connection_refund_verified',
        'application_bytes_not_refunded_until_actual_close'):assert p[k],k
    assert p['native_padding_payload_bytes']==65535 and p['held_actual_wire_cycles']==17
    assert p['actual_dma_ids_returned']==ids and p['native_complete_grpc_calls']==1
    assert p['actual_window_update_frames']==513
    debits=p['actual_receive_debits'];assert len(debits)==257
    assert [d['amount']for d in debits[:256]]==[256]*255+[255]
    application_bytes=debits[-1]['amount'];assert application_bytes==29
    assert all((d['op'],d['user'],d['stream'],d['generation'],d['address'])==(2,0,1,0,0)for d in debits)
    updates=p['actual_receive_updates'];assert len(updates)==513
    expected=[(s,256)for _ in range(255)for s in(1,0)]+[(1,255),(0,255),(0,application_bytes)]
    assert [(u['stream'],u['amount'])for u in updates]==expected
    for u in updates:assert u['intent_ack_clock']<u['wire_clock']<u['available_ack_clock']<=u['clear_ack_clock']<u['result_ack_clock']
    for a,b in zip(updates,updates[1:]):assert a['result_ack_clock']<b['intent_ack_clock']
    for k in('receive_flow_control_negative_matrix_verified','application_ring_reclamation_verified','retained_memory_reset_verified'):assert p[k]is False
    # Replay the current generator from immutable copies, including its exact
    # 10-file registered-scope predecessor and passive source fixtures.
    replay=root/'build/validation/receive-integration-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    to_copy=set(generation['input_sha256'])|{
        'tools/generate_receive_integration_experiment.py','tools/generate_receive_commit_test.py',
        'tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py','rtl/axis_frame_arbiter.v',
        'sim/cocotb_two_fpga_enveloped_top.sv','sim/cocotb/test_raw_grpc_enveloped.py','sim/cocotb/test_raw_receive_flow.py'}
    to_copy|={p.relative_to(root).as_posix()for p in(root/'build/experiments/registered-envelope-scope/rtl').glob('*.v')}
    replay_inputs={}
    for name in sorted(to_copy):
        original=root/name
        if name in generation['input_sha256']:assert sha(original)==generation['input_sha256'][name],name
        target=replay/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target);replay_inputs[name]=sha(target)
    subprocess.run([sys.executable,str(replay/'tools/generate_receive_integration_experiment.py')],check=True,capture_output=True,text=True)
    for name,h in generation['generated_sha256'].items():assert sha(replay/'build/experiments/receive-integration/rtl'/name)==h,name
    for name,key in(('cocotb_two_fpga_enveloped_top.sv','harness_sha256'),('test_raw_grpc_enveloped.py','test_overlay_sha256'),('test_raw_receive_flow.py','padding_overlay_sha256')):
        assert sha(replay/'build/experiments/receive-integration/sim'/name)==generation[key],name
    assert records['native']['input_sha256']['sim/cocotb/test_raw_grpc_enveloped.py']==generation['test_overlay_sha256']
    assert records['padding']['input_sha256']['sim/cocotb/test_raw_receive_flow.py']==generation['padding_overlay_sha256']
    native=dict(phase='not_yet_verified',routed=False,timing_met=False)
    folder=root/'build/implementation/xcau15p-ffvb676-2-e'/args.native_run
    if (folder/'source-provenance.json').exists():
        frozen=folder/'sources';provenance=json.loads((folder/'source-provenance.json').read_text())
        for name,data in provenance['files'].items():assert sha(frozen/name)==data['sha256'],name
        dag=closure('http2_enveloped_parser_application',frozen);assert len(dag)==71
        for module,path in dag.items():assert sha(path)==dags['native'][module],module
        # All current application ports, including client 18, must have a
        # register neighbor. Verify generator replay rather than trusting width.
        output=replay/'native_timing_harness.v'
        shutil.copy2(frozen/'tools/generate_parser_timing_harness.py',replay/'tools/generate_parser_timing_harness.py')
        subprocess.run([sys.executable,str(replay/'tools/generate_parser_timing_harness.py'),'--source',str(frozen/'rtl/http2_enveloped_parser_application.v'),
            '--top','http2_enveloped_parser_application','--harness-top','http2_enveloped_parser_application_timing_harness','--output',str(output)],check=True,capture_output=True,text=True)
        assert sha(output)==sha(frozen/'timing_harness.v')
        exceptions=[s.strip()for s in(frozen/'scripts/implement_registered_subsystem.tcl').read_text().splitlines()if s.strip().startswith('set_false_path')]
        assert exceptions==['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        log=root/('build/'+args.native_run+'-implementation.log');log_bytes=log.read_bytes();log_text=log_bytes.decode()
        captured=root/'build/validation/native-log-snapshots'/hashlib.sha256(log_bytes).hexdigest();captured.parent.mkdir(parents=True,exist_ok=True)
        if not captured.exists():captured.write_bytes(log_bytes)
        native.update(phase='native_sources_and_all_port_neighbors_verified',captured_log=str(captured),source_provenance_sha256=sha(folder/'source-provenance.json'))
        routed='REGISTERED_SUBSYSTEM_ROUTE_COMPLETE'in log_text
        synthesized='synth_design completed successfully'in log_text and (folder/'synthesis_timing.rpt').exists()
        if routed or synthesized:
            assert '0 Critical Warnings and 0 Errors encountered.'in log_text
            suffix='routed'if routed else'synthesis';checkpoint=folder/('routed.dcp'if routed else'synthesized.dcp')
            with ZipFile(checkpoint)as package:metadata={n.tag:n.attrib.get('Name')for n in ET.fromstring(package.read('dcp.xml'))}
            assert metadata['Part']=='xcau15p-ffvb676-2-e'and metadata['Top']=='http2_enveloped_parser_application_timing_harness'and metadata['OutOfContext']=='1'
            area=resources(folder/(suffix+'_utilization.rpt'));clocks=timing(folder/(suffix+'_timing.rpt'))
            row=next(s for s in(folder/(suffix+'_utilization.rpt')).read_text().splitlines()
                if re.match(r'\|\s*http2_enveloped_parser_application_timing_harness\s*\|',s))
            cells=[s.strip()for s in row.split('|')[1:-1]]
            total=dict(luts=int(cells[2]),registers=int(cells[6]),bram36=int(cells[7]),bram18=int(cells[8]),uram=int(cells[9]),dsps=int(cells[10]))
            assert total['luts']<=77760 and total['registers']<=155520 and total['uram']==0
            assert total['bram36']+total['bram18']/2<=144 and total['dsps']<=576
            if routed:
                assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
                assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
            native.update(phase='native_route_verified'if routed else'native_synthesis_verified',routed=routed,resources=area,total_harness_resources=total,timing=clocks,
                native_resource_capacity_verified=True,registered_all_current_application_ports_verified=True,
                checkpoint_metadata=metadata,checkpoint_sha256=sha(checkpoint),
                reports_sha256={n:sha(folder/n)for n in(suffix+'_utilization.rpt',suffix+'_timing.rpt')},
                timing_met=routed and clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0)
    result=dict(phase='actual_receive_integrated_parser_direct_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        exact_parser_modules_verified=71,exact_tokenizer_modules_verified=22,parser_memory_clients=18,
        current_executed_rtl_sha256=dags['native'],executions=records,generation_replay_inputs=replay_inputs,
        generation_report_sha256=sha(root/'build/experiments/receive-integration/generation.json'),
        original_complete_model_image_verified=True,independent_native_tokenizer_reference_verified=True,
        actual_admission_debit_committed_padding_wire_and_close_verified=True,native=native,
        concurrent_directory_mutation_isolation_verified=False,per_connection_fatal_refund_policy_verified=False,
        global_runtime_arena_nonoverlap_verified=False,
        full_receive_negative_matrix_verified=False,open_rpc_ring_reclamation_verified=False,
        retained_memory_reset_verified=False,full_native_corpus_on_current_variant_verified=False,
        whole_rpc_gpu_image_leases_verified=False,physical_interfaces_verified=False,
        full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-integration-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for name in('generate_receive_integration_experiment.py','generate_receive_commit_test.py'):
        shutil.copy2(root/'tools'/name,evidence/name)
    result['evidence_folder']=str(evidence)
    (root/'build/validation/receive-integration-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,actual_wire_updates_verified=513,native_stage=native['phase'],full_system_complete=False)))


if __name__=='__main__':main()
