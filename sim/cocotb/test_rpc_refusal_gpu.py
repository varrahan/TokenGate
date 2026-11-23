"""Actual old-call GPU response and refused-DATA traffic overlap at the wire."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import Frame
from test_http2_prefill import value
from test_rpc_admission_fence import FenceBench,settled
from test_rpc_stream_refusal import request_headers
from test_raw_grpc_enveloped import varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


ORDER='gpu-first'


async def promises(d,counts):
    held={}
    probes=[('raw',d.dut.core.forward,'s_axis_rx_',('tdata','tkeep','tlast','tuser'),('s_axis_rx_tag',)),
        ('gpu',d.dut.core.reverse,'s_axis_tokens_',('tdata','tkeep','tlast','tuser'),
            ('s_stream','s_generation','s_model_epoch','s_schema_epoch','s_ordinal')),
        ('wire',d,'m_axis_tx_',('tdata','tkeep','tlast','tuser'),())]
    while True:
        await RisingEdge(d.clk)
        if value(d,'rst'):held.clear();continue
        for label,node,prefix,fields,extra in probes:
            valid=value(node,prefix+'tvalid');ready=value(node,prefix+'tready')
            item=tuple(value(node,prefix+n)for n in fields)+tuple(value(node,n)for n in extra)if valid else None
            if label in held:assert item==held[label],(label,'AXIS offer changed while held',held[label],item)
            if valid and not ready:
                held[label]=item;counts[label+'_held_cycles']+=1
            else:held.pop(label,None)
            if valid and ready:counts[label+'_handshakes']+=1


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def real_gpu_and_refused_data_preserve_wire_ownership(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    initial=b''.join(int(word,16).to_bytes(8,'little')for word in(folder/'memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    image=bytearray(initial);memory=SeparateMemory(d,image);b=FenceBench(d,layout,memory,reverse)
    b.expected_fence_stream=None;b.fence_rejections=[]
    b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_generated_tvalid=0,
        response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,
        admit_new_rpcs=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();counts={name+'_'+field:0 for name in('raw','gpu','wire')for field in('held_cycles','handshakes')}
    for worker in(Clock(d.clk,4,unit='ns').start(),memory.parser.run(),memory.tokenizer.run(),
        b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated(),b.observe_private_credit(),promises(d,counts)):
        cocotb.start_soon(worker)
    await cycles(d,5);b.set(rst=0)
    for prefix in('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    b.response_configuration(2);await b.directory(4);await b.open()
    await b.packet(0,1,b.client.data_to_send(),1)
    record=b'\0\0\0\0\r\x0a\x0bhello world'
    raw=request_headers(b.client,1);b.client.send_data(1,record,end_stream=True);raw+=b.client.data_to_send()
    await b.packet(0,2,raw,1);await b.drain(0,1,101,[15339,1917]);captured={1:list(b.received)}
    await settled(b)
    address=b.handles[0,1];binding=b.bindings[0,1]
    assert int.from_bytes(image[address:address+4],'little')==0x47525331
    assert b.ids==2 and len(b.generated_accepts)==0
    # Queue both frames before the peer could see a reset. Only the order of
    # starting these real interfaces differs between the two frozen runs.
    b.set(admit_new_rpcs=0);b.expected_fence_stream=3
    raw=request_headers(b.client,3);b.client.send_data(3,record,pad_length=7,end_stream=True);raw+=b.client.data_to_send()
    before=len(b.wire);b.ready_wire=False
    if ORDER=='gpu-first':
        await b.gpu_offer(1,captured[1][0],0,0,2)
        await b.wait('m_axis_tx_tvalid')
        sending=cocotb.start_soon(b.packet(0,3,raw,1));gpu=None
    else:
        assert ORDER=='reset-first'
        sending=cocotb.start_soon(b.packet(0,3,raw,1))
        await b.wait('m_axis_tx_tvalid')
        gpu=cocotb.start_soon(b.gpu_offer(1,captured[1][0],0,0,2))
        await cycles(d,2)
    snapshot=tuple(value(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
    wire=snapshot[0].to_bytes(64,'little')[:snapshot[1].bit_count()]
    frame,size=Frame.parse_frame_header(memoryview(wire[:9]));frame.parse_body(memoryview(wire[9:]))
    assert (frame.type,frame.stream_id)==((1,1)if ORDER=='gpu-first'else(3,3))
    if frame.type==3:assert frame.error_code==7
    overlap=[]
    for _ in range(37):
        await FallingEdge(d.clk)
        assert value(d,'m_axis_tx_tvalid')and not value(d,'m_axis_tx_tready')
        assert snapshot==tuple(value(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
        assert not value(d,'response_result_valid')
        entry=dict(clock=b.clocks,return_pending=value(d.dut.core,'return_pending'),
            gpu_valid=value(d,'s_axis_generated_tvalid'),gpu_accepted=len(b.generated_accepts),
            directory_lease=value(d,'response_record_lease_active'),
            raw_valid=value(d,'s_axis_rx_tvalid'),forward_state=value(d.dut.core.forward,'state'),
            refusal_pending=value(d.dut.core.forward,'refusal_pending'))
        if ORDER=='gpu-first':assert entry['gpu_accepted']==entry['return_pending']==entry['directory_lease']==1
        else:assert entry['gpu_valid']or entry['return_pending']
        overlap.append(entry)
    Path('overlap-held.json').write_text(json.dumps(dict(order=ORDER,wire_hex=wire.hex(),observations=overlap),indent=2)+'\n')
    b.ready_wire=True
    if gpu is not None:await gpu
    await b.terminal(0,0,0)
    for _ in range(100000):
        if not value(d.dut.core,'return_pending'):break
        await cycles(d)
    else:raise AssertionError('First GPU descriptor did not retire')
    b.current=None;await sending
    assert len(b.fence_rejections)==1 and b.fence_rejections[0]['stream']==3
    assert (0,3)not in b.bindings and b.bindings[0,1]==binding
    assert int.from_bytes(image[address:address+4],'little')==0x47525331
    assert ('StreamReset',3)in b.client_events and not any(k=='ConnectionTerminated'for k,s in b.client_events)
    await b.gpu(1,captured[1][1],1,1,2);await b.directory(3,0,1);await settled(b)
    # Resume on the same connection, reusing shared HPACK entries installed by
    # the refused request. Both return streams use actual captured DMA IDs.
    b.set(admit_new_rpcs=1);raw=request_headers(b.client,5)
    b.client.send_data(5,record,end_stream=True);raw+=b.client.data_to_send()
    await b.packet(0,4,raw,1);await b.drain(0,5,101,[15339,1917]);captured[5]=list(b.received)
    for ordinal,token in enumerate(captured[5]):await b.gpu(5,token,ordinal,int(ordinal==1),2)
    await b.directory(3,0,5);await settled(b)
    expected=bytearray()
    for chunk in reverse['cases'][0]['chunks']:
        text=bytes.fromhex(chunk['bow_hex']);payload=varint(17<<3|2)+varint(len(text))+text
        expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
    assert all(bytes(b.response_records[s])==expected and('StreamEnded',s)in b.client_events for s in(1,5))
    frames=[]
    for raw_wire in b.wire[before:]:
        f,size=Frame.parse_frame_header(memoryview(raw_wire[:9]));f.parse_body(memoryview(raw_wire[9:]));frames.append(f)
    assert [(f.stream_id,f.error_code)for f in frames if f.type==3]==[(3,7)]
    assert b.ids==4 and b.messages==2 and len(b.generated_accepts)==4
    assert counts['gpu_handshakes']==4 and counts['wire_held_cycles']>=37
    assert not any(b.pending)and not b.packet_bytes
    assert not value(d,'receive_recovery_required')and not value(d,'response_recovery_required')
    assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    capacity=layout[14]//128*(layout[18]+5);assert b.client.outbound_flow_control_window==capacity
    b.save_wire_evidence()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',order=ORDER,
        overlap=overlap,held_wire_hex=wire.hex(),held_wire_cycles=37,axis_promise_counts=counts,
        actual_captured_dma_ids_returned=captured,actual_generated_descriptors=b.generated_accepts,
        native_complete_grpc_calls=2,byte_exact_response_hex=bytes(expected).hex(),
        refused_data_flow_controlled_bytes=26,header_rejections=b.fence_rejections,
        final_connection_credit=capacity,complete_model_prefixes_immutable=True,
        fault_injection=False,retained_reset_verified=False,native_vendor_runtime_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,full_system_complete=False),indent=2)+'\n')
