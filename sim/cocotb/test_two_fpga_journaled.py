"""Full raw/DMA/return workload with RTL-applied peer credits and wire ACKs."""
import json
from pathlib import Path

import cocotb
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame,SettingsFrame,WindowUpdateFrame
from test_bidirectional_application import run_bidirectional
from test_http2_prefill import Bench as RawBench,value
from test_two_fpga_application import SeparateMemory,separate_memory_acceptance
from test_two_fpga_initialized import InitializedBench
from test_tokenizer_mmio import cycles


class JournaledBench(InitializedBench):
    def __init__(self,*args):
        super().__init__(*args);self.ack_frames=[];self.ack_stalls=0;self.wire_kind=None;self.notices=[]

    def configure(self):
        super().configure();self.set(cfg_control_journal_base=0x780005,cfg_control_journal_bytes=3*131072,cfg_control_slot_bytes=131072)

    def poison(self):
        super().poison();self.set(cfg_control_journal_base=0x7fffff,cfg_control_journal_bytes=0,cfg_control_slot_bytes=0)

    async def opening(self,user):
        await RawBench.opening(self,user)
        assert value(self.d,'command_control_status')==0 and self.connection_credit[user]==65535

    async def ready_driver(self):
        await RawBench.ready_driver(self)

    async def packet(self,user,tag,raw,commit):
        await RawBench.packet(self,user,tag,raw,commit)
        if user==0 and not self.zeroed_first and bytes(raw).startswith(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'):
            self.zeroed_first=True
            setting=SettingsFrame(0);setting.settings={4:0}
            await RawBench.packet(self,0,0xf001,setting.serialize(),1);self.extra_packets+=1

    async def flow_observer(self):
        fields=('kind','data','arg0','arg1','length','type','flags','stream','user');held=None
        cocotb.start_soon(self.notice_worker())
        while True:
            await RisingEdge(self.d.clk)
            if value(self.d,'rst'):held=None;continue
            valid=value(self.d,'flow_event_valid');ready=value(self.d,'flow_event_ready')
            record=tuple(value(self.d,'flow_event_'+n)for n in fields)if valid else None
            if held is not None:assert record==held
            held=record if valid and not ready else None
            if valid:
                if not ready:self.flow_stalls+=1
                else:
                    self.flow_count+=1;kind,_,arg0,_,length,typ,flags,stream,user=record
                    if kind==0 and typ==0:self.flow_data_begins+=1
                    if kind==7:
                        assert self.gpu_owned and value(self.d,'response_record_lease_active')
                        assert length==4 and typ==8 and flags==0
                        self.flow_updates.append([user,stream,arg0])
            assert not value(self.d,'cancel_valid')and not value(self.d,'classify_valid')

    async def notice_worker(self):
        d=self.d;await FallingEdge(d.clk)
        while True:
            await self.wait('notice_valid');names=('notice_kind','notice_user','notice_setting','notice_value','notice_payload')
            record=tuple(value(d,n)for n in names)
            for _ in range(5):await cycles(d);assert value(d,'notice_valid')and record==tuple(value(d,n)for n in names)
            self.set(notice_ready=1);await cycles(d);self.set(notice_ready=0);self.notices.append(record)
            await cycles(d,5);self.set(notice_result_valid=1,notice_status=0)
            while True:
                await RisingEdge(d.clk)
                if value(d,'notice_result_ready'):break
            await FallingEdge(d.clk);self.set(notice_result_valid=0)

    def capture(self,target,prefix,width,held,is_bow=False):
        if is_bow:return super().capture(target,prefix,width,held,True)
        valid=value(target,prefix+'tvalid');ready=value(target,prefix+'tready')
        record=tuple(value(target,prefix+n)for n in('tdata','tkeep','tlast','tuser'))if valid else None
        if held is not None:assert record==held
        if valid and self.wire_kind is None:self.wire_kind=record[0]>>24&255
        if self.wire_kind in(4,6):
            if valid:
                if not ready:self.ack_stalls+=1
                else:
                    data,keep,last,user=record;assert last and user<3 and keep in(0x1ff,0x1ffff)
                    wire=data.to_bytes(64,'little')[:keep.bit_count()]
                    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
                    assert frame.serialize()==wire and len(wire)==9+size and 'ACK'in frame.flags and frame.stream_id==0
                    self.ack_frames.append(wire.hex());self.wire_kind=None
            return record if valid and not ready else None
        result=super().capture(target,prefix,width,held,False)
        if valid and ready and record[2]:self.wire_kind=None
        return result

    async def directory(self,op,user=0,stream=0):
        if op==3 and(user,stream)in self.jobs:
            while not self.jobs[user,stream]['done']:
                if value(self.d,'credit_parked'):
                    reference=self.current_response[0];owner=reference['connection'];sid=reference['stream']
                    connection=WindowUpdateFrame(0);target=WindowUpdateFrame(sid)
                    if not self.raw_probe:
                        self.credit_paused=True;connection.window_increment=101;target.window_increment=37
                        await RawBench.packet(self,owner,0xf00d,connection.serialize()+target.serialize(),1);self.extra_packets+=1
                        setting=SettingsFrame(0);setting.settings={4:65535}
                        await RawBench.packet(self,owner,0xf00e,setting.serialize(),1);self.extra_packets+=1
                        self.credit_paused=False;self.raw_probe=True;self.control_probe_complete=True
                    else:
                        connection.window_increment=target.window_increment=1048576
                        await RawBench.packet(self,owner,0xf00f,connection.serialize()+target.serialize(),1);self.extra_packets+=1
                await cycles(self.d)
        await RawBench.directory(self,op,user,stream)
        if op==3:self.stream_credit.pop((user,stream),None)


def acceptance(memory,tested,initial):
    result=separate_memory_acceptance(memory,tested,initial)
    assert tested.raw_probe and tested.zero_grants and tested.positive_grants==tested.total_frames
    assert tested.connection_initializations==tested.opens and tested.stream_initializations==17
    assert tested.flow_updates[:2]==[[0,0,101],[0,1,37]]and len(tested.flow_updates)==tested.peer_updates
    assert not tested.reserved and tested.pending_window is None and tested.ack_frames
    settings_ack=SettingsFrame(0);settings_ack.flags.add('ACK')
    assert tested.ack_frames==[settings_ack.serialize().hex()]*(tested.opens+2)
    result.update(parser_memory_clients=15,automatic_connection_and_control_roots_verified=True,
        actual_admission_windows_verified=True,raw_control_commit_and_replay_verified=True,no_fixture_credit_updates=True,
        independent_credit_model_verified=True,durable_debits_before_data_verified=True,
        response_transport_framing_verified=True,connection_initializations=tested.connection_initializations,
        stream_initializations=tested.stream_initializations,window_commands=tested.window_commands,
        positive_grants=tested.positive_grants,zero_grants=tested.zero_grants,peer_window_updates=tested.peer_updates,
        response_data_frames=tested.total_frames,response_wire_bytes=tested.total_wire_bytes,credit_park_cycles=tested.credit_stalls,
        raw_credit_probe_packets=tested.extra_packets,full_metadata_window_updates=tested.flow_updates,
        native_settings_ack_frames=len(tested.ack_frames),ack_stall_cycles=tested.ack_stalls,
        frame_arbitration_verified=True,non_window_notice_callbacks_supplied_by_fixture=True,
        postcommit_gpu_cancellation_verified=False)
    return result


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def raw_requests_dma_returns_committed_peer_controls_and_ack_tx(d):
    await run_bidirectional(d,bench_factory=JournaledBench,memory_factory=SeparateMemory,extra_result=acceptance)
