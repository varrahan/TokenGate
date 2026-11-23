"""Actual raw peer SETTINGS/ACK state and server preface, without notice fixtures."""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from hyperframe.frame import SettingsFrame,PingFrame
from test_raw_journaled_controls import Bench as JournalBench
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles

PEER=0x7e4005


class Bench(JournalBench):
    def configure(self):
        super().configure();self.set(cfg_peer_base=PEER,cfg_peer_bytes=192)
    def poison(self):
        super().poison();self.set(cfg_peer_base=0x7fffff,cfg_peer_bytes=0)
    async def send(self,valid,ready):
        await super().send(valid,ready)
        if valid=='command_valid':self.set(cfg_peer_base=0x7fffff,cfg_peer_bytes=0)
    def peer(self,user=0):
        words=struct.unpack_from('<8Q',self.memory.data,PEER+64*user)
        assert words[0]&0xffffffff==0x48325031 and words[0]>>32&0xffff==user
        assert words[1]==192<<32|PEER and words[2]&0xffffffff==PEER+64*user
        return dict(table=words[3]&0xffffffff,concurrent=words[3]>>32,headers=words[4]&0xffffffff,
            push=words[4]>>32&1,pending=words[5]&0xffffffff,acks=words[5]>>32)
    async def open(self,*,expected=0):
        a=self.layout;self.configure()
        self.set(maintenance_grant=1,command_op=0,command_user=0,command_server_role=1,command_allow_push=0,command_max_frame_bytes=16384,
            command_buffer_base=a[28],command_buffer_bytes=a[29],command_table_base=a[30],command_table_bytes=a[31],
            command_scratch_base=a[32],command_scratch_bytes=a[33],command_hpack_maximum=4096,command_hpack_allowed=4096,
            command_header_list_limit=32768,command_required_maximum=4096,command_required_update=0)
        await self.send('command_valid','command_ready');self.poison();self.set(command_user=65535,maintenance_grant=0)
        await self.wait('rsp_valid');fields=('rsp_status','rsp_detail','rsp_memory_status','command_window_status','command_control_status','peer_format_status')
        r=tuple(value(self.d,n)for n in fields);assert r[0]==expected and r[3]==0,r
        if expected:assert r[2]==0x75 and r[4:]==(10,5)and self.memory.data[a[19]:a[19]+8]==bytes(8),r
        else:assert r==(0,0,0,0,0,0)and self.peer()['pending']==1,r
        assert not value(self.d,'m_axis_tx_tvalid'),'OPEN escaped before server SETTINGS wire retirement'
        for _ in range(9):await cycles(self.d);assert value(self.d,'rsp_valid')and r==tuple(value(self.d,n)for n in fields)
        await self.ack('rsp_valid','rsp_ready',0)
    async def close(self):
        self.configure();self.set(command_op=1,command_user=0,maintenance_grant=1)
        await self.send('command_valid','command_ready');await self.wait('rsp_valid');assert value(self.d,'rsp_status')==0
        await self.ack('rsp_valid','rsp_ready',0)


@cocotb.test(timeout_time=50,timeout_unit='ms')
async def actual_raw_peer_notices_server_preface_and_fault_recovery(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES']);layout=list(map(int,(folder/'layout.txt').read_text().split()))
    reference=json.loads((folder/'journaled_control_reference.json').read_text());meta=json.loads((folder/'fixture_manifest.json').read_text())
    image=bytearray(b''.join(int(line,16).to_bytes(8,'little')for line in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==meta['loaded_image_sha256'];initial=bytes(image)
    memory=SeparateMemory(d,image);b=Bench(d,layout,memory)
    assert not hasattr(d,'notice_ready')and not hasattr(d,'notice_result_valid'),'Python notice worker is still exposed'
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        cancel_ready=0,cancel_result_valid=0,classify_ready=0,classify_result_valid=0,
        maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.tx_driver()):cocotb.start_soon(worker)
    await cycles(d,5);d.rst.value=0
    await b.send('queue_cfg_valid','queue_cfg_ready');await b.wait('queue_cfg_result_valid');assert value(d,'queue_cfg_status')==0
    await b.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await b.send('stream_cfg_valid','stream_cfg_ready');await b.wait('stream_cfg_result_valid');assert value(d,'stream_cfg_status')==0
    await b.ack('stream_cfg_result_valid','stream_cfg_result_ready',0);await b.directory(4);await b.open()
    settings=SettingsFrame(0);ack=SettingsFrame(0);ack.flags.add('ACK')
    assert b.tx==[settings.serialize().hex()]and b.peer()['pending']==1 and value(d,'peer_format_status')==0
    await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1)
    assert b.peer()['table']==4096 and b.tx[-2:]==[reference['settings_ack'],reference['ping_ack']]
    result=await b.read_window();assert result['initial_window']==1000 and result['max_frame_bytes']==32768
    before=len(b.tx);await b.packet(0,2,ack.serialize(),1);assert b.peer()['pending']==0 and b.peer()['acks']==1 and len(b.tx)==before
    await b.packet(0,3,ack.serialize(),1);assert b.peer()['acks']==1 and len(b.tx)==before
    await b.packet(0,4,bytes.fromhex(reference['headers_packet']),1)
    assert b.bindings[0,1]>0 and(await b.read_window(1))['stream_window']==1000
    await b.packet(0,5,bytes.fromhex(reference['settings_first']),1)
    assert b.peer()['table']==4096 and(await b.read_window(1))['stream_window']==1000
    await b.packet(0,6,bytes.fromhex(reference['settings_last']),1)
    assert b.peer()['table']==2048 and(await b.read_window(1))['stream_window']==2000 and b.tx[-1]==reference['settings_ack']
    settings.settings={2:0,3:0,6:12345,1:512};await b.packet(0,7,settings.serialize(),1)
    peer=b.peer();assert(peer['push'],peer['concurrent'],peer['headers'],peer['table'])==(0,0,12345,512)
    # Committed receive PING ACK has no pending local PING and cannot generate
    # an ACK-of-ACK. A preceding malformed raw frame still cannot apply controls.
    ping=PingFrame(0);ping.flags.add('ACK');ping.opaque_data=b'ignored!';before=len(b.tx)
    await b.packet(0,8,ping.serialize(),1);assert len(b.tx)==before
    # The actual peer memory client fails after applying its final state write.
    # Journal completion fails, no ACK is sent, RAW is closed and new RX is fenced.
    d.fault_client.value=24;d.fault_target.value=17;d.fault_arm.value=1;await cycles(d);d.fault_arm.value=0
    settings.settings={1:99};before=len(b.tx);await b.packet(0,9,settings.serialize(),0)
    assert value(d,'fault_injected')and value(d,'packet_control_memory_status')==0x75 and value(d,'journal_recovery_required')
    assert len(b.tx)==before and memory.data[layout[19]:layout[19]+8]==bytes(8)
    d.fault_client.value=-1
    await b.directory(3,0,1);await b.open();assert not value(d,'journal_recovery_required')and b.peer()['pending']==1
    assert b.tx[-1]==SettingsFrame(0).serialize().hex()
    # Peer FORMAT and automatic server SETTINGS commit failures both suppress
    # public OPEN success. Reopen is explicitly fenced and starts a new wire owner.
    bootstrap_faults=0
    for phase in(0,9,10,18,19,27):
        await b.close();d.fault_client.value=24;d.fault_target.value=phase;d.fault_arm.value=1;await cycles(d);d.fault_arm.value=0
        before=len(b.tx);await b.open(expected=10)
        assert value(d,'fault_injected')and value(d,'command_control_status')==10 and value(d,'peer_format_memory_status')==0x75
        assert len(b.tx)==before+int(phase>=19)and memory.data[layout[19]:layout[19]+8]==bytes(8)
        d.fault_client.value=-1;await b.open();assert not value(d,'journal_recovery_required')and b.peer()['pending']==1;bootstrap_faults+=1
    assert memory.data[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data==initial
    accepted=dict(phase='passed',raw_packets=b.packets,actual_header_bindings=b.headers,native_frames=len(b.tx),
        no_notice_fixture=True,actual_raw_non_window_settings=True,server_settings_before_open_success=True,
        actual_settings_ack_tracking=True,no_ack_of_ack=True,partial_settings_and_real_windows=True,
        peer_memory_failure_suppresses_ack=True,raw_closed_before_failed_public_result=True,
        peer_initialization_and_wire_commit_faults=bootstrap_faults,explicit_fenced_reopen=True,
        parser_memory_clients=16,tokenizer_memory_clients=9,complete_model_prefix_immutable=True,tokenizer_bank_untouched=True,
        cancellation_and_classification_supplied_externally=True,postcommit_gpu_cancellation_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
