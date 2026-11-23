"""Committed control frames reach the actual directory-owned window ledger."""
import hashlib
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame,SettingsFrame,PingFrame,WindowUpdateFrame,RstStreamFrame,GoAwayFrame
from test_http2_owned_windows import Bench as WindowBench
from test_http2_control_journal import FIELDS
from test_tokenizer_mmio import cycles

JOURNAL=0x760005;SLOT=512


class Memory:
    def __init__(self,d,image,a):
        self.d=d;self.data=bytearray(image);self.a=a;self.pending=[None]*3;self.trace=[];self.count=[0]*3
        self.fail_client=-1;self.fail_at=-1;self.clock=0;self.rng=random.Random(20261128)

    async def run(self):
        d=self.d;a=self.a;held=[None]*3
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert not any(self.pending)
                d.mem_ready.value=0;d.mem_rsp_valid.value=0;d.mem_rsp_data.value=0;d.mem_rsp_status.value=0;held=[None]*3;continue
            ready=valid=data=status=0
            for client,p in enumerate(self.pending):
                if p and p['delay']:p['delay']-=1
                if p and not p['delay']:valid|=1<<client;data|=p['data']<<(72*client);status|=p['entry']['status']<<(8*client)
                if p is None and self.rng.randrange(4):ready|=1<<client
            d.mem_ready.value=ready;d.mem_rsp_valid.value=valid;d.mem_rsp_data.value=data;d.mem_rsp_status.value=status
            await RisingEdge(d.clk);self.clock+=1
            locked=int(d.directory_pool_lock_active.value)
            if locked:assert not(int(d.mem_valid.value)&2),'Directory memory during actual pool ownership'
            for client in range(3):
                if valid>>client&1 and int(d.mem_rsp_ready.value)>>client&1:
                    self.pending[client]['entry']['ack']=self.clock;self.pending[client]=None
                if int(d.mem_valid.value)>>client&1:
                    item=(int(d.mem_write.value)>>client&1,int(d.mem_addr.value)>>(23*client)&0x7fffff,
                        int(d.mem_bytes.value)>>(4*client)&15,int(d.mem_data.value)>>(72*client)&((1<<72)-1))
                    if held[client]is not None:assert item==held[client]
                    held[client]=item if not(ready>>client&1)else None
                    if ready>>client&1:
                        write,address,size,value=item;assert self.pending[client]is None and size==8 and address>=a['work_floor']and address+8<=len(self.data)
                        context=a['context_base']<=address and address+8<=a['context_base']+a['context_bytes']
                        rpc=a['stream_base']<=address and address+8<=a['stream_base']+a['stream_bytes']
                        if client==2:assert locked
                        if write:
                            if client==0:allowed=context and 216<=(address-a['context_base'])%256<=248 or JOURNAL<=address and address+8<=JOURNAL+3*SLOT
                            elif client==1:allowed=rpc and(address-a['stream_base'])%128<=56
                            else:allowed=context and 168<=(address-a['context_base'])%256<=208 or a['window_base']<=address and address+8<=a['window_base']+a['window_bytes']
                            assert allowed,(client,hex(address));self.data[address:address+8]=(value&((1<<64)-1)).to_bytes(8,'little')
                        failed=client==self.fail_client and self.count[client]==self.fail_at
                        entry=dict(client=client,write=write,address=address,status=0x75 if failed else 0,ack=None)
                        self.trace.append(entry);self.count[client]+=1
                        self.pending[client]=dict(entry=entry,data=int.from_bytes(self.data[address:address+8],'little'),delay=self.rng.randrange(2,10))
                else:assert held[client]is None


def events(frame,kind=None,arg0=0,arg1=0):
    wire=frame.serialize();parsed,size=Frame.parse_frame_header(memoryview(wire[:9]));parsed.parse_body(memoryview(wire[9:]));assert parsed.serialize()==wire
    typ,flags=wire[3:5];stream=int.from_bytes(wire[5:9],'big');result=[(0,0,0,0,size,typ,flags,stream,0)]
    if typ==4 and not(flags&1):result +=[(4,0,key,value,size,typ,flags,stream,0)for key,value in frame.settings.items()]
    elif kind is not None:result.append((kind,0,arg0,arg1,size,typ,flags,stream,0))
    result.append((3,0,0,0,size,typ,flags,stream,0));return result


class Bench(WindowBench):
    def __init__(self,d,m,a):
        super().__init__(d,m,a);self.tx=[];self.notices=[];self.cancels=[];self.classes=[];self.notice_error=0;self.closed=True
        self.tx_stalls=0;self.frame_results=[];self.cancel_error=0

    async def start(self,formatting=False):
        a=self.a;self.set(start_user=0,start_format=int(formatting),start_maintenance=int(formatting),start_authority=1,
            cfg_context_base=a['context_base'],cfg_context_bytes=a['context_bytes'],cfg_journal_base=JOURNAL,cfg_journal_bytes=3*SLOT,
            cfg_slot_bytes=SLOT,cfg_work_floor=a['work_floor'],cfg_stream_base=a['stream_base'],cfg_stream_bytes=a['stream_bytes'],
            cfg_window_base=a['window_base'],cfg_window_bytes=a['window_bytes'])
        await self.send('start_valid','start_ready')
        self.set(start_user=65535,start_maintenance=0,start_authority=0,cfg_context_base=0x7fffff,cfg_context_bytes=0,
            cfg_journal_base=0x7fffff,cfg_journal_bytes=0,cfg_slot_bytes=0,cfg_window_base=0x7fffff,cfg_window_bytes=0,
            cfg_stream_base=0x7fffff,cfg_stream_bytes=0)

    async def result(self,status=0):
        await self.wait('result_valid');fields=('result_status','result_detail','result_memory_status','result_committed',
            'result_records','result_frames','control_status','control_detail','control_memory_status',
            'control_http2_error','control_frames','control_ack_frames','control_window_updates')
        result={n:int(getattr(self.d,n).value)for n in fields};assert result['result_status']==status,result
        for _ in range(7):await cycles(self.d);assert int(self.d.result_valid.value)and result=={n:int(getattr(self.d,n).value)for n in fields}
        await self.retire('result_ready');self.frame_results.append(result);return result

    async def send_events(self,records):
        for record in records:
            self.set(**{'s_'+n:v for n,v in zip(FIELDS,record)});await self.send('s_valid','s_ready')

    async def finish(self,commit=True,status=0):
        self.set(finish_commit=int(commit));await self.send('finish_valid','finish_ready');return await self.result(status)

    async def packet(self,records,commit=True,status=0):
        await self.start();await self.send_events(records);return await self.finish(commit,status)

    async def fresh(self):
        await super().fresh();self.m.data[JOURNAL:JOURNAL+3*SLOT]=bytes(3*SLOT)
        await self.window(0)
        for stream in(1,3):await self.directory(0,stream);await self.window(1,stream)
        await self.start(True);await self.result()

    async def callbacks(self,kind):
        d=self.d;prefix=kind+'_';valid=prefix+'valid';ready=prefix+'ready';result_valid=prefix+'result_valid';result_ready=prefix+'result_ready'
        fields={'notice':('kind','user','setting','value','payload'),'cancel':('user','goaway','stream','arg0','arg1'),'classify':('user','stream')}[kind]
        await FallingEdge(d.clk)
        while True:
            await self.wait(valid);snapshot=tuple(int(getattr(d,prefix+n).value)for n in fields)
            for _ in range(5):
                await cycles(d);assert int(getattr(d,valid).value)and snapshot==tuple(int(getattr(d,prefix+n).value)for n in fields)
            self.set(**{ready:1});await cycles(d);self.set(**{ready:0})
            if kind=='notice':self.notices.append(snapshot);status=self.notice_error
            elif kind=='classify':self.classes.append(snapshot);status=0;self.set(classify_closed=int(self.closed))
            else:
                self.cancels.append(snapshot);status=self.cancel_error
                if not snapshot[1]:await self.directory(3,snapshot[2])
            await cycles(d,5);self.set(**{prefix+'status':status,result_valid:1})
            while True:
                await RisingEdge(d.clk)
                if int(getattr(d,result_ready).value):break
            await FallingEdge(d.clk);self.set(**{result_valid:0})

    async def tx_driver(self):
        rng=random.Random(20261129);held=None
        while True:
            await FallingEdge(self.d.clk);self.d.m_axis_tx_tready.value=not int(self.d.rst.value)and rng.randrange(5)==0
            await RisingEdge(self.d.clk)
            if int(self.d.rst.value):held=None;continue
            valid=int(self.d.m_axis_tx_tvalid.value)
            snapshot=tuple(int(getattr(self.d,'m_axis_tx_'+n).value)for n in('tdata','tkeep','tlast','tuser'))if valid else None
            if held is not None:assert snapshot==held
            held=snapshot if valid and not int(self.d.m_axis_tx_tready.value)else None
            if valid:
                if not int(self.d.m_axis_tx_tready.value):self.tx_stalls+=1
                else:
                    data,keep,last,user=snapshot;assert last and user==0 and keep in(0x1ff,0x1ffff)
                    wire=data.to_bytes(64,'little')[:keep.bit_count()]
                    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]));assert frame.serialize()==wire and size+9==len(wire)
                    self.tx.append(wire)


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def committed_controls_actual_window_updates_and_native_ack_frames(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);ref=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['original_image_sha256']
    m=Memory(d,image,ref['layout']);b=Bench(d,m,ref['layout']);b.set(rst=1,start_valid=0,s_valid=0,finish_valid=0,result_ready=0,
        notice_ready=0,notice_result_valid=0,cancel_ready=0,cancel_result_valid=0,classify_ready=0,classify_result_valid=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());cocotb.start_soon(b.tx_driver())
    for kind in('notice','cancel','classify'):cocotb.start_soon(b.callbacks(kind))
    await b.fresh();await b.lease(1)
    settings=SettingsFrame(0);settings.settings={1:2048,4:1200,5:32768,65000:0xdeadbeef};records=events(settings)
    before=len(b.tx);await b.packet(records[:3]);assert len(b.tx)==before
    result=await b.window(6,1);assert result['rsp_stream_window']==65535,'Partial SETTINGS escaped the journal'
    result=await b.packet(records[3:]);assert result['control_window_updates']==2 and result['control_ack_frames']==1
    ack=SettingsFrame(0);ack.flags.add('ACK');assert b.tx[-1]==ack.serialize()
    for stream in(1,3):assert(await b.window(6,stream))['rsp_stream_window']==1200
    assert b.notices[-1][:4]==(0,0,1,2048)
    update=WindowUpdateFrame(1);update.window_increment=37;records=events(update,7,37)
    await b.packet(records,False);assert(await b.window(6,1))['rsp_stream_window']==1200
    await b.packet(records);assert(await b.window(6,1))['rsp_stream_window']==1237
    update=WindowUpdateFrame(0);update.window_increment=101;await b.packet(events(update,7,101))
    assert(await b.window(6))['rsp_connection_window']==65636
    ping=PingFrame(0);ping.opaque_data=b'journal!';hi,lo=struct.unpack('>II',ping.opaque_data)
    await b.packet(events(ping,5,hi,lo));ping.flags.add('ACK');assert b.tx[-1]==ping.serialize()
    before=len(b.tx);await b.packet(events(ping,5,hi,lo));await b.packet(events(ack))
    assert len(b.tx)==before and b.notices[-2][0]==2 and b.notices[-1][0]==1
    missing=WindowUpdateFrame(127);missing.window_increment=1;await b.packet(events(missing,7,1));assert b.classes[-1]==(0,127)
    reset=RstStreamFrame(3);reset.error_code=8;await b.packet(events(reset,8,8))
    assert m.data[b.a['stream_base']+128:b.a['stream_base']+136]==bytes(8),'RST callback did not close actual RPC'
    go=GoAwayFrame(0);go.last_stream_id=1;go.error_code=0;await b.packet(events(go,6,1,0));assert b.cancels[-1][1:]==(1,0,1,0)
    await b.retire('lease_rsp_ready')
    # Applied WINDOW_UPDATE write with an error ACK must fail the executor and
    # journal, never emit an ACK or grant, and prevent a duplicated increment.
    m.fail_client=2;m.fail_at=m.count[2]+13
    update=WindowUpdateFrame(1);update.window_increment=9;result=await b.packet(events(update,7,9),status=8)
    assert result['control_status']==5 and result['result_memory_status']==0x75 and int(d.recovery_required.value)and int(d.window_recovery_required.value)
    before=list(m.count);await b.start();await b.result(6);assert m.count==before
    m.fail_client=-1;await b.directory(3,1);await b.window(7)
    await b.start(True);await b.result();assert not int(d.recovery_required.value)and not int(d.window_recovery_required.value)
    await b.fresh();before_tx=len(b.tx);m.fail_client=0;m.fail_at=m.count[0]+48
    plain_ping=PingFrame(0);plain_ping.opaque_data=b'journal!'
    result=await b.packet(events(plain_ping,5,hi,lo),status=5)
    assert result['result_memory_status']==0x75 and result['control_ack_frames']==1 and len(b.tx)==before_tx+1
    assert int(d.recovery_required.value)and not int(d.window_recovery_required.value)
    counts=list(m.count);await b.start();await b.result(6);assert m.count==counts and len(b.tx)==before_tx+1
    m.fail_client=-1
    for stream in(1,3):await b.directory(3,stream)
    await b.start(True);await b.result()
    await b.fresh();b.closed=False;before_tx=len(b.tx)
    missing=WindowUpdateFrame(125);missing.window_increment=1;result=await b.packet(events(missing,7,1),status=8)
    assert result['control_status']==4 and result['control_http2_error']==1 and int(d.control_connection_error.value)
    assert len(b.tx)==before_tx and not int(d.window_recovery_required.value)
    await b.fresh();b.closed=True;b.notice_error=0x31;before_tx=len(b.tx)
    limited=SettingsFrame(0);limited.settings={1:1024};result=await b.packet(events(limited),status=8)
    assert result['control_status']==9 and result['control_detail']==0x31 and len(b.tx)==before_tx
    await b.fresh();b.notice_error=0;b.cancel_error=0x41
    reset=RstStreamFrame(3);reset.error_code=8;result=await b.packet(events(reset,8,8),status=8)
    assert result['control_status']==10 and result['control_detail']==0x41
    assert m.data[b.a['stream_base']+128:b.a['stream_base']+136]==bytes(8)
    for stream in(1,):await b.directory(3,stream)
    await b.start(True);await b.result();b.cancel_error=0
    await cycles(d,5);assert not any(m.pending)and int(d.idle.value)and int(d.service_idle.value)
    assert m.data[:b.a['work_floor']]==image[:b.a['work_floor']]
    accepted=dict(phase='passed',actual_directory_and_window_engine_verified=True,partial_settings_do_not_apply=True,
        settings_applied_before_ack=True,actual_stream_and_connection_updates=True,aborted_packet_no_update=True,
        native_ack_frames=len(b.tx),peer_ack_callbacks=2,unknown_settings_ignored=True,
        held_cached_lease_survives_controls=True,actual_rst_directory_close=True,
        goaway_callback_verified=True,missing_key_classification_callback=True,uncertain_window_write_quarantines_both=True,
        retry_does_not_duplicate_increment=True,explicit_recovery_verified=True,held_tx_cycles=b.tx_stalls,
        ack_retired_before_failed_head_commit=True,head_failure_does_not_duplicate_ack=True,
        missing_idle_is_connection_error=True,notice_failure_suppresses_ack=True,uncertain_cancel_callback_quarantined=True,
        complete_model_prefix_immutable=True,non_window_callbacks_supplied_by_fixture=True,
        raw_parser_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
