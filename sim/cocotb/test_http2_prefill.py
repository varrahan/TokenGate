"""Raw HTTP/2/gRPC public-port acceptance against native tiktoken fixtures.

The real Parser, BoW, complete BPE, admission and shared cache/fabric run in
RTL. Python owns packet/control stimulus, the AXI memory BFM and scoreboards.
This is forward-path evidence; full transport and reverse acceptance remain.
"""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_tokenizer_mmio import cycles
from test_tokenizer_mmio_system import Memory


def value(d, name):
    return int(getattr(d, name).value)


def commands(path):
    words=iter(map(int,path.read_text().split()))
    while (op:=next(words,None)) is not None:
        count={0:1,1:4,2:4,3:2,4:2}[op]
        fields=[next(words)for _ in range(count)]
        payload=[next(words)for _ in range(fields[2]if op==1 else fields[3]if op==2 else 0)]
        yield op,fields,payload


class Bench:
    def __init__(self,d,layout,memory):
        self.d=d;self.layout=layout;self.memory=memory;self.rng=random.Random(20261120)
        self.bindings={};self.handles={};self.draining=False;self.expected=None;self.received=[]
        self.saw_last=False;self.held_dma=None;self.last_tag=None;self.phase='initialization'
        self.packets=self.headers=self.rejected=self.messages=self.ids=self.aborts=self.opens=self.faults=self.stalls=self.clocks=0

    def set(self,**signals):
        for name,data in signals.items():getattr(self.d,name).value=data

    def configure(self):
        names=('cfg_token_class_base','cfg_token_hash_base','cfg_token_node_base','cfg_token_edge_base',
               'cfg_token_node_count','cfg_token_edge_count','cfg_token_work_floor','cfg_token_scalar_base',
               'cfg_token_scalar_bytes','cfg_token_merge_base','cfg_token_merge_bytes','cfg_token_commit_base',
               'cfg_token_commit_bytes','cfg_stream_base','cfg_stream_bytes','queue_cfg_base','queue_cfg_bytes',
               'cfg_payload_base','cfg_payload_slot_bytes','cfg_context_base','cfg_context_bytes','cfg_route_base',
               'cfg_route_bytes','cfg_route_strings_base','cfg_route_strings_bytes','cfg_routes','cfg_model_epoch','cfg_schema_epoch')
        self.set(**dict(zip(names,self.layout[:28])))
        self.set(cfg_payload_bytes=3*self.layout[18],cfg_work_floor=self.layout[6])

    def poison(self):
        self.set(cfg_context_base=0x7fffff,cfg_context_bytes=0,cfg_payload_base=0x7fffff,
                 cfg_payload_bytes=0,cfg_payload_slot_bytes=0,cfg_route_base=0x7fffff,cfg_route_bytes=0,
                 cfg_route_strings_base=0x7fffff,cfg_route_strings_bytes=0,cfg_routes=0,
                 cfg_model_epoch=0xffffffff,cfg_schema_epoch=0xffffffff,cfg_work_floor=0x7fffff)

    async def send(self,valid,ready):
        d=self.d;await FallingEdge(d.clk);getattr(d,valid).value=1
        while True:
            await RisingEdge(d.clk)
            if value(d,ready):break
        await FallingEdge(d.clk);getattr(d,valid).value=0

    async def wait(self,name):
        while not value(self.d,name):await FallingEdge(self.d.clk)

    async def ack(self,valid,ready,hold=3):
        await self.wait(valid)
        for _ in range(hold):
            await cycles(self.d);assert value(self.d,valid),(self.phase,valid,'withdrawn')
        getattr(self.d,ready).value=1;await cycles(self.d);getattr(self.d,ready).value=0

    async def ready_driver(self):
        while True:
            await FallingEdge(self.d.clk)
            active=not value(self.d,'rst')
            self.set(header_ready=active and self.rng.randrange(4)!=0,
                     control_event_ready=active and self.rng.randrange(4)!=0,
                     m_axis_tokens_tready=active and self.draining and self.rng.randrange(4)!=0)

    def permitted_write(self,client,address,size):
        a=self.layout
        def inside(base,capacity):return base<=address and address+size<=base+capacity
        if client==0:return inside(a[13],a[14])and(address-a[13])%128+size<=64
        if client==1:return inside(a[17],3*a[18])
        if client==2:return inside(a[15],a[16])
        if client in(6,11,12):
            index={6:7,11:9,12:11}[client];return inside(a[index],a[index+1])
        if client==13:return inside(a[19],a[20])and(address-a[19])%256+size<=160
        if client in(14,15,16):return any(inside(a[i],a[i+1])for i in range(28,46,2))
        if client==19:return(inside(a[19],a[20])and 160<=(address-a[19])%256 and(address-a[19])%256+size<=168)or(
            inside(a[13],a[14])and 64<=(address-a[13])%128 and(address-a[13])%128+size<=128)
        return False

    async def observe(self):
        d=self.d
        dma_names=('m_axis_tokens_tdata','m_axis_tokens_tkeep','m_axis_tokens_tlast','m_axis_tokens_tuser',
                   'dma_connection','dma_stream','dma_generation','dma_ordinal','dma_packet_tag')
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            self.clocks+=1
            writes=value(d,'mem_valid')&value(d,'mem_ready')&value(d,'mem_write')
            if writes:
                addresses=value(d,'mem_addr');sizes=value(d,'mem_bytes')
                for client in range(20):
                    if writes>>client&1:
                        address=addresses>>(23*client)&0x7fffff;size=sizes>>(4*client)&15
                        assert 1<=size<=9 and address>=self.layout[6]and self.permitted_write(client,address,size),(
                            'memory ownership',client,hex(address),size)
            if value(d,'header_valid')and value(d,'header_ready'):
                self.headers+=1;status=value(d,'header_status');user=value(d,'header_user');stream=value(d,'header_stream')
                if status==0:
                    generation=value(d,'header_generation');assert generation and user<3 and stream<128
                    assert(value(d,'header_model_epoch'),value(d,'header_schema_epoch'))==(23,9)
                    if value(d,'header_trailers'):assert self.bindings[user,stream]==generation
                    self.bindings[user,stream]=generation;self.handles[user,stream]=value(d,'header_address')
                else:
                    self.rejected+=1
                    assert status==3 or(value(d,'fault_client')==19 and status==5 and
                        value(d,'header_memory_status')==0x75 and value(d,'header_cleanup_status')==0),(
                            'header status',status,value(d,'header_detail'),value(d,'header_memory_status'),
                            value(d,'header_cleanup_status'),self.phase)
            assert not(value(d,'rpc_error_valid')and value(d,'rpc_error_ready')),('unexpected RPC error',value(d,'rpc_error_status'))
            valid=value(d,'m_axis_tokens_tvalid')
            snapshot=tuple(value(d,name)for name in dma_names)if valid else None
            if self.held_dma is not None:assert snapshot==self.held_dma,'DMA changed while stalled'
            ready=value(d,'m_axis_tokens_tready');self.held_dma=snapshot if valid and not ready else None
            if self.held_dma is not None:self.stalls+=1
            if valid and ready:
                assert self.draining and not self.saw_last and self.expected is not None
                data,keep,last,app,user,stream,generation,ordinal,tag=snapshot
                eu,es,ea,expected=self.expected
                assert(user,stream,app,generation,ordinal,tag)==(eu,es,ea,self.bindings[eu,es],0,self.last_tag),('DMA identity',snapshot[3:])
                for lane in range(16):
                    enables=keep>>(4*lane)&15;token=data>>(32*lane)&0xffffffff
                    if enables==15:
                        assert len(self.received)<len(expected)and token==expected[len(self.received)],(
                            'token',len(self.received),token,expected[len(self.received):len(self.received)+1])
                        self.received.append(token);self.ids+=1
                    else:assert enables==0 and token==0,'Partial token or nonzero padding'
                if last:assert self.received==expected;self.saw_last=True
            if self.clocks%100000==0:
                progress=self.statistics();Path('progress.json').write_text(json.dumps(progress,indent=2)+'\n')
                d._log.info('Progress: %s; %d packets/%d messages/%d IDs; AXI %d reads/%d writes',
                            self.phase,self.packets,self.messages,self.ids,self.memory.reads,self.memory.writes)

    def statistics(self):
        return dict(phase=self.phase,packets=self.packets,headers=self.headers,rejected=self.rejected,
                    messages=self.messages,token_ids=self.ids,packet_aborts=self.aborts,connection_opens=self.opens,
                    memory_faults=self.faults,dma_stall_cycles=self.stalls,clock_cycles=self.clocks,
                    axi_line_refills=self.memory.reads,axi_writes=self.memory.writes)

    async def directory(self,op,user=0,stream=0):
        self.configure();self.set(control_op=op,control_user=user,control_stream=stream,control_maintenance=op==4,
            control_address=self.handles[user,stream]if op==3 else 0,
            control_generation=self.bindings[user,stream]if op==3 else 0)
        await self.send('control_valid','control_ready');await self.wait('control_result_valid')
        assert value(self.d,'control_status')==0,('directory',op,value(self.d,'control_status'))
        await self.ack('control_result_valid','control_result_ready')

    async def opening(self,user):
        self.phase=f'OPEN connection {user}';self.configure();offset=28+6*user;a=self.layout
        self.set(maintenance_grant=1,command_op=0,command_user=user,command_server_role=1,
                 command_allow_push=0,command_max_frame_bytes=16384,command_buffer_base=a[offset],
                 command_buffer_bytes=a[offset+1],command_table_base=a[offset+2],command_table_bytes=a[offset+3],
                 command_scratch_base=a[offset+4],command_scratch_bytes=a[offset+5],command_hpack_maximum=4096,
                 command_hpack_allowed=4096,command_header_list_limit=32768,command_required_maximum=4096,
                 command_required_update=0)
        await self.send('command_valid','command_ready')
        self.set(command_user=0xffff,command_buffer_base=0x7fffff,command_buffer_bytes=0,
                 command_scratch_base=0x7fffff,command_scratch_bytes=0,maintenance_grant=0)
        await self.wait('rsp_valid')
        assert(value(self.d,'rsp_is_command'),value(self.d,'rsp_status'),value(self.d,'rsp_user'),
               value(self.d,'admission_recovery_required'))==(1,0,user,0)
        await self.ack('rsp_valid','rsp_ready',4);self.set(maintenance_grant=1);self.opens+=1

    async def packet(self,user,tag,raw,commit):
        self.phase=f'packet {self.packets} user {user}';self.configure();offset=0
        while offset<len(raw):
            data=keep=0
            for lane in range(64):
                if offset<len(raw)and(self.rng.randrange(5)!=0 or lane==63):
                    data|=raw[offset]<<(8*lane);keep|=1<<lane;offset+=1
            self.set(s_axis_rx_tdata=data,s_axis_rx_tkeep=keep,s_axis_rx_tuser=user,
                     s_axis_rx_tag=tag,s_axis_rx_tlast=offset==len(raw))
            await self.send('s_axis_rx_tvalid','s_axis_rx_tready')
            self.set(s_axis_rx_tag=0xdeadbeef);self.poison()
        await self.wait('packet_result_valid')
        assert(value(self.d,'packet_committed'),value(self.d,'packet_user'),value(self.d,'packet_tag'))==(commit,user,tag),(
            self.phase,value(self.d,'packet_status'),value(self.d,'packet_detail'))
        if not commit:
            self.aborts+=1
            assert(value(self.d,'queued_count'),value(self.d,'pending_count'),value(self.d,'m_axis_tokens_tvalid'))==(0,0,0)
        if value(self.d,'fault_client')>=0 and value(self.d,'fault_client')<20:
            assert value(self.d,'fault_injected')and not commit
            if value(self.d,'fault_client')==19:assert value(self.d,'admission_recovery_required')
            self.faults+=1;self.set(fault_client=-1)
        await self.ack('packet_result_valid','packet_result_ready',6);self.packets+=1;self.last_tag=tag

    async def drain(self,user,stream,application,expected):
        self.phase=f'drain {user}/{stream} ({len(expected)} IDs)';self.received=[];self.saw_last=False
        self.expected=(user,stream,application,expected);self.draining=True
        await self.wait('completion_valid')
        assert self.saw_last and self.received==expected
        names=('completion_status','completion_detail','completion_memory_status','completion_token_stage',
               'completion_count','completion_user','completion_stream','completion_application','completion_generation',
               'completion_ordinal','completion_packet_tag','payload_lease_active')
        observed=tuple(value(self.d,n)for n in names)
        assert observed==(0,0,0,0,len(expected),user,stream,application,self.bindings[user,stream],0,self.last_tag,1),('completion',observed)
        if self.messages==0:
            self.configure();self.set(control_op=1,control_user=user,control_stream=stream,control_valid=1)
            await cycles(self.d,3);assert not value(self.d,'control_ready')
            self.set(command_op=2,command_user=user,command_max_frame_bytes=16384,command_valid=1)
            await cycles(self.d,3);assert not value(self.d,'command_ready')
        for _ in range(20):
            await cycles(self.d)
            assert tuple(value(self.d,n)for n in names)==observed,'Completion/lease changed before ACK'
        self.set(completion_ready=1);await cycles(self.d);self.set(completion_ready=0);self.draining=False
        if self.messages==0:
            while True:
                await RisingEdge(self.d.clk)
                if value(self.d,'control_ready'):break
            await FallingEdge(self.d.clk);self.set(control_valid=0)
            await self.wait('control_result_valid')
            assert value(self.d,'control_status')==0 and value(self.d,'control_result_generation')==self.bindings[user,stream]
            await self.ack('control_result_valid','control_result_ready',0)
            while True:
                await RisingEdge(self.d.clk)
                if value(self.d,'command_ready'):break
            await FallingEdge(self.d.clk);self.set(command_valid=0)
            await self.wait('rsp_valid');assert value(self.d,'rsp_status')==0
            await self.ack('rsp_valid','rsp_ready',0)
        self.messages+=1;self.expected=None


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def raw_http2_grpc_to_full_model_token_dma(d):
    fixtures=Path(os.environ['PARSER_PREFILL_FIXTURES'])
    layout=list(map(int,(fixtures/'layout.txt').read_text().split()));assert len(layout)==46
    metadata=json.loads((fixtures/'fixture_manifest.json').read_text())
    references=json.loads((fixtures/'reference_cases.json').read_text())
    image=bytearray(b''.join(int(line,16).to_bytes(8,'little')for line in(fixtures/'memory.mem').read_text().splitlines()))
    assert len(image)==8*1024*1024 and hashlib.sha256(image).hexdigest()==metadata['loaded_image_sha256']
    assert references['encoding']=='cl100k_base'and references['method']=='encode_ordinary'
    assert references['tiktoken_version']==metadata['packages']['tiktoken']
    initial=bytes(image);memory=Memory(d,image);bench=Bench(d,layout,memory)
    d.rst.value=1;bench.configure();bench.set(m_return_tready=1)
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start())
    cocotb.start_soon(memory.run());cocotb.start_soon(bench.ready_driver());cocotb.start_soon(bench.observe())
    await cycles(d,5);d.rst.value=0
    bench.set(maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    await bench.send('queue_cfg_valid','queue_cfg_ready');await bench.wait('queue_cfg_result_valid')
    assert value(d,'queue_cfg_status')==0;await bench.ack('queue_cfg_result_valid','queue_cfg_result_ready',0)
    await bench.send('stream_cfg_valid','stream_cfg_ready');await bench.wait('stream_cfg_result_valid')
    assert value(d,'stream_cfg_status')==0;await bench.ack('stream_cfg_result_valid','stream_cfg_result_ready',0)
    await bench.directory(4)
    reference_index=0
    for op,fields,payload in commands(fixtures/'vectors.txt'):
        if op==0:await bench.opening(fields[0])
        elif op==1:await bench.packet(fields[0],fields[1],payload,fields[3])
        elif op==2:
            user,stream,app,count=fields;reference=references['cases'][reference_index];reference_index+=1
            assert(user,stream,app,count)==(reference['connection'],reference['stream'],reference['application'],len(reference['token_ids']))
            assert payload==reference['token_ids'];bytes.fromhex(reference['prompt_utf8_hex']).decode('utf-8')
            await bench.drain(user,stream,app,payload)
        elif op==3:await bench.directory(3,*fields)
        elif op==4:
            bench.set(fault_client=fields[0],fault_target=fields[1],fault_arm=1)
            await cycles(d);bench.set(fault_arm=0)
    bench.phase='final drain'
    while not(value(d,'idle')and value(d,'fabric_idle')):await cycles(d)
    assert image[:layout[6]]==initial[:layout[6]],'Complete model was modified'
    assert image[layout[21]:layout[23]+layout[24]]==initial[layout[21]:layout[23]+layout[24]],'Route policy was modified'
    assert(bench.packets,bench.headers,bench.messages,bench.ids,bench.aborts,bench.rejected,bench.opens,bench.faults)==(38,21,16,2828,4,3,7,2)
    assert bench.stalls>0 and reference_index==len(references['cases'])==metadata['messages']
    result=bench.statistics();result.update(phase='passed',full_model_bytes=len(image),model_and_policy_immutable=True,
        reference_tiktoken_version=references['tiktoken_version'],raw_http2_forward_verified=True,
        complete_http2_transport_verified=False,reverse_path_verified=False,physical_throughput_verified=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    d._log.info('PASS: cocotb raw HTTP/2/gRPC -> complete-model DMA: %d packets/%d headers/%d messages/%d exact IDs, four aborts, two memory faults, shared memory ownership and immutable model/policy',
                bench.packets,bench.headers,bench.messages,bench.ids)
