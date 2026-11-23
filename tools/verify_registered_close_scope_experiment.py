"""Bind the two-leaf timing experiment to actual RPC tests, formal proofs and route."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure,resources,timing


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rpc',default='registered_closed_scope_compact_headers')
    parser.add_argument('--proof',default='registered_closed_scope_capture_projection')
    parser.add_argument('--native-run',default='rpc_http2_scu35_compact_registered_closed_scope')
    parser.add_argument('--parser-native-run',help='Audit completed synthesis or routing of the experimental 68-module AU15P Parser')
    parser.add_argument('--raw',help='Require the native-client/reset execution on the experimental 68-module raw join')
    parser.add_argument('--raw-shutdown-faults',help='Require all 41 raw shutdown fault phases on the experiment')
    parser.add_argument('--raw-return-faults',help='Require all 20 raw return metadata fault phases on the experiment')
    parser.add_argument('--require-native',action='store_true');args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',n)for n in(args.rpc,args.proof,args.native_run,args.parser_native_run,args.raw,args.raw_shutdown_faults,args.raw_return_faults)if n)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={}
    archive=root/'build/wsl-reports'/('rpc_http2_'+args.rpc);source=archive/'execution-sources'
    inputs=json.loads((archive/'inputs.json').read_text());report=json.loads((archive/'report.json').read_text())
    accepted=json.loads((archive/'acceptance.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    assert sorted(snapshot['isolated_rtl_overrides'])==['rtl/grpc_response_headers.v','rtl/rpc_grpc_http2_return.v']
    for n,h in inputs.items():assert sha(source/n)==h,n;files[Path('rpc/execution')/n]=source/n
    xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='actual_rpc_native_client_headers_data_trailers_and_commit_faults'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    baseline_path=root/'build/validation/rpc-http2-return.json';baseline=json.loads(baseline_path.read_text())
    assert baseline['phase']=='actual_rpc_response_envelope_verified'and baseline['verifier_sha256']==sha(root/'tools/verify_rpc_http2_return.py')
    baseline_evidence=Path(baseline['evidence_folder']);baseline_source=baseline_evidence/'rpc/execution'
    baseline_inputs=json.loads((baseline_evidence/'rpc/reports/inputs.json').read_text())
    assert accepted==baseline['rpc']['acceptance']
    original_xml=ET.parse(baseline_evidence/'rpc/reports/results.xml')
    properties={p.attrib['name']:p.attrib['value']for p in cases[0].findall('properties/property')}
    original_properties={p.attrib['name']:p.attrib['value']for p in original_xml.findall('.//testcase')[0].findall('properties/property')}
    assert properties['sim_time_unit']==original_properties['sim_time_unit']=='ns'
    assert float(properties['sim_time_duration'])==float(original_properties['sim_time_duration'])>0
    dag=closure('rpc_grpc_http2_return',source);assert len(dag)==20;changes=[]
    for name,p in dag.items():
        n=p.relative_to(source).as_posix();assert sha(baseline_source/n)==baseline_inputs[n]==sha(root/n),n
        if inputs[n]!=baseline_inputs[n]:changes.append(name)
    assert changes==['grpc_response_headers','rpc_grpc_http2_return']
    for n,h in inputs.items():
        if n.startswith(('build/rpc-grpc-fixtures/','build/grpc-header-fixtures/','native-vendor/')):
            assert h==baseline_inputs[n],n
    assert inputs['sim/cocotb/test_rpc_http2_return.py']==baseline_inputs['sim/cocotb/test_rpc_http2_return.py']
    for p in closure('inverse_tokenizer_partition',source).values():
        n=p.relative_to(source).as_posix();assert inputs[n]==baseline_inputs[n]==sha(root/n)
    files[Path('baseline/rpc-http2-return.json')]=baseline_path
    compact_path=root/'build/validation/compact-grpc-headers-experiment.json';compact=json.loads(compact_path.read_text())
    assert compact['unbounded_post_reset_formatter_equivalence_verified']and compact['verifier_sha256']==sha(root/'tools/verify_compact_grpc_headers_experiment.py')
    compact_evidence=Path(compact['evidence_folder'])
    assert sha(compact_evidence/'formal/execution/rtl/gate_input.v')==inputs['rtl/grpc_response_headers.v']
    files[Path('baseline/compact-grpc-headers-experiment.json')]=compact_path

    proof=root/'build/wsl-reports'/('closed_scope_equivalence_'+args.proof);proof_source=proof/'execution-sources'
    proof_inputs=json.loads((proof/'inputs.json').read_text());proof_report=json.loads((proof/'report.json').read_text())
    proof_snapshot=json.loads((proof/'snapshot.json').read_text())
    assert proof_report['phase']=='passed'and proof_report['yosys_exit_code']==proof_snapshot['exit_code']==0
    assert proof_report['input_sha256']==proof_inputs and proof_report['unbounded_post_reset_scope_comparison_equivalence']
    assert proof_report['simultaneous_capture_events_unconstrained']and not proof_report['whole_module_equivalence_verified']
    assert proof_report['memory_address_width']==23 and 'Induction step proven: SUCCESS!'in(proof/'yosys.log').read_text()
    for n,h in proof_inputs.items():assert sha(proof_source/n)==h,n;files[Path('proof/execution')/n]=proof_source/n
    for n,h in proof_report['generated_sha256'].items():assert sha(proof/n)==h,n
    assert proof_inputs['rtl/gold_input.v']==baseline_inputs['rtl/rpc_grpc_http2_return.v']
    assert proof_inputs['rtl/gate_input.v']==inputs['rtl/rpc_grpc_http2_return.v']
    spec=importlib.util.spec_from_file_location('frozen_scope_projection',proof_source/'scripts/run_closed_scope_equivalence.py')
    projection=importlib.util.module_from_spec(spec);spec.loader.exec_module(projection)
    for name in('gold','gate'):
        text,public,conditions=projection.model((proof_source/f'rtl/{name}_input.v').read_text(),name)
        assert text==(proof/(name+'.v')).read_text()and conditions==proof_report['actual_capture_conditions']
    miter=(proof/'miter.v').read_text()
    assert miter.count('assume(')==1 and 'if(!initialized)assume(rst);'in miter and 'reg initialized=0;'in miter
    assert 'assert(gold_observed==gate_observed);assert(gold_value==gate_value);'in miter
    for _,n in public:assert miter.count('.'+n+'('+n+')')==2,n
    assert(proof/'proof.ys').read_text()=='read_verilog -formal gold.v gate.v miter.v\nprep -top scope_equivalence -flatten\nsat -seq 1 -tempinduct -maxsteps 8 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n'
    for n in('report.json','snapshot.json','inputs.json','gold.v','gate.v','miter.v','proof.ys','yosys.log'):files[Path('proof/reports')/n]=proof/n

    replay=root/'build/validation/registered-close-scope-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in('rtl/rpc_grpc_http2_return.v','tools/generate_registered_close_scope_experiment.py'):
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(baseline_source/n if n.startswith('rtl/')else source/n,p)
    header=replay/'build/experiments/compact-grpc-headers/rtl/grpc_response_headers.v';header.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/'rtl/grpc_response_headers.v',header)
    subprocess.run([sys.executable,str(replay/'tools/generate_registered_close_scope_experiment.py')],check=True,capture_output=True,text=True)
    for n in('grpc_response_headers.v','rpc_grpc_http2_return.v'):
        assert sha(replay/'build/experiments/registered-close-scope/rtl'/n)==inputs['rtl/'+n]
    for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('rpc/reports')/n]=archive/n
    raw_records={}
    if args.raw or args.raw_shutdown_faults or args.raw_return_faults:
        raw_baseline_path=root/'build/validation/raw-enveloped-parser.json';raw_baseline=json.loads(raw_baseline_path.read_text())
        assert raw_baseline['phase']=='native_raw_grpc_response_envelope_verified'
        assert raw_baseline['verifier_sha256']==sha(root/'tools/verify_raw_enveloped_parser.py')
        files[Path('baseline/raw-enveloped-parser.json')]=raw_baseline_path
        profiles=(('native',args.raw,'native_calls_return_actual_dma_ids_and_complete_grpc','acceptance'),
            ('shutdown-faults',args.raw_shutdown_faults,'raw_shutdown_memory_failures_preserve_quarantine_and_ownership','raw_shutdown_fault_acceptance'),
            ('return-faults',args.raw_return_faults,'raw_admitted_return_metadata_faults_keep_real_ownership','raw_return_metadata_fault_acceptance'))
        for profile,name,test,field in profiles:
            if not name:continue
            raw=root/'build/wsl-reports'/('raw_envelope_'+name);executed=raw/'execution-sources'
            raw_inputs=json.loads((raw/'inputs.json').read_text());raw_report=json.loads((raw/'report.json').read_text())
            raw_acceptance=json.loads((raw/'acceptance.json').read_text());raw_snapshot=json.loads((raw/'snapshot.json').read_text())
            assert raw_report['phase']==raw_acceptance['phase']=='passed'and raw_report['tests']==1 and raw_report['failures']==0 and raw_snapshot['exit_code']==0
            assert raw_report['profile']==raw_snapshot['profile']==profile
            assert raw_report['input_sha256']==raw_inputs and raw_report['acceptance_sha256']==sha(raw/'acceptance.json')
            assert sorted(raw_snapshot['isolated_rtl_overrides'])==['rtl/grpc_response_headers.v','rtl/rpc_grpc_http2_return.v']
            for n,h in raw_inputs.items():assert sha(executed/n)==h,n;files[Path('raw')/profile/'execution'/n]=executed/n
            raw_xml=ET.parse(raw/'results.xml');raw_cases=raw_xml.findall('.//testcase')
            assert len(raw_cases)==1 and raw_cases[0].attrib['name']==test
            assert not raw_xml.findall('.//failure')and not raw_xml.findall('.//error')
            parser_dag=closure('http2_enveloped_parser_application',executed);tokenizer_dag=closure('tokenizer_fpga_memory_subsystem',executed)
            assert(len(parser_dag),len(tokenizer_dag))==(68,22)
            for p in[*parser_dag.values(),*tokenizer_dag.values()]:
                n=p.relative_to(executed).as_posix();expected=inputs[n]if n in snapshot['isolated_rtl_overrides']else sha(root/n)
                assert raw_inputs[n]==expected,n
            assert raw_acceptance==raw_baseline[field]
            raw_records[profile]=dict(acceptance=raw_acceptance,exact_experimental_parser_and_tokenizer_sources_verified=True)
            for n in('report.json','snapshot.json','inputs.json','acceptance.json','simulation.log','build.log','results.xml'):files[Path('raw')/profile/'reports'/n]=raw/n
    folder=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run;log=root/f'build/{args.native_run}-implementation.log'
    native=dict(phase='not_yet_verified',timing_met=False,run=args.native_run)
    if log.is_file()and'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE'in log.read_text():
        provenance=json.loads((folder/'source-provenance.json').read_text());frozen=folder/'sources'
        for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256']
        for p in closure('rpc_grpc_http2_return',frozen).values():
            n=p.relative_to(frozen).as_posix();assert sha(p)==inputs[n],n;files[Path('native/sources')/n]=p
        clocks=timing(folder/'routed_timing.rpt');area=resources(folder/'routed_utilization.rpt')
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
        exceptions=[s.strip()for s in(frozen/'scripts/implement_registered_subsystem.tcl').read_text().splitlines()if s.strip().startswith('set_false_path')]
        assert exceptions==['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        native=dict(phase='native_route_verified',run=args.native_run,resources=area,timing=clocks,
            timing_met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0,
            registered_neighbors=True,package_paths_excluded=True,routed_checkpoint_sha256=sha(folder/'routed.dcp'))
        for n in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('native')/n]=folder/n
        files[Path('native/implementation.log')]=log
    if args.require_native:assert native['timing_met'],'Exact experimental native timing is not met'
    parser_native=dict(phase='not_requested',timing_met=False)
    if args.parser_native_run:
        assert 'native'in raw_records,'Full Parser native audit requires the experimental raw integration execution'
        part='xcau15p-ffvb676-2-e';top='http2_enveloped_parser_application'
        folder=root/'build/implementation'/part/args.parser_native_run
        log=root/f'build/{args.parser_native_run}-implementation.log'
        parser_native=dict(phase='not_yet_verified',timing_met=False,run=args.parser_native_run,part=part,top=top)
        marker=f'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP={top} PART={part}'
        log_bytes=log.read_bytes()if log.is_file()else b'';native_log=log_bytes.decode()
        routed=marker in native_log
        synthesized='synth_design completed successfully'in native_log and 'Command: opt_design'in native_log
        if routed or synthesized:
            assert '0 Critical Warnings and 0 Errors encountered.'in native_log
            provenance=json.loads((folder/'source-provenance.json').read_text());frozen=folder/'sources'
            for n,r in provenance['files'].items():assert sha(frozen/n)==r['sha256'],n
            raw_source=root/'build/wsl-reports'/('raw_envelope_'+args.raw)/'execution-sources'
            parser_dag=closure(top,frozen);assert len(parser_dag)==68
            assert not {'bpe_tokenizer_engine','detokenizer_engine','token_packager'}&parser_dag.keys()
            for p in parser_dag.values():
                n=p.relative_to(frozen).as_posix();assert sha(p)==sha(raw_source/n),n
                files[Path('parser-native/sources')/n]=p
            suffix='routed'if routed else'synthesis'
            clocks=timing(folder/(suffix+'_timing.rpt'));area=resources(folder/(suffix+'_utilization.rpt'))
            assert area['luts']<=77760 and area['bram36']+area['bram18']/2<=144
            if routed:
                assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(folder/'route_status.rpt').read_text())
                assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(folder/'routed_drc.rpt').read_text(),re.M)
            exceptions=[s.strip()for s in(frozen/'scripts/implement_registered_subsystem.tcl').read_text().splitlines()if s.strip().startswith('set_false_path')]
            assert exceptions==['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
            assert f'synth_design -top {top}_timing_harness -part {part} -mode out_of_context'in native_log
            parser_native=dict(phase='native_route_verified'if routed else'native_synthesis_verified',run=args.parser_native_run,part=part,top=top,
                resources=area,timing=clocks,exact_experimental_parser_modules_verified=len(parser_dag),
                timing_met=routed and clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0,
                native_lut_and_bram_fit=True,routed=routed,
                registered_neighbors=True,package_paths_excluded=True,physical_interfaces_verified=False,
                checkpoint_sha256=sha(folder/('routed.dcp'if routed else'synthesized.dcp')))
            reports=['source-provenance.json',suffix+'_timing.rpt',suffix+'_utilization.rpt']
            if routed:reports+=['routed_drc.rpt','route_status.rpt']
            for n in reports:
                files[Path('parser-native')/n]=folder/n
            # The log can still grow during placement/routing. Bind one complete
            # read rather than hashing and copying different live versions.
            captured=root/'build/validation/native-log-snapshots'/hashlib.sha256(log_bytes).hexdigest()
            captured.parent.mkdir(parents=True,exist_ok=True)
            if captured.exists():assert captured.read_bytes()==log_bytes
            else:captured.write_bytes(log_bytes)
            files[Path('parser-native/implementation.log')]=captured
    files[Path('verification/verify_registered_close_scope_experiment.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/registered-close-scope-evidence'/key
    for n,p in files.items():
        destination=evidence/n;destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():assert sha(destination)==sha(p)
        else:shutil.copy2(p,destination)
    result=dict(phase='registered_close_scope_rpc_and_formal_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        changed_modules=changes,rpc_acceptance=accepted,actual_rpc_matrix_matches_baseline=True,exact_matrix_cycles_unchanged=True,
        matrix_simulation_time_ns=float(properties['sim_time_duration']),
        projected_close_scope_equivalence=proof_report,formatter_full_public_output_equivalence_bound=True,
        original_model_and_native_oracle_inputs_match_audited_baseline=True,exact_generation_replayed=True,
        production_rtl_unchanged=True,native=native,raw_executions=raw_records,
        raw_native_calls_and_reset_on_experiment_verified='native'in raw_records,
        raw_shutdown_fault_matrix_on_experiment_verified='shutdown-faults'in raw_records,
        raw_return_fault_matrix_on_experiment_verified='return-faults'in raw_records,
        full_raw_workload_on_experiment_verified=False,
        parser_native=parser_native,full_parser_native_timing_verified=parser_native['timing_met'],
        physical_interfaces_verified=False,whole_rpc_gpu_image_lease_verified=False,
        full_system_complete=False,evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/registered-close-scope-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','changed_modules','exact_matrix_cycles_unchanged','native','evidence_folder')},indent=2))


if __name__=='__main__':main()
