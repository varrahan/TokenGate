"""Exact event conservation, ordered control ACK and independent backpressure."""
from collections import deque
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_tokenizer_mmio import cycles


FIELDS=('kind','data','arg0','arg1','length','type','flags','stream','user')


def snapshot(d,prefix):
    return tuple(int(getattr(d,prefix+field).value)for field in FIELDS)


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def native_semantic_events_control_before_forward(d):
    reference=json.loads(Path(os.environ['PARSER_HTTP2_CONTROL_FIXTURES']).read_text())
    assert reference['phase']=='native_wire_payload_references_passed'
    expected=[tuple(row)for row in reference['events']]
    queue=deque();rng=random.Random(20261120)
    state=dict(sent=0,forwarded=0,controls=0,control_stalls=0,forward_stalls=0,input_stalls=0,clocks=0)
    d.rst.value=1;d.s_valid.value=0;d.m_ready.value=0;d.control_ready.value=0
    for field in FIELDS:getattr(d,'s_'+field).value=0
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start())
    await cycles(d,5);d.rst.value=0

    async def observe():
        held_control=held_forward=None
        while state['forwarded']<len(expected):
            await RisingEdge(d.clk)
            state['clocks']+=1
            if int(d.rst.value):continue
            cv,mv=int(d.control_valid.value),int(d.m_valid.value)
            assert not(cv and mv),'Control preflight and downstream forwarding overlapped'
            c=snapshot(d,'control_')if cv else None
            m=snapshot(d,'m_')if mv else None
            if held_control is not None:assert c==held_control,'Control changed during a stall'
            if held_forward is not None:assert m==held_forward,'Forward event changed during a stall'
            held_control=c if cv and not int(d.control_ready.value)else None
            held_forward=m if mv and not int(d.m_ready.value)else None
            if cv:
                assert queue and queue[0]['control'] and not queue[0]['acked']
                assert c==queue[0]['event']
                if int(d.control_ready.value):queue[0]['acked']=True;state['controls']+=1
                else:state['control_stalls']+=1
            if mv:
                assert queue and (not queue[0]['control']or queue[0]['acked'])
                assert m==queue[0]['event']==expected[state['forwarded']]
                if int(d.m_ready.value):queue.popleft();state['forwarded']+=1
                else:state['forward_stalls']+=1
            if int(d.s_valid.value):
                if int(d.s_ready.value):
                    event=snapshot(d,'s_');assert event==expected[state['sent']]
                    queue.append(dict(event=event,control=event[0]in(0,3)or event[0]>=4,acked=False))
                    state['sent']+=1
                else:state['input_stalls']+=1

    observer=cocotb.start_soon(observe())
    index=0;present=False
    while state['forwarded']<len(expected):
        await FallingEdge(d.clk)
        # Long independent stalls exercise both sides of the ordering fence.
        phase=state['clocks']%113
        d.control_ready.value=phase>=31 and rng.randrange(4)!=0
        d.m_ready.value=phase<53 and rng.randrange(4)!=0
        if present and state['sent']>index:
            index+=1;present=False
        if not present and index<len(expected) and rng.randrange(7)!=0:
            for field,value in zip(FIELDS,expected[index]):getattr(d,'s_'+field).value=value
            present=True
        d.s_valid.value=int(present)
    d.s_valid.value=0
    await observer
    await cycles(d,3)
    assert not queue and int(d.idle.value)
    assert state['sent']==state['forwarded']==reference['semantic_events']
    assert state['controls']==reference['control_events']
    assert all(state[name]>0 for name in('control_stalls','forward_stalls','input_stalls'))
    settings_ack=sum(row[0]==3 and row[5]==4 and row[6]&1 for row in expected)
    ping_ack=sum(row[0]==5 and row[6]&1 for row in expected)
    state.update(phase='passed',native_wire_fragments=reference['packets'],settings_ack=settings_ack,
        ping_ack=ping_ack,all_metadata_preserved=True,control_before_dispatch_verified=True,
        full_transport_verified=False,credit_ledger_verified=False)
    Path('acceptance.json').write_text(json.dumps(state,indent=2)+'\n')
    d._log.info('PASS: ordered HTTP/2 control fork: %s',state)
