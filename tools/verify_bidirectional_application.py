"""Bind joint wire/DMA/return acceptance to exact combined native synthesis."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET


def main():
    root=Path(__file__).resolve().parents[1];parser=argparse.ArgumentParser()
    parser.add_argument('--native-run',default='http2_bidirectional_application_registered_grant');args=parser.parse_args()
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    reports=root/'build/wsl-reports/cocotb_bidirectional';fixtures=root/'build/bidirectional-fixtures'
    native=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run
    report=json.loads((reports/'report.json').read_text());acceptance=json.loads((reports/'acceptance.json').read_text())
    oracle_file=root/'build/bidirectional-reference-validation.json';oracle=json.loads(oracle_file.read_text())
    reverse=json.loads((fixtures/'response_reference.json').read_text())
    assert report['phase']==acceptance['phase']==oracle['phase']=='passed'
    assert report['suite']=='bidirectional'and report['tests']==1 and report['failures']==0 and not report.get('changed_inputs')
    assert report['acceptance_sha256']==sha(reports/'acceptance.json')
    tree=ET.parse(reports/'results.xml');cases=tree.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='raw_requests_and_actual_dma_token_returns'
    assert not tree.findall('.//failure')and not tree.findall('.//error')
    rtl_count=0
    for name,digest in report['source_sha256'].items():
        assert sha(root/name)==digest,('Current source differs',name)
        if name.startswith('rtl/'):
            assert sha(native/'sources'/name)==digest,('Combined native RTL differs',name)
            rtl_count+=1
    assert rtl_count>=60
    for name,digest in report['fixture_sha256'].items():
        assert sha(root/name)==digest,('Current fixture differs',name)
        if Path(name).name!='response_reference.json':assert oracle['fixture_sha256'][Path(name).name]==digest
    assert len(report['fixture_sha256'])==7
    assert oracle['verifier_sha256']==sha(root/'tools/verify_http2_prefill_references.py')
    assert reverse['generator_sha256']==sha(root/'tools/generate_bidirectional_vectors.py')
    assert reverse['packet_reference_sha256']==sha(root/'tools/generate_rpc_response_vectors.py')
    assert oracle['complete_model_prefix_matches_image']and oracle['model_ordinary_tokens']==100256
    assert oracle['model_image_sha256']==sha(root/'build/scu35/image/external_memory.bin')
    assert oracle['model_manifest_sha256']==sha(root/'build/scu35/image/external_manifest.json')
    assert (acceptance['packets'],acceptance['headers'],acceptance['messages'],acceptance['token_ids'],
            acceptance['packet_aborts'],acceptance['rejected'],acceptance['connection_opens'],acceptance['memory_faults'])==(38,21,16,2828,4,3,7,2)
    assert (oracle['wire_packets'],oracle['grpc_messages'],oracle['native_token_ids'])==(38,16,2828)
    assert acceptance['response_chunks']==reverse['response_chunks']==2828
    assert acceptance['response_bytes']==reverse['response_bytes']==144686
    assert acceptance['response_rejections']==4 and acceptance['response_memory_faults']==1
    assert acceptance['shared_actual_rpc_directory']and acceptance['actual_dma_ids_returned']and acceptance['model_and_policy_immutable']
    assert acceptance['full_model_bytes']==8388608
    assert acceptance['early_gpu_admissions']and acceptance['return_waited_for_prefill_cycles']
    assert acceptance['mid_packet_gpu_admissions']and acceptance['continued_rx_beats']and acceptance['registered_schedule_owned_cycles']
    assert acceptance['response_stall_cycles']and acceptance['response_held_result_cycles']and acceptance['dma_stall_cycles']
    assert not acceptance['complete_http2_transport_verified']and not acceptance['response_transport_framing_verified']
    assert not acceptance['whole_rpc_gpu_image_lease_verified']and not acceptance['full_system_complete']
    log_file=root/f'build/{args.native_run}-implementation.log';log=log_file.read_text()
    assert 'REGISTERED_SUBSYSTEM_SYNTHESIS_COMPLETE TOP=http2_bidirectional_application PART=xcsu35p-sbvb625-2-e'in log
    assert '0 Critical Warnings and 0 Errors encountered.'in log
    assert 'Found timing loop'not in log and 'ERROR: [Synth'not in log
    utilization=(native/'synthesis_utilization.rpt').read_text()
    row=next(line for line in utilization.splitlines()if re.match(r'\|\s+core\s+\|',line))
    cells=[c.strip()for c in row.split('|')[1:-1]]
    resources=dict(luts=int(cells[2]),registers=int(cells[6]),bram36=int(cells[7]),bram18=int(cells[8]),uram=int(cells[9]),dsps=int(cells[10]))
    timing=(native/'synthesis_timing.rpt').read_text()
    match=re.search(r'WNS\(ns\).*?\n[-\s]+\n\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)',timing,re.S)
    assert match
    setup_path=re.search(r'Slack \((?:VIOLATED|MET)\).*?Source:\s*(.*?)\n.*?Destination:\s*(.*?)\n.*?Logic Levels:\s*(\d+)',timing,re.S)
    assert setup_path
    path_check_file=root/'build/validation/registered-grant-path-check.json'
    path_check=json.loads(path_check_file.read_text())
    assert path_check['phase']=='passed'
    assert len(path_check['runs'])==2 and path_check['runs'][0]['timing_paths_found']>0 and path_check['runs'][1]['timing_paths_found']==0
    assert path_check['runs'][1]['native_run']==args.native_run
    assert all(item['source_register_pins']and item['destination_enable_pins']for item in path_check['runs'])
    path_check_inputs={}
    for item in path_check['runs']:
        folder=native.parent/item['native_run']
        for name in ('synthesized.dcp','source-provenance.json'):
            path=folder/name
            path_check_inputs[path.relative_to(root).as_posix()]=sha(path)
    lut_fit=resources['luts']<=16320
    key=hashlib.sha256((sha(reports/'report.json')+sha(oracle_file)+sha(native/'source-provenance.json')+sha(Path(__file__))).encode()).hexdigest()[:16]
    evidence=root/'build/validation/bidirectional-application-evidence'/key
    files={Path(name):root/name for name in{**report['source_sha256'],**report['fixture_sha256']}}
    files.update({Path('reports')/name:reports/name for name in('report.json','acceptance.json','results.xml','simulation.log','build.log')})
    files.update({Path('native')/name:native/name for name in('source-provenance.json','synthesis_utilization.rpt','synthesis_timing.rpt')})
    files[Path('native/synthesis.log')]=log_file;files[Path('native-reference.json')]=oracle_file
    files[Path('native/registered-grant-path-check.json')]=path_check_file
    files[Path('native/registered-grant-path-check.log')]=root/'build/registered-grant-path-check.log'
    files[Path('verification/check_registered_grant_path.tcl')]=root/'scripts/check_registered_grant_path.tcl'
    for name in('external_memory.bin','external_manifest.json'):files[Path('model')/name]=root/'build/scu35/image'/name
    for name in('verify_bidirectional_application.py','verify_http2_prefill_references.py'):files[Path('verification')/name]=root/'tools'/name
    for name,source in files.items():
        target=evidence/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source),('Immutable evidence differs',name)
        else:shutil.copy2(source,target)
    result=dict(phase='functional_passed_native_fit_pending'if lut_fit else'functional_passed_native_over_capacity',
        verified_utc=datetime.now(timezone.utc).isoformat(),joint_application_acceptance_verified=True,
        sources_verified=len(report['source_sha256']),fixtures_verified=len(report['fixture_sha256']),native_rtl_files_matched=rtl_count,
        native_rtl_snapshot=args.native_run,acceptance=acceptance,native_reference_packages=oracle['packages'],
        model_ordinary_tokens=100256,complete_model_prefix_verified=True,core_resources=resources,
        available_device_luts=16320,native_lut_fit=lut_fit,luts_over_capacity=max(0,resources['luts']-16320),
        clock_period_ns=4,synthesis_setup_wns_estimate_ns=float(match[1]),routed_timing_verified=False,
        critical_setup_source=setup_path[1],critical_setup_destination=setup_path[2],critical_setup_logic_levels=int(setup_path[3]),
        serializer_to_ingress_enable_path_cut_verified=True,registered_grant_timing_check=path_check,
        registered_grant_checkpoint_inputs_sha256=path_check_inputs,
        native_harness_includes_shared_cache_fabric=False,package_paths_excluded=True,
        evidence_folder=str(evidence),verifier_sha256=sha(Path(__file__)),
        complete_http2_transport_verified=False,response_transport_framing_integrated=False,
        whole_rpc_gpu_image_lease_integrated=False,physical_adapters_verified=False,
        sustained_throughput_verified=False,full_system_fit_verified=False,full_system_complete=False)
    output=root/'build/validation/bidirectional-application.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
