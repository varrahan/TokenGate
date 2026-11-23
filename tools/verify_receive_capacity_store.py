"""Replay actual capacity-store wires, durable writes and every ACK fault."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import xml.etree.ElementTree as ET

from h2.config import H2Configuration
from h2.connection import H2Connection
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def peers():
    client=H2Connection(H2Configuration(client_side=True));server=H2Connection(H2Configuration(client_side=False))
    client.initiate_connection();server.initiate_connection()
    server.receive_data(client.data_to_send());client.receive_data(server.data_to_send())
    server.receive_data(client.data_to_send());server.data_to_send()
    for group in ((1,3),(5,7)):
        for stream in group:client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/rpc')])
        server.receive_data(client.data_to_send());server.data_to_send()
    return client,server


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True)
    ap.add_argument('--extended-large-refunds',action='store_true');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    candidate=root/'build/experiments/receive-capacity-store';generation=read(candidate/'generation.json')
    parent=read(root/'build/validation/open-rpc-reclaim-assembly.json');assert parent['key']=='ad1b6bc9beebcaf5'
    assert generation['parent_assembly_audit_key']==parent['key']
    assert sha(candidate/'generate_receive_capacity_store.py')==generation['generator_sha256']
    assert all(sha(candidate/n)==h for n,h in generation['outputs_sha256'].items())
    modified=(candidate/'rtl/http2_receive_credit_store.v').read_text();inverse=modified
    for before,after in reversed(generation['source_edit_certificate']):
        assert inverse.count(after)==1;inverse=inverse.replace(after,before)
    assert hashlib.sha256(inverse.replace('\n',generation['original_newline']).encode()).hexdigest()==generation['original_store_sha256']==parent['executed_parser_sha256']['http2_receive_credit_store']
    archive=root/'build/wsl-reports'/args.name;source=archive/'execution-sources'
    inputs=read(archive/'inputs.json');report=read(archive/'results/report.json');snapshot=read(archive/'snapshot.json')
    assert snapshot['exit_code']==0 and report['passed'] and report['phase']=='passed'
    assert report['inputs_sha256']==inputs and len(report['executions'])==2
    for n,h in inputs.items():assert sha(source/n)==h,n
    assert read(archive/'generation.json')==generation
    modules=closure('http2_receive_credit_store',source)
    assert set(modules)=={'http2_receive_credit_store','memory_command_slot'}
    assert {'rtl/'+p.name:sha(p) for p in modules.values()}==generation['outputs_sha256']
    original=root/'build/wsl-reports/http2_receive_credits_receive_credit_actual_retired_binding'
    baseline=read(original/'inputs.json')
    assert set(inputs)==set(baseline)|{'sim/cocotb/test_receive_capacity_store.py','tools/run_receive_capacity_store_units_wsl.py'}
    assert {n for n in baseline if inputs[n]!=baseline[n]}=={'rtl/http2_receive_credit_store.v'}
    assert inputs['build/http2-send-window-fixtures/model.bin']=='c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    assert (source/'build/http2-send-window-fixtures/model.bin').stat().st_size==8388608
    accepted={}
    for result,label,module,enabled in zip(report['executions'],('legacy','capacity'),('test_receive_credit_store','test_receive_capacity_store'),(0,1)):
        assert (result['mode'],result['test_module'],result['enabled'])==(label,module,enabled)
        folder=archive/'results'/label;xml=ET.parse(folder/'results.xml')
        assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure') and not xml.findall('.//error')
        assert xml.findall('.//testcase')[0].attrib['classname']==module
        assert sha(folder/'acceptance.json')==result['acceptance_sha256']
        accepted[label]=read(folder/'acceptance.json');assert accepted[label]['phase']=='passed'
    assert accepted['legacy']==read(original/'acceptance.json'),'Original complete legacy assertions/acceptance changed'
    legacy_faults=accepted['legacy']['every_memory_ack_fault'];assert len(legacy_faults)==142
    actual=accepted['capacity'];assert actual['complete_model_bytes']==8388608
    for field in ('actual_intent_ack_before_capacity_wire','actual_wire_before_available_commit',
        'captured_backing_survives_input_poison','unused_pending_capacity_not_refunded_twice','complete_model_prefix_immutable',
        'typed_directory_maintenance_and_consumption_authority'):assert actual[field] is True
    for field in ('actual_parser_integrated','actual_dma_retirement_integrated','original_large_message_counterexample_fixed',
        'whole_system_retained_reset_verified','full_system_complete'):assert actual[field] is False
    assert actual['invalid_backing_geometries']==8 and actual['invalid_rpc_backings']==4
    stream_capacity=131077;connection_capacity=524308
    client,server=peers();wire=[bytes.fromhex(x) for x in actual['large_record']['wire_hex']]
    assert len(wire)==4 and actual['large_record']['actual_data_bytes']==65541
    def update(index,stream,amount):
        server.increment_flow_control_window(amount,stream_id=stream or None)
        assert server.data_to_send()==wire[index]
        client.receive_data(wire[index])
    update(0,1,stream_capacity-65535);update(1,0,connection_capacity-65535)
    record=b'\0\0\1\0\0'+b'U'*65536
    for offset in range(0,len(record),16384):
        chunk=record[offset:offset+16384];client.send_data(1,chunk,end_stream=offset+len(chunk)==len(record))
        events=server.receive_data(client.data_to_send())
        assert b''.join(e.data for e in events if type(e).__name__=='DataReceived')==chunk
    update(2,1,len(record));update(3,0,len(record))
    assert client.outbound_flow_control_window==connection_capacity and client.streams[1].outbound_flow_control_window==stream_capacity
    interleaved=actual['interleaved'];client,server=peers();wire=[bytes.fromhex(x) for x in interleaved['wire_hex']]
    assert len(wire)==6
    for i,stream in enumerate((1,3,5,7)):update(i,stream,stream_capacity-65535)
    update(4,0,connection_capacity-65535)
    for _ in range(2):
        for stream in (1,3,5,7):
            client.send_data(stream,b'P'*16384)
            assert sum(len(e.data) for e in server.receive_data(client.data_to_send()) if type(e).__name__=='DataReceived')==16384
    assert client.outbound_flow_control_window==interleaved['connection_available_before_close']==connection_capacity-131072
    update(5,0,131072)
    assert client.outbound_flow_control_window==interleaved['final_connection_available']==connection_capacity
    assert interleaved['close_refund_idempotent'] and interleaved['streams']==4 and interleaved['data_bytes']==131072
    # Reconstruct the durable ledgers from every real memory write, including
    # writes physically applied before their failed ACK. Reads cannot mutate.
    def apply(before,trace):
        ledgers={n:bytearray.fromhex(h) for n,h in before.items()}
        for row in trace:
            assert row['acked'] and row['status'] in (0,0x75)
            if row['write']:
                address=row['address'];found=False
                for n,base in [('connection',0x7e0800),('stream',0x7e1000)]:
                    if base<=address and address+8<=base+len(ledgers[n]):
                        ledgers[n][address-base:address-base+8]=(row['data']&((1<<64)-1)).to_bytes(8,'little');found=True;break
                assert found,('Write escaped selected durable ledgers',address)
        return {n:bytes(v).hex() for n,v in ledgers.items()}
    baselines={(b['op'],b['stream']):b for b in actual['actual_operation_baselines']}
    expected={(12,0):10,(1,1):22,(4,1):20,(4,0):12}
    if args.extended_large_refunds:expected.update({(3,1):19,(5,1):20})
    assert set(baselines)==set(expected)
    layout=read(source/'build/http2-send-window-fixtures/cases.json')['layout']
    conn=struct.pack('<16I',0x48325243,0,65535,stream_capacity,connection_capacity-65535,0,
        layout['context_base'],layout['context_bytes'],layout['stream_base'],layout['stream_bytes'],
        0x7e0800,192,0x7e1000,128,0x740000,4*131072)
    stream=struct.pack('<8I',0x48325253,101,65535,1,stream_capacity-65535,0,stream_capacity,0)
    assert baselines[12,0]['after_ledgers']['connection']==conn.hex()
    assert baselines[1,1]['after_ledgers']['stream']==stream.hex()
    for key,b in baselines.items():
        assert len(b['actual_memory_trace'])==expected[key]
        assert all(c['status']==0 for c in b['actual_memory_trace'])
        assert apply(b['before_ledgers'],b['actual_memory_trace'])==b['after_ledgers']
    assert int.from_bytes(bytes.fromhex(baselines[4,1]['after_ledgers']['stream'])[8:12],'little')==stream_capacity
    assert int.from_bytes(bytes.fromhex(baselines[4,0]['after_ledgers']['connection'])[8:12],'little')==connection_capacity
    if args.extended_large_refunds:
        for key in ((3,1),(5,1)):
            b=baselines[key]
            assert b['amount']==(65541 if key[0]==3 else 0)
            before={n:struct.unpack('<'+('16I' if n=='connection' else '8I'),bytes.fromhex(h)) for n,h in b['before_ledgers'].items()}
            after={n:struct.unpack('<'+('16I' if n=='connection' else '8I'),bytes.fromhex(h)) for n,h in b['after_ledgers'].items()}
            assert before['connection'][2]==connection_capacity-65541 and before['connection'][4:6]==(0,0)
            assert before['stream'][2]==stream_capacity-65541 and before['stream'][3:6]==(1,0,0)
            assert after['connection'][2]==connection_capacity-65541 and after['connection'][4:6]==(65541,0)
            assert after['stream'][2]==stream_capacity-65541
            assert after['stream'][3:6]==((1,65541,0) if key[0]==3 else (0x80000001,0,0))
    faults=actual['every_capacity_memory_ack_fault'];assert len(faults)==sum(expected.values())==(103 if args.extended_large_refunds else 64)
    assert [(f['op'],f['stream'],f['phase']) for f in faults]==[(op,s,p) for (op,s),count in expected.items() for p in range(count)]
    for fault in faults:
        key=fault['op'],fault['stream'];phase=fault['phase'];b=baselines[key];trace=fault['actual_memory_trace']
        assert fault['before_ledgers']==b['before_ledgers'] and len(trace)==fault['memory_commands']==phase+1
        for i,c in enumerate(trace):assert dict(c,status=0)==b['actual_memory_trace'][i]
        assert [c['status'] for c in trace]==[0]*phase+[0x75]
        assert apply(fault['before_ledgers'],trace)==fault['after_ledgers']
        assert fault['wire_retired']==(key[0]==4 and phase>=expected[key]-2)
        assert fault['error']==0x75 and fault['foreign_backing_cannot_clear_quarantine']
        if args.extended_large_refunds:assert fault['amount']==b['amount']
    # Preserve the incorrect V1 wire-history assertion, and prove V2/V3
    # exercised identical RTL rather than repairing hardware to fit a test.
    prior={}
    for version,code in ((1,1),(2,0)):
        folder=root/'build/wsl-reports'/f'receive_capacity_store_units_v{version}_20261122'
        assert read(folder/'snapshot.json')['exit_code']==code
        old_inputs=read(folder/'inputs.json')
        assert old_inputs['rtl/http2_receive_credit_store.v']==inputs['rtl/http2_receive_credit_store.v']
        prior[str(version)]=dict(exit_code=code,snapshot_sha256=sha(folder/'snapshot.json'))
    result=dict(phase='receive_capacity_store_component_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,parent_assembly_audit_key=parent['key'],generation_sha256=sha(candidate/'generation.json'),
        actual_store_sha256=inputs['rtl/http2_receive_credit_store.v'],actual_memory_slot_sha256=inputs['rtl/memory_command_slot.v'],
        source_edit_inverse_verified=True,legacy_acceptance_exactly_equal=True,legacy_memory_ack_faults=142,
        new_capacity_memory_ack_faults=len(faults),actual_failed_ack_writes_independently_replayed=True,
        large_release_and_close_ack_faults=39 if args.extended_large_refunds else 0,
        native_large_record_bytes=65541,native_interleaved_partial_streams=4,
        actual_native_window_updates_independently_replayed=True,durable_backing_geometry_verified=True,
        complete_original_image_preserved=True,typed_component_authority=True,prior_runs_preserved=prior,
        actual_parser_integrated=False,actual_dma_retirement_integrated=False,large_message_deadlock_fixed=False,
        native_vendor_runtime_verified=False,whole_system_retained_reset_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p) for p in [archive/'inputs.json',archive/'generation.json',archive/'snapshot.json',archive/'results/report.json',
            *[p for p in (archive/'results').glob('*/*') if p.is_file()]]},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-capacity-store-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    label='receive-capacity-store-large-refunds' if args.extended_large_refunds else 'receive-capacity-store'
    for p in (evidence/'audit.json',root/'build/validation'/(label+'.json')):p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','new_capacity_memory_ack_faults')}))


if __name__=='__main__':main()
