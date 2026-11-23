"""Extend the native padding regression with passive real commit/wire witnesses."""
from pathlib import Path


BENCH = r'''
class Bench(BaseBench):
    def __init__(self,*args):
        super().__init__(*args)
        self.receive_updates=[];self.receive_active={};self.receive_intent_addresses={0x7e5010:0}
        self.receive_available_addresses={0x7e5008:0};self.receive_binding=None
        self.receive_held_cycles=0;self.receive_debits=[];self.receive_initializations=[]
        self.receive_close_witness=False;self.receive_packet_fences=0

    async def receive_witness(self):
        from cocotb.triggers import FallingEdge,RisingEdge,Timer
        d=self.d;c=d.dut.core;pending=None;clock=0;authorized=None;last_request=None
        initialization_ack={};held_once=False
        while True:
            await FallingEdge(d.clk)
            # Settle after the ordinary ready driver, before the next edge.
            await Timer(1,unit='ns')
            if not value(d,'rst')and not held_once and value(d,'m_axis_tx_tvalid'):
                raw=value(d,'m_axis_tx_tdata').to_bytes(64,'little')
                if raw[3]==8 and int.from_bytes(raw[5:9],'big')==1:
                    held_once=True;self.ready_wire=False;d.m_axis_tx_tready.value=0
                    offered=tuple(value(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
                    address=next(a for a,s in self.receive_available_addresses.items()if s==1)
                    old=bytes(self.memory.data[address:address+8]);native=self.client.outbound_flow_control_window
                    for _ in range(17):
                        await RisingEdge(d.clk)
                        assert value(d,'m_axis_tx_tvalid')and not value(d,'m_axis_tx_tready')
                        assert offered==tuple(value(d,'m_axis_tx_'+n)for n in('tdata','tkeep','tlast','tuser'))
                        assert self.memory.data[address:address+8]==old
                        assert self.client.outbound_flow_control_window==native
                        assert not value(d,'packet_result_valid'),'Packet escaped while its credit wire promise was held'
                        self.receive_held_cycles+=1
                    self.ready_wire=True
            await RisingEdge(d.clk);clock+=1
            if value(d,'rst'):continue
            if value(c,'rx_request_valid')and value(c,'rx_request_ready'):
                last_request={n:value(c,'rx_request_'+n)for n in('op','user','stream','generation','address','amount')}
                if last_request['op']==1:
                    assert last_request['generation'] and last_request['stream']==1
                    base=0x7e6000+(last_request['address']-self.layout[13])//4
                    self.receive_intent_addresses[base+16]=1;self.receive_available_addresses[base+8]=1
                    self.receive_binding=(last_request['address'],last_request['generation'],base)
                elif last_request['op']==9:
                    assert value(c,'service_control_rsp_valid')and value(c,'service_control_rsp_status')==0
                    assert value(c,'service_control_rsp_op')==3 and not value(c,'service_control_rsp_ready')
                    assert tuple(last_request[n]for n in('user','stream','generation','address'))==tuple(
                        value(c,'service_control_rsp_'+n)for n in('user','stream','generation','address'))
                    assert self.memory.data[last_request['address']:last_request['address']+8]==bytes(8)
                    self.receive_close_witness=True
            # Observe the extra physical Parser client, never a fixture ledger.
            if value(d,'mem_rsp_valid')>>26&value(d,'mem_rsp_ready')>>26&1:
                assert pending is not None
                write,address,data=pending;assert value(d,'mem_rsp_status')>>(26*8)&255==0
                if write:
                    if address in self.receive_intent_addresses:
                        scope=self.receive_intent_addresses[address];intent=data>>32&0xffffffff
                        if intent:
                            assert scope not in self.receive_active
                            self.receive_active[scope]=dict(stream=scope,amount=intent,intent_ack_clock=clock)
                        elif scope in self.receive_active:
                            entry=self.receive_active[scope]
                            assert entry.get('wire_clock',clock)>=entry['intent_ack_clock'] and clock>entry['wire_clock']
                            entry['clear_ack_clock']=clock
                    if address in self.receive_available_addresses:
                        scope=self.receive_available_addresses[address]
                        if scope in self.receive_active:
                            entry=self.receive_active[scope]
                            assert clock>entry['wire_clock'];entry['available_ack_clock']=clock
                pending=None
            if value(d,'mem_valid')>>26&value(d,'mem_ready')>>26&1:
                assert pending is None
                pending=(value(d,'mem_write')>>26&1,value(d,'mem_addr')>>(26*23)&0x7fffff,
                    value(d,'mem_data')>>(26*72)&((1<<64)-1))
            if value(c,'rx_result_valid')and value(c,'rx_result_ready'):
                assert last_request is not None and value(c,'rx_result_status')==0
                op=last_request['op']
                if op==1:
                    initialization_ack[last_request['generation']]=clock
                    self.receive_initializations.append(dict(last_request,ack_clock=clock))
                elif op==2:
                    assert value(c,'rx_result_debit_authorized')
                    authorized=dict(last_request,ack_clock=clock);self.receive_debits.append(authorized)
                elif op==4 and last_request['stream']in self.receive_active:
                    entry=self.receive_active.pop(last_request['stream'])
                    assert entry['intent_ack_clock']<entry['wire_clock']<entry['available_ack_clock']<=entry['clear_ack_clock']<clock
                    entry['result_ack_clock']=clock;self.receive_updates.append(entry)
            if value(d,'header_valid')and value(d,'header_ready')and value(d,'header_status')==0:
                generation=value(d,'header_generation')
                assert generation in initialization_ack and initialization_ack[generation]<clock
                assert (value(d,'header_address'),generation)==self.receive_binding[:2]
            f=c.forward
            if value(f,'p_s_valid')and value(f,'p_s_ready')and value(f,'p_s_kind')==0:
                assert authorized is not None and clock>authorized['ack_clock']
                assert value(f,'p_s_stream')==authorized['stream']
            if value(d,'m_axis_tx_tvalid')and value(d,'m_axis_tx_tready'):
                raw=value(d,'m_axis_tx_tdata').to_bytes(64,'little')
                if raw[3]==8:
                    scope=int.from_bytes(raw[5:9],'big');amount=int.from_bytes(raw[9:13],'big')
                    entry=self.receive_active[scope]
                    assert amount==entry['amount'] and clock>entry['intent_ack_clock']
                    entry['wire_clock']=clock
            if value(d,'packet_result_valid')and value(d,'packet_result_ready'):
                assert not self.receive_active,'Public packet result preceded durable receive-credit results'
                self.receive_packet_fences+=1

    async def close_and_verify_receive(self,application_bytes):
        assert self.receive_held_cycles==17 and len(self.receive_debits)==257
        assert sum(x['amount']for x in self.receive_debits)==65535+application_bytes
        address,generation,base=self.receive_binding
        available=int.from_bytes(self.memory.data[0x7e5008:0x7e500c],'little')
        assert available==self.client.outbound_flow_control_window==65535-application_bytes
        assert int.from_bytes(self.memory.data[base+8:base+12],'little')==65535-application_bytes
        await self.directory(3,0,1)
        assert self.receive_close_witness and self.memory.data[address:address+8]==bytes(8)
        assert int.from_bytes(self.memory.data[base+8:base+16],'little')>>63==1
        assert int.from_bytes(self.memory.data[base+4:base+8],'little')==generation
        assert int.from_bytes(self.memory.data[0x7e5008:0x7e500c],'little')==self.client.outbound_flow_control_window==65535
        assert not self.receive_active and not any(self.pending)
        assert len(self.receive_updates)==513
        assert sum(x['amount']for x in self.receive_updates if x['stream']==1)==65535
        assert sum(x['amount']for x in self.receive_updates if x['stream']==0)==65535+application_bytes
'''


def generate(root: Path, target: Path):
    text=(root/'sim/cocotb/test_raw_receive_flow.py').read_text()
    text=text.replace('from test_raw_grpc_enveloped import Bench','from test_raw_grpc_enveloped import Bench as BaseBench')
    assert text.count('@cocotb.test(')==1
    text=text.replace('@cocotb.test(',BENCH+'\n\n@cocotb.test(',1)
    marker='for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated()):'
    assert text.count(marker)==1
    text=text.replace(marker,'for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), b.receive_witness()):')
    marker="    accepted = dict(phase='passed', native_padding_payload_bytes=payload_bytes,"
    assert text.count(marker)==1
    text=text.replace(marker,"    await b.close_and_verify_receive(5+len(body))\n"+marker)
    marker='        receive_flow_control_negative_matrix_verified=False, full_system_complete=False)'
    assert text.count(marker)==1
    text=text.replace(marker,'''        receive_flow_control_negative_matrix_verified=False,
        actual_header_initialization_before_public_binding=True,
        actual_both_budget_debit_before_application_dispatch=True,
        actual_committed_frame_padding_release=True,
        actual_intent_wire_available_clear_result_order_verified=True,
        held_actual_wire_cycles=b.receive_held_cycles,
        actual_successful_close_inactive_binding_and_connection_refund_verified=True,
        application_bytes_not_refunded_until_actual_close=True,
        actual_receive_debits=b.receive_debits,actual_receive_updates=b.receive_updates,
        parser_memory_clients=len(d.p_mem_valid),tokenizer_memory_clients=9,
        application_ring_reclamation_verified=False,retained_memory_reset_verified=False,
        full_system_complete=False)''')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    generate(root,root/'build/experiments/receive-integration/sim/test_raw_receive_flow.py')
