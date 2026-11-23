"""A real reservation/LOAD stays owned through DATA-wire drain and key closure."""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from hyperframe.frame import DataFrame, PingFrame

from test_http2_owned_windows import Bench, Memory
from test_cancel_send_windows import close_key
from test_grpc_durable_window_framer import start_message, retire_frame
from test_tokenizer_mmio import cycles


class Wire:
    def __init__(self,d,m):
        self.d=d;self.m=m;self.ready=True;self.frames=[];self.grants=[];self.reserve_traces=[]
        self.data_beats=0;self.stalls=0;self.paused_controls=0;self.frame_done=0;self.zero_grants=[]
        self.dispatched=None;self.packet=bytearray();self.outstanding=None

    async def run(self):
        d=self.d;held=None
        while True:
            await FallingEdge(d.clk);d.m_axis_tx_tready.value=int(self.ready)
            await RisingEdge(d.clk)
            if int(d.rst.value):
                assert not self.packet and held is None and self.outstanding is None,'Reset abandoned DATA/wire ownership'
                self.dispatched=None;continue
            c=d.credits
            if int(c.state.value)==0 and int(c.owned_request_ready.value)and int(c.reserve_pending.value)and not int(c.control_pending.value):
                self.dispatched=len(self.m.trace)
            if int(c.frame_request_valid.value)and int(c.frame_request_ready.value):
                grant=int(d.frame_grant_bytes.value)
                if grant:
                    assert self.outstanding is None and self.dispatched is not None
                    accesses=[e for e in self.m.trace[self.dispatched:]if e['client']==1]
                    writes=[e for e in accesses if e['write']]
                    assert len(writes)==2 and all(e['ack_cycle']is not None for e in writes),'Grant preceded durable debit ACKs'
                    assert [e['address']for e in writes]==[self.m.a['window_base']+8,self.m.a['context_base']+176]
                    self.reserve_traces.append(accesses);self.grants.append(grant);self.outstanding=grant
                else:
                    assert int(d.credit_error_valid.value)and int(d.credit_error_ready.value)
                    self.zero_grants.append(int(d.credit_error_status.value))
            if int(d.frame_tracking_error.value):raise AssertionError('Actual DATA tracking lost ownership')
            if int(d.data_tvalid.value)and int(d.data_tready.value):
                assert self.outstanding is not None,'DATA accepted before a durable positive grant'
                self.data_beats+=1
                if int(d.data_tlast.value):self.frame_done+=1
            if int(d.m_axis_tx_tvalid.value):
                item=tuple(int(getattr(d,n).value)for n in('m_axis_tx_tdata','m_axis_tx_tkeep','m_axis_tx_tlast','m_axis_tx_tuser'))
                if held is not None:assert item==held,'Wire promise changed under backpressure'
                if not int(d.m_axis_tx_tready.value):held=item;self.stalls+=1
                else:
                    held=None;data,keep,last,user=item;assert user==0 and keep and keep&(keep+1)==0
                    self.packet.extend(data.to_bytes(64,'little')[:keep.bit_count()])
                    if last:
                        raw=bytes(self.packet);self.packet.clear();assert len(raw)==9+int.from_bytes(raw[:3],'big')
                        if raw[3]==0:
                            assert self.outstanding==len(raw)-9
                            self.outstanding=None
                        elif int(d.freeze_drained.value):self.paused_controls+=1
                        self.frames.append(raw)
            else:assert held is None,'Stalled wire VALID withdrawn'


async def freeze(b,stream=1,*,already_falling=False):
    d=b.d
    if not already_falling:await FallingEdge(d.clk)
    b.set(freeze_user=0,freeze_stream=stream,freeze_valid=1)
    while True:
        await RisingEdge(d.clk)
        if int(d.freeze_ready.value):break
    await FallingEdge(d.clk);b.set(freeze_valid=0,freeze_user=65535,freeze_stream=0x7fffffff)
    assert int(d.freeze_active.value)


async def ping(b,payload):
    f=PingFrame(0);f.opaque_data=payload;f.flags.add('ACK');raw=f.serialize()
    b.set(b_axis_tdata=int.from_bytes(raw,'little'),b_axis_tkeep=(1<<len(raw))-1,b_axis_tlast=1,b_axis_tuser=0)
    await b.send('b_axis_tvalid','b_axis_tready')
    return raw


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def actual_reserved_data_drains_before_key_close_and_cached_retirement(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);ref=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['original_image_sha256']
    m=Memory(d,image,ref['layout']);b=Bench(d,m,ref['layout']);w=Wire(d,m)
    b.set(rst=1,req_valid=0,rsp_ready=0,lease_valid=0,lease_rsp_ready=0,window_req_valid=0,window_rsp_ready=0,
        start_valid=0,s_axis_message_tvalid=0,result_ready=0,credit_error_ready=0,freeze_valid=0,freeze_release_valid=0,b_axis_tvalid=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());cocotb.start_soon(w.run())
    payload=bytes((i*17+3)&255 for i in range(200));record=b'\0'+len(payload).to_bytes(4,'big')+payload

    async def prepare(initial=64):
        b.set(freeze_valid=0,freeze_release_valid=0,b_axis_tvalid=0,credit_error_ready=0,lease_rsp_ready=0)
        w.ready=True;await b.fresh();await b.directory(0,1);await b.window(0);await b.window(1,1)
        await b.window(3,amount=initial);await b.lease(1)

    # A complete native DATA frame establishes the real reservation phase list.
    await prepare(65535);initial_frames=len(w.frames);await start_message(b,payload,premature_lease_ack=True)
    result=await retire_frame(b);native=DataFrame(1);native.data=record
    assert w.frames[initial_frames:]==[native.serialize()]and result[3:7]==(len(payload),len(record)+9,1,1)
    phases=len(w.reserve_traces[-1]);assert phases>=12
    debit_phases=[i for i,e in enumerate(w.reserve_traces[-1])if e['write']];assert len(debit_phases)==2

    async def complete_cancel(frame_mark,grant_mark,expected_data,*,closed=False):
        await b.wait('freeze_drained')
        assert int(d.freeze_binding_valid.value)and int(d.freeze_record_address.value)==b.addresses[1]and int(d.freeze_generation.value)==101
        assert not int(d.frame_wire_pending.value)and int(d.data_wire_paused.value)
        cached=tuple(int(getattr(d,n).value)for n in('lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_address','lease_rsp_state'))
        if not closed:await close_key(b,1)
        # B/control frames still use the actual wire while matching DATA is paused.
        control=await ping(b,b'FROZEN01');assert w.frames[-1]==control
        assert int(d.lease_rsp_valid.value)and cached==tuple(int(getattr(d,n).value)for n in('lease_rsp_user','lease_rsp_stream','lease_rsp_generation','lease_rsp_address','lease_rsp_state'))
        result=await b.window(6,1)
        assert result['rsp_connection_window']==65535-sum(w.grants[grant_mark:])
        assert result['rsp_stream_window']==(0 if not expected_data else 64-sum(w.grants[grant_mark:]))
        before=len(m.trace)
        for _ in range(13):await cycles(d);assert int(d.freeze_drained.value)and not int(d.result_valid.value)and len(m.trace)==before
        await b.send('freeze_release_valid','freeze_release_ready');await b.wait('credit_error_valid')
        assert int(d.credit_error_status.value)==8 and int(d.credit_error_http2_error.value)==5 and int(d.frame_grant_bytes.value)==0
        for _ in range(11):await cycles(d);assert int(d.lease_rsp_valid.value)and not int(d.result_valid.value)
        b.set(credit_error_ready=1);await b.wait('result_valid');b.set(credit_error_ready=0)
        result=await retire_frame(b,status=5)
        assert result[4:7]==(sum(len(x)for x in expected_data),len(expected_data),int(bool(expected_data))),result
        actual=[x for x in w.frames[frame_mark:]if x[3]==0]
        assert actual==expected_data,(len(actual),len(expected_data))
        assert not int(d.frame_wire_pending.value)and not int(d.freeze_active.value)and not any(m.pending)

    cancelled=0
    # Freeze and a newly eligible reservation on the very same edge: no memory/debit.
    await prepare(0);fm=len(w.frames);gm=len(w.grants);await start_message(b,payload,premature_lease_ack=True)
    while True:
        await FallingEdge(d.clk)
        if int(d.framer.state.value)==3 and int(d.credits.state.value)==0:break
    before=m.count[1];await freeze(b,already_falling=True)
    for _ in range(15):await cycles(d);assert m.count[1]==before and int(d.freeze_drained.value)
    await complete_cancel(fm,gm,[]);cancelled+=1
    # A real zero-credit reservation already parked the sender before cancellation.
    await prepare(0);fm=len(w.frames);gm=len(w.grants);await start_message(b,payload,premature_lease_ack=True)
    await b.wait('credit_parked');await freeze(b);await complete_cancel(fm,gm,[]);cancelled+=1

    native=DataFrame(1);native.data=record[:64];first_frame=native.serialize()
    # Every dispatched reserve memory phase, plus each DATA-wire boundary.
    targets=[('memory',i)for i in range(phases)]+[(s,0)for s in('positive_private','first_stall','frame_gap','last_stall','wire_last')]
    for target,phase in targets:
        await prepare();fm=len(w.frames);gm=len(w.grants);base=m.count[1]
        w.ready=target=='frame_gap' or target=='wire_last'
        await start_message(b,payload,premature_lease_ack=True)
        if target=='memory':
            while m.count[1]<base+phase+1:await FallingEdge(d.clk)
            assert int(d.credits.state.value)==2
        elif target=='positive_private':
            await b.wait('frame_wire_pending');assert not int(d.data_tvalid.value)
        elif target=='first_stall':
            await b.wait('m_axis_tx_tvalid');assert not w.ready and not int(d.m_axis_tx_tlast.value)
        elif target=='frame_gap':
            prior=w.data_beats
            while w.data_beats==prior:await FallingEdge(d.clk)
            w.ready=False
            assert not int(d.data_tvalid.value),'Expected a real gap while the byte framer fills its final beat'
        elif target=='last_stall':
            w.ready=True
            while True:
                await FallingEdge(d.clk)
                if int(d.data_tvalid.value)and int(d.data_tlast.value):
                    w.ready=False;d.m_axis_tx_tready.value=0;break
        elif target=='wire_last':
            while True:
                await FallingEdge(d.clk)
                if int(d.data_tvalid.value)and int(d.data_tlast.value):break
            await freeze(b,already_falling=True)
        if target!='wire_last':await freeze(b)
        # Queue actual key closure now. It cannot be accepted until the owned
        # frame has retired on the wire, including all stalls and internal gaps.
        close=cocotb.start_soon(close_key(b,1))
        if int(d.frame_wire_pending.value)or int(d.credits.state.value)==2:
            before=m.count[1]
            for _ in range(17):
                await cycles(d);assert not int(d.freeze_drained.value)and not int(d.window_req_ready.value)
            if target!='memory':assert m.count[1]==before
        w.ready=True;await close;await complete_cancel(fm,gm,[first_frame],closed=True);cancelled+=1

    # A freeze for another key must not pause, close or consume the active stream.
    await prepare(65535);await b.directory(0,3);await b.window(1,3);fm=len(w.frames)
    await start_message(b,payload,premature_lease_ack=True);await b.wait('frame_wire_pending');await freeze(b,3)
    assert int(d.freeze_drained.value)and not int(d.freeze_binding_valid.value)and not int(d.data_wire_paused.value)
    await close_key(b,3);result=await retire_frame(b)
    native=DataFrame(1);native.data=record;assert w.frames[fm:]==[native.serialize()]and result[0]==0
    await b.send('freeze_release_valid','freeze_release_ready')

    # If the whole message is already on the wire, freezing cannot retract it
    # or manufacture a STREAM_CLOSED reservation. Preserve its held success
    # result and real LOAD until the parent acknowledges that terminal result.
    await prepare(65535);fm=len(w.frames);await start_message(b,payload,premature_lease_ack=True)
    await b.wait('result_valid');await freeze(b);await b.wait('freeze_drained')
    assert int(d.result_status.value)==0 and int(d.lease_rsp_valid.value)and int(d.freeze_binding_valid.value)
    await close_key(b,1);control=await ping(b,b'FINISHED')
    assert w.frames[fm:]==[native.serialize(),control]
    await b.send('freeze_release_valid','freeze_release_ready');result=await retire_frame(b)
    assert result[0]==0 and result[4:7]==(len(record)+9,1,1)

    # A failed debit ACK never grants DATA, even if the physical write applied.
    faults=0
    for phase in debit_phases:
        await prepare();fm=len(w.frames);gm=len(w.grants);base=m.count[1];m.fail_client=1;m.fail_at=base+phase
        await start_message(b,payload,premature_lease_ack=True)
        while m.count[1]<base+1:await FallingEdge(d.clk)
        await freeze(b);await b.wait('credit_error_valid')
        assert int(d.credit_error_status.value)==5 and int(d.credit_error_memory_status.value)==0x75
        for _ in range(17):await cycles(d);assert not int(d.freeze_drained.value)and int(d.lease_rsp_valid.value)
        assert int(d.window_recovery_required.value)and len(w.grants)==gm and len(w.frames)==fm
        b.set(credit_error_ready=1);await b.wait('freeze_drained');b.set(credit_error_ready=0)
        await close_key(b,1,status=6);assert not int(d.window_rsp_binding_valid.value)
        await b.send('freeze_release_valid','freeze_release_ready');await retire_frame(b,status=5)
        assert len(w.grants)==gm and len(w.frames)==fm and not any(m.pending);faults+=1
    await cycles(d,4)
    assert m.data[:b.a['work_floor']]==image[:b.a['work_floor']]
    accepted=dict(phase='passed',native_reference='hyperframe',native_reference_version=version('hyperframe'),
        reserved_memory_phases=phases,cancelled_scenarios=cancelled,wire_boundary_scenarios=5,
        uncertain_debit_ack_faults=faults,native_frames=len(w.frames),data_frames=w.frame_done,wire_stalls=w.stalls,
        controls_while_data_frozen=w.paused_controls,completed_message_result_races=1,
        completed_wire_success_not_retracted=True,same_edge_freeze_blocks_dispatch=True,actual_parked_sender_cancelled=True,
        positive_reservation_drained_to_actual_wire=True,all_dispatched_memory_phases_frozen=True,
        stalled_wire_promises_preserved=True,actual_key_close_waits_for_wire=True,actual_cached_load_held_through_terminal_result=True,
        both_debit_acks_precede_every_positive_grant=True,no_credit_refund=True,nonmatching_stream_continues=True,
        uncertain_debits_never_grant_or_publish_close=True,model_prefix_immutable=True,
        actual_rpc_return_integrated=False,actual_rst_controller_integrated=False,gpu_image_lease_cancellation_verified=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
