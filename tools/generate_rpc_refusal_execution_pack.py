"""Carry unchanged full-workload metadata to the exact V7 RTL; no runtime claim."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil

from verify_two_fpga_application import closure


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())


METADATA=('route_word_offsets','owned_quiet','schema_mmio','expected_schema_durable_applies',
    'expected_host_route_configuration_commands','complete_images','complete_image_bytes_each',
    'full_corpus_sequences','expected_actual_dma_ids')


def source_gate(root):
    parent=root/'build/experiments/joint-schema-capacity-success-v1'
    candidate=root/'build/experiments/rpc-stream-refusal-v7'
    baseline=read(parent/'generation.json');current=read(candidate/'generation.json')
    native=read(root/'build/validation/joint-capacity-success-native-assembly.json')
    directed=read(root/'build/validation/rpc-stream-refusal-v7-directed.json')
    assert native['key']=='e346244ae567e5d1' and native['generation_sha256']==sha(parent/'generation.json')
    assert directed['key']=='950ce3b65ccb9b0a' and directed['generation_sha256']==sha(candidate/'generation.json')
    assert directed['full_pair_strict_vendor_elaboration_verified'] and directed['exact_source_edits_and_native_declaration_order_verified']
    for folder,g in ((parent,baseline),(candidate,current)):
        assert all(sha(folder/n)==h for n,h in g['outputs_sha256'].items())
    assert baseline['outputs_sha256'].keys()<=current['outputs_sha256'].keys()
    for n,h in baseline['outputs_sha256'].items():
        if not n.startswith('joint/rtl/') and n!='joint_hyperram_grpc_tb.sv':
            assert current['outputs_sha256'][n]==h,n
    original=(parent/'joint_hyperram_grpc_tb.sv').read_bytes().decode()
    updated=(candidate/'joint_hyperram_grpc_tb.sv').read_bytes().decode()
    edits=[('reg  parser_admit_messages=0;','reg  parser_admit_messages=0;\nreg  parser_admit_new_rpcs=1;'),
        ('.parser_admit_messages(parser_admit_messages),','.parser_admit_messages(parser_admit_messages),\n.parser_admit_new_rpcs(parser_admit_new_rpcs),')]
    if '\r\n'in original:edits=[(a.replace('\n','\r\n'),b.replace('\n','\r\n'))for a,b in edits]
    expected=original
    for a,b in edits:assert expected.count(a)==1;expected=expected.replace(a,b)
    assert expected==updated
    parser={n:sha(p)for n,p in closure('http2_schema_mmio_application',candidate/'joint').items()}
    tokenizer={n:sha(p)for n,p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',candidate/'joint').items()}
    assert len(parser)==79 and len(tokenizer)==31
    assert parser==current['canonical_parser_sha256'] and tokenizer==current['canonical_tokenizer_sha256']==baseline['canonical_tokenizer_sha256']
    return baseline,current,dict(parent_generation_sha256=sha(parent/'generation.json'),
        refusal_generation_sha256=sha(candidate/'generation.json'),directed_refusal_audit_key=directed['key'],
        capacity_assembly_audit_key=native['capacity_assembly_audit_key'],
        executed_parser_sha256=parser,executed_tokenizer_sha256=tokenizer,
        strict_unchanged_vendor_elaboration_verified=True,
        original_workload_images_vectors_and_assertions_preserved=True,
        original_testbench_edit_replacements=[list(pair)for pair in edits],
        original_testbench_sha256=sha(parent/'joint_hyperram_grpc_tb.sv'),
        execution_testbench_sha256=sha(candidate/'joint_hyperram_grpc_tb.sv'))


def validate_pack(root,source):
    baseline,current,gate=source_gate(root);generation=read(source/'generation.json');assembly=read(source/'source-assembly.json')
    assert generation['refusal_execution_pack'] and generation['workload_provenance']==gate
    assert generation['parser_modules']==79 and generation['tokenizer_modules']==31
    assert generation['unchanged_original_workload_images_vectors_and_assertions']
    assert generation['native_elaboration_verified'] is False
    assert generation['strict_unchanged_vendor_elaboration_verified']
    for n in METADATA:assert generation[n]==baseline[n]
    expected=dict(current['outputs_sha256']);expected['generate_rpc_refusal_execution_pack.py']=generation['generator_sha256']
    assert expected==generation['outputs_sha256']
    assert all(sha(source/n)==h for n,h in expected.items())
    assert assembly['generation_sha256']==sha(source/'generation.json')
    assert all(assembly[k]==v for k,v in gate.items())
    assert assembly['key']==hashlib.sha256(json.dumps({k:v for k,v in assembly.items()if k!='key'},sort_keys=True).encode()).hexdigest()[:16]
    return assembly


def main():
    root=Path(__file__).resolve().parents[1];baseline,current,gate=source_gate(root)
    source=root/'build/experiments/rpc-stream-refusal-v7';target=root/'build/experiments/joint-rpc-refusal-v7-v2'
    target.mkdir(parents=True,exist_ok=False)
    for n,h in current['outputs_sha256'].items():
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,p)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    generation=dict(phase='exact_refusal_source_execution_pack_runtime_unverified',refusal_execution_pack=True,
        workload_provenance=gate,parser_modules=79,tokenizer_modules=31,
        canonical_parser_sha256=current['canonical_parser_sha256'],canonical_tokenizer_sha256=current['canonical_tokenizer_sha256'],
        unchanged_original_workload_images_vectors_and_assertions=True,
        native_elaboration_verified=False,strict_unchanged_vendor_elaboration_verified=True,
        simulation_verified=False,native_timing_verified=False,global_schema_maintenance_authority_verified=False,
        full_system_complete=False,generator_sha256=sha(Path(__file__)),**{n:baseline[n]for n in METADATA})
    generation['outputs_sha256']={**current['outputs_sha256'],Path(__file__).name:sha(Path(__file__))}
    (target/'generation.json').write_text(json.dumps(generation,indent=2)+'\n')
    assembly=dict(phase='exact_refusal_execution_pack_source_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(target/'generation.json'),**gate)
    assembly['key']=hashlib.sha256(json.dumps(assembly,sort_keys=True).encode()).hexdigest()[:16]
    (target/'source-assembly.json').write_text(json.dumps(assembly,indent=2)+'\n')
    validate_pack(root,target)
    print(json.dumps(dict(phase=assembly['phase'],key=assembly['key'],parser_modules=79,tokenizer_modules=31)))


if __name__=='__main__':main()
