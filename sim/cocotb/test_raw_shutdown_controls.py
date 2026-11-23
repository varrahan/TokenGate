"""Raw committed resets own actual GPU, wire, window and directory retirement."""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import DataFrame,Frame,GoAwayFrame,RstStreamFrame,SettingsFrame,WindowUpdateFrame
from test_raw_peer_controls import Bench as PeerBench,PEER
from test_http2_prefill import value
from test_two_fpga_application import SeparateMemory
from test_bidirectional_application import RESULTS
from test_tokenizer_mmio import cycles


class Bench(PeerBench):
    def __init__(self,d,layout,memory,reverse):
        super().__init__(d,layout,memory);self.reverse=reverse;self.pending=[None]*len(d.mem_valid);self.commands=[0]*len(d.mem_valid)
        self.wire=[];self.packet_bytes=bytearray();self.closed=set();self.ready_wire=True;self.held_wire=0
        self.processed=[];self.directories=[];self.results=[];self.allow_quarantine=False
        self.close_proof=self.history_proof=None;self.history_start=0;self.data_beats=0;self.metadata_acks=0;self.debit_acks=0;self.reserve_start=None
        self.receive_trace=[]
    def configure(self):
        super().configure()
        if hasattr(self.d,'cfg_receive_connection_base'):
            self.set(cfg_receive_connection_base=0x7e5000,cfg_receive_connection_bytes=192,
                cfg_receive_stream_base=0x7e6000,cfg_receive_stream_bytes=self.layout[14]//4)
    def poison(self):
        super().poison()
        if hasattr(self.d,'cfg_receive_connection_base'):
            self.set(cfg_receive_connection_base=0x7fffff,cfg_receive_connection_bytes=0,
                cfg_receive_stream_base=0x7fffff,cfg_receive_stream_bytes=0)
    async def wait(self,name):
        for _ in range(100000):
            if value(self.d,name):return
            await FallingEdge(self.d.clk)
        raise AssertionError(('Timeout',name,self.phase,value(self.d.dut.core.shutdown,'state')))
    async def wait_internal(self,node,name):
        for _ in range(100000):
            if value(node,name):return
            await FallingEdge(self.d.clk)
        raise AssertionError(('Internal timeout',name,self.phase))
    def response_configuration(self,format_mode=0):
        self.configure();a=self.reverse
        self.set(cfg_response_progress_base=a['response_progress']['base'],cfg_response_progress_bytes=a['response_progress']['bytes'],
            cfg_response_directory_base=a['model_directory']['base'],cfg_response_directory_bytes=a['model_directory']['capacity'],
            cfg_response_pool_base=a['string_pool']['base'],cfg_response_pool_bytes=a['string_pool']['capacity'],
            cfg_response_strip_special=1,cfg_response_replace_invalid=1,cfg_response_format=format_mode,cfg_response_protobuf_field=17,
            cfg_peer_max_frame_bytes=16384)
    async def token(self,stream,token=15339,format_mode=0):
        self.response_configuration(format_mode)
        self.set(s_axis_generated_tdata=token,s_axis_generated_tkeep=15,s_axis_generated_tlast=0,s_axis_generated_tuser=0,
            generated_stream=stream,generated_generation=self.bindings[0,stream],generated_model_epoch=23,generated_schema_epoch=9,generated_ordinal=0)
        await self.send('s_axis_generated_tvalid','s_axis_generated_tready')
        self.set(s_axis_generated_tdata=0xffffffff,generated_stream=0,generated_generation=0,
            cfg_response_progress_base=0x7fffff,cfg_response_progress_bytes=0,cfg_response_format=3)
    async def terminal(self,stage,status,cancelled,*,ack=True):
        await self.wait('response_result_valid');d=self.d
        record=tuple(value(d,n)for n in RESULTS+('response_result_cancelled',))
        assert record[:3]==(stage,status,0)and record[-1]==cancelled,record
        for _ in range(13):
            await cycles(d);assert value(d,'response_result_valid')and record==tuple(value(d,n)for n in RESULTS+('response_result_cancelled',))
        if ack:self.set(response_result_ready=1);await cycles(d);self.set(response_result_ready=0)
        return record
    async def raw_fragment(self,tag,raw,last):
        self.configure();self.set(s_axis_rx_tdata=int.from_bytes(raw,'little'),s_axis_rx_tkeep=(1<<len(raw))-1,
            s_axis_rx_tlast=last,s_axis_rx_tuser=0,s_axis_rx_tag=tag)
        await self.send('s_axis_rx_tvalid','s_axis_rx_tready')
    async def packet_result(self,tag,commit):
        await self.wait('packet_result_valid')
        assert(value(self.d,'packet_committed'),value(self.d,'packet_tag'))==(commit,tag),(
            value(self.d,'packet_status'),value(self.d,'packet_detail'),value(self.d,'transport_packet_http2_error'))
        await self.ack('packet_result_valid','packet_result_ready',6);self.packets+=1
    async def admit_headers(self,reference,tag,stream):
        raw=bytes.fromhex(reference['headers_packet']);frame,size=Frame.parse_frame_header(memoryview(raw[:9]));frame.parse_body(memoryview(raw[9:]))
        frame.stream_id=stream;await self.packet(0,tag,frame.serialize(),1);assert self.bindings[0,stream]>0
        self.closed.discard((0,stream))
    async def window_read_held(self,stream):
        a=self.layout;self.set(window_req_op=6,window_req_maintenance=0,window_req_user=0,window_req_stream=stream,
            window_req_generation=self.bindings[0,stream],window_req_record_address=self.handles[0,stream],window_req_amount=0,
            window_cfg_context_base=a[19],window_cfg_context_bytes=a[20],window_cfg_stream_base=a[13],window_cfg_stream_bytes=a[14],
            window_cfg_window_base=0x7f0000,window_cfg_window_bytes=a[14]//8,window_cfg_work_floor=a[6])
        await self.send('window_req_valid','window_req_ready');await self.wait('window_rsp_valid');assert value(self.d,'window_rsp_status')==0
    def check_progress_before_reservation(self):assert self.metadata_acks==5
    def check_progress_before_positive_grant(self):self.check_progress_before_reservation()
    def observe_wire_frame(self,user,frame,raw):pass
    async def actual_observer(self):
        d=self.d;held=None;held_result=None
        while True:
            await FallingEdge(d.clk);d.m_axis_tx_tready.value=int(self.ready_wire)
            await RisingEdge(d.clk)
            if value(d,'rst'):
                assert not any(self.pending)and held is None and not self.packet_bytes,'Reset abandoned real ownership'
                held_result=None;continue
            core=d.dut.core
            if hasattr(core,'receive_flow'):
                for request,result,fields in (
                    ('rx_request','rx_result',('op','user','stream','generation','address','amount')),
                    ('service_control_req','service_control_rsp',('op','user','stream','generation','address'))):
                    if value(core,request+'_valid')and value(core,request+'_ready'):
                        self.receive_trace.append(dict(event=request,phase=self.phase,**{n:value(core,request+'_'+n)for n in fields}))
                    if value(core,result+'_valid')and value(core,result+'_ready'):
                        entry=dict(event=result,phase=self.phase,**{n:value(core,result+'_'+n)for n in('status','detail','memory_status')})
                        self.receive_trace.append(entry)
                        if result=='service_control_rsp':entry['op']=value(core,'service_control_rsp_op')
                        if entry['status']and not(result=='service_control_rsp'and entry['status']==3):
                            Path('receive_trace.json').write_text(json.dumps(self.receive_trace,indent=2)+'\n')
                            d._log.info('Actual receive/directory failure: %s',entry)
                if value(d,'packet_result_valid')and not value(d,'packet_committed'):
                    Path('receive_trace.json').write_text(json.dumps(self.receive_trace,indent=2)+'\n')
            if value(d,'s_axis_generated_tvalid')and value(d,'s_axis_generated_tready'):self.metadata_acks=self.debit_acks=0
            if value(d,'cancel_valid')and value(d,'cancel_ready'):
                assert value(core,'ctl_history_fence')and value(core.forward,'state')==26 and value(core.forward,'p_packet_committed')
                self.close_proof=self.history_proof=None;self.history_start=self.commands[25]
            if value(core,'shutdown_close_rsp_valid')and value(core,'shutdown_close_rsp_ready')and value(core,'service_window_rsp_status')==0:
                assert value(core.reverse,'freeze_drained')and value(core,'service_window_rsp_binding_valid')and value(core,'service_window_rsp_send_closed')
                self.close_proof=(value(core,'service_window_rsp_user'),value(core,'service_window_rsp_stream'))
                if value(core,'return_pending')and(value(core,'return_user'),value(core,'return_stream'))==self.close_proof:
                    assert not value(core.reverse,'frame_wire_pending')
            if value(core,'shutdown_classify_rsp_valid')and value(core,'shutdown_classify_rsp_ready')and value(core,'shutdown_classify_rsp_status')==0:
                assert self.commands[25]==self.history_start+2 and value(core,'ctl_history_fence')
                if value(core,'shutdown_classify_rsp_closed'):
                    self.history_proof=(value(core,'shutdown_classify_rsp_user'),value(core,'shutdown_classify_rsp_stream'))
            if value(d,'reset_processed'):
                key=(value(d,'cancel_user'),value(d,'cancel_stream'));self.closed.add(key);self.processed.append(key)
                assert key in(self.close_proof,self.history_proof),'Reset had no actual durable-close/history witness'
            for client in range(len(self.pending)):
                if value(d,'mem_rsp_valid')>>client&value(d,'mem_rsp_ready')>>client&1:
                    assert self.pending[client]is not None
                    if client==0 and value(d,'mem_rsp_status')&255:
                        self.receive_trace.append(dict(event='actual_directory_memory_error',request=self.pending[client],status=value(d,'mem_rsp_status')&255))
                    if self.pending[client][1]and not(value(d,'mem_rsp_status')>>(8*client)&255):
                        if client==20:self.metadata_acks+=1
                        if client==22:self.debit_acks+=1
                    self.pending[client]=None
                if value(d,'mem_valid')>>client&value(d,'mem_ready')>>client&1:
                    assert self.pending[client]is None
                    address=value(d,'mem_addr')>>(23*client)&0x7fffff;write=value(d,'mem_write')>>client&1
                    self.pending[client]=(address,write);self.commands[client]+=1
                    if write:
                        assert address>=self.layout[6]and client not in(21,25)
                        if client==20:assert self.reverse['response_progress']['base']<=address<self.reverse['response_progress']['base']+self.reverse['response_progress']['bytes']
                        if client==22:assert getattr(self,'window_base',0x7f0000)<=address<getattr(self,'window_base',0x7f0000)+self.layout[14]//8 or self.layout[13]<=address<self.layout[13]+self.layout[14]or self.layout[19]<=address<self.layout[19]+self.layout[20]
                        if client==23:assert 0x780005<=address<0x780005+3*131072 or (
                            self.layout[19]<=address<self.layout[19]+self.layout[20]and 216<=(address-self.layout[19])%256<256)
                        if client==24:assert PEER<=address<PEER+192
            scheduler=core.reverse.directory_service
            if value(scheduler,'state')==0 and value(scheduler,'reserve_pending')and value(scheduler,'owned_request_ready')and not value(scheduler,'control_pending'):
                self.check_progress_before_reservation();self.reserve_start=self.debit_acks
            if value(core.reverse,'frame_req_valid')and value(core.reverse,'frame_req_ready')and value(core.reverse,'frame_grant_bytes'):
                self.check_progress_before_positive_grant()
                assert self.reserve_start is not None and self.debit_acks-self.reserve_start==2 and self.pending[22]is None
            if value(d,'m_axis_tx_tvalid'):
                item=tuple(value(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
                if held is not None:assert item==held,'Actual wire promise changed'
                if not value(d,'m_axis_tx_tready'):held=item;self.held_wire+=1
                else:
                    held=None;data,keep,last,user=item;assert keep and keep&(keep+1)==0
                    self.packet_bytes.extend(data.to_bytes(64,'little')[:keep.bit_count()])
                    if len(self.packet_bytes)>=9 and self.packet_bytes[3]==0:
                        self.data_beats+=1
                        sid=int.from_bytes(self.packet_bytes[5:9],'big')&0x7fffffff
                        assert(user,sid)not in self.closed,'DATA began after actual reset processing'
                    if last:
                        raw=bytes(self.packet_bytes);self.packet_bytes.clear();f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw
                        assert not(f.type==0 and(user,f.stream_id)in self.closed),'DATA escaped after durable RST processing'
                        self.observe_wire_frame(user,f,raw);self.wire.append(raw)
            else:assert held is None,'Held wire VALID withdrawn'
            record=tuple(value(d,n)for n in RESULTS+('response_result_cancelled',))if value(d,'response_result_valid')else None
            if held_result is not None:assert record==held_result,'Held GPU result changed'
            held_result=record if record is not None and not value(d,'response_result_ready')else None
            assert self.allow_quarantine or not value(d,'shutdown_recovery_required'),'Unexpected shutdown quarantine'
            if value(d.dut.core.shutdown,'directory_valid'):
                assert not(value(d.dut.core,'return_pending')and value(d.dut.core,'return_user')==value(d,'cancel_user')and value(d.dut.core,'return_stream')==value(d,'cancel_stream'))


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def raw_reset_and_goaway_use_actual_owned_services(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES']);layout=list(map(int,(folder/'layout.txt').read_text().split()))
    reference=json.loads((folder/'journaled_control_reference.json').read_text());reverse=json.loads((folder/'response_reference.json').read_text())
    meta=json.loads((folder/'fixture_manifest.json').read_text());image=bytearray(b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines()))
    native=json.loads((folder.parent/'http2-shutdown-fixtures/cases.json').read_text())
    assert native['phase']=='native_shutdown_references_passed'and native['model_image_sha256']==meta['loaded_image_sha256']
    resets={case['name']:case for case in native['reset_cases']}
    assert [resets[name]['rfc_http2_error']for name in('open','duplicate','idle')]==[0,0,1]
    assert [resets[name]['native_http2_error']for name in('open','duplicate','idle')]==[0,0,0]
    assert hashlib.sha256(image).hexdigest()==meta['loaded_image_sha256'];initial=bytes(image);memory=SeparateMemory(d,image);b=Bench(d,layout,memory,reverse)
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.actual_observer()):cocotb.start_soon(worker)
    await cycles(d,5);d.rst.value=0
    await b.send('queue_cfg_valid','queue_cfg_ready');await b.wait('queue_cfg_result_valid');assert value(d,'queue_cfg_status')==0;await b.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await b.send('stream_cfg_valid','stream_cfg_ready');await b.wait('stream_cfg_result_valid');assert value(d,'stream_cfg_status')==0;await b.ack('stream_cfg_result_valid','stream_cfg_result_ready',0)
    await b.directory(4);await b.open();await b.packet(0,1,bytes.fromhex(reference['initial_packet']),1);await b.admit_headers(reference,2,1)
    # Actual raw RST closes and retires the record, then a duplicate uses the
    # actual admission-history classifier rather than an external callback.
    rst=RstStreamFrame(1);rst.error_code=8;mark=len(b.wire);await b.packet(0,3,rst.serialize(),1)
    assert rst.serialize().hex()==resets['open']['wire_hex']==resets['duplicate']['wire_hex']
    assert value(d,'resets_processed')==1 and struct.unpack_from('<Q',image,b.handles[0,1])[0]==0
    before=b.commands[25];await b.packet(0,4,rst.serialize(),1)
    assert value(d,'resets_processed')==2 and b.commands[25]==before+2 and len(b.wire)==mark
    idle=RstStreamFrame(3);idle.error_code=8;await b.packet(0,5,idle.serialize(),0)
    assert idle.serialize().hex()==resets['idle']['wire_hex']
    assert value(d,'transport_packet_http2_error')==1 and value(d,'shutdown_status')==4
    # Reopen through actual roots. Incoming GOAWAY updates durable peer state
    # without treating its server-stream cutoff as an odd client-RPC cutoff.
    await b.open();await b.packet(0,6,bytes.fromhex(reference['reopen_preface']),1);await b.admit_headers(reference,7,1)
    go=GoAwayFrame(0);go.last_stream_id=0;go.error_code=0;await b.packet(0,8,go.serialize(),1)
    assert go.serialize().hex()==native['goaway_wire_cases'][0]['wire_hex']
    peer=struct.unpack_from('<8Q',image,PEER);assert peer[0]>>50&1 and peer[4]>>33==0 and peer[7]&0xffffffff==0
    assert value(d,'goaways_processed')==1 and struct.unpack_from('<Q',image,b.handles[0,1])[0]!=0
    mark=len(b.wire);await b.token(1);await b.terminal(0,0,0)
    packet=bytes.fromhex(reverse['cases'][0]['chunks'][0]['packet_hex']);f=DataFrame(1);f.data=b'\0'+len(packet).to_bytes(4,'big')+packet
    assert b.wire[mark:]==[f.serialize()]
    # A descriptor accepted mid-packet cannot wait for the same raw completion
    # that is waiting for its reset. It terminates before any actual LOAD.
    await b.admit_headers(reference,9,3);r3=RstStreamFrame(3);r3.error_code=8;raw=r3.serialize();before=[b.commands[i]for i in(20,21)]
    await b.raw_fragment(10,raw[:6],0);await b.token(3);await cycles(d,5)
    assert value(d.dut.core,'return_pending')and value(d.dut.core.reverse,'lookup_waiting')and not value(d,'response_record_lease_active')
    await b.raw_fragment(10,raw[6:],1);b.poison();await b.terminal(17,1,1,ack=False)
    for _ in range(13):await cycles(d);assert not value(d,'packet_result_valid')and value(d.dut.core,'return_pending')and not value(d,'cfg_quiescent')
    assert [b.commands[i]for i in(20,21)]==before
    b.set(response_result_ready=1);await cycles(d);b.set(response_result_ready=0);await b.packet_result(10,1)
    assert struct.unpack_from('<Q',image,b.handles[0,3])[0]==0 and value(d,'resets_processed')==3
    # A parked actual LOAD takes the real STREAM_CLOSED reservation path.
    await b.admit_headers(reference,11,5);settings=SettingsFrame(0);settings.settings[4]=0;await b.packet(0,12,settings.serialize(),1)
    await b.token(5);await b.wait('credit_parked');assert value(d,'response_record_lease_active')
    r5=RstStreamFrame(5);r5.error_code=8;closing=cocotb.start_soon(b.packet(0,13,r5.serialize(),1))
    await b.terminal(16,5,1,ack=False);assert value(d,'response_result_credit_status')==8 and not value(d,'response_recovery_required')
    await b.window_read_held(5);b.set(response_result_ready=1);await cycles(d);b.set(response_result_ready=0);await cycles(d,2)
    assert value(d,'response_result_retirement_pending')and not value(d,'response_result_valid')
    for _ in range(19):
        await cycles(d);assert value(d.dut.core,'return_pending')and value(d,'response_record_lease_active')and not value(d,'cfg_quiescent')and not value(d,'packet_result_valid')
    await b.ack('window_rsp_valid','window_rsp_ready',0);await closing
    assert not value(d,'response_result_retirement_pending')and not value(d,'response_record_lease_active')and struct.unpack_from('<Q',image,b.handles[0,5])[0]==0
    # Repeated GOAWAY cannot expand the previously learned server-stream retry
    # boundary and does not touch odd client RPCs or freeze the return engine.
    for index,(tag,last)in enumerate(((14,2),(15,0x7fffffff)),1):
        go.last_stream_id=last;go.error_code=11;await b.packet(0,tag,go.serialize(),1)
        assert go.serialize().hex()==native['goaway_wire_cases'][index]['wire_hex']
        peer=struct.unpack_from('<8Q',image,PEER);assert peer[4]>>33==0 and peer[7]&0xffffffff==11
    assert value(d,'goaways_processed')==3
    # A real previously reserved multi-beat DATA frame keeps its first offer
    # and its source gap; no later grant is issued after reset processing.
    await b.admit_headers(reference,16,7);update=WindowUpdateFrame(7);update.window_increment=native['grant'];await b.packet(0,17,update.serialize(),1)
    b.ready_wire=False;mark=len(b.wire);before=value(d,'resets_processed');await b.token(7,native['token']);await b.wait('m_axis_tx_tvalid')
    assert value(d.dut.core.reverse,'frame_wire_pending')and not value(d,'m_axis_tx_tlast')
    r7=RstStreamFrame(7);r7.error_code=8;closing=cocotb.start_soon(b.packet(0,18,r7.serialize(),1))
    await b.wait_internal(d.dut.core.reverse,'freeze_active')
    for _ in range(17):await cycles(d);assert not value(d.dut.core.reverse,'freeze_drained')and value(d,'resets_processed')==before
    beats=b.data_beats;b.ready_wire=True
    while b.data_beats==beats:await FallingEdge(d.clk)
    b.ready_wire=False;d.m_axis_tx_tready.value=0
    for _ in range(17):await cycles(d);assert not value(d.dut.core.reverse,'freeze_drained')and value(d,'resets_processed')==before
    b.ready_wire=True;await b.terminal(16,5,1);await closing
    assert b.wire[mark:]==[bytes.fromhex(native['first_frame_hex'])]and struct.unpack_from('<Q',image,b.handles[0,7])[0]==0
    assert memory.data[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data==initial
    assert not any(b.pending)and not b.packet_bytes
    accepted=dict(phase='passed',actual_raw_packets=b.packets,actual_header_bindings=b.headers,
        actual_resets=value(d,'resets_processed'),actual_goaways=value(d,'goaways_processed'),
        prelookup_gpu_reset_without_inverse_or_progress=True,parked_cached_load_reset_without_quarantine=True,
        gpu_ack_buffered_until_actual_window_retirement=True,actual_directory_close_after_return_retirement=True,
        duplicate_reset_uses_actual_history=True,idle_reset_protocol_error=True,actual_peer_goaway_persisted=True,
        client_rpc_continues_after_incoming_goaway=True,no_data_after_actual_reset_processing=True,
        positive_actual_wire_promise_drained_before_reset_processing=True,actual_first_beat_stall_and_frame_gap=True,
        both_debit_acks_and_all_progress_acks_before_data=True,repeated_goaway_never_expands_retry_boundary=True,
        reset_callbacks_supplied_by_rtl=True,native_wire_frames=len(b.wire),complete_model_prefix_immutable=True,
        native_h2_open_and_duplicate_reset_references_verified=True,native_goaway_wire_references_verified=True,
        idle_reset_follows_rfc_9113_6_4=True,native_h2_idle_reset_divergence_recorded=True,
        whole_rpc_gpu_image_lease_verified=False,physical_dma_packet_drain_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
