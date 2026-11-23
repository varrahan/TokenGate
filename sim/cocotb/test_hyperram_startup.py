"""Device startup and queued AXI access through the real three-module assembly."""
import hashlib
import json
import math
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge
from hyperram_word_model import HyperRAMWordModel,value
from test_axi_hyperram_bridge import Host,tick


class Lifecycle:
    def __init__(self,d,model,hz):
        self.d=d;self.model=model;self.hz=hz;self.cycles=0;self.low=None;self.released=None
        self.first_cs=False;self.id0=0x0c81;self.id1=1;self.inject=None;self.corrupt=False
        self.epochs=0;self.expected=None;self.timings=[];self.current=None;self.corrupted=False

    async def run(self):
        d=self.d;m=self.model
        while True:
            await FallingEdge(d.clk);self.cycles+=1
            if not value(d,'phy_reset_n'):
                assert value(d,'phy_cs_n')and not value(d,'phy_clock_enable')
                if self.low is None:
                    self.low=self.cycles;self.epochs+=1;self.first_cs=False;self.corrupted=False
                    # RESET# stops refresh: deliberately destroy the old image.
                    self.expected=bytearray(bytes([self.epochs&255])*len(m.memory))
                    m.memory[:]=self.expected
                m.registers.update({0:self.id0,2:self.id1,0x1000:0x8f2f,0x1002:0xffc2})
            elif self.low is not None:
                assert self.cycles-self.low>=math.ceil(self.hz*200e-9)
                self.current=dict(reset_low_cycles=self.cycles-self.low,reset_release_cycle=self.cycles)
                self.released=self.cycles;self.low=None
                if self.inject=='timeout':m.drop_after_next=0
                if self.inject=='phy_fault':m.fault_after_read_next=0
            if value(d,'phy_reset_n')and not value(d,'phy_cs_n')and not self.first_cs:
                delay=self.cycles-self.released
                assert delay>=math.ceil(self.hz*150e-6),(delay,self.hz)
                self.current['first_cs_delay_cycles']=delay;self.timings.append(self.current);self.first_cs=True
            if self.corrupt and not self.corrupted and value(d,'startup_phase')==8:
                # Simulate a bad configuration readback without altering latency.
                m.registers[0x1000]^=0x0100;self.corrupted=True
            if not value(d,'memory_ready'):
                assert not value(d,'hb_cmd_ready')and not value(d,'hb_rsp_valid')


async def wait_status(d,*,fault=False):
    for _ in range(100000):
        if value(d,'startup_fault'if fault else'memory_ready'):return
        assert not value(d,'memory_ready'if fault else'startup_fault')
        await tick(d)
    raise AssertionError('Startup did not reach a bounded status')


async def reset_device(d,lifecycle,*,id0=0x0c81,id1=1,inject=None,corrupt=False):
    d.rst.value=1;d.power_good.value=0;d.phy_ready.value=0;d.contents_reload_ack.value=0
    for name in ('s_axi_arvalid','s_axi_awvalid','s_axi_wvalid','s_axi_rready','s_axi_bready'):
        getattr(d,name).value=0
    lifecycle.id0=id0;lifecycle.id1=id1;lifecycle.inject=inject;lifecycle.corrupt=corrupt
    await tick(d,7);d.rst.value=0;d.power_good.value=1
    await tick(d,13)
    assert value(d,'fabric_reset')and not value(d,'phy_reset_n')
    d.phy_ready.value=1;await tick(d)


async def queue_both(d,h,address,payload):
    d.s_axi_araddr.value=0;d.s_axi_arlen.value=0;d.s_axi_arsize.value=3;d.s_axi_arburst.value=1
    await h.send('ar')
    d.s_axi_awaddr.value=address;d.s_axi_awlen.value=7;d.s_axi_awsize.value=3;d.s_axi_awburst.value=1
    await h.send('aw')
    for index in range(8):
        d.s_axi_wdata.value=int.from_bytes(payload[index*8:index*8+8],'little')
        d.s_axi_wstrb.value=255;d.s_axi_wlast.value=int(index==7);await h.send('w')
    assert not value(d,'memory_ready')and not value(d,'s_axi_rvalid')and not value(d,'s_axi_bvalid')


async def drain_queued(d,expected):
    for _ in range(1000):
        if value(d,'s_axi_rvalid')and value(d,'s_axi_bvalid'):break
        await tick(d)
    else:raise AssertionError('Queued AXI traffic did not resume after startup')
    saved=(value(d,'s_axi_rdata'),value(d,'s_axi_rresp'),value(d,'s_axi_rlast'),value(d,'s_axi_bresp'))
    assert saved==(int.from_bytes(expected[:8],'little'),0,1,0)
    for _ in range(23):
        await tick(d)
        assert value(d,'s_axi_rvalid')and value(d,'s_axi_bvalid')
        assert saved==tuple(value(d,n)for n in ('s_axi_rdata','s_axi_rresp','s_axi_rlast','s_axi_bresp'))
    d.s_axi_rready.value=1;d.s_axi_bready.value=1;await tick(d)
    d.s_axi_rready.value=0;d.s_axi_bready.value=0;await tick(d)


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def startup_checks_device_before_releasing_axi(d):
    image=Path(os.environ['PARSER_HYPERRAM_IMAGE']).read_bytes();assert len(image)==8388608
    hz=int(os.environ['PARSER_HYPERRAM_CLOCK_HZ']);latency=int(os.environ['PARSER_HYPERRAM_LATENCY'])
    fixed=int(os.environ['PARSER_HYPERRAM_FIXED']);code={3:14,4:15,5:0,6:1,7:2}[latency]
    config=0x8f07|(code<<4)|(fixed<<3)
    model=HyperRAMWordModel(d,image,hz);h=Host(d,model);lifecycle=Lifecycle(d,model,hz)
    d.clk.value=0;d.rst.value=1;d.power_good.value=0;d.phy_ready.value=0;d.contents_reload_ack.value=0
    for name in ('s_axi_arvalid','s_axi_awvalid','s_axi_wvalid','s_axi_rready','s_axi_bready',
        's_axi_araddr','s_axi_arlen','s_axi_arsize','s_axi_arburst','s_axi_awaddr','s_axi_awlen',
        's_axi_awsize','s_axi_awburst','s_axi_wdata','s_axi_wstrb','s_axi_wlast',
        'phy_latency_extra','phy_rx_valid','phy_rx_word','phy_fault'):
        getattr(d,name).value=0
    period=2*math.ceil(1e12/hz/2)
    cocotb.start_soon(Clock(d.clk,period,unit='ps').start())
    cocotb.start_soon(model.run());cocotb.start_soon(lifecycle.run())
    await reset_device(d,lifecycle)
    payload=bytes(range(64));address=0x700000
    await queue_both(d,h,address,payload)
    # Even a premature host acknowledgement cannot clear the reset-loss status.
    d.contents_reload_ack.value=1;await tick(d,17);d.contents_reload_ack.value=0
    assert value(d,'contents_lost')
    await wait_status(d)
    assert [value(d,n)for n in('device_id0','device_id1','config_readback')]==[0x0c81,1,config]
    assert value(d,'contents_lost')and not value(d,'startup_fault')
    first=list(model.transactions[:4])
    assert [(t['register'],t['write'],t['address'])for t in first]==[
        (True,False,0),(True,False,2),(True,True,0x1000),(True,False,0x1000)]
    assert first[2]['write_words']==[config]and first[2]['clocks']==4
    assert first[3]['data_clock']==2+latency*(2 if fixed else 1)
    await drain_queued(d,lifecycle.expected)
    lifecycle.expected[address:address+64]=payload
    await h.read(address,8,expected=payload)
    assert model.memory==lifecycle.expected
    # This is acknowledgement of an external validated reload, not an image validator.
    d.contents_reload_ack.value=1;await tick(d);d.contents_reload_ack.value=0
    assert not value(d,'contents_lost')
    failures=[]
    for kwargs,detail in ((dict(id0=0x0c82),0x11),(dict(id1=2),0x12),
        (dict(corrupt=True),0x13),(dict(inject='timeout'),0x22),(dict(inject='phy_fault'),0x23)):
        await reset_device(d,lifecycle,**kwargs)
        d.s_axi_araddr.value=0;d.s_axi_arlen.value=0;d.s_axi_arsize.value=3;d.s_axi_arburst.value=1
        await h.send('ar');await wait_status(d,fault=True)
        assert value(d,'startup_detail')==detail and value(d,'contents_lost')
        before=len(model.transactions)
        for _ in range(53):
            await tick(d)
            assert not value(d,'memory_ready')and not value(d,'s_axi_rvalid')
            assert value(d,'startup_fault')and value(d,'startup_detail')==detail
        assert len(model.transactions)==before and all(t.get('register',True)for t in model.transactions[-1:])
        failures.append(detail)
    await reset_device(d,lifecycle);await wait_status(d)
    assert value(d,'contents_lost')and model.memory==lifecycle.expected
    await h.read(0,1,expected=bytes(lifecycle.expected[:8]))
    # Supply loss during a real issued AXI transaction asserts the shared reset.
    d.s_axi_araddr.value=0;d.s_axi_arlen.value=7;d.s_axi_arsize.value=3;d.s_axi_arburst.value=1
    await h.send('ar')
    for _ in range(1000):
        txn=model.current
        if txn is not None and not txn.get('register',True)and len(txn['read_words'])>=4:break
        await tick(d)
    else:raise AssertionError('No actual partial HyperBus read to reset')
    reset_read_words=len(model.current['read_words']);assert 4<=reset_read_words<32
    d.power_good.value=0;await tick(d,3)
    assert value(d,'fabric_reset')and not value(d,'s_axi_arready')and not value(d,'s_axi_rvalid')
    assert value(d,'contents_lost')and value(d,'phy_cs_n')and not value(d,'phy_reset_n')
    d.power_good.value=1;await tick(d);await wait_status(d)
    assert not value(d,'s_axi_rvalid')and value(d,'contents_lost')
    await h.read(0,1,expected=bytes(lifecycle.expected[:8]))
    await tick(d,5);assert value(d,'idle')and model.memory==lifecycle.expected
    result=dict(phase='passed',clock_hz=hz,latency=latency,fixed_latency=fixed,config_word=config,
        startup_attempts=len(lifecycle.timings),hardware_reset_epochs=lifecycle.epochs,
        startup_fault_details=failures,reset_timing=lifecycle.timings,
        hyperbus_transactions=len(model.transactions),queued_axi_reads=1,queued_axi_writes=1,
        partial_read_words_before_supply_loss=reset_read_words,
        completed_host_reads=h.reads,full_image_sha256=hashlib.sha256(image).hexdigest(),
        final_memory_sha256=hashlib.sha256(model.memory).hexdigest(),
        register_sequence_and_config_latency_verified=True,powerup_reset_delays_verified=True,
        startup_faults_fence_axi_verified=True,shared_reset_aborts_inflight_axi_verified=True,
        reset_destroys_old_memory_image_in_device_model=True,contents_loss_ack_is_external_trust=True,
        full_image_bootstrap_via_axi_verified=False,pin_level_ddr_phy_verified=False,
        rwds_cdc_verified=False,application_instantiation_verified=False,native_timing_verified=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    Path('hyperbus_trace.json').write_text(json.dumps(model.transactions,indent=2)+'\n')
