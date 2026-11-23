"""Preserve RPC return acceptance and bind it to exact native component RTL."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser();parser.add_argument('--native-run',default='rpc_generated_response_initial');args=parser.parse_args()
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    reports=root/'build/wsl-reports/cocotb_rpc_response'
    native=root/'build/implementation/xcsu35p-sbvb625-2-e'/args.native_run
    report=json.loads((reports/'report.json').read_text());acceptance=json.loads((reports/'acceptance.json').read_text())
    assert report['phase']==acceptance['phase']=='passed'and report['tests']==1 and report['failures']==0
    assert not report.get('changed_inputs')and report['acceptance_sha256']==sha(reports/'acceptance.json')
    tree=ET.parse(reports/'results.xml');cases=tree.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='bound_generated_tokens_and_durable_progress'
    assert not tree.findall('.//failure')and not tree.findall('.//error')
    rtl_count=0
    for name,digest in report['source_sha256'].items():
        assert sha(source_path(root, name))==digest,('Current source differs',name)
        if name.startswith('rtl/'):
            assert sha(native/'sources'/name)==digest,('Native RTL differs',name)
            rtl_count+=1
    assert rtl_count==17
    for name,digest in report['fixture_sha256'].items():assert sha(source_path(root, name))==digest,('Current fixture differs',name)
    fixtures=root/'build/rpc-response-fixtures';reference=json.loads((fixtures/'rpc_cases.json').read_text())
    assert reference['generator_sha256']==sha(root/'tools/generate_rpc_response_vectors.py')
    assert sha(fixtures/'memory.bin')==reference['model_image_sha256']==sha(root/'build/scu35/image/external_memory.bin')
    assert sha(fixtures/'model_manifest.json')==sha(root/'build/scu35/image/external_manifest.json')
    assert (acceptance['cases'],acceptance['successes'],acceptance['rejections'],acceptance['injected_faults'])==(178,108,70,21)
    assert acceptance['model_image_sha256']==reference['model_image_sha256']
    assert acceptance['actual_directory_load_verified']and acceptance['durable_rpc_carry_verified']
    assert acceptance['tx_stall_cycles']and acceptance['bow_stall_cycles']and acceptance['result_stall_cycles']
    assert acceptance['blocked_control_cycles']and acceptance['directory_lease_cycles']
    assert not acceptance['whole_rpc_gpu_image_lease_verified']and not acceptance['full_transport_verified']and not acceptance['full_system_verified']
    log=(source_path(root, f'build/{args.native_run}-implementation.log')).read_text()
    assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE'in log and '0 Critical Warnings and 0 Errors encountered.'in log
    assert 'Found timing loop'not in log and 'ERROR: [Synth'not in log
    timing=(native/'routed_timing.rpt').read_text()
    match=re.search(r'WNS\(ns\).*?\n[-\s]+\n\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)',timing,re.S)
    assert match
    wns,whs=float(match[1]),float(match[5]);timing_passed=wns>=0 and whs>=0 and int(match[3])==int(match[7])==0
    assert re.search(r'# of nets with routing errors\.+\s*:\s*0\s*:',(native/'route_status.rpt').read_text())
    assert 'Checks found: 0'in(native/'routed_drc.rpt').read_text()
    row=next(line for line in(native/'routed_utilization.rpt').read_text().splitlines()if re.match(r'\|\s+core\s+\|',line))
    cells=[cell.strip()for cell in row.split('|')[1:-1]]
    resources=dict(luts=int(cells[2]),registers=int(cells[6]),bram36=int(cells[7]),bram18=int(cells[8]),uram=int(cells[9]),dsps=int(cells[10]))
    key=hashlib.sha256((sha(reports/'report.json')+sha(native/'source-provenance.json')+sha(Path(__file__))).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-response-evidence'/key
    files={Path(name):source_path(root, name) for name in{**report['source_sha256'],**report['fixture_sha256']}}
    files.update({Path('reports')/name:reports/name for name in('report.json','acceptance.json','results.xml','simulation.log','build.log')})
    files.update({Path('native')/name:native/name for name in('source-provenance.json','routed_timing.rpt','routed_utilization.rpt','route_status.rpt','routed_drc.rpt')})
    files[Path('verification/verify_rpc_response.py')]=Path(__file__)
    for name,source in files.items():
        target=evidence/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(source),('Evidence already differs',name)
        else:shutil.copy2(source,target)
    result=dict(phase='passed'if timing_passed else'timing_failed',verified_utc=datetime.now(timezone.utc).isoformat(),
        functional_acceptance_verified=True,sources_verified=len(report['source_sha256']),fixtures_verified=len(report['fixture_sha256']),
        native_rtl_files_matched=rtl_count,native_rtl_snapshot=args.native_run,acceptance=acceptance,
        native_reference_packages=dict(tiktoken=reference['tiktoken_version']),ordinary_image_entries_checked=reference['ordinary_entries_verified'],
        core_resources=resources,clock_period_ns=4,routed_setup_wns_ns=wns,routed_hold_whs_ns=whs,routed_timing_passed=timing_passed,
        setup_failing_endpoints=int(match[3]),hold_failing_endpoints=int(match[7]),routing_errors=0,evidence_folder=str(evidence),
        verifier_sha256=sha(Path(__file__)),package_paths_excluded=True,native_harness_includes_rpc_directory_or_shared_fabric=False,
        whole_rpc_gpu_image_lease_integrated=False,maintenance_recovery_integrated=False,raw_forward_response_joined=False,
        transport_framing_integrated=False,physical_adapters_verified=False,sustained_throughput_verified=False,
        full_system_fit_verified=False,full_system_complete=False)
    output=root/'build/validation/rpc-response.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not timing_passed:raise SystemExit('Functional RPC response acceptance passed; routed 4 ns timing failed')


if __name__=='__main__':main()
