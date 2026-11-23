"""Inject an actual directory ACK error after the private retirement handshake."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/local-semantic-cases/rst_idle_stream/test_raw_grpc_duplex.py'
    folder=root/'build/experiments/post-commit-retire-fault-probe';folder.mkdir(exist_ok=True)
    text=source.read_text()
    old='        workers += [close.observe(), close.hold_and_close(), observe_cancel(d, b, trace)]'
    assert text.count(old)==1
    text=text.replace(old,'        workers += [observe_cancel(d, b, trace)]')
    marker='    command_start = b.commands[22]'
    assert text.count(marker)==1
    text=text.split(marker)[0]+'''
    leaf=d.dut.core.forward.prefill.parser.ingress
    sampled={}
    async def inject_retirement_fault():
        for _ in range(12000):
            await RisingEdge(d.clk)
            if value(leaf,'post_abort_valid') and value(leaf,'post_abort_ready'):break
        else:raise AssertionError('No actual post-commit retirement request')
        sampled['original']=[value(leaf,n) for n in ('packet_committed','packet_status','packet_detail','packet_memory_status','packet_user','packet_tag')]
        assert sampled['original']==[1,0,0,0,0,3]
        assert not value(d,'response_record_lease_active') and not value(d.dut.core,'return_pending')
        sampled['directory_commands_before']=b.commands[0]
        b.set(fault_client=0,fault_target=0,fault_arm=1)
        await cycles(d);b.set(fault_arm=0)
        for _ in range(6000):
            await RisingEdge(d.clk)
            assert value(leaf,'packet_result_valid')
            assert [value(leaf,n) for n in ('packet_committed','packet_status','packet_detail','packet_memory_status','packet_user','packet_tag')]==sampled['original']
            if value(leaf,'post_abort_result_valid'):
                sampled['retirement_result']=[value(leaf,n) for n in ('post_abort_status','post_abort_detail','post_abort_memory_status')]
                assert sampled['retirement_result']==[13,0x82,0x75]
                assert value(d,'fault_injected') and value(d,'stream_recovery_required')
                assert b.commands[0]==sampled['directory_commands_before']+1
                return
        raise AssertionError('Actual retirement ACK error not reported')
    injection=cocotb.start_soon(inject_retirement_fault())
    await b.raw_fragment(3,invalid,1)
    await b.terminal(16,5,1,ack=False)
    for _ in range(17):
        await cycles(d)
        assert value(d,'response_record_lease_active') and not value(d,'packet_result_valid')
    b.set(response_result_ready=1);await cycles(d);b.set(response_result_ready=0);b.current=None
    await injection
    await b.wait('packet_result_valid')
    assert (value(d,'packet_committed'),value(d,'packet_control_status'),value(d,'packet_control_memory_status'),value(d,'transport_packet_http2_error'))==(0,13,0x75,2)
    assert not value(d,'response_record_lease_active') and not any(p[3]==7 for p in b.wire[before:])
    assert not value(d,'transport_close_valid') and value(leaf,'retirement_pending')
    commands=b.commands[0]
    b.set(fault_client=-1)
    for _ in range(19):
        await cycles(d)
        assert value(d,'packet_result_valid') and value(d,'stream_recovery_required')
        assert value(d,'packet_control_memory_status')==0x75 and value(leaf,'retirement_pending')
        assert b.commands[0]==commands and not value(d,'transport_close_valid')
        assert not value(d,'s_axis_rx_tready') and not value(d,'s_axis_generated_tready')
    await b.ack('packet_result_valid','packet_result_ready',13)
    await cycles(d,19)
    assert value(leaf,'retirement_pending') and value(d,'stream_recovery_required')
    assert value(leaf,'state')==13 and b.commands[0]==commands
    assert image[address:address+8]!=bytes(8)
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    accepted=dict(phase='passed',actual_retirement_fault_client=0,actual_retirement_fault_ack_phase=0,
        actual_retirement_error=sampled['retirement_result'],actual_preserved_committed_result=sampled['original'],
        actual_directory_commands_after_request=1,actual_rpc_record_remains_owned=True,
        actual_gpu_retired_before_retirement_request=True,actual_memory_error_propagated_to_packet=True,
        actual_no_goaway_or_host_close_on_uncertain_retirement=True,actual_no_replay_after_injection_cleared=True,
        actual_retirement_pending_and_recovery_retained=True,recovery_after_uncertain_retirement_verified=False,
        complete_model_prefix_immutable=True,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\\n')
'''
    destination=folder/'test_raw_grpc_duplex.py';destination.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (folder/'generation.json').write_text(json.dumps(dict(generator_sha256=sha(Path(__file__)),
        source_sha256=sha(source),fixture_sha256=sha(destination),fault_client=0,ack_phase=0,
        actual_execution_verified=False),indent=2)+'\n')
    print(destination)


if __name__=='__main__':main()
