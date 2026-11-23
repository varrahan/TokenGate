"""Directed actual FORMAT ACK faults and same-scope retry without global reset."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'build/experiments/receive-format/sim';folder.mkdir(parents=True,exist_ok=True)
    text='''"""Real global FORMAT clears retained RX records through acknowledged writes."""
import hashlib,json,os
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from test_raw_shutdown_faults import FaultBench
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles
from receive_format_witness import ReceiveFormatWitness


class FormatBench(FaultBench):
    async def formatting(self,expected=0,*,maintenance=True,stream_base=None,stream_bytes=None):
        self.configure();self.set(maintenance_grant=int(maintenance),control_maintenance=1,
            control_op=4,control_user=0,control_stream=0,control_generation=0,control_address=0)
        if stream_base is not None:self.set(cfg_receive_stream_base=stream_base)
        if stream_bytes is not None:self.set(cfg_receive_stream_bytes=stream_bytes)
        await self.send('control_valid','control_ready')
        # Only mutate public inputs after their real handshake. The production
        # operation must continue using its captured runtime arena and authority.
        self.poison();self.set(control_op=7,control_user=65535,control_maintenance=0,maintenance_grant=0)
        await self.wait('control_result_valid')
        result=tuple(value(self.d,n) for n in ReceiveFormatWitness.fields)
        assert result[0]==expected,result
        if expected==5:assert result[:3]==(5,7,0x75),result
        assert result[3]==4
        for _ in range(13):
            await cycles(self.d)
            assert value(self.d,'control_result_valid') and result==tuple(value(self.d,n) for n in ReceiveFormatWitness.fields)
            assert not value(self.d,'s_axis_rx_tready') and not value(self.d,'s_axis_generated_tready')
        await self.ack('control_result_valid','control_result_ready',0)
        return result


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def actual_format_ack_faults_retry_and_captured_scope(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    meta=json.loads((folder/'fixture_manifest.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    reference=json.loads((folder/'journaled_control_reference.json').read_text())
    image=bytearray(b''.join(int(s,16).to_bytes(8,'little') for s in (folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==meta['loaded_image_sha256'];initial=bytes(image)
    memory=SeparateMemory(d,image);b=FormatBench(d,layout,memory,reverse);b.allow_quarantine=True
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,
        window_req_valid=0,window_rsp_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,
        rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();witness=ReceiveFormatWitness(d)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in (b.ready_driver(),b.observe(),b.actual_observer(),witness.observe()):cocotb.start_soon(worker)
    await cycles(d,5);b.set(rst=0)
    for prefix in ('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    before=b.commands[26]
    missing_authority=await b.formatting(7,maintenance=False)
    assert missing_authority[:3]==(7,2,0) and b.commands[26]==before
    await b.formatting()
    before=b.commands[26]
    bad_geometry=await b.formatting(2,stream_bytes=layout[14]//4-1)
    assert bad_geometry[:3]==(2,1,0) and b.commands[26]==before
    await b.formatting()
    # Create the stale ledger using production OPEN and actual HTTP/2 HEADERS.
    await b.open();await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1)
    await b.admit_headers(reference,2,1)
    base=0x7e6000;size=layout[14]//4
    assert image[base:base+size]!=bytes(size)
    cases=[]
    for phase in range(size//8):
        b.phase=f'FORMAT receive ACK {phase}'
        before=b.commands[26];b.set(fault_client=26,fault_target=phase,fault_arm=1)
        await cycles(d);b.set(fault_arm=0)
        await b.formatting(5)
        assert value(d,'fault_injected') and b.commands[26]-before==phase+1
        assert value(d,'receive_recovery_required') and value(d.dut.core,'rx_format_failed')
        assert value(d,'receive_fault_memory_status')==0x75
        b.set(fault_client=-1)
        # Removing injection cannot replay any uncertain operation or admit work.
        before=b.commands[26]
        for _ in range(19):
            await cycles(d)
            assert b.commands[26]==before and value(d,'receive_recovery_required')
            assert not value(d,'s_axis_rx_tready') and not value(d,'s_axis_generated_tready')
            assert not value(d,'window_req_ready') and not value(d,'command_ready')
        if phase==size//8-1:
            # A different valid receive arena cannot clear the original
            # uncertain scope. No BFM write or reset helps this retry.
            saved=bytes(image[0x7e6100:0x7e6100+size])
            mismatch=await b.formatting(6,stream_base=0x7e6100)
            assert mismatch[:3]==(6,1,0) and b.commands[26]==before
            assert value(d,'receive_recovery_required') and value(d,'receive_fault_memory_status')==0x75
            assert bytes(image[0x7e6100:0x7e6100+size])==saved
        await b.formatting()
        assert b.commands[26]-before==size//8
        assert not value(d,'receive_recovery_required') and not value(d,'receive_fault_valid')
        assert not value(d.dut.core,'rx_format_failed') and image[base:base+size]==bytes(size)
        cases.append(dict(phase=phase,actual_error=0x75,explicit_same_scope_retry_without_reset=True))
    # The successfully reformatted scope admits real work again.
    await b.open();await b.packet(0,3,bytes.fromhex(reference['initial_packet']),1)
    await b.admit_headers(reference,4,1)
    assert image[base:base+size]!=bytes(size) and not value(d,'receive_recovery_required')
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data==initial
    assert not any(b.pending) and not b.packet_bytes
    result=dict(phase='passed',actual_format_transactions=witness.result(),actual_format_ack_fault_cases=cases,
        captured_runtime_scope_and_maintenance_verified=True,actual_pool_lock_for_format_verified=True,
        held_format_results_verified=True,explicit_same_scope_retry_without_global_reset=True,
        missing_maintenance_rejected_without_receive_memory=True,invalid_receive_geometry_rejected_without_receive_memory=True,
        mismatched_receive_scope_cannot_clear_quarantine=True,
        post_retry_open_and_native_headers_admitted=True,complete_model_prefix_immutable=True,
        retained_window_warm_reset_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\\n')
'''
    # The override keeps the established profile filename, so import its base
    # directly rather than importing the replacement module recursively.
    text=text.replace('from test_raw_shutdown_faults import FaultBench','from test_raw_shutdown_controls import Bench as FaultBench')
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (folder/'generation.json').write_text(json.dumps(dict(generator_sha256=sha(Path(__file__)),
        fixture_sha256=sha(output),witness_sha256=sha(root/'sim/cocotb/receive_format_witness.py'),
        actual_execution_verified=False),indent=2)+'\n')
    print(output)


if __name__=='__main__':main()
