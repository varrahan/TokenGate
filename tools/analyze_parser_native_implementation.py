"""Audit an AU15P implementation against the exact tested Parser sources."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    launch_path=root/'build/validation'/(args.run+'-launch.json');launch=read(launch_path)
    assert launch['phase']=='native_process_completed'and launch['exit_code']==0
    assert launch['part']=='xcau15p-ffvb676-2-e'and launch['max_threads']==1
    top=launch['top'];assert top in('proto_json_decoder','http2_enveloped_parser_application')
    role='json-simd-decoder'if top=='proto_json_decoder'else'progress-format-parser'
    if 'functional_source_audit_name'in launch:
        assert top=='http2_enveloped_parser_application'
        assert launch['functional_source_audit_name']in('freeze-idle-experiment','json-simd-corpus','frame-event-buffer-corpus','frame-event-buffer-units','frame-owned-quiet-formal','payload-event-buffer-units','rpc-completion-flags','rpc-success-predicate','rpc-stream-refusal-v7-directed','rpc-registered-frame-select-v1-directed','receive-payload-settling')
        role={'freeze-idle-experiment':'freeze-idle-parser','json-simd-corpus':'json-simd-parser',
              'frame-event-buffer-corpus':'frame-event-buffer-parser','frame-event-buffer-units':'frame-event-buffer-parser',
              'frame-owned-quiet-formal':'frame-owned-quiet-parser','payload-event-buffer-units':'payload-event-buffer-parser',
              'rpc-completion-flags':'rpc-completion-flags-parser','rpc-success-predicate':'rpc-success-predicate-parser',
              'rpc-stream-refusal-v7-directed':'rpc-refusal-v7-parser',
              'rpc-registered-frame-select-v1-directed':'rpc-registered-select-parser',
              'receive-payload-settling':'receive-payload-pipeline-parser'}[launch['functional_source_audit_name']]
    folder=root/'build/implementation'/launch['part']/args.run;frozen=folder/'sources'
    inputs=root/'build/validation'/(args.run+'-inputs')
    provenance_path=folder/'source-provenance.json';provenance=read(provenance_path)
    artifacts={launch_path,provenance_path,Path(__file__)}
    for name,record in provenance['files'].items():
        path=frozen/name;assert sha(path)==record['sha256'],name;artifacts.add(path)
    for name,digest in launch['inputs_sha256'].items():
        assert sha(inputs/name)==digest,name
        actual=frozen/('timing.xdc'if name=='constraints/parser.xdc'else name)
        assert sha(actual)==digest,('Implemented input differs from the launch freeze',name)
    if role in('freeze-idle-parser','json-simd-parser','frame-event-buffer-parser','frame-owned-quiet-parser','payload-event-buffer-parser','rpc-completion-flags-parser','rpc-success-predicate-parser','rpc-refusal-v7-parser','rpc-registered-select-parser','receive-payload-pipeline-parser'):
        functional_path=inputs/'source-functional-audit.json';functional=read(functional_path)
        assert functional['key']==launch['functional_source_audit_key']
        assert sha(functional_path)==launch['functional_source_audit_sha256']
        if launch['functional_source_audit_name']=='receive-payload-settling':
            from verify_receive_payload_settling import require_settling_audit
            qualified=require_settling_audit(root)
            assert functional['key']==qualified['key']
            assert functional['production_address_width']==23 and functional['production_context_width']==16
            assert functional['capacity_and_stream_format_enabled']
            candidate=root/'build/experiments/rpc-receive-payload-pipeline-v1'
            assert sha(candidate/'generation.json')==functional['generation_sha256']
            expected=functional['candidate_parser_sha256'];assert len(expected)==78
            artifacts.update((root/'build/validation/receive-payload-settling.json',candidate/'generation.json'))
        elif launch['functional_source_audit_name']=='rpc-registered-frame-select-v1-directed':
            from verify_registered_frame_select import require_unit_audit
            unit=require_unit_audit(root)
            assert functional['key']=='381fe48f058bf0b1'and functional['four_directed_application_runs_verified']
            assert functional['full_pair_strict_vendor_elaboration_verified']and functional['registered_selection_unit_audit_key']==unit['key']
            gpu_path=root/'build/validation/rpc-registered-select-gpu.json';gpu=read(gpu_path)
            assert gpu['key']=='c5a8fb353b291447'and len(gpu['executions'])==2
            candidate=root/'build/experiments/rpc-registered-frame-select-v1'
            assert sha(candidate/'generation.json')==functional['generation_sha256']==gpu['generation_sha256']==unit['generation_sha256']
            expected=functional['executed_parser_sha256'];assert len(expected)==78
            artifacts.update((gpu_path,root/'build/validation/registered-frame-select-unit.json',candidate/'generation.json'))
        elif launch['functional_source_audit_name']=='rpc-stream-refusal-v7-directed':
            assert functional['key']=='950ce3b65ccb9b0a'and functional['four_directed_application_runs_verified']
            assert functional['full_pair_strict_vendor_elaboration_verified']and functional['exact_source_edits_and_native_declaration_order_verified']
            faults_path=root/'build/validation/rpc-refusal-ack-faults.json'
            formal_path=root/'build/validation/rpc-refusal-default-open-equivalence.json'
            faults=read(faults_path);formal=read(formal_path)
            assert faults['key']=='12513e8bd9c65f5d'and faults['actual_memory_response_positions']==46
            assert formal['key']=='462e4c8b3b38971b'and formal['default_open_conditional_equivalence_verified']
            candidate=root/'build/experiments/rpc-stream-refusal-v7'
            assert sha(candidate/'generation.json')==functional['generation_sha256']==faults['generation_sha256']==formal['candidate_generation_sha256']
            expected=functional['executed_parser_sha256']
            assert faults['executed_parser_sha256']==expected and len(expected)==78
            artifacts.update((faults_path,formal_path,candidate/'generation.json'))
        elif launch['functional_source_audit_name']=='rpc-success-predicate':
            assert functional['full_production_response_subtree_induction_verified'] and functional['actual_initial_reset_base_verified']
            assert functional['predicate_equivalence_verified'] and functional['proven_equivalence_cells']==4295
            assert functional['original_output_ports_compared']==72 and functional['exact_parser_modules']==77
            corpus_path=root/'build/validation/rpc-success-predicate-v2-corpus.json';corpus=read(corpus_path)
            assert corpus['full_native_corpus_verified'] and corpus['unit_audit_key']==functional['key']
            assert corpus['executed_parser_sha256']==functional['executed_parser_sha256']
            expected=corpus['executed_parser_sha256'];artifacts.add(corpus_path)
        elif launch['functional_source_audit_name']=='rpc-completion-flags':
            assert functional['full_production_response_subtree_induction_verified'] and functional['actual_initial_reset_base_verified']
            assert functional['original_output_ports_compared']==72 and functional['exact_parser_modules']==77
            corpus_path=root/'build/validation/rpc-completion-flags-corpus.json';corpus=read(corpus_path)
            assert corpus['full_native_corpus_verified'] and corpus['unit_audit_key']==functional['key']
            assert corpus['executed_parser_sha256']==functional['executed_parser_sha256']
            expected=corpus['executed_parser_sha256'];artifacts.add(corpus_path)
        elif launch['functional_source_audit_name']=='payload-event-buffer-units':
            assert functional['unbounded_fifo_induction_verified'] and functional['exact_parser_modules']==77
            corpus_path=root/'build/validation/payload-event-buffer-corpus.json';corpus=read(corpus_path)
            assert corpus['full_native_corpus_verified'] and corpus['unit_audit_key']==functional['key']
            assert corpus['executed_parser_sha256']==functional['executed_parser_sha256']
            expected=corpus['executed_parser_sha256'];artifacts.add(corpus_path)
        elif launch['functional_source_audit_name']=='frame-owned-quiet-formal':
            assert functional['conservative_idle_induction_verified'] and functional['exact_parser_modules']==76
            corpus_path=root/'build/validation/frame-owned-quiet-corpus.json';corpus=read(corpus_path)
            assert corpus['full_native_corpus_verified'] and corpus['unit_audit_key']==functional['key']
            assert corpus['executed_parser_sha256']==functional['executed_parser_sha256']
            expected=corpus['executed_parser_sha256'];artifacts.add(corpus_path)
        elif launch['functional_source_audit_name']=='frame-event-buffer-units':
            assert functional['source_edit_replay_verified'] and functional['exact_parser_modules']==76
            corpus_path=root/'build/validation/frame-event-buffer-corpus.json';corpus=read(corpus_path)
            assert corpus['full_native_corpus_verified'] and corpus['unit_audit_key']==functional['key']
            assert corpus['executed_parser_sha256']==functional['candidate_parser_sha256']
            expected=corpus['executed_parser_sha256'];artifacts.add(corpus_path)
        elif role=='freeze-idle-parser':
            assert functional['full_original_protocol_stimulus_preserved']and len(functional['executions'])==7
            assert functional['parent_corpus_audit_key']=='6dd529d376e06926'
        else:assert functional['full_native_corpus_verified']
        if launch['functional_source_audit_name']not in('frame-event-buffer-units','frame-owned-quiet-formal','payload-event-buffer-units','rpc-completion-flags','rpc-success-predicate','rpc-stream-refusal-v7-directed','rpc-registered-frame-select-v1-directed','receive-payload-settling'):expected=functional['executed_parser_sha256']
        assert len(expected)==(78 if role in('rpc-refusal-v7-parser','rpc-registered-select-parser','receive-payload-pipeline-parser')else 75 if role=='freeze-idle-parser'else 77 if role in('payload-event-buffer-parser','rpc-completion-flags-parser','rpc-success-predicate-parser')else 76)
        driver=inputs/'run_audited_parser_implementation.py'
    elif role=='progress-format-parser':
        functional_path=inputs/'functional-corpus-audit.json';functional=read(functional_path)
        assert functional['key']==launch['functional_corpus_audit_key']=='6dd529d376e06926'
        assert sha(functional_path)==launch['functional_corpus_audit_sha256']
        expected=functional['executed_parser_sha256'];assert len(expected)==75
        driver=inputs/'run_progress_format_implementation.py'
    else:
        functional_path=inputs/'functional-report.json';functional=read(functional_path)
        assert functional['passed']and functional['full_default_decoder_parameters']
        assert sha(functional_path)==launch['functional_report_sha256']
        assert functional['expected']['committed']==32 and functional['expected']['maximum_text_bytes']==16200
        expected={Path(name).stem:digest for name,digest in functional['revisions']['candidate']['inputs_sha256'].items()if name.startswith('rtl/')}
        assert len(expected)==11;driver=inputs/'run_json_simd_decoder_implementation.py'
    assert sha(driver)==launch['driver_sha256'];artifacts.update((functional_path,driver))
    dependencies=closure(top,frozen)
    assert {module:sha(path)for module,path in dependencies.items()}==expected
    for module,path in dependencies.items():assert launch['inputs_sha256']['rtl/'+path.name]==expected[module]
    harness=frozen/'timing_harness.v';assert sha(harness)==launch['harness_sha256']
    # Reproduce every neighboring register from the frozen public interface.
    with tempfile.TemporaryDirectory(prefix='ph-',dir=root/'build')as temporary:
        replay=Path(temporary);assert replay.resolve().is_relative_to((root/'build').resolve())
        output=replay/'harness.v'
        subprocess.run([sys.executable,str(frozen/'tools/generate_parser_timing_harness.py'),
            '--source',str(frozen/'rtl'/(top+'.v')),'--top',top,'--harness-top',top+'_timing_harness',
            '--output',str(output)],check=True,capture_output=True)
        assert sha(output)==sha(harness)
    script=(frozen/'scripts/implement_registered_subsystem.tcl').read_text()
    assert script.count('set_false_path')==2 and all(word not in script for word in('set_clock_groups','set_multicycle_path','create_waiver'))
    assert all('{'+code+'}'in script and '-new_severity ERROR'in script for code in('Synth 8-326','Synth 8-295','Synth 8-6859'))
    assert (frozen/'timing.xdc').read_text().strip()=='create_clock -name axis_clk -period 4.000 [get_ports clk]'
    log=root/'build'/(args.run+'-implementation.log');text=log.read_text(errors='replace');artifacts.add(log)
    assert 'REGISTERED_SUBSYSTEM_ROUTE_COMPLETE TOP='+top+' PART='+launch['part']+' CLOCK_PERIOD_NS=4.000 PACKAGE_TIMING_EXCLUDED=1'in text
    assert 'route_design completed successfully'in text and 'ERROR:'not in text and 'Found timing loop'not in text
    with ZipFile(folder/'routed.dcp')as archive:xml=ET.fromstring(archive.read('dcp.xml'))
    fields={node.tag:node.attrib.get('Name')for node in xml}
    assert fields['Part']==launch['part']and fields['Top']==top+'_timing_harness'and fields['OutOfContext']=='1'
    timing=(folder/'routed_timing.rpt').read_text()
    row=re.search(r'^\s*([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s+([\d.-]+)\s+([\d.-]+)\s+(\d+)\s+(\d+)\s*$',timing,re.M);assert row
    measured=dict(setup_slack_ns=float(row[1]),hold_slack_ns=float(row[5]),pulse_width_slack_ns=float(row[9]),
        setup_failing_endpoints=int(row[3]),hold_failing_endpoints=int(row[7]),pulse_failing_endpoints=int(row[11]))
    timing_met=all(measured[key]>=0 for key in('setup_slack_ns','hold_slack_ns','pulse_width_slack_ns'))
    assert timing_met==('All user specified timing constraints are met.'in timing)
    unconstrained={key:int(re.search(r'checking '+key+r' \((\d+)\)',timing)[1])for key in
        ('no_clock','constant_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops')}
    area=(folder/'routed_utilization.rpt').read_text()
    def resources(instance,module):
        rows=[[cell.strip()for cell in line.split('|')[1:-1]]for line in area.splitlines()if line.startswith('|')]
        cells=next(row for row in rows if len(row)==11 and row[0]==instance and row[1]==module)
        return dict(luts=int(cells[2]),lutram=int(cells[4]),registers=int(cells[6]),bram36=int(cells[7]),bram18=int(cells[8]),uram=int(cells[9]),dsps=int(cells[10]))
    core=resources('core',top);total=resources(top+'_timing_harness','(top)')
    part_path=root/'build/parser-candidates/xcau15p-properties.txt';part_text=part_path.read_text();artifacts.add(part_path)
    capacities={key:int(re.search(r'^'+name+r'\s+\S+\s+true\s+(\d+)',part_text,re.M)[1])for key,name in
        dict(luts='LUT_ELEMENTS',registers='FLIPFLOPS',bram36='BLOCK_RAMS',dsps='DSP').items()}
    fit=all(core[key]<=capacities[key]for key in('luts','registers','dsps'))and core['bram36']+core['bram18']/2<=capacities['bram36']and core['uram']==0
    route=(folder/'route_status.rpt').read_text()
    errors=int(re.search(r'nets with routing errors\.+\s*:\s*(\d+)',route)[1])
    routable=int(re.search(r'# of routable nets\.+\s*:\s*(\d+)',route)[1]);routed=int(re.search(r'# of fully routed nets\.+\s*:\s*(\d+)',route)[1])
    assert errors==0 and routable==routed
    drc=(folder/'routed_drc.rpt').read_text()
    checks=[dict(rule=rule,severity=severity,checks=int(number))for rule,severity,number in re.findall(
        r'^\|\s*([\w-]+)\s*\|\s*(Warning|Error|Critical Warning|Advisory)\s*\|[^\n]*?\|\s*(\d+)\s*\|',drc,re.M)]
    assert sum(row['checks']for row in checks)==int(re.search(r'Checks found:\s*(\d+)',drc)[1])
    for path in folder.iterdir():
        if path.is_file()and path.suffix in('.json','.rpt','.dcp'):artifacts.add(path)
    critical=re.search(r'Max Delay Paths\n-+\n(.*?)(?=\nMin Delay Paths)',timing,re.S);assert critical
    first=critical[1]
    result=dict(phase='audited_parser_native_implementation_recorded',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.run,role=role,part=launch['part'],top=top,exact_core_modules=len(dependencies),core_resources=core,
        capacity=capacities,resource_fit=fit,timing_neighbor_registers=total['registers']-core['registers'],
        clock_period_ns=4.0,timing_met=timing_met,**measured,unconstrained=unconstrained,
        first_setup_source=re.search(r'Source:\s+([^\n]+)',first)[1].strip(),
        first_setup_destination=re.search(r'Destination:\s+([^\n]+)',first)[1].strip(),
        first_setup_logic_levels=int(re.search(r'Logic Levels:\s+(\d+)',first)[1]),
        fully_routed_nets=routed,routing_errors=errors,reported_drc_checks=checks,
        exact_tested_source_digests_verified=True,harness_replay_verified=True,
        package_timing_verified=False,pin_level_phy_verified=False,physical_link_verified=False,pcie_verified=False,
        whole_system_reset_fault_matrix_verified=False,full_protocol_matrix_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in sorted(artifacts)})
    if role=='rpc-refusal-v7-parser':
        result.update(directed_functional_audit_key=functional['key'],ack_fault_audit_key=faults['key'],
            default_open_equivalence_audit_key=formal['key'],full_new_source_32_call_runtime_verified=False,
            retained_reset_and_concurrent_refusal_gpu_faults_verified=False)
    if role=='rpc-registered-select-parser':
        result.update(directed_functional_audit_key=functional['key'],registered_selection_unit_audit_key=unit['key'],
            registered_selection_gpu_audit_key=gpu['key'],full_new_source_32_call_runtime_verified=False,
            new_source_ack_fault_matrix_verified=False,retained_reset_and_concurrent_refusal_gpu_faults_verified=False)
    if role=='receive-payload-pipeline-parser':
        result.update(settling_and_source_consumption_audit_key=functional['key'],
            functional_equivalence_derived_from_settling_and_exact_source_inverse=True,
            direct_all_public_output_induction_verified=False,exact_tested_source_digests_verified=False,
            exact_qualified_source_digests_verified=True,actual_new_source_runtime_verified=False,
            full_new_source_32_call_runtime_verified=False,new_source_ack_fault_matrix_verified=False,
            retained_reset_and_concurrent_refusal_gpu_faults_verified=False)
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    output=root/'build/validation'/(role+'-native.json');output.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation'/(role+'-native-evidence')/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(output,evidence/'verified.json');target=evidence/'tools'/Path(__file__).name;target.parent.mkdir();shutil.copy2(Path(__file__),target)
    print(json.dumps({key:result[key]for key in('phase','key','run','core_resources','resource_fit','timing_met','setup_slack_ns','hold_slack_ns')}))


if __name__=='__main__':main()
