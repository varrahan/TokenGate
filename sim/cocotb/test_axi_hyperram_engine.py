"""Actual AXI bursts through the real sequencer to decoded HyperBus words."""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from hyperram_word_model import HyperRAMWordModel,value
from test_axi_hyperram_bridge import Host,tick


async def observe_held_outputs(d):
    held={}
    interfaces=(('s_axi_rvalid','s_axi_rready',('s_axi_rdata','s_axi_rresp','s_axi_rlast')),
        ('s_axi_bvalid','s_axi_bready',('s_axi_bresp',)),
        ('hb_cmd_valid','hb_cmd_ready',('hb_cmd_write','hb_cmd_address','hb_cmd_bytes','hb_cmd_data','hb_cmd_strobes')))
    while True:
        await RisingEdge(d.clk)
        if value(d,'rst'):held={};continue
        for valid,ready,fields in interfaces:
            item=tuple(value(d,n)for n in fields)if value(d,valid)else None
            if valid in held:assert item==held[valid],(valid,'changed under backpressure')
            if item is not None and not value(d,ready):held[valid]=item
            else:held.pop(valid,None)


@cocotb.test(timeout_time=10,timeout_unit='ms')
async def axi_bursts_reach_actual_hyperbus_word_sequencer(d):
    image=Path(os.environ['PARSER_HYPERRAM_IMAGE']).read_bytes();expected=bytearray(image);rng=random.Random(20261126)
    model=HyperRAMWordModel(d,image);host=Host(d,model)
    d.clk.value=0;d.rst.value=1;d.enable.value=0;d.cfg_latency.value=7;d.cfg_fixed_latency.value=1
    for name in ('s_axi_arvalid','s_axi_awvalid','s_axi_wvalid','s_axi_rready','s_axi_bready',
        's_axi_araddr','s_axi_arlen','s_axi_arsize','s_axi_arburst','s_axi_awaddr','s_axi_awlen',
        's_axi_awsize','s_axi_awburst','s_axi_wdata','s_axi_wstrb','s_axi_wlast',
        'phy_latency_extra','phy_rx_valid','phy_rx_word','phy_fault'):
        getattr(d,name).value=0
    cocotb.start_soon(Clock(d.clk,5,unit='ns').start());cocotb.start_soon(model.run());cocotb.start_soon(observe_held_outputs(d))
    await tick(d,5);d.rst.value=0;await tick(d)
    # Bus traffic can queue while the external device is not yet enabled.
    read=cocotb.start_soon(host.read(0,8,expected=bytes(expected[:64])))
    for _ in range(1000):
        if value(d,'hb_cmd_valid'):break
        await tick(d)
    else:raise AssertionError('No buffered command while engine disabled')
    payload=rng.randbytes(16);address=0x700000
    write=cocotb.start_soon(host.write(address,payload,[255,255],order=2))
    for _ in range(37):
        await tick(d);assert value(d,'phy_cs_n')and not value(d,'hb_cmd_ready')
    d.enable.value=1;await read;await write;expected[address:address+16]=payload
    for i in range(64):
        beats=1+i%8;address=rng.randrange(len(image)//64)*64
        model.rx_delay_next=i%4
        await host.read(address,beats,expected=bytes(expected[address:address+8*beats]))
        address=rng.randrange(len(image)//64)*64;payload=rng.randbytes(8*beats)
        strobes=[rng.randrange(256)for _ in range(beats)]if i%5 else[0]*beats
        await host.write(address,payload,strobes,order=i%3)
        transaction=model.transactions[-1]
        assert transaction['write']and not transaction['register']and transaction['address']==address
        assert len(transaction['write_words'])==4*beats
        for b in range(beats):
            for lane in range(8):
                if strobes[b]>>lane&1:expected[address+8*b+lane]=payload[8*b+lane]
        await host.read(address,beats,expected=bytes(expected[address:address+8*beats]))
    for i in range(16):
        beats=1+i%8;ra=0x1000+i*64;wa=0x710000+i*64;payload=rng.randbytes(8*beats);strobes=[rng.randrange(256)for _ in range(beats)]
        r=cocotb.start_soon(host.read(ra,beats,expected=bytes(expected[ra:ra+8*beats])))
        w=cocotb.start_soon(host.write(wa,payload,strobes,order=i%3));await r;await w
        for b in range(beats):
            for lane in range(8):
                if strobes[b]>>lane&1:expected[wa+8*b+lane]=payload[8*b+lane]
    before=len(model.transactions)
    for address,beats,size,burst in((1,1,3,1),(0,1,2,1),(0,1,3,0),(0,1,3,2),
        (0,9,3,1),(0,256,3,1),(4096-8,2,3,1),(len(image)-8,2,3,1)):
        await host.read(address,beats,size=size,burst=burst,status=3)
    for kwargs,beats in((dict(address=1),1),(dict(address=0,size=2),1),(dict(address=0,burst=0),1),
        (dict(address=4096-8),2),(dict(address=len(image)-8),2),(dict(address=0,length=7),2),(dict(address=0,length=7),9)):
        await host.write(data=rng.randbytes(8*beats),strobes=[255]*beats,status=2 if kwargs.get('length')==7 else 3,**kwargs)
    assert len(model.transactions)==before
    model.drop_after_next=3;await host.read(0,8,status=2)
    assert value(d,'memory_detail')==2 and model.transactions[-1]['cs_cycles']==180
    await host.read(0,8,expected=bytes(expected[:64]))
    address=0x720000;payload=rng.randbytes(64);model.fault_after_write_next=3
    await host.write(address,payload,[255]*8,status=2)
    partial=model.transactions[-1];assert 3<=len(partial['write_words'])<32 and value(d,'memory_detail')==3
    expected[address:address+2*len(partial['write_words'])]=payload[:2*len(partial['write_words'])]
    await host.read(address,8,expected=bytes(expected[address:address+64]))
    await tick(d,5);assert value(d,'idle')and model.current is None and model.memory==expected
    assert len(model.transactions)==host.reads+host.writes-15
    result=dict(phase='passed',axi_reads=host.reads,axi_writes=host.writes,hyperbus_word_transactions=len(model.transactions),
        rejected_axi_requests=15,simultaneous_read_write_rounds=17,actual_phy_timeout_cycles=180,
        partial_write_error_words=len(partial['write_words']),full_image_sha256=hashlib.sha256(image).hexdigest(),
        final_memory_sha256=hashlib.sha256(model.memory).hexdigest(),actual_axi_and_hyperbus_modules_connected=True,
        independently_decoded_ca_and_data_verified=True,held_axi_and_backend_commands_verified=True,
        byte_strobes_and_endian_conversion_verified=True,bounded_phy_errors_propagated_to_axi=True,
        full_image_byte_scoreboard_verified=True,pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,
        device_initialization_manager_verified=False,native_timing_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
    Path('hyperbus_trace.json').write_text(json.dumps(model.transactions,indent=2)+'\n')
