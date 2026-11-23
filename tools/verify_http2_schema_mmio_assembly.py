"""Verify the complete configuration wiring and native elaboration, not runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from h2.config import H2Configuration
from h2.connection import H2Connection

from generate_http2_schema_mmio_application import BUS, MANUAL, render
from generate_joint_hyperram_grpc_vectors import varint
from verify_joint_hyperram_grpc_native import load_frames, load_ids
from verify_two_fpga_application import closure
from generate_frame_event_buffer import buffered
from generate_frame_owned_quiet import quiet
from run_frame_fifo_equivalence_wsl import observe


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    folder=root/'build/validation'/args.name;generation=read(folder/'generation.json');report=read(folder/'report.json')
    owned_quiet=generation.get('owned_quiet',False)
    assert generation['schema_mmio'] and generation['parser_modules']==77
    assert generation['route_word_offsets']==dict(schema_epoch=16,model_epoch=20)
    route=folder/'joint/rtl/http2_route_lookup.v'
    assert sha(route)==generation['route_layout_source_sha256']
    assert 'result_schema_epoch<=record_data[159:128]' in route.read_text()
    assert 'result_model_epoch<=record_data[191:160]' in route.read_text()
    assert report['schema_mmio'] and report['parser_modules']==77
    assert report['phase'] in ('simulating','native_simulation_completed_protocol_oracle_pending','native_joint_workload_failed')
    assert report['inputs_sha256']==generation['outputs_sha256']
    for name,digest in report['inputs_sha256'].items():assert sha(folder/name)==digest,name
    assert sha(folder/'generation.json')==report['generation_sha256']
    assert report['production_compiled_as_verilog'] and report['native_vendor_memory'] and not report['portable_backend']
    assert report['normal_global_startup'] and report['compatibility_defines']==['OBSOLETE']
    assert 'Built simulation snapshot joint_hyperram_grpc' in (folder/'elaboration-stdout.log').read_text()
    production=sorted((folder/'joint/rtl').glob('*.v'))+[folder/'joint/vendor/glbl.v']
    assert (folder/'production.prj').read_text()==''.join('verilog work "'+p.relative_to(folder).as_posix()+'"\n' for p in production)
    compiled=(folder/'production.log').read_text()
    assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',compiled,re.M)
    assert all(p.name in compiled for p in production)
    parent=root/'build/validation/joint_hyperram_grpc_full_v5_20261122'
    audit=read(root/'build/validation/joint-hyperram-grpc-evidence/2e24ad59fccef5f2/audit.json')
    assert sha(parent/'report.json')==generation['parent_report_sha256']==audit['report_sha256']
    assert generation['parent_joint_audit_key']==audit['key']
    assert generation['parent_inputs_sha256']==read(parent/'report.json')['inputs_sha256']
    changed={n for n,h in generation['parent_inputs_sha256'].items() if sha(folder/n)!=h}
    expected_changes={'joint/rtl/two_fpga_hyperram_application.v','joint_hyperram_grpc_tb.sv',
        'reference.json','epoch0.vectors','epoch1.vectors'}
    if owned_quiet:expected_changes|={'joint/rtl/http2_axis_ingress.v','joint/rtl/http2_enveloped_frame_grants.v'}
    assert changed==expected_changes
    for name,digest in generation['unchanged_parent_inputs_sha256'].items():assert sha(folder/name)==digest
    old_top=parent/'joint/rtl/http2_enveloped_parser_application.v'
    text,interface,body=render(old_top.read_text())
    assert text.encode()==(folder/'joint/rtl/http2_schema_mmio_application.v').read_bytes()
    parser={n:sha(p) for n,p in closure('http2_schema_mmio_application',folder/'joint').items()}
    tokenizer={n:sha(p) for n,p in closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',folder/'joint').items()}
    assert len(parser)==77
    # Tokenizer module types in the joint source are namespaced.
    assert len(tokenizer)==31
    old_parser=closure('http2_enveloped_parser_application',parent/'joint')
    for name,path in old_parser.items():
        if name=='http2_enveloped_parser_application':continue
        if owned_quiet and name in ('http2_axis_ingress','http2_enveloped_frame_grants'):
            old=path.read_text()
            if name=='http2_axis_ingress':
                transformed,restored,edits=buffered(old);assert restored==old
            else:transformed,edit=quiet(old);edits=[edit]
            native_path=folder/'joint/rtl'/path.name
            assert native_path.read_bytes()==transformed.encode()
            certificate=generation['native_source_edit_certificates'][path.name]
            assert certificate['parent_raw_sha256']==sha(path)
            assert certificate['parent_normalized_sha256']==certificate['inverse_normalized_sha256']==hashlib.sha256(old.encode()).hexdigest()
            assert certificate['candidate_sha256']==sha(native_path) and certificate['edits']==edits
        else:assert parser[name]==sha(path)
    component=read(root/'build/validation/parser-schema-mmio.json')
    assert component['key']=='43a8b7a78f950e37'
    assert parser['parser_schema_mmio']==component['compiled_rtl_sha256']['parser_schema_mmio']
    # Replay the exact used generator against its proven parents. This checks
    # all joint-top connections, test assertions, schemas, vectors and images;
    # a permissive changed-file allowlist alone would not establish that.
    generator=root/'tools'/('generate_joint_schema_owned_quiet_test.py' if owned_quiet else 'generate_joint_hyperram_schema_test.py')
    assert sha(generator)==generation['generator_sha256']==sha(folder/generator.name)
    replay_name=('http2-schema-owned-quiet-replay-' if owned_quiet else 'http2-schema-mmio-replay-')+generation['generator_sha256'][:16]
    replay=root/'build/experiments'/replay_name
    if not replay.exists():
        result=subprocess.run([sys.executable,str(generator),'--name',replay_name],cwd=root,capture_output=True,text=True)
        assert result.returncode==0,result.stderr[-3000:]
    replay_generation=read(replay/'generation.json')
    assert replay_generation==generation
    for name,digest in generation['outputs_sha256'].items():assert sha(replay/name)==digest
    canonical_proof=None
    if owned_quiet:
        previous=read(root/'build/validation/joint-hyperram-schema-evidence/292670e03a24501d/audit.json')
        assert generation['parent_schema_audit_key']==previous['key']
        assert generation['owner_formal_audit_key']=='c56de709b9b5681a'
        formal=root/'build/wsl-reports/joint_schema_owned_quiet_formal_20261122'
        canonical_proof=read(formal/'report.json')
        assert canonical_proof['passed'] and canonical_proof['phase']=='frame_owned_quiet_conservative_idle_induction_verified'
        assert canonical_proof['generation_sha256']==sha(folder/'generation.json')
        assert canonical_proof['exact_owner_modules']==7 and canonical_proof['complete_production_owner_subtree']
        for n,h in canonical_proof['inputs_sha256'].items():assert sha(formal/n)==h,n
        assert sha(formal/'run_frame_owned_quiet_formal_wsl.py')==canonical_proof['driver_sha256']
        observed=(root/'build/experiments/joint-schema-owned-quiet-v1/joint/rtl/http2_enveloped_frame_grants.v').read_text()
        assert observed==(folder/'joint/rtl/http2_enveloped_frame_grants.v').read_text()
        rhs=generation['owned_quiet_source_edit_certificate']['old'].removeprefix('assign idle=').removesuffix(';')
        observed=observed.replace('endmodule','wire reference_idle='+rhs+';\nendmodule')
        observed=observe(observed,'http2_enveloped_frame_grants',[('','reference_idle'),('','owned_quiet'),('','owned_idle'),('','quiet_inputs')])
        assert observed==(formal/'rtl/http2_enveloped_frame_grants.v').read_text()
        for n,p in closure('http2_enveloped_frame_grants',folder/'joint').items():
            if n!='http2_enveloped_frame_grants':assert sha(formal/'rtl'/p.name)==sha(p)
        original_formal=root/'build/wsl-reports/frame_owned_quiet_formal_v1_20261122'
        assert (formal/'miter.sv').read_bytes()==(original_formal/'miter.sv').read_bytes()
        assert (formal/'proof.ys').read_bytes()==(original_formal/'proof.ys').read_bytes()
        proof_log=(formal/'proof.log').read_text()
        assert 'Induction step proven: SUCCESS!' in proof_log and 'Base case for induction length 1 proven.' in proof_log
        assert sha(formal/'proof.log')==canonical_proof['proof_log_sha256']
        assert sha(formal/'netlist.json')==canonical_proof['netlist_sha256']
    # Fresh native clients rebuild every new request using actual SETTINGS
    # from the passed parent. New-run responses/settings still need their own
    # runtime oracle after simulation finishes.
    for name,digest in audit['actual_outputs_sha256'].items():assert sha(parent/name)==digest
    frames,_=load_frames(parent/'wire.log');dma=load_ids(parent/'dma.log')
    ref=read(folder/'reference.json')
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    corpus=read(root/'build/validation/json-simd-corpus.json')
    reference=original/'build/bidirectional-fixtures/reference_cases.json'
    assert sha(reference)==corpus['inputs_sha256']['build/bidirectional-fixtures/reference_cases.json']
    prompts=read(reference)['cases'];assert len(prompts)==16
    for epoch in range(2):
        schema=ref['schemas'][epoch]
        assert schema==dict(json_key=('message','content')[epoch],protobuf_field=(37,2712)[epoch],transport_schema_epoch=10+epoch)
        client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'))
        client.initiate_connection();client.update_settings({4:1<<20});client.increment_flow_control_window(1<<20)
        initial=client.data_to_send();assert initial.hex()==ref['epochs'][epoch]['initial_request_hex']
        for raw in frames[epoch,-1]:client.receive_data(raw)
        values=iter(map(int,(folder/f'epoch{epoch}.vectors').read_text().split()))
        size=next(values);assert bytes(next(values) for _ in range(size))==initial
        assert next(values)==16
        for index,prompt in enumerate(prompts):
            raw_text=bytes.fromhex(prompt['prompt_utf8_hex']);stream=index*2+1;mode=2 if index&1 else 0
            client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
                (':path','/parser.Tokenize/Proto' if mode==2 else '/parser.Tokenize/Json'),
                ('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json'),('te','trailers')])
            payload=(json.dumps({schema['json_key']:raw_text.decode()},ensure_ascii=False,separators=(',',':')).encode()
                if mode==0 else varint(schema['protobuf_field']<<3|2)+varint(len(raw_text))+raw_text)
            record=b'\0'+len(payload).to_bytes(4,'big')+payload
            for offset in range(0,len(record),16384):client.send_data(stream,record[offset:offset+16384],end_stream=offset+16384>=len(record))
            raw=client.data_to_send();fields=[next(values) for _ in range(6)]
            assert fields==[index,stream,mode,100+int(mode==2),len(raw),len(dma[epoch,index])]
            assert bytes(next(values) for _ in range(fields[4]))==raw
            assert [next(values) for _ in range(fields[5])]==dma[epoch,index]
        assert next(values,None) is None
    result=dict(phase='complete_http2_schema_mmio_native_assembly_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,generation_sha256=sha(folder/'generation.json'),parent_joint_audit_key=audit['key'],
        component_audit_key=component['key'],exact_parser_modules=77,exact_tokenizer_modules=31,
        unchanged_application_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        executed_parser_sha256=parser,executed_tokenizer_sha256=tokenizer,
        generator_replay_exact=True,complete_original_prompt_model_combinations=32,
        native_requests_rebuilt_from_parent_actual_settings=True,full_vocabulary_images_unchanged=True,
        route_word_offsets=generation['route_word_offsets'],route_layout_source_sha256=sha(route),
        native_elaboration_verified=True,production_configuration_wiring_verified=True,
        full_http2_mmio_runtime_verified=False,global_schema_maintenance_authority_verified=False,
        native_timing_verified=False,full_system_complete=False,
        production_project_sha256=sha(folder/'production.prj'),elaboration_log_sha256=sha(folder/'xelab.log'),
        verifier_sha256=sha(Path(__file__)))
    if owned_quiet:
        result.update(phase='complete_http2_schema_owned_quiet_native_assembly_verified',
            canonical_owned_quiet_induction_verified=True,canonical_owner_proof_report_sha256=sha(formal/'report.json'),
            parent_schema_native_audit_key=previous['key'],frame_event_buffer_integrated=True)
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    audit_name='http2-schema-owned-quiet-assembly' if owned_quiet else 'http2-schema-mmio-assembly'
    evidence=root/'build/validation'/(audit_name+'-evidence')/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    shutil.copy2(root/'tools/generate_http2_schema_mmio_application.py',evidence/'generate_http2_schema_mmio_application.py')
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation'/(audit_name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','exact_parser_modules','native_elaboration_verified')}))


if __name__=='__main__':main()
