"""Tentative control frames, per-connection continuation and every memory fault.

Actual connection ownership/raw-context setup is a fixture contract here.
Consumer ACKs model completed effects; this is not a window-controller join.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from hyperframe.frame import Frame, PingFrame, WindowUpdateFrame, RstStreamFrame, GoAwayFrame, SettingsFrame
from test_http2_owned_windows import Bench as Helpers
from test_tokenizer_mmio import cycles


BASE=0x700003;JOURNAL=0x720005;SLOT=256;FLOOR=0x695700
FIELDS=('kind','data','arg0','arg1','length','type','flags','stream','user')


def native_events():
    settings=[(1,4096),(4,0),(5,16384),(4,65535),(65000,0xdeadbeef)]
    payload=b''.join(struct.pack('>HI',*p)for p in settings)
    wire=len(payload).to_bytes(3,'big')+b'\x04\0'+bytes(4)+payload
    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
    assert size==30 and frame.settings==dict(settings)
    events=[(0,0,0,0,30,4,0,0,0)]
    events +=[(4,0,i,v,30,4,0,0,0)for i,v in settings]
    events +=[(3,0,0,0,30,4,0,0,0)]
    ping=PingFrame(0);ping.opaque_data=b'journal!';pingwire=ping.serialize()
    decoded,size=Frame.parse_frame_header(memoryview(pingwire[:9]));decoded.parse_body(memoryview(pingwire[9:]))
    hi,lo=struct.unpack('>II',decoded.opaque_data)
    pings=[(0,0,0,0,8,6,0,0,0),(5,0,hi,lo,8,6,0,0,0),(3,0,0,0,8,6,0,0,0)]
    return events,pings


class Memory:
    def __init__(self,d,image):
        self.d=d;self.data=bytearray(image);self.pending=None;self.trace=[];self.fail=-1;self.clock=0
        self.rng=random.Random(20261126)

    async def run(self):
        d=self.d;held=None
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert self.pending is None
                d.mem_ready.value=0;d.mem_rsp_valid.value=0;d.mem_rsp_data.value=0;d.mem_rsp_status.value=0;held=None;continue
            p=self.pending
            if p and p['delay']:p['delay']-=1
            valid=p is not None and not p['delay'];ready=p is None and self.rng.randrange(4)!=0
            d.mem_ready.value=ready;d.mem_rsp_valid.value=valid;d.mem_rsp_data.value=p['data']if valid else 0
            d.mem_rsp_status.value=p['entry']['status']if valid else 0
            await RisingEdge(d.clk);self.clock+=1
            if valid and int(d.mem_rsp_ready.value):p['entry']['ack']=self.clock;self.pending=None
            if int(d.mem_valid.value):
                item=tuple(int(getattr(d,n).value)for n in('mem_write','mem_addr','mem_bytes','mem_data'))
                if held is not None:assert item==held
                held=item if not ready else None
                if ready:
                    write,address,size,value=item;assert self.pending is None and size==8 and address>=FLOOR and address+8<=len(self.data)
                    if write:
                        root=BASE<=address and address+8<=BASE+512 and 216<=(address-BASE)%256<=248
                        entry=JOURNAL<=address and address+8<=JOURNAL+2*SLOT
                        assert root or entry,('Journal write ownership',hex(address))
                        self.data[address:address+8]=(value&((1<<64)-1)).to_bytes(8,'little')
                    event=dict(write=write,address=address,status=0x75 if len(self.trace)==self.fail else 0,ack=None)
                    self.trace.append(event);self.pending=dict(entry=event,data=int.from_bytes(self.data[address:address+8],'little'),delay=self.rng.randrange(2,10))
            else:assert held is None


class Bench(Helpers):
    def __init__(self,d,m):
        self.d=d;self.m=m;self.emitted=[];self.allowed=False;self.consumer_error=0;self.stalls=0

    async def consume(self):
        held=None;rng=random.Random(20261127)
        while True:
            await FallingEdge(self.d.clk)
            self.d.m_ready.value=not int(self.d.rst.value)and rng.randrange(4)==0
            self.d.consume_status.value=self.consumer_error
            await RisingEdge(self.d.clk)
            if int(self.d.rst.value):held=None;continue
            valid=int(self.d.m_valid.value);record=tuple(int(getattr(self.d,'m_'+n).value)for n in FIELDS)if valid else None
            if held is not None:assert record==held,'Committed control metadata changed under backpressure'
            held=record if valid and not int(self.d.m_ready.value)else None
            if valid:
                assert self.allowed,'Tentative or incomplete frame escaped'
                if int(self.d.m_ready.value):
                    if not self.consumer_error:self.emitted.append(record)
                else:self.stalls+=1

    async def begin(self,user=0,formatting=False,patch=None):
        fields=dict(start_user=user,start_format=int(formatting),start_maintenance=int(formatting),start_authority=1,
            cfg_context_base=BASE,cfg_context_bytes=512,cfg_journal_base=JOURNAL,cfg_journal_bytes=2*SLOT,cfg_slot_bytes=SLOT,cfg_work_floor=FLOOR)
        fields.update(patch or {});self.set(**fields);await self.send('start_valid','start_ready')
        self.set(start_user=65535,start_format=0,start_maintenance=0,start_authority=0,
            cfg_context_base=0x7fffff,cfg_context_bytes=0,cfg_journal_base=0x7fffff,cfg_journal_bytes=0,cfg_slot_bytes=0)

    async def result(self,status=0):
        await self.wait('result_valid')
        fields=('result_status','result_detail','result_memory_status','result_user','result_committed','result_records','result_frames')
        result=tuple(int(getattr(self.d,n).value)for n in fields);assert result[0]==status,result
        for _ in range(7):await cycles(self.d);assert int(self.d.result_valid.value)and result==tuple(int(getattr(self.d,n).value)for n in fields)
        await self.retire('result_ready');return result

    async def finish(self,commit=True,status=0):
        self.set(finish_commit=int(commit));self.allowed=bool(commit)
        await self.send('finish_valid','finish_ready');return await self.result(status)

    async def events(self,events,user=0):
        for event in events:
            self.set(**{'s_'+n:v for n,v in zip(FIELDS,(*event[:-1],user))})
            await self.send('s_valid','s_ready')

    async def fresh(self):
        await cycles(self.d,3);assert self.m.pending is None
        self.set(rst=1,start_valid=0,s_valid=0,finish_valid=0,result_ready=0)
        await cycles(self.d,5)
        self.m.data[BASE:BASE+512]=bytes(512);self.m.data[JOURNAL:JOURNAL+2*SLOT]=bytes(2*SLOT)
        for user in range(2):struct.pack_into('<Q',self.m.data,BASE+256*user,0x48324331|3<<32|16384<<40)
        self.m.fail=-1;self.allowed=False;self.consumer_error=0;self.emitted.clear();self.set(rst=0)
        for user in range(2):await self.begin(user,True);await self.result()


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def partial_control_frames_packet_abort_wrap_and_every_memory_fault(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    ref=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['original_image_sha256']
    m=Memory(d,image);b=Bench(d,m);d.rst.value=1
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());cocotb.start_soon(b.consume())
    settings,ping=native_events();await b.fresh()
    await b.begin();await b.events(settings[:2]);result=await b.finish()
    assert result[4:]==(1,0,0)and not b.emitted
    saved=bytes(m.data[BASE+216:BASE+256])
    await b.begin(1);await b.events(ping,1);await b.finish()
    assert b.emitted==[(*e[:-1],1)for e in ping]
    b.emitted.clear();b.allowed=False
    await b.begin();await b.events(settings[2:]);result=await b.finish(False)
    assert result[4:]==(0,0,0)and not b.emitted and m.data[BASE+216:BASE+256]==saved
    await b.begin();await b.events(settings[2:]);result=await b.finish()
    assert b.emitted==settings and result[5:]==(7,1)
    b.emitted.clear();await b.begin();await b.events(ping);await b.finish()
    assert b.emitted==ping
    head,tail=struct.unpack_from('<II',m.data,BASE+224);assert head==tail==64,'Ring did not wrap'
    update=WindowUpdateFrame(127);update.window_increment=0x7fffffff
    reset=RstStreamFrame(127);reset.error_code=8
    goaway=GoAwayFrame(0);goaway.last_stream_id=0x7fffffff;goaway.error_code=13;goaway.additional_data=b'epoch'
    ack=PingFrame(0);ack.flags.add('ACK');ack.opaque_data=b'journal!'
    settings_ack=SettingsFrame(0);settings_ack.flags.add('ACK')
    extra_frames=0
    for frame,kind,arg0,arg1 in((update,7,0x7fffffff,0),(reset,8,8,0),
        (goaway,6,0x7fffffff,13),(ack,5,*struct.unpack('>II',ack.opaque_data)),(settings_ack,None,0,0)):
        wire=frame.serialize();decoded,size=Frame.parse_frame_header(memoryview(wire[:9]));decoded.parse_body(memoryview(wire[9:]))
        assert decoded.serialize()==wire
        length=int.from_bytes(wire[:3],'big');typ,flags=wire[3:5];stream=int.from_bytes(wire[5:9],'big')
        expected=[(0,0,0,0,length,typ,flags,stream,0)]
        if kind is not None:expected.append((kind,0,arg0,arg1,length,typ,flags,stream,0))
        expected.append((3,0,0,0,length,typ,flags,stream,0))
        b.emitted.clear();b.allowed=False;await b.begin();await b.events(expected);await b.finish()
        assert b.emitted==expected;extra_frames+=1
    negatives=0
    for patch,status in (({'start_authority':0},7),({'start_user':2},2),
        ({'cfg_journal_base':BASE},2),({'cfg_slot_bytes':32},2),
        ({'cfg_journal_base':0x100},2),({'cfg_context_bytes':256,'start_user':1},2)):
        before=len(m.trace);await b.begin(patch=patch);await b.result(status)
        assert len(m.trace)==before and not int(d.recovery_required.value);negatives+=1
    before=len(m.trace);await b.begin(formatting=True,patch={'start_maintenance':0});await b.result(7)
    assert len(m.trace)==before;negatives+=1
    # Full input capacity fails explicitly; it never waits for an impossible
    # packet commit or exposes the incomplete frame to the consumer.
    await b.fresh();await b.begin();await b.events([settings[0]]+settings[1:6]+[settings[1]])
    await b.events([settings[-1]]);await b.result(4);assert int(d.recovery_required.value)and not b.emitted
    await b.begin(formatting=True);await b.result();assert not int(d.recovery_required.value)

    await b.fresh();before=len(m.trace);await b.begin();await b.events(ping);await b.finish();phases=len(m.trace)-before
    assert phases==54,phases
    faults=0
    for phase in range(phases):
        await b.fresh();m.fail=len(m.trace)+phase;await b.begin()
        async def drive():
            for event in ping:
                if int(d.result_valid.value):return
                # A memory error may complete while a held source event is
                # waiting; stop this fixture's unaccepted request on result.
                b.set(**{'s_'+n:v for n,v in zip(FIELDS,event)})
                await FallingEdge(d.clk);d.s_valid.value=1
                while not int(d.result_valid.value):
                    await RisingEdge(d.clk)
                    if int(d.s_ready.value):break
                await FallingEdge(d.clk);d.s_valid.value=0
            if not int(d.result_valid.value):
                b.allowed=True;b.set(finish_commit=1);d.finish_valid.value=1
                while not int(d.result_valid.value):
                    await RisingEdge(d.clk)
                    if int(d.finish_ready.value):break
                await FallingEdge(d.clk);d.finish_valid.value=0
        driver=cocotb.start_soon(drive());result=await b.result(5);await driver
        assert result[2]==0x75 and int(d.recovery_required.value)and b.emitted==ping[:len(b.emitted)]
        failed=[e for e in m.trace if e['status']][-1]
        assert int(d.recovery_address.value)==failed['address']and result[4]==0
        before=len(m.trace);await b.begin();await b.result(6);assert len(m.trace)==before
        m.fail=-1;await b.begin(formatting=True);await b.result();assert not int(d.recovery_required.value)
        faults+=1
    await b.fresh();await b.begin();await b.events(ping);b.consumer_error=0x31
    result=await b.finish(status=8);assert result[1]==0x31 and int(d.recovery_required.value)and not b.emitted
    assert m.data[:FLOOR]==image[:FLOOR]
    accepted=dict(phase='passed',native_settings_parameters=5,duplicate_settings_preserved=True,
        unknown_settings_preserved=True,partial_frame_across_packets_verified=True,independent_connections_verified=True,
        native_extra_control_frames=extra_frames,stream_id_and_ack_flags_preserved=True,
        aborted_packet_preserves_committed_root=True,complete_frame_before_consumer_verified=True,ring_wrap_verified=True,
        explicit_capacity_failure_verified=True,memory_phases=phases,injected_memory_faults=faults,
        negative_configuration_and_authority_commands=negatives,
        applied_write_errors_quarantined=True,no_retry_after_uncertain_effect=True,consumer_error_quarantined=True,
        poisoned_config_verified=True,held_output_cycles=b.stalls,complete_model_prefix_immutable=True,
        hyperframe_version=importlib.metadata.version('hyperframe'),actual_connection_ownership_supplied_by_fixture=True,
        window_consumer_integrated=False,raw_parser_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
