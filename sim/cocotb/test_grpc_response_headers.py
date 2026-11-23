"""Actual HPACK wire bytes, native client completion and real arbiter abort fences."""
import json
import os
from pathlib import Path
import random
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'native-vendor'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame,PingFrame


def v(d,n):return int(getattr(d,n).value)


class Bench:
    def __init__(self,d):
        self.d=d;self.wire=[];self.ready=True;self.held_cycles=0;self.clock=0
    def set(self,**fields):
        for n,x in fields.items():getattr(self.d,n).value=x
    async def tick(self,n=1):
        for _ in range(n):await RisingEdge(self.d.clk);await FallingEdge(self.d.clk)
    async def wait(self,n):
        for _ in range(1000):
            if v(self.d,n):return
            await FallingEdge(self.d.clk)
        raise AssertionError(('Timeout',n))
    async def observe(self):
        held=None
        while True:
            await FallingEdge(self.d.clk);self.d.m_axis_tx_tready.value=int(self.ready);self.clock+=1
            await RisingEdge(self.d.clk)
            if v(self.d,'rst'):assert held is None;continue
            record=tuple(v(self.d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))if v(self.d,'m_axis_tx_tvalid')else None
            if held is not None:assert record==held,'Actual held wire frame changed'
            held=record if record is not None and not v(self.d,'m_axis_tx_tready')else None
            if held is not None:self.held_cycles+=1
            if record is not None and v(self.d,'m_axis_tx_tready'):
                data,keep,last,user=record;assert last and keep and keep&(keep+1)==0
                assert not data>>(8*keep.bit_count()),'Nonzero wire padding'
                raw=data.to_bytes(64,'little')[:keep.bit_count()]
                frame,size=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
                assert frame.serialize()==raw and len(raw)==size+9
                self.wire.append((user,raw))
    async def command(self,case,user):
        d=self.d;await FallingEdge(d.clk)
        self.set(req_kind=case['kind'],req_encoding=case['encoding'],req_grpc_status=case['status'],
            req_stream=case['stream'],req_user=user,req_valid=1)
        while True:
            await RisingEdge(d.clk)
            if v(d,'req_ready'):break
        await FallingEdge(d.clk);self.set(req_valid=0,req_kind=3,req_encoding=3,req_grpc_status=0xffffffff,req_stream=0,req_user=0)
    async def result(self,status,case,user,emitted,raw_bytes=0,*,ack=True):
        d=self.d;await self.wait('result_valid')
        names=('result_status','result_kind','result_user','result_stream','result_tx_emitted','result_wire_bytes')
        record=tuple(v(d,n)for n in names);assert record==(status,case['kind'],user,case['stream'],emitted,raw_bytes),record
        for _ in range(13):await self.tick();assert record==tuple(v(d,n)for n in names)and v(d,'result_valid')
        if ack:self.set(result_ready=1);await self.tick();self.set(result_ready=0)
        return record


@cocotb.test(timeout_time=2,timeout_unit='ms')
async def native_headers_trailers_and_actual_wire_abort_fences(d):
    fixture=json.loads((Path(os.environ['PARSER_GRPC_HEADER_FIXTURES'])/'cases.json').read_text())
    assert fixture['phase']=='native_grpc_header_references_passed'
    b=Bench(d);b.set(rst=1);cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(b.observe())
    await b.tick(5);b.set(rst=0);captured={};rng=random.Random(20261121)
    for index,case in enumerate(fixture['cases']):
        user=(index*16381)&65535;mark=len(b.wire);b.ready=False
        await b.command(case,user);await b.wait('m_axis_tx_tvalid')
        for _ in range(rng.randrange(1,20)):await b.tick();assert not v(d,'result_valid')
        b.ready=True;await b.result(0,case,user,1,len(bytes.fromhex(case['wire_hex'])))
        assert b.wire[mark:]==[(user,bytes.fromhex(case['wire_hex']))]
        captured[case['kind'],case['encoding'],case['status'],case['stream']]=b.wire[-1][1]
    negative=[]
    base=dict(kind=0,encoding=0,status=0,stream=1)
    for changes,status in((dict(kind=3),1),(dict(stream=0),2),(dict(stream=2),2),
        (dict(encoding=3),3),(dict(status=1),4),(dict(kind=1,status=17),4),
        (dict(kind=1,status=0xffffffff),4),(dict(kind=2,status=0),4)):
        case={**base,**changes};mark=len(b.wire);await b.command(case,65535);await b.result(status,case,65535,0)
        assert len(b.wire)==mark;negative.append(case)
    # Actual A fence permits private abort while a real independent B/control
    # frame is offered and stalled. The B promise is not reset or withdrawn.
    case=dict(kind=0,encoding=2,status=0,stream=3);b.set(pause=1);await b.tick();assert v(d,'wire_fenced')
    mark=len(b.wire);await b.command(case,17);await b.wait('header_valid');assert not v(d,'m_axis_tx_tvalid')
    ping=PingFrame(0);ping.flags.add('ACK');ping.opaque_data=b'grpc-hdr';raw=ping.serialize();b.ready=False
    b.set(b_axis_tdata=int.from_bytes(raw,'little'),b_axis_tkeep=(1<<len(raw))-1,b_axis_tlast=1,b_axis_tuser=99,b_axis_tvalid=1)
    await b.wait('m_axis_tx_tvalid');await b.tick(2);assert v(d,'wire_fenced')
    b.set(abort_valid=1);await b.wait('abort_ready');await b.tick();b.set(abort_valid=0)
    await b.result(5,case,17,0);assert len(b.wire)==mark and v(d,'m_axis_tx_tvalid')
    b.ready=True
    while True:
        await RisingEdge(d.clk)
        if v(d,'b_axis_tready'):break
    await FallingEdge(d.clk);b.set(b_axis_tvalid=0);await b.tick();assert b.wire[mark:]==[(99,raw)]
    # A header already offered on the actual wire owns its first beat even
    # before READY. Pause/abort cannot retract it. Completion then wins abort.
    b.set(pause=0);b.ready=False;case=dict(kind=2,encoding=1,status=13,stream=5);mark=len(b.wire)
    await b.command(case,23);await b.wait('m_axis_tx_tvalid');await b.tick(2);b.set(pause=1,abort_valid=1)
    for _ in range(17):
        await b.tick();assert not v(d,'wire_fenced')and not v(d,'abort_ready')and not v(d,'result_valid')
    b.ready=True;await b.wait('result_valid');await b.wait('abort_ready');await b.tick();b.set(abort_valid=0)
    await b.result(0,case,23,1,51)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
    from generate_grpc_header_vectors import client,wire
    assert b.wire[mark:]==[(23,wire(2,1,13,5))]
    # Complete native clients consume RTL-produced initial/trailer bytes.
    # DATA remains an explicit opaque native fixture at this component stage.
    for exchange in fixture['exchanges']:
        encoding=exchange['encoding'];status=exchange['status']
        if exchange['trailers_only']:raw=captured[2,encoding,status,1]
        else:
            from hyperframe.frame import DataFrame
            body=bytes.fromhex(exchange['body_hex']);data=DataFrame(1);data.data=b'\0'+len(body).to_bytes(4,'big')+body
            raw=captured[0,encoding,0,1]+data.serialize()+captured[1,encoding,status,1]
        assert raw.hex()==exchange['wire_hex']
        events=client(encoding).receive_data(raw)
        assert [type(event).__name__ for event in events]==exchange['events']
    b.set(pause=0);await b.tick(3);assert v(d,'header_idle')and v(d,'arb_idle')
    result=dict(phase='passed',native_header_cases=len(fixture['cases']),native_client_exchanges=len(fixture['exchanges']),
        rejected_commands=len(negative),actual_wire_frames=len(b.wire),held_wire_cycles=b.held_cycles,
        stateless_hpack_with_zero_dynamic_decoder=True,config_poisoned_after_acceptance=True,held_results_verified=True,
        private_abort_requires_actual_wire_fence=True,held_control_survives_private_abort=True,
        offered_header_drains_before_abort=True,completed_header_result_not_retracted=True,
        native_client_uses_rtl_header_bytes=True,client_exchange_data_is_native_fixture=True,
        actual_rpc_metadata_joined=False,actual_granted_data_joined=False,raw_reset_controller_joined=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n');d._log.info('PASS: %s',result)
