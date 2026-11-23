"""Retain both complete memory banks across drained native RPC/reset epochs."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments/post-commit-retire/sim/test_raw_grpc_enveloped.py'
    text=source.read_text();prefix=text[:text.index('@cocotb.test(')]
    calls=text[text.index('    token_ids=reference'):text.index('    # A real native-client RST')]
    calls='\n'.join('    '+line if line else line for line in calls.splitlines())+'\n'
    needle='                await b.gpu(stream,token,ordinal,int(ordinal+1==len(actual_ids)),mode)'
    diagnostic='''progress_address=reverse['response_progress']['base']+(b.handles[0,stream]-layout[13])//4
before_progress=bytes(memory.data[progress_address:progress_address+32])
try:await b.gpu(stream,token,ordinal,int(ordinal+1==len(actual_ids)),mode)
except BaseException:
    loaded=value(d.dut.core.reverse.response.rpc,'progress')
    diagnostic=dict(epoch=epoch,stream=stream,token=token,ordinal=ordinal,
        rpc_address=b.handles[0,stream],generation=b.bindings[0,stream],
        progress_address=progress_address,progress_before_hex=before_progress.hex(),
        actual_hardware_progress=loaded,actual_hardware_progress_hex=loaded.to_bytes(32,'little').hex(),
        actual_result=[value(d,n)for n in('response_result_stage','response_result_status',
            'response_result_memory_status','response_result_generation','response_result_ordinal')],
        completed_epochs=epochs,actual_format_transactions=witness.result(),
        both_memory_bank_objects_retained=(id(memory.data),id(memory.tokenizer_data))==bank_ids)
    (Path.cwd()/'failure.json').write_text(json.dumps(diagnostic,indent=2)+'\\n')
    raise'''
    assert calls.count(needle)==1
    calls=calls.replace(needle,'\n'.join('                '+line for line in diagnostic.splitlines()))
    body='''@cocotb.test(timeout_time=30,timeout_unit='ms')
async def native_round_trips_reuse_retained_memory_after_drained_reset(d):
    from window_format_witness import WindowFormatWitness
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    reference=json.loads((folder/'reference_cases.json').read_text())
    initial=b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines())
    assert hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    memory=SeparateMemory(d,bytearray(initial))
    assert memory.data is not memory.tokenizer_data
    clock=cocotb.start_soon(Clock(d.clk,4,unit='ns').start())
    memory_task=cocotb.start_soon(memory.run())
    witness=WindowFormatWitness(d);witness_task=cocotb.start_soon(witness.observe())
    epochs=[];all_dma=[];bank_ids=(id(memory.data),id(memory.tokenizer_data))
    for epoch in range(2):
        b=Bench(d,layout,memory,reverse)
        b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,
            window_req_valid=0,window_rsp_ready=0,maintenance_grant=1,admit_packets=1,
            admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1,fault_client=-1,fault_arm=0)
        b.configure()
        workers=[cocotb.start_soon(worker)for worker in
            (b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated())]
        await cycles(d,5);b.set(rst=0)
        for control in ('queue','stream'):
            await b.send(control+'_cfg_valid',control+'_cfg_ready')
            await b.wait(control+'_cfg_result_valid');assert value(d,control+'_cfg_status')==0
            await b.ack(control+'_cfg_result_valid',control+'_cfg_result_ready',0)
        await b.directory(4);await b.open();await b.packet(0,1,b.client.data_to_send(),1)
'''
    tail='''        for _ in range(100000):
            if (not any(b.pending) and not b.packet_bytes and value(d,'fabric_idle')
                and not value(d,'m_axis_tx_tvalid') and not value(d,'response_record_lease_active')
                and not value(d.dut.core,'return_pending') and not value(d,'response_result_retirement_pending')):
                break
            await cycles(d)
        else:raise AssertionError('Native RPC owners did not drain before reset')
        assert len(returned_dma_ids)==2*len(token_ids)
        assert memory.data[:layout[6]]==memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
        assert (id(memory.data),id(memory.tokenizer_data))==bank_ids
        record=dict(epoch=epoch,rpc_addresses=[b.handles[0,s]for s in(1,3)],
            generations=[b.bindings[0,s]for s in(1,3)],actual_dma_ids=returned_dma_ids,
            native_response_bodies=expected_bodies,all_real_owners_drained=True,
            retained_parser_mutable_sha256=hashlib.sha256(memory.data[layout[6]:]).hexdigest(),
            retained_tokenizer_mutable_sha256=hashlib.sha256(memory.tokenizer_data[layout[6]:]).hexdigest())
        epochs.append(record);all_dma.extend(returned_dma_ids)
        (Path.cwd()/'retained_native_progress.json').write_text(json.dumps(epochs,indent=2)+'\\n')
        for task in workers:task.cancel()
    assert epochs[0]['rpc_addresses']==epochs[1]['rpc_addresses']
    assert epochs[0]['generations']==epochs[1]['generations']
    assert epochs[0]['actual_dma_ids']==epochs[1]['actual_dma_ids']
    assert epochs[0]['native_response_bodies']==epochs[1]['native_response_bodies']
    formats=witness.result();assert len(formats)==2
    for item in formats:
        assert item['result'][:3]==(0,0,0) or item['result'][:3]==[0,0,0]
        assert len(item['acks']['26'])==12 and len(item['acks']['22'])==6
    accepted=dict(phase='passed',epochs=epochs,actual_format_transactions=formats,
        actual_dma_returns=len(all_dma),native_rpc_round_trips=4,drained_global_reset_boundaries=1,
        same_rpc_addresses_and_generations_reused=True,both_memory_banks_retained_without_bfm_clear=True,
        complete_model_prefix_immutable=True,whole_system_reset_fault_matrix_verified=False,
        physical_interfaces_verified=False,full_system_complete=False)
    (Path.cwd()/'acceptance.json').write_text(json.dumps(accepted,indent=2)+'\\n')
'''
    target=root/'build/experiments/retained-native-roundtrip/test_raw_grpc_enveloped.py'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(prefix+body+calls+tail)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    record=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),fixture_sha256=sha(target),
        full_model_and_original_native_round_trip_checks_preserved=True,
        separate_memory_objects_created_once=True,reset_epochs=2,whole_system_complete=False)
    (target.parent/'generation.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))


if __name__=='__main__':main()
