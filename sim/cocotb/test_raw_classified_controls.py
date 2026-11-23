"""Missing-key controls read actual raw/admission history under the real fence."""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame,WindowUpdateFrame
from test_raw_peer_controls import Bench as PeerBench
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


class Bench(PeerBench):
    def __init__(self,*args):super().__init__(*args);self.queries=[];self.history_reads=0;self.history_held=0
    async def tx_driver(self):
        held=None;clock=0
        while True:
            await FallingEdge(self.d.clk);clock+=1;self.d.m_axis_tx_tready.value=not value(self.d,'rst')and clock%19>=8
            await RisingEdge(self.d.clk)
            if value(self.d,'rst'):held=None;continue
            valid=value(self.d,'m_axis_tx_tvalid');ready=value(self.d,'m_axis_tx_tready')
            record=tuple(value(self.d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))if valid else None
            if held is not None:assert held==record
            held=record if valid and not ready else None
            assert not value(self.d,'cancel_valid'),'Cancellation fixture used by classification case'
            if valid:
                if not ready:self.tx_stalls+=1
                else:
                    data,keep,last,user=record;assert last and user==0 and keep in(0x1ff,0x1ffff)
                    wire=data.to_bytes(64,'little')[:keep.bit_count()];frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
                    assert frame.serialize()==wire and len(wire)==size+9;self.tx.append(wire.hex())
    async def history_observer(self):
        d=self.d;c=d.dut.core.controls.classifier;f=d.dut.core.forward;pending=None;reads=0
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            if value(c,'req_valid')and value(c,'req_ready'):
                assert pending is None and value(c,'history_fence')and value(f,'state')==26
                assert all(value(f,n)for n in('p_packet_result_valid','p_packet_committed','r_idle','a_idle','h_idle'))
                assert not any(value(f,n)for n in('header_pending','router_active','control_owner'))
                pending=(value(c,'req_user'),value(c,'req_stream'));reads=0
            if pending is not None:
                assert value(c,'history_fence'),'Actual parent released admission history during classification'
                self.history_held+=1
            if value(d,'mem_valid')>>25&value(d,'mem_ready')>>25&1:
                assert pending is not None and not(value(d,'mem_write')>>25&1)
                address=value(d,'mem_addr')>>(25*23)&0x7fffff
                assert address==self.layout[19]+pending[0]*256+(160 if reads else 0)
                assert value(d,'mem_bytes')>>(25*4)&15==8 and value(d,'mem_data')>>(25*72)&((1<<72)-1)==0
                reads+=1;self.history_reads+=1
            if value(c,'rsp_valid')and value(c,'rsp_ready'):
                assert pending==(value(c,'rsp_user'),value(c,'rsp_stream'))
                self.queries.append((*pending,value(c,'rsp_status'),value(c,'rsp_closed'),value(c,'rsp_last_stream'),reads));pending=None
    async def update(self,stream,tag,commit=1):
        frame=WindowUpdateFrame(stream);frame.window_increment=1;await self.packet(0,tag,frame.serialize(),commit)


@cocotb.test(timeout_time=50,timeout_unit='ms')
async def actual_raw_missing_keys_use_committed_admission_history(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES']);layout=list(map(int,(folder/'layout.txt').read_text().split()))
    reference=json.loads((folder/'journaled_control_reference.json').read_text());meta=json.loads((folder/'fixture_manifest.json').read_text())
    native=json.loads((folder.parent/'http2-classifier-fixtures/cases.json').read_text());assert native['phase']=='native_missing_stream_references_passed'
    native_cases={(c['last_stream'],c['stream']):c for c in native['cases']}
    image=bytearray(b''.join(int(line,16).to_bytes(8,'little')for line in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==meta['loaded_image_sha256'];initial=bytes(image);memory=SeparateMemory(d,image);b=Bench(d,layout,memory)
    assert not hasattr(d,'classify_ready')and not hasattr(d,'classify_result_valid')and not hasattr(d,'notice_ready')
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        cancel_ready=0,cancel_result_valid=0,maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.tx_driver(),b.history_observer()):cocotb.start_soon(worker)
    await cycles(d,5);d.rst.value=0
    await b.send('queue_cfg_valid','queue_cfg_ready');await b.wait('queue_cfg_result_valid');assert value(d,'queue_cfg_status')==0;await b.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await b.send('stream_cfg_valid','stream_cfg_ready');await b.wait('stream_cfg_result_valid');assert value(d,'stream_cfg_status')==0;await b.ack('stream_cfg_result_valid','stream_cfg_result_ready',0)
    await b.directory(4);await b.open();await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1)
    wire=bytes.fromhex(reference['headers_packet']);headers,size=Frame.parse_frame_header(memoryview(wire[:9]));headers.parse_body(memoryview(wire[9:]));headers.stream_id=5;headers_wire=headers.serialize()
    skipped=WindowUpdateFrame(1);skipped.window_increment=1
    await b.packet(0,2,headers_wire+skipped.serialize(),1);assert b.bindings[0,5]>0
    assert b.queries[-1]==(0,1,0,1,5,2),'Same-packet update did not use newly committed admission history'
    assert struct.unpack_from('<Q',image,layout[19]+160)[0]==0x48325731|5<<32
    before=len(b.tx)
    for stream,tag in((1,3),(3,4)):
        await b.update(stream,tag);assert b.queries[-1]==(0,stream,0,int(native_cases[5,stream]['closed']),5,2)
    await b.directory(3,0,5);await b.update(5,5);assert b.queries[-1]==(0,5,0,1,5,2)
    assert len(b.tx)==before,'Ignored WINDOW_UPDATE generated a control frame'
    await b.update(2,6,0);assert not native_cases[5,2]['closed']and b.queries[-1]==(0,2,0,0,5,2)
    assert value(d,'journal_control_http2_error')==value(d,'transport_packet_http2_error')==1
    assert memory.data[layout[19]:layout[19]+8]==bytes(8)and value(d,'journal_recovery_required')
    await b.open();await b.packet(0,7,bytes.fromhex(reference['reopen_preface']),1);await b.update(1,8,0)
    assert b.queries[-1]==(0,1,0,0,0,2)and not native_cases[0,1]['closed']
    assert value(d,'transport_packet_http2_error')==1
    faults=0;tag=9
    for phase in(0,1):
        await b.open();await b.packet(0,tag,bytes.fromhex(reference['reopen_preface']),1);tag+=1
        await b.packet(0,tag,headers_wire,1);tag+=1
        b.set(fault_client=25,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        before=len(b.tx);await b.update(1,tag,0);tag+=1
        assert value(d,'fault_injected')and b.queries[-1]==(0,1,5,0,0,phase+1)
        assert value(d,'history_memory_status')==value(d,'packet_control_memory_status')==value(d,'journal_control_memory_status')==0x75
        assert len(b.tx)==before and memory.data[layout[19]:layout[19]+8]==bytes(8)and value(d,'journal_recovery_required')
        b.set(fault_client=-1);await b.directory(3,0,5);faults+=1
    await b.open();assert not value(d,'journal_recovery_required')and value(d,'history_queries')==8
    assert memory.data[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data==initial
    accepted=dict(phase='passed',raw_packets=b.packets,actual_header_bindings=b.headers,native_control_frames=len(b.tx),
        actual_history_queries=len(b.queries),actual_history_reads=b.history_reads,actual_history_fence_cycles=b.history_held,
        skipped_and_directory_closed_streams_ignored=True,future_and_even_idle_streams_protocol_error=True,
        actual_high_water_written_by_admission=True,actual_raw_admission_fence_verified=True,no_classification_or_notice_fixture=True,
        same_packet_headers_and_window_update_verified=True,
        native_h2_decisions_verified=True,protocol_error_reaches_transport_result=True,injected_history_memory_faults=faults,
        history_reads_are_read_only=True,read_failures_never_classified_closed=True,explicit_fenced_reopen=True,
        parser_memory_clients=17,tokenizer_memory_clients=9,complete_model_prefix_immutable=True,tokenizer_bank_untouched=True,
        cancellation_supplied_externally=True,postcommit_gpu_cancellation_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
