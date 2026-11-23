"""Full raw/DMA/return workload with actual durable peer state and server preface."""
import json
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge
from hyperframe.frame import Frame,SettingsFrame
from test_bidirectional_application import run_bidirectional
from test_http2_prefill import Bench as RawBench,value
from test_two_fpga_application import SeparateMemory,separate_memory_acceptance
from test_two_fpga_journaled import JournaledBench
from test_tokenizer_mmio import cycles

PEER=0x7e4005


class PeerBench(JournaledBench):
    def __init__(self,*args):
        super().__init__(*args);self.server_frames=[];self.peer_pending={};self.peer_acks={};self.pending_peer=None
        self.peer_commands=self.peer_formats=self.peer_sends=self.peer_received_acks=self.peer_settings=0;self.peer_write_acks=0;self.peer_write_pending=False
    def configure(self):
        super().configure();self.set(cfg_peer_base=PEER,cfg_peer_bytes=192)
    def poison(self):
        super().poison();self.set(cfg_peer_base=0x7fffff,cfg_peer_bytes=0)
    async def opening(self,user):
        await super().opening(user);assert self.peer_pending[user]==1 and value(self.d,'peer_format_status')==0
    async def packet(self,user,tag,raw,commit):
        await super().packet(user,tag,raw,commit)
        if bytes(raw).startswith(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'):
            ack=SettingsFrame(0);ack.flags.add('ACK');settings=SettingsFrame(0);settings.settings={1:2048,2:0,3:0,6:8192}
            await RawBench.packet(self,user,0xf020,ack.serialize()+settings.serialize(),1);self.extra_packets+=1
            assert self.peer_pending[user]==0 and self.peer_acks[user]==1
    async def notice_worker(self):
        assert not hasattr(self.d,'notice_ready')and not hasattr(self.d,'notice_result_valid')
        cocotb.start_soon(self.peer_observer())
    async def peer_observer(self):
        d=self.d;p=d.dut.core.controls.peer
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            if value(p,'req_valid')and value(p,'req_ready'):
                assert self.pending_peer is None
                self.pending_peer=tuple(value(p,'req_'+n)for n in('op','user','setting','value','payload'));self.peer_write_acks=0
            if value(d,'mem_valid')>>24&value(d,'mem_ready')>>24&value(d,'mem_write')>>24&1:
                assert not self.peer_write_pending;self.peer_write_pending=True
            if value(d,'mem_rsp_valid')>>24&value(d,'mem_rsp_ready')>>24&1 and self.peer_write_pending:
                assert value(d,'mem_rsp_status')>>(24*8)&255==0;self.peer_write_pending=False;self.peer_write_acks+=1
            if not(value(p,'rsp_valid')and value(p,'rsp_ready')):continue
            assert self.pending_peer is not None and value(p,'rsp_status')==0
            op,user,setting,amount,payload=self.pending_peer;self.pending_peer=None;self.peer_commands+=1
            assert self.peer_write_acks==9 and not self.peer_write_pending
            if op==0:self.peer_pending[user]=self.peer_acks[user]=0;self.peer_formats+=1
            elif op==2:
                assert value(p,'rsp_wire_retired')and self.server_frames[-1][0]==user
                self.peer_pending[user]+=1;self.peer_sends+=1
            elif op==4:
                assert setting in(1,2,3,6);self.peer_settings+=1
                field={1:'header_table_size',2:'enable_push',3:'max_concurrent_streams',6:'max_header_list_size'}[setting]
                assert value(p,'rsp_'+field)==amount
            elif op==5:
                assert value(p,'rsp_ack_matched')and self.peer_pending[user]>0
                self.peer_pending[user]-=1;self.peer_acks[user]+=1;self.peer_received_acks+=1
            else:raise AssertionError(('Unexpected peer op',op))
            assert value(p,'rsp_settings_pending')==self.peer_pending[user]and value(p,'rsp_settings_acks')==self.peer_acks[user]
    def capture(self,target,prefix,width,held,is_bow=False):
        if is_bow:return super().capture(target,prefix,width,held,True)
        valid=value(target,prefix+'tvalid');ready=value(target,prefix+'tready')
        record=tuple(value(target,prefix+n)for n in('tdata','tkeep','tlast','tuser'))if valid else None
        if held is not None:assert held==record
        if valid and self.wire_kind is None:self.wire_kind=record[0]>>24&255
        if self.wire_kind==4 and valid and not(record[0]>>32&1):
            if ready:
                data,keep,last,user=record;wire=data.to_bytes(64,'little')[:keep.bit_count()]
                assert keep==0x1ff and last and wire==SettingsFrame(0).serialize()
                frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]));assert size==0 and not frame.flags
                self.server_frames.append((user,wire.hex()));self.wire_kind=None
            return record if not ready else None
        return super().capture(target,prefix,width,held,False)


def acceptance(memory,tested,initial):
    result=separate_memory_acceptance(memory,tested,initial)
    assert tested.raw_probe and tested.zero_grants and tested.positive_grants==tested.total_frames
    assert tested.connection_initializations==tested.opens==tested.peer_formats==tested.peer_sends==tested.peer_received_acks==len(tested.server_frames)
    assert tested.stream_initializations==17 and tested.peer_settings==4*tested.opens
    assert tested.flow_updates[:2]==[[0,0,101],[0,1,37]]and len(tested.flow_updates)==tested.peer_updates
    assert not tested.reserved and tested.pending_window is None and tested.pending_peer is None
    ack=SettingsFrame(0);ack.flags.add('ACK');assert tested.ack_frames==[ack.serialize().hex()]*(2*tested.opens+2)
    result.update(parser_memory_clients=16,automatic_connection_and_control_roots_verified=True,
        actual_admission_windows_verified=True,raw_control_commit_and_replay_verified=True,no_fixture_credit_updates=True,
        independent_credit_model_verified=True,durable_debits_before_data_verified=True,frame_arbitration_verified=True,
        connection_initializations=tested.connection_initializations,stream_initializations=tested.stream_initializations,
        window_commands=tested.window_commands,positive_grants=tested.positive_grants,zero_grants=tested.zero_grants,
        peer_window_updates=tested.peer_updates,response_data_frames=tested.total_frames,response_wire_bytes=tested.total_wire_bytes,
        credit_park_cycles=tested.credit_stalls,raw_credit_probe_packets=tested.extra_packets,full_metadata_window_updates=tested.flow_updates,
        native_settings_ack_frames=len(tested.ack_frames),native_server_settings_frames=len(tested.server_frames),
        peer_commands=tested.peer_commands,actual_peer_settings_applied=tested.peer_settings,
        actual_settings_acknowledgments=tested.peer_received_acks,no_notice_fixture=True,actual_peer_memory_commits_before_results=True,
        server_settings_before_open_success=True,postcommit_gpu_cancellation_verified=False)
    return result


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def full_raw_dma_returns_with_actual_peer_state_and_server_settings(d):
    await run_bidirectional(d,bench_factory=PeerBench,memory_factory=SeparateMemory,extra_result=acceptance)
