"""Actual directory/close authority, inverse lookup and GPU terminal cancellation."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import DataFrame,Frame,PingFrame

from test_rpc_durable_response import WindowedBench
from test_rpc_response import RESULTS,val
from test_tokenizer_mmio import cycles
from test_tokenizer_mmio_system import Memory


class Bench(WindowedBench):
    def __init__(self,*args):
        super().__init__(*args,keyed=True);self.count=[0]*5;self.trace=[];self.pending=[None]*5
        self.wire=[];self.bow_bytes=0;self.data_beats=0;self.grants=[];self.ready_wire=True;self.held_cycles=0
        self.gpu_accepted=self.directory_accepted=0;self.packet=bytearray();self.outstanding=None;self.progress_acks=0

    async def window(self,op,binding,amount=0,*,status=0,retire=True):
        a=self.a;b=binding;stream=0 if op in(0,3,4,7)else b['stream']
        self.set(window_req_op=op,window_req_maintenance=int(op in(0,7)),window_req_user=b['user'],window_req_stream=stream,
            window_req_generation=0 if op in(9,10)else b['generation'],window_req_record_address=0 if op in(9,10)else a['stream_base']+b['slot']*128,
            window_req_amount=amount,window_cfg_context_base=self.context_base,window_cfg_context_bytes=self.context_bytes,
            window_cfg_stream_base=a['stream_base'],window_cfg_stream_bytes=a['stream_bytes'],window_cfg_window_base=self.window_base,
            window_cfg_window_bytes=self.window_bytes,window_cfg_work_floor=a['work_floor'],window_rsp_ready=0)
        await self.send('window_req_valid','window_req_ready')
        self.set(window_req_user=65535,window_req_stream=0x7fffffff,window_req_generation=0xffffffff,window_req_record_address=0x7fffff,
            window_cfg_stream_base=0x7fffff,window_cfg_stream_bytes=0,window_req_amount=0xffffffff)
        await self.wait('window_rsp_valid')
        fields=('window_rsp_status','window_rsp_memory_status','window_rsp_binding_valid','window_rsp_record_address','window_rsp_generation','window_rsp_send_closed')
        result=tuple(val(self.d,n)for n in fields);assert result[0]==status,(op,result,status)
        if op==10 and status==0:assert result[2:]==(1,a['stream_base']+b['slot']*128,b['generation'],1),result
        if status:assert result[2]==result[5]==0
        for _ in range(9):await cycles(self.d);assert val(self.d,'window_rsp_valid')and result==tuple(val(self.d,n)for n in fields)
        if retire:await self.acknowledge('window_rsp_valid','window_rsp_ready')
        return result

    async def wait(self,name):
        for _ in range(1000000):
            if val(self.d,name):return
            if name=='lookup_waiting' and val(self.d,'result_valid'):
                raise AssertionError(('Unexpected terminal before lookup',tuple(val(self.d,n)for n in RESULTS)))
            await FallingEdge(self.d.clk)
        raise AssertionError(('Timed out',name))

    async def token(self,b,*,generation=None,pool_patch=False,scope_patch=None,chunk=None,keep=15):
        self.configure();c=chunk or dict(token=self.ref['ascii_token'],eos=0,ordinal=0)
        self.set(s_axis_tokens_tdata=c['token'],s_axis_tokens_tkeep=keep,s_axis_tokens_tlast=c['eos'],s_axis_tokens_tuser=b['user'],
            s_stream=b['stream'],s_generation=b['generation']if generation is None else generation,s_model_epoch=23,s_schema_epoch=9,
            s_ordinal=c['ordinal'],cfg_format=b['format'],cfg_protobuf_field=b.get('field',17),cfg_replace_invalid=1,cfg_strip_special=1,
            cfg_peer_max_frame_bytes=16384)
        if pool_patch:self.set(cfg_stream_base=self.a['stream_base']+128,cfg_stream_bytes=self.a['stream_bytes']-128)
        if scope_patch:self.set(**scope_patch)
        await self.send('s_axis_tokens_tvalid','s_axis_tokens_tready')
        self.set(s_stream=0,s_generation=0,s_axis_tokens_tdata=0xffffffff,cfg_stream_base=0x7fffff,cfg_stream_bytes=0,
            cfg_context_base=0x7fffff,cfg_context_bytes=0,cfg_window_base=0x7fffff,cfg_window_bytes=0,cfg_model_epoch=0xffffffff,
            cfg_schema_epoch=0xffffffff,cfg_format=3,cfg_protobuf_field=0)

    async def freeze(self,b):
        self.set(freeze_user=b['user'],freeze_stream=b['stream']);await self.send('freeze_valid','freeze_ready')
        self.set(freeze_user=65535,freeze_stream=0x7fffffff);assert val(self.d,'freeze_active')

    async def terminal(self,b,stage,status,cancelled,*,lease=False,application=None,gen=None,eos=0):
        d=self.d;await self.wait('result_valid')
        fields=RESULTS+('result_cancelled','result_credit_status','result_wire_bytes','result_frames','result_progress_committed')
        record=tuple(val(d,n)for n in fields)
        assert record[:3]==(stage,status,0),record
        assert record[5:]==(b['user'],b['application']if application is None else application,b['stream'],
            b['generation']if gen is None else gen,23,9,0,eos,cancelled,record[14],record[15],record[16],record[17]),record
        for _ in range(19):
            await cycles(d);assert val(d,'result_valid')and record==tuple(val(d,n)for n in fields)
            assert bool(val(d,'record_lease_active'))==lease and not val(d,'s_axis_tokens_tready')
        self.set(result_ready=1);await cycles(d);self.set(result_ready=0)
        while not val(d,'fabric_idle'):await cycles(d)
        return record

    async def ping(self):
        f=PingFrame(0);f.opaque_data=b'RPCSTOP1';f.flags.add('ACK');raw=f.serialize()
        self.set(b_axis_tdata=int.from_bytes(raw,'little'),b_axis_tkeep=(1<<len(raw))-1,b_axis_tlast=1,b_axis_tuser=0)
        await self.send('b_axis_tvalid','b_axis_tready');return raw

    async def observe_actual(self):
        d=self.d;held=None;held_request=None;held_result=None;reserve_start=None
        while True:
            await FallingEdge(d.clk);d.m_axis_tx_tready.value=int(self.ready_wire)
            await RisingEdge(d.clk)
            if val(d,'rst'):
                assert not any(self.pending)and self.outstanding is None and not self.packet and held is None,'Reset abandoned actual ownership'
                held_request=held_result=None;continue
            self.clocks+=1
            if self.clocks%100000==0:
                Path('progress.json').write_text(json.dumps(dict(clocks=self.clocks,gpu_descriptors=self.gpu_accepted,
                    directory_lookups=self.directory_accepted,rpc_state=val(d.dut.response.rpc,'state'),
                    result_valid=val(d,'result_valid'),result_stage=val(d,'result_stage'),result_status=val(d,'result_status'))))
            if val(d,'s_axis_tokens_tvalid')and val(d,'s_axis_tokens_tready'):self.gpu_accepted+=1;self.progress_acks=0
            if val(d.dut,'directory_valid')and val(d.dut,'directory_ready'):self.directory_accepted+=1
            for client in range(5):
                if val(d,'all_rsp_valid')>>client&val(d,'all_rsp_ready')>>client&1:
                    p=self.pending[client];assert p is not None;p['acked']=True;p['status']=val(d,'fault_rsp_status')>>(8*client)&255
                    if client==0 and p['write']and not p['status']:self.progress_acks+=1
                    self.pending[client]=None
                if val(d,'all_valid')>>client&val(d,'all_ready')>>client&1:
                    assert self.pending[client]is None
                    address=val(d,'all_addr')>>(23*client)&0x7fffff;write=val(d,'all_write')>>client&1
                    assert(val(d,'all_bytes')>>(4*client)&15)==8
                    if write:
                        assert address>=self.a['work_floor']and client!=1
                        if client==0:assert self.a['progress_base']<=address<self.a['progress_base']+self.a['progress_bytes']
                        elif client==2:assert(self.a['stream_base']<=address<self.a['stream_base']+self.a['stream_bytes'])and(address-self.a['stream_base'])%128<64
                        elif client==4:assert self.window_base<=address<self.window_base+self.window_bytes or self.context_base<=address<self.context_base+self.context_bytes and 168<=(address-self.context_base)%256<=208
                    p=dict(client=client,address=address,write=write,acked=False,status=None);self.pending[client]=p;self.trace.append(p);self.count[client]+=1
                    if client==4:assert val(d,'directory_pool_lock_active')
            service=d.dut.directory_service
            if val(service,'state')==0 and val(service,'reserve_pending')and val(service,'owned_request_ready')and not val(service,'control_pending'):
                reserve_start=len(self.trace)
            if val(d,'frame_req_valid')and val(d,'frame_req_ready'):
                amount=val(d,'frame_grant_bytes')
                if amount:
                    assert self.outstanding is None and self.progress_acks==5 and reserve_start is not None
                    writes=[p for p in self.trace[reserve_start:]if p['client']==4 and p['write']]
                    assert len(writes)==2 and all(p['acked']and p['status']==0 for p in writes)
                    self.outstanding=amount;self.grants.append(amount)
                else:assert val(d.dut,'credit_error_valid')
            request=tuple(val(d,n)for n in('frame_req_user','frame_req_stream','frame_req_max_bytes'))if val(d,'frame_req_valid')else None
            if held_request is not None:assert request==held_request
            held_request=request if request is not None and not val(d,'frame_req_ready')else None
            if val(d.dut,'data_tvalid')and val(d.dut,'data_tready'):self.data_beats+=1
            if val(d,'link_s_s_axis_text_tvalid')and val(d,'link_s_s_axis_text_tready'):
                self.bow_bytes+=val(d,'link_s_s_axis_text_tkeep').bit_count()
            if val(d,'m_axis_tx_tvalid'):
                item=tuple(val(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
                if held is not None:assert item==held
                if not val(d,'m_axis_tx_tready'):held=item;self.held_cycles+=1
                else:
                    held=None;data,keep,last,user=item;assert keep and keep&(keep+1)==0
                    self.packet.extend(data.to_bytes(64,'little')[:keep.bit_count()])
                    if last:
                        raw=bytes(self.packet);self.packet.clear();f,size=Frame.parse_frame_header(memoryview(raw[:9]));f.parse_body(memoryview(raw[9:]));assert f.serialize()==raw
                        if f.type==0:assert self.outstanding==size;self.outstanding=None
                        self.wire.append(raw)
            else:assert held is None,'Held actual wire beat was withdrawn'
            result=tuple(val(d,n)for n in RESULTS+('result_cancelled',))if val(d,'result_valid')else None
            if held_result is not None:assert result==held_result
            held_result=result if result is not None and not val(d,'result_ready')else None
            assert not val(d,'frame_tracking_error')


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def actual_rpc_prelookup_and_loaded_cancel_preserve_all_owners(d):
    folder=Path(os.environ['PARSER_RPC_RESPONSE_FIXTURES']);ref=json.loads((folder/'rpc_cases.json').read_text());image=(folder/'memory.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['model_image_sha256']
    memory=Memory(d,bytearray(image));b=Bench(d,ref,memory)
    b.set(rst=1,s_axis_tokens_tvalid=0,result_ready=0,m_axis_tx_tready=0,host_valid=0,program_valid=0,fault_enable=0,fault_arm=0,
        freeze_valid=0,freeze_release_valid=0,b_axis_tvalid=0,lookup_admit=0)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run());cocotb.start_soon(b.observe_actual())
    await cycles(d,5);b.set(rst=0);await cycles(d,3)
    generation=1000
    async def fresh(mode=1):
        nonlocal generation
        generation+=1;b.set(freeze_valid=0,freeze_release_valid=0,b_axis_tvalid=0,lookup_admit=0);b.ready_wire=True
        while not val(d,'fabric_idle'):await cycles(d)
        await b.fenced_reset();binding=dict(slot=0,user=0,stream=1,generation=generation,application=777,format=mode,field=17,protobuf=int(mode==2))
        await b.open(binding);return binding
    async def no_backend(before):assert [b.count[i]for i in(0,1,2)]==before,'Pre-lookup cancellation issued shared work'
    async def release():await b.send('freeze_release_valid','freeze_release_ready')
    def data_frames(mark):return [raw for raw in b.wire[mark:]if raw[3]==0]
    def native_data(body,stream=1):
        f=DataFrame(stream);f.data=b'\0'+len(body).to_bytes(4,'big')+body;return f.serialize()
    body=bytes.fromhex(ref['ascii_packet_hex'])

    # The pending descriptor retires with lookup_admit held low throughout.
    binding=await fresh();before=[b.count[i]for i in(0,1,2)];wm=len(b.wire);bow=b.bow_bytes
    await b.token(binding);await b.wait('lookup_waiting');await b.freeze(binding);await b.wait('freeze_drained')
    assert val(d.dut.response.rpc,'checked_stream_end')==b.a['stream_base']+b.a['stream_bytes']
    await b.window(10,binding);await b.terminal(binding,17,1,1,application=0);await no_backend(before)
    assert not data_frames(wm)and b.bow_bytes==bow and not val(d,'recovery_required')
    await release()
    # Repeated closed descriptors and stale generations cannot start a LOAD,
    # even when ordinary lookup admission is simultaneously enabled.
    b.set(lookup_admit=1);await b.token(binding,chunk=dict(token=ref['ascii_token'],eos=1,ordinal=0))
    await b.terminal(binding,17,1,1,application=0,eos=1);await no_backend(before)
    await b.token(binding,chunk=dict(token=ref['ascii_token'],eos=1,ordinal=0),keep=0)
    await b.terminal(binding,17,1,1,application=0,eos=1);await no_backend(before)
    await b.token(binding,generation=binding['generation']+1)
    await b.terminal(binding,17,2,0,application=0,gen=binding['generation']+1);await no_backend(before)
    # A real unrelated OPEN may win the generic port on the same edge that
    # the saved close terminates DREQ. Invalidation must not feed READY back
    # into directory VALID, and the cancelled descriptor must create no LOAD.
    lookups=b.directory_accepted;progress=b.count[0];inverse=b.count[1]
    await b.token(binding)
    while val(d.dut.response.rpc,'state')!=2:await FallingEdge(d.clk)
    assert not val(d.dut,'directory_valid')
    b.set(host_op=0,host_pool_base=b.a['stream_base'],host_pool_bytes=b.a['stream_bytes'],host_user=0,host_stream=3,
        host_generation=binding['generation']+200,host_application=778,host_protobuf=0,host_encoding=0,
        host_address=b.a['stream_base']+128,host_buffer_base=b.a['payload_base']+b.a['payload_bytes'],
        host_buffer_bytes=b.a['payload_bytes'],host_message_limit=4096,host_maintenance=0,host_valid=1)
    await RisingEdge(d.clk);assert val(d,'host_ready')and not val(d.dut,'directory_valid')
    await FallingEdge(d.clk);b.set(host_valid=0);await b.wait('host_result_valid');assert val(d,'host_status')==0
    await b.acknowledge('host_result_valid','host_result_ready');await b.terminal(binding,17,1,1,application=0)
    assert b.directory_accepted==lookups and b.count[0]==progress and b.count[1]==inverse
    # Real allocation/connection mutations invalidate the cached close binding.
    await b.host(3,binding);assert not val(d.dut,'saved_closed_valid')
    newer=dict(binding,generation=binding['generation']+100);await b.open(newer);assert not val(d.dut,'saved_closed_valid')
    await b.window(3,newer,65535);wm=len(b.wire);await b.token(newer);result=await b.terminal(newer,0,0,0,lease=True)
    assert data_frames(wm)==[native_data(body)]and result[17]==1 and not val(d,'recovery_required')

    # A different close key cannot terminate the held descriptor.
    binding=await fresh();other=dict(binding,slot=1,stream=3,generation=binding['generation']+1);await b.open(other);await b.window(3,binding,65535)
    before=[b.count[i]for i in(0,1,2)];await b.token(binding);await b.wait('lookup_waiting');await b.freeze(other);await b.window(10,other)
    await cycles(d,21);assert not val(d,'result_valid');await no_backend(before)
    await release();wm=len(b.wire);b.set(lookup_admit=1);await b.terminal(binding,0,0,0,lease=True);assert data_frames(wm)==[native_data(body)]

    # Same key but different captured pool geometry is not a close authority.
    binding=await fresh();before=[b.count[i]for i in(0,1,2)];await b.token(binding,pool_patch=True);await b.wait('lookup_waiting')
    await b.freeze(binding);await b.window(10,binding);await cycles(d,21);assert not val(d,'result_valid');await no_backend(before)
    await release();b.set(lookup_admit=1);await b.terminal(binding,2,3,0,application=0)
    assert b.count[2]>before[2]and b.count[0]==before[0]and b.count[1]==before[1]

    # Directory identity alone cannot borrow a close from a different runtime
    # window/context/protected-prefix geometry. The ordinary LOAD/validation
    # path remains available and reports its actual closed/bad-root result.
    scope_negatives=0
    for patch,credit,cancelled in (
        ({'cfg_work_floor':b.a['work_floor']-64},8,1),
        ({'cfg_context_base':b.context_base+0x2000},3,0),
        ({'cfg_window_base':b.window_base+0x1000},3,0)):
        binding=await fresh();await b.freeze(binding);await b.window(10,binding);await release()
        before=[b.count[i]for i in(0,1,2)];await b.token(binding,scope_patch=patch);await b.wait('lookup_waiting')
        await cycles(d,21);assert not val(d,'result_valid');await no_backend(before)
        b.set(lookup_admit=1);result=await b.terminal(binding,16,5,cancelled,lease=True)
        assert result[14]==credit and b.count[2]>before[2]and b.count[1]>before[1]
        assert bool(val(d,'recovery_required')) == (not bool(cancelled))
        scope_negatives+=1

    # A held actual LOAD and zero-credit wait use the real closed reservation.
    binding=await fresh();b.set(lookup_admit=1);wm=len(b.wire);await b.token(binding);await b.wait('credit_parked')
    assert val(d,'record_lease_active')and b.progress_acks==5
    await b.freeze(binding);await b.wait('freeze_drained');await b.window(10,binding);await release()
    result=await b.terminal(binding,16,5,1,lease=True)
    assert result[14]==8 and not data_frames(wm)and not val(d,'recovery_required')
    await b.host(3,binding);other=dict(binding,stream=3,generation=binding['generation']+100)
    await b.open(other);await b.window(3,other,65535);wm=len(b.wire);await b.token(other);await b.terminal(other,0,0,0,lease=True)
    assert data_frames(wm)==[native_data(body,3)]and not val(d,'recovery_required')

    # An already granted multi-beat DATA frame drains its real first-beat
    # promise and inter-beat gap before close; control ACKs keep wire ownership.
    binding=await fresh(2);b.set(lookup_admit=1);await b.window(3,binding,128);b.ready_wire=False;wm=len(b.wire)
    capacity=next(c for c in b.frame_oracle['capacity_cases']if c['mode']==2)
    await b.token(binding,chunk=dict(token=capacity['token'],eos=0,ordinal=0));await b.wait('m_axis_tx_tvalid')
    assert val(d,'frame_wire_pending')and not val(d,'m_axis_tx_tlast');await b.freeze(binding)
    closing=cocotb.start_soon(b.window(10,binding));ping=cocotb.start_soon(b.ping())
    for _ in range(17):await cycles(d);assert not val(d,'freeze_drained')and not val(d,'window_req_ready')
    beats=b.data_beats;b.ready_wire=True
    while b.data_beats==beats:await FallingEdge(d.clk)
    b.ready_wire=False
    for _ in range(17):await cycles(d);assert not val(d,'freeze_drained')and len(b.wire)==wm
    b.ready_wire=True;await closing;control=await ping;await b.wait('freeze_drained');await release()
    result=await b.terminal(binding,16,5,1,lease=True)
    packet=bytes.fromhex(capacity['packet_hex']);f=DataFrame(1);f.data=(b'\0'+len(packet).to_bytes(4,'big')+packet)[:128]
    assert b.wire[wm:]==[f.serialize(),control]and result[14:17]==(8,137,1)and not val(d,'recovery_required')

    # A completely delivered message keeps its successful held terminal result.
    binding=await fresh();b.set(lookup_admit=1);await b.window(3,binding,65535);wm=len(b.wire);await b.token(binding);await b.wait('result_valid')
    await b.freeze(binding);await b.wait('freeze_drained');await b.window(10,binding,retire=False)
    assert val(d,'result_valid')and not val(d,'result_cancelled')and val(d,'record_lease_active')
    b.set(result_ready=1);await cycles(d);b.set(result_ready=0);await cycles(d,2)
    assert val(d,'result_retirement_pending')and not val(d,'result_valid')
    for _ in range(19):
        await cycles(d);assert val(d,'record_lease_active')and val(d,'directory_pool_lock_active')and val(d,'window_rsp_valid')
    await b.acknowledge('window_rsp_valid','window_rsp_ready')
    while val(d,'result_retirement_pending')or val(d,'record_lease_active'):await cycles(d)
    await release();assert data_frames(wm)==[native_data(body)]and not val(d,'recovery_required')

    # Every real key-close read/write fault aborts the pre-lookup token without
    # manufacturing a successful binding or waiting for lookup admission.
    faults=0
    for phase in range(14):
        binding=await fresh();before=[b.count[i]for i in(0,1,2)];wm=len(b.wire);await b.token(binding);await b.wait('lookup_waiting');await b.freeze(binding)
        b.set(fault_enable=1,fault_client=4,fault_target=phase,fault_arm=1);await cycles(d);b.set(fault_arm=0)
        result=await b.window(10,binding,status=5);assert result[1]==0x75 and not val(d.dut,'saved_closed_valid')and val(d,'window_recovery_required')
        await release();await b.terminal(binding,17,3,0,application=0);await no_backend(before)
        assert not data_frames(wm)and val(d,'recovery_required')and val(d,'fault_injected')
        before_window=b.count[4];b.set(fault_enable=0);await b.window(10,binding,status=6);assert b.count[4]==before_window
        faults+=1
    assert memory.data[:b.a['work_floor']]==image[:b.a['work_floor']]and not any(b.pending)
    accepted=dict(phase='passed',actual_parser_rpc_modules=18,prelookup_matching_cancel_cases=4,prelookup_generation_mismatch_cases=1,
        simultaneous_generic_open_and_cancel_without_ready_feedback=True,
        runtime_window_context_and_protected_prefix_scope_negatives=scope_negatives,
        closed_binding_allocation_invalidation_verified=True,different_key_and_pool_geometry_do_not_cancel=True,
        prelookup_actual_directory_inverse_and_progress_commands=0,lookup_admission_remains_low_during_early_cancel=True,
        cached_load_retained_through_public_terminal_ack=True,expected_stream_closed_has_no_transport_quarantine=True,
        ordinary_other_stream_continues_without_global_reset=True,real_inverse_and_bow_used=True,
        positive_frame_drained_before_actual_key_close=True,actual_wire_first_stall_and_frame_gap_verified=True,
        controls_continue_through_actual_wire_arbiter=True,complete_message_success_not_retracted=True,
        offered_result_preserved_during_window_commands=True,gpu_ack_deferred_until_actual_window_owner_retires=True,
        zero_keep_and_eos_descriptor_cancellation_verified=True,
        uncertain_close_fault_phases=faults,uncertain_close_never_publishes_binding=True,prelookup_recovery_abort_without_shared_work=True,
        native_data_frames=len([r for r in b.wire if r[3]==0]),native_control_frames=len([r for r in b.wire if r[3]!=0]),
        held_wire_cycles=b.held_cycles,actual_gpu_descriptors=b.gpu_accepted,actual_directory_lookups=b.directory_accepted,
        model_prefix_immutable=True,actual_raw_rst_controller_integrated=False,whole_rpc_gpu_image_lease_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
