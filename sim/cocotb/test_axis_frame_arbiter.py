"""Real HTTP/2 DATA/ACK frame ordering, stalls, gaps and sustained beat rate."""
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
async def native_frames_never_interleave_and_retire_on_wire(d):
    rng=random.Random(20261130);expected=[deque(),deque()];accepted=[[],[]]
    frames=[[],[]]
    for index in range(80):
        frame=DataFrame(2*index+1);frame.data=bytes((lane*7+index)&255 for lane in range((index*73)%1537+1));frames[0].append(frame.serialize())
        frame=PingFrame(0)if index%2 else SettingsFrame(0);frame.flags.add('ACK')
        if index%2:frame.opaque_data=index.to_bytes(8,'big')
        frames[1].append(frame.serialize())
    counters=dict(output_frames=0,output_beats=0,held_cycles=0,first_beat_stalls=0,locked_gap_cycles=0,wire_retirement_checks=0,fairness_boundaries=0)
    running=True;force_ready=False;clock=0;burst_cycles=[]
    for p in('a','b'):
        for n in('tdata','tkeep','tvalid','tlast','tuser'):getattr(d,p+'_axis_'+n).value=0
    d.rst.value=1;d.m_axis_tready.value=0
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());await cycles(d,5);d.rst.value=0

    async def producer(source):
        prefix=('a','b')[source]+'_axis_'
        for number,wire in enumerate(frames[source]):
            expected[source].append(wire)
            for offset in range(0,len(wire),64):
                beat=wire[offset:offset+64];await FallingEdge(d.clk)
                getattr(d,prefix+'tdata').value=int.from_bytes(beat,'little');getattr(d,prefix+'tkeep').value=(1<<len(beat))-1
                getattr(d,prefix+'tlast').value=offset+64>=len(wire);getattr(d,prefix+'tuser').value=source+1
                if source==1 and number==0:await cycles(d,7)
                if source==0 and offset and number%3==0:await cycles(d,5)
                getattr(d,prefix+'tvalid').value=1
                while True:
                    await RisingEdge(d.clk)
                    if int(getattr(d,prefix+'tready').value):break
                accepted[source].append((number,offset));await FallingEdge(d.clk);getattr(d,prefix+'tvalid').value=0
            await cycles(d,rng.randrange(3))

    async def ready():
        while running:
            await FallingEdge(d.clk);d.m_axis_tready.value=force_ready or rng.randrange(4)!=0

    async def observe():
        nonlocal clock
        held=None;current=None;wire=bytearray();next_required=None
        while running:
            await RisingEdge(d.clk);clock+=1
            valid=int(d.m_axis_tvalid.value);ready=int(d.m_axis_tready.value)
            record=tuple(int(getattr(d,'m_axis_'+n).value)for n in('tdata','tkeep','tlast','tuser'))if valid else None
            if held is not None:assert record==held,'Presented beat changed before wire acceptance'
            held=record if valid and not ready else None
            if valid and not ready:
                counters['held_cycles']+=1
                if current is None:counters['first_beat_stalls']+=1
            a=int(d.a_axis_tvalid.value)and int(d.a_axis_tready.value);b=int(d.b_axis_tvalid.value)and int(d.b_axis_tready.value)
            assert int(bool(a))+int(bool(b))==int(bool(valid and ready)),'Input accepted before/without actual wire retirement'
            counters['wire_retirement_checks']+=1
            if current is not None and not valid and int(getattr(d,('b'if current==0 else'a')+'_axis_tvalid').value):
                counters['locked_gap_cycles']+=1
            if valid and ready:
                data,keep,last,user=record;source=user-1;assert source in(0,1)
                assert a==int(source==0)and b==int(source==1)
                if current is None:
                    if next_required is not None:assert source==next_required,'Waiting frame lost round-robin service'
                    next_required=None;current=source
                assert current==source,'ACK/DATA frames interleaved'
                assert keep==(1<<keep.bit_count())-1 and(last or keep.bit_count()==64)
                wire.extend(data.to_bytes(64,'little')[:keep.bit_count()]);counters['output_beats']+=1
                if last:
                    assert expected[source]and bytes(wire)==expected[source].popleft()
                    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]));assert frame.serialize()==wire and len(wire)==size+9
                    if int(d.a_axis_tvalid.value)and int(d.b_axis_tvalid.value):
                        next_required=1-source;counters['fairness_boundaries']+=1
                    wire.clear();current=None;counters['output_frames']+=1

    tasks=[cocotb.start_soon(ready()),cocotb.start_soon(observe())]
    a=cocotb.start_soon(producer(0));b=cocotb.start_soon(producer(1));await a;await b;await cycles(d,4)
    assert counters['output_frames']==160 and not any(expected)and int(d.idle.value)
    assert counters['first_beat_stalls']and counters['locked_gap_cycles']and counters['fairness_boundaries']
    # One always-valid source sustains a beat every clock, with no extra queue
    # acceptance that could retire a response/ACK early.
    running=False
    for task in tasks:task.cancel()
    d.m_axis_tready.value=1;d.a_axis_tvalid.value=1;d.a_axis_tkeep.value=(1<<64)-1;d.a_axis_tuser.value=1;d.a_axis_tlast.value=0
    for index in range(32):
        d.a_axis_tdata.value=index;d.a_axis_tlast.value=index==31
        await RisingEdge(d.clk)
        assert int(d.a_axis_tready.value)and int(d.m_axis_tvalid.value)and int(d.m_axis_tdata.value)==index
        burst_cycles.append(index);await FallingEdge(d.clk)
    d.a_axis_tvalid.value=0;await cycles(d,2);assert int(d.idle.value)
    accepted=dict(phase='passed',native_frames=160,**counters,sustained_beats=len(burst_cycles),
        held_first_beat_and_midframe_gap_verified=True,no_frame_interleaving=True,input_acceptance_is_wire_retirement=True,
        hyperframe_version=importlib.metadata.version('hyperframe'),full_parser_integrated=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
