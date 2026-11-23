"""Actual directory pool ownership, nonempty RPCs and read-only probe faults."""
import hashlib
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge,ReadOnly,Timer


def value(d,name):return int(getattr(d,name).value)


class Bench:
    def __init__(self,d):
        self.d=d;self.inputs={};self.clock=0
        self.memory=bytearray((i*29+7)&255 for i in range(4096));self.prefix=bytes(self.memory[:1024])
        self.pending=None;self.trace=[];self.probe_trace=[];self.fail_probe_at=None;self.fail_directory_next=False
        self.stall_requests=False;self.held_request=None;self.held_result=None;self.held_checks=0

    def set(self,**fields):self.inputs.update(fields)

    async def step(self):
        d=self.d;await FallingEdge(d.clk)
        for name,v in self.inputs.items():getattr(d,name).value=v
        ready=not self.stall_requests and self.pending is None and self.clock%7>=2 and not self.inputs.get('rst',0)
        if self.pending and self.pending['delay']>0:self.pending['delay']-=1
        response=self.pending if self.pending and self.pending['delay']==0 else None
        d.mem_ready.value=int(ready);d.mem_rsp_valid.value=int(response is not None)
        d.mem_rsp_data.value=response['data']if response else 0;d.mem_rsp_status.value=response['status']if response else 0
        await Timer(1,unit='ns')
        sample={n:value(d,n)for n in('probe_req_ready','probe_result_valid','probe_release_ready','probe_certificate_active','probe_admission_fence',
            'probe_recovery_required','probe_memory_owner','dir_req_ready','dir_rsp_valid','dir_lease_ready','dir_lease_rsp_valid',
            'dir_pool_lock_active','dir_pool_unlock_ready','mem_valid','mem_write','mem_addr','mem_bytes','mem_data','mem_rsp_ready')}
        sample['probe_result']=tuple(value(d,'probe_'+n)for n in('result_tag','result_status','result_empty','result_holding_requested','result_pool_base','result_pool_bytes','result_address','result_header','result_records_examined','result_lock_status','result_memory_status'))
        sample['dir_result']={n:value(d,'dir_rsp_'+n)for n in('status','detail','memory_status','address','generation')}
        sample['lease_status']=value(d,'dir_lease_rsp_status')
        sample['rsp_fire']=response is not None and bool(sample['mem_rsp_ready'])
        sample['req_fire']=bool(sample['mem_valid']and ready)
        offer=tuple(sample[n]for n in('mem_write','mem_addr','mem_bytes','mem_data'))
        if self.held_request is not None:assert sample['mem_valid']and offer==self.held_request,'Physical request changed before acceptance'
        self.held_request=offer if sample['mem_valid']and not ready else None
        if self.held_result is not None:assert sample['probe_result_valid']and sample['probe_result']==self.held_result,'Probe result changed under backpressure'
        self.held_result=sample['probe_result']if sample['probe_result_valid']and not self.inputs.get('probe_result_ready',0)else None
        if self.held_result is not None:self.held_checks+=1
        if sample['probe_memory_owner']:
            assert sample['dir_pool_lock_active']or sample['probe_recovery_required']or self.inputs.get('force_unlock',0)
            assert not value(d,'dir_mem_valid'),'Actual directory emitted memory during exclusive probe ownership'
        await RisingEdge(d.clk);self.clock+=1
        if sample['rsp_fire']:
            self.pending['entry']['ack_cycle']=self.clock;self.pending=None
        if sample['req_fire']:
            assert self.pending is None
            write,address,size,data=offer;assert size==8 and 0<=address<=len(self.memory)-8
            probe=bool(sample['probe_memory_owner'])
            if probe:assert not write and sample['dir_pool_lock_active']or probe and self.inputs.get('force_unlock',0)or probe and sample['probe_recovery_required']
            status=0
            if probe and self.fail_probe_at==len(self.probe_trace):status=0x61+len(self.probe_trace)
            if not probe and self.fail_directory_next:status=0x75;self.fail_directory_next=False
            if write:
                assert not probe and 1024<=address<1408
                self.memory[address:address+8]=(data&((1<<64)-1)).to_bytes(8,'little')
            entry=dict(probe=probe,write=write,address=address,size=size,data=data,cycle=self.clock,ack_cycle=None,status=status)
            self.trace.append(entry)
            if probe:self.probe_trace.append(entry)
            self.pending=dict(delay=2+self.clock%4,data=int.from_bytes(self.memory[address:address+8],'little'),status=status,entry=entry)
        await ReadOnly()
        return sample

    async def until(self,predicate,limit=10000):
        for _ in range(limit):
            sample=await self.step()
            if predicate(sample):return sample
        raise AssertionError('Bounded actual-pool operation did not complete')

    async def reset(self):
        assert self.pending is None
        self.set(rst=1,probe_req_valid=0,probe_result_ready=0,probe_release_valid=0,dir_req_valid=0,dir_rsp_ready=0,dir_lease_valid=0,dir_lease_rsp_ready=0,force_unlock=0)
        self.held_request=None;self.held_result=None
        for _ in range(4):await self.step()
        self.set(rst=0)
        for _ in range(3):await self.step()

    async def directory(self,op,**fields):
        defaults=dict(dir_cfg_pool_base=1024,dir_cfg_pool_bytes=384,dir_req_user=1,dir_req_application=2,
            dir_req_stream=1,dir_req_generation=0,dir_req_address=0,dir_req_buffer_base=2048,dir_req_buffer_bytes=128,
            dir_req_message_limit=128,dir_req_protobuf=1,dir_req_unsupported_encoding=0,dir_req_state=0,dir_req_maintenance=int(op==4))
        defaults.update({'dir_'+k:v for k,v in fields.items()});self.set(**defaults,dir_req_op=op,dir_req_valid=1,dir_rsp_ready=0)
        await self.until(lambda s:s['dir_req_ready'])
        self.set(dir_req_valid=0)
        sample=await self.until(lambda s:s['dir_rsp_valid']);result=sample['dir_result']
        self.set(dir_rsp_ready=1);await self.until(lambda s:s['dir_rsp_valid']);self.set(dir_rsp_ready=0)
        return result

    async def start_probe(self,tag=1,hold=False,scope=True,base=1024,size=384):
        self.probe_trace=[];self.set(probe_req_valid=1,probe_req_tag=tag,probe_req_hold_empty=int(hold),
            probe_req_scope_valid=int(scope),probe_req_pool_base=base,probe_req_pool_bytes=size,probe_result_ready=0)
        await self.until(lambda s:s['probe_req_ready']);self.set(probe_req_valid=0)

    async def result(self):
        sample=await self.until(lambda s:s['probe_result_valid'])
        keys=('tag','status','empty','hold','base','bytes','address','header','examined','lock_status','memory_status')
        result=dict(zip(keys,sample['probe_result']));result['offer_cycle']=self.clock
        for _ in range(19):
            held=await self.step();assert held['probe_result_valid']and held['probe_result']==sample['probe_result']
        return result

    async def ack_result(self):
        self.set(probe_result_ready=1);await self.until(lambda s:s['probe_result_valid']);self.set(probe_result_ready=0)


@cocotb.test()
async def actual_pool_lock_guards_the_read_only_absence_probe(d):
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());b=Bench(d);await b.reset();cases=[]
    # Nonzero malformed metadata must never be treated as absence.
    await b.start_probe(tag=10);r=await b.result();assert r['status']==5 and not r['empty']and r['examined']==1
    assert not value(d,'probe_admission_fence')and not value(d,'dir_pool_lock_active');cases.append(dict(case='malformed',result=r))
    await b.ack_result()
    assert (await b.directory(4))['status']==0
    await b.start_probe(tag=11,hold=True)
    # Poison live pins after acceptance; all physical addresses use the snapshot.
    b.set(probe_req_pool_base=0,probe_req_pool_bytes=1,probe_req_tag=999)
    r=await b.result();assert r['tag']==11 and r['status']==0 and r['empty']and r['hold']and r['examined']==3
    assert [x['address']for x in b.probe_trace]==[1024,1152,1280]and value(d,'probe_certificate_active')
    # A real OPEN must remain unaccepted while the actual pool lock is held.
    b.set(dir_req_valid=1,dir_req_op=0,dir_cfg_pool_base=1024,dir_cfg_pool_bytes=384,dir_req_user=1,
        dir_req_application=2,dir_req_stream=1,dir_req_buffer_base=2048,dir_req_buffer_bytes=128,dir_req_message_limit=128,
        dir_req_generation=0,dir_req_address=0,dir_req_state=0,dir_req_maintenance=0,dir_req_protobuf=1,dir_req_unsupported_encoding=0)
    for _ in range(17):
        s=await b.step();assert not s['dir_req_ready']and s['probe_certificate_active']
    await b.ack_result();b.set(probe_release_valid=1)
    await b.until(lambda s:s['probe_release_ready']);b.set(probe_release_valid=0)
    await b.until(lambda s:s['dir_req_ready']);b.set(dir_req_valid=0)
    s=await b.until(lambda s:s['dir_rsp_valid']);opened=s['dir_result'];assert opened['status']==0
    b.set(dir_rsp_ready=1);await b.until(lambda s:s['dir_rsp_valid']);b.set(dir_rsp_ready=0)
    cases.append(dict(case='empty_held_blocks_real_open',result=r,actual_open=opened))
    # BUSY unlocks before presenting its result, even if the host stalls it.
    await b.start_probe(tag=12,hold=True);r=await b.result()
    assert r['status']==2 and not r['empty']and r['examined']==1 and not value(d,'probe_certificate_active')
    assert not value(d,'dir_pool_lock_active')and not value(d,'probe_admission_fence')
    closed=await b.directory(3,req_address=opened['address'],req_generation=opened['generation']);assert closed['status']==0
    assert value(d,'probe_result_valid')and value(d,'probe_result_status')==2
    cases.append(dict(case='busy_result_does_not_block_actual_close',result=r,actual_close=closed));await b.ack_result()
    for fault in range(3):
        b.fail_probe_at=fault;await b.start_probe(tag=20+fault,hold=True);r=await b.result()
        assert r['status']==4 and not r['empty']and r['memory_status']==0x61+fault and r['examined']==fault
        assert r['address']==1024+128*fault and len(b.probe_trace)==fault+1
        assert all(x['ack_cycle']is not None and x['ack_cycle']<=r['offer_cycle']for x in b.probe_trace)
        assert not value(d,'dir_pool_lock_active')and not value(d,'probe_admission_fence')
        cases.append(dict(case='read_fault',position=fault,result=r,trace=list(b.probe_trace)));await b.ack_result()
    b.fail_probe_at=None
    for tag,scope,base,size in((30,False,1024,384),(31,True,1024,0),(32,True,1024,129),(33,True,0x7fff80,256)):
        await b.start_probe(tag=tag,scope=scope,base=base,size=size);r=await b.result()
        assert r['status']==1 and not r['empty']and not b.probe_trace
        cases.append(dict(case='invalid_scope_or_geometry',result=r));await b.ack_result()
    await b.start_probe(tag=40,hold=False);r=await b.result()
    assert r['status']==0 and r['empty']and not r['hold']and r['examined']==3
    assert not value(d,'probe_certificate_active')and not value(d,'dir_pool_lock_active')
    cases.append(dict(case='unlocked_snapshot_is_not_a_held_certificate',result=r));await b.ack_result()
    # Adversarially remove the REAL lock while a physical read offer is held.
    b.stall_requests=True;await b.start_probe(tag=50,hold=True)
    await b.until(lambda s:s['mem_valid']and s['probe_memory_owner'])
    b.set(force_unlock=1);await b.until(lambda s:s['dir_pool_unlock_ready']);b.set(force_unlock=0)
    for _ in range(17):
        s=await b.step();assert s['mem_valid']and not s['probe_result_valid']and not s['probe_certificate_active']
    b.stall_requests=False;r=await b.result()
    assert r['status']==6 and not r['empty']and value(d,'probe_recovery_required')
    assert len(b.probe_trace)==1 and b.probe_trace[0]['ack_cycle']is not None
    assert b.probe_trace[0]['ack_cycle']<=r['offer_cycle']and b.pending is None
    cases.append(dict(case='lost_real_lock_still_drains_accepted_read',result=r,trace=list(b.probe_trace)));await b.ack_result()
    for _ in range(8):
        s=await b.step();assert not s['probe_req_ready']and s['probe_admission_fence']
    assert bytes(b.memory[:1024])==b.prefix
    assert all(not x['write']for x in b.trace if x['probe'])
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',cases=cases,actual_shared_memory_trace=b.trace,
        actual_pool_guard_and_directory_and_memory_slot=True,component_only=True,full_application_integrated=False,
        protected_prefix_sha256=hashlib.sha256(b.prefix).hexdigest(),protected_prefix_unchanged=True,
        held_response_checks=b.held_checks,probe_never_writes=True,global_reload_authority_verified=False,
        retained_system_recovery_verified=False,full_system_complete=False),indent=2)+'\n')
