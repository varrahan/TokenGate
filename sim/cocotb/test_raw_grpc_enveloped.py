"""Native HTTP/2 calls through actual request/DMA/inverse/response and raw reset."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'native-vendor'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from h2.config import H2Configuration
from h2.connection import H2Connection
from test_raw_shutdown_controls import Bench as ShutdownBench
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


def varint(n):
    result=bytearray()
    while n>=128:result.append((n&127)|128);n>>=7
    result.append(n);return bytes(result)


class Bench(ShutdownBench):
    def __init__(self,*args):
        super().__init__(*args);self.client=H2Connection(H2Configuration(client_side=True,header_encoding='utf-8'))
        self.client.initiate_connection();self.client_events=[];self.current=None;self.response_records={};self.generated_accepts=[]
    async def observe_generated(self):
        while True:
            await RisingEdge(self.d.clk)
            if not value(self.d,'rst')and value(self.d,'s_axis_generated_tvalid')and value(self.d,'s_axis_generated_tready'):
                self.generated_accepts.append(tuple(value(self.d,n)for n in('generated_stream','s_axis_generated_tdata','generated_ordinal','s_axis_generated_tlast')))
    def check_progress_before_reservation(self):assert self.metadata_acks>=5
    def check_progress_before_positive_grant(self):
        assert self.current is not None;assert self.metadata_acks==(10 if self.current['ordinal']==0 else 5)
        address=self.reverse['response_progress']['base']+(self.handles[0,self.current['stream']]-self.layout[13])//4
        progress=int.from_bytes(self.memory.data[address:address+32],'little')
        assert progress>>188&1 and not(progress>>187&1)
    def observe_wire_frame(self,user,frame,raw):
        assert user==0
        if frame.type in(0,1):assert(user,frame.stream_id)not in self.closed,'RPC frame after actual raw reset processing'
        events=self.client.receive_data(raw)
        for event in events:
            kind=type(event).__name__
            if kind=='ResponseReceived':
                assert self.current is not None
                assert event.headers==[(':status','200'),('content-type','application/grpc+proto'if self.current['format']==2 else'application/grpc+json')]
            elif kind=='TrailersReceived':assert event.headers==[('grpc-status','0')]
            elif kind=='DataReceived':self.response_records.setdefault(event.stream_id,bytearray()).extend(event.data)
            self.client_events.append((kind,getattr(event,'stream_id',0)))
    async def gpu_offer(self,stream,token,ordinal,eos,format_mode):
        self.current=dict(stream=stream,ordinal=ordinal,eos=eos,format=format_mode);self.response_configuration(format_mode)
        self.set(s_axis_generated_tdata=token,s_axis_generated_tkeep=15,s_axis_generated_tlast=eos,s_axis_generated_tuser=0,
            generated_stream=stream,generated_generation=self.bindings[0,stream],generated_model_epoch=23,generated_schema_epoch=9,generated_ordinal=ordinal)
        await self.send('s_axis_generated_tvalid','s_axis_generated_tready')
        self.set(s_axis_generated_tdata=0xffffffff,generated_stream=0,generated_generation=0,cfg_response_progress_base=0x7fffff,
            cfg_response_progress_bytes=0,cfg_response_format=3)
    async def gpu(self,stream,token,ordinal,eos,format_mode):
        await self.gpu_offer(stream,token,ordinal,eos,format_mode)
        await self.terminal(0,0,0)
        while value(self.d.dut.core,'return_pending'):await cycles(self.d)
        self.current=None


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def native_calls_return_actual_dma_ids_and_complete_grpc(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES']);layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text());reverse=json.loads((folder/'response_reference.json').read_text())
    reference=json.loads((folder/'reference_cases.json').read_text());image=bytearray(b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==manifest['loaded_image_sha256'];initial=bytes(image)
    memory=SeparateMemory(d,image);b=Bench(d,layout,memory,reverse)
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated()):cocotb.start_soon(worker)
    await cycles(d,5);b.set(rst=0)
    for prefix in('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid');assert value(d,prefix+'_cfg_status')==0
        await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    await b.directory(4);await b.open();await b.packet(0,1,b.client.data_to_send(),1)
    token_ids=reference['cases'][0]['token_ids'];text=bytes.fromhex(reference['cases'][0]['prompt_utf8_hex'])
    expected_bodies={};tag=2;returned_dma_ids=[]
    for stream,mode,path in((1,0,'/parser.Tokenize/Json'),(3,2,'/parser.Tokenize/Proto')):
        body=json.dumps({'prompt':text.decode()},separators=(',',':')).encode()if mode==0 else b'\x0a'+varint(len(text))+text
        b.client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path',path),
            ('content-type','application/grpc+proto'if mode==2 else'application/grpc+json'),('te','trailers')])
        b.client.send_data(stream,b'\0'+len(body).to_bytes(4,'big')+body,end_stream=True)
        await b.packet(0,tag,b.client.data_to_send(),1);tag+=1
        await b.drain(0,stream,100+int(mode==2),token_ids);actual_ids=list(b.received)
        assert actual_ids==token_ids
        chunks=[]
        for ordinal,token in enumerate(actual_ids):
            await b.gpu(stream,token,ordinal,int(ordinal+1==len(actual_ids)),mode)
            returned_dma_ids.append((stream,token,ordinal,int(ordinal+1==len(actual_ids))))
            # This prompt's native token references are already checked by the
            # original complete-model fixture oracle. The GPU inputs above are
            # the actual captured DMA IDs, rather than a second supplied list.
            decoded=bytes.fromhex(reverse['cases'][0]['chunks'][ordinal]['bow_hex'])
            packet=json.dumps({'choices':[{'delta':{'content':decoded.decode()}}]},ensure_ascii=False,separators=(',',':')).encode()if mode==0 else varint(17<<3|2)+varint(len(decoded))+decoded
            chunks.append(b'\0'+len(packet).to_bytes(4,'big')+packet)
        assert bytes(b.response_records[stream])==b''.join(chunks)
        assert('StreamEnded',stream)in b.client_events and not value(d,'response_recovery_required')
        expected_bodies[stream]=[chunk.hex()for chunk in chunks]
    # A real native-client RST packet and a descriptor accepted mid-packet use
    # production cancellation; no Python callback or window mutation is supplied.
    b.client.send_headers(5,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json'),
        ('content-type','application/grpc+json'),('te','trailers')])
    await b.packet(0,tag,b.client.data_to_send(),1);tag+=1;b.client.reset_stream(5,error_code=8);raw=b.client.data_to_send()
    assert len(raw)==13;before=len(b.wire);inverse=b.commands[21];progress=b.commands[20]
    await b.raw_fragment(tag,raw[:6],0);await b.token(5);await b.raw_fragment(tag,raw[6:],1)
    await b.terminal(17,1,1);await b.packet_result(tag,1)
    assert len(b.wire)==before and(b.commands[21],b.commands[20])==(inverse,progress)
    tag+=1
    # A real RST cannot process while an initial response header is already
    # offered on the actual wire. Its exact beat drains and commits first.
    b.client.send_headers(7,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json'),
        ('content-type','application/grpc+json'),('te','trailers')])
    await b.packet(0,tag,b.client.data_to_send(),1);tag+=1;b.ready_wire=False;before=len(b.wire)
    await b.gpu_offer(7,15339,0,0,0);await b.wait('m_axis_tx_tvalid');await cycles(d,2)
    b.client.reset_stream(7,error_code=8);resetting=cocotb.start_soon(b.packet(0,tag,b.client.data_to_send(),1))
    await b.wait_internal(d.dut.core.reverse,'freeze_active');processed=value(d,'resets_processed')
    for _ in range(17):
        await cycles(d);assert not value(d.dut.core.reverse,'freeze_drained')and value(d,'resets_processed')==processed and not value(d,'response_result_valid')
    b.ready_wire=True;await b.terminal(16,5,1);await resetting;b.current=None
    assert [packet[3]for packet in b.wire[before:]]==[1]and not value(d,'response_recovery_required')
    tag+=1
    # A later ordinary prompt still tokenizes without a shared reset. Freeze
    # then meets an already offered final trailer, which completes on the wire
    # and preserves its successful GPU result before directory retirement.
    body=json.dumps({'prompt':text.decode()},separators=(',',':')).encode()
    b.client.send_headers(9,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json'),
        ('content-type','application/grpc+json'),('te','trailers')])
    b.client.send_data(9,b'\0'+len(body).to_bytes(4,'big')+body,end_stream=True)
    await b.packet(0,tag,b.client.data_to_send(),1);tag+=1;await b.drain(0,9,100,token_ids)
    before=len(b.wire);await b.gpu_offer(9,15339,0,1,0)
    for _ in range(100000):
        if value(d.dut.core.reverse.response.envelope,'state')==10:break
        await cycles(d)
    else:raise AssertionError('Actual final trailer did not start')
    b.ready_wire=False;d.m_axis_tx_tready.value=0;await b.wait('m_axis_tx_tvalid');await cycles(d,2)
    assert value(d,'m_axis_tx_tdata')>>32&255==5
    b.client.reset_stream(9,error_code=8);resetting=cocotb.start_soon(b.packet(0,tag,b.client.data_to_send(),1))
    await b.wait_internal(d.dut.core.reverse,'freeze_active');processed=value(d,'resets_processed')
    for _ in range(17):
        await cycles(d);assert not value(d.dut.core.reverse,'freeze_drained')and value(d,'resets_processed')==processed and not value(d,'response_result_valid')
    b.ready_wire=True;await b.terminal(0,0,0);await resetting;b.current=None
    assert [packet[3]for packet in b.wire[before:]]==[1,0,1]and not value(d,'response_recovery_required')
    tag+=1
    # A physically applied final header-commit write can still return an error.
    # The real raw reset is already owned and must report that exact memory
    # error, quarantine the connection, and never publish a successful close.
    b.client.send_headers(11,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json'),
        ('content-type','application/grpc+json'),('te','trailers')])
    await b.packet(0,tag,b.client.data_to_send(),1);tag+=1;b.ready_wire=False;before=len(b.wire)
    await b.gpu_offer(11,15339,0,0,0);await b.wait('m_axis_tx_tvalid');await cycles(d,2)
    b.client.reset_stream(11,error_code=8);resetting=cocotb.start_soon(b.packet(0,tag,b.client.data_to_send(),0))
    await b.wait_internal(d.dut.core.reverse,'freeze_active');processed=value(d,'resets_processed')
    assert b.pending[20]is None;b.allow_quarantine=True
    b.set(fault_client=20,fault_target=4,fault_arm=1);await cycles(d);b.set(fault_arm=0);b.ready_wire=True
    await b.wait('response_result_valid')
    fields=('response_result_stage','response_result_status','response_result_memory_status','response_result_cancelled')
    result=tuple(value(d,n)for n in fields);assert result==(20,3,0x75,0),result
    for _ in range(13):await cycles(d);assert result==tuple(value(d,n)for n in fields)and value(d,'response_result_valid')and value(d,'response_record_lease_active')
    b.set(response_result_ready=1);await cycles(d);b.set(response_result_ready=0);await resetting;b.current=None
    assert value(d,'fault_injected')and value(d,'shutdown_recovery_required')and value(d,'shutdown_memory_status')==0x75
    assert value(d,'packet_control_memory_status')==0x75 and value(d,'transport_packet_http2_error')==2
    assert value(d,'resets_processed')==processed and [packet[3]for packet in b.wire[before:]]==[1]
    for _ in range(19):
        await cycles(d);assert not value(d,'s_axis_rx_tready')and not value(d,'s_axis_generated_tready')and not value(d,'control_ready')and not value(d,'window_req_ready')
    assert b.generated_accepts[:len(returned_dma_ids)]==returned_dma_ids
    assert len(b.generated_accepts)==8 and b.ids==6
    assert not any(b.pending)and not b.packet_bytes and not value(d,'response_record_lease_active')
    assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    accepted=dict(phase='passed',actual_raw_packets=b.packets,actual_header_bindings=b.headers,
        native_complete_grpc_calls=2,actual_forward_dma_ids=b.ids,actual_gpu_descriptors_accepted=len(b.generated_accepts),
        actual_captured_dma_ids_returned=len(returned_dma_ids),additional_generated_control_case_descriptors=4,
        native_request_headers_and_data_generated_by_client=True,native_client_consumes_actual_rtl_responses=True,
        normal_call_generated_input_is_captured_forward_dma=True,json_and_protobuf_response_fields_verified=True,
        actual_response_headers_and_grpc_status_verified=True,actual_raw_mid_packet_reset_without_lookup=True,
        actual_raw_rst_drains_offered_initial_header=True,actual_raw_rst_drains_offered_final_trailer=True,
        actual_completed_eos_result_survives_raw_reset=True,ordinary_prompt_after_reset_without_global_reset=True,
        actual_header_commit_failure_propagates_through_raw_reset=True,failed_header_commit_never_processes_reset=True,
        expected_response_records=expected_bodies,native_wire_frames=len(b.wire),parser_memory_clients=17,tokenizer_memory_clients=9,
        complete_model_prefix_immutable=True,whole_rpc_gpu_image_lease_verified=False,
        sse_transport_verified=False,receive_flow_control_verified=False,physical_interfaces_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
