"""Three interleaved large partial RPCs on the actual Parser/Tokenizer pair."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_prefill import value
from test_raw_grpc_enveloped import varint
from test_raw_open_rpc_credit import RecordingBench
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def three_large_partial_streams_preserve_actual_slots_and_dma(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text());reverse=json.loads((folder/'response_reference.json').read_text())
    initial=b''.join(int(word,16).to_bytes(8,'little')for word in(folder/'memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    body=((varint(99<<3|2)+varint(8000)+b'U'*8000)*8+
        varint(99<<3|2)+varint(1487)+b'U'*1487+b'\x0a\x0bhello world')
    record=b'\0'+len(body).to_bytes(4,'big')+body
    assert len(body)==65536 and len(record)==65541 and layout[14]//128==3
    image=bytearray(initial);memory=SeparateMemory(d,image);b=RecordingBench(d,layout,memory,reverse)
    b.completion_wait_limit=100000+16*len(body)
    b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_generated_tvalid=0,
        response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure()
    for worker in(Clock(d.clk,4,unit='ns').start(),memory.parser.run(),memory.tokenizer.run(),
        b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated(),b.observe_private_credit()):cocotb.start_soon(worker)
    await cycles(d,5);b.set(rst=0)
    for prefix in('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    b.response_configuration(0);await b.directory(4);await b.open()
    await b.packet(0,1,b.client.data_to_send(),1)
    streams=(1,3,5)
    for stream in streams:b.client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    await b.packet(0,2,b.client.data_to_send(),1)
    requests=[];tag=2
    # Leave five bytes missing from every message at once. No descriptor can
    # exist yet, so real initial capacity must permit all partial DATA.
    for offset in range(0,65536,8192):
        for stream in streams:
            assert b.client.local_flow_control_window(stream)>=8192,(stream,offset,'Backed capacity did not arrive')
            payload=record[offset:offset+8192];b.client.send_data(stream,payload)
            raw=b.client.data_to_send();tag+=1
            requests.append(dict(stream=stream,offset=offset,data_bytes=len(payload),end_stream=False,raw_hex=raw.hex()))
            await b.packet(0,tag,raw,1)
    assert b.messages==b.ids==len(b.generated_accepts)==0
    partials=[]
    for stream in streams:
        address=b.handles[0,stream]
        saved=int.from_bytes(image[address+32:address+64],'little')
        base=int.from_bytes(image[address+16:address+20],'little')
        assert (saved&0xffffffff,saved>>32&0xffffffff,saved>>64&0xffffffff,saved>>96&0xffffffff,saved>>128&0xffffffff,saved>>160&7)==(65531,0,65536,65531,0,5)
        assert image[base:base+65531]==body[:65531]
        partials.append(dict(stream=stream,generation=b.bindings[0,stream],record_address=address,
            payload_base=base,received_body_bytes=65531,message_length=65536,
            partial_body_sha256=hashlib.sha256(image[base:base+65531]).hexdigest()))
    assert len({p['payload_base'] for p in partials})==3
    captured={}
    for stream in streams:
        b.client.send_data(stream,record[65536:],end_stream=True);raw=b.client.data_to_send();tag+=1
        requests.append(dict(stream=stream,offset=65536,data_bytes=5,end_stream=True,raw_hex=raw.hex()))
        await b.packet(0,tag,raw,1)
        await b.drain(0,stream,101,[15339,1917])
        captured[stream]=list(b.received)
        d._log.info('Completed actual large partial RPC %d: %s',stream,captured[stream])
    for ordinal in range(2):
        for stream in streams:await b.gpu(stream,captured[stream][ordinal],ordinal,int(ordinal==1),2)
    expected=bytearray()
    for chunk in reverse['cases'][0]['chunks']:
        raw=bytes.fromhex(chunk['bow_hex']);payload=varint(17<<3|2)+varint(len(raw))+raw
        expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
    for stream in streams:
        assert bytes(b.response_records[stream])==expected and ('StreamEnded',stream) in b.client_events
        await b.directory(3,0,stream)
    capacity=3*(layout[18]+5)
    for _ in range(100000):
        if b.client.outbound_flow_control_window==capacity:break
        await cycles(d)
    else:raise AssertionError('Closing all actual streams did not restore capacity')
    assert not any(b.pending) and not b.packet_bytes
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    assert not value(d,'receive_fault_valid') and not value(d,'receive_recovery_required')
    b.save_wire_evidence();Path('requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',native_complete_grpc_calls=3,
        concurrent_partial_streams=partials,actual_captured_dma_ids_returned=captured,
        actual_generated_descriptors=b.generated_accepts,actual_application_data_bytes=3*len(record),
        byte_exact_response_hex=bytes(expected).hex(),final_connection_credit=b.client.outbound_flow_control_window,
        explicit_host_directory_closes=3,complete_model_prefixes_immutable=True,
        actual_parser_and_tokenizer_executed=True,whole_system_retained_reset_verified=False,
        native_vendor_runtime_verified=False,full_system_complete=False),indent=2)+'\n')
