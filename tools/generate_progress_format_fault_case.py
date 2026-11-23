"""Keep all eighteen RX/TX faults and add every real progress-clear ACK fault."""
import hashlib
import json
from pathlib import Path

from generate_receive_pool_experiment import replace


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/window-format/sim/test_raw_shutdown_faults.py'
    text=source.read_text()
    text=replace(text,'from window_format_witness import WindowFormatWitness as ReceiveFormatWitness',
        'from progress_format_witness import ProgressFormatWitness as ReceiveFormatWitness')
    text=replace(text,'window_bytes=None,fault_detail=2):',
        'window_bytes=None,fault_detail=2,progress_base=None,progress_bytes=None):')
    text=replace(text,'        self.configure();self.set(maintenance_grant=int(maintenance),control_maintenance=1,',
        '        self.response_configuration(0)\n'
        '        if progress_base is not None:self.set(cfg_response_progress_base=progress_base)\n'
        '        if progress_bytes is not None:self.set(cfg_response_progress_bytes=progress_bytes)\n'
        '        self.set(maintenance_grant=int(maintenance),control_maintenance=1,')
    text=replace(text,'        self.poison();self.set(control_op=7,',
        '        self.poison();self.set(cfg_response_progress_base=0x7fffff,cfg_response_progress_bytes=0)\n'
        '        self.set(control_op=7,')
    text=replace(text,'async def actual_window_format_ack_faults_and_same_scope_retry(d):',
        'async def all_three_format_ledger_ack_faults_and_same_scope_retry(d):')
    insertion='''    progress_cases=[]
    progress_base=reverse['response_progress']['base'];progress_bytes=reverse['response_progress']['bytes']
    before=b.commands[20]
    bad=await b.formatting(2,progress_bytes=progress_bytes-1)
    assert bad[:3]==(2,20,0) and b.commands[20]==before
    await b.formatting()
    for phase in range(progress_bytes//8):
        b.phase=f'progress FORMAT ACK {phase}'
        before=b.commands[20]
        b.set(fault_client=20,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        await b.formatting(5,fault_detail=18)
        assert value(d,'fault_injected') and b.commands[20]-before==phase+1
        assert value(d.dut.core,'progress_format_quarantined') and value(d.dut.core,'rx_format_failed')
        assert not value(d,'receive_recovery_required') and not value(d,'window_recovery_required')
        b.set(fault_client=-1);before=b.commands[20]
        for _ in range(19):
            await cycles(d)
            assert b.commands[20]==before and value(d.dut.core,'progress_format_quarantined')
            assert not value(d,'s_axis_rx_tready') and not value(d,'s_axis_generated_tready')
            assert not value(d,'window_req_ready') and not value(d,'command_ready')
        if phase==progress_bytes//8-1:
            alternate=progress_base+256;prior=bytes(image[alternate:alternate+progress_bytes])
            wrong=await b.formatting(7,progress_base=alternate)
            assert wrong[:3]==(7,19,0) and b.commands[20]==before
            assert value(d.dut.core,'progress_format_quarantined')
            assert bytes(image[alternate:alternate+progress_bytes])==prior
        await b.formatting()
        assert b.commands[20]-before==progress_bytes//8
        assert image[progress_base:progress_base+progress_bytes]==bytes(progress_bytes)
        assert not value(d.dut.core,'progress_format_quarantined') and not value(d.dut.core,'rx_format_failed')
        progress_cases.append(dict(phase=phase,error=0x75,actual_commands_before_error=phase+1,
            explicit_same_scope_retry_without_reset=True))
'''
    text=replace(text,"    await b.open();await b.packet(0,3,bytes.fromhex(reference['initial_packet']),1)",
        insertion+"    await b.open();await b.packet(0,3,bytes.fromhex(reference['initial_packet']),1)")
    text=replace(text,"accepted=dict(phase='passed',actual_format_transactions=witness.result(),",
        "accepted=dict(phase='passed',actual_progress_format_fault_cases=progress_cases,actual_format_transactions=witness.result(),")
    folder=root/'build/experiments/progress-format/faults';folder.mkdir(parents=True,exist_ok=True)
    fixture=folder/'test_raw_shutdown_faults.py';fixture.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(fixture),
        witness_sha256=sha(root/'sim/cocotb/progress_format_witness.py'),receive_faults=12,send_faults=6,progress_faults=12,
        full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
