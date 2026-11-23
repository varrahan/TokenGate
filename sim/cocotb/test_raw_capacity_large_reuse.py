"""Recycle one physical payload slot across three actual 64 KiB messages."""
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


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def large_messages_reuse_actual_slot_before_gpu_eos(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder/'layout.txt').read_text().split()))
    manifest = json.loads((folder/'fixture_manifest.json').read_text())
    reverse = json.loads((folder/'response_reference.json').read_text())
    initial = b''.join(int(word,16).to_bytes(8,'little') for word in (folder/'memory.mem').read_text().splitlines())
    assert len(initial) == 8388608 and hashlib.sha256(initial).hexdigest() == manifest['loaded_image_sha256']
    body = ((varint(99<<3|2)+varint(8000)+b'U'*8000)*8 +
        varint(99<<3|2)+varint(1487)+b'U'*1487+b'\x0a\x0bhello world')
    record = b'\0'+len(body).to_bytes(4,'big')+body
    assert len(body) == 65536 and len(record) == 65541 and 3*len(body) > layout[18] == 131072
    image = bytearray(initial)
    memory = SeparateMemory(d,image)
    b = RecordingBench(d,layout,memory,reverse)
    b.completion_wait_limit = 100000+16*len(body)
    b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_generated_tvalid=0,
        response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure()
    for worker in (Clock(d.clk,4,unit='ns').start(),memory.parser.run(),memory.tokenizer.run(),
        b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated(),b.observe_private_credit()):
        cocotb.start_soon(worker)
    await cycles(d,5)
    b.set(rst=0)
    for prefix in ('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready')
        await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status') == 0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    b.response_configuration(0)
    await b.directory(4)
    await b.open()
    await b.packet(0,1,b.client.data_to_send(),1)
    b.client.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
    await b.packet(0,2,b.client.data_to_send(),1)
    address = b.handles[0,1]
    slot_base = int.from_bytes(image[address+16:address+20],'little')
    capacity = layout[14]//128*(layout[18]+5)
    requests, captured, snapshots = [], [], []
    for message in range(3):
        for offset in range(0,len(record),8192):
            payload = record[offset:offset+8192]
            for _ in range(100000):
                if b.client.local_flow_control_window(1) >= len(payload):
                    break
                await cycles(d)
            else:
                b.save_wire_evidence()
                raise AssertionError(('No actual credit for next large message',message,offset))
            end = message == 2 and offset+len(payload) == len(record)
            b.client.send_data(1,payload,end_stream=end)
            raw = b.client.data_to_send()
            requests.append(dict(message=message,offset=offset,data_bytes=len(payload),end_stream=end,raw_hex=raw.hex()))
            Path('requests.json').write_text(json.dumps(requests,indent=2)+'\n')
            await b.packet(0,len(requests)+2,raw,1)
        await b.drain(0,1,101,[15339,1917],ordinal=message)
        captured.extend(b.received)
        assert b.messages == message+1 and not b.generated_accepts
        core = d.dut.core
        for _ in range(100000):
            if not value(core,'rc_pending') and not value(core,'rc_busy'):
                break
            await cycles(d)
        else:
            raise AssertionError(('Private large-message reclaim did not retire',message))
        await cycles(d,2)
        progress = int.from_bytes(image[address+32:address+64],'little')
        assert int.from_bytes(image[address+16:address+20],'little') == slot_base
        assert image[slot_base:slot_base+len(body)] == body
        used, position = progress&0xffffffff, progress>>32&0xffffffff
        completed, reclaimed = progress>>128&0xffffffff, progress>>165&((1<<33)-1)
        ended = progress>>163&1
        assert (used,position,completed,reclaimed,ended) == (
            (0,0,message+1,message+1,0) if message < 2 else (65536,65536,3,2,1))
        assert b.client.outbound_flow_control_window == capacity-(len(record) if message == 2 else 0)
        snapshots.append(dict(message=message,record_address=address,payload_base=slot_base,
            progress_hex=image[address+32:address+64].hex(),
            payload_sha256=hashlib.sha256(image[slot_base:slot_base+len(body)]).hexdigest(),
            connection_credit=b.client.outbound_flow_control_window,
            stream_credit=b.client.local_flow_control_window(1),
            actual_messages=b.messages,actual_dma_ids=b.ids,actual_generated_descriptors=len(b.generated_accepts),
            wire_frame_count=len(b.wire),receive_trace_count=len(b.receive_trace),
            private_credit_trace_count=len(b.private_credit_trace)))
        Path('reuse_progress.json').write_text(json.dumps(snapshots,indent=2)+'\n')
        d._log.info('Reused actual payload slot after large message %d: reclaimed=%d',message,reclaimed)
    expected = bytearray()
    for ordinal,token in enumerate(captured):
        await b.gpu(1,token,ordinal,int(ordinal==len(captured)-1),2)
        raw = bytes.fromhex(reverse['cases'][0]['chunks'][ordinal%2]['bow_hex'])
        payload = varint(17<<3|2)+varint(len(raw))+raw
        expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
    assert captured == [15339,1917]*3 and bytes(b.response_records[1]) == expected
    assert ('StreamEnded',1) in b.client_events
    await b.directory(3,0,1)
    for _ in range(100000):
        if b.client.outbound_flow_control_window == capacity:
            break
        await cycles(d)
    else:
        raise AssertionError('Large-message final CLOSE did not refund the remaining record')
    assert not any(b.pending) and not b.packet_bytes and not value(d,'response_record_lease_active')
    b.save_wire_evidence()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',
        complete_messages_acknowledged=3,actual_application_data_bytes=3*len(record),
        actual_body_bytes=3*len(body),actual_captured_dma_ids_returned=captured,
        actual_generated_descriptors=b.generated_accepts,reuse_snapshots=snapshots,
        byte_exact_response_hex=expected.hex(),native_complete_grpc_calls=1,
        explicit_host_directory_closes=1,final_connection_credit=b.client.outbound_flow_control_window,
        complete_model_prefixes_immutable=image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]],
        full_system_complete=False),indent=2)+'\n')
