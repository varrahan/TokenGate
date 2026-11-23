"""Decode emitted HyperBus CA/data words independently of engine request ports."""
import math
from cocotb.triggers import FallingEdge,RisingEdge


def value(d,name):return int(getattr(d,name).value)


class HyperRAMWordModel:
    def __init__(self,d,image,clock_hz=200000000):
        self.d=d;self.memory=bytearray(image);self.clock_hz=clock_hz
        self.registers={0:0x0c81,2:1,0x1000:0x8f2f,0x1002:0}
        self.refresh_next=False;self.rx_delay_next=0;self.drop_after_next=None;self.fault_after_write_next=None
        self.fault_after_read_next=None;self.transactions=[];self.current=None;self.clock=0;self.previous_end=None

    async def run(self):
        d=self.d
        while True:
            await FallingEdge(d.clk)
            t=self.current
            d.phy_latency_extra.value=int(t['extra'])if t else 0
            valid=False;word=0;fault=False
            if t is not None:
                fault=(t['fault_write']is not None and len(t['write_words'])>=t['fault_write'])or(
                    t['fault_read']is not None and len(t['read_words'])>=t['fault_read'])
                if 'data_clock'in t and not t['write']and t['clocks']>=t['data_clock']+t['rx_delay'] and value(d,'phy_rx_enable'):
                    index=len(t['read_words'])
                    if t['drop_after']is None or index<t['drop_after']:
                        valid=True
                        if t['register']:word=self.registers[t['address']]
                        else:
                            address=(t['address']+2*index)%len(self.memory)
                            word=self.memory[address]<<8|self.memory[(address+1)%len(self.memory)]
            d.phy_rx_valid.value=int(valid);d.phy_rx_word.value=word;d.phy_fault.value=int(fault)
            await RisingEdge(d.clk);self.clock+=1
            if value(d,'rst'):
                self.current=None;self.previous_end=None;continue
            if value(d,'phy_cs_n'):
                assert not value(d,'phy_clock_enable')and not value(d,'phy_dq_oe')and not value(d,'phy_rwds_oe')
                if self.current is not None:
                    t=self.current;assert t['cs_cycles']<=self.clock_hz//1000000*9//10
                    t['end_clock']=self.clock;self.previous_end=self.clock;self.transactions.append(t);self.current=None
                continue
            if self.current is None:
                if self.previous_end is not None:assert self.clock-self.previous_end>=math.ceil(self.clock_hz*40e-9)
                fixed=bool(self.registers[0x1000]&8)
                self.current=dict(ca_words=[],clocks=0,cs_cycles=0,start_clock=self.clock,
                    extra=fixed or self.refresh_next,rx_delay=self.rx_delay_next,drop_after=self.drop_after_next,
                    fault_write=self.fault_after_write_next,fault_read=self.fault_after_read_next,
                    write_words=[],write_masks=[],read_words=[])
                self.refresh_next=False;self.rx_delay_next=0;self.drop_after_next=None
                self.fault_after_write_next=None;self.fault_after_read_next=None
            t=self.current;t['cs_cycles']+=1
            if not value(d,'phy_clock_enable'):
                assert not value(d,'phy_dq_oe')and not value(d,'phy_rwds_oe')
                continue
            c=t['clocks']
            if len(t['ca_words'])<3:
                assert value(d,'phy_dq_oe')and not value(d,'phy_rwds_oe')
                t['ca_words'].append(value(d,'phy_tx_word'))
                if len(t['ca_words'])==3:
                    ca=int.from_bytes(b''.join(w.to_bytes(2,'big')for w in t['ca_words']),'big')
                    assert ca>>45&1 and (ca>>35&1023)==0 and (ca>>3&8191)==0
                    t.update(ca_hex=f'{ca:012x}',write=not bool(ca>>47&1),register=bool(ca>>46&1),
                        address=(((ca>>16&((1<<29)-1))<<3)|(ca&7))*2)
                    assert t['address']<len(self.memory)
                    latency={0:5,1:6,2:7,14:3,15:4}[self.registers[0x1000]>>4&15]
                    t['data_clock']=3 if t['write']and t['register']else 2+latency*(2 if t['extra']else 1)
            elif t['write']:
                if c<t['data_clock']:
                    assert not value(d,'phy_dq_oe')
                    assert value(d,'phy_rwds_oe')==int(c==t['data_clock']-1)
                    if value(d,'phy_rwds_oe'):assert value(d,'phy_tx_mask')==0
                else:
                    assert value(d,'phy_dq_oe')
                    word=value(d,'phy_tx_word');mask=value(d,'phy_tx_mask');index=len(t['write_words'])
                    t['write_words'].append(word);t['write_masks'].append(mask)
                    if t['register']:
                        assert index==0 and not value(d,'phy_rwds_oe')
                        assert t['address']in(0x1000,0x1002);self.registers[t['address']]=word
                    else:
                        assert value(d,'phy_rwds_oe')
                        address=(t['address']+2*index)%len(self.memory)
                        if not(mask&2):self.memory[address]=word>>8
                        if not(mask&1):self.memory[(address+1)%len(self.memory)]=word&255
            else:
                assert not value(d,'phy_dq_oe')and not value(d,'phy_rwds_oe')
                assert value(d,'phy_rx_enable')==int(c>=t['data_clock'])
                if valid:t['read_words'].append(word)
            t['clocks']+=1
