"""Real inverse/BoW/metadata/credits produce complete native-client gRPC replies."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'native-vendor'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import DataFrame,Frame
from test_rpc_cancel_directed import Bench as CancelBench
from test_rpc_response import RESULTS,val
from test_tokenizer_mmio import cycles
from test_tokenizer_mmio_system import Memory


class Bench(CancelBench):
    def __init__(self,*args):
        super().__init__(*args);self.clients={};self.events=[];self.current=None;self.closed=set();self.allow_error=False
        self.wire_users=[];self.metadata_writes=0;self.positive_grants=0;self.scope_proofs=0
    def open_client(self,b):
        user=b['user']
        if user not in self.clients:
            client=H2Connection(H2Configuration(client_side=True,header_encoding='utf-8'))
            server=H2Connection(H2Configuration(client_side=False,header_encoding='utf-8'))
            client.initiate_connection();server.initiate_connection();server.receive_data(client.data_to_send())
            client.receive_data(server.data_to_send());server.receive_data(client.data_to_send());server.data_to_send();self.clients[user]=client
        c=self.clients[user];c.send_headers(b['stream'],[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Generate/Stream'),('content-type','application/grpc+proto'if b['format']==2 else'application/grpc+json'),('te','trailers')],end_stream=True)
        c.data_to_send();self.closed.discard((user,b['stream']))
    async def freeze(self,b,*,foreign_scope=False):
        a=self.a
        self.set(**{'freeze_cfg_'+n:v for n,v in dict(context_base=self.context_base,context_bytes=self.context_bytes,
            stream_base=a['stream_base'],stream_bytes=a['stream_bytes'],window_base=self.window_base+(128 if foreign_scope else 0),
            window_bytes=self.window_bytes,work_floor=a['work_floor']).items()})
        await super().freeze(b)
        self.set(**{'freeze_cfg_'+n:0 for n in('context_base','context_bytes','stream_base','stream_bytes','window_base','window_bytes','work_floor')})
    async def submit(self,b,chunk):
        self.current=(b,chunk);await self.token(b,chunk=chunk)
    async def wait_internal(self,node,name):
        for _ in range(100000):
            if val(node,name):return
            await FallingEdge(self.d.clk)
        raise AssertionError(('Internal timeout',str(node),name))
    async def complete(self,b,chunk,stage=0,status=0,memory_status=0,cancelled=0,*,lease=True,application=None):
        d=self.d;await self.wait('result_valid')
        fields=RESULTS+('result_cancelled','result_wire_bytes','result_frames')
        record=tuple(val(d,n)for n in fields)
        assert record[:3]==(stage,status,memory_status),record
        assert record[5:13]==(b['user'],b['application']if application is None else application,b['stream'],b['generation'],23,9,chunk['ordinal'],chunk['eos']),record
        assert record[13]==cancelled
        for _ in range(19):
            await cycles(d);assert val(d,'result_valid')and record==tuple(val(d,n)for n in fields)
            assert bool(val(d,'record_lease_active'))==lease and not val(d,'s_axis_tokens_tready')
        self.set(result_ready=1);await cycles(d);self.set(result_ready=0)
        for _ in range(1000):
            if not val(d,'record_lease_active')and val(d,'fabric_idle'):break
            await FallingEdge(d.clk)
        else:raise AssertionError('Actual cached LOAD did not retire')
        self.current=None;return record
    async def observe_actual(self):
        d=self.d;held=None;held_result=None;reserve_start=0
        while True:
            await FallingEdge(d.clk);d.m_axis_tx_tready.value=int(self.ready_wire)
            await RisingEdge(d.clk)
            if val(d,'rst'):
                assert not any(self.pending)and not self.packet and held is None and self.outstanding is None
                held_result=None;continue
            self.clocks+=1
            if val(d,'s_axis_tokens_tvalid')and val(d,'s_axis_tokens_tready'):
                self.gpu_accepted+=1;self.progress_acks=0;self.metadata_writes=0
            if val(d,'window_rsp_valid')and val(d,'window_rsp_op')==10 and val(d,'window_rsp_status')==0:
                assert val(d,'window_rsp_binding_valid')and val(d,'window_rsp_send_closed')and val(d,'freeze_drained')
                self.closed.add((val(d,'window_rsp_user'),val(d,'window_rsp_stream')))
            if val(d.dut,'directory_valid')and val(d.dut,'directory_ready'):self.directory_accepted+=1
            for client in range(5):
                if val(d,'all_rsp_valid')>>client&val(d,'all_rsp_ready')>>client&1:
                    p=self.pending[client];assert p is not None;p['acked']=True;p['status']=val(d,'fault_rsp_status')>>(8*client)&255
                    if client==0 and p['write']:
                        self.metadata_writes+=1
                        if not p['status']:self.progress_acks+=1
                        else:assert bytes(self.memory.data[p['address']:p['address']+8])==p['data'].to_bytes(9,'little')[:8],'Failed write did not physically apply'
                    self.pending[client]=None
                if val(d,'all_valid')>>client&val(d,'all_ready')>>client&1:
                    assert self.pending[client]is None
                    address=val(d,'all_addr')>>(23*client)&0x7fffff;write=val(d,'all_write')>>client&1
                    assert val(d,'all_bytes')>>(4*client)&15==8
                    if write:
                        assert address>=self.a['work_floor']and client!=1
                        if client==0:assert self.a['progress_base']<=address<self.a['progress_base']+self.a['progress_bytes']
                        if client==2:assert self.a['stream_base']<=address<self.a['stream_base']+self.a['stream_bytes']and(address-self.a['stream_base'])%128<64
                        if client==4:assert self.window_base<=address<self.window_base+self.window_bytes or self.context_base<=address<self.context_base+self.context_bytes and 168<=(address-self.context_base)%256<=208
                    if client in(0,1):assert val(d,'record_lease_active')
                    p=dict(client=client,address=address,write=write,data=val(d,'all_data')>>(72*client)&((1<<72)-1),acked=False,status=None)
                    self.pending[client]=p;self.trace.append(p);self.count[client]+=1
                    if client==4:assert val(d,'directory_pool_lock_active')
            service=d.dut.directory_service
            if val(service,'state')==0 and val(service,'reserve_pending')and val(service,'owned_request_ready')and not val(service,'control_pending'):reserve_start=len(self.trace)
            if val(d,'frame_req_valid')and val(d,'frame_req_ready'):
                amount=val(d,'frame_grant_bytes')
                if amount:
                    assert self.current is not None;binding,chunk=self.current
                    assert self.progress_acks==(10 if chunk['ordinal']==0 else 5)
                    writes=[p for p in self.trace[reserve_start:]if p['client']==4 and p['write']]
                    assert len(writes)==2 and all(p['acked']and p['status']==0 for p in writes)
                    assert self.outstanding is None;self.outstanding=amount;self.positive_grants+=1
            if val(d,'m_axis_tx_tvalid'):
                item=tuple(val(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
                if held is not None:assert item==held,'Actual RPC wire promise changed'
                if not val(d,'m_axis_tx_tready'):held=item;self.held_cycles+=1
                else:
                    held=None;data,keep,last,user=item;assert keep and keep&(keep+1)==0
                    self.packet.extend(data.to_bytes(64,'little')[:keep.bit_count()])
                    if last:
                        raw=bytes(self.packet);self.packet.clear();f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw
                        if f.type in(0,1):
                            assert(user,f.stream_id)not in self.closed,'RPC frame followed actual close acknowledgement'
                            assert self.current is not None;binding,chunk=self.current
                            assert(user,f.stream_id)==(binding['user'],binding['stream'])and val(d,'record_lease_active')
                            address=self.a['progress_base']+binding['slot']*32
                            progress=int.from_bytes(self.memory.data[address:address+32],'little')
                            if f.type==0:
                                assert self.outstanding==size;self.outstanding=None
                                assert progress>>188&1 and not(progress>>187&1)
                            elif 'END_STREAM'in f.flags:
                                assert self.progress_acks==(15 if chunk['ordinal']==0 else 10)
                                assert progress>>189&1 and not(progress>>190&1)and self.outstanding is None
                            else:
                                assert chunk['ordinal']==0 and self.progress_acks==5
                                assert progress>>187&1 and not(progress>>188&1)and self.outstanding is None
                            events=self.clients[user].receive_data(raw)
                            for event in events:
                                if type(event).__name__=='ResponseReceived':
                                    assert event.headers==[(':status','200'),('content-type','application/grpc+proto'if binding['format']==2 else'application/grpc+json')]
                                elif type(event).__name__=='TrailersReceived':assert event.headers==[('grpc-status','0')]
                                elif type(event).__name__=='StreamEnded':assert chunk['eos']and f.type==1 and 'END_STREAM'in f.flags
                            self.events.extend((user,f.stream_id,type(e).__name__)for e in events)
                        self.wire.append(raw);self.wire_users.append(user)
            else:assert held is None
            record=tuple(val(d,n)for n in RESULTS+('result_cancelled',))if val(d,'result_valid')else None
            if held_result is not None:assert record==held_result
            held_result=record if record is not None and not val(d,'result_ready')else None
            assert self.allow_error or not val(d,'frame_tracking_error')


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def actual_rpc_native_client_headers_data_trailers_and_commit_faults(d):
    folder=Path(os.environ['PARSER_RPC_RESPONSE_FIXTURES']);reference=json.loads((folder/'rpc_cases.json').read_text())
    initial=(folder/'memory.bin').read_bytes();assert hashlib.sha256(initial).hexdigest()==reference['model_image_sha256']
    memory=Memory(d,bytearray(initial));b=Bench(d,reference,memory)
    b.set(rst=1,s_axis_tokens_tvalid=0,result_ready=0,m_axis_tx_tready=0,host_valid=0,program_valid=0,fault_enable=0,fault_arm=0,
        freeze_valid=0,freeze_release_valid=0,b_axis_tvalid=0,lookup_admit=1)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run());cocotb.start_soon(b.observe_actual())
    await cycles(d,5);b.set(rst=0);await cycles(d,3)
    async def reset():
        assert not any(b.pending)and b.outstanding is None and not b.packet and not val(d,'record_lease_active')
        b.set(freeze_valid=0,freeze_release_valid=0,b_axis_tvalid=0);await b.fenced_reset()
        b.clients.clear();b.closed.clear();b.allow_error=False;b.ready_wire=True
    async def prepare(binding):
        await b.open(binding);await b.window(9,binding,4096);b.open_client(binding)
    messages=streams=0
    for group in(reference['groups'][0],reference['groups'][2]):
        await reset()
        for binding in group:await prepare(binding)
        for ordinal in range(max(len(binding['chunks'])for binding in group)):
            for binding in group:
                if ordinal>=len(binding['chunks']):continue
                chunk=binding['chunks'][ordinal];mark=len(b.wire);await b.submit(binding,chunk);result=await b.complete(binding,chunk)
                packets=b.wire[mark:];data=[p for p in packets if p[3]==0];record=b''.join(p[9:]for p in data)
                body=bytes.fromhex(chunk['packet_hex']);assert record==b'\0'+len(body).to_bytes(4,'big')+body
                assert result[14:]==(sum(map(len,packets)),len(packets)),result
                expected_writes=5+5*(ordinal==0)+10*chunk['eos'];assert b.metadata_writes==expected_writes
                progress=int.from_bytes(memory.data[b.a['progress_base']+32*binding['slot']:b.a['progress_base']+32*binding['slot']+32],'little')
                assert progress>>188&1 and not(progress>>187&1)and not(progress>>189&1)
                assert bool(progress>>190&1)==bool(chunk['eos'])
                if chunk['eos']:
                    assert (binding['user'],binding['stream'],'StreamEnded')in b.events;streams+=1
                messages+=1
    async def state(node,number):
        for _ in range(100000):
            if val(node,'state')==number:return
            await FallingEdge(d.clk)
        raise AssertionError(('State wait timed out',str(node),number,val(node,'state')))
    async def fresh(generation,mode=0):
        await reset();binding=dict(slot=0,user=0,stream=1,generation=generation,application=777,format=mode,field=17,protobuf=int(mode==2))
        await prepare(binding);return binding
    async def close_frozen(binding):
        await b.wait('freeze_drained');await b.window(10,binding)
        await b.send('freeze_release_valid','freeze_release_ready')
    chunk=dict(token=15339,eos=1,ordinal=0);cancellations=[]
    # The accepted descriptor has not acquired any actual shared LOAD. The
    # acknowledged key close suppresses that LOAD and the inverse/progress work.
    binding=await fresh(6000);b.set(lookup_admit=0);mark=len(b.wire);before=b.count[:3]
    await b.submit(binding,chunk);await b.wait('lookup_waiting');await b.freeze(binding);await close_frozen(binding)
    await b.complete(binding,chunk,17,1,cancelled=1,lease=False,application=0)
    assert b.count[:3]==before and len(b.wire)==mark and not val(d,'recovery_required')
    b.set(lookup_admit=1);await b.host(3,binding);cancellations.append('prelookup_without_header_or_load')
    other=dict(slot=0,user=1,stream=3,generation=6001,application=777,format=0,field=17,protobuf=0)
    await prepare(other);await b.submit(other,chunk);await b.complete(other,chunk)
    assert(1,3,'StreamEnded')in b.events
    # An independent B/control promise remains held while the private initial
    # header is aborted through the actual A wire fence and metadata rollback.
    binding=await fresh(6002);b.ready_wire=False;mark=len(b.wire);ping=cocotb.start_soon(b.ping())
    await b.wait('m_axis_tx_tvalid');await cycles(d,2);await b.submit(binding,chunk)
    await b.wait_internal(d.dut.response.headers,'m_axis_tx_tvalid');await b.freeze(binding)
    await close_frozen(binding);await b.complete(binding,chunk,16,5,cancelled=1)
    assert len(b.wire)==mark and b.metadata_writes==10 and not val(d,'recovery_required')
    b.ready_wire=True;control=await ping;await cycles(d,2);assert b.wire[mark:]==[control]
    cancellations.append('private_header_and_held_control')
    # A header already offered on the actual wire drains, then commits, before
    # an otherwise ready matching CLOSE_SEND_KEY can handshake.
    binding=await fresh(6003);b.ready_wire=False;mark=len(b.wire);await b.submit(binding,chunk)
    await b.wait('m_axis_tx_tvalid');await cycles(d,2);await b.freeze(binding)
    closing=cocotb.start_soon(b.window(10,binding));commands=b.count[4]
    for _ in range(17):
        await cycles(d);assert not val(d,'freeze_drained')and not val(d,'window_req_ready')and b.count[4]==commands
    b.ready_wire=True;await closing;await b.send('freeze_release_valid','freeze_release_ready')
    await b.complete(binding,chunk,16,5,cancelled=1)
    assert [p[3]for p in b.wire[mark:]]==[1]and b.metadata_writes==10 and not val(d,'recovery_required')
    cancellations.append('offered_header_before_close')
    # The final trailer has the same actual first-offer ownership as DATA.
    # Once offered it drains and commits, and its completed success is retained.
    binding=await fresh(6004);mark=len(b.wire);await b.submit(binding,chunk)
    await state(d.dut.response.envelope,10);b.ready_wire=False;d.m_axis_tx_tready.value=0
    await b.wait('m_axis_tx_tvalid');await cycles(d,2);assert val(d,'m_axis_tx_tdata')>>32&255==5
    await b.freeze(binding);closing=cocotb.start_soon(b.window(10,binding));commands=b.count[4]
    for _ in range(17):await cycles(d);assert not val(d,'freeze_drained')and not val(d,'window_req_ready')and b.count[4]==commands
    b.ready_wire=True;await closing;await b.send('freeze_release_valid','freeze_release_ready');await b.complete(binding,chunk)
    assert [p[3]for p in b.wire[mark:]]==[1,0,1]and b.metadata_writes==20 and not val(d,'recovery_required')
    cancellations.append('offered_trailer_completes_before_close')
    # An unoffered trailer is different: roll back only its durable intent,
    # preserve the held B frame, and report expected EOS cancellation.
    binding=await fresh(6005);mark=len(b.wire);await b.submit(binding,chunk)
    await state(d.dut.response.envelope,8);b.ready_wire=False;d.m_axis_tx_tready.value=0
    ping=cocotb.start_soon(b.ping());await b.wait('m_axis_tx_tvalid');await cycles(d,2)
    await b.wait_internal(d.dut.response.headers,'m_axis_tx_tvalid');await b.freeze(binding);await close_frozen(binding)
    await b.complete(binding,chunk,17,1,cancelled=1)
    assert [p[3]for p in b.wire[mark:]]==[1,0]and b.metadata_writes==20 and not val(d,'recovery_required')
    b.ready_wire=True;control=await ping;await cycles(d,2);assert b.wire[-1]==control
    cancellations.append('private_trailer_expected_cancel')
    # The same key in a different window arena is not authority to abort this
    # response's initial header. Its grant can wait for ordinary freeze release.
    binding=await fresh(6006);b.ready_wire=False;mark=len(b.wire);await b.submit(binding,chunk)
    await b.wait('m_axis_tx_tvalid');await cycles(d,2);await b.freeze(binding,foreign_scope=True)
    await b.wait('freeze_drained');assert not val(d.dut,'envelope_match_freeze')and not val(d,'data_wire_paused')
    b.ready_wire=True;await b.send('freeze_release_valid','freeze_release_ready');await b.complete(binding,chunk)
    assert [p[3]for p in b.wire[mark:]]==[1,0,1]and not val(d,'recovery_required');b.scope_proofs+=1
    cancellations.append('foreign_scope_does_not_abort_header')
    # SSE remains a separate required HTTP transport. This gRPC variant rejects
    # it before inverse/progress writes rather than mislabelling an SSE body.
    binding=await fresh(6007,1);mark=len(b.wire);inverse_before=b.count[1]
    await b.submit(binding,chunk);await b.complete(binding,chunk,3,6)
    assert len(b.wire)==mark and b.count[1]==inverse_before and b.metadata_writes==0 and not val(d,'recovery_required')
    binding['format']=0;await b.submit(binding,chunk);await b.complete(binding,chunk)
    assert(0,1,'StreamEnded')in b.events
    faults=[]
    for phase in range(20):
        await reset();binding=dict(slot=0,user=0,stream=1,generation=5000+phase,application=777,format=0,field=17,protobuf=0)
        await prepare(binding);chunk=dict(token=15339,eos=1,ordinal=0);mark=len(b.wire);b.allow_error=True
        await b.submit(binding,chunk)
        for _ in range(100000):
            if val(d.dut.response.rpc,'state')==12:break
            await FallingEdge(d.clk)
        else:raise AssertionError('Initial progress commit did not start')
        assert b.pending[0]is None
        b.set(fault_enable=1,fault_client=0,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        await b.complete(binding,chunk,5 if phase<5 else 20,3,0x75)
        assert val(d,'fault_injected')and val(d,'recovery_required')and b.metadata_writes==phase+1
        kinds=[p[3]for p in b.wire[mark:]];assert kinds==([]if phase<5 else[1]if phase<10 else[1,0]if phase<15 else[1,0,1]),(phase,kinds)
        for _ in range(19):await cycles(d);assert not val(d,'s_axis_tokens_tready')and len(b.wire)==mark+len(kinds)
        faults.append(dict(phase=phase,wire_types=kinds,memory_writes=phase+1))
        d._log.info('Verified actual envelope commit fault %d',phase)
    assert memory.data[:b.a['work_floor']]==initial[:b.a['work_floor']]
    accepted=dict(phase='passed',native_complete_rpc_streams=streams,actual_gpu_messages=messages,
        actual_gpu_descriptors=b.gpu_accepted,envelope_cancellation_cases=cancellations,
        ordinary_other_stream_completes_without_global_reset=True,rejected_sse_mode_retries_as_json_without_reset=True,
        injected_progress_and_envelope_write_faults=faults,actual_positive_grants=b.positive_grants,actual_wire_frames=len(b.wire),
        actual_inverse_full_vocabulary=True,actual_bow_and_rpc_cached_load=True,native_clients_consume_actual_rtl_frames=True,
        all_progress_acks_before_initial_headers=True,header_wire_and_commit_before_actual_data=True,
        both_actual_debit_acks_before_data=True,trailer_intent_before_end_stream=True,trailer_commit_before_gpu_result=True,
        physical_write_errors_do_not_repeat_wire=True,held_gpu_results_retain_actual_load=True,complete_model_prefix_immutable=True,
        raw_network_request_and_reset_joined=False,sse_transport_joined=False,whole_rpc_gpu_image_lease_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
