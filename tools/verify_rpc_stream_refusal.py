"""Independent source/wire/accounting audit of the four directed refusal runs."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from hpack import Decoder
from hyperframe.frame import Frame
import tiktoken

from generate_dual_fpga_hyperram_integration import order_declarations
from generate_hyperram_cdc_timing_harness import ports
from run_joint_capacity_verilator_wsl import check_dead_ecc_json
from verify_dual_fpga_hyperram_integration import verify_order
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('rpc-stream-refusal-v6','rpc-stream-refusal-v7','rpc-registered-frame-select-v1','rpc-receive-payload-pipeline-v1'),default='rpc-stream-refusal-v6');args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    candidate=root/'build/experiments'/args.candidate;generation=read(candidate/'generation.json')
    registered=args.candidate=='rpc-registered-frame-select-v1'
    payload=args.candidate=='rpc-receive-payload-pipeline-v1'
    source_candidate=candidate;source_generation=generation
    if registered or payload:
        from verify_registered_frame_select import require_unit_audit
        selection_audit=require_unit_audit(root)
        source_candidate=root/'build/experiments/rpc-stream-refusal-v7'
        source_generation=read(source_candidate/'generation.json')
    if payload:
        from verify_receive_payload_settling import require_settling_audit
        settling_audit=require_settling_audit(root)
    version=args.candidate.rsplit('-',1)[1]
    parent=root/'build/experiments/rpc-admission-fence-v1';old=read(parent/'generation.json')
    assert source_generation['parent_generation_sha256']==sha(parent/'generation.json')
    assert source_generation['counterexample_audit_key']=='d246ef849f723296'
    expected={'http2_classified_parser_transport','http2_keyed_receive_credit_store',
        'http2_receive_flow_controller','http2_enveloped_parser_core'}
    assert set(source_generation['source_edit_certificates'])=={'joint/rtl/'+n+'.v' for n in expected}
    for name,certificate in source_generation['source_edit_certificates'].items():
        original=(parent/name).read_bytes().decode();edited=original
        assert sha(parent/name)==certificate['before_sha256']
        for before,after in certificate['replacements']:
            if Path(name).stem=='http2_enveloped_parser_core' and before==');\n':
                edited=edited.replace(before,after,1)
            else:
                assert edited.count(before)==1,(name,before)
                edited=edited.replace(before,after)
        assert hashlib.sha256(edited.encode()).hexdigest()==certificate['edited_preorder_sha256']
        inverse=edited
        for before,after in reversed(certificate['replacements']):
            assert inverse.count(after)==1
            inverse=inverse.replace(after,before)
        assert inverse==original
        ordered,order=order_declarations(edited)
        verify_order(edited,ordered,certificate['declaration_order_certificate'])
        assert order==certificate['declaration_order_certificate']
        assert ordered.encode()==(source_candidate/name).read_bytes()
        assert sha(source_candidate/name)==certificate['after_sha256']
        module=Path(name).stem;old_ports=ports(original,module);new_ports=ports(ordered,module)
        assert [p for p in new_ports if p[2] in {q[2] for q in old_ports}]==old_ports
        if module=='http2_enveloped_parser_core':assert new_ports==old_ports
    assert {n for n,h in old['outputs_sha256'].items() if sha(source_candidate/n)!=h}==set(source_generation['source_edit_certificates'])
    for n,h in generation['outputs_sha256'].items():assert sha(candidate/n)==h,n
    assert generation['canonical_tokenizer_sha256']==old['canonical_tokenizer_sha256']
    assert len(generation['canonical_parser_sha256'])==79 and len(generation['non_mmio_parser_sha256'])==78
    core=(candidate/'joint/rtl/http2_enveloped_parser_core.v').read_text()
    assert core.count('(receive_controller_idle||rx_packet_gap_quiescent)')==1
    assert core.count('rx_packet_gap_quiescent')==3
    assert 'assign cfg_quiescent=f_cfg_quiescent&&allow_config&&receive_controller_idle&&refusal_wire_idle;' in core
    assert '&&receive_controller_idle&&receive_wire_idle&&' in core
    flow=(candidate/'joint/rtl/http2_receive_flow_controller.v').read_text()
    assert 'assign packet_gap_quiescent=state==IDLE&&!init_valid&&!s_valid&&!replay_valid&&(frame_active||discard_active);' in flow
    assert '&&!frame_active&&!discard_active;' in flow
    elaboration=root/'build/wsl-reports'/('rpc_receive_payload_pipeline_v1_elaboration'if payload else'rpc_registered_frame_select_v1_elaboration'if registered else'rpc_stream_refusal_'+version+'_elaboration');er=read(elaboration/'report.json')
    assert er['phase']=='elaborated_independent_audit_pending' and er['exit_code']==0
    assert er['generation_sha256']==sha(candidate/'generation.json') and er['inputs_sha256']==generation['outputs_sha256']
    for n,h in er['inputs_sha256'].items():assert sha(elaboration/'execution-sources'/n)==h
    for n,h in er['artifacts_sha256'].items():assert sha(elaboration/n)==h
    assert '--assert' in er['command'] and '--json-only' in er['command'] and '--flatten' in er['command']
    assert not any(s in ' '.join(er['command']) for s in ('--bbox','DONESPIN','DISABLE_ASSERT'))
    assert er['simulator_binary_sha256']=='16ef0287751c10ec74f56643c45552652cc325d4b758fe8fd42c2cbe5bd471b3'
    assert check_dead_ecc_json(elaboration,source_folder=elaboration/'execution-sources')==er['vendor_elaboration_checks']
    prefix='rpc_receive_payload_v1'if payload else'rpc_registered_select_v1'if registered else'rpc_stream_refusal_'+version
    cases={case:prefix+'_'+suffix+'_20261122' for case,suffix in (
        ('preservation','live'),('coalesced','coalesced'),('fragmented','fragmented'),('live-fragmented','live_fragmented'))}
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    encoding=tiktoken.get_encoding('cl100k_base');assert encoding.encode('hello world')==[15339,1917]
    expected_response=b''.join(b'\0'+(3+len(text)).to_bytes(4,'big')+b'\x8a\x01'+bytes([len(text)])+text
        for text in [encoding.decode_single_token_bytes(t) for t in (15339,1917)])
    results={};combined_inputs={};model_sha=None;expanded_requests=None
    negative=root/'build/wsl-reports/raw_envelope_rpc_admission_fence_live_v4_observed_20261122'
    for case,run in cases.items():
        archive=root/'build/wsl-reports'/('raw_envelope_'+run);source=archive/'execution-sources'
        launch=read(archive/'launch.json');report=read(archive/'report.json');inputs=read(archive/'inputs.json');accepted=read(archive/'acceptance.json')
        assert launch['phase']=='completed' and launch['exit_code']==0
        if registered or payload:assert launch['registered_selection_unit_audit_key']==selection_audit['key']
        if payload:assert launch['settling_source_audit_key']==settling_audit['key']
        if payload:
            parent_run=run.replace('rpc_receive_payload_v1_','rpc_registered_select_v1_',1)
            parent_archive=root/'build/wsl-reports'/('raw_envelope_'+parent_run)
            assert accepted==read(parent_archive/'acceptance.json'),(case,'Observable acceptance changed despite zero-latency arithmetic retiming')
            parent_inputs=read(parent_archive/'inputs.json')
            for name,digest in parent_inputs.items():
                if not name.startswith('rtl/'):
                    assert inputs[name]==digest,(case,name,'Original directed fixture changed')
        assert report['phase']==accepted['phase']=='passed' and report['tests']==1 and report['failures']==0
        assert report['input_sha256']==inputs==launch['inputs_sha256']
        assert sha(archive/'acceptance.json')==report['acceptance_sha256']
        assert sha(archive/'run_rpc_admission_fence_wsl.py')==launch['driver_sha256']
        assert sha(archive/'fence-generation.json')==sha(candidate/'generation.json')
        for n,h in inputs.items():assert sha(source/n)==h,(case,n)
        parser={n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}
        tokenizer={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}
        assert parser==generation['non_mmio_parser_sha256']==launch['parser_sha256']
        assert len(tokenizer)==22 and tokenizer==launch['tokenizer_sha256']
        parent_fixture=root/'build/wsl-reports/raw_envelope_receive_capacity_v4_native_owner_admission_20261122'
        assert launch['parent_inputs_sha256']==read(parent_fixture/'inputs.json')
        assert tokenizer=={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',parent_fixture/'execution-sources').items()}
        for name,edit in launch['fixture_edits'].items():
            inverse=(source/name).read_bytes().decode()
            assert sha(source/name)==edit['after_sha256']
            for before,after in reversed(edit['replacements']):
                assert inverse.count(after)==1
                inverse=inverse.replace(after,before)
            assert hashlib.sha256(inverse.encode()).hexdigest()==edit['before_sha256']
            if name in launch['parent_inputs_sha256']:assert edit['before_sha256']==launch['parent_inputs_sha256'][name]
        model=inputs['build/bidirectional-fixtures/memory.mem']
        if model_sha is None:model_sha=model
        assert model==model_sha==launch['parent_inputs_sha256']['build/bidirectional-fixtures/memory.mem']
        xml=ET.parse(archive/'results.xml');tests=xml.findall('.//testcase')
        assert len(tests)==1 and not xml.findall('.//failure') and not xml.findall('.//error')
        assert tests[0].attrib['name']==('new_rpc_fence_preserves_old_calls_and_sampled_begin' if case=='preservation'
            else 'coalesced_refusals_discard_real_data_and_preserve_hpack')
        packets=read(archive/'ingress_packets.json');wire=read(archive/'wire_frames.json')
        assert all(p['expected_commit']==1 and p['user']==0 for p in packets)
        server=H2Connection(H2Configuration(client_side=False,header_encoding='utf8'));server.initiate_connection()
        requests={};bodies={};consumed={}
        for packet in packets:
            for event in server.receive_data(bytes.fromhex(packet['raw_hex'])):
                kind=type(event).__name__
                if kind=='RequestReceived':requests[event.stream_id]=dict(event.headers)
                if kind=='DataReceived':
                    bodies[event.stream_id]=bodies.get(event.stream_id,b'')+event.data
                    consumed[event.stream_id]=consumed.get(event.stream_id,0)+event.flow_controlled_length
        expected_streams=[1,3,5] if case=='preservation' else [1,3,5,7]
        assert sorted(requests)==expected_streams
        assert all(v[':path']=='/parser.Tokenize/Proto' and v[':method']=='POST' and v['content-type']=='application/grpc+proto' for v in requests.values())
        good=(1,5) if case=='preservation' else (1,7);refused=[3] if case=='preservation' else [3,5]
        assert all(bodies[s]==b'\0\0\0\0\r\x0a\x0bhello world' for s in good)
        if case!='preservation':
            assert bodies[3]==b'X'*4097+b'Y'*17 and bodies[5]==b'Z'*1025
            assert consumed[3]+consumed[5]==accepted['already_queued_discarded_data_bytes']==5403
            assert all(requests[s]['x-refusal-shared']=='dynamic-entry-from-refused-request' for s in (3,5,7))
            joined=b''.join(bytes.fromhex(p['raw_hex']) for p in packets)
            if expanded_requests is None:expanded_requests=joined
            assert joined==expanded_requests
        decoder=Decoder();resets=[];received={};headers={};connection_updates=0;stream_updates={}
        for item in wire:
            raw=bytes.fromhex(item);frame,size=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
            assert frame.serialize()==raw
            assert frame.type!=7
            if frame.type==3:resets.append((frame.stream_id,frame.error_code))
            if frame.type==1:
                assert frame.stream_id in good and 'END_HEADERS' in frame.flags
                headers.setdefault(frame.stream_id,[]).append(decoder.decode(frame.data))
            if frame.type==0:
                assert frame.stream_id in good
                received[frame.stream_id]=received.get(frame.stream_id,b'')+frame.data
            if frame.type==8:
                if frame.stream_id==0:connection_updates+=frame.window_increment
                else:stream_updates[frame.stream_id]=stream_updates.get(frame.stream_id,0)+frame.window_increment
        assert resets==[(s,7) for s in refused]
        assert all(received[s]==expected_response for s in good)
        assert all(headers[s]==[[(':status','200'),('content-type','application/grpc+proto')],[('grpc-status','0')]] for s in good)
        assert accepted['actual_captured_dma_ids_returned']=={str(s):[15339,1917] for s in good}
        assert accepted['actual_generated_descriptors']==[[s,t,i,int(i==1)] for s in good for i,t in enumerate((15339,1917))]
        layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
        capacity=layout[14]//128*(layout[18]+5)
        assert connection_updates==capacity-65535+sum(consumed.values())
        assert not any(s in refused for s in stream_updates)
        assert layout[18]+5-65535<=stream_updates[1]<=layout[18]+5-65535+18
        if case=='preservation':
            observation=read(archive/'fence_refusal_observation.json')
            assert observation['before_record_hex']==observation['after_record_hex']
            assert bytes.fromhex(observation['before_record_hex'])[:4]==(0x47525331).to_bytes(4,'little')
            edit=launch['fixture_edits']['sim/cocotb/test_rpc_admission_fence.py']
            assert edit['before_sha256']==read(negative/'inputs.json')['sim/cocotb/test_rpc_admission_fence.py']
            assert edit['replacements']==[['await b.packet(0, 4, headers(3, b.client), 0)','await b.packet(0, 4, headers(3, b.client), 1)']]
            assert accepted['sampled_begin'][0]['stream']==5 and accepted['sampled_begin'][0]['sampled_admit_new']==1
        else:
            assert accepted['held_reset_cycles']==37 and accepted['final_connection_credit']==capacity
            if case in ('fragmented','live-fragmented'):
                checkpoint=read(archive/'fragment_checkpoint.json')
                assert checkpoint['discard_valid']==(1 if case=='fragmented' else 0)
                if case=='fragmented':assert checkpoint['receive_controller_idle']==0
                else:
                    # Normal DATA's control records remain journaled until
                    # frame completion; its replay state need not be live yet.
                    assert checkpoint['receive_controller_idle']==1 and checkpoint['live_receive_frame']==0
                    assert bytes.fromhex(packets[4]['raw_hex'])==b'lo world'
                    assert bytes.fromhex(packets[3]['raw_hex'])[-12:]==b'\0\0\x0b\0\0\0\0\0\x01hel'
                assert [p['tag'] for p in packets]==[1,2,3,4,40,5,6]
        assert accepted['complete_model_prefixes_immutable'] and not accepted['native_vendor_runtime_verified']
        results[case]=dict(run=run,parser_modules=78,tokenizer_modules=22,native_complete_grpc_calls=2,
            actual_dma_ids_returned=4,rst_streams=resets,connection_updates=connection_updates,
            native_incoming_flow_controlled_bytes=sum(consumed.values()),final_backed_connection_credit=capacity,
            acceptance_sha256=sha(archive/'acceptance.json'),inputs_sha256=sha(archive/'inputs.json'),
            wire_sha256=sha(archive/'wire_frames.json'),ingress_sha256=sha(archive/'ingress_packets.json'))
        combined_inputs[case]=inputs
    result=dict(phase='rpc_stream_refusal_four_directed_application_runs_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        candidate=args.candidate,parent_counterexample='d246ef849f723296',executions=results,
        four_directed_application_runs_verified=True,full_pair_strict_vendor_elaboration_verified=True,
        exact_source_edits_and_native_declaration_order_verified=True,original_old_rpc_preservation_assertion_retained=True,
        shared_hpack_and_discarded_data_connection_credit_verified=True,private_packet_gap_never_used_as_global_idle=True,
        native_vendor_runtime_verified=False,full_protocol_fault_matrix_verified=False,whole_rpc_gpu_maintenance_authority_verified=False,
        native_timing_verified=False,full_system_complete=False,generation_sha256=sha(candidate/'generation.json'),
        executed_parser_sha256=generation['non_mmio_parser_sha256'],verifier_sha256=sha(Path(__file__)),
        checker_sha256=sha(root/'tools/run_joint_capacity_verilator_wsl.py'))
    if registered or payload:result.update(registered_selection_unit_audit_key=selection_audit['key'],
        phase='registered_selection_four_directed_application_runs_verified')
    if payload:result.update(settling_source_audit_key=settling_audit['key'],
        exact_parent_directed_acceptance_and_original_fixture_bytes_verified=True,
        phase='receive_payload_pipeline_four_directed_application_runs_verified')
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-stream-refusal-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    shutil.copy2(root/'tools/run_joint_capacity_verilator_wsl.py',evidence/'run_joint_capacity_verilator_wsl.py')
    shutil.copy2(candidate/'generation.json',evidence/'generation.json')
    (evidence/'inputs.json').write_text(json.dumps(combined_inputs,indent=2)+'\n')
    text=json.dumps(result,indent=2)+'\n';(evidence/'audit.json').write_text(text)
    name='rpc-stream-refusal'if version=='v6'else args.candidate+'-directed'
    (root/'build/validation'/(name+'.json')).write_text(text)
    print(json.dumps({k:result[k] for k in ('phase','key','four_directed_application_runs_verified')}))


if __name__=='__main__':main()
