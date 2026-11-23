"""Real directory allocation, cached leases and pool-owned window commands."""
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
from test_http2_send_windows import RESULTS


class Memory:
    def __init__(self,d,image,a):
        self.d=d;self.data=bytearray(image);self.a=a;self.pending=[None,None];self.trace=[];self.rng=random.Random(20261124)
        self.fail_client=-1;self.fail_at=-1;self.count=[0,0];self.clocks=0;self.blocked=0

    async def run(self):
        d=self.d;held=[None,None]
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert not any(self.pending),'Reset abandoned memory ownership'
                d.mem_ready.value=0;d.mem_rsp_valid.value=0;d.mem_rsp_data.value=0;d.mem_rsp_status.value=0;held=[None,None];continue
            ready=valid=data=status=0
            for client in range(2):
                p=self.pending[client]
                if p and p['delay']>0:p['delay']-=1
                if p and p['delay']==0:
                    valid|=1<<client;data|=p['data']<<(72*client);status|=p['status']<<(8*client)
                if p is None and self.rng.randrange(4)!=0:ready|=1<<client
            d.mem_ready.value=ready;d.mem_rsp_valid.value=valid;d.mem_rsp_data.value=data;d.mem_rsp_status.value=status
            await RisingEdge(d.clk);self.clocks+=1
            active=int(d.directory_pool_lock_active.value)
            if active:
                assert not int(d.req_ready.value)and not int(d.lease_ready.value)
                assert not(int(d.mem_valid.value)&1),'Directory issued memory during exclusive pool ownership'
                if int(d.req_valid.value)or int(d.lease_valid.value):self.blocked+=1
            for client in range(2):
                if valid>>client&1 and int(d.mem_rsp_ready.value)>>client&1:
                    self.pending[client]['entry']['ack_cycle']=self.clocks;self.pending[client]=None
                if int(d.mem_valid.value)>>client&1:
                    item=(int(d.mem_write.value)>>client&1,int(d.mem_addr.value)>>(23*client)&0x7fffff,
                        int(d.mem_bytes.value)>>(4*client)&15,int(d.mem_data.value)>>(72*client)&((1<<72)-1))
                    if held[client] is not None:assert item==held[client]
                    held[client]=item if not(ready>>client&1)else None
                    if ready>>client&1:
                        write,address,size,value=item;assert self.pending[client]is None and size==8 and address+8<=len(self.data)
                        if client==1:assert active,'Window access escaped actual pool ownership'
                        if write:
                            a=self.a
                            allowed=(a['stream_base']<=address and address+8<=a['stream_base']+a['stream_bytes']and(address-a['stream_base'])%128<64)if client==0 else(
                                a['context_base']<=address<a['context_base']+a['context_bytes']and 168<=(address-a['context_base'])%256<=208 or
                                a['window_base']<=address and address+8<=a['window_base']+a['window_bytes'])
                            assert allowed and address>=a['work_floor'],('Write ownership',client,hex(address))
                            self.data[address:address+8]=(value&((1<<64)-1)).to_bytes(8,'little')
                        failed=client==self.fail_client and self.count[client]==self.fail_at
                        entry=dict(client=client,write=write,address=address,cycle=self.clocks,ack_cycle=None,status=0x75 if failed else 0)
                        self.trace.append(entry);self.count[client]+=1
                        self.pending[client]=dict(delay=self.rng.randrange(2,12),data=int.from_bytes(self.data[address:address+8],'little'),status=entry['status'],entry=entry)
                else:assert held[client]is None


class Bench:
    def __init__(self,d,m,a):self.d=d;self.m=m;self.a=a;self.commands=0;self.addresses={}

    def set(self,**fields):
        for n,v in fields.items():getattr(self.d,n).value=v

    async def wait(self,name):
        while not int(getattr(self.d,name).value):await FallingEdge(self.d.clk)

    async def send(self,valid,ready):
        await FallingEdge(self.d.clk);getattr(self.d,valid).value=1
        while True:
            await RisingEdge(self.d.clk)
            if int(getattr(self.d,ready).value):break
        await FallingEdge(self.d.clk);getattr(self.d,valid).value=0

    async def retire(self,ready):
        getattr(self.d,ready).value=1;await cycles(self.d);getattr(self.d,ready).value=0

    async def directory(self,op,stream=0,*,retire=True,status=0):
        a=self.a;slot=(stream-1)//2 if stream else 0
        self.set(cfg_pool_base=a['stream_base'],cfg_pool_bytes=a['stream_bytes'],req_op=op,req_user=0,req_application=100+stream,
            req_stream=stream,req_generation=101+slot if stream else 0,req_address=self.addresses.get(stream,0),
            req_buffer_base=0x740000+slot*256,req_buffer_bytes=256,req_message_limit=256,
            req_protobuf=0,req_unsupported_encoding=0,req_maintenance=int(op in(4,5)),req_state=0)
        await self.send('req_valid','req_ready');await self.wait('rsp_valid')
        assert int(self.d.rsp_status.value)==status,('Directory',op,stream,int(self.d.rsp_status.value))
        if op==0 and status==0:self.addresses[stream]=int(self.d.rsp_address.value)
        if retire:await self.retire('rsp_ready')

    async def lease(self,stream):
        self.set(lease_user=0,lease_stream=stream,lease_pool_base=self.a['stream_base'],lease_pool_bytes=self.a['stream_bytes'])
        await self.send('lease_valid','lease_ready');await self.wait('lease_rsp_valid')
        assert int(self.d.lease_rsp_status.value)==0 and int(self.d.lease_rsp_address.value)==self.addresses[stream]

    async def window(self,op,stream=0,amount=0,*,status=0,patch=None,retire=True):
        a=self.a;slot=(stream-1)//2 if stream else 0
        fields=dict(req_op=op,req_maintenance=int(op in(0,7)),req_user=0,req_stream=stream,req_generation=101+slot if stream else 0,
            req_record_address=self.addresses.get(stream,0),req_amount=amount,
            cfg_context_base=a['context_base'],cfg_context_bytes=a['context_bytes'],cfg_stream_base=a['stream_base'],cfg_stream_bytes=a['stream_bytes'],
            cfg_window_base=a['window_base'],cfg_window_bytes=a['window_bytes'],cfg_work_floor=a['work_floor'])
        fields.update(patch or {});self.set(**{'window_'+n:v for n,v in fields.items()})
        start=len(self.m.trace);await self.send('window_req_valid','window_req_ready')
        self.set(window_req_op=7,window_req_stream=0x7fffffff,window_req_amount=0xffffffff,
            window_cfg_stream_base=0x7fffff,window_cfg_stream_bytes=0,window_cfg_window_base=0x7fffff,window_cfg_window_bytes=0)
        await self.wait('window_rsp_valid')
        result={n:int(getattr(self.d,'window_'+n).value)for n in RESULTS}
        assert result['rsp_status']==status,(op,stream,result,status)
        assert(result['rsp_op'],result['rsp_user'],result['rsp_stream'])==(op,0,stream)
        owned=status!=7
        assert bool(int(self.d.directory_pool_lock_active.value))==owned
        if op==5 and status==0:
            writes=[e for e in self.m.trace[start:]if e['client']==1 and e['write']]
            assert len(writes)==2 and all(e['ack_cycle']is not None for e in writes)
            assert result['rsp_grant_bytes']>0
        else:assert result['rsp_grant_bytes']==0
        for _ in range(9):
            await cycles(self.d);assert int(self.d.window_rsp_valid.value)
            assert result=={n:int(getattr(self.d,'window_'+n).value)for n in RESULTS}
            assert bool(int(self.d.directory_pool_lock_active.value))==owned
        if retire:
            await self.retire('window_rsp_ready')
            while int(self.d.window_busy.value):await cycles(self.d)
        self.commands+=1;return result

    async def fresh(self):
        await cycles(self.d,3);assert not any(self.m.pending)
        self.set(rst=1,req_valid=0,rsp_ready=0,lease_valid=0,lease_rsp_ready=0,window_req_valid=0,window_rsp_ready=0)
        await cycles(self.d,5);a=self.a
        self.m.data[a['context_base']:a['window_base']+a['window_bytes']]=bytes(a['window_base']+a['window_bytes']-a['context_base'])
        for user in range(3):struct.pack_into('<Q',self.m.data,a['context_base']+256*user,0x48324331|3<<32|16384<<40)
        self.m.fail_client=-1;self.addresses={};self.set(rst=0);await cycles(self.d,2)
        await self.directory(4)


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def actual_directory_authority_and_owned_window_progress(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);reference=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==reference['original_image_sha256']
    memory=Memory(d,image,reference['layout']);b=Bench(d,memory,reference['layout'])
    b.set(rst=1,req_valid=0,rsp_ready=0,lease_valid=0,lease_rsp_ready=0,window_req_valid=0,window_rsp_ready=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run());await b.fresh()
    for case in reference['cases']:
        if case.get('open'):await b.directory(0,case['stream'])
        result=await b.window(case['op'],case['stream'],case['amount'],status=case['status'])
        if not case.get('recovery'):
            for output,key in(('rsp_grant_bytes','grant'),('rsp_connection_window','connection_window'),('rsp_initial_window','initial_window'),
                ('rsp_stream_window','stream_window'),('rsp_max_frame_bytes','max_frame'),('rsp_affected_streams','affected')):
                assert result[output]==case[key]&0xffffffff,('Native h2',case,output,result)
    await b.fresh();await b.window(0)
    for stream in(1,3,5):await b.directory(0,stream);await b.window(1,stream)
    await b.lease(1)
    lease_fields=('lease_rsp_status','lease_rsp_address','lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_application','lease_rsp_state')
    cached=tuple(int(getattr(d,n).value)for n in lease_fields)
    save=cocotb.start_soon(b.directory(2,3,retire=False))
    while not(int(d.mem_valid.value)&1 and int(d.mem_write.value)&1):await FallingEdge(d.clk)
    start=len(memory.trace);await b.window(5,1,100,retire=False);await save
    window_trace=[e for e in memory.trace[start:]if e['client']==1]
    directory_trace=[e for e in memory.trace[start:]if e['client']==0]
    assert window_trace and directory_trace and max(e['ack_cycle']for e in directory_trace)<min(e['cycle']for e in window_trace)
    assert int(d.rsp_valid.value)and tuple(int(getattr(d,n).value)for n in lease_fields)==cached
    b.set(req_op=0,req_stream=7,req_generation=104,req_address=0,req_application=107,req_buffer_base=0x740300,req_buffer_bytes=256,
        req_message_limit=256,req_state=0,req_maintenance=0,req_valid=1,lease_stream=3,lease_valid=1)
    await b.retire('rsp_ready');await b.retire('lease_rsp_ready')
    before=len(memory.trace)
    for _ in range(40):
        await cycles(d);assert not int(d.req_ready.value)and not int(d.lease_ready.value)and int(d.directory_pool_lock_active.value)
        assert len(memory.trace)==before
    async def finish_present(valid,ready):
        while True:
            await RisingEdge(d.clk)
            if int(getattr(d,ready).value):break
        await FallingEdge(d.clk);getattr(d,valid).value=0
    generic=cocotb.start_soon(finish_present('req_valid','req_ready'));lease=cocotb.start_soon(finish_present('lease_valid','lease_ready'))
    await b.retire('window_rsp_ready');await generic;await lease
    await b.wait('rsp_valid');await b.wait('lease_rsp_valid')
    assert int(d.rsp_status.value)==int(d.lease_rsp_status.value)==0
    await b.retire('rsp_ready');await b.retire('lease_rsp_ready')
    await b.lease(1)
    for patch,reason in(({'cfg_stream_bytes':1},1),({'cfg_stream_base':0x711000},2)):
        before=memory.count[1];await b.window(6,status=7,patch=patch)
        assert int(d.window_lock_status.value)==reason and memory.count[1]==before
    # A failed physical CLOSE leaves the real backend quarantined; the wrapper
    # must refuse to manufacture window authority from backend idle alone.
    memory.fail_client=0;memory.fail_at=memory.count[0]+8
    await b.directory(3,3,status=5);assert int(d.recovery_required.value)
    before=memory.count[1];await b.window(6,status=7)
    assert int(d.window_lock_status.value)==3 and memory.count[1]==before
    memory.fail_client=-1;await b.directory(5,3);assert not int(d.recovery_required.value)
    await b.window(6)
    memory.fail_client=1;memory.fail_at=memory.count[1]+13
    result=await b.window(5,1,100,status=5,retire=False)
    assert result['rsp_grant_bytes']==0 and int(d.window_recovery_required.value)and int(d.directory_pool_lock_active.value)
    await b.retire('window_rsp_ready')
    while int(d.window_busy.value):await cycles(d)
    memory.fail_client=-1;await b.window(7);assert not int(d.window_recovery_required.value)
    await b.retire('lease_rsp_ready');await cycles(d,4)
    assert int(d.idle.value)and not any(memory.pending)
    assert memory.data[:b.a['work_floor']]==image[:b.a['work_floor']]
    result=dict(phase='passed',native_window_commands=len(reference['cases']),window_commands=b.commands,
        actual_directory_allocation_verified=True,actual_pool_authority_verified=True,
        backend_drained_before_window_access=True,cached_results_survive_pool_lock=True,
        frontend_blocked_cycles=memory.blocked,pool_configuration_rejections=2,backend_quarantine_rejections=1,
        uncertain_window_debit_withheld=True,model_prefix_immutable=True,
        actual_raw_control_integrated=False,actual_framer_grants_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n');d._log.info('PASS: %s',result)
