"""Bind an isolated formatter experiment to native references and synthesis."""
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

from verify_two_fpga_application import closure,resources,timing
from generate_bidirectional_application import ports
from generate_two_fpga_application import add_ports,rename

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',default='compact_constant_packet_experiment')
    parser.add_argument('--native-run',default='rpc_http2_scu35_compact_headers_experiment')
    parser.add_argument('--baseline-run',default='rpc_http2_scu35_registered_close_scope')
    parser.add_argument('--equivalence',help='Require the archived unbounded post-reset RTL equivalence proof');args=parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',n)for n in vars(args).values()if n)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();files={}
    archive=root/'build/wsl-reports'/('grpc_headers_'+args.snapshot);source=archive/'execution-sources'
    report=json.loads((archive/'report.json').read_text());accepted=json.loads((archive/'acceptance.json').read_text())
    inputs=json.loads((archive/'inputs.json').read_text());snapshot=json.loads((archive/'snapshot.json').read_text())
    assert report['phase']==accepted['phase']=='passed'and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
    assert snapshot['isolated_rtl_override']and report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    for n,h in inputs.items():assert sha(source/n)==h,n;files[Path('unit/execution')/n]=source/n
    xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='native_headers_trailers_and_actual_wire_abort_fences'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    assert tuple(accepted[n]for n in('native_header_cases','native_client_exchanges','rejected_commands','actual_wire_frames'))==(122,99,8,124)
    for n in('stateless_hpack_with_zero_dynamic_decoder','config_poisoned_after_acceptance','held_results_verified',
        'private_abort_requires_actual_wire_fence','held_control_survives_private_abort','offered_header_drains_before_abort',
        'completed_header_result_not_retracted','native_client_uses_rtl_header_bytes'):assert accepted[n],n
    assert accepted['held_wire_cycles']>0 and accepted['client_exchange_data_is_native_fixture']
    assert not any(accepted[n]for n in('actual_rpc_metadata_joined','actual_granted_data_joined','raw_reset_controller_joined','full_system_complete'))
    for n in('report.json','acceptance.json','snapshot.json','inputs.json','simulation.log','build.log','results.xml'):files[Path('unit/reports')/n]=archive/n
    replay=root/'build/validation/compact-headers-generation-replay';replay.mkdir(parents=True,exist_ok=True)
    for n in inputs:
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,target)
    (replay/'build/validation').mkdir(parents=True,exist_ok=True)
    code='import sys,runpy;sys.path[:0]=[sys.argv[1]];runpy.run_path(sys.argv[2],run_name="__main__")'
    subprocess.run([sys.executable,'-c',code,str(replay/'native-vendor'),str(replay/'tools/generate_grpc_header_vectors.py')],check=True,capture_output=True,text=True)
    assert sha(replay/'build/grpc-header-fixtures/cases.json')==inputs['build/grpc-header-fixtures/cases.json']

    parent=root/'build/implementation/xcsu35p-sbvb625-2-e';baseline=parent/args.baseline_run;experiment=parent/args.native_run
    log=source_path(root, f'build/{args.native_run}-implementation.log')
    assert 'REGISTERED_SUBSYSTEM_SYNTHESIS_COMPLETE TOP=rpc_grpc_http2_return'in log.read_text()
    assert re.search(r'0 Critical Warnings and 0 Errors encountered\.',log.read_text())
    # A later route may use this frozen checkpoint. This evidence still covers
    # synthesis only; no routed result is inferred from those later artifacts.
    dags=[]
    for label,folder in(('baseline',baseline),('experiment',experiment)):
        provenance=json.loads((folder/'source-provenance.json').read_text());frozen=folder/'sources'
        for n,record in provenance['files'].items():assert sha(frozen/n)==record['sha256'],n
        dag=closure('rpc_grpc_http2_return',frozen);assert len(dag)==20;dags.append(dag)
        for path in dag.values():files[Path(label)/path.relative_to(folder)]=path
        for n in('source-provenance.json','synthesis_utilization.rpt','synthesis_timing.rpt'):files[Path(label)/n]=folder/n
    differences=[]
    for name,p in dags[0].items():
        q=dags[1][name];relative=p.relative_to(baseline/'sources').as_posix()
        assert sha(p)==sha(source_path(root, relative)),'Production changed during the isolated experiment: '+relative
        if sha(p)!=sha(q):differences.append(name)
    assert differences==['grpc_response_headers']
    assert sha(experiment/'sources/rtl/grpc_response_headers.v')==inputs['rtl/grpc_response_headers.v']
    assert(baseline/'sources/timing_harness.v').read_bytes()==(experiment/'sources/timing_harness.v').read_bytes()
    assert(baseline/'sources/timing.xdc').read_bytes()==(experiment/'sources/timing.xdc').read_bytes()
    assert(baseline/'sources/synthesis-options.txt').read_bytes()==(experiment/'sources/synthesis-options.txt').read_bytes()
    # Regenerate the alternative from the exact original RTL used by baseline
    # synthesis, and bind the generator itself into the reviewable evidence.
    shutil.copy2(baseline/'sources/rtl/grpc_response_headers.v',replay/'rtl/grpc_response_headers.v')
    generator=root/'tools/generate_compact_grpc_headers_experiment.py';shutil.copy2(generator,replay/'tools'/generator.name)
    subprocess.run([sys.executable,str(replay/'tools'/generator.name)],check=True,capture_output=True,text=True)
    assert sha(replay/'build/experiments/compact-grpc-headers/rtl/grpc_response_headers.v')==inputs['rtl/grpc_response_headers.v']
    before=resources(baseline/'synthesis_utilization.rpt');after=resources(experiment/'synthesis_utilization.rpt')
    assert before['bram36']==after['bram36']==36 and before['bram18']==after['bram18']==0
    assert before['uram']==after['uram']==before['dsps']==after['dsps']==0
    files[Path('experiment/implementation.log')]=log
    files[Path('experiment/isolated-override.txt')]=experiment/'sources/isolated-override.txt'
    files[Path('verification')/generator.name]=generator
    native=dict(phase='not_yet_verified',timing_met=False)
    route_log=source_path(root, f'build/{args.native_run}-route-resume.log')
    if route_log.is_file()and'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE'in route_log.read_text():
        clocks=timing(experiment/'routed_timing.rpt');routed_area=resources(experiment/'routed_utilization.rpt')
        assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(experiment/'route_status.rpt').read_text())
        assert not re.search(r'^\|[^\n]*\|\s*(Error|Critical Warning)\s*\|',(experiment/'routed_drc.rpt').read_text(),re.M)
        exceptions=[line.strip()for line in(experiment/'sources/scripts/implement_registered_subsystem.tcl').read_text().splitlines()if line.strip().startswith('set_false_path')]
        assert exceptions==['set_false_path -from [get_ports -filter {DIRECTION == IN && NAME != clk}]','set_false_path -to [all_outputs]']
        met=clocks['setup_wns_ns']>=0 and clocks['hold_whs_ns']>=0 and clocks['setup_failing_endpoints']==clocks['hold_failing_endpoints']==0
        native=dict(phase='native_route_verified',timing_met=met,timing=clocks,resources=routed_area,
            routed_checkpoint_sha256=sha(experiment/'routed.dcp'),registered_neighbors=True,package_paths_excluded=True)
        for n in('routed_timing.rpt','routed_utilization.rpt','routed_drc.rpt','route_status.rpt'):files[Path('route')/n]=experiment/n
        files[Path('route/implementation.log')]=route_log
    equivalence=None
    if args.equivalence:
        formal=root/'build/wsl-reports'/('grpc_header_equivalence_'+args.equivalence);formal_source=formal/'execution-sources'
        equivalence=json.loads((formal/'report.json').read_text());formal_snapshot=json.loads((formal/'snapshot.json').read_text())
        formal_inputs=json.loads((formal/'inputs.json').read_text())
        assert equivalence['phase']=='passed'and equivalence['unbounded_post_reset_equivalence_proven']and equivalence['yosys_exit_code']==formal_snapshot['exit_code']==0
        assert equivalence['input_sha256']==formal_inputs and 'Induction step proven: SUCCESS!'in(formal/'yosys.log').read_text()
        for n,h in formal_inputs.items():assert sha(formal_source/n)==h,n;files[Path('formal/execution')/n]=formal_source/n
        for n,h in equivalence['generated_sha256'].items():assert sha(formal/n)==h,n
        assert formal_inputs['rtl/gold_input.v']==sha(baseline/'sources/rtl/grpc_response_headers.v')
        assert formal_inputs['rtl/gate_input.v']==inputs['rtl/grpc_response_headers.v']
        helpers=[('output','[2:0]','formal_state'),('output','[1:0]','formal_encoding'),('output','[31:0]','formal_status_code')]
        public=ports((formal_source/'rtl/gold_input.v').read_text(),'grpc_response_headers')
        for name in('gold','gate'):
            original=(formal_source/f'rtl/{name}_input.v').read_text()
            expected=add_ports(original,'grpc_response_headers',helpers)
            expected=expected.replace('endmodule','assign formal_state=state;assign formal_encoding=encoding;assign formal_status_code=status_code;\nendmodule')
            expected=rename(expected,'grpc_response_headers','header_'+name)
            assert expected==(formal/(name+'.v')).read_text()
        miter=(formal/'miter.v').read_text()
        assert miter.count('assume(')==1 and 'if(!initialized)assume(rst);'in miter
        assert 'reg initialized=0;'in miter and 'initialized<=1;'in miter and 'if(initialized)begin'in miter
        for direction,_,n in public:
            if direction=='input':assert miter.count(f'.{n}({n})')==2,n
            else:assert f'assert(gold_{n}==gate_{n});'in miter,n
        assert equivalence['actual_public_outputs']==sum(d=='output'for d,_,_ in public)
        assert equivalence['technology_mapped_proof_model']
        assert (formal/'proof.ys').read_text()=='read_verilog -formal gold.v gate.v miter.v\nprep -top header_equivalence -flatten\ntechmap\nopt -full\nabc -g simple\nopt_clean\nsat -seq 1 -tempinduct -maxsteps 12 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n'
        for n in('report.json','snapshot.json','inputs.json','yosys.log','gold.v','gate.v','miter.v','proof.ys'):files[Path('formal/reports')/n]=formal/n
    files[Path('verification/verify_compact_grpc_headers_experiment.py')]=Path(__file__)
    key=hashlib.sha256(''.join(str(n)+sha(files[n])for n in sorted(files)).encode()).hexdigest()[:16]
    evidence=root/'build/validation/compact-headers-evidence'/key
    for n,p in files.items():
        target=evidence/n;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(p)
        else:shutil.copy2(p,target)
    result=dict(phase='isolated_compact_header_references_and_synthesis_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        unit_acceptance=accepted,production_rtl_unchanged=True,only_changed_hardware_module=differences[0],
        exact_native_reference_and_experimental_generation_replayed=True,identical_synthesis_settings_and_registered_neighbors=True,
        synthesis_baseline_resources=before,synthesis_experiment_resources=after,synthesis_luts_saved=before['luts']-after['luts'],
        native_synthesized_checkpoint_sha256=dict(baseline=sha(baseline/'synthesized.dcp'),experiment=sha(experiment/'synthesized.dcp')),
        unbounded_post_reset_formatter_equivalence_verified=equivalence is not None,equivalence=equivalence,
        native=native,routed_implementation_verified=native['phase']=='native_route_verified',routed_timing_verified=native['timing_met'],
        actual_rpc_matrix_replayed=False,full_raw_workload_replayed=False,full_system_complete=False,
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)))
    (root/'build/validation/compact-grpc-headers-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in('phase','synthesis_baseline_resources','synthesis_experiment_resources','synthesis_luts_saved','native','evidence_folder')},indent=2))


if __name__=='__main__':main()
