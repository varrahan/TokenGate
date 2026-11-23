"""Actual history reads, native h2 classifications, corruption and fence losses."""
import hashlib
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from test_tokenizer_mmio import cycles

FIELDS=('rsp_status','rsp_detail','rsp_memory_status','rsp_user','rsp_stream','rsp_closed','rsp_last_stream')


class Memory:
    def __init__(self,d,image,a):self.d=d;self.data=bytearray(image);self.a=a;self.pending=None;self.trace=[];self.fail=-1;self.clock=0;self.rng=random.Random(20261203)
    async def run(self):
        d=self.d;held=None
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert self.pending is None;d.mem_ready.value=0;d.mem_rsp_valid.value=0;d.mem_rsp_data.value=0;d.mem_rsp_status.value=0;held=None;continue
            ready=self.pending is None and self.rng.randrange(4)!=0
            if self.pending and self.pending['delay']:self.pending['delay']-=1
            valid=self.pending is not None and not self.pending['delay'];d.mem_ready.value=ready;d.mem_rsp_valid.value=valid
            d.mem_rsp_data.value=self.pending['data']if valid else 0;d.mem_rsp_status.value=self.pending['entry']['status']if valid else 0
            await RisingEdge(d.clk);self.clock+=1
            if valid and int(d.mem_rsp_ready.value):self.pending['entry']['ack']=self.clock;self.pending=None
            if int(d.mem_valid.value):
                item=tuple(int(getattr(d,n).value)for n in('mem_write','mem_addr','mem_bytes','mem_data'))
                if held is not None:assert held==item
                held=item if not ready else None
                if ready:
                    write,address,size,data=item;assert self.pending is None and write==0 and size==8 and data==0
                    assert self.a['context_base']<=address and address+8<=self.a['context_base']+self.a['context_bytes']and(address-self.a['context_base'])%256 in(0,160)
                    entry=dict(address=address,status=0x75 if len(self.trace)==self.fail else 0,ack=None);self.trace.append(entry)
                    self.pending=dict(entry=entry,data=int.from_bytes(self.data[address:address+8],'little'),delay=self.rng.randrange(3,12))
            else:assert held is None


class Bench:
    def __init__(self,d,m,a):self.d=d;self.m=m;self.a=a;self.commands=0
    def set(self,**fields):
        for n,v in fields.items():getattr(self.d,n).value=v
    async def wait(self,n):
        for _ in range(1000):
            if int(getattr(self.d,n).value):return
            await FallingEdge(self.d.clk)
        raise AssertionError('Timeout '+n)
    def history(self,highest,user=0):
        address=self.a['context_base']+256*user
        struct.pack_into('<Q',self.m.data,address,0x48324331|3<<32|16384<<40)
        struct.pack_into('<Q',self.m.data,address+160,0x48325731|highest<<32)
    async def request(self,stream,*,user=0,patch=None):
        a=self.a;fields=dict(req_stream=stream,req_user=user,req_missing_key=1,history_fence=1,cfg_context_base=a['context_base'],cfg_context_bytes=a['context_bytes'],cfg_work_floor=a['work_floor'])
        fields.update(patch or {});self.set(**fields);await FallingEdge(self.d.clk);self.d.req_valid.value=1
        while True:
            await RisingEdge(self.d.clk)
            if int(self.d.req_ready.value):break
        await FallingEdge(self.d.clk);self.set(req_valid=0,req_stream=0x7fffffff,req_user=65535,req_missing_key=0,
            cfg_context_base=0x7fffff,cfg_context_bytes=0,cfg_work_floor=0x7fffff)
    async def result(self,status=0):
        d=self.d;await self.wait('rsp_valid');r={n:int(getattr(d,n).value)for n in FIELDS};assert r['rsp_status']==status,r
        assert all(e['ack']is not None for e in self.m.trace)
        before=len(self.m.trace)
        for _ in range(9):await cycles(d);assert int(d.rsp_valid.value)and r=={n:int(getattr(d,n).value)for n in FIELDS}and len(self.m.trace)==before
        d.rsp_ready.value=1;await cycles(d);d.rsp_ready.value=0;self.commands+=1;return r
    async def run(self,stream,*,status=0,**args):await self.request(stream,**args);return await self.result(status)


@cocotb.test()
async def native_missing_key_classification_uses_fenced_actual_history(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);reference=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==reference['original_image_sha256']
    a=dict(reference['layout']);a['context_base']+=3
    cases=json.loads((folder.parent/'http2-classifier-fixtures/cases.json').read_text());assert cases['phase']=='native_missing_stream_references_passed'
    m=Memory(d,image,a);b=Bench(d,m,a);b.set(rst=1,req_valid=0,rsp_ready=0,history_fence=0,mem_ready=0,mem_rsp_valid=0,mem_rsp_data=0,mem_rsp_status=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());await cycles(d,5);d.rst.value=0
    for index,c in enumerate(cases['cases']):
        user=index%3;b.history(c['last_stream'],user);before=len(m.trace);r=await b.run(c['stream'],user=user)
        assert r['rsp_closed']==c['closed']and r['rsp_last_stream']==c['last_stream']and(r['rsp_user'],r['rsp_stream'])==(user,c['stream'])and len(m.trace)==before+2
    negative=0
    for patch,status in(({'cfg_context_bytes':255},2),({'cfg_context_base':0x7fffff},2),({'cfg_context_base':0},2),
        ({'req_user':65535},2),({'req_missing_key':0},7),({'history_fence':0},7)):
        before=len(m.trace);await b.run(1,status=status,patch=patch);assert len(m.trace)==before;negative+=1
    before=len(m.trace);await b.run(0,status=4);assert len(m.trace)==before;negative+=1
    corruptions=0
    for offset,mask in((0,1),(4,1),(4,0x10),(6,0x40),(160,1),(167,0x80),(164,1)):
        b.history(5);m.data[a['context_base']+offset]^=mask;r=await b.run(1,status=3);assert not r['rsp_closed'];corruptions+=1
    b.history(5);m.data[a['context_base']+4]^=2;await b.run(1,status=3);corruptions+=1
    faults=0
    for phase in range(2):
        b.history(5);m.fail=len(m.trace)+phase;r=await b.run(1,status=5);assert r['rsp_memory_status']==0x75 and not r['rsp_closed'];m.fail=-1;faults+=1
        assert(await b.run(1))['rsp_closed']
    fence_losses=0
    for phase in range(2):
        b.history(5);start=len(m.trace);task=cocotb.start_soon(b.run(1,status=7))
        while len(m.trace)<start+phase+1:await FallingEdge(d.clk)
        b.set(history_fence=0);await cycles(d,2);b.set(history_fence=1);r=await task;assert not r['rsp_closed'];fence_losses+=1
    assert m.data[:a['work_floor']]==image[:a['work_floor']]and m.pending is None
    accepted=dict(phase='passed',commands=b.commands,native_h2_cases=len(cases['cases']),negative_no_memory_commands=negative,
        corrupt_history_and_context_rejections=corruptions,injected_memory_faults=faults,lost_live_fences=fence_losses,
        actual_context_and_admission_history_read=True,skipped_and_closed_ids_ignored=True,idle_and_wrong_parity_ids_distinguished=True,
        captured_configuration_poisoned=True,all_reads_acknowledged_before_result=True,read_only_no_memory_writes=True,
        unaligned_runtime_context_supported=True,complete_model_prefix_immutable=True,
        server_initiated_streams_absent=True,actual_parent_fence_supplied_by_fixture=True,raw_parser_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
