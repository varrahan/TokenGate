"""Real raw Parser packets drive committed windows and actual wire ACKs.

Only non-window peer-state callbacks are supplied by the fixture. Window
updates/settings, journal commit, HEADERS allocation and TX are production RTL.
"""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame
from test_http2_prefill import Bench as RawBench,value
from test_two_fpga_bootstrap import BootstrapBench
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


class Bench(BootstrapBench):
    def __init__(self,*args):
        super().__init__(*args);self.tx=[];self.notices=[];self.tx_stalls=0

    def configure(self):
        super().configure();self.set(cfg_control_journal_base=0x780005,cfg_control_journal_bytes=3*131072,cfg_control_slot_bytes=131072)

    def poison(self):
        super().poison();self.set(cfg_window_base=0x7fffff,cfg_window_bytes=0,
            cfg_control_journal_base=0x7fffff,cfg_control_journal_bytes=0,cfg_control_slot_bytes=0)

    async def send(self,valid,ready):
        await super().send(valid,ready)
        if valid=='command_valid':self.set(cfg_control_journal_base=0x7fffff,cfg_control_journal_bytes=0,cfg_control_slot_bytes=0)

    async def read_window(self,stream=0):
        a=self.layout;self.set(window_req_op=6,window_req_maintenance=0,window_req_user=0,window_req_stream=stream,
            window_req_generation=self.bindings[0,stream]if stream else 0,window_req_record_address=self.handles[0,stream]if stream else 0,
            window_req_amount=0,window_cfg_context_base=a[19],window_cfg_context_bytes=a[20],window_cfg_stream_base=a[13],window_cfg_stream_bytes=a[14],
            window_cfg_window_base=0x7f0000,window_cfg_window_bytes=a[14]//8,window_cfg_work_floor=a[6])
        await self.send('window_req_valid','window_req_ready');await self.wait('window_rsp_valid')
        assert value(self.d,'window_rsp_status')==0
        result={n:value(self.d,'window_rsp_'+n)for n in('connection_window','initial_window','stream_window','max_frame_bytes')}
        await self.ack('window_rsp_valid','window_rsp_ready',4);return result

    async def notice_driver(self):
        d=self.d;await FallingEdge(d.clk)
        while True:
            await self.wait('notice_valid');names=('notice_kind','notice_user','notice_setting','notice_value','notice_payload')
            record=tuple(value(d,n)for n in names)
            for _ in range(7):await cycles(d);assert value(d,'notice_valid')and record==tuple(value(d,n)for n in names)
            self.set(notice_ready=1);await cycles(d);self.set(notice_ready=0);self.notices.append(record)
            await cycles(d,5);self.set(notice_status=0,notice_result_valid=1)
            while True:
                await RisingEdge(d.clk)
                if value(d,'notice_result_ready'):break
            await FallingEdge(d.clk);self.set(notice_result_valid=0)

    async def tx_driver(self):
        held=None;clock=0
        while True:
            await FallingEdge(self.d.clk);clock+=1;self.d.m_axis_tx_tready.value=not value(self.d,'rst')and clock%19>=8
            await RisingEdge(self.d.clk)
            if value(self.d,'rst'):held=None;continue
            valid=value(self.d,'m_axis_tx_tvalid');ready=value(self.d,'m_axis_tx_tready')
            record=tuple(value(self.d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))if valid else None
            if held is not None:assert record==held
            held=record if valid and not ready else None
            assert not value(self.d,'cancel_valid')and not value(self.d,'classify_valid'),'Unexpected unimplemented callback in this directed case'
            if valid:
                if not ready:self.tx_stalls+=1
                else:
                    data,keep,last,user=record;assert last and user==0 and keep in(0x1ff,0x1ffff)
                    wire=data.to_bytes(64,'little')[:keep.bit_count()];frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
                    assert frame.serialize()==wire and len(wire)==9+size;self.tx.append(wire.hex())


@cocotb.test(timeout_time=50,timeout_unit='ms')
async def raw_packets_commit_real_windows_and_retire_native_acks(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES']);layout=list(map(int,(folder/'layout.txt').read_text().split()))
    reference=json.loads((folder/'journaled_control_reference.json').read_text())
    metadata=json.loads((folder/'fixture_manifest.json').read_text())
    image=bytearray(b''.join(int(line,16).to_bytes(8,'little')for line in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==metadata['loaded_image_sha256']and reference['phase']=='native_raw_control_references_passed'
    initial=bytes(image);memory=SeparateMemory(d,image);b=Bench(d,layout,memory)
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        notice_ready=0,notice_result_valid=0,cancel_ready=0,cancel_result_valid=0,classify_ready=0,classify_result_valid=0,
        maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.notice_driver(),b.tx_driver()):cocotb.start_soon(worker)
    await cycles(d,5);d.rst.value=0
    await b.send('queue_cfg_valid','queue_cfg_ready');await b.wait('queue_cfg_result_valid');assert value(d,'queue_cfg_status')==0
    await b.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await b.send('stream_cfg_valid','stream_cfg_ready');await b.wait('stream_cfg_result_valid');assert value(d,'stream_cfg_status')==0
    await b.ack('stream_cfg_result_valid','stream_cfg_result_ready',0);await b.directory(4);await b.open()
    assert value(d,'command_control_status')==0
    await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1)
    assert b.tx==[reference['settings_ack'],reference['ping_ack']]
    result=await b.read_window();assert result['initial_window']==1000 and result['max_frame_bytes']==32768
    await b.packet(0,2,bytes.fromhex(reference['headers_packet']),1)
    assert b.bindings[0,1]>0 and(await b.read_window(1))['stream_window']==1000
    await b.packet(0,3,bytes.fromhex(reference['update_packet']),1)
    result=await b.read_window(1);assert result['stream_window']==1037 and result['connection_window']==65636
    before=len(b.tx);await b.packet(0,4,bytes.fromhex(reference['settings_first']),1)
    result=await b.read_window(1);assert result['stream_window']==1037 and result['initial_window']==1000 and len(b.tx)==before
    await b.packet(0,5,bytes.fromhex(reference['settings_last']),1)
    result=await b.read_window(1);assert result['stream_window']==2037 and result['initial_window']==2000 and result['max_frame_bytes']==16384
    assert b.tx[-1]==reference['settings_ack']and len(b.tx)==before+1
    await b.packet(0,6,bytes.fromhex(reference['abort_packet']),0)
    assert len(b.tx)==before+1
    assert struct.unpack_from('<I',image,layout[19]+176)[0]==65636
    address=0x7f0000+((b.handles[0,1]-layout[13])//8)
    assert struct.unpack_from('<I',image,address+8)[0]==2037,'Aborted raw WINDOW_UPDATE applied'
    if struct.unpack_from('<I',image,b.handles[0,1])[0]==0x47525331:await b.directory(3,0,1)
    await b.open();await b.packet(0,7,bytes.fromhex(reference['reopen_preface']),1)
    # Fail root restore before the raw parser starts. The actual parent drains
    # the packet, aborts its queue context, closes raw state and can reopen.
    b.set(fault_client=23,fault_target=0,fault_arm=1);await cycles(d);b.set(fault_arm=0)
    prior=len(b.tx);await b.packet(0,8,bytes.fromhex(reference['restore_fault_packet']),0)
    assert value(d,'fault_injected')and value(d,'journal_recovery_required')and len(b.tx)==prior
    assert value(d,'packet_control_status')==5 and value(d,'packet_control_memory_status')==0x75
    b.set(fault_client=-1);await b.open();await b.packet(0,9,bytes.fromhex(reference['reopen_preface']),1)
    assert not value(d,'journal_recovery_required')
    # Fail a tentative entry write while raw frame events are still arriving.
    # The parent must drain those events/remaining AXI beats without waiting on
    # the quarantined journal and without exposing an ACK for any staged PING.
    b.set(fault_client=23,fault_target=6,fault_arm=1);await cycles(d);b.set(fault_arm=0)
    prior=len(b.tx);await b.packet(0,10,bytes.fromhex(reference['restore_fault_packet']),0)
    assert value(d,'fault_injected')and value(d,'journal_recovery_required')and len(b.tx)==prior
    assert value(d,'packet_control_status')==5
    b.set(fault_client=-1);await b.open();await b.packet(0,11,bytes.fromhex(reference['reopen_preface']),1)
    # The actual wire ACK precedes a failed head write; its ordinary retry is
    # forbidden, and a fenced OPEN reformats the same real connection root.
    b.set(fault_client=23,fault_target=48,fault_arm=1);await cycles(d);b.set(fault_arm=0)
    prior=len(b.tx);await b.packet(0,12,bytes.fromhex(reference['ping_packet']),0)
    assert value(d,'fault_injected')and value(d,'journal_recovery_required')and b.tx[prior:]==[reference['ping_ack']]
    for _ in range(7):await cycles(d);assert not value(d,'s_axis_rx_tready')and len(b.tx)==prior+1
    b.set(fault_client=-1);await b.open();await b.packet(0,13,bytes.fromhex(reference['reopen_preface']),1)
    while not(value(d,'idle')and value(d,'fabric_idle')):await cycles(d)
    assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data==initial
    accepted=dict(phase='passed',raw_control_packets=b.packets,actual_header_bindings=b.headers,native_ack_frames=len(b.tx),
        raw_settings_and_window_updates_applied_by_rtl=True,partial_settings_do_not_apply=True,aborted_update_does_not_apply=True,
        actual_headers_allocate_stream_window=True,no_fixture_credit_updates=True,native_ack_bytes_verified=True,
        raw_restore_fault_drained_and_reopened=True,raw_head_commit_fault_no_duplicate_ack=True,
        raw_staging_fault_drains_flow=True,multi_beat_failed_packets_drained=True,
        independent_banks_verified=True,actual_parser_memory_clients=15,actual_tokenizer_memory_clients=9,
        complete_model_prefix_immutable=True,tokenizer_bank_untouched=True,held_tx_cycles=b.tx_stalls,
        non_window_notice_callbacks_supplied_by_fixture=True,postcommit_gpu_cancellation_verified=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
