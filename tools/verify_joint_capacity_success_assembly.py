"""Audit composed production linkage and native elaboration, not runtime."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_dual_fpga_hyperram_integration import verify_order
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    folder=root/'build/validation'/args.name;generation=read(folder/'generation.json');report=read(folder/'report.json')
    assert generation['capacity_composed'] and generation['schema_mmio'] and generation['success_predicate_integrated']
    assert report['parser_modules']==generation['parser_modules']==79 and report['tokenizer_modules']==31
    assert report['inputs_sha256']==generation['outputs_sha256'] and report['generation_sha256']==sha(folder/'generation.json')
    for n,h in report['inputs_sha256'].items():assert sha(folder/n)==h,n
    assert sha(folder/'generate_joint_capacity_success_test.py')==generation['generator_sha256']
    parent=root/'build/validation'/generation['composition_parent_run']
    parent_audit=read(root/'build/validation/joint-hyperram-schema-owned-quiet.json')
    assert parent_audit['key']==generation['composition_parent_audit_key']=='3072016f57de6d32'
    assert parent_audit['run']==parent.name and sha(parent/'report.json')==generation['composition_parent_report_sha256']==parent_audit['report_sha256']
    parent_inputs=read(parent/'report.json')['inputs_sha256'];assert parent_inputs==generation['composition_parent_inputs_sha256']
    capacity=read(root/'build/validation/receive-capacity-v4-assembly.json')
    runtime=read(root/'build/validation/receive-capacity-format-owner.json')
    success=read(root/'build/validation/rpc-success-predicate.json')
    semantic=read(root/'build/validation/payload-event-buffer-units.json')
    assert capacity['key']==generation['capacity_assembly_audit_key']=='69a29b3c155b339f'
    assert runtime['key']==generation['capacity_directed_runtime_audit_key']=='2ad2339cea44fec0'
    assert success['key']==generation['success_predicate_audit_key']=='a4f36fdbbab5143f'
    assert semantic['key']==generation['semantic_payload_audit_key']=='5707783a4aa0af25'
    assert success['full_production_response_subtree_induction_verified'] and success['actual_initial_reset_base_verified']
    assert capacity['source_edit_inverse_verified'] and capacity['earlier_command_and_control_offers_preserved']
    cap_source=root/'build/experiments/receive-capacity-v4';pred_source=root/'build/experiments/rpc-success-predicate-v2'
    cap_gen=read(cap_source/'generation.json')
    assert sha(cap_source/'generation.json')==generation['portable_capacity_generation_sha256']==capacity['generation_sha256']
    assert sha(pred_source/'generation.json')==generation['portable_success_generation_sha256']==success['generation_sha256']
    expected={n:cap_source/'rtl'/(n+'.v') for n in cap_gen['changed_existing_modules']+['grpc_payload_reclaimer']}
    expected.update({n:pred_source/'rtl'/(n+'.v') for n in ('http2_payload_decoder','axis_pingpong_skid_buffer','rpc_http2_response_partition','rpc_grpc_http2_parser_response')})
    certificates=generation['exact_overlay_source_certificates'];assert set(certificates)==set(expected) and len(expected)==14
    for n,p in expected.items():
        certificate=certificates[n];native=folder/'joint/rtl'/(n+'.v')
        digest=(capacity['executed_parser_sha256'] if p.parent.parent==cap_source else success['executed_parser_sha256'])[n]
        assert sha(p)==certificate['portable_raw_sha256']==digest and certificate['portable_source']==p.relative_to(root).as_posix()
        assert sha(native)==certificate['native_sha256']
        verify_order(p.read_text(),native.read_text(),certificate['declaration_order_certificate'])
        assert ports(p.read_text(),n)==ports(native.read_text(),n)
    changed={n for n,h in parent_inputs.items() if sha(folder/n)!=h}
    assert changed=={'joint/rtl/'+n+'.v' for n in expected if 'joint/rtl/'+n+'.v' in parent_inputs} and len(changed)==12
    assert set(report['inputs_sha256'])-set(parent_inputs)=={'generate_joint_capacity_success_test.py','joint/rtl/grpc_payload_reclaimer.v','joint/rtl/axis_pingpong_skid_buffer.v'}
    for n,h in parent_inputs.items():
        if n not in changed:assert sha(folder/n)==h,n
    parser={n:sha(p) for n,p in closure('http2_schema_mmio_application',folder/'joint').items()}
    tokenizer={n:sha(p) for n,p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',folder/'joint').items()}
    assert len(parser)==79 and parser==generation['canonical_parser_sha256']
    assert len(tokenizer)==31 and tokenizer==generation['canonical_tokenizer_sha256']
    assert tokenizer=={n:sha(p) for n,p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',parent/'joint').items()}
    for n in ('cdc','memory','fifo'):
        p=folder/f'joint/vendor/xpm_{n}.sv'
        assert sha(p)==sha(Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+n)/'hdl'/p.name)
    production=sorted((folder/'joint/rtl').glob('*.v'))+[folder/'joint/vendor/glbl.v']
    assert (folder/'production.prj').read_text()==''.join('verilog work "'+p.relative_to(folder).as_posix()+'"\n' for p in production)
    compiled=(folder/'production.log').read_text();elaborated=(folder/'elaboration-stdout.log').read_text()
    assert all(p.name in compiled for p in production)
    assert not re.search(r'^\s*(?:ERROR|FATAL|Error|Fatal):',compiled+elaborated,re.M)
    assert 'Built simulation snapshot joint_hyperram_grpc' in elaborated
    assert report['production_compiled_as_verilog'] and report['native_vendor_memory'] and not report['portable_backend']
    assert report['normal_global_startup'] and report['compatibility_defines']==['OBSOLETE'] and report['testbench_assertions_enabled']
    block=read(root/'build/validation/joint-capacity-success-native-runtime-block.json')
    assert block['run']==args.name and block['code_integrity_event_id']==3077 and not block['native_runtime_started']
    assert block['executable_sha256']==sha(folder/'xsim.dir/joint_hyperram_grpc/xsimk.exe')
    assert block['generation_sha256']==sha(folder/'generation.json') and report['phase']=='native_joint_workload_failed'
    result=dict(phase='composed_capacity_success_native_elaboration_verified_runtime_blocked',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,parser_modules=79,tokenizer_modules=31,parent_native_runtime_audit_key=parent_audit['key'],
        capacity_assembly_audit_key=capacity['key'],capacity_directed_runtime_audit_key=runtime['key'],success_predicate_audit_key=success['key'],
        semantic_payload_audit_key=semantic['key'],generation_sha256=sha(folder/'generation.json'),
        full_original_two_images_32_requests_and_assertions_unchanged=True,exact_overlay_and_native_declaration_order_verified=True,
        native_vendor_sources_unchanged=True,native_production_compilation_verified=True,native_elaboration_verified=True,
        executed_parser_sha256=parser,executed_tokenizer_sha256=tokenizer,
        native_runtime_started=False,native_runtime_verified=False,code_integrity_runtime_block_verified=True,
        native_timing_verified=False,full_protocol_fault_matrix_verified=False,full_system_complete=False,
        production_project_sha256=sha(folder/'production.prj'),elaboration_log_sha256=sha(folder/'xelab.log'),
        artifacts_sha256={p.relative_to(root).as_posix():sha(p) for p in [folder/'report.json',folder/'generation.json',folder/'production.prj',folder/'production.log',folder/'xelab.log',root/'build/validation/joint-capacity-success-native-runtime-block.json']},
        verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/joint-capacity-success-native-assembly-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    for p in (evidence/'audit.json',root/'build/validation/joint-capacity-success-native-assembly.json'):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','parser_modules','tokenizer_modules','native_runtime_started')}))


if __name__=='__main__':main()
