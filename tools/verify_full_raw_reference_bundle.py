"""Verify the frozen full-model wire/token oracle used by a two-FPGA run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from hyperframe.frame import Frame


def verify(root,archive,executed,report,files,label):
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    snapshot=json.loads((archive/'snapshot.json').read_text());inputs={**report['source_sha256'],**report['fixture_sha256']}
    assert snapshot['phase']=='snapshot_run_archived'and snapshot['runner_exit_code']==0
    assert snapshot['execution_report_sha256']==sha(archive/'report.json')
    assert all(snapshot['source_and_fixture_sha256'][n]==h for n,h in inputs.items())
    oracle=json.loads((archive/'native-reference.json').read_text());fixture=executed/'build/bidirectional-fixtures'
    verifier=executed/'tools/verify_http2_prefill_references.py';runner=executed/'scripts/run_cocotb_snapshot.py'
    assert oracle['phase']=='passed'and(oracle['wire_packets'],oracle['grpc_messages'],oracle['native_token_ids'])==(38,16,2828)
    assert oracle['complete_model_prefix_matches_image']and oracle['model_ordinary_tokens']==100256
    assert oracle['verifier_sha256']==sha(verifier)==sha(root/'tools/verify_http2_prefill_references.py')
    assert snapshot['source_and_fixture_sha256']['build/bidirectional-reference-validation.json']==sha(archive/'native-reference.json')
    assert snapshot['snapshot_runner_sha256']==sha(runner)==snapshot['source_and_fixture_sha256']['scripts/run_cocotb_snapshot.py']
    for name,digest in oracle['fixture_sha256'].items():assert inputs['build/bidirectional-fixtures/'+name]==digest
    for name in('external_memory.bin','external_manifest.json'):
        path=root/'build/scu35/image'/name;field='model_image_sha256'if name.endswith('.bin')else'model_manifest_sha256'
        assert sha(path)==oracle[field];files[Path('native-reference')/label/'model'/name]=path
    # Re-run the independent hyper-h2/JSON/Protobuf/tiktoken decoder against the
    # exact executed fixture bytes. Neither current fixture output nor RTL is its oracle.
    fresh=root/'build/validation'/f'{label}-full-native-reference.json'
    reference_env=os.environ.copy();reference_env['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    subprocess.run([sys.executable,str(root/'tools/verify_http2_prefill_references.py'),
        '--fixtures',str(fixture),'--output',str(fresh)],check=True,capture_output=True,text=True,env=reference_env)
    current=json.loads(fresh.read_text())
    for n in('wire_packets','grpc_messages','native_token_ids','model_image_sha256','model_manifest_sha256',
        'model_prefix_bytes','model_trie_nodes','model_trie_edges','model_ordinary_tokens','packages'):
        assert current[n]==oracle[n],n
    for n,h in oracle['fixture_sha256'].items():assert current['fixture_sha256'][n]==h
    framed=json.loads((fixture/'framed_reference.json').read_text())
    assert framed['phase']=='native_references_passed'and framed['hyperframe_version']=='6.1.0'
    assert framed['generator_sha256']==inputs['tools/generate_two_fpga_framed_vectors.py']
    assert framed['input_sha256']==inputs['build/bidirectional-fixtures/response_reference.json']
    frames=0
    for key,entry in framed['frames'].items():
        stream,body_hex,_=key.split(':');record=bytearray();assert len(entry['grants'])==len(entry['wire'])
        for grant,raw_hex in zip(entry['grants'],entry['wire']):
            raw=bytes.fromhex(raw_hex);frame,length=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
            assert frame.type==0 and frame.stream_id==int(stream)and not frame.flags
            assert length==grant==len(frame.data)and 1<=grant<=16384 and frame.serialize()==raw
            record.extend(frame.data);frames+=1
        body=bytes.fromhex(body_hex);assert record==b'\0'+len(body).to_bytes(4,'big')+body
    for name,path in(('original-native-reference.json',archive/'native-reference.json'),('rechecked-native-reference.json',fresh),
        ('verify_http2_prefill_references.py',verifier),('run_cocotb_snapshot.py',runner),('verify_full_raw_reference_bundle.py',Path(__file__))):
        files[Path('native-reference')/label/name]=path
    return dict(frozen_reference_bundle_verified=True,independent_wire_json_protobuf_tiktoken_recheck=True,
        complete_model_prefix_verified=True,model_ordinary_tokens=100256,model_image_sha256=oracle['model_image_sha256'],
        native_response_patterns=len(framed['frames']),native_response_frames_redecoded=frames,
        response_headers_and_trailers_verified=False)
