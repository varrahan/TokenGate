"""Bind original lifecycle/fault replays to exact capacity-mode extensions."""
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import xml.etree.ElementTree as ET

from hyperframe.frame import Frame
from verify_frame_event_buffer_protocol import differences,timing_path
from verify_two_fpga_application import closure


CASES=('native','other_connection','owned_gpu_drain','retained_native','all_ledger_faults','retained_shutdown','external_denial')


def helper_functions(path):
    module=ast.parse(path.read_text());names=('capacity_pool_witness_edits','capacity_admission_barrier_edits','capacity_format_fault_barrier_edits','capacity_retained_snapshot_edits','capacity_shutdown_credit_barrier_edits')
    scope={}
    for name in names:
        node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==name)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    return scope


def frame(raw):
    f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw
    return f


def normalize(accepted,baseline,case,layout,archive):
    actual=json.loads(json.dumps(accepted));extensions={}
    extra={'capacity_admission_barriers'} if case=='native' else {'actual_initial_capacity_wire_before_faults'} if case=='all_ledger_faults' else set()
    assert actual.keys()==baseline.keys()|extra
    stream_capacity=layout[18]+5;connection_capacity=layout[14]//128*stream_capacity
    if case=='native':
        barriers=actual.pop('capacity_admission_barriers');assert len(barriers)==3
        previous=[]
        for b,s in zip(barriers,(5,7,11)):
            assert b['stream']==s and b['stream_credit']==stream_capacity
            raw=[bytes.fromhex(h) for h in b['actual_wire_prefix']]
            assert len(raw)==b['wire_after'] and 0<=b['wire_before']<=b['wire_after']
            assert raw[:len(previous)]==previous
            assert all(frame(w).type==8 for w in raw[b['wire_before']:])
            assert [(f.stream_id,f.window_increment) for f in map(frame,raw) if f.type==8 and f.stream_id==s]==[(s,stream_capacity-65535)]
            previous=raw
        added=[f for f in map(frame,previous) if f.type==8 and ((f.stream_id in (5,7,11) and f.window_increment==stream_capacity-65535) or (f.stream_id==0 and f.window_increment==connection_capacity-65535))]
        assert [(f.stream_id,f.window_increment) for f in added]==[(5,65542),(0,327696),(7,65542),(11,65542)]
        actual['native_wire_frames']-=len(added)
        extensions['actual_initial_capacity_frames']=len(added)
    if case=='all_ledger_faults':
        raw=[bytes.fromhex(h) for h in actual.pop('actual_initial_capacity_wire_before_faults')]
        parsed=list(map(frame,raw));assert [f.type for f in parsed]==[4,4,6,8,8]
        reference=json.loads((archive/'execution-sources/build/bidirectional-fixtures/journaled_control_reference.json').read_text())
        request=bytes.fromhex(reference['initial_packet'])[24:];pings=[]
        while request:
            f,size=Frame.parse_frame_header(memoryview(request[:9]));f.parse_body(memoryview(request[9:9+size]))
            if f.type==6:pings.append(f.opaque_data)
            request=request[9+size:]
        assert pings==[parsed[2].opaque_data] and 'ACK' in parsed[2].flags
        assert [(f.stream_id,f.window_increment) for f in parsed if f.type==8]==[(1,stream_capacity-65535),(0,connection_capacity-65535)]
        extensions['initial_private_capacity_retired_before_original_fault_arming']=True
    if case=='retained_native':
        assert len(actual['epochs'])==len(baseline['epochs'])==2
        for epoch,old in zip(actual['epochs'],baseline['epochs']):
            index=epoch['epoch'];bank=bytearray((archive/f'retained_parser_mutable_epoch{index}.bin').read_bytes())
            tokenizer=(archive/f'retained_tokenizer_mutable_epoch{index}.bin').read_bytes()
            assert len(bank)==len(tokenizer)==8388608-layout[6]
            assert hashlib.sha256(bank).hexdigest()==epoch['retained_parser_mutable_sha256']
            assert hashlib.sha256(tokenizer).hexdigest()==epoch['retained_tokenizer_mutable_sha256']==old['retained_tokenizer_mutable_sha256']
            # Reverse only the exact new capacity fields in the connection and
            # two admitted stream ledgers. A baseline digest match then proves
            # every other byte of the retained mutable bank is unchanged.
            offset=0x7e5000-layout[6]
            assert struct.unpack_from('<I',bank,offset+12)[0]==stream_capacity
            assert struct.unpack_from('<I',bank,offset+16)[0]==connection_capacity-65535
            assert struct.unpack_from('<2I',bank,offset+56)==(layout[17],layout[14]//128*layout[18])
            struct.pack_into('<I',bank,offset+12,65535);struct.pack_into('<I',bank,offset+16,0);struct.pack_into('<Q',bank,offset+56,0)
            for slot,sid in enumerate((1,3)):
                offset=0x7e6000-layout[6]+slot*32
                assert struct.unpack_from('<I',bank,offset+12)[0]==sid
                assert struct.unpack_from('<I',bank,offset+16)[0]==stream_capacity-65535
                assert struct.unpack_from('<I',bank,offset+24)[0]==stream_capacity
                struct.pack_into('<I',bank,offset+16,0);struct.pack_into('<I',bank,offset+24,65535)
            assert hashlib.sha256(bank).hexdigest()==old['retained_parser_mutable_sha256']
            epoch['retained_parser_mutable_sha256']=old['retained_parser_mutable_sha256']
        extensions['both_retained_banks_verified_byte_for_byte_against_exact_capacity_encoding_and_baseline']=True
    if case=='retained_shutdown':
        prefixes=json.loads((archive/'capacity_shutdown_admission_wires.json').read_text());assert len(prefixes)==42
        for prefix in prefixes:
            parsed=[frame(bytes.fromhex(h)) for h in prefix]
            assert all(f.type==8 for f in parsed)
            assert [(f.stream_id,f.window_increment) for f in parsed]==[(1,stream_capacity-65535),(0,connection_capacity-65535)]
        extensions['all_41_faults_and_final_success_follow_verified_initial_capacity']=True
    if 'actual_receive_pool_ownership' in actual:
        pool=actual['actual_receive_pool_ownership'];old=baseline['actual_receive_pool_ownership']
        keys={'private_commands','private_results','private_memory_commands','private_memory_acks'}
        assert pool.keys()==old.keys()|keys
        commands=pool['private_commands'];memory=pool['private_memory_commands']
        assert commands==pool['private_results'] and memory==pool['private_memory_acks'] and min(commands,memory)>=0
        for name in ('receive_grants','receive_unlocks'):
            assert pool[name]>=commands;pool[name]-=commands
        for name in ('receive_memory_commands','receive_memory_acks'):
            assert pool[name]>=memory;pool[name]-=memory
        for name in keys:del pool[name]
        extensions.update(actual_private_pool_transactions=commands,actual_private_memory_commands=memory,
            only_measured_private_owner_counts_removed_for_original_path_comparison=True)
    return actual,extensions


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',choices=('receive-capacity-v2','receive-capacity-v4'),default='receive-capacity-v4')
    ap.add_argument('--cases',nargs='+',choices=CASES,default=CASES);args=ap.parse_args()
    assert len(set(args.cases))==len(args.cases)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    label='receive-capacity-v4' if args.candidate=='receive-capacity-v4' else 'receive-capacity'
    assembly_path=root/'build/validation'/(label+'-assembly.json');assembly=read(assembly_path)
    assert assembly['key']==('69a29b3c155b339f' if args.candidate=='receive-capacity-v4' else 'c4cf022229153691')
    driver=root/'tools/run_frame_event_buffer_protocol_wsl.py';helpers=helper_functions(driver)
    baselines={}
    for n,key in [('progress-format-regressions','736eec1fa78adf7d'),('progress-format-experiment','c7aebf98ee6f7e25')]:
        audit=read(root/'build/validation'/(n+'.json'));assert audit['key']==key
        baselines.update(audit['executions'])
    assert set(baselines)==set(CASES)
    executions={};artifacts={Path(__file__),driver,assembly_path}
    for case in args.cases:
        suffix='_owner_admission' if case=='native' else '_owner_budget' if case=='other_connection' else '_owner_fault_barrier' if case=='all_ledger_faults' else '_owner_snapshots' if case=='retained_native' and args.candidate=='receive-capacity-v4' else '_owner_credit' if case=='retained_shutdown' else '_owner'
        name=args.candidate.replace('-','_')+'_'+case+suffix+'_20261122'
        launch_path=root/'build/validation'/(name+'-launch.json');launch=read(launch_path)
        assert launch['phase']=='completed' and launch['exit_code']==0 and launch['candidate_variant']==args.candidate
        assert launch['generation_sha256']==assembly['generation_sha256']
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
        original=root/'build/wsl-reports'/('raw_envelope_'+baselines[case]['snapshot']);old_inputs=read(original/'inputs.json')
        assert old_inputs==baselines[case]['inputs_sha256']
        inputs=read(archive/'inputs.json');report=read(archive/'report.json');accepted=read(archive/'acceptance.json')
        assert inputs==launch['inputs_sha256']==report['input_sha256'] and report['phase']==accepted['phase']=='passed'
        assert report['tests']==1 and report['failures']==0 and read(archive/'snapshot.json')['exit_code']==0
        assert sha(archive/'acceptance.json')==report['acceptance_sha256']
        for n,h in inputs.items():assert sha(source/n)==h,n
        assert {n:sha(p) for n,p in closure('http2_enveloped_parser_application',source).items()}==assembly['executed_parser_sha256']
        assert {n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',source).items()}=={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',original/'execution-sources').items()}
        edits=[('fixture_ownership_edit','capacity_pool_witness_edits','sim/cocotb/receive_pool_witness.py')]
        if case=='native':edits.append(('fixture_admission_edit','capacity_admission_barrier_edits','sim/cocotb/test_raw_grpc_enveloped.py'))
        if case=='all_ledger_faults':edits.append(('fixture_fault_barrier_edit','capacity_format_fault_barrier_edits','sim/cocotb/test_raw_shutdown_faults.py'))
        if case=='retained_native':edits.append(('fixture_retained_snapshot_edit','capacity_retained_snapshot_edits','sim/cocotb/test_raw_grpc_enveloped.py'))
        if case=='retained_shutdown':edits.append(('fixture_shutdown_credit_edit','capacity_shutdown_credit_barrier_edits','sim/cocotb/test_raw_shutdown_faults.py'))
        expected_edits={e[0] for e in edits}|({'fixture_budget_edit'} if case=='other_connection' else set())
        assert {n for n in ('fixture_ownership_edit','fixture_admission_edit','fixture_budget_edit','fixture_fault_barrier_edit','fixture_retained_snapshot_edit','fixture_shutdown_credit_edit') if launch.get(n)}==expected_edits
        edited=set()
        for key,function,n in edits:
            e=launch[key];assert e['path']==n and e['exact_inverse_verified']
            expected,replacements=helpers[function]((original/'execution-sources'/n).read_bytes().decode())
            assert e['replacements']==[list(r) for r in replacements] and (source/n).read_bytes().decode()==expected
            assert sha(source/n)==e['new_sha256'] and old_inputs[n]==e['old_sha256'];edited.add(n)
        if case=='other_connection':
            e=launch['fixture_budget_edit'];n='sim/cocotb/test_raw_grpc_duplex.py'
            replacements=[['assert b.client.outbound_flow_control_window == 65535','assert b.client.outbound_flow_control_window == layout[14] // 128 * (layout[18] + 5)'],
                ['assert b.other.outbound_flow_control_window==65535','assert b.other.outbound_flow_control_window==layout[14] // 128 * (layout[18] + 5)']]
            assert e['path']==n and e['replacements']==replacements and e['exact_inverse_verified']
            text=(source/n).read_bytes().decode()
            for before,after in reversed(replacements):assert text.count(after)==1;text=text.replace(after,before)
            assert hashlib.sha256(text.encode()).hexdigest()==e['old_sha256']==old_inputs[n]
            assert sha(source/n)==e['new_sha256'];edited.add(n)
        for n,h in old_inputs.items():
            if not n.startswith('rtl/') and n not in edited:assert inputs[n]==h,n
        xml=ET.parse(archive/'results.xml');old_xml=ET.parse(original/'results.xml')
        tests=xml.findall('.//testcase');assert len(tests)==1 and tests[0].attrib['name']==old_xml.findall('.//testcase')[0].attrib['name']
        assert not xml.findall('.//failure') and not xml.findall('.//error')
        layout=list(map(int,(source/'build/bidirectional-fixtures/layout.txt').read_text().split()))
        assert layout[14]==384 and layout[18]==131072
        compared,extensions=normalize(accepted,read(original/'acceptance.json'),case,layout,archive)
        deltas=[]
        for path,actual,prior in differences(compared,read(original/'acceptance.json')):
            assert timing_path(path) and type(actual)==type(prior)==int and min(actual,prior)>=0,(case,path,actual,prior)
            deltas.append(dict(path=list(path),actual=actual,baseline=prior))
        assert sha(archive/'protocol-runner-used.py')==launch['driver_sha256']
        executions[case]=dict(run=name,original_snapshot=baselines[case]['snapshot'],accepted=accepted,
            validated_capacity_extensions=extensions,all_original_operation_data_status_and_scope_traces_preserved=True,
            explicit_timing_measurement_differences=deltas,inputs_sha256=inputs)
        artifacts.update([launch_path,*[p for p in archive.iterdir() if p.is_file()]])
    result=dict(phase='receive_capacity_selected_original_lifecycle_replays_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        candidate=args.candidate,assembly_audit_key=assembly['key'],executions=executions,exact_parser_modules=77,exact_tokenizer_modules=22,
        all_seven_original_lifecycle_suites_verified=set(args.cases)==set(CASES),
        complete_images_and_native_packages_preserved=True,all_original_traffic_vectors_preserved=True,
        exact_fixture_edit_inverses_verified=True,only_validated_capacity_and_timing_differences=True,
        full_protocol_fault_matrix_verified=False,native_vendor_memory_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p) for p in artifacts},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation'/(label+'-protocol-evidence')/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name);shutil.copy2(driver,evidence/driver.name)
    for p in (evidence/'audit.json',root/'build/validation'/(label+'-protocol.json')):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','all_seven_original_lifecycle_suites_verified')}))


if __name__=='__main__':main()
