"""Manufacturer-protocol word model, full-image byte scoreboard and faults."""
import hashlib
import json
import os
import math
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperram_word_model import HyperRAMWordModel,value


async def cycles(d,n=1):
    for _ in range(n):await RisingEdge(d.clk)
    await FallingEdge(d.clk)


class Host:
    def __init__(self,d):self.d=d;self.fixed=1;self.latency=7;self.calls=0
    async def command(self,address,size,*,write=False,register=False,data=0,strobes=0,error=0,detail=0,hold=17):
        d=self.d;await FallingEdge(d.clk)
        d.enable.value=1;d.cfg_latency.value=self.latency;d.cfg_fixed_latency.value=self.fixed
        d.cmd_address.value=address;d.cmd_bytes.value=size;d.cmd_write.value=int(write);d.cmd_register.value=int(register)
        d.cmd_data.value=data;d.cmd_strobes.value=strobes;d.cmd_valid.value=1;d.rsp_ready.value=0
        for _ in range(1000):
            await RisingEdge(d.clk)
            if value(d,'cmd_ready'):break
        else:raise AssertionError('Request was not accepted')
        await FallingEdge(d.clk);d.cmd_valid.value=0
        d.enable.value=0;d.cfg_latency.value=0;d.cfg_fixed_latency.value=1-self.fixed
        d.cmd_address.value=0x7fffff;d.cmd_bytes.value=127;d.cmd_write.value=0;d.cmd_register.value=1
        d.cmd_data.value=(1<<512)-1;d.cmd_strobes.value=0
        for _ in range(1000):
            if value(d,'rsp_valid'):break
            await cycles(d)
        else:raise AssertionError('Missing bounded transaction result')
        result=tuple(value(d,n)for n in('rsp_error','rsp_detail','rsp_data'))
        assert result[:2]==(error,detail),result
        assert value(d,'phy_cs_n')and not value(d,'phy_clock_enable')and value(d,'phy_rx_flush')
        d.enable.value=1
        for _ in range(hold):
            await cycles(d);assert value(d,'rsp_valid')and not value(d,'cmd_ready')
            assert result==tuple(value(d,n)for n in('rsp_error','rsp_detail','rsp_data'))
        d.rsp_ready.value=1;await cycles(d);d.rsp_ready.value=0;self.calls+=1
        return result[2]


@cocotb.test(timeout_time=5,timeout_unit='ms')
async def hyperbus_ca_latency_masks_and_bounded_faults(d):
    image=Path(os.environ['PARSER_HYPERRAM_IMAGE']).read_bytes();expected=bytearray(image);rng=random.Random(20261125)
    assert len(image)==8388608
    clock_hz=int(os.environ.get('PARSER_HYPERRAM_CLOCK_HZ','200000000'))
    minimum=7 if clock_hz>166000000 else 6 if clock_hz>133000000 else 5 if clock_hz>104000000 else 4 if clock_hz>85000000 else 3
    variable_cr0=0x8f07|({3:14,4:15,5:0,6:1,7:2}[minimum]<<4)
    model=HyperRAMWordModel(d,image,clock_hz);host=Host(d)
    d.clk.value=0;d.rst.value=1
    for n in ('enable','cmd_valid','cmd_write','cmd_register','cmd_address','cmd_bytes','cmd_data','cmd_strobes',
        'cfg_latency','cfg_fixed_latency','rsp_ready','phy_latency_extra','phy_rx_valid','phy_rx_word','phy_fault'):
        getattr(d,n).value=0
    # Cocotb's symmetric clock needs an even number of simulator ticks.
    # Round up so the generated clock never exceeds the requested frequency.
    period_ps=2*math.ceil(1e12/clock_hz/2)
    cocotb.start_soon(Clock(d.clk,period_ps,unit='ps').start());cocotb.start_soon(model.run())
    await cycles(d,5);d.rst.value=0;await cycles(d)
    assert await host.command(0,2,register=True)==0x0c81
    assert await host.command(0x1000,2,register=True)==0x8f2f
    # Register writes have no initial latency, no RWDS drive and natural big-endian words.
    await host.command(0x1000,2,write=True,register=True,data=variable_cr0,strobes=3);host.fixed=0;host.latency=minimum
    assert model.registers[0x1000]==variable_cr0 and model.transactions[-1]['ca_hex']=='600001000000'
    valid_sizes=(2,4,8,16,32,64)
    for index in range(48):
        size=valid_sizes[index%6]
        address=(rng.randrange((len(image)-64)//2)*2)
        if index<5:address=(0,0x3fe,0xffe,len(image)-64,len(image)-size)[index]
        payload=rng.randbytes(size);strobes=rng.getrandbits(size)if index%5 else 0
        model.refresh_next=bool(index&1)
        await host.command(address,size,write=True,data=int.from_bytes(payload,'little'),strobes=strobes,hold=index%3)
        t=model.transactions[-1]
        assert t['address']==address and not t['register']and t['write']
        assert t['write_words']==[int.from_bytes(payload[i:i+2],'big')for i in range(0,size,2)]
        assert t['write_masks']==[((not(strobes>>i&1))<<1)|int(not(strobes>>(i+1)&1))for i in range(0,size,2)]
        for i,byte in enumerate(payload):
            if strobes>>i&1:expected[address+i]=byte
        model.refresh_next=not bool(index&1);model.rx_delay_next=index%4
        actual=await host.command(address,size,hold=index%4)
        assert actual.to_bytes(64,'little')[:size]==expected[address:address+size]and actual>>(size*8)==0
        assert len(model.transactions[-1]['read_words'])==size//2
    await host.command(0x1000,2,write=True,register=True,data=0x8f2f,strobes=3);host.fixed=1;host.latency=7
    model.rx_delay_next=3
    assert await host.command(0,64)==int.from_bytes(expected[:64],'little')
    before=len(model.transactions)
    bad=[(0,0,False,False,0),(1,2,False,False,0),(0,3,False,False,0),(0,65,False,False,0),
        (0x7ffffe,4,False,False,0),(0,4,False,True,0),(4,2,False,True,0),
        (0,2,True,True,3),(0x1000,2,True,True,1)]
    for address,size,write,register,strobes in bad:
        assert await host.command(address,size,write=write,register=register,strobes=strobes,error=1,detail=1)==0
    host.latency=minimum-1;await host.command(0,2,error=1,detail=1);host.latency=7
    assert len(model.transactions)==before
    model.drop_after_next=3
    assert await host.command(0,64,error=1,detail=2)==0
    timeout=model.transactions[-1];assert len(timeout['read_words'])==3 and timeout['cs_cycles']==clock_hz//1000000*9//10
    assert await host.command(0,64)==int.from_bytes(expected[:64],'little')
    model.fault_after_write_next=3;address=0x710000;payload=rng.randbytes(64)
    assert await host.command(address,64,write=True,data=int.from_bytes(payload,'little'),strobes=(1<<64)-1,error=1,detail=3)==0
    partial=model.transactions[-1];assert 3<=len(partial['write_words'])<32
    assert partial['write_words']==[int.from_bytes(payload[i:i+2],'big')for i in range(0,2*len(partial['write_words']),2)]
    expected[address:address+2*len(partial['write_words'])]=payload[:2*len(partial['write_words'])]
    assert await host.command(address,64)==int.from_bytes(expected[address:address+64],'little')
    model.fault_after_read_next=2
    assert await host.command(0,64,error=1,detail=3)==0
    assert await host.command(0,64)==int.from_bytes(expected[:64],'little')
    await cycles(d,3);assert value(d,'idle')and model.current is None and model.memory==expected
    assert all(t['ca_hex'][0]in('2','6','a','e')for t in model.transactions)
    result=dict(phase='passed',accepted_requests=host.calls,hyperbus_word_transactions=len(model.transactions),
        configured_clock_hz=clock_hz,simulated_clock_period_ps=period_ps,minimum_latency_tested=minimum,
        rejected_requests=len(bad)+1,variable_latency_transactions=sum(not t['register']and t['data_clock']==2+minimum for t in model.transactions),
        extended_latency_transactions=sum(not t['register']and t['data_clock']==2+minimum*2 for t in model.transactions),
        full_image_sha256=hashlib.sha256(image).hexdigest(),final_memory_sha256=hashlib.sha256(model.memory).hexdigest(),
        actual_timeout_cs_cycles=timeout['cs_cycles'],actual_partial_write_words=len(partial['write_words']),
        captured_requests_and_configuration_verified=True,ca_words_decoded_independently=True,
        register_zero_latency_and_big_endian_verified=True,memory_byte_masks_and_linear_bursts_verified=True,
        held_results_and_bounded_faults_verified=True,full_image_byte_scoreboard_verified=True,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,device_initialization_manager_verified=False,
        native_timing_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    Path('hyperbus_trace.json').write_text(json.dumps(model.transactions,indent=2)+'\n')
