"""Bind the unchanged complete controller workload to registered arbitration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from generate_rpc_refusal_execution_pack import METADATA, source_gate as refusal_gate
from verify_registered_frame_select import require_unit_audit, source_gate as selection_gate


NAME = 'joint-rpc-registered-select-v1'
TIMING_BODY='joint_hyperram_grpc_schema_body.svh'


def timing_certificate(candidate):
    original=(candidate/TIMING_BODY).read_bytes().decode()
    marker='dma_received=0;dma_last_count=0;packet(c+2);complete_forward();return_captured_ids();directory(3,case_stream);'
    begin='$display("JOINT_CASE_WINDOW stage=start epoch=%0d case=%0d cycle=%0d bytes=%0d tokens=%0d reads=%0d writes=%0d hyperbus=%0d",epoch,c,cycle,length,expected_count,parser_reads,parser_writes,transaction_count);'
    forward='$display("JOINT_CASE_WINDOW stage=forward epoch=%0d case=%0d cycle=%0d bytes=%0d tokens=%0d reads=%0d writes=%0d hyperbus=%0d",epoch,c,cycle,length,dma_received,parser_reads,parser_writes,transaction_count);'
    end='$display("JOINT_CASE_WINDOW stage=end epoch=%0d case=%0d cycle=%0d bytes=%0d tokens=%0d reads=%0d writes=%0d hyperbus=%0d",epoch,c,cycle,length,dma_received,parser_reads,parser_writes,transaction_count);'
    updated_marker=begin+'\n            dma_received=0;dma_last_count=0;packet(c+2);complete_forward();\n            '+forward+'\n            return_captured_ids();directory(3,case_stream);'
    finish='$display("JOINT_CORPUS_CASE epoch=%0d case=%0d tokens=%0d total_dma=%0d total_gpu=%0d",epoch,c,dma_received,total_dma,total_gpu);'
    replacements=[(marker,updated_marker),(finish,finish+'\n            '+end)]
    if '\r\n'in original:replacements=[(a.replace('\n','\r\n'),b.replace('\n','\r\n'))for a,b in replacements]
    updated=original
    for a,b in replacements:
        assert updated.count(a)==1;updated=updated.replace(a,b)
    inverse=updated
    for a,b in reversed(replacements):
        assert inverse.count(b)==1;inverse=inverse.replace(b,a)
    assert inverse==original
    return dict(path=TIMING_BODY,before_sha256=sha(candidate/TIMING_BODY),after_sha256=hashlib.sha256(updated.encode()).hexdigest(),
        replacements=[list(pair)for pair in replacements],only_zero_time_display_statements_added=True),updated


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def source_gate(root, payload=False):
    baseline, refusal, provenance = refusal_gate(root)
    candidate, current = selection_gate(root)
    unit = require_unit_audit(root)
    directed = read(root/'build/validation/rpc-registered-frame-select-v1-directed.json')
    faults = read(root/'build/validation/rpc-registered-select-ack-faults.json')
    assert directed['key'] == '381fe48f058bf0b1'
    assert faults['key'] == '41f0a03c9f1e5cd5'
    assert directed['generation_sha256'] == faults['generation_sha256'] == sha(candidate/'generation.json')
    assert directed['four_directed_application_runs_verified']
    assert directed['full_pair_strict_vendor_elaboration_verified']
    assert current['canonical_tokenizer_sha256'] == refusal['canonical_tokenizer_sha256']
    assert sha(candidate/'joint_hyperram_grpc_tb.sv') == provenance['execution_testbench_sha256']
    provenance.update(
        registered_selection_generation_sha256=sha(candidate/'generation.json'),
        registered_selection_unit_audit_key=unit['key'],
        registered_selection_directed_audit_key=directed['key'],
        registered_selection_ack_fault_audit_key=faults['key'],
        executed_parser_sha256=current['canonical_parser_sha256'],
        executed_tokenizer_sha256=current['canonical_tokenizer_sha256'],
        sole_additional_changed_rtl='axis_frame_arbiter',
        no_additional_workload_or_fixture_edits=True,
        full_controller_runtime_verified=False)
    if payload:
        from verify_receive_payload_settling import require_settling_audit,source_gate as payload_gate
        settling=require_settling_audit(root)
        candidate,current,consumer=payload_gate(root)
        directed=read(root/'build/validation/rpc-receive-payload-pipeline-v1-directed.json')
        assert directed['generation_sha256']==settling['generation_sha256']==sha(candidate/'generation.json')
        assert directed['settling_source_audit_key']==settling['key']
        assert directed['four_directed_application_runs_verified'] and directed['full_pair_strict_vendor_elaboration_verified']
        assert directed['exact_parent_directed_acceptance_and_original_fixture_bytes_verified']
        assert sha(candidate/'joint_hyperram_grpc_tb.sv')==provenance['execution_testbench_sha256']
        provenance.pop('sole_additional_changed_rtl')
        provenance.update(receive_payload_generation_sha256=sha(candidate/'generation.json'),
            receive_payload_settling_audit_key=settling['key'],receive_payload_directed_audit_key=directed['key'],
            additional_changed_rtl=['axis_frame_arbiter','http2_receive_credit_store'],
            executed_parser_sha256=current['canonical_parser_sha256'],
            executed_tokenizer_sha256=current['canonical_tokenizer_sha256'])
        observation,unused=timing_certificate(candidate)
        provenance.update(no_additional_workload_or_fixture_edits=False,only_passive_cycle_observation_edits=True,
            passive_cycle_observation_certificate=observation)
    return baseline, current, provenance


def validate_pack(root, source):
    generation = read(source/'generation.json')
    payload=generation.get('payload_pipeline_execution_pack',False)
    baseline, current, gate = source_gate(root,payload)
    assembly = read(source/'source-assembly.json')
    assert generation['refusal_execution_pack'] and generation['registered_selection_execution_pack']
    assert generation['workload_provenance'] == gate
    assert generation['parser_modules'] == 79 and generation['tokenizer_modules'] == 31
    assert generation['unchanged_original_workload_images_vectors_and_assertions']
    assert not generation['native_elaboration_verified']
    assert generation['strict_unchanged_vendor_elaboration_verified']
    for name in METADATA:
        assert generation[name] == baseline[name]
    expected = dict(current['outputs_sha256'])
    if payload:
        original=root/'build/experiments/rpc-receive-payload-pipeline-v1'
        observation,observed=timing_certificate(original)
        assert gate['passive_cycle_observation_certificate']==observation
        expected[TIMING_BODY]=observation['after_sha256']
        assert (source/TIMING_BODY).read_bytes().decode()==observed
    expected[Path(__file__).name] = generation['generator_sha256']
    assert expected == generation['outputs_sha256']
    assert all(sha(source/name) == digest for name, digest in expected.items())
    assert generation['canonical_parser_sha256'] == current['canonical_parser_sha256']
    assert generation['canonical_tokenizer_sha256'] == current['canonical_tokenizer_sha256']
    assert assembly['generation_sha256'] == sha(source/'generation.json')
    assert all(assembly[key] == value for key, value in gate.items())
    content = {key: value for key, value in assembly.items() if key != 'key'}
    assert assembly['key'] == hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    return assembly


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--payload-pipeline',action='store_true');args=ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    baseline, current, gate = source_gate(root,args.payload_pipeline)
    source = root/'build/experiments'/('rpc-receive-payload-pipeline-v1'if args.payload_pipeline else'rpc-registered-frame-select-v1')
    target = root/'build/experiments'/('joint-rpc-receive-payload-v1'if args.payload_pipeline else NAME)
    target.mkdir(parents=True, exist_ok=False)
    for name in current['outputs_sha256']:
        path = target/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source/name, path)
    if args.payload_pipeline:
        observation,observed=timing_certificate(source)
        assert observation==gate['passive_cycle_observation_certificate']
        (target/TIMING_BODY).write_bytes(observed.encode())
    shutil.copy2(Path(__file__), target/Path(__file__).name)
    generation = dict(
        phase='receive_payload_execution_pack_runtime_unverified'if args.payload_pipeline else'registered_selection_execution_pack_runtime_unverified',
        refusal_execution_pack=True, registered_selection_execution_pack=True,
        payload_pipeline_execution_pack=args.payload_pipeline,
        workload_provenance=gate, parser_modules=79, tokenizer_modules=31,
        canonical_parser_sha256=current['canonical_parser_sha256'],
        canonical_tokenizer_sha256=current['canonical_tokenizer_sha256'],
        unchanged_original_workload_images_vectors_and_assertions=True,
        native_elaboration_verified=False, strict_unchanged_vendor_elaboration_verified=True,
        simulation_verified=False, native_timing_verified=False,
        global_schema_maintenance_authority_verified=False, full_system_complete=False,
        generator_sha256=sha(Path(__file__)), **{name: baseline[name] for name in METADATA})
    generation['outputs_sha256'] = {**current['outputs_sha256'], Path(__file__).name: sha(Path(__file__))}
    if args.payload_pipeline:generation['outputs_sha256'][TIMING_BODY]=sha(target/TIMING_BODY)
    (target/'generation.json').write_text(json.dumps(generation, indent=2)+'\n')
    assembly = dict(phase='receive_payload_execution_pack_source_verified'if args.payload_pipeline else'registered_selection_execution_pack_source_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(target/'generation.json'), **gate)
    assembly['key'] = hashlib.sha256(json.dumps(assembly, sort_keys=True).encode()).hexdigest()[:16]
    (target/'source-assembly.json').write_text(json.dumps(assembly, indent=2)+'\n')
    validate_pack(root, target)
    print(json.dumps(dict(phase=assembly['phase'], key=assembly['key'], parser_modules=79, tokenizer_modules=31)))


if __name__ == '__main__':
    main()
