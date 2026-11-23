"""Inject actual memory ACK failures at every raw shutdown mutation phase."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import with_timeout
from hyperframe.frame import GoAwayFrame,RstStreamFrame
from test_raw_shutdown_controls import Bench
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


class FaultBench(Bench):
    window_base=0x7f0000
    def configure(self):
        super().configure();self.set(cfg_window_base=self.window_base)
    async def send(self,valid,ready):
        try:await with_timeout(super().send(valid,ready),400,timeout_unit='us')
        except cocotb.triggers.SimTimeoutError:
            core=self.d.dut.core
            diagnostic={n:value(core,n)for n in('window_owner','shutdown_dir_owner','return_pending','shutdown_busy',
                'shutdown_recovery_required','f_cfg_quiescent','allow_config','rx_active','f_idle',
                'service_control_req_valid','service_control_req_ready','service_control_rsp_valid')}
            diagnostic.update(shutdown_state=value(core.shutdown,'state'),forward_state=value(core.forward,'state'))
            raise AssertionError(('Input handshake timeout',valid,ready,self.phase,diagnostic))


async def bootstrap(b,reference):
    d=b.d
    # Reset may clear uncertain owners only after their actual promises have
    # retired. Durable roots are then explicitly reformatted by production RTL.
    assert not any(b.pending)and not b.packet_bytes and value(d,'fabric_idle')
    assert not value(d,'m_axis_tx_tvalid')and not value(d,'response_record_lease_active')
    assert not value(d.dut.core,'return_pending')and not value(d,'response_result_retirement_pending')
    b.set(rst=1,fault_client=-1,fault_arm=0,window_req_valid=0,window_rsp_ready=0,
        s_axis_generated_tvalid=0,response_result_ready=0,queue_cfg_clear=1,maintenance_grant=1)
    # Global reset restarts the admission generation counter. An old external
    # window arena is therefore not reusable solely because reset was asserted.
    # Provision a fresh disjoint zeroed arena; all roots/bindings are still
    # initialized by the real FORMAT/OPEN/admission services, with no BFM writes.
    b.window_base+=64
    assert b.window_base+layout_bytes(b)<0x800000
    assert b.memory.data[b.window_base:b.window_base+layout_bytes(b)]==bytes(layout_bytes(b))
    b.closed.clear();b.configure();await cycles(d,5);b.set(rst=0)
    for prefix in('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    await b.directory(4);await b.open();await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1)
    await b.admit_headers(reference,2,1)


def layout_bytes(b):return b.layout[14]//8


@cocotb.test(timeout_time=50,timeout_unit='ms')
async def raw_shutdown_memory_failures_preserve_quarantine_and_ownership(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    reference=json.loads((folder/'journaled_control_reference.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    manifest=json.loads((folder/'fixture_manifest.json').read_text())
    image=bytearray(b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==manifest['loaded_image_sha256']
    initial=bytes(image);memory=SeparateMemory(d,image);b=FaultBench(d,layout,memory,reverse);b.allow_quarantine=True
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,
        window_req_valid=0,window_rsp_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,
        rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.actual_observer()):cocotb.start_soon(worker)
    await cycles(d,5);cases=[]
    # Applied writes return an error, rather than silently disappearing. The
    # last-write cases therefore exercise genuinely uncertain durable state.
    for kind,client,count in(('directory',0,9),('window',22,14),('peer',24,18)):
        for phase in range(count):
            await bootstrap(b,reference);b.phase=f'{kind} shutdown ACK fault {phase}'
            before=len(b.wire);processed=len(b.processed);start=b.commands[client]
            b.set(fault_client=client,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
            if kind=='peer':
                frame=GoAwayFrame(0);frame.last_stream_id=0;frame.error_code=11
            else:frame=RstStreamFrame(1);frame.error_code=8
            await b.packet(0,3,frame.serialize(),0)
            assert value(d,'fault_injected'),(kind,phase,b.commands[client]-start)
            assert value(d,'shutdown_memory_status')==0x75 and value(d,'shutdown_recovery_required')
            assert value(d,'packet_control_memory_status')==0x75 and value(d,'transport_packet_http2_error')==2
            assert value(d,'shutdown_status')!=0 and not value(d,'cfg_quiescent')
            assert len(b.processed)-processed==int(kind=='directory')
            assert len(b.wire)==before and not value(d,'response_result_valid')
            assert b.commands[client]-start==phase+1,(kind,phase,b.commands[client]-start)
            b.set(fault_client=-1)
            # A global shutdown quarantine must also stop new external window
            # mutations, including after a directory/peer failure when the
            # window engine itself is still healthy. Observe admission only;
            # retain VALID through the explicit fenced reset below.
            a=b.layout;b.set(window_req_op=6,window_req_maintenance=0,window_req_user=0,window_req_stream=0,
                window_req_generation=0,window_req_record_address=0,window_req_amount=0,
                window_cfg_context_base=a[19],window_cfg_context_bytes=a[20],window_cfg_stream_base=a[13],window_cfg_stream_bytes=a[14],
                window_cfg_window_base=b.window_base,window_cfg_window_bytes=a[14]//8,window_cfg_work_floor=a[6],window_req_valid=1)
            commands=b.commands[22]
            for _ in range(19):
                await cycles(d)
                assert not value(d,'window_req_ready'),'New external window accepted during global shutdown quarantine'
                assert not value(d,'s_axis_generated_tready')and not value(d,'control_ready')and not value(d,'s_axis_rx_tready')
                assert b.commands[22]==commands and value(d,'shutdown_recovery_required')
            assert not any(b.pending)and value(d,'fabric_idle')
            cases.append(dict(service=kind,phase=phase,memory_commands=phase+1,reset_processed=kind=='directory'))
            d._log.info('Verified shutdown fault %s/%d',kind,phase)
    # A final explicit reset plus real FORMAT/OPEN proves the prior quarantined
    # run has no abandoned memory, wire or return promise.
    await bootstrap(b,reference)
    rst=RstStreamFrame(1);rst.error_code=8;await b.packet(0,4,rst.serialize(),1)
    assert not value(d,'shutdown_recovery_required')and not any(b.pending)
    assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data==initial
    accepted=dict(phase='passed',actual_raw_fault_cases=cases,window_close_faults=14,directory_close_faults=9,
        peer_goaway_faults=18,actual_memory_error=0x75,applied_write_errors=True,
        new_admission_fenced_until_global_reset=True,global_resets_only_after_actual_owners_drained=True,
        successful_reset_after_explicit_root_reinitialization=True,fresh_disjoint_window_arena_per_global_reset=True,
        retained_window_arena_warm_reset_verified=False,complete_model_prefix_immutable=True,
        whole_rpc_gpu_image_lease_verified=False,physical_dma_packet_drain_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
