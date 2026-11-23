"""Raw requests and actual DMA IDs with framed returns and independent RX.

External grants are a test credit provider. Receiving WINDOW_UPDATE during a
blocked return is verified; applying signed connection/stream ledgers is not.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from test_bidirectional_application import JointBench, RESULTS, run_bidirectional
from test_http2_prefill import Bench, value
from test_two_fpga_application import SeparateMemory, separate_memory_acceptance
from test_tokenizer_mmio import cycles


class FramedJointBench(JointBench):
    def __init__(self,d,layout,memory,reverse):
        super().__init__(d,layout,memory,reverse,control=d.dut.core,return_bow=d.tokenizer.application.inverse.bow)
        self.oracle=json.loads((Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])/'framed_reference.json').read_text())
        assert self.oracle['phase']=='native_references_passed'
        self.response=d.dut.core.reverse.response
        self.job_frames=self.job_grants=0;self.job_reference=None
        self.wire_packet=bytearray();self.grpc_record=bytearray()
        self.total_frames=self.total_wire_bytes=self.credit_stalls=0
        self.metadata_acks=0;self.metadata_pending=False
        self.credit_paused=False;self.control_probe_started=False;self.control_probe_complete=False
        self.extra_packets=0;self.observed_updates=[];self.rx_during_return=0

    async def response_ready(self):
        while True:
            await FallingEdge(self.d.clk)
            active=not value(self.d,'rst')
            self.d.m_axis_tx_tready.value=active and self.clocks%31>=9 and self.response_rng.randrange(4)!=0
            grants=self.job_reference['grants'] if self.job_reference else []
            self.d.frame_req_ready.value=active and not self.credit_paused and self.clocks%29>=11 and self.response_rng.randrange(4)!=0
            self.d.frame_grant_bytes.value=grants[self.job_grants] if self.job_grants<len(grants) else 0

    async def send_response(self,reference,chunk,generation,error=(0,0,0),**kwargs):
        good=error[1]==0
        probe=good and not self.control_probe_started
        pattern='prefix_split' if probe else 'normal'
        self.job_reference=self.oracle['frames'][f"{reference['stream']}:{chunk['packet_hex']}:{pattern}"] if good else None
        self.job_frames=self.job_grants=0;self.wire_packet.clear();self.grpc_record.clear()
        self.metadata_acks=0;self.metadata_pending=False
        self.d.cfg_peer_max_frame_bytes.value=16384
        if probe:self.credit_paused=True;self.control_probe_started=True
        await super().send_response(reference,chunk,generation,error=error,**kwargs)
        if good:
            assert self.job_frames==len(self.job_reference['wire']) and self.job_grants==len(self.job_reference['grants'])
            assert self.metadata_acks==5
        else:assert self.job_frames==self.job_grants==0

    def capture(self,target,prefix,width,held,is_bow=False):
        if is_bow:return super().capture(target,prefix,width,held,True)
        valid=value(target,prefix+'tvalid');ready=value(target,prefix+'tready')
        snapshot=tuple(value(target,prefix+n)for n in('tdata','tkeep','tlast','tuser')) if valid else None
        if held is not None:assert snapshot==held,'Held wire beat changed'
        if valid:
            assert self.current_response is not None and self.job_reference is not None
            reference,chunk,_,_,expected,_=self.current_response
            assert value(self.d,'response_record_lease_active') and self.metadata_acks==5
            if not ready:self.response_stalls+=1
            else:
                data,keep,last,user=snapshot
                assert user==reference['connection'] and keep==(1<<keep.bit_count())-1
                assert last or keep.bit_count()==64
                for lane in range(64):
                    byte=data>>(8*lane)&255
                    if keep>>lane&1:self.wire_packet.append(byte)
                    else:assert byte==0
                if last:
                    raw=bytes(self.wire_packet)
                    assert raw.hex()==self.job_reference['wire'][self.job_frames],('HTTP/2 DATA frame',raw.hex())
                    assert len(raw)==9+int.from_bytes(raw[:3],'big') and raw[3:5]==b'\0\0'
                    self.grpc_record.extend(raw[9:]);self.job_frames+=1;self.total_frames+=1;self.total_wire_bytes+=len(raw)
                    self.wire_packet.clear()
                    if self.job_frames==len(self.job_reference['wire']):
                        record=bytes(self.grpc_record)
                        assert record[0]==0 and int.from_bytes(record[1:5],'big')==len(expected) and record[5:]==expected
                        self.tx.extend(record[5:]);self.tx_last=True
        return snapshot if valid and not ready else None

    async def response_observer(self):
        d=self.d
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            assert bool(value(self.control,'return_pending'))==self.gpu_owned
            gpu_accept=value(d,'s_axis_generated_tvalid') and value(d,'s_axis_generated_tready')
            rx_accept=value(d,'s_axis_rx_tvalid') and value(d,'s_axis_rx_tready')
            if self.gpu_owned:
                self.owned_schedule_cycles+=1
                assert not any(value(d,n)for n in('command_ready','stream_cfg_ready','queue_cfg_ready','cfg_schema_ready'))
                if rx_accept:
                    self.rx_during_return+=1
                    if value(self.control,'rx_active'):self.continued_rx_beats+=1
            if gpu_accept:
                assert not self.gpu_owned
                if value(self.control,'rx_active'):self.mid_packet_gpu_admissions+=1
                else:assert not rx_accept
                self.gpu_owned=True
            if value(d,'response_result_valid') and value(d,'response_result_ready'):
                assert self.gpu_owned;self.gpu_owned=False
            if rx_accept and not value(d,'s_axis_rx_tlast') and (0,1)in self.jobs:self.mid_packet_available=True
            if value(d,'m_axis_tokens_tvalid') and value(d,'m_axis_tokens_tready'):
                data,keep=value(d,'m_axis_tokens_tdata'),value(d,'m_axis_tokens_tkeep')
                self.dma_current.extend(data>>(32*lane)&0xffffffff for lane in range(16)if keep>>(4*lane)&15==15)
                if value(d,'m_axis_tokens_tlast'):
                    self.dma_packets.append((value(d,'dma_connection'),value(d,'dma_stream'),value(d,'dma_generation'),list(self.dma_current)))
                    self.dma_current.clear()
            if gpu_accept and value(d,'payload_lease_active'):self.early_gpu_admissions+=1
            if value(d,'payload_lease_active') and value(self.control,'r_directory_valid'):
                assert not value(self.control,'r_directory_ready'),'Return LOAD bypassed prefill authority'
                self.waited_for_prefill+=1
            self.return_lease_cycles+=value(d,'response_directory_lease_active')
            request=(value(d,'mem_valid')&value(d,'mem_ready'))>>20&1
            if request:
                self.reverse_memory_commands+=1
                assert value(d,'response_directory_lease_active')
                if value(d,'mem_write')>>20&1:
                    address=value(d,'mem_addr')>>(23*20)&0x7fffff
                    assert self.reverse['response_progress']['base']<=address<self.reverse['response_progress']['base']+self.reverse['response_progress']['bytes']
                    assert not self.metadata_pending
                    self.metadata_pending=True
            if value(d,'mem_rsp_valid')>>20&1 and value(d,'mem_rsp_ready')>>20&1 and self.metadata_pending:
                assert value(d,'mem_rsp_status')>>(8*20)&255==0
                self.metadata_pending=False;self.metadata_acks+=1
            if value(d,'frame_req_valid'):
                assert self.metadata_acks==5 and value(d,'response_result_progress_committed')
                assert value(d,'frame_req_user')==self.current_response[0]['connection']
                assert value(d,'frame_req_stream')==self.current_response[0]['stream']
                if value(d,'frame_req_ready'):
                    assert self.job_reference is not None
                    grant=value(d,'frame_grant_bytes')
                    assert 1<=grant<=value(d,'frame_req_max_bytes')
                    self.job_grants+=1
                else:self.credit_stalls+=1
            if value(d,'control_event_valid') and value(d,'control_event_ready') and value(d,'control_event_kind')==7:
                assert self.credit_paused and value(d,'response_record_lease_active') and self.total_frames==0
                self.observed_updates.append([value(d,'control_event_stream'),value(d,'control_event_arg0')])
            self.held_tx=self.capture(d,'m_axis_tx_',64,self.held_tx)
            self.held_bow=self.capture(self.return_bow,'m_egress_',16,self.held_bow,True)
            snapshot=tuple(value(d,n)for n in RESULTS) if value(d,'response_result_valid') else None
            if self.held_result is not None:assert snapshot==self.held_result
            self.held_result=snapshot if snapshot is not None and not value(d,'response_result_ready') else None
            if self.held_result is not None:
                self.response_held_cycles+=1
                assert not value(d,'s_axis_generated_tready') and value(d,'mem_valid')>>20&1==0

    async def directory(self,op,user=0,stream=0):
        if op==3 and (user,stream)in self.jobs:
            while not self.jobs[user,stream]['done']:
                if self.credit_paused and value(self.d,'frame_req_valid') and not self.control_probe_complete:
                    # The main packet driver is waiting here; send a new raw
                    # control-only packet through that same public RX port.
                    assert not self.wire_packet and self.total_frames==0
                    owner=self.current_response[0]['connection']
                    await Bench.packet(self,owner,0xf00d,bytes.fromhex(self.oracle['window_update_wire_hex']),1)
                    self.extra_packets+=1
                    assert self.observed_updates==self.oracle['window_updates']
                    assert value(self.d,'response_record_lease_active') and self.total_frames==0
                    self.control_probe_complete=True;self.credit_paused=False
                await cycles(self.d)
        await Bench.directory(self,op,user,stream)


def acceptance(memory,tested,initial):
    result=separate_memory_acceptance(memory,tested,initial)
    assert tested.control_probe_complete and tested.rx_during_return and tested.extra_packets==1
    assert tested.total_frames>=tested.response_chunks and tested.credit_stalls
    result.update(response_transport_framing_verified=True,actual_http2_window_update_ingress_verified=True,
        window_updates=tested.observed_updates,control_probe_packets=tested.extra_packets,
        response_data_frames=tested.total_frames,response_wire_bytes=tested.total_wire_bytes,
        credit_stall_cycles=tested.credit_stalls,rx_beats_during_return=tested.rx_during_return,
        shared_cached_directory_integrated=True,credit_ledger_verified=False,
        tokenizer_memory_fabric_integrated=True,parser_memory_clients=13)
    return result


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def raw_requests_actual_dma_framed_returns_and_control_progress(d):
    await run_bidirectional(d,bench_factory=FramedJointBench,memory_factory=SeparateMemory,extra_result=acceptance)
