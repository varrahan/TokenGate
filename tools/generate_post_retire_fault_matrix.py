"""Generate one cold actual-ACK fault for every observed retirement transaction."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/post-commit-retire-fault-probe/test_raw_grpc_duplex.py'
    archive=root/'build/wsl-reports/raw_envelope_post_retire_memory_trace'
    accepted=json.loads((archive/'acceptance.json').read_text())
    assert json.loads((archive/'snapshot.json').read_text())['exit_code']==0 and accepted['phase']=='passed'
    trace=accepted['actual_retirement_memory']['actual_logical_client_acks']
    assert {n:len(a) for n,a in trace.items()}=={'0':20,'26':19}
    folder=root/'build/experiments/post-retire-fault-matrix';folder.mkdir(exist_ok=True)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original=source.read_text();cases={}
    for client in (0,26):
        for phase,ack in enumerate(trace[str(client)]):
            name=f'client_{client}_ack_{phase}'
            text=original.replace('from test_two_fpga_application import SeparateMemory',
                'from test_two_fpga_application import SeparateMemory\nfrom post_retire_fault_witness import PostRetireFaultWitness')
            expected=[{k:a[k] for k in ('write','address','bytes','data','response_data')} for a in trace[str(client)][:phase+1]]
            text=text.replace('    sampled={}',
                f'    sampled={{}}\n    client={client};fault_phase={phase}\n    expected={expected!r}\n'
                '    memory_fault=PostRetireFaultWitness(d,client,fault_phase,expected)\n'
                '    cocotb.start_soon(memory_fault.observe())\n'
                "    recovery='stream_recovery_required' if client==0 else 'receive_recovery_required'\n"
                '    command_counts=lambda:(b.commands[0],b.commands[26])')
            error=[13,0x85 if client==26 or ack['write'] else 0x82,0x75]
            replacements={
                "sampled['directory_commands_before']=b.commands[0]":"sampled['directory_commands_before']=b.commands[client]",
                'b.set(fault_client=0,fault_target=0,fault_arm=1)':'b.set(fault_client=client,fault_target=fault_phase,fault_arm=1)',
                "sampled['retirement_result']==[13,0x82,0x75]":f"sampled['retirement_result']=={error!r}",
                "value(d,'stream_recovery_required')":"value(d,recovery)",
                "b.commands[0]==sampled['directory_commands_before']+1":"b.commands[client]==sampled['directory_commands_before']+fault_phase+1",
                'commands=b.commands[0]':'commands=command_counts()',
                'b.commands[0]==commands':'command_counts()==commands',
                'actual_retirement_fault_client=0,actual_retirement_fault_ack_phase=0':'actual_retirement_fault_client=client,actual_retirement_fault_ack_phase=fault_phase',
                'actual_directory_commands_after_request=1,actual_rpc_record_remains_owned=True,':'actual_selected_client_commands_after_request=fault_phase+1,actual_ack_prefix=memory_fault.result(),\n        actual_rpc_header_cleared=header_cleared,actual_receive_closed=receive_closed,\n        actual_last_selected_write_applied=bool(expected[-1][\'write\']),',
            }
            for before,after in replacements.items():
                assert before in text,(name,before)
                text=text.replace(before,after)
            expected_header=client==26 or phase>=16
            expected_rx=(client==0 and phase>=17) or (client==26 and phase>=17)
            before='    assert image[address:address+8]!=bytes(8)'
            text=text.replace(before,
                "    header_cleared=image[address:address+8]==bytes(8)\n"
                "    receive_closed=bool(int.from_bytes(image[0x7e6008:0x7e6010],'little')>>63)\n"
                f'    assert header_cleared=={expected_header!r} and receive_closed=={expected_rx!r}\n'
                "    for record in expected:\n"
                "        if record['write']:\n"
                "            a=record['address'];assert int.from_bytes(image[a:a+8],'little')==record['data']")
            text=text.replace('    commands=command_counts()',
                "    assert int.from_bytes(image[0x7e5008:0x7e500c],'little')==0xffed\n    commands=command_counts()")
            output=folder/name/'test_raw_grpc_duplex.py';output.parent.mkdir(exist_ok=True);output.write_text(text)
            cases[name]=dict(client=client,ack_phase=phase,expected_error=error,
                expected_rpc_header_cleared=expected_header,expected_receive_closed=expected_rx,
                actual_successful_prefix=expected,fixture_sha256=sha(output))
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),
        witness_sha256=sha(root/'sim/cocotb/post_retire_fault_witness.py'),
        golden_acceptance_sha256=sha(archive/'acceptance.json'),cases=cases,
        generated_fault_cases=39,actual_execution_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(cases=len(cases),directory_acks=20,receive_acks=19)))


if __name__=='__main__':main()
