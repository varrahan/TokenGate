"""Exercise actual send-window FORMAT ACK faults and explicit same-scope retry."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/receive-format/sim/test_raw_shutdown_faults.py'
    text=source.read_text();text=text[:text.index('    before=b.commands[26]')]
    text=replace(text,'from receive_format_witness import ReceiveFormatWitness',
        'from window_format_witness import WindowFormatWitness as ReceiveFormatWitness')
    text=replace(text,'stream_bytes=None):','stream_bytes=None,window_base=None,window_bytes=None):')
    text=replace(text,'window_bytes=None):','window_bytes=None,fault_detail=2):')
    text=replace(text,'        if stream_base is not None:',
        '        if window_base is not None:self.set(cfg_window_base=window_base)\n'
        '        if window_bytes is not None:self.set(cfg_window_bytes=window_bytes)\n        if stream_base is not None:')
    text=replace(text,'(5,7,0x75)','(5,2,0x75)')
    text=replace(text,'if expected==5:assert result[:3]==(5,2,0x75)',
        'if expected==5:assert result[:3]==(5,fault_detail,0x75)')
    text=replace(text,'actual_format_ack_faults_retry_and_captured_scope','actual_window_format_ack_faults_and_same_scope_retry')
    text+='''    before=b.commands[22]
    denied=await b.formatting(7,maintenance=False)
    assert denied[:3]==(7,2,0) and b.commands[22]==before
    await b.formatting()
    before=b.commands[22]
    bad=await b.formatting(2,window_bytes=layout[14]//8-1)
    assert bad[:3]==(2,1,0) and b.commands[22]==before
    await b.formatting()
    await b.open();await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1)
    await b.admit_headers(reference,2,1)
    base=0x7f0000;size=layout[14]//8
    assert image[base:base+size]!=bytes(size)
    receive_cases=[]
    for phase in range(layout[14]//4//8):
        b.phase=f'receive FORMAT ACK {phase}'
        before=b.commands[26];windows_before=b.commands[22]
        b.set(fault_client=26,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        await b.formatting(5,fault_detail=7)
        assert value(d,'fault_injected') and b.commands[26]-before==phase+1
        assert b.commands[22]==windows_before and value(d,'receive_recovery_required')
        assert not value(d,'window_recovery_required') and not value(d.dut.core,'tx_format_error_owned')
        b.set(fault_client=-1);before=b.commands[26]
        for _ in range(19):
            await cycles(d)
            assert b.commands[26]==before and b.commands[22]==windows_before
            assert value(d,'receive_recovery_required') and not value(d,'s_axis_rx_tready')
        await b.formatting()
        assert b.commands[26]-before==12 and b.commands[22]-windows_before==6
        assert not value(d,'receive_recovery_required') and not value(d,'receive_fault_valid')
        assert not value(d.dut.core,'rx_format_failed')
        receive_cases.append(dict(phase=phase,error=0x75,send_ledger_not_touched_after_receive_fault=True))
    cases=[]
    for phase in range(size//8):
        b.phase=f'window FORMAT ACK {phase}'
        before=b.commands[22];b.set(fault_client=22,fault_target=phase,fault_arm=1)
        await cycles(d);b.set(fault_arm=0)
        await b.formatting(5)
        assert value(d,'fault_injected') and b.commands[22]-before==phase+1
        assert value(d,'window_recovery_required') and value(d,'response_recovery_required')
        assert value(d.dut.core,'rx_format_failed') and value(d.dut.core,'tx_format_error_owned')
        assert value(d.dut.core,'window_format_recovery_only')
        b.set(fault_client=-1);before=b.commands[22]
        for _ in range(19):
            await cycles(d)
            assert b.commands[22]==before and value(d,'window_recovery_required')
            assert not value(d,'s_axis_rx_tready') and not value(d,'s_axis_generated_tready')
            assert not value(d,'window_req_ready') and not value(d,'command_ready')
        if phase==size//8-1:
            saved=bytes(image[base+256:base+256+size])
            wrong=await b.formatting(6,window_base=base+256)
            assert wrong[:3]==(6,1,0) and b.commands[22]==before
            assert value(d,'window_recovery_required') and value(d.dut.core,'tx_format_error_owned')
            assert bytes(image[base+256:base+256+size])==saved
        await b.formatting()
        assert b.commands[22]-before==size//8 and image[base:base+size]==bytes(size)
        assert not value(d,'window_recovery_required') and not value(d,'response_recovery_required')
        assert not value(d.dut.core,'rx_format_failed') and not value(d.dut.core,'tx_format_error_owned')
        cases.append(dict(phase=phase,error=0x75,explicit_same_scope_retry_without_reset=True))
    await b.open();await b.packet(0,3,bytes.fromhex(reference['initial_packet']),1)
    await b.admit_headers(reference,4,1)
    assert image[base:base+size]!=bytes(size) and not value(d,'window_recovery_required')
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data==initial
    assert not any(b.pending) and not b.packet_bytes
    accepted=dict(phase='passed',actual_format_transactions=witness.result(),actual_window_format_fault_cases=cases,
        actual_receive_format_fault_cases=receive_cases,
        captured_window_scope_and_maintenance_verified=True,actual_pool_lock_for_both_ledgers_verified=True,
        explicit_same_scope_retry_without_reset=True,alternate_window_scope_cannot_clear_quarantine=True,
        missing_maintenance_and_invalid_window_geometry_rejected=True,
        actual_post_retry_open_and_headers_admitted=True,complete_model_prefix_immutable=True,
        whole_system_retained_state_recovery_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\\n')
'''
    folder=root/'build/experiments/window-format/sim';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(output),
        witness_sha256=sha(root/'sim/cocotb/window_format_witness.py'),actual_execution_verified=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(output)


if __name__=='__main__':main()
