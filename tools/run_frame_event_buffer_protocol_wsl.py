"""Replay complete original protocol/fault corpora on the buffered 76-module Parser."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys

from verify_two_fpga_application import closure


def capacity_pool_witness_edits(original):
    """Keep original receive checks and account for the additional private owner."""
    edits=[
        ("        b_owned = value(c, 'receive_pool_active')",
         """        if value(c, 'rc_start') and value(c, 'rc_start_ready'):
            assert active is None and not pending
            active = 'private'
            counts['private_commands'] += 1
        b_owned = value(c, 'receive_pool_active')"""),
        ("value(c, 'receive_request_pool_base'), value(c, 'receive_request_pool_bytes'))",
         "(value(c, 'rc_lock_base'), value(c, 'rc_lock_bytes')) if active == 'private' else (value(c, 'receive_request_pool_base'), value(c, 'receive_request_pool_bytes')))"),
        ("        if value(c, 'receive_pool_unlock_valid') and value(c, 'receive_pool_unlock_ready'):\n            assert active is None and not pending",
         """        if value(c, 'receive_pool_unlock_valid') and value(c, 'receive_pool_unlock_ready'):
            if active == 'private':
                assert value(c, 'rc_unlock_valid') and value(c, 'rc_unlock_ready') and not pending
            else:
                assert active is None and not pending"""),
        ("            if active == 'ordinary':",
         """            if active == 'private':
                assert value(c, 'rc_busy') or value(c, 'rc_start')
                assert not value(c, 'receive_admission_lock_active')
            elif active == 'ordinary':"""),
        ("            assert active is not None and pending",
         """            assert active is not None and pending
            if active == 'private':
                assert value(c, 'rc_lock_active') and b_owned
                assert value(c, 'rc_memory_owner') ^ value(c, 'rc_credit_owner')
                counts['private_memory_acks'] += 1"""),
        ("            assert active is not None and not pending\n            pending = True",
         """            assert active is not None and not pending
            if active == 'private':
                assert value(c, 'rc_lock_active') and b_owned
                assert value(c, 'rc_memory_owner') ^ value(c, 'rc_credit_owner')
                counts['private_memory_commands'] += 1
            pending = True"""),
        ("        if value(c, 'rx_result_valid') and value(c, 'rx_result_ready'):",
         """        if value(c, 'rc_result_valid'):
            assert active == 'private' and not pending
            assert (value(c, 'rc_status'), value(c, 'rc_detail'), value(c, 'rc_memory_status')) == (0, 0, 0)
            counts['private_results'] += 1
            active = None
        if value(c, 'rx_result_valid') and value(c, 'rx_result_ready'):"""),
        ("ordinary_commands=0, receive_memory_commands=0, receive_memory_acks=0)",
         "ordinary_commands=0, receive_memory_commands=0, receive_memory_acks=0, private_commands=0, private_results=0, private_memory_commands=0, private_memory_acks=0)"),
    ]
    text=original
    for before,after in edits:
        assert text.count(before)==1,before
        text=text.replace(before,after)
    inverse=text
    for before,after in reversed(edits):
        assert inverse.count(after)==1
        inverse=inverse.replace(after,before)
    assert inverse==original
    compile(text,'receive_pool_witness.py','exec')
    return text,edits


def capacity_admission_barrier_edits(original):
    """Drain new HEADERS-only capacity before the original wire-stall probes."""
    helper='''async def wait_initial_capacity(b, stream):
    before = len(b.wire)
    core = b.d.dut.core
    for _ in range(100000):
        if not value(core, 'rc_pending') and not value(core, 'rc_busy'):
            break
        await cycles(b.d)
    else:
        raise AssertionError(('Initial capacity did not retire before wire probe', stream))
    assert not value(b.d, 'receive_recovery_required') and not value(core, 'rc_lock_active')
    assert b.client.streams[stream].outbound_flow_control_window == b.layout[18] + 5
    updates = [raw for raw in b.wire if raw[3] == 8 and int.from_bytes(raw[5:9], 'big') == stream]
    assert len(updates) == 1 and len(updates[0]) == 13
    assert int.from_bytes(updates[0][9:], 'big') == b.layout[18] + 5 - 65535
    assert all(len(raw) == 13 and raw[3] == 8 for raw in b.wire[before:])
    if not hasattr(b, 'capacity_admission_barriers'):
        b.capacity_admission_barriers = []
    b.capacity_admission_barriers.append(dict(stream=stream, wire_before=before, wire_after=len(b.wire),
        actual_wire_prefix=[raw.hex() for raw in b.wire], stream_credit=b.client.streams[stream].outbound_flow_control_window))


'''
    edits=[('@cocotb.test(timeout_time=30,timeout_unit=\'ms\')',helper+'@cocotb.test(timeout_time=30,timeout_unit=\'ms\')')]
    before='await b.packet(0,tag,b.client.data_to_send(),1);tag+=1;b.client.reset_stream(5,error_code=8);raw=b.client.data_to_send()'
    edits.append((before,before.replace(';tag+=1;', ';await wait_initial_capacity(b,5);tag+=1;')))
    for stream in (7,11):
        before=f"await b.packet(0,tag,b.client.data_to_send(),1);tag+=1;b.ready_wire=False;before=len(b.wire)\n    await b.gpu_offer({stream},15339,0,0,0)"
        edits.append((before,before.replace(';tag+=1;',f';await wait_initial_capacity(b,{stream});tag+=1;')))
    before="    accepted['actual_receive_pool_ownership']=pool"
    edits.append((before,before+"\n    accepted['capacity_admission_barriers']=b.capacity_admission_barriers"))
    newline='\r\n' if '\r\n' in original else '\n'
    edits=[(before.replace('\n',newline),after.replace('\n',newline)) for before,after in edits]
    text=original
    for before,after in edits:
        assert text.count(before)==1,before
        text=text.replace(before,after)
    inverse=text
    for before,after in reversed(edits):
        assert inverse.count(after)==1
        inverse=inverse.replace(after,before)
    assert inverse==original
    compile(text,'test_raw_grpc_enveloped.py','exec')
    return text,edits


def capacity_format_fault_barrier_edits(original):
    before='''    await b.admit_headers(reference,2,1)
    base=0x7f0000;size=layout[14]//8'''
    after='''    await b.admit_headers(reference,2,1)
    # Retire initial packet-triggered credit work before arming a fault for
    # the separate explicit global FORMAT. Concurrent FORMAT admission is
    # checked by the independent directed ownership-race fixture.
    for _ in range(100000):
        if not value(d.dut.core,'rc_pending') and not value(d.dut.core,'rc_busy'):
            break
        await cycles(d)
    else:raise AssertionError('Initial private capacity did not drain before FORMAT fault arming')
    assert not value(d.dut.core,'rc_lock_active') and not value(d,'receive_recovery_required')
    capacity_before_faults=[raw.hex() for raw in b.wire]
    base=0x7f0000;size=layout[14]//8'''
    marker="    accepted=dict(phase='passed',actual_progress_format_fault_cases=progress_cases,"
    edits=[(before,after),(marker,marker+"\n        actual_initial_capacity_wire_before_faults=capacity_before_faults,")]
    newline='\r\n' if '\r\n' in original else '\n'
    edits=[(a.replace('\n',newline),b.replace('\n',newline)) for a,b in edits]
    text=original
    for before,after in edits:
        assert text.count(before)==1,before;text=text.replace(before,after)
    inverse=text
    for before,after in reversed(edits):
        assert inverse.count(after)==1;inverse=inverse.replace(after,before)
    assert inverse==original
    compile(text,'test_raw_shutdown_faults.py','exec')
    return text,edits


def capacity_retained_snapshot_edits(original):
    before='        epochs.append(record);all_dma.extend(returned_dma_ids)'
    after='''        (Path.cwd()/f'retained_parser_mutable_epoch{epoch}.bin').write_bytes(memory.data[layout[6]:])
        (Path.cwd()/f'retained_tokenizer_mutable_epoch{epoch}.bin').write_bytes(memory.tokenizer_data[layout[6]:])
        epochs.append(record);all_dma.extend(returned_dma_ids)'''
    newline='\r\n' if '\r\n' in original else '\n'
    after=after.replace('\n',newline)
    assert original.count(before)==1
    text=original.replace(before,after);assert text.replace(after,before)==original
    compile(text,'test_raw_grpc_enveloped.py','exec')
    return text,[(before,after)]


def capacity_shutdown_credit_barrier_edits(original):
    before='    await b.admit_headers(reference,2,1)'
    after='''    await b.admit_headers(reference,2,1)
    for _ in range(100000):
        if not value(d.dut.core,'rc_pending') and not value(d.dut.core,'rc_busy'):
            break
        await cycles(d)
    else:raise AssertionError('Initial capacity did not drain before shutdown fault arming')
    assert not value(d.dut.core,'rc_lock_active') and not value(d,'receive_recovery_required')
    stream_increment=b.layout[18]+5-65535
    connection_increment=b.layout[14]//128*(b.layout[18]+5)-65535
    expected=[b'\\0\\0\\4\\x08\\0'+sid.to_bytes(4,'big')+amount.to_bytes(4,'big')
        for sid,amount in ((1,stream_increment),(0,connection_increment))]
    assert b.wire[-2:]==expected
    if not hasattr(b,'capacity_shutdown_admission_wires'):b.capacity_shutdown_admission_wires=[]
    b.capacity_shutdown_admission_wires.append([raw.hex() for raw in b.wire[-2:]])
    Path('capacity_shutdown_admission_wires.json').write_text(json.dumps(b.capacity_shutdown_admission_wires,indent=2)+'\\n')'''
    newline='\r\n' if '\r\n' in original else '\n'
    after=after.replace('\n',newline)
    assert original.count(before)==1
    text=original.replace(before,after);assert text.replace(after,before)==original
    compile(text,'test_raw_shutdown_faults.py','exec')
    return text,[(before,after)]


def capacity_extended_barrier_edits(original, case):
    """Verify each new initial grant before the original directed fault/race."""
    helper='''async def settle_backed_initial_capacity(b, stream, before, first):
    core = b.d.dut.core
    for _ in range(100000):
        if not value(core, 'rc_pending') and not value(core, 'rc_busy'):
            break
        await cycles(b.d)
    else:
        raise AssertionError(('Initial backed capacity did not retire', stream))
    assert not value(b.d, 'receive_recovery_required') and not value(core, 'rc_lock_active')
    capacity = b.layout[18] + 5
    connection_capacity = b.layout[14] // 128 * capacity
    expected = [(stream, capacity - 65535)]
    if first:
        expected.append((0, connection_capacity - 65535))
    updates = [raw for raw in b.wire[before:] if raw[3] == 8]
    assert len(updates) == len(expected)
    assert [(int.from_bytes(raw[5:9], 'big'), int.from_bytes(raw[9:], 'big')) for raw in updates] == expected
    assert all(len(raw) == 13 and raw[:5] == bytes.fromhex('0000040800') for raw in updates)
    assert b.client.streams[stream].outbound_flow_control_window == capacity
    assert b.client.outbound_flow_control_window == connection_capacity
    path = Path('capacity_extended_admission_wires.json')
    records = json.loads(path.read_text()) if path.exists() else []
    records.append(dict(stream=stream, first=first, wire_before=before, wire_after=len(b.wire),
        actual_wire=[raw.hex() for raw in b.wire[before:]],
        stream_credit=capacity, connection_credit=connection_capacity))
    path.write_text(json.dumps(records, indent=2) + '\\n')


'''
    if case in ('duplex','duplex_faults'):
        anchor='async def exercise_duplex(d, fault_phase=None):'
        packets=[('    await b.packet(0, 2, b.client.data_to_send(), 1)',1,True),
                 ('    await b.packet(0, 5, b.client.data_to_send(), 1)',3,False)]
    elif case=='return_faults':
        anchor='async def bootstrap(b,index):'
        packets=[('    await b.packet(0,2,b.client.data_to_send(),1)',1,True)]
    else:
        anchor=original[original.index('@cocotb.test'):].splitlines()[0]
        packets=[('    await b.packet(0, 2, '+('headers' if case=='receive_errors' else 'b.client.data_to_send()')+', 1)',1,True)]
    edits=[(anchor,helper+anchor)]
    for before,stream,first in packets:
        after='    capacity_wire_before = len(b.wire)\n'+before+f'\n    await settle_backed_initial_capacity(b, {stream}, capacity_wire_before, {first})'
        edits.append((before,after))
    if case=='receive_errors':
        edits.append(('assert b.client.outbound_flow_control_window == 65535',
                      'assert b.client.outbound_flow_control_window == layout[14] // 128 * (layout[18] + 5)'))
    newline='\r\n' if '\r\n' in original else '\n'
    edits=[(before.replace('\n',newline),after.replace('\n',newline)) for before,after in edits]
    text=original
    for before,after in edits:
        assert text.count(before)==1,(case,before)
        text=text.replace(before,after)
    inverse=text
    for before,after in reversed(edits):
        assert inverse.count(after)==1
        inverse=inverse.replace(after,before)
    assert inverse==original
    compile(text,'capacity_extended_'+case+'.py','exec')
    return text,edits


def capacity_fault_link_top_edits(original):
    """Apply legal backpressure at the real Tokenizer-to-Parser UTF-8 boundary."""
    newline='\r\n' if '\r\n' in original else '\n'
    original=original.replace('\r\n','\n')
    declaration='wire  link_s_s_axis_text_tready;'
    extra='''
reg return_link_pause=0;
wire return_link_source_ready=link_s_s_axis_text_tready&&!return_link_pause;
integer return_link_pause_clocks=0,return_link_held_clocks=0,return_link_transfers=0;
reg return_link_was_held=0;
reg [160:0] return_link_held_payload;
always @(posedge clk)begin
    if(rst)return_link_was_held<=0;
    else begin
        if(return_link_was_held)begin
            assert(link_s_s_axis_text_tvalid&&
                {link_s_s_axis_text_tdata,link_s_s_axis_text_tkeep,link_s_s_axis_text_tlast,link_s_s_axis_text_tuser}===return_link_held_payload)
                else $fatal(1,"Actual inter-FPGA UTF-8 offer changed while backpressured");
        end
        return_link_was_held<=link_s_s_axis_text_tvalid&&!return_link_source_ready;
        return_link_held_payload<={link_s_s_axis_text_tdata,link_s_s_axis_text_tkeep,link_s_s_axis_text_tlast,link_s_s_axis_text_tuser};
        if(return_link_pause)return_link_pause_clocks<=return_link_pause_clocks+1;
        if(link_s_s_axis_text_tvalid&&!return_link_source_ready)return_link_held_clocks<=return_link_held_clocks+1;
        if(link_s_s_axis_text_tvalid&&return_link_source_ready)return_link_transfers<=return_link_transfers+1;
    end
end
'''
    edits=[(declaration,declaration+extra)]
    # There are two endpoints. Change the Parser valid and Tokenizer ready only.
    ready='    .link_s_s_axis_text_tready(link_s_s_axis_text_tready),'
    valid='    .link_s_s_axis_text_tvalid(link_s_s_axis_text_tvalid),'
    assert original.count(ready)==original.count(valid)==2
    parser_context=original[original.index(ready)-len(valid)-1:original.index(ready)+len(ready)]
    assert parser_context==valid+'\n'+ready
    edits.append((parser_context,valid.replace('(link_s_s_axis_text_tvalid)','(link_s_s_axis_text_tvalid&&!return_link_pause)')+'\n'+ready))
    # Scoped by the following unchanged Tokenizer lease wiring, after Parser ready differs.
    tokenizer_before=valid+'\n'+ready
    tokenizer_after=valid+'\n'+ready.replace('(link_s_s_axis_text_tready)','(return_link_source_ready)')
    text=original
    applied=[]
    for index,(before,after) in enumerate(edits):
        assert text.count(before)==(2 if index==1 else 1)
        text=text.replace(before,after,1);applied.append((before,after))
    assert text.count(valid+'\n'+ready)==1
    text=text.replace(tokenizer_before,tokenizer_after)
    applied.append((tokenizer_before,tokenizer_after))
    inverse=text
    for before,after in reversed(applied):
        assert inverse.count(after)==1;inverse=inverse.replace(after,before,1)
    assert inverse==original
    return text.replace('\n',newline),[(before.replace('\n',newline),after.replace('\n',newline)) for before,after in applied]


def capacity_fault_link_fixture_edits(original):
    before='    generated = cocotb.start_soon(b.gpu_offer(3, 15339, 0, 1, 0)); await cycles(d, 19)'
    after='''    if fault_phase is not None:
        assert not value(d, 'link_s_s_axis_text_tvalid')
        pause_start = value(d, 'return_link_pause_clocks')
        held_start = value(d, 'return_link_held_clocks')
        b.set(return_link_pause=1)
'''+before
    edits=[(before,after)]
    before='''        await cycles(d); b.set(fault_arm=0)
    injecting = cocotb.start_soon(inject_write_fault()) if fault_phase is not None else None'''
    after='''        await cycles(d); b.set(fault_arm=0)
        for _ in range(100000):
            if value(d, 'fault_injected'):
                break
            await cycles(d)
        else:
            raise AssertionError(('Actual raw context fault did not acknowledge under link backpressure', fault_phase))
        assert value(d, 'response_record_lease_active') and value(d, 'return_link_pause')
        assert not any(raw[3] == 0 and int.from_bytes(raw[5:9], 'big') == 3 for raw in b.wire)
        b.set(return_link_pause=0)
    injecting = cocotb.start_soon(inject_write_fault()) if fault_phase is not None else None'''
    edits.append((before,after))
    before='''            cold_memory_initialization=True, final_recovery=recovery, **counts)
        for worker in workers: worker.cancel()'''
    after='''            cold_memory_initialization=True, final_recovery=recovery, **counts)
        result['capacity_fault_link_pause'] = dict(
            pause_cycles=value(d, 'return_link_pause_clocks')-pause_start,
            held_cycles=value(d, 'return_link_held_clocks')-held_start,
            actual_fault_ack=value(d, 'fault_injected'), link_released=not value(d, 'return_link_pause'))
        assert result['capacity_fault_link_pause']['pause_cycles'] > 0
        for worker in workers: worker.cancel()'''
    edits.append((before,after));text=original
    for before,after in edits:
        assert text.count(before)==1; text=text.replace(before,after)
    inverse=text
    for before,after in reversed(edits):
        assert inverse.count(after)==1;inverse=inverse.replace(after,before)
    assert inverse==original;compile(text,'capacity_fault_link.py','exec')
    return text,edits


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cases',nargs='+',required=True)
    ap.add_argument('--candidate',choices=('frame-event-buffer','frame-owned-quiet','payload-event-buffer','open-rpc-reclaim','rpc-completion-flags','receive-capacity-v2','receive-capacity-v4','rpc-success-predicate-v2'),default='frame-event-buffer')
    ap.add_argument('--variant',choices=('buffered','unbuffered'),default='buffered')
    ap.add_argument('--initialize-progress',action='store_true')
    ap.add_argument('--capacity-owner-witness',action='store_true')
    ap.add_argument('--capacity-admission-barrier',action='store_true')
    ap.add_argument('--capacity-budget-expectations',action='store_true')
    ap.add_argument('--capacity-format-fault-barrier',action='store_true')
    ap.add_argument('--capacity-retained-snapshots',action='store_true')
    ap.add_argument('--capacity-shutdown-credit-barrier',action='store_true')
    ap.add_argument('--capacity-extended-barrier',action='store_true')
    ap.add_argument('--capacity-fault-link-pause',action='store_true');args=ap.parse_args()
    capacity=args.candidate in ('receive-capacity-v2','receive-capacity-v4')
    reclaim=args.candidate=='open-rpc-reclaim' or capacity
    if args.capacity_owner_witness:assert capacity
    if args.capacity_admission_barrier:assert args.capacity_owner_witness and args.cases==['native']
    if args.capacity_budget_expectations:assert args.capacity_owner_witness and args.cases==['other_connection']
    if args.capacity_format_fault_barrier:assert args.candidate=='receive-capacity-v4' and args.capacity_owner_witness and args.cases==['all_ledger_faults']
    if args.capacity_retained_snapshots:assert args.candidate=='receive-capacity-v4' and args.capacity_owner_witness and args.cases==['retained_native']
    if args.capacity_shutdown_credit_barrier:assert args.candidate=='receive-capacity-v4' and args.capacity_owner_witness and args.cases==['retained_shutdown']
    if args.capacity_extended_barrier:assert args.candidate=='receive-capacity-v4' and args.initialize_progress and set(args.cases)<={'receive_flow','receive_errors','duplex','duplex_faults','return_faults'}
    if args.capacity_fault_link_pause:assert args.capacity_extended_barrier and args.cases==['duplex_faults']
    assert len(set(args.cases))==len(args.cases)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    driver_source=Path(__file__).read_bytes()
    flags=args.candidate in ('rpc-completion-flags','rpc-success-predicate-v2')
    semantic=args.candidate=='payload-event-buffer' or flags
    approved=Path('/home/varrahan/development/hardware/parser');assert approved.is_dir()
    import cocotb
    sys.path.insert(0,str(root/'scripts'));from run_raw_envelope_tests import freeze_model_image
    cases={}
    for name,key in (('progress-format-regressions','736eec1fa78adf7d'),('progress-format-experiment','c7aebf98ee6f7e25')):
        audit=read(root/'build/validation'/(name+'.json'));assert audit['key']==key
        for case,record in audit['executions'].items():
            assert case not in cases;cases[case]=(key,record)
    corpus=read(root/'build/validation/json-simd-corpus.json');assert corpus['key']=='2509134d2630b47e'
    archive=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122'
    cases['corpus']=(corpus['key'],dict(snapshot='json_simd_full_native_corpus_20261122',profile='workload',inputs_sha256=corpus['inputs_sha256']))
    extra_profiles=dict(receive_flow='receive-flow',receive_errors='receive-errors',duplex='duplex',duplex_faults='duplex-faults',return_faults='return-faults')
    for case,profile in extra_profiles.items():
        cases[case]=(corpus['key'],dict(snapshot='json_simd_full_native_corpus_20261122',profile=profile,inputs_sha256=corpus['inputs_sha256']))
    assert set(args.cases)<=cases.keys()
    if args.variant=='unbuffered' or args.initialize_progress:assert set(args.cases)<=extra_profiles.keys()
    if args.candidate!='frame-event-buffer':assert args.variant=='buffered'
    candidate=root/'build/experiments'/args.candidate;generation=read(candidate/'generation.json')
    assert all(sha(candidate/n)==h for n,h in generation['outputs_sha256'].items())
    for case in args.cases:
        key,baseline=cases[case]
        prefix=({'frame-owned-quiet':'frame_owned_quiet_','frame-event-buffer':'frame_event_buffer_',
                 'payload-event-buffer':'payload_event_buffer_','open-rpc-reclaim':'open_rpc_reclaim_',
                 'rpc-completion-flags':'rpc_completion_flags_','receive-capacity-v2':'receive_capacity_v2_',
                 'receive-capacity-v4':'receive_capacity_v4_',
                 'rpc-success-predicate-v2':'rpc_success_predicate_v2_'}[args.candidate]) if args.variant=='buffered' else 'frame_event_before_'
        run=prefix+case+('_init' if args.initialize_progress else '')+('_owner' if args.capacity_owner_witness else '')+('_admission' if args.capacity_admission_barrier else '')+('_budget' if args.capacity_budget_expectations else '')+('_fault_barrier' if args.capacity_format_fault_barrier else '')+('_snapshots' if args.capacity_retained_snapshots else '')+('_credit' if args.capacity_shutdown_credit_barrier else '')+('_credit' if args.capacity_extended_barrier else '')+('_textlink' if args.capacity_fault_link_pause else '')+'_20261122';target=approved/'build/raw-envelope-tests'/run
        output=root/'build/wsl-reports'/('raw_envelope_'+run)
        assert not target.exists() and not output.exists()
        assert min(shutil.disk_usage(root).free,shutil.disk_usage(approved).free)>3*1024**3
        original=root/'build/wsl-reports'/('raw_envelope_'+baseline['snapshot'])
        inputs=read(original/'inputs.json');assert inputs==baseline['inputs_sha256']
        target.mkdir(parents=True,exist_ok=False)
        for name,digest in inputs.items():
            source=original/'execution-sources'/name;assert sha(source)==digest,name
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
            if name=='build/bidirectional-fixtures/memory.mem':freeze_model_image(source,destination,approved)
            else:shutil.copy2(source,destination)
        changed=[];added=[]
        for name,digest in generation['outputs_sha256'].items():
            if args.variant=='unbuffered' and name=='rtl/http2_axis_ingress.v':continue
            if inputs.get(name)==digest:continue
            source=candidate/name;assert sha(source)==digest
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
            (changed if name in inputs else added).append(name);shutil.copy2(source,destination);inputs[name]=digest
        if args.variant=='unbuffered':assert not changed and not added
        elif case=='corpus' or case in extra_profiles:
            expected_changes={'rtl/http2_axis_ingress.v'}
            if args.candidate=='frame-owned-quiet' or reclaim or semantic:expected_changes.add('rtl/http2_enveloped_frame_grants.v')
            if semantic:expected_changes.add('rtl/http2_payload_decoder.v')
            if flags:expected_changes.add('rtl/rpc_http2_response_partition.v')
            if args.candidate=='rpc-success-predicate-v2':expected_changes.add('rtl/rpc_grpc_http2_parser_response.v')
            if reclaim:expected_changes.update('rtl/'+n+'.v' for n in generation['changed_existing_modules'])
            expected_added={'rtl/axis_pingpong_skid_buffer.v'} if semantic else {'rtl/grpc_payload_reclaimer.v'} if reclaim else set()
            assert set(changed)==expected_changes and set(added)==expected_added
        else:
            expected_changes={'rtl/http2_axis_ingress.v','rtl/json_string_normalizer.v','rtl/proto_json_decoder.v','rtl/speculative_json_fsm.v'}
            if args.candidate=='frame-owned-quiet' or reclaim or semantic:expected_changes.add('rtl/http2_enveloped_frame_grants.v')
            if semantic:expected_changes.add('rtl/http2_payload_decoder.v')
            if flags:expected_changes.add('rtl/rpc_http2_response_partition.v')
            if args.candidate=='rpc-success-predicate-v2':expected_changes.add('rtl/rpc_grpc_http2_parser_response.v')
            if reclaim:expected_changes.update('rtl/'+n+'.v' for n in generation['changed_existing_modules'])
            assert set(changed)==expected_changes,changed
            expected_added={'rtl/axis_compacting_window.v','rtl/json_simd_scanner.v'}
            if semantic:expected_added.add('rtl/axis_pingpong_skid_buffer.v')
            if reclaim:expected_added.add('rtl/grpc_payload_reclaimer.v')
            assert set(added)==expected_added,added
        parser_modules=77 if semantic or reclaim else 76
        assert len(closure('http2_enveloped_parser_application',target))==parser_modules
        assert len(closure('tokenizer_fpga_memory_subsystem',target))==22
        fixture_edit=None
        if args.initialize_progress:
            module=dict(receive_flow='test_raw_receive_flow.py',receive_errors='test_raw_receive_errors.py',
                duplex='test_raw_grpc_duplex.py',duplex_faults='test_raw_grpc_duplex.py',return_faults='test_raw_grpc_return_faults.py')[case]
            name='sim/cocotb/'+module;path=target/name;old=path.read_text()
            before='await b.directory(4)';after='b.response_configuration(0); await b.directory(4)'
            assert old.count(before)==1
            updated=old.replace(before,after);assert updated.replace(after,before)==old
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            fixture_edit=dict(path=name,old=before,new=after,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                only_change='Initialize the existing response-progress geometry before its required FORMAT')
        ownership_edit=None
        if args.capacity_owner_witness:
            name='sim/cocotb/receive_pool_witness.py';path=target/name
            original=path.read_bytes().decode();updated,replacements=capacity_pool_witness_edits(original)
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            ownership_edit=dict(path=name,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Extend passive ownership assertions to the actual private pool/memory owner; preserve receive assertions')
        admission_edit=None
        if args.capacity_admission_barrier:
            name='sim/cocotb/test_raw_grpc_enveloped.py';path=target/name
            original=path.read_bytes().decode();updated,replacements=capacity_admission_barrier_edits(original)
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            admission_edit=dict(path=name,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Complete backed initial capacity before original reset/held-wire probes; preserve every original assertion and packet')
        budget_edit=None
        if args.capacity_budget_expectations:
            name='sim/cocotb/test_raw_grpc_duplex.py';path=target/name;original=path.read_bytes().decode()
            replacements=[('assert b.client.outbound_flow_control_window == 65535',
                'assert b.client.outbound_flow_control_window == layout[14] // 128 * (layout[18] + 5)'),
                ('assert b.other.outbound_flow_control_window==65535',
                'assert b.other.outbound_flow_control_window==layout[14] // 128 * (layout[18] + 5)')]
            updated=original
            for before,after in replacements:
                assert updated.count(before)==1;updated=updated.replace(before,after)
            inverse=updated
            for before,after in reversed(replacements):
                assert inverse.count(after)==1;inverse=inverse.replace(after,before)
            assert inverse==original
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            budget_edit=dict(path=name,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Assert exact geometry-derived connection capacity after both real CLOSE refunds; preserve all original traffic and fault assertions')
        fault_barrier_edit=None
        if args.capacity_format_fault_barrier:
            name='sim/cocotb/test_raw_shutdown_faults.py';path=target/name;original=path.read_bytes().decode()
            updated,replacements=capacity_format_fault_barrier_edits(original)
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            fault_barrier_edit=dict(path=name,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Retire actual initial private capacity before fault arming for the separate FORMAT; preserve all original ledger ACK phases and assertions')
        snapshot_edit=None
        if args.capacity_retained_snapshots:
            name='sim/cocotb/test_raw_grpc_enveloped.py';path=target/name;original=path.read_bytes().decode()
            updated,replacements=capacity_retained_snapshot_edits(original)
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            snapshot_edit=dict(path=name,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Save both actual mutable memory banks at the original retained-reset observation points; no stimulus or assertion changes')
        shutdown_credit_edit=None
        if args.capacity_shutdown_credit_barrier:
            name='sim/cocotb/test_raw_shutdown_faults.py';path=target/name;original=path.read_bytes().decode()
            updated,replacements=capacity_shutdown_credit_barrier_edits(original)
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            shutdown_credit_edit=dict(path=name,old_sha256=baseline['inputs_sha256'][name],new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Retire and verify initial capacity frames before each of the original 41 shutdown faults and the final successful reset')
        extended_edit=None
        if args.capacity_extended_barrier:
            name=fixture_edit['path'];path=target/name;original=path.read_bytes().decode()
            updated,replacements=capacity_extended_barrier_edits(original,case)
            path.write_bytes(updated.encode());inputs[name]=sha(path)
            extended_edit=dict(path=name,old_sha256=hashlib.sha256(original.encode()).hexdigest(),new_sha256=inputs[name],
                replacements=replacements,exact_inverse_verified=True,
                purpose='Verify actual backed initial capacity before every original directed race/fault; all original assertions and packets preserved')
        link_top_edit=None;link_fixture_edit=None
        if args.capacity_fault_link_pause:
            for name,helper,label in [('sim/cocotb_two_fpga_enveloped_top.sv',capacity_fault_link_top_edits,'top'),
                (fixture_edit['path'],capacity_fault_link_fixture_edits,'fixture')]:
                path=target/name;original=path.read_bytes().decode();updated,replacements=helper(original)
                path.write_bytes(updated.encode());prior=inputs[name];inputs[name]=sha(path)
                edit=dict(path=name,old_sha256=prior,new_sha256=inputs[name],replacements=replacements,
                    exact_inverse_verified=True,purpose='Real inter-FPGA inverse UTF-8 backpressure holds GPU work until actual raw fault ACK; preserve all original packets and assertions')
                if label=='top':link_top_edit=edit
                else:link_fixture_edit=edit
        # Existing protocol stimulus, full images and native package sources
        # retain their original hashes; only Parser implementation is overlaid.
        for name,digest in baseline['inputs_sha256'].items():
            if not name.startswith('rtl/') and (not fixture_edit or name!=fixture_edit['path']) and (not ownership_edit or name!=ownership_edit['path']) and (not admission_edit or name!=admission_edit['path']) and (not budget_edit or name!=budget_edit['path']) and (not fault_barrier_edit or name!=fault_barrier_edit['path']) and (not snapshot_edit or name!=snapshot_edit['path']) and (not shutdown_credit_edit or name!=shutdown_credit_edit['path']) and (not link_top_edit or name!=link_top_edit['path']):assert inputs[name]==digest,name
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        (target/'protocol-runner-used.py').write_bytes(driver_source)
        shutil.copy2(candidate/'generation.json',target/'frame-event-buffer-generation.json')
        launch=root/'build/validation'/(run+'-launch.json')
        state=dict(phase='running',name=run,case=case,profile=baseline['profile'],baseline_audit_key=key,
            baseline_snapshot=baseline['snapshot'],target=str(target),archive=str(output),inputs_sha256=inputs,
            changed_rtl=changed,added_rtl=added,exact_parser_modules=parser_modules,exact_tokenizer_modules=22,
            generation_sha256=sha(candidate/'generation.json'),driver_sha256=hashlib.sha256(driver_source).hexdigest(),
            protocol_fixture_sources_unchanged=fixture_edit is None and ownership_edit is None,
            fixture_initialization_edit=fixture_edit,fixture_ownership_edit=ownership_edit,
            fixture_admission_edit=admission_edit,
            fixture_budget_edit=budget_edit,
            fixture_fault_barrier_edit=fault_barrier_edit,
            fixture_retained_snapshot_edit=snapshot_edit,
            fixture_shutdown_credit_edit=shutdown_credit_edit,
            fixture_extended_credit_edit=extended_edit,
            fixture_fault_link_top_edit=link_top_edit,fixture_fault_link_edit=link_fixture_edit,
            original_traffic_vectors_and_assertions_preserved=True,
            parser_variant=args.variant,candidate_variant=args.candidate,full_images_preserved=True,cocotb_version=cocotb.__version__,
            portable_memory_backend=True,native_timing_verified=False,full_system_complete=False,
            started_utc=datetime.now(timezone.utc).isoformat())
        def save():launch.write_text(json.dumps(state,indent=2)+'\n')
        save();print('Frozen buffered Parser full protocol case: '+case,flush=True)
        try:
            with (target/'driver.log').open('w') as stream:
                process=subprocess.Popen([sys.executable,str(target/'scripts/run_raw_envelope_tests.py'),'--execute','--profile',baseline['profile']],
                    cwd=target,stdout=stream,stderr=subprocess.STDOUT)
                state['launcher_pid']=process.pid;save();code=process.wait()
            assert all(sha(target/n)==h for n,h in inputs.items())
            output.mkdir(parents=True,exist_ok=False)
            for name,digest in inputs.items():
                destination=output/'execution-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
                if name=='build/bidirectional-fixtures/memory.mem':freeze_model_image(target/name,destination,root)
                else:shutil.copy2(target/name,destination)
                assert sha(destination)==digest
            for filename in ('report.json','acceptance.json','simulation.log','build.log','results.xml','progress.json','failure.json','receive_trace.json','window_trace.json',
                'retained_parser_mutable_epoch0.bin','retained_parser_mutable_epoch1.bin',
                'retained_tokenizer_mutable_epoch0.bin','retained_tokenizer_mutable_epoch1.bin'):
                path=target/'build/test'/filename
                if path.is_file():shutil.copy2(path,output/filename)
            path=target/'build/test/capacity_shutdown_admission_wires.json'
            if path.is_file():shutil.copy2(path,output/path.name)
            path=target/'build/test/capacity_extended_admission_wires.json'
            if path.is_file():shutil.copy2(path,output/path.name)
            for filename in ('inputs.json','driver.log','protocol-runner-used.py','frame-event-buffer-generation.json'):
                shutil.copy2(target/filename,output/filename)
            (output/'snapshot.json').write_text(json.dumps(dict(name=run,profile=baseline['profile'],exit_code=code,
                baseline_audit_key=key,baseline_snapshot=baseline['snapshot'],finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
            state.update(phase='completed' if code==0 else 'failed',exit_code=code)
            assert code==0,(case,'Full original protocol fixture failed; evidence preserved')
        except BaseException as error:state.update(phase='stopped_with_error',error=str(error));raise
        finally:state['finished_utc']=datetime.now(timezone.utc).isoformat();save()
        print(json.dumps(dict(case=case,phase=state['phase'],exit_code=code)),flush=True)


if __name__=='__main__':main()
