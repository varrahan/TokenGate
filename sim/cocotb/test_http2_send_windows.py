"""Native h2 window sequence and failure of every acknowledged memory phase.

The typed directory-authority contract is supplied by this component fixture.
It does not instantiate admission, a directory arbiter or a network controller.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_tokenizer_mmio import cycles


RESULTS=('rsp_status','rsp_detail','rsp_memory_status','rsp_connection_error','rsp_http2_error','rsp_grant_bytes',
    'rsp_connection_window','rsp_initial_window','rsp_stream_window','rsp_max_frame_bytes','rsp_affected_streams','rsp_op','rsp_user','rsp_stream')


class CommandMemory:
    def __init__(self,d,image,layout):
        self.d=d;self.data=bytearray(image);self.a=layout;self.trace=[];self.fail_at=-1;self.rng=random.Random(20261120);self.pending=None

    async def run(self):
        d=self.d;held=None
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert self.pending is None,'Reset abandoned an owned memory command'
                d.mem_ready.value=0;d.mem_rsp_valid.value=0;d.mem_rsp_data.value=0;d.mem_rsp_status.value=0;held=None
                continue
            d.mem_ready.value=self.pending is None and self.rng.randrange(4)!=0
            if self.pending is not None and self.pending['delay']>0:self.pending['delay']-=1
            valid=self.pending is not None and self.pending['delay']==0
            d.mem_rsp_valid.value=valid
            d.mem_rsp_data.value=self.pending['data']if valid else 0
            d.mem_rsp_status.value=self.pending['status']if valid else 0
            await RisingEdge(d.clk)
            if valid and int(d.mem_rsp_ready.value):
                self.pending['entry']['acked']=True;self.pending=None
            if int(d.mem_valid.value):
                item=tuple(int(getattr(d,n).value)for n in('mem_write','mem_addr','mem_bytes','mem_data'))
                if held is not None:assert item==held,'Memory command changed under backpressure'
                held=item if not int(d.mem_ready.value)else None
                if int(d.mem_ready.value):
                    write,address,size,data=item
                    assert self.pending is None and size==8 and address%8==0 and address+8<=len(self.data)
                    if write:
                        a=self.a;connection=(a['context_base']<=address<a['context_base']+a['context_bytes']and 168<=(address-a['context_base'])%256<=208)
                        window=a['window_base']<=address and address+8<=a['window_base']+a['window_bytes']
                        assert address>=a['work_floor']and(connection or window),('Illegal write ownership',hex(address))
                        self.data[address:address+8]=int(data&((1<<64)-1)).to_bytes(8,'little')
                    status=0x75 if len(self.trace)==self.fail_at else 0
                    entry=dict(write=write,address=address,data=data,status=status,acked=False);self.trace.append(entry)
                    self.pending=dict(data=int.from_bytes(self.data[address:address+8],'little'),status=status,delay=self.rng.randrange(1,8),entry=entry)
            else:assert held is None,'Memory request withdrawn while stalled'


class Bench:
    def __init__(self,d,memory,reference):self.d=d;self.m=memory;self.ref=reference;self.a=reference['layout'];self.commands=0

    def set(self,**fields):
        for name,value in fields.items():getattr(self.d,name).value=value

    async def wait(self,name):
        while not int(getattr(self.d,name).value):await FallingEdge(self.d.clk)

    def open_record(self,stream,slot=None,user=0):
        slot=(stream-1)//2 if slot is None else slot;a=self.a;generation=101+slot
        address=a['stream_base']+128*slot
        self.m.data[address:address+128]=bytes(128)
        struct.pack_into('<8I',self.m.data,address,0x47525331,1,user|(100+stream)<<16,stream,0x740000+slot*256,256,256,generation)
        return address,generation

    async def run(self,op,stream=0,amount=0,*,status=0,user=0,patch=None):
        d=self.d;a=self.a;slot=(stream-1)//2 if stream else 0
        fields=dict(req_op=op,req_authority=1,req_maintenance=int(op in(0,7)),req_user=user,req_stream=stream,
            req_generation=101+slot if stream else 0,req_record_address=a['stream_base']+128*slot if stream else 0,req_amount=amount,
            cfg_context_base=a['context_base'],cfg_context_bytes=a['context_bytes'],cfg_stream_base=a['stream_base'],
            cfg_stream_bytes=a['stream_bytes'],cfg_window_base=a['window_base'],cfg_window_bytes=a['window_bytes'],cfg_work_floor=a['work_floor'])
        fields.update(patch or {});self.set(**fields);start=len(self.m.trace)
        await FallingEdge(d.clk);d.req_valid.value=1
        while True:
            await RisingEdge(d.clk)
            if int(d.req_ready.value):break
        await FallingEdge(d.clk);self.set(req_valid=0,req_op=7,req_user=0xffff,req_stream=0x7fffffff,req_amount=0xffffffff,
            req_authority=0,req_maintenance=0,req_record_address=0x7fffff,cfg_context_base=0x7fffff,cfg_context_bytes=0,
            cfg_stream_base=0x7fffff,cfg_stream_bytes=0,cfg_window_base=0x7fffff,cfg_window_bytes=0,cfg_work_floor=0x7fffff)
        await self.wait('rsp_valid');result={n:int(getattr(d,n).value)for n in RESULTS}
        assert result['rsp_status']==status,('Window result',op,stream,result,status)
        assert (result['rsp_op'],result['rsp_user'],result['rsp_stream'])==(op,user,stream)
        assert all(x['acked']for x in self.m.trace[start:]),'Result escaped before memory acknowledgements'
        if op==5 and status==0:
            assert result['rsp_grant_bytes']>0 and sum(x['write']for x in self.m.trace[start:])==2
        else:assert result['rsp_grant_bytes']==0
        before=len(self.m.trace)
        for _ in range(7):
            await cycles(d);assert int(d.rsp_valid.value) and result=={n:int(getattr(d,n).value)for n in RESULTS}
            assert not int(d.req_ready.value) and len(self.m.trace)==before
        d.rsp_ready.value=1;await cycles(d);d.rsp_ready.value=0;self.commands+=1
        return result,len(self.m.trace)-start

    async def fresh(self,op):
        await cycles(self.d,3);assert self.m.pending is None
        self.d.rst.value=1;await cycles(self.d,5)
        a=self.a;self.m.data[a['context_base']:a['window_base']+a['window_bytes']]=bytes(a['window_base']+a['window_bytes']-a['context_base'])
        for user in range(3):struct.pack_into('<Q',self.m.data,a['context_base']+256*user,0x48324331|3<<32|16384<<40)
        self.m.fail_at=-1;self.d.rst.value=0;await cycles(self.d,2)
        if op!=0:await self.run(0)
        if op!=0:
            for stream in((1,3,5)if op==3 else(1,)):
                self.open_record(stream)
                if op!=1:await self.run(1,stream)


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def native_signed_windows_and_every_memory_failure(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert reference['phase']=='native_send_window_references_passed' and hashlib.sha256(image).hexdigest()==reference['original_image_sha256']
    memory=CommandMemory(d,image,reference['layout']);bench=Bench(d,memory,reference)
    bench.set(rst=1,req_valid=0,rsp_ready=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    await bench.fresh(0)
    for case in reference['cases']:
        if case.get('open'):bench.open_record(case['stream'])
        result,_=await bench.run(case['op'],case['stream'],case['amount'],status=case['status'])
        if case.get('recovery'):
            assert int(d.recovery_required.value) and result['rsp_http2_error']==3 and result['rsp_connection_error']==1
            assert result['rsp_affected_streams']==case['affected']==2
        else:
            for output,key in(('rsp_grant_bytes','grant'),('rsp_connection_window','connection_window'),('rsp_initial_window','initial_window'),
                ('rsp_stream_window','stream_window'),('rsp_max_frame_bytes','max_frame'),('rsp_affected_streams','affected')):
                assert result[output]==case[key]&0xffffffff,('Native h2 mismatch',case,output,result)
    negatives=0
    await bench.fresh(5)
    for op,stream,amount,status,patch,no_memory in(
        (6,1,0,3,{'req_generation':999},False),(6,1,0,2,{'req_record_address':0x710007},True),
        (2,1,0,4,{},True),(2,0,0,4,{},True),(2,1,0x80000000,4,{},True),
        (1,1,0,3,{},False),(0,0,0,7,{'req_maintenance':0},True),
        (6,0,0,7,{'req_authority':0},True),(6,0,0,2,{'cfg_window_base':0x710000},True),
        (6,0,0,2,{'cfg_window_base':0x100},True),(6,0,0,2,{'cfg_window_bytes':16},True)):
        _,count=await bench.run(op,stream,amount,status=status,patch=patch)
        if no_memory:assert count==0
        negatives+=1
    faults=0;phase_counts={}
    for op,stream,amount in((0,0,0),(1,1,0),(5,1,100),(3,0,1000)):
        await bench.fresh(op);_,count=await bench.run(op,stream,amount);phase_counts[str(op)]=count
        for index in range(count):
            await bench.fresh(op);memory.fail_at=len(memory.trace)+index
            result,_=await bench.run(op,stream,amount,status=5)
            assert result['rsp_memory_status']==0x75 and int(d.recovery_required.value)
            _,issued=await bench.run(6,user=2,status=6);assert issued==0
            await bench.run(7);assert not int(d.recovery_required.value)
            faults+=1
    assert memory.data[:reference['layout']['work_floor']]==image[:reference['layout']['work_floor']]
    result=dict(phase='passed',native_commands=len(reference['cases']),negative_commands=negatives,injected_memory_faults=faults,
        memory_phase_counts=phase_counts,total_commands=bench.commands,total_memory_commands=len(memory.trace),
        full_model_bytes=len(image),model_prefix_immutable=True,both_debits_before_grant_verified=True,
        signed_negative_windows_verified=True,all_live_stream_settings_scan_verified=True,
        typed_authority_supplied_by_fixture=True,actual_directory_admission_integrated=False,
        actual_network_control_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n');d._log.info('PASS: %s',result)
