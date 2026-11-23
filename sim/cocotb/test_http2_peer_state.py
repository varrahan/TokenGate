"""Durable peer parameters, actual wire tracking and every memory fault phase."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame,SettingsFrame,PingFrame
from test_tokenizer_mmio import cycles

PEER=0x770005
RESULTS=('rsp_status','rsp_detail','rsp_memory_status','rsp_connection_error','rsp_http2_error','rsp_op','rsp_user',
    'rsp_wire_retired','rsp_ack_matched','rsp_header_table_size','rsp_max_concurrent_streams','rsp_max_header_list_size',
    'rsp_enable_push','rsp_ping_pending','rsp_settings_pending','rsp_settings_acks','rsp_ping_acks','rsp_ping_payload')


class Memory:
    def __init__(self,d,image,a):
        self.d=d;self.data=bytearray(image);self.a=a;self.trace=[];self.pending=None;self.fail=-1
        self.rng=random.Random(20261130);self.clock=0

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
                    write,address,size,data=item;assert self.pending is None and size==8 and address+8<=len(self.data)
                    a=self.a;context=a['context_base']<=address and address+8<=a['context_base']+a['context_bytes']
                    peer=PEER<=address and address+8<=PEER+192
                    assert peer or context and (address-a['context_base'])%256==0,(write,hex(address))
                    if write:
                        assert peer and address>=a['work_floor'];self.data[address:address+8]=(data&((1<<64)-1)).to_bytes(8,'little')
                    entry=dict(write=write,address=address,data=data,status=0x75 if len(self.trace)==self.fail else 0,ack=None)
                    self.trace.append(entry);self.pending=dict(entry=entry,data=int.from_bytes(self.data[address:address+8],'little'),delay=self.rng.randrange(2,10))
            else:assert held is None


class Bench:
    def __init__(self,d,m,a):self.d=d;self.m=m;self.a=a;self.tx=[];self.tx_stalls=0;self.commands=0;self.force_stall=False
    def set(self,**fields):
        for n,v in fields.items():getattr(self.d,n).value=v
    async def wait(self,n):
        for _ in range(10000):
            if int(getattr(self.d,n).value):return
            await FallingEdge(self.d.clk)
        raise AssertionError('Timeout '+n)
    async def request(self,op,*,user=0,setting=0,value=0,payload=0,patch=None):
        a=self.a;fields=dict(req_op=op,req_user=user,req_authority=1,req_maintenance=int(op==0),req_setting=setting,req_value=value,
            req_payload=payload,cfg_context_base=a['context_base'],cfg_context_bytes=a['context_bytes'],cfg_peer_base=PEER,cfg_peer_bytes=192,cfg_work_floor=a['work_floor'])
        fields.update(patch or {});self.set(**fields)
        await FallingEdge(self.d.clk);self.d.req_valid.value=1
        while True:
            await RisingEdge(self.d.clk)
            if int(self.d.req_ready.value):break
        await FallingEdge(self.d.clk);self.set(req_valid=0,req_op=15,req_user=65535,req_setting=65535,req_value=0xffffffff,req_payload=0xffffffffffffffff,
            req_authority=0,req_maintenance=0,cfg_context_base=0x7fffff,cfg_context_bytes=0,cfg_peer_base=0x7fffff,cfg_peer_bytes=0,cfg_work_floor=0x7fffff)
    async def result(self,status=0):
        d=self.d;await self.wait('rsp_valid');r={n:int(getattr(d,n).value)for n in RESULTS};assert r['rsp_status']==status,r
        assert all(e['ack']is not None for e in self.m.trace)
        before=len(self.m.trace)
        for _ in range(7):
            await cycles(d);assert int(d.rsp_valid.value)and r=={n:int(getattr(d,n).value)for n in RESULTS}
            assert not int(d.req_ready.value)and len(self.m.trace)==before
        d.rsp_ready.value=1;await cycles(d);d.rsp_ready.value=0;self.commands+=1;return r
    async def run(self,op,*,status=0,**args):
        await self.request(op,**args);return await self.result(status)
    async def fresh(self,client=False):
        await cycles(self.d,3);assert self.m.pending is None
        self.d.rst.value=1;await cycles(self.d,5);self.m.fail=-1;self.force_stall=False
        self.m.data[PEER:PEER+192]=bytes(192)
        for user in range(3):struct.pack_into('<Q',self.m.data,self.a['context_base']+256*user,0x48324331|(1 if client else 3)<<32|16384<<40)
        self.d.rst.value=0;await cycles(self.d,2)
    async def tx_driver(self):
        rng=random.Random(20261201);held=None
        while True:
            await FallingEdge(self.d.clk);self.d.m_axis_tx_tready.value=not int(self.d.rst.value)and not self.force_stall and rng.randrange(5)==0
            await RisingEdge(self.d.clk)
            if int(self.d.rst.value):held=None;continue
            valid=int(self.d.m_axis_tx_tvalid.value)
            snap=tuple(int(getattr(self.d,'m_axis_tx_'+n).value)for n in('tdata','tkeep','tlast','tuser'))if valid else None
            if held is not None:assert snap==held
            held=snap if valid and not int(self.d.m_axis_tx_tready.value)else None
            if valid and not int(self.d.m_axis_tx_tready.value):self.tx_stalls+=1
            if valid and int(self.d.m_axis_tx_tready.value):
                data,keep,last,user=snap;assert last and keep in(0x1ff,0x1ffff)
                wire=data.to_bytes(64,'little')[:keep.bit_count()];frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
                assert frame.serialize()==wire and size+9==len(wire)and not frame.flags
                self.tx.append((user,wire,self.m.clock))


@cocotb.test()
async def durable_peer_parameters_wire_requests_and_all_commit_faults(d):
    root=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);reference=json.loads((root/'cases.json').read_text());image=(root/'model.bin').read_bytes();a=reference['layout']
    assert hashlib.sha256(image).hexdigest()==reference['original_image_sha256']
    m=Memory(d,image,a);b=Bench(d,m,a);b.set(rst=1,req_valid=0,rsp_ready=0,m_axis_tx_tready=0,mem_ready=0,mem_rsp_valid=0,mem_rsp_data=0,mem_rsp_status=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());cocotb.start_soon(b.tx_driver())
    await b.fresh();r=await b.run(0);assert r['rsp_header_table_size']==4096 and r['rsp_max_concurrent_streams']==r['rsp_max_header_list_size']==0xffffffff and r['rsp_enable_push']==1
    for key,amount in((1,0),(1,0xffffffff),(2,0),(2,1),(3,0),(3,0xffffffff),(6,0),(6,0xffffffff)):
        r=await b.run(4,setting=key,value=amount)
        field={1:'rsp_header_table_size',2:'rsp_enable_push',3:'rsp_max_concurrent_streams',6:'rsp_max_header_list_size'}[key];assert r[field]==amount
    before=bytes(m.data[PEER:PEER+64]);start=len(m.trace);await b.run(4,setting=65000,value=42)
    assert before==bytes(m.data[PEER:PEER+64])and len(m.trace)-start==9
    r=await b.run(4,setting=2,value=2,status=4);assert r['rsp_connection_error']and r['rsp_http2_error']==1 and before==bytes(m.data[PEER:PEER+64])
    for key in(4,5):await b.run(4,setting=key,value=65535,status=9)
    # Another connection uses its own slot; reloading user zero retains its full values.
    await b.run(0,user=1);await b.run(4,user=1,setting=1,value=17);r=await b.run(1);assert r['rsp_header_table_size']==0xffffffff
    # No pending SETTINGS is consumed for an unsolicited ACK, and no ACK-of-ACK is sent.
    start=len(b.tx);r=await b.run(5);assert not r['rsp_ack_matched']and not r['rsp_settings_pending']and len(b.tx)==start
    settings=SettingsFrame(0).serialize()
    b.force_stall=True;await b.request(2);await b.wait('m_axis_tx_tvalid');before=bytes(m.data[PEER:PEER+64]);start=len(m.trace)
    for _ in range(17):await cycles(d);assert not int(d.rsp_valid.value)and not int(d.req_ready.value)and len(m.trace)==start and before==bytes(m.data[PEER:PEER+64])
    b.force_stall=False;r=await b.result();assert r['rsp_wire_retired']and r['rsp_settings_pending']==1 and b.tx[-1][1]==settings
    r=await b.run(2);assert r['rsp_settings_pending']==2
    r=await b.run(5);assert r['rsp_ack_matched']and r['rsp_settings_pending']==1 and r['rsp_settings_acks']==1
    r=await b.run(5);assert r['rsp_settings_pending']==0 and r['rsp_settings_acks']==2
    r=await b.run(5);assert not r['rsp_ack_matched']and r['rsp_settings_acks']==2
    ping=PingFrame(0);ping.opaque_data=b'peerdata';payload=int.from_bytes(ping.opaque_data,'big')
    r=await b.run(3,payload=payload);assert r['rsp_wire_retired']and r['rsp_ping_pending']and r['rsp_ping_payload']==payload and b.tx[-1][1]==ping.serialize()
    start=len(b.tx);await b.run(3,payload=123,status=8);assert len(b.tx)==start
    r=await b.run(6,payload=payload^1);assert not r['rsp_ack_matched']and r['rsp_ping_pending']
    r=await b.run(6,payload=payload);assert r['rsp_ack_matched']and not r['rsp_ping_pending']and r['rsp_ping_acks']==1
    r=await b.run(6,payload=payload);assert not r['rsp_ack_matched']and r['rsp_ping_acks']==1
    # Client role accepts server ENABLE_PUSH=0, rejects 1 without a write.
    await b.fresh(client=True);r=await b.run(0);assert not r['rsp_enable_push'];await b.run(4,setting=2,value=0)
    r=await b.run(4,setting=2,value=1,status=4);assert r['rsp_http2_error']==1
    negatives=0
    for patch,status in(({'cfg_context_bytes':255},2),({'cfg_peer_bytes':63},2),({'cfg_peer_base':a['context_base']},2),
        ({'cfg_peer_base':0x7fffc0,'cfg_peer_bytes':192},2),({'req_user':65535},2),({'req_authority':0},7),({'req_maintenance':0},7)):
        start=len(m.trace);await b.run(0,status=status,patch=patch);assert len(m.trace)==start;negatives+=1
    # Persistent owner, role, arena and reserved bits are independently checked
    # before any local frame can reach the wire. These records emulate stale or
    # corrupt external memory rather than a cooperative live caller.
    corruptions=0
    for offset,mask in((0,1),(4,1),(6,1),(8,1),(16,1),(39,0x80)):
        await b.fresh();await b.run(0);m.data[PEER+offset]^=mask;before=len(b.tx)
        await b.run(2,status=3);assert int(d.recovery_required.value)and len(b.tx)==before
        trace=len(m.trace)
        await b.run(0,status=6,patch={'cfg_peer_bytes':128});assert len(m.trace)==trace
        await b.run(0);assert not int(d.recovery_required.value);corruptions+=1
    await b.fresh();await b.run(0)
    struct.pack_into('<I',m.data,PEER+40,0xffffffff);before=len(b.tx)
    await b.run(2,status=8);assert len(b.tx)==before,'Pending SETTINGS counter wrapped'
    faults=0;phases={};wire_uncertain=0
    for op,arguments in((0,{}),(4,{'setting':1,'value':37}),(2,{}),(3,{'payload':payload}),(5,{}),(6,{'payload':payload})):
        async def prepare():
            await b.fresh()
            if op!=0:await b.run(0)
            if op==5:await b.run(2)
            if op==6:await b.run(3,payload=payload)
        await prepare();start=len(m.trace);await b.run(op,**arguments);count=len(m.trace)-start;phases[str(op)]=count
        for phase in range(count):
            await prepare();start=len(m.trace);start_tx=len(b.tx);m.fail=start+phase;r=await b.run(op,status=5,**arguments)
            failed=m.trace[-1];assert failed['status']==0x75 and r['rsp_memory_status']==0x75 and int(d.recovery_required.value)
            assert int(d.recovery_address.value)==failed['address']
            if op in(2,3):
                assert len(b.tx)-start_tx==int(phase>=9)==r['rsp_wire_retired'];wire_uncertain+=int(phase>=9)
            before=len(m.trace)
            if op==0:await b.run(1,status=6)
            else:await b.run(op,status=6,**arguments)
            assert len(m.trace)==before and len(b.tx)==start_tx+int(r['rsp_wire_retired'])
            # A different user's FORMAT cannot clear the quarantined owner.
            await b.run(0,user=1,status=6);assert len(m.trace)==before
            m.fail=-1;await b.run(0);assert not int(d.recovery_required.value);faults+=1
    assert all(e['ack']is not None for e in m.trace)and m.data[:a['work_floor']]==image[:a['work_floor']]
    accepted=dict(phase='passed',commands=b.commands,native_outbound_frames=len(b.tx),memory_phases=phases,injected_memory_faults=faults,
        wire_retired_before_failed_commit=wire_uncertain,negative_configuration_and_authority_commands=negatives,
        corrupt_record_bindings_quarantined=corruptions,pending_settings_overflow_no_tx=True,
        all_non_window_settings_verified=True,peer_direction_verified=True,independent_connections_verified=True,
        actual_tx_handshake_tracking=True,no_pending_count_before_wire=True,no_ack_of_ack=True,ordered_settings_ack_tracking=True,
        matching_ping_ack_only=True,single_outstanding_ping_backpressure=True,unknown_settings_ignored=True,
        all_applied_write_errors_quarantined=True,no_repeat_wire_after_uncertain_commit=True,fenced_owner_recovery_verified=True,
        captured_configuration_poisoned=True,held_tx_cycles=b.tx_stalls,complete_model_prefix_immutable=True,
        hyperframe_version=importlib.metadata.version('hyperframe'),actual_connection_ownership_supplied_by_fixture=True,
        raw_parser_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
