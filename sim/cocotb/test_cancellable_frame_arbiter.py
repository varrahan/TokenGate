"""Native frame bytes, real wire cutoff, stalled first beat and private abort."""
from collections import deque
import importlib.metadata
import json
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import DataFrame,Frame,PingFrame,SettingsFrame
from test_tokenizer_mmio import cycles


@cocotb.test(timeout_time=5,timeout_unit='ms')
async def actual_wire_data_fence_preserves_promised_frames_and_control_acks(d):
    expected=[deque(),deque()];counts=dict(frames=0,beats=0,held_cycles=0,paused_control_frames=0,paused_cycles=0,wire_handshake_checks=0)
    running=True;rng=random.Random(20261204)
    def data_frame(stream,size):
        frame=DataFrame(stream);frame.data=bytes((n*13+stream)&255 for n in range(size));return frame.serialize()
    def ack_frame(ping=False,index=0):
        frame=PingFrame(0)if ping else SettingsFrame(0);frame.flags.add('ACK')
        if ping:frame.opaque_data=index.to_bytes(8,'big')
        return frame.serialize()
    def set_source(source,**fields):
        for n,v in fields.items():getattr(d,('a'if source==0 else'b')+'_axis_'+n).value=v
    async def wait(n):
        for _ in range(10000):
            if int(getattr(d,n).value):return
            await FallingEdge(d.clk)
        raise AssertionError('Timeout '+n)
    async def send(source,wire,*,gaps=0,expect=True):
        if expect:expected[source].append(wire)
        for offset in range(0,len(wire),64):
            await FallingEdge(d.clk)
            if offset and gaps:await cycles(d,gaps)
            beat=wire[offset:offset+64];set_source(source,tdata=int.from_bytes(beat,'little'),tkeep=(1<<len(beat))-1,tlast=offset+64>=len(wire),tuser=source+1,tvalid=1)
            while True:
                await RisingEdge(d.clk)
                if int(getattr(d,('a'if source==0 else'b')+'_axis_tready').value):break
            await FallingEdge(d.clk);set_source(source,tvalid=0)
    async def observe():
        held=None;current=None;wire=bytearray()
        while running:
            await RisingEdge(d.clk)
            if int(d.rst.value):continue
            valid=int(d.m_axis_tvalid.value);ready=int(d.m_axis_tready.value)
            record=tuple(int(getattr(d,'m_axis_'+n).value)for n in('tdata','tkeep','tlast','tuser'))if valid else None
            if held is not None:assert held==record,'Pause withdrew or changed a wire promise'
            held=record if valid and not ready else None
            if held is not None:counts['held_cycles']+=1
            a=int(d.a_axis_tvalid.value)and int(d.a_axis_tready.value);b=int(d.b_axis_tvalid.value)and int(d.b_axis_tready.value)
            assert int(bool(a))+int(bool(b))==int(bool(valid and ready));counts['wire_handshake_checks']+=1
            if int(d.a_paused.value):
                counts['paused_cycles']+=1;assert int(d.a_pause.value)and not a and not int(d.a_axis_tready.value)
                assert not valid or record[3]==2,'New DATA was offered after actual wire fence'
            if valid and ready:
                data,keep,last,user=record;source=user-1;assert source in(0,1)
                assert bool(a)==(source==0)and bool(b)==(source==1)
                if current is None:current=source
                assert current==source and keep==(1<<keep.bit_count())-1 and(last or keep.bit_count()==64)
                wire.extend(data.to_bytes(64,'little')[:keep.bit_count()]);counts['beats']+=1
                if last:
                    assert expected[source]and bytes(wire)==expected[source].popleft()
                    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]));assert frame.serialize()==wire and size+9==len(wire)
                    if source==1 and int(d.a_paused.value):counts['paused_control_frames']+=1
                    current=None;wire.clear();counts['frames']+=1
    for source in(0,1):set_source(source,tdata=0,tkeep=0,tlast=0,tuser=0,tvalid=0)
    d.rst.value=1;d.a_pause.value=0;d.m_axis_tready.value=0
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());observer=cocotb.start_soon(observe());await cycles(d,5);d.rst.value=0
    # A's first beat is already visible but not accepted. Pause cannot withdraw
    # it, and B cannot interleave through deliberate gaps inside that DATA frame.
    first=cocotb.start_soon(send(0,data_frame(11,233),gaps=4));await wait('m_axis_tvalid');await cycles(d)
    d.a_pause.value=1;control=cocotb.start_soon(send(1,ack_frame()))
    for _ in range(7):await cycles(d);assert int(d.m_axis_tvalid.value)and int(d.m_axis_tuser.value)==1 and not int(d.a_paused.value)
    d.m_axis_tready.value=1;await first;await wait('a_paused');await control
    # A queued private frame never offered on the wire can be aborted after the
    # fence. ACK traffic must still retire with its exact native bytes.
    aborted=cocotb.start_soon(send(0,data_frame(13,71),expect=False));await wait('a_axis_tvalid')
    await send(1,ack_frame(True,17));await cycles(d,5);assert int(d.a_paused.value)
    aborted.cancel();await FallingEdge(d.clk);set_source(0,tvalid=0)
    # B's own stalled promise survives A-source activity and private abort.
    d.m_axis_tready.value=0;control=cocotb.start_soon(send(1,ack_frame()));await wait('m_axis_tvalid');await cycles(d)
    queued=cocotb.start_soon(send(0,data_frame(15,6)));await wait('a_axis_tvalid')
    for _ in range(7):await cycles(d);assert int(d.a_paused.value)and int(d.m_axis_tuser.value)==2
    d.m_axis_tready.value=1;await control;await cycles(d,3);assert int(d.a_axis_tvalid.value)and not int(d.a_axis_tready.value)
    d.a_pause.value=0;await queued
    ready_running=True
    async def ready():
        while ready_running:await FallingEdge(d.clk);d.m_axis_tready.value=rng.randrange(4)!=0
    async def producer(source):
        for index in range(32):
            wire=data_frame(21+2*index,(index*37)%503+1)if source==0 else ack_frame(bool(index%2),index)
            await send(source,wire,gaps=2 if source==0 and index%3==0 else 0)
    async def pauses():
        for index in range(8):
            await cycles(d,5+index);d.a_pause.value=1;await wait('a_paused');await cycles(d,9);d.a_pause.value=0
    ready_task=cocotb.start_soon(ready());pause_task=cocotb.start_soon(pauses());a=cocotb.start_soon(producer(0));b=cocotb.start_soon(producer(1))
    await a;await b;await pause_task;ready_running=False;ready_task.cancel();await FallingEdge(d.clk);d.m_axis_tready.value=1
    # Native 2048-byte DATA frame: one beat per clock, without output buffering.
    burst=data_frame(333,2039);assert len(burst)==2048;expected[0].append(burst)
    for index in range(32):
        beat=burst[index*64:(index+1)*64];set_source(0,tdata=int.from_bytes(beat,'little'),tkeep=(1<<64)-1,tlast=index==31,tuser=1,tvalid=1)
        await RisingEdge(d.clk);assert int(d.a_axis_tready.value)and int(d.m_axis_tvalid.value)
        await FallingEdge(d.clk)
    set_source(0,tvalid=0);await cycles(d,4);assert not any(expected)and int(d.idle.value)and counts['frames']==70
    assert counts['held_cycles']and counts['paused_control_frames']and counts['paused_cycles'];running=False;observer.cancel()
    accepted=dict(phase='passed',**counts,native_frames=70,private_unoffered_frame_aborted=1,random_pause_sequences=8,sustained_beats=32,
        stalled_first_wire_beat_preserved=True,inflight_data_frame_drains_across_gaps=True,controls_continue_while_data_paused=True,
        paused_source_abort_does_not_reset_control_owner=True,no_new_wire_data_after_fence=True,input_acceptance_is_actual_wire_retirement=True,
        hyperframe_version=importlib.metadata.version('hyperframe'),actual_rpc_cancellation_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
