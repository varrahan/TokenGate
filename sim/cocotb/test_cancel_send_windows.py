"""Key-only send closure owns the actual pool, binding and durable close ACK."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_owned_windows import Bench,Memory
from test_http2_keyed_windows import prepare_search,keyed
from test_tokenizer_mmio import cycles

META=('window_rsp_binding_valid','window_rsp_record_address','window_rsp_generation','window_rsp_send_closed')


async def close_key(b,stream,*,status=0,retire=True,patch=None):
    fields={'req_generation':0,'req_record_address':0};fields.update(patch or {})
    result=await b.window(10,stream,0,status=status,retire=False,patch=fields)
    metadata=tuple(int(getattr(b.d,n).value)for n in META)
    if status==0:
        slot=(stream-1)//2;assert metadata==(1,b.addresses[stream],101+slot,1),metadata
    else:assert not metadata[0]and not metadata[3],metadata
    before=len(b.m.trace)
    for _ in range(11):await cycles(b.d);assert metadata==tuple(int(getattr(b.d,n).value)for n in META)and len(b.m.trace)==before
    if retire:
        await b.retire('window_rsp_ready')
        while int(b.d.window_busy.value):await cycles(b.d)
    return result,metadata


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def actual_key_close_binding_cached_lease_and_every_memory_fault(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);ref=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['original_image_sha256']
    m=Memory(d,image,ref['layout']);b=Bench(d,m,ref['layout'])
    b.set(rst=1,req_valid=0,rsp_ready=0,lease_valid=0,lease_rsp_ready=0,window_req_valid=0,window_rsp_ready=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run())
    await b.fresh();native_updates=0
    for case in ref['cases']:
        if case.get('open'):await b.directory(0,case['stream'])
        if case['op']==2:
            result=await keyed(b,case['stream'],case['amount'],status=case['status']);native_updates+=1
        else:result=await b.window(case['op'],case['stream'],case['amount'],status=case['status'])
        if not case.get('recovery'):
            for field,key in(('rsp_grant_bytes','grant'),('rsp_connection_window','connection_window'),('rsp_initial_window','initial_window'),
                ('rsp_stream_window','stream_window'),('rsp_max_frame_bytes','max_frame'),('rsp_affected_streams','affected')):
                assert result[field]==case[key]&0xffffffff,('Native compatibility',case,field,result)
    await prepare_search(b);foreign=bytes(m.data[b.a['stream_base']:b.a['stream_base']+128])
    grant=await b.window(5,1,7);assert grant['rsp_grant_bytes']==7
    await b.lease(1);cached=tuple(int(getattr(d,n).value)for n in('lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_address','lease_rsp_state'))
    before=m.count[1];result,metadata=await close_key(b,1,retire=False);phases=m.count[1]-before;assert phases==22
    assert result['rsp_connection_window']==result['rsp_stream_window']==65528 and result['rsp_grant_bytes']==0
    assert int(d.lease_rsp_valid.value)and cached==tuple(int(getattr(d,n).value)for n in('lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_address','lease_rsp_state'))
    opening=cocotb.start_soon(b.directory(0,5));await cycles(d,30)
    assert not int(d.req_ready.value)and int(d.directory_pool_lock_active.value)
    await b.retire('lease_rsp_ready');await cycles(d,5);assert not int(d.req_ready.value),'Cached retirement released the pool before close-result ACK'
    await b.retire('window_rsp_ready');await opening
    assert bytes(m.data[b.a['stream_base']:b.a['stream_base']+128])==foreign
    assert m.data[b.a['window_base']:b.a['window_base']+16]==bytes(16),'Foreign same-number stream was closed'
    start=len(m.trace);again,_=await close_key(b,1)
    assert not any(e['client']==1 and e['write']for e in m.trace[start:])and again['rsp_stream_window']==65528
    result=await b.window(5,1,100,status=8);assert result['rsp_http2_error']==5 and result['rsp_grant_bytes']==0
    result=await keyed(b,1,99);assert result['rsp_stream_window']==result['rsp_connection_window']==65528
    result,_=await close_key(b,127,status=3);assert result['rsp_detail']==10 and result['rsp_http2_error']==0 and not result['rsp_connection_error']
    negatives=0
    for stream,patch in((0,{}),(1,{'req_generation':101}),(1,{'req_record_address':b.addresses[1]}),(1,{'req_amount':1})):
        before=m.count[1];await close_key(b,stream,status=2,patch=patch);assert m.count[1]==before;negatives+=1
    old=b.addresses[1];await b.directory(3,1);await b.directory(0,7);assert b.addresses[7]==old
    await b.window(1,7);await close_key(b,1,status=3);assert not(int.from_bytes(m.data[b.a['window_base']+(old-b.a['stream_base'])//8:b.a['window_base']+(old-b.a['stream_base'])//8+16],'little')>>127)
    await close_key(b,7)
    faults=0;applied=0
    for phase in range(phases):
        await prepare_search(b);await b.lease(1);m.fail_client=1;m.fail_at=m.count[1]+phase
        result,metadata=await close_key(b,1,status=5,retire=False)
        assert result['rsp_memory_status']==0x75 and int(d.window_recovery_required.value)and int(d.directory_pool_lock_active.value)
        failed=[e for e in m.trace if e['client']==1 and e['status']][-1];assert int(d.window_recovery_address.value)==failed['address']
        if phase==phases-1:
            address=b.a['window_base']+(b.addresses[1]-b.a['stream_base'])//8
            assert m.data[address+15]&0x80 and not metadata[0];applied+=1
        await b.retire('window_rsp_ready')
        while int(d.window_busy.value):await cycles(d)
        m.fail_client=-1;before=m.count[1];await close_key(b,1,status=6);assert m.count[1]==before
        assert int(d.lease_rsp_valid.value);await b.retire('lease_rsp_ready');await b.window(7);faults+=1
    assert m.data[:b.a['work_floor']]==image[:b.a['work_floor']]and not any(m.pending)
    accepted=dict(phase='passed',window_commands=b.commands,key_close_memory_phases=phases,injected_close_memory_faults=faults,
        native_window_commands=len(ref['cases']),native_keyed_updates=native_updates,legacy_native_reference_matrix_verified=True,
        applied_close_with_failed_ack=applied,no_memory_binding_negatives=negatives,
        actual_directory_and_pool_verified=True,resolved_binding_after_durable_close=True,foreign_same_stream_untouched=True,
        cached_load_survives_key_close=True,pool_held_through_close_result=True,no_credit_refund=True,
        duplicate_close_idempotent=True,closed_reserve_has_no_grant=True,late_closed_update_ignored=True,
        missing_key_neutral=True,real_generation_reuse_verified=True,caller_binding_metadata_rejected=True,
        failed_close_never_publishes_binding=True,quarantined_exact_retry_has_no_memory=True,model_prefix_immutable=True,
        actual_rst_controller_integrated=False,inflight_wire_frame_drain_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
