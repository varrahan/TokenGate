"""The committed journal uses actual peer-state memory and actual shared windows."""
import hashlib
import json
import os
from pathlib import Path
import random
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperframe.frame import SettingsFrame,PingFrame,WindowUpdateFrame
from test_journaled_controls import Bench as JournalBench,events,JOURNAL,SLOT
from test_http2_peer_state import PEER,RESULTS
from test_tokenizer_mmio import cycles


class Memory:
    def __init__(self,d,image,a):
        self.d=d;self.data=bytearray(image);self.a=a;self.pending=[None]*4;self.trace=[];self.count=[0]*4
        self.fail_client=-1;self.fail_at=-1;self.clock=0;self.rng=random.Random(20261202)
    async def run(self):
        d=self.d;a=self.a;held=[None]*4
        while True:
            await FallingEdge(d.clk)
            if int(d.rst.value):
                assert not any(self.pending);d.mem_ready.value=0;d.mem_rsp_valid.value=0;d.mem_rsp_data.value=0;d.mem_rsp_status.value=0;held=[None]*4;continue
            ready=valid=data=status=0
            for client,p in enumerate(self.pending):
                if p and p['delay']:p['delay']-=1
                if p and not p['delay']:valid|=1<<client;data|=p['data']<<(72*client);status|=p['entry']['status']<<(8*client)
                if p is None and self.rng.randrange(4):ready|=1<<client
            d.mem_ready.value=ready;d.mem_rsp_valid.value=valid;d.mem_rsp_data.value=data;d.mem_rsp_status.value=status
            await RisingEdge(d.clk);self.clock+=1;locked=int(d.directory_pool_lock_active.value)
            if locked:assert not(int(d.mem_valid.value)&4)
            for client in range(4):
                if valid>>client&1 and int(d.mem_rsp_ready.value)>>client&1:self.pending[client]['entry']['ack']=self.clock;self.pending[client]=None
                if int(d.mem_valid.value)>>client&1:
                    item=(int(d.mem_write.value)>>client&1,int(d.mem_addr.value)>>(23*client)&0x7fffff,
                        int(d.mem_bytes.value)>>(4*client)&15,int(d.mem_data.value)>>(72*client)&((1<<72)-1))
                    if held[client]is not None:assert held[client]==item
                    held[client]=item if not(ready>>client&1)else None
                    if ready>>client&1:
                        write,address,size,value=item;assert self.pending[client]is None and size==8 and address>=a['work_floor']and address+8<=len(self.data)
                        context=a['context_base']<=address and address+8<=a['context_base']+a['context_bytes']
                        rpc=a['stream_base']<=address and address+8<=a['stream_base']+a['stream_bytes']
                        if client==3:assert locked
                        if write:
                            if client==0:allowed=context and 216<=(address-a['context_base'])%256<=248 or JOURNAL<=address and address+8<=JOURNAL+3*SLOT
                            elif client==1:allowed=PEER<=address and address+8<=PEER+192
                            elif client==2:allowed=rpc and(address-a['stream_base'])%128<=56
                            else:allowed=context and 168<=(address-a['context_base'])%256<=208 or a['window_base']<=address and address+8<=a['window_base']+a['window_bytes']
                            assert allowed,(client,hex(address));self.data[address:address+8]=(value&((1<<64)-1)).to_bytes(8,'little')
                        entry=dict(client=client,write=write,address=address,status=0x75 if client==self.fail_client and self.count[client]==self.fail_at else 0,ack=None)
                        self.trace.append(entry);self.count[client]+=1;self.pending[client]=dict(entry=entry,data=int.from_bytes(self.data[address:address+8],'little'),delay=self.rng.randrange(2,10))
                else:assert held[client]is None


class Bench(JournalBench):
    async def start(self,formatting=False):
        self.set(cfg_peer_base=PEER,cfg_peer_bytes=192);await super().start(formatting);self.set(cfg_peer_base=0x7fffff,cfg_peer_bytes=0)
    async def peer(self,op,payload=0,status=0):
        a=self.a;self.set(peer_cmd_req_op=op,peer_cmd_req_user=0,peer_cmd_req_authority=1,peer_cmd_req_maintenance=int(op==0),peer_cmd_req_payload=payload,
            cfg_context_base=a['context_base'],cfg_context_bytes=a['context_bytes'],cfg_peer_base=PEER,cfg_peer_bytes=192,cfg_work_floor=a['work_floor'])
        await self.send('peer_cmd_req_valid','peer_cmd_req_ready')
        self.set(peer_cmd_req_op=15,peer_cmd_req_user=65535,peer_cmd_req_authority=0,peer_cmd_req_maintenance=0,peer_cmd_req_payload=0,
            cfg_context_base=0x7fffff,cfg_context_bytes=0,cfg_peer_base=0x7fffff,cfg_peer_bytes=0,cfg_work_floor=0x7fffff)
        await self.wait('peer_cmd_rsp_valid');r={n:int(getattr(self.d,'peer_cmd_'+n).value)for n in RESULTS};assert r['rsp_status']==status,r
        for _ in range(7):await cycles(self.d);assert int(self.d.peer_cmd_rsp_valid.value)and r=={n:int(getattr(self.d,'peer_cmd_'+n).value)for n in RESULTS}
        await self.retire('peer_cmd_rsp_ready');return r


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def committed_peer_settings_and_acks_use_actual_rtl(d):
    folder=Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES']);ref=json.loads((folder/'cases.json').read_text());image=(folder/'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest()==ref['original_image_sha256']
    m=Memory(d,image,ref['layout']);b=Bench(d,m,ref['layout']);b.set(rst=1,start_valid=0,s_valid=0,finish_valid=0,result_ready=0,
        peer_cmd_req_valid=0,peer_cmd_rsp_ready=0,cancel_ready=0,cancel_result_valid=0,classify_ready=0,classify_result_valid=0)
    assert not hasattr(d,'notice_ready')and not hasattr(d,'notice_result_valid'),'Notice fixture was not removed'
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(m.run());cocotb.start_soon(b.tx_driver())
    await b.fresh();r=await b.peer(1);assert r['rsp_header_table_size']==4096 and r['rsp_settings_pending']==1
    assert b.tx[-1]==SettingsFrame(0).serialize(),'FORMAT result escaped before actual server SETTINGS'
    initial_ack=SettingsFrame(0);initial_ack.flags.add('ACK');await b.packet(events(initial_ack))
    settings=SettingsFrame(0);settings.settings={1:8192,2:0,3:0,6:2048,4:1000,5:32768,65000:42};records=events(settings)
    before=len(b.tx);await b.packet(records[:3]);assert len(b.tx)==before
    r=await b.peer(1);assert r['rsp_header_table_size']==4096 and r['rsp_enable_push']==1
    result=await b.packet(records[3:]);assert result['control_window_updates']==2 and result['control_ack_frames']==1
    ack=SettingsFrame(0);ack.flags.add('ACK');assert b.tx[-1]==ack.serialize()
    r=await b.peer(1);assert(r['rsp_header_table_size'],r['rsp_enable_push'],r['rsp_max_concurrent_streams'],r['rsp_max_header_list_size'])==(8192,0,0,2048)
    assert(await b.window(6,1))['rsp_stream_window']==1000
    settings.settings={1:17};await b.packet(events(settings),False);assert(await b.peer(1))['rsp_header_table_size']==8192
    r=await b.peer(2);assert r['rsp_wire_retired']and r['rsp_settings_pending']==1 and b.tx[-1]==SettingsFrame(0).serialize()
    r=await b.peer(2);assert r['rsp_settings_pending']==2
    before=len(b.tx);await b.packet(events(ack));r=await b.peer(1);assert r['rsp_settings_pending']==1 and r['rsp_settings_acks']==2
    await b.packet(events(ack));await b.packet(events(ack));r=await b.peer(1);assert r['rsp_settings_pending']==0 and r['rsp_settings_acks']==3 and len(b.tx)==before
    ping=PingFrame(0);ping.opaque_data=b'peerdata';payload=int.from_bytes(ping.opaque_data,'big');hi,lo=struct.unpack('>II',ping.opaque_data)
    await b.peer(3,payload);assert b.tx[-1]==ping.serialize();before=len(b.tx);await b.peer(3,payload^1,status=8);assert len(b.tx)==before
    ping.flags.add('ACK');await b.packet(events(ping,5,hi,lo^1));assert(await b.peer(1))['rsp_ping_pending']
    await b.packet(events(ping,5,hi,lo));r=await b.peer(1);assert not r['rsp_ping_pending']and r['rsp_ping_acks']==1 and len(b.tx)==before
    # Real notices remain possible while the real directory's cached LOAD is held.
    await b.lease(1);settings.settings={1:512};await b.packet(events(settings));assert int(d.lease_rsp_valid.value)
    await b.retire('lease_rsp_ready');assert(await b.peer(1))['rsp_header_table_size']==512
    # Invalid ENABLE_PUSH preserves the real peer value, suppresses ACK and
    # propagates the protocol error through the actual executor/journal result.
    settings.settings={2:2};before=len(b.tx);result=await b.packet(events(settings),status=8)
    assert result['control_status']==9 and result['control_http2_error']==1 and len(b.tx)==before
    assert int(d.recovery_required.value);await b.start(True);await b.result()
    # Every peer FORMAT and notice-memory phase is faulted through the real join.
    faults=0
    for phase in range(28):
        await b.fresh();m.fail_client=1;m.fail_at=m.count[1]+phase;before=len(b.tx)
        await b.start(True);result=await b.result(10)
        assert result['result_memory_status']==0x75 and int(d.peer_format_status.value)==5 and len(b.tx)==before+int(phase>=19)and int(d.recovery_required.value)
        m.fail_client=-1;await b.start(True);await b.result();assert not int(d.recovery_required.value);faults+=1
    settings.settings={1:73}
    for phase in range(18):
        await b.fresh();m.fail_client=1;m.fail_at=m.count[1]+phase;before=len(b.tx)
        result=await b.packet(events(settings),status=8)
        assert result['control_status']==9 and result['result_memory_status']==0x75 and len(b.tx)==before and int(d.recovery_required.value)
        m.fail_client=-1;await b.start(True);await b.result();assert not int(d.recovery_required.value);faults+=1
    assert not any(m.pending)and all(e['ack']is not None for e in m.trace)
    assert m.data[:b.a['work_floor']]==image[:b.a['work_floor']]
    accepted=dict(phase='passed',actual_notice_controller_verified=True,notice_fixture_removed=True,
        journal_format_initializes_peer_state=True,server_settings_before_format_result=True,all_non_window_settings_persisted=True,
        settings_and_actual_window_updates_before_ack=True,partial_and_aborted_settings_do_not_apply=True,
        actual_local_settings_and_ping_wire_verified=True,ordered_settings_ack_tracking=True,matching_ping_ack_only=True,
        no_ack_of_ack=True,invalid_enable_push_propagates_protocol_error=True,held_cached_load_survives=True,
        native_frames=len(b.tx),held_tx_cycles=b.tx_stalls,injected_peer_memory_faults=faults,
        uncertain_peer_write_suppresses_ack=True,fenced_format_recovers_both=True,actual_memory_clients=4,
        complete_model_prefix_immutable=True,raw_parser_integrated=False,cancellation_and_classification_supplied_externally=True,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
