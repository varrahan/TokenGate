"""Compose actual capacity, semantic buffering, success flags and native memory."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_dual_fpga_hyperram_integration import order_declarations
from generate_hyperram_cdc_timing_harness import ports
from verify_dual_fpga_hyperram_integration import verify_order
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    joint=read(root/'build/validation/joint-hyperram-schema-owned-quiet.json')
    capacity=read(root/'build/validation/receive-capacity-v4-assembly.json')
    runtime=read(root/'build/validation/receive-capacity-format-owner.json')
    success=read(root/'build/validation/rpc-success-predicate.json')
    semantic=read(root/'build/validation/payload-event-buffer-units.json')
    assert joint['key']=='3072016f57de6d32' and joint['full_http2_schema_mmio_functional_workload_verified']
    assert capacity['key']=='69a29b3c155b339f' and capacity['earlier_command_and_control_offers_preserved']
    assert runtime['key']=='2ad2339cea44fec0' and runtime['actual_private_lock_blocks_new_format']
    assert success['key']=='a4f36fdbbab5143f' and success['predicate_equivalence_verified'] and success['proven_equivalence_cells']==4295
    assert semantic['key']=='5707783a4aa0af25' and semantic['unbounded_fifo_induction_verified']
    parent=root/'build/validation'/joint['run'];report=read(parent/'report.json')
    assert report['simulation_passed'] and sha(parent/'report.json')==joint['report_sha256']
    target=root/'build/experiments'/args.name;target.mkdir(parents=True,exist_ok=False)
    for n,h in report['inputs_sha256'].items():
        p=parent/n;assert sha(p)==h,n
        destination=target/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination)
    cap_source=root/'build/experiments/receive-capacity-v4'
    success_source=root/'build/experiments/rpc-success-predicate-v2'
    cap_gen=read(cap_source/'generation.json');success_gen=read(success_source/'generation.json')
    assert sha(cap_source/'generation.json')==capacity['generation_sha256']
    assert sha(success_source/'generation.json')==success['generation_sha256']
    overlays={n:cap_source/'rtl'/(n+'.v') for n in cap_gen['changed_existing_modules']+['grpc_payload_reclaimer']}
    overlays.update({n:success_source/'rtl'/(n+'.v') for n in ('http2_payload_decoder','axis_pingpong_skid_buffer','rpc_http2_response_partition','rpc_grpc_http2_parser_response')})
    assert len(overlays)==14
    certificates={}
    for n,p in overlays.items():
        expected=capacity['executed_parser_sha256'].get(n) if p.parent.parent==cap_source else success['executed_parser_sha256'][n]
        assert sha(p)==expected,n
        original=p.read_text();ordered,certificate=order_declarations(original)
        verify_order(original,ordered,certificate)
        assert ports(original,n)==ports(ordered,n)
        destination=target/'joint/rtl'/(n+'.v');destination.write_bytes(ordered.encode())
        certificates[n]=dict(portable_source=p.relative_to(root).as_posix(),portable_raw_sha256=sha(p),
            native_sha256=sha(destination),declaration_order_certificate=certificate)
    parser=closure('http2_schema_mmio_application',target/'joint')
    tokenizer=closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',target/'joint')
    assert len(parser)==79 and len(tokenizer)==31
    assert {n:sha(p) for n,p in tokenizer.items()}=={n:sha(p) for n,p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',parent/'joint').items()}
    changed={n for n,h in report['inputs_sha256'].items() if sha(target/n)!=h}
    expected_changes={'joint/rtl/'+n+'.v' for n in overlays if 'joint/rtl/'+n+'.v' in report['inputs_sha256']}
    assert changed==expected_changes and len(changed)==12
    wrapper='joint/rtl/http2_schema_mmio_application.v'
    assert sha(target/wrapper)==report['inputs_sha256'][wrapper]
    for n,h in report['inputs_sha256'].items():
        if not n.startswith('joint/rtl/'):assert sha(target/n)==h,n
    generation=read(parent/'generation.json')
    generation.update(phase='joint_schema_capacity_success_full_corpus_generated',parser_modules=79,tokenizer_modules=31,
        capacity_composed=True,semantic_payload_buffer_integrated=True,success_predicate_integrated=True,
        composition_parent_audit_key=joint['key'],composition_parent_run=joint['run'],composition_parent_report_sha256=sha(parent/'report.json'),
        composition_parent_inputs_sha256=report['inputs_sha256'],capacity_assembly_audit_key=capacity['key'],
        capacity_directed_runtime_audit_key=runtime['key'],success_predicate_audit_key=success['key'],semantic_payload_audit_key=semantic['key'],
        exact_overlay_source_certificates=certificates,unchanged_original_workload_images_vectors_and_assertions=True,
        portable_capacity_generation_sha256=sha(cap_source/'generation.json'),portable_success_generation_sha256=sha(success_source/'generation.json'),
        canonical_parser_sha256={n:sha(p) for n,p in parser.items()},canonical_tokenizer_sha256={n:sha(p) for n,p in tokenizer.items()},
        simulation_verified=False,native_elaboration_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=sha(Path(__file__)))
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    generation['outputs_sha256']={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
    (target/'generation.json').write_text(json.dumps(generation,indent=2)+'\n')
    print(json.dumps({k:generation[k] for k in ('phase','parser_modules','tokenizer_modules','capacity_composed')}))


if __name__=='__main__':main()
