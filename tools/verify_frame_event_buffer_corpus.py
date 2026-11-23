"""Verify the complete original native-client workload on the buffered Parser."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from verify_native_grpc_corpus_reference import verify_reference
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('frame-event-buffer','frame-owned-quiet','payload-event-buffer','open-rpc-reclaim','rpc-completion-flags','receive-capacity-v2','receive-capacity-v4','rpc-success-predicate-v2'),default='frame-event-buffer')
    ap.add_argument('--capacity-owner-witness',action='store_true');args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    capacity=args.candidate in ('receive-capacity-v2','receive-capacity-v4')
    if args.capacity_owner_witness:assert capacity
    success=args.candidate=='rpc-success-predicate-v2'
    flags=args.candidate=='rpc-completion-flags' or success;payload=args.candidate=='payload-event-buffer' or flags;reclaim=args.candidate=='open-rpc-reclaim' or capacity
    quiet=args.candidate=='frame-owned-quiet' or reclaim or payload
    name=args.candidate.replace('-','_')+'_corpus'+('_owner' if args.capacity_owner_witness else '')+'_20261122';archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
    launch=read(root/'build/validation'/(name+'-launch.json'))
    assert launch['phase']=='completed' and launch['exit_code']==0
    inputs=read(archive/'inputs.json');report=read(archive/'report.json');snapshot=read(archive/'snapshot.json');accepted=read(archive/'acceptance.json')
    assert report['phase']==accepted['phase']=='passed' and report['tests']==1 and report['failures']==0
    assert snapshot['exit_code']==0 and snapshot['profile']==report['profile']=='workload'
    assert inputs==launch['inputs_sha256']==report['input_sha256']
    assert sha(archive/'acceptance.json')==report['acceptance_sha256']
    for name,digest in inputs.items():assert sha(source/name)==digest,name
    parent=read(root/'build/validation/json-simd-corpus.json');assert parent['key']=='2509134d2630b47e'
    assert set(inputs)==set(parent['inputs_sha256'])|({'rtl/axis_pingpong_skid_buffer.v'} if payload else {'rtl/grpc_payload_reclaimer.v'} if reclaim else set())
    changed=[n for n in parent['inputs_sha256'] if inputs[n]!=parent['inputs_sha256'][n]]
    expected_changes={'rtl/http2_axis_ingress.v'}|({'rtl/http2_enveloped_frame_grants.v'} if quiet else set())
    ownership_edit=launch.get('fixture_ownership_edit')
    if args.capacity_owner_witness:
        assert ownership_edit and ownership_edit['path']=='sim/cocotb/receive_pool_witness.py'
        assert ownership_edit['exact_inverse_verified'] and len(ownership_edit['replacements'])==8
        assert not launch['protocol_fixture_sources_unchanged'] and launch['original_traffic_vectors_and_assertions_preserved']
        n=ownership_edit['path'];assert inputs[n]==ownership_edit['new_sha256']
        text=(source/n).read_bytes().decode()
        for before,after in reversed(ownership_edit['replacements']):
            assert text.count(after)==1;text=text.replace(after,before)
        assert hashlib.sha256(text.encode()).hexdigest()==ownership_edit['old_sha256']==parent['inputs_sha256'][n]
        expected_changes.add(n)
        pool=accepted['actual_receive_pool_ownership']
        assert pool['private_commands']==pool['private_results'] and pool['private_commands']>=17
        assert pool['private_memory_commands']==pool['private_memory_acks'] and pool['private_memory_commands']>0
        assert pool['receive_grants']==pool['receive_unlocks'] and pool['receive_grants']>0
        assert pool['receive_memory_commands']==pool['receive_memory_acks']
    else:assert ownership_edit is None
    if payload:expected_changes.add('rtl/http2_payload_decoder.v')
    if flags:expected_changes.add('rtl/rpc_http2_response_partition.v')
    if success:expected_changes.add('rtl/rpc_grpc_http2_parser_response.v')
    generation=read(archive/'frame-event-buffer-generation.json')
    if reclaim:expected_changes.update('rtl/'+n+'.v' for n in generation['changed_existing_modules'])
    assert set(changed)==expected_changes
    assert sha(archive/'frame-event-buffer-generation.json')==launch['generation_sha256']
    if capacity:assert generation['parent_assembly_audit_key']=='ad1b6bc9beebcaf5' and generation['capacity_component_audit_key']=='76cbac586a7c94ac'
    elif success:assert generation['parent_corpus_audit_key']=='5e0925fc997e1e08'
    elif flags:assert generation['parent_corpus_audit_key']=='f50480b11ead03b3'
    elif payload or reclaim:assert generation['parent_corpus_audit_key']=='b89b9aea0dd403cb'
    elif quiet:assert generation['parent_unit_audit_key']=='0629d7b95661f8df'
    else:assert generation['parent_corpus_audit_key']==parent['key']
    parser={n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}
    tokenizer={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
    assert len(parser)==(77 if payload or reclaim else 76) and len(tokenizer)==22 and tokenizer==parent['executed_tokenizer_sha256']
    assert parser=={Path(n).stem:h for n,h in generation['outputs_sha256'].items()}
    xml=ET.parse(archive/'results.xml');cases=xml.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='complete_prompt_corpus_uses_native_grpc_and_actual_dma'
    assert not xml.findall('.//failure') and not xml.findall('.//error')
    reference=verify_reference(root,source,accepted,parser_memory_clients=19,native_wire_frames=2879)
    units=read(root/'build/validation'/('receive-capacity-v4-assembly.json' if args.candidate=='receive-capacity-v4' else 'receive-capacity-assembly.json' if capacity else 'rpc-success-predicate.json' if success else 'rpc-completion-flags.json' if flags else 'open-rpc-reclaim-assembly.json' if reclaim else 'payload-event-buffer-units.json' if payload else 'frame-owned-quiet-formal.json' if quiet else 'frame-event-buffer-units.json'))
    assert units['source_edit_inverse_verified' if reclaim else 'source_edit_replay_verified'] and units['executed_parser_sha256' if quiet else 'candidate_parser_sha256']==parser
    if capacity:
        assert units['key']==('69a29b3c155b339f' if args.candidate=='receive-capacity-v4' else 'c4cf022229153691') and units['capacity_format_translation_tied_to_actual_initialization']
        assert units['generation_sha256']==launch['generation_sha256']
    elif reclaim:assert units['key']=='ad1b6bc9beebcaf5'
    if success:
        assert units['key']=='a4f36fdbbab5143f' and units['predicate_equivalence_verified']
        buffered_parent=read(root/'build/validation/rpc-completion-flags-corpus.json')
        assert buffered_parent['key']=='5e0925fc997e1e08'
        assert inputs.keys()==buffered_parent['inputs_sha256'].keys()
        assert {n for n in inputs if inputs[n]!=buffered_parent['inputs_sha256'][n]}=={'rtl/rpc_http2_response_partition.v','rtl/rpc_grpc_http2_parser_response.v'}
    elif flags:
        assert units['full_production_response_subtree_induction_verified'] and units['actual_initial_reset_base_verified']
        buffered_parent=read(root/'build/validation/payload-event-buffer-corpus.json')
        assert buffered_parent['key']=='f50480b11ead03b3'
        assert inputs.keys()==buffered_parent['inputs_sha256'].keys()
        assert {n for n in inputs if inputs[n]!=buffered_parent['inputs_sha256'][n]}=={'rtl/rpc_http2_response_partition.v'}
    elif payload or reclaim:
        buffered_parent=read(root/'build/validation/frame-owned-quiet-corpus.json')
        assert buffered_parent['key']=='b89b9aea0dd403cb'
        parent_changes=({'rtl/'+n+'.v' for n in generation['changed_existing_modules']} if reclaim else {'rtl/http2_payload_decoder.v'})
        if args.capacity_owner_witness:parent_changes.add(ownership_edit['path'])
        assert {n for n in buffered_parent['inputs_sha256'] if inputs[n]!=buffered_parent['inputs_sha256'][n]}==parent_changes
        assert set(inputs)-set(buffered_parent['inputs_sha256'])==({'rtl/grpc_payload_reclaimer.v'} if reclaim else {'rtl/axis_pingpong_skid_buffer.v'})
    elif quiet:
        buffered_parent=read(root/'build/validation/frame-event-buffer-corpus.json')
        assert buffered_parent['key']=='8dc09b4c450eaa4f'
        assert {n for n in inputs if inputs[n]!=buffered_parent['inputs_sha256'][n]}=={'rtl/http2_enveloped_frame_grants.v'}
    assert sha(archive/'protocol-runner-used.py')==launch['driver_sha256']
    result=dict(phase=args.candidate.replace('-','_')+'_complete_native_corpus_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        snapshot=snapshot['name'],parent_corpus_audit_key=buffered_parent['key'] if quiet else parent['key'],unit_audit_key=units['key'],
        exact_parser_modules=77 if payload or reclaim else 76,exact_tokenizer_modules=22,acceptance=accepted,independent_native_reference=reference,
        executed_parser_sha256=parser,executed_tokenizer_sha256=tokenizer,inputs_sha256=inputs,
        actual_execution_sources_verified=True,full_native_corpus_verified=True,protocol_fixture_sources_unchanged=not args.capacity_owner_witness,
        original_traffic_vectors_and_assertions_preserved=True,passive_private_owner_checks_extended=args.capacity_owner_witness,
        complete_model_and_native_packages_preserved=True,only_changed_module=None if reclaim or success else 'rpc_http2_response_partition' if flags else 'http2_payload_decoder' if payload else 'http2_enveloped_frame_grants' if quiet else 'http2_axis_ingress',
        changed_modules_from_qualified_parent=generation['changed_existing_modules'] if reclaim or success else ['rpc_http2_response_partition' if flags else 'http2_payload_decoder' if payload else 'http2_enveloped_frame_grants' if quiet else 'http2_axis_ingress'],
        added_module=None if flags else 'grpc_payload_reclaimer' if reclaim else 'axis_pingpong_skid_buffer' if payload else None,
        portable_memory_backend=True,latest_31_module_tokenizer_controller_integrated=False,
        native_timing_verified=False,full_protocol_matrix_verified=False,physical_interfaces_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p) for p in archive.iterdir() if p.is_file()},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    audit_name=args.candidate+'-corpus'
    target=root/'build/validation'/(audit_name+'-evidence')/result['key'];target.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    shutil.copy2(root/'tools/verify_native_grpc_corpus_reference.py',target/'verify_native_grpc_corpus_reference.py')
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation'/(audit_name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','exact_parser_modules','full_native_corpus_verified')}))


if __name__=='__main__':main()
