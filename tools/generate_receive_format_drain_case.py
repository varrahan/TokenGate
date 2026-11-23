"""Hold global FORMAT behind a real offered GPU response, then drain both."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/receive-format/sim/test_raw_shutdown_faults.py'
    text=source.read_text()
    text=text[:text.index('    before=b.commands[26]')]
    text=text.replace('from test_raw_shutdown_controls import Bench as FaultBench',
        'from test_raw_grpc_enveloped import Bench as FaultBench,varint\nfrom cocotb.triggers import RisingEdge')
    text=text.replace('actual_format_ack_faults_retry_and_captured_scope','actual_format_waits_for_owned_gpu_drain')
    text+='''    await b.formatting();await b.open()
    await b.packet(0,1,b.client.data_to_send(),1)
    complete=json.loads((folder/'reference_cases.json').read_text())['cases'][0]
    prompt=bytes.fromhex(complete['prompt_utf8_hex']);body=b'\\x0a'+varint(len(prompt))+prompt
    b.client.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    b.client.send_data(1,b'\\0'+len(body).to_bytes(4,'big')+body,end_stream=True)
    await b.packet(0,2,b.client.data_to_send(),1);await b.drain(0,1,101,complete['token_ids'])
    captured=list(b.received);assert captured==complete['token_ids']
    b.ready_wire=False;await b.gpu_offer(1,captured[0],0,1,2)
    await b.wait('m_axis_tx_tvalid');await cycles(d,2)
    assert value(d,'response_record_lease_active') and value(d.dut.core,'return_pending')
    events=[]
    async def ordering():
        tick=0;gpu_ack=None
        while True:
            await RisingEdge(d.clk);tick+=1
            if value(d,'response_result_valid') and value(d,'response_result_ready'):
                gpu_ack=tick;events.append(dict(event='actual_gpu_result_ack',clock=tick))
            if value(d,'control_valid') and value(d,'control_ready') and value(d,'control_op')==4:
                assert gpu_ack is not None and gpu_ack<tick
                assert not value(d,'response_record_lease_active') and not value(d.dut.core,'return_pending')
                events.append(dict(event='actual_format_request_ack',clock=tick))
                return
    proof=cocotb.start_soon(ordering());before=b.commands[26]
    formatting=cocotb.start_soon(b.formatting());await b.wait('control_valid')
    held=tuple(value(d,'m_axis_tx_'+n) for n in ('tdata','tkeep','tlast','tuser'))
    for _ in range(17):
        await cycles(d)
        assert not value(d,'control_ready') and not value(d,'control_result_valid')
        assert value(d,'m_axis_tx_tvalid') and held==tuple(value(d,'m_axis_tx_'+n) for n in ('tdata','tkeep','tlast','tuser'))
        assert b.commands[26]==before and value(d,'response_record_lease_active')
    b.ready_wire=True;await b.terminal(0,0,0);await formatting;await proof
    # The native HTTP/2 client consumes actual RTL headers, DATA and trailers.
    chunk=bytes.fromhex(reverse['cases'][0]['chunks'][0]['bow_hex'])
    payload=varint(17<<3|2)+varint(len(chunk))+chunk
    expected=b'\\0'+len(payload).to_bytes(4,'big')+payload
    assert bytes(b.response_records[1])==expected and ('StreamEnded',1) in b.client_events
    assert b.commands[26]-before==12 and not value(d,'receive_recovery_required')
    assert not value(d.dut.core,'rx_format_failed') and image[0x7e6000:0x7e6060]==bytes(96)
    assert not any(b.pending) and not b.packet_bytes
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    result=dict(phase='passed',actual_format_transactions=witness.result(),actual_ordering=events,
        actual_captured_dma_ids=captured,actual_gpu_token=captured[0],actual_native_response_hex=bytes(b.response_records[1]).hex(),
        actual_format_waited_for_offered_wire_and_gpu_lease=True,held_wire_cycles=17,
        actual_gpu_lookup_and_response_drained_while_format_waited=True,actual_format_completed_without_reset=True,
        complete_model_prefix_immutable=True,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\\n')
'''
    folder=root/'build/experiments/receive-format/drain';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'test_raw_shutdown_faults.py';output.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (folder/'generation.json').write_text(json.dumps(dict(generator_sha256=sha(Path(__file__)),
        source_sha256=sha(source),fixture_sha256=sha(output),actual_execution_verified=False),indent=2)+'\n')
    print(output)


if __name__=='__main__':main()
