"""Audit unchanged lifecycle/fault fixtures, preserving measured time differences."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_relative


def differences(actual,baseline,path=()):
    if type(actual)!=type(baseline):
        yield path,actual,baseline
    elif isinstance(actual,dict):
        assert actual.keys()==baseline.keys(),path
        for key in sorted(actual):yield from differences(actual[key],baseline[key],path+(key,))
    elif isinstance(actual,list):
        assert len(actual)==len(baseline),path
        for index,(a,b) in enumerate(zip(actual,baseline)):yield from differences(a,b,path+(index,))
    elif actual!=baseline:yield path,actual,baseline


def timing_path(path):
    # Only established fixture measurement fields may differ. Data, statuses,
    # scopes, operation order and all other trace fields must remain identical.
    if path[0]=='actual_format_transactions':return path[-1] in ('clock','ack_clock','first_offer_clock','request_clock','result_ack_clock')
    if path[0] in ('actual_cancel_trace','actual_ordering'):return path[-1]=='clock'
    if path[0]=='actual_post_commit_retirement':return path[-1] in ('clock','held_original_result_cycles')
    if path[0]=='actual_receive_pool_ownership':return path[-1]=='receive_lock_cycles'
    if path[0]=='local_error_ownership':return path[-1] in ('clock','first_public_packet_result_clock','host_close_retired_clock','wire_retired_clock')
    return False


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('frame-event-buffer','frame-owned-quiet','payload-event-buffer','open-rpc-reclaim','rpc-completion-flags','rpc-success-predicate-v2'),default='frame-event-buffer');args=ap.parse_args()
    success=args.candidate=='rpc-success-predicate-v2'
    flags=args.candidate=='rpc-completion-flags' or success;payload=args.candidate=='payload-event-buffer' or flags;reclaim=args.candidate=='open-rpc-reclaim'
    quiet=args.candidate in ('frame-owned-quiet','open-rpc-reclaim') or payload
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    baseline_cases={}
    for name,key in (('progress-format-regressions','736eec1fa78adf7d'),('progress-format-experiment','c7aebf98ee6f7e25')):
        audit=read(root/'build/validation'/(name+'.json'));assert audit['key']==key
        for case,record in audit['executions'].items():assert case not in baseline_cases;baseline_cases[case]=(key,record)
    generation=read(root/'build/experiments'/args.candidate/'generation.json')
    parser_expected={Path(n).stem:h for n,h in generation['outputs_sha256'].items()}
    assert len(baseline_cases)==7
    executions={};artifacts={Path(__file__)}
    for case,(key,baseline) in baseline_cases.items():
        name=args.candidate.replace('-','_')+'_'+case+'_20261122'
        launch_path=root/'build/validation'/(name+'-launch.json');launch=read(launch_path)
        assert launch['phase']=='completed' and launch['exit_code']==0
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
        inputs=read(archive/'inputs.json');report=read(archive/'report.json');snapshot=read(archive/'snapshot.json');accepted=read(archive/'acceptance.json')
        assert launch['inputs_sha256']==report['input_sha256']==inputs
        assert report['phase']==accepted['phase']=='passed' and report['tests']==1 and report['failures']==0 and snapshot['exit_code']==0
        assert sha(archive/'acceptance.json')==report['acceptance_sha256']
        for n,h in inputs.items():assert sha(source/n)==h,n
        original=root/'build/wsl-reports'/('raw_envelope_'+baseline['snapshot'])
        old_inputs=read(original/'inputs.json');assert old_inputs==baseline['inputs_sha256']
        for n,h in old_inputs.items():
            if not n.startswith('rtl/'):assert inputs[n]==h,n
        actual_parser={n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}
        tokenizer={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
        original_tokenizer={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',original/'execution-sources').items()}
        assert actual_parser==parser_expected and len(tokenizer)==22 and tokenizer==original_tokenizer
        results=ET.parse(archive/'results.xml');old_results=ET.parse(original/'results.xml')
        tests=results.findall('.//testcase');old_tests=old_results.findall('.//testcase')
        assert len(tests)==len(old_tests)==1 and tests[0].attrib['name']==old_tests[0].attrib['name']
        assert not results.findall('.//failure') and not results.findall('.//error')
        deltas=[]
        for path,actual,prior in differences(accepted,read(original/'acceptance.json')):
            assert timing_path(path) and type(actual)==type(prior)==int and min(actual,prior)>=0,(case,path,actual,prior)
            deltas.append(dict(path=list(path),actual=actual,baseline=prior))
        assert sha(archive/'protocol-runner-used.py')==launch['driver_sha256']
        executions[case]=dict(snapshot=name,baseline_audit_key=key,baseline_snapshot=baseline['snapshot'],
            original_test_name=tests[0].attrib['name'],accepted=accepted,
            operation_data_status_and_scope_traces_equal=True,explicit_timing_measurement_differences=deltas,
            inputs_sha256=inputs,executed_tokenizer_sha256=tokenizer)
        artifacts.update([launch_path,*[p for p in archive.iterdir() if p.is_file()]])
    units=read(root/'build/validation'/('rpc-success-predicate.json' if success else 'rpc-completion-flags.json' if flags else 'open-rpc-reclaim-assembly.json' if reclaim else 'payload-event-buffer-units.json' if payload else 'frame-owned-quiet-formal.json' if quiet else 'frame-event-buffer-units.json'))
    if flags:assert units['full_production_response_subtree_induction_verified'] and units['actual_initial_reset_base_verified']
    if reclaim:assert units['key']=='ad1b6bc9beebcaf5' and units['source_edit_inverse_verified']
    assert units['executed_parser_sha256' if quiet else 'candidate_parser_sha256']==parser_expected
    result=dict(phase=args.candidate.replace('-','_')+'_original_protocol_replays_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,unit_audit_key=units['key'],executed_parser_sha256=parser_expected,
        exact_parser_modules=77 if payload or reclaim else 76,exact_tokenizer_modules=22,full_original_protocol_stimulus_preserved=True,
        all_operation_data_status_and_scope_traces_equal_baselines=True,
        timing_measurement_differences_preserved=True,full_protocol_matrix_verified=False,
        latest_31_module_tokenizer_controller_integrated=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p) for p in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    audit_name=args.candidate+'-protocol'
    target=root/'build/validation'/(audit_name+'-evidence')/result['key'];target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation'/(audit_name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],executions=len(executions),timing_measurement_differences=sum(len(e['explicit_timing_measurement_differences']) for e in executions.values()))))


if __name__=='__main__':main()
