"""Fault every durable root bootstrap phase in the actual 56-module Parser."""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from test_http2_prefill import Bench, value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


class BootstrapBench(Bench):
    def configure(self):
        super().configure(); self.set(cfg_window_base=0x7f0000,cfg_window_bytes=self.layout[14]//8)

    async def open(self, *, expected=0, cleanup=0):
        a=self.layout;self.configure()
        self.set(maintenance_grant=1,command_op=0,command_user=0,command_server_role=1,
            command_allow_push=0,command_max_frame_bytes=16384,command_buffer_base=a[28],command_buffer_bytes=a[29],
            command_table_base=a[30],command_table_bytes=a[31],command_scratch_base=a[32],command_scratch_bytes=a[33],
            command_hpack_maximum=4096,command_hpack_allowed=4096,command_header_list_limit=32768,
            command_required_maximum=4096,command_required_update=0)
        await self.send('command_valid','command_ready')
        self.set(command_user=65535,maintenance_grant=0,cfg_window_base=0x7fffff,cfg_window_bytes=0,
            cfg_context_base=0x7fffff,cfg_context_bytes=0,command_scratch_base=0x7fffff,command_scratch_bytes=0)
        await self.wait('rsp_valid')
        fields=('rsp_status','rsp_detail','rsp_memory_status','rsp_http2_error','rsp_user','rsp_command_op',
            'command_window_status','command_window_cleanup_status')
        result=tuple(value(self.d,n)for n in fields)
        assert result[0]==expected and result[4:6]==(0,0) and result[7]==cleanup,result
        assert not any(value(self.d,n)for n in('header_valid','m_axis_tokens_tvalid','m_axis_tx_tvalid'))
        if expected:
            assert result[2:4]==(0x75,2) and result[6]==5,result
            assert value(self.d,'window_recovery_required')
            if cleanup==0:assert self.memory.data[a[19]:a[19]+8]==bytes(8),'Failed OPEN left its raw connection active'
        else:
            assert result==(0,0,0,0,0,0,0,0),result
            assert struct.unpack_from('<I',self.memory.data,a[19])[0]==0x48324331
            words=struct.unpack_from('<6Q',self.memory.data,a[19]+168)
            assert words==(0x48324357,65535|(65535<<32),16384,a[13]|a[14]<<32,
                0x7f0000|(a[14]//8)<<32,a[19]|a[20]<<32),words
            assert not value(self.d,'window_recovery_required') and not value(self.d,'transport_recovery_required')
        for _ in range(9):
            await cycles(self.d);assert value(self.d,'rsp_valid')and tuple(value(self.d,n)for n in fields)==result
        await self.ack('rsp_valid','rsp_ready',0)

    async def recover_window(self):
        a=self.layout;self.configure()
        self.set(window_req_op=7,window_req_maintenance=1,window_req_user=0,window_req_stream=0,
            window_req_generation=0,window_req_record_address=0,window_req_amount=0,
            window_cfg_context_base=a[19],window_cfg_context_bytes=a[20],window_cfg_stream_base=a[13],window_cfg_stream_bytes=a[14],
            window_cfg_window_base=0x7f0000,window_cfg_window_bytes=a[14]//8,window_cfg_work_floor=a[6])
        await self.send('window_req_valid','window_req_ready');await self.wait('window_rsp_valid')
        assert value(self.d,'window_rsp_status')==0 and not value(self.d,'window_recovery_required')
        await self.ack('window_rsp_valid','window_rsp_ready',5)


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def actual_connection_bootstrap_all_memory_faults_and_cleanup_failure(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    metadata=json.loads((folder/'fixture_manifest.json').read_text())
    image=bytearray(b''.join(int(line,16).to_bytes(8,'little')for line in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==metadata['loaded_image_sha256']
    initial=bytes(image);m=SeparateMemory(d,image);b=BootstrapBench(d,layout,m)
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,flow_event_ready=1,
        window_req_valid=0,window_rsp_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,
        rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run())
    await cycles(d,5);d.rst.value=0
    await b.send('queue_cfg_valid','queue_cfg_ready');await b.wait('queue_cfg_result_valid')
    assert value(d,'queue_cfg_status')==0;await b.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await b.send('stream_cfg_valid','stream_cfg_ready');await b.wait('stream_cfg_result_valid')
    assert value(d,'stream_cfg_status')==0;await b.ack('stream_cfg_result_valid','stream_cfg_result_ready',0)
    await b.directory(4)
    await b.open()
    faults=0
    for phase in range(8):
        b.set(fault_client=22,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        await b.open(expected=9)
        assert value(d,'fault_injected') and not value(d,'transport_recovery_required')
        b.set(fault_client=-1);await b.recover_window();await b.open();faults+=1
    # Change the fault selector only after the root error is visible. The raw
    # CLOSE write then physically applies but also returns an error ACK.
    b.set(fault_client=22,fault_target=7,fault_arm=1);await cycles(d);b.set(fault_arm=0)
    opening=cocotb.start_soon(b.open(expected=9,cleanup=5))
    while not(value(d.dut.core,'init_window_rsp_valid')and value(d.dut.core,'init_window_rsp_status')==5):await FallingEdge(d.clk)
    b.set(fault_client=13,fault_target=0,fault_arm=1);await cycles(d);b.set(fault_arm=0)
    await opening
    assert value(d,'transport_recovery_required') and value(d,'window_recovery_required') and value(d,'fault_injected')
    b.set(fault_client=-1);await b.recover_window();await b.open()
    while not value(d,'fabric_idle'):await cycles(d)
    assert image[:layout[6]]==initial[:layout[6]] and m.tokenizer_data==initial
    accepted=dict(phase='passed',bootstrap_memory_phases=8,injected_bootstrap_faults=faults,
        double_fault_cleanup_cases=1,successful_opens=10,held_public_open_results_verified=True,
        raw_close_before_failed_open_result_verified=True,independent_raw_and_window_recovery_verified=True,
        poisoned_open_configuration_verified=True,actual_56_module_parser=True,parser_memory_clients=14,
        actual_shared_directory_and_window_service=True,complete_parser_model_prefix_immutable=True,
        untouched_tokenizer_bank=True,physical_interfaces_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
