"""Actual raw requests -> DMA IDs -> RPC-bound inverse/BoW/application bytes."""
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.queue import Queue
from cocotb.triggers import FallingEdge, RisingEdge
from test_http2_prefill import Bench, commands, value
from test_tokenizer_mmio import cycles
from test_tokenizer_mmio_system import Memory


RESULTS=('response_result_stage','response_result_status','response_result_memory_status','response_result_bytes',
         'response_result_tx_emitted','response_result_user','response_result_application','response_result_stream',
         'response_result_generation','response_result_model_epoch','response_result_schema_epoch','response_result_ordinal','response_result_eos')


class JointBench(Bench):
    def __init__(self,d,layout,memory,reverse,control=None,return_bow=None):
        super().__init__(d,layout,memory)
        self.control=d.dut if control is None else control
        self.return_bow=d.dut.reverse.response.bow if return_bow is None else return_bow
        self.reverse=reverse;self.gpu_queue=Queue();self.jobs={};self.dma_packets=[];self.dma_current=[]
        self.current_response=None;self.tx=bytearray();self.bow=bytearray();self.tx_last=self.bow_last=False
        self.held_tx=self.held_bow=self.held_result=None;self.response_rng=random.Random(20261120)
        self.response_chunks=self.response_rejections=self.response_faults=self.response_bytes=0
        self.response_stalls=self.return_bow_stalls=self.response_held_cycles=self.return_lease_cycles=0
        self.early_gpu_admissions=self.waited_for_prefill=self.reverse_memory_commands=0
        self.gpu_owned=False;self.mid_packet_available=False
        self.mid_packet_gpu_admissions=self.continued_rx_beats=self.owned_schedule_cycles=0

    def statistics(self):
        result=super().statistics()
        result.update(response_chunks=self.response_chunks,response_bytes=self.response_bytes,
            pending_return_jobs=sum(not job['done']for job in self.jobs.values()),
            mid_packet_gpu_admissions=self.mid_packet_gpu_admissions,continued_rx_beats=self.continued_rx_beats)
        return result

    def poison(self):
        super().poison()
        # These are common committed image fields. Another interface may own
        # a pending GPU handshake while packet-only fields are poisoned.
        self.set(cfg_model_epoch=23,cfg_schema_epoch=9,cfg_work_floor=self.layout[6])

    def response_configuration(self,reference):
        self.configure();a=self.reverse
        self.set(cfg_response_progress_base=a['response_progress']['base'],cfg_response_progress_bytes=a['response_progress']['bytes'],
                 cfg_response_directory_base=a['model_directory']['base'],cfg_response_directory_bytes=a['model_directory']['capacity'],
                 cfg_response_pool_base=a['string_pool']['base'],cfg_response_pool_bytes=a['string_pool']['capacity'],
                 cfg_response_strip_special=1,cfg_response_replace_invalid=1,cfg_response_format=reference['format'],cfg_response_protobuf_field=reference['field'])

    async def response_ready(self):
        while True:
            await FallingEdge(self.d.clk)
            self.d.m_axis_tx_tready.value=not value(self.d,'rst')and self.clocks%31>=9 and self.response_rng.randrange(4)!=0

    def capture(self,target,prefix,width,held,is_bow=False):
        valid=value(target,prefix+'tvalid');ready=value(target,prefix+'tready')
        snapshot=tuple(value(target,prefix+name)for name in('tdata','tkeep','tlast','tuser'))if valid else None
        if held is not None:assert snapshot==held,('Held response changed',prefix)
        if valid:
            assert self.current_response is not None
            reference,chunk,generation,error,expected_tx,expected_bow=self.current_response
            assert value(self.d,'response_directory_lease_active')
            expected=expected_bow if is_bow else expected_tx
            assert expected is not None,('Rejected return exposed stream',prefix,error)
            if not ready:
                if is_bow:self.return_bow_stalls+=1
                else:self.response_stalls+=1
            else:
                data,keep,last,user=snapshot;assert user==reference['application']
                assert keep==(1<<keep.bit_count())-1 and(last or keep.bit_count()==width)
                assert not(self.bow_last if is_bow else self.tx_last)
                sink=self.bow if is_bow else self.tx
                for lane in range(width):
                    byte=data>>(8*lane)&255
                    if keep>>lane&1:sink.append(byte)
                    else:assert byte==0
                if last:
                    if is_bow:self.bow_last=True
                    else:self.tx_last=True
        return snapshot if valid and not ready else None

    async def response_observer(self):
        d=self.d
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            assert bool(value(self.control,'return_pending'))==self.gpu_owned,'Scheduling grant differs from accepted descriptor/result ownership'
            gpu_accept=value(d,'s_axis_generated_tvalid')and value(d,'s_axis_generated_tready')
            rx_accept=value(d,'s_axis_rx_tvalid')and value(d,'s_axis_rx_tready')
            rx_active=value(self.control,'rx_active')
            if self.gpu_owned:
                self.owned_schedule_cycles+=1
                assert not any(value(d,n)for n in('command_ready','stream_cfg_ready','queue_cfg_ready','cfg_schema_ready'))
                if rx_accept:
                    assert rx_active,'An unowned new packet crossed the accepted-return fence'
                    self.continued_rx_beats+=1
            if gpu_accept:
                assert not self.gpu_owned
                if rx_active:self.mid_packet_gpu_admissions+=1
                else:assert not rx_accept,'A new packet and return descriptor were admitted together'
                self.gpu_owned=True
            if value(d,'response_result_valid')and value(d,'response_result_ready'):
                assert self.gpu_owned;self.gpu_owned=False
            if rx_accept and not value(d,'s_axis_rx_tlast')and (0,1)in self.jobs:
                self.mid_packet_available=True
            if value(d,'m_axis_tokens_tvalid')and value(d,'m_axis_tokens_tready'):
                data,keep=value(d,'m_axis_tokens_tdata'),value(d,'m_axis_tokens_tkeep')
                self.dma_current.extend(data>>(32*lane)&0xffffffff for lane in range(16)if keep>>(4*lane)&15==15)
                if value(d,'m_axis_tokens_tlast'):
                    self.dma_packets.append((value(d,'dma_connection'),value(d,'dma_stream'),value(d,'dma_generation'),list(self.dma_current)))
                    self.dma_current.clear()
            if value(d,'s_axis_generated_tvalid')and value(d,'s_axis_generated_tready')and value(d,'payload_lease_active'):
                self.early_gpu_admissions+=1
            if value(d,'payload_lease_active')and value(self.control,'r_directory_valid'):
                assert not value(self.control,'r_directory_ready'),'Return LOAD bypassed an active prefill payload lease'
                self.waited_for_prefill+=1
            self.return_lease_cycles+=value(d,'response_directory_lease_active')
            if not value(d,'response_idle')and not value(self.control,'rx_active'):
                assert not value(d,'s_axis_rx_tready'),'New packet crossed the return ownership fence'
            requests=value(d,'mem_valid')&value(d,'mem_ready')
            for client in(20,21):
                if requests>>client&1:
                    self.reverse_memory_commands+=1
                    assert value(d,'response_directory_lease_active')
                    if value(d,'mem_write')>>client&1:
                        address=value(d,'mem_addr')>>(23*client)&0x7fffff
                        size=value(d,'mem_bytes')>>(4*client)&15
                        p=self.reverse['response_progress']
                        assert client==20 and size==8 and p['base']<=address and address+size<=p['base']+p['bytes']
                        assert self.tx_last,'Return progress changed before application TX retired'
            self.held_tx=self.capture(d,'m_axis_tx_',64,self.held_tx)
            self.held_bow=self.capture(self.return_bow,'m_egress_',16,self.held_bow,True)
            snapshot=tuple(value(d,n)for n in RESULTS)if value(d,'response_result_valid')else None
            if self.held_result is not None:assert snapshot==self.held_result
            self.held_result=snapshot if snapshot is not None and not value(d,'response_result_ready')else None
            if self.held_result is not None:
                self.response_held_cycles+=1
                assert not value(d,'s_axis_generated_tready')and value(d,'mem_valid')>>20==0

    async def send_response(self,reference,chunk,generation,error=(0,0,0),fault=None,ordinal=None,bow=None):
        d=self.d;good=error[1]==0
        packet=bytes.fromhex(chunk['packet_hex'])if good else None
        raw=bytes.fromhex(chunk['bow_hex'])if good else bow
        self.current_response=(reference,chunk,generation,error,packet,raw)
        self.tx.clear();self.bow.clear();self.tx_last=self.bow_last=False
        self.response_configuration(reference)
        self.set(s_axis_generated_tdata=chunk['token'],s_axis_generated_tkeep=15,s_axis_generated_tlast=chunk['eos'],
            s_axis_generated_tuser=reference['connection'],generated_stream=reference['stream'],generated_generation=generation,
            generated_model_epoch=23,generated_schema_epoch=9,generated_ordinal=chunk['ordinal']if ordinal is None else ordinal,
            fault_client=fault[0]if fault else -1,fault_target=fault[1]if fault else -1,fault_arm=1)
        await cycles(d);self.set(fault_arm=0)
        await self.send('s_axis_generated_tvalid','s_axis_generated_tready')
        self.set(s_axis_generated_tdata=0xffffffff,generated_generation=0,generated_stream=0,
                 cfg_response_format=3,cfg_response_protobuf_field=0,cfg_response_strip_special=0,cfg_response_replace_invalid=0,
                 cfg_response_progress_base=0x7fffff,cfg_response_progress_bytes=0,cfg_response_directory_bytes=0,cfg_response_pool_bytes=0)
        await self.wait('response_result_valid')
        snapshot=tuple(value(d,n)for n in RESULTS)
        expected=(*error,chunk['decoded_bytes']if good else 0,int(good),reference['connection'],reference['application'],reference['stream'],
                  generation,23,9,chunk['ordinal']if ordinal is None else ordinal,chunk['eos'])
        assert snapshot==expected,('Joined return result',reference['connection'],reference['stream'],chunk['ordinal'],snapshot,expected)
        assert bytes(self.tx)==(packet or b'')and self.tx_last==good,('Application bytes',chunk,bytes(self.tx).hex())
        assert bytes(self.bow)==(raw or b'')and self.bow_last==(raw is not None),('Return BoW bytes',chunk,bytes(self.bow).hex())
        if fault:assert value(d,'fault_injected');self.response_faults+=1
        for _ in range(5):
            await cycles(d);assert tuple(value(d,n)for n in RESULTS)==snapshot and value(d,'response_result_valid')
        self.set(response_result_ready=1);await cycles(d);self.set(response_result_ready=0,fault_client=-1)
        self.current_response=None
        if good:
            self.response_chunks+=1;self.response_bytes+=len(packet)
            address=self.reverse['response_progress']['base']+(self.handles[reference['connection'],reference['stream']]-self.layout[13])//4
            words=struct.unpack_from('<4Q',self.memory.data,address)
            wanted=(0x52535031|generation<<32,23|9<<32,chunk['ordinal']+1|chunk['carry']<<32|chunk['carry_count']<<56|chunk['eos']<<58,
                    reference['field']|reference['format']<<29|1<<31|1<<32)
            assert words==wanted,('Actual durable RPC progress',words,wanted)
            if self.response_chunks%256==0:self.d._log.info('Returned %d actual DMA token chunks',self.response_chunks)
        else:self.response_rejections+=1

    async def gpu_worker(self):
        while True:
            job=await self.gpu_queue.get();index,reference,dma,generation=job['index'],job['reference'],job['dma'],job['generation']
            assert dma==[c['token']for c in reference['chunks']]
            first=reference['chunks'][0]
            if index==0:
                # Keep the original RPC alive, let the next raw request begin,
                # then exercise return admission during an owned RX packet.
                while not self.mid_packet_available:await cycles(self.d)
                await self.send_response(reference,first,generation^0x80000000,error=(3,1,0))
                await self.send_response(reference,first,generation,error=(4,3,0),ordinal=1)
            if index==1:
                await self.send_response(reference,first,generation,error=(8,5,0x75),fault=(21,1),bow=b'')
            for position,chunk in enumerate(reference['chunks']):
                # Feed actual accepted C2H IDs back into the generated-token
                # port. The byte oracle remains independently native-derived.
                assert dma[position]==chunk['token']
                await self.send_response(reference,dict(chunk,token=dma[position]),generation)
                if index==0 and position==0:
                    await self.send_response(reference,chunk,generation,error=(4,4 if chunk['eos']else 3,0))
            job['done']=True
            self.d._log.info('Completed joint response %d: %d actual DMA IDs',index,len(dma))

    async def drain(self,user,stream,application,expected):
        index=self.messages;reference=self.reverse['cases'][index]
        assert(user,stream,application)==(reference['connection'],reference['stream'],reference['application'])
        async def enqueue_when_dma_completes():
            await self.wait('completion_valid')
            while len(self.dma_packets)<=index:await cycles(self.d)
            u,s,generation,dma=self.dma_packets[index]
            assert(u,s)==(user,stream)and dma==expected
            job=dict(index=index,reference=reference,dma=dma,generation=generation,done=False)
            self.jobs[user,stream]=job
            await self.gpu_queue.put(job)
        enqueue=cocotb.start_soon(enqueue_when_dma_completes())
        await super().drain(user,stream,application,expected)
        await enqueue

    async def directory(self,op,user=0,stream=0):
        if op==3 and(user,stream)in self.jobs:
            while not self.jobs[user,stream]['done']:await cycles(self.d)
        await super().directory(op,user,stream)


async def run_bidirectional(d,bench_factory=JointBench,memory_factory=Memory,extra_result=None):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()));assert len(layout)==46
    metadata=json.loads((folder/'fixture_manifest.json').read_text())
    references=json.loads((folder/'reference_cases.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    image=bytearray(b''.join(int(line,16).to_bytes(8,'little')for line in(folder/'memory.mem').read_text().splitlines()))
    assert len(image)==8388608 and hashlib.sha256(image).hexdigest()==metadata['loaded_image_sha256']
    initial=bytes(image);memory=memory_factory(d,image);bench=bench_factory(d,layout,memory,reverse)
    bench.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0)
    bench.configure()
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    cocotb.start_soon(bench.ready_driver());cocotb.start_soon(bench.observe())
    cocotb.start_soon(bench.response_ready());cocotb.start_soon(bench.response_observer());cocotb.start_soon(bench.gpu_worker())
    await cycles(d,5);d.rst.value=0
    bench.set(maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    await bench.send('queue_cfg_valid','queue_cfg_ready');await bench.wait('queue_cfg_result_valid')
    assert value(d,'queue_cfg_status')==0;await bench.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await bench.send('stream_cfg_valid','stream_cfg_ready');await bench.wait('stream_cfg_result_valid')
    assert value(d,'stream_cfg_status')==0;await bench.ack('stream_cfg_result_valid','stream_cfg_result_ready',0)
    await bench.directory(4)
    script=list(commands(folder/'vectors.txt'))
    drains=[i for i,(op,_,_)in enumerate(script)if op==2]
    assert any(op==1 and len(payload)>64 for op,_,payload in script[drains[0]+1:drains[1]]),'Missing mid-packet scheduling stimulus'
    reference_index=0;deferred_close=None
    for op,fields,payload in script:
        if op==0:await bench.opening(fields[0])
        elif op==1:await bench.packet(fields[0],fields[1],payload,fields[3])
        elif op==2:
            user,stream,app,count=fields;reference=references['cases'][reference_index];reference_index+=1
            assert(user,stream,app,count)==(reference['connection'],reference['stream'],reference['application'],len(reference['token_ids']))
            assert payload==reference['token_ids'];await bench.drain(user,stream,app,payload)
            if reference_index==2 and deferred_close is not None:
                await bench.directory(3,*deferred_close);deferred_close=None
        elif op==3:
            if reference_index==1 and tuple(fields)==(0,1):deferred_close=fields
            else:await bench.directory(3,*fields)
        else:
            bench.set(fault_client=fields[0],fault_target=fields[1],fault_arm=1);await cycles(d);bench.set(fault_arm=0)
    while not(value(d,'idle')and value(d,'fabric_idle')):await cycles(d)
    assert image[:layout[6]]==initial[:layout[6]]
    assert image[layout[21]:layout[23]+layout[24]]==initial[layout[21]:layout[23]+layout[24]]
    assert(bench.packets,bench.headers,bench.messages,bench.ids,bench.aborts,bench.rejected,bench.opens,bench.faults)==(38+getattr(bench,'extra_packets',0),21,16,2828,4,3,7,2)
    assert bench.response_chunks==reverse['response_chunks']==2828 and bench.response_bytes==reverse['response_bytes']
    assert bench.response_rejections==4 and bench.response_faults==1
    assert bench.early_gpu_admissions and bench.waited_for_prefill and bench.response_stalls and bench.response_held_cycles
    assert bench.mid_packet_gpu_admissions and bench.continued_rx_beats and bench.owned_schedule_cycles
    result=bench.statistics();result.update(phase='passed',response_chunks=bench.response_chunks,response_bytes=bench.response_bytes,
        response_rejections=bench.response_rejections,response_memory_faults=bench.response_faults,
        response_stall_cycles=bench.response_stalls,return_bow_stall_cycles=bench.return_bow_stalls,response_held_result_cycles=bench.response_held_cycles,
        return_directory_lease_cycles=bench.return_lease_cycles,early_gpu_admissions=bench.early_gpu_admissions,
        return_waited_for_prefill_cycles=bench.waited_for_prefill,reverse_memory_commands=bench.reverse_memory_commands,
        mid_packet_gpu_admissions=bench.mid_packet_gpu_admissions,continued_rx_beats=bench.continued_rx_beats,
        registered_schedule_owned_cycles=bench.owned_schedule_cycles,
        full_model_bytes=len(image),model_and_policy_immutable=True,shared_actual_rpc_directory=True,actual_dma_ids_returned=True,
        response_transport_framing_verified=False,complete_http2_transport_verified=False,whole_rpc_gpu_image_lease_verified=False,
        physical_adapters_verified=False,full_system_complete=False)
    if extra_result is not None:result.update(extra_result(memory,bench,initial))
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    d._log.info('PASS: joint raw ingress and actual DMA token return: %s',result)


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def raw_requests_and_actual_dma_token_returns(d):
    await run_bidirectional(d)
