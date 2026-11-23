"""Program and read back every byte of the complete image through real AXI RTL."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge,FallingEdge
from hyperram_word_model import HyperRAMWordModel,value
from test_hyperram_startup import Lifecycle,reset_device,wait_status
from test_axi_hyperram_bridge import tick


class WireDigest:
    # Verify each decoded transaction online instead of retaining a large trace.
    def __init__(self,image):
        self.image=image;self.registers=[];self.writes=0;self.reads=0
        self.write_hash=hashlib.sha256();self.read_hash=hashlib.sha256();self.last=None

    def append(self,t):
        assert len(t['ca_words'])==3 and t['ca_hex']
        if t['register']:
            assert self.writes==self.reads==0;self.registers.append(t);assert len(self.registers)<=4
            return
        assert len(self.registers)==4
        if t['write']:
            assert self.reads==0;index=self.writes;words=t['write_words']
            assert t['write_masks']==[0]*32
        else:
            assert self.writes==len(self.image)//64;index=self.reads;words=t['read_words']
        assert t['address']==index*64 and len(words)==32
        raw=b''.join(word.to_bytes(2,'big')for word in words)
        assert raw==self.image[index*64:index*64+64]
        if t['write']:self.write_hash.update(raw);self.writes+=1
        else:self.read_hash.update(raw);self.reads+=1
        self.last=dict(ca_hex=t['ca_hex'],address=t['address'],write=t['write'],bytes=64)


async def write_burst(d,address,payload):
    assert len(payload)==64
    d.s_axi_awaddr.value=address;d.s_axi_awlen.value=7;d.s_axi_awsize.value=3;d.s_axi_awburst.value=1
    d.s_axi_awvalid.value=1;d.s_axi_wvalid.value=1;d.s_axi_wstrb.value=255
    d.s_axi_wdata.value=int.from_bytes(payload[:8],'little');d.s_axi_wlast.value=0;d.s_axi_bready.value=1
    address_done=False;beat=0
    for _ in range(1000):
        await RisingEdge(d.clk)
        aw=not address_done and value(d,'s_axi_awready')
        w=beat<8 and value(d,'s_axi_wready')
        b=value(d,'s_axi_bvalid')
        if b:assert address_done and beat==8 and value(d,'s_axi_bresp')==0
        await FallingEdge(d.clk)
        if aw:address_done=True;d.s_axi_awvalid.value=0
        if w:
            beat+=1
            if beat==8:d.s_axi_wvalid.value=0
            else:
                d.s_axi_wdata.value=int.from_bytes(payload[8*beat:8*beat+8],'little')
                d.s_axi_wlast.value=int(beat==7)
        if b:return
    raise AssertionError(('Bootstrap AXI write timed out',address))


async def read_burst(d,address):
    d.s_axi_araddr.value=address;d.s_axi_arlen.value=7;d.s_axi_arsize.value=3;d.s_axi_arburst.value=1
    d.s_axi_arvalid.value=1;d.s_axi_rready.value=1;address_done=False;words=[]
    for _ in range(1000):
        await RisingEdge(d.clk)
        ar=not address_done and value(d,'s_axi_arready')
        if value(d,'s_axi_rvalid'):
            assert address_done and value(d,'s_axi_rresp')==0
            assert value(d,'s_axi_rlast')==int(len(words)==7)
            words.append(value(d,'s_axi_rdata'))
        await FallingEdge(d.clk)
        if ar:address_done=True;d.s_axi_arvalid.value=0
        if len(words)==8:return b''.join(word.to_bytes(8,'little')for word in words)
    raise AssertionError(('Bootstrap AXI read timed out',address))


def progress(phase,count,total):
    Path('progress.json').write_text(json.dumps(dict(phase=phase,completed_bytes=count,total_bytes=total))+'\n')


@cocotb.test(timeout_time=500,timeout_unit='ms')
async def complete_image_is_programmed_and_read_back_through_axi(d):
    image=Path(os.environ['PARSER_HYPERRAM_IMAGE']).read_bytes();assert len(image)==8388608
    model=HyperRAMWordModel(d,image,200000000);wire=WireDigest(image);model.transactions=wire
    lifecycle=Lifecycle(d,model,200000000)
    d.clk.value=0;d.rst.value=1;d.power_good.value=0;d.phy_ready.value=0;d.contents_reload_ack.value=0
    for name in ('s_axi_arvalid','s_axi_awvalid','s_axi_wvalid','s_axi_rready','s_axi_bready',
        's_axi_araddr','s_axi_arlen','s_axi_arsize','s_axi_arburst','s_axi_awaddr','s_axi_awlen',
        's_axi_awsize','s_axi_awburst','s_axi_wdata','s_axi_wstrb','s_axi_wlast',
        'phy_latency_extra','phy_rx_valid','phy_rx_word','phy_fault'):
        getattr(d,name).value=0
    cocotb.start_soon(Clock(d.clk,5,unit='ns').start());cocotb.start_soon(model.run());cocotb.start_soon(lifecycle.run())
    await reset_device(d,lifecycle);await wait_status(d)
    assert value(d,'contents_lost')and model.memory!=image
    before=model.clock;progress('writing',0,len(image))
    for address in range(0,len(image),64):
        await write_burst(d,address,image[address:address+64])
        assert value(d,'contents_lost')and value(d,'memory_ready')and not value(d,'startup_fault')
        if (address+64)%(256*1024)==0:
            progress('writing',address+64,len(image));d._log.info('Bootstrap wrote %d/%d bytes',address+64,len(image))
    write_cycles=model.clock-before
    assert model.memory==image and wire.writes==131072 and wire.reads==0
    assert wire.write_hash.hexdigest()==hashlib.sha256(image).hexdigest()
    before=model.clock;received_hash=hashlib.sha256();progress('reading',0,len(image))
    for address in range(0,len(image),64):
        actual=await read_burst(d,address);assert actual==image[address:address+64];received_hash.update(actual)
        assert value(d,'contents_lost')and value(d,'memory_ready')and not value(d,'startup_fault')
        if (address+64)%(256*1024)==0:
            progress('reading',address+64,len(image));d._log.info('Bootstrap read %d/%d bytes',address+64,len(image))
    read_cycles=model.clock-before
    d.s_axi_rready.value=0;d.s_axi_bready.value=0;await tick(d,5)
    assert value(d,'idle')and model.current is None and model.memory==image
    expected_hash=hashlib.sha256(image).hexdigest()
    assert wire.reads==131072 and wire.read_hash.hexdigest()==received_hash.hexdigest()==expected_hash
    d.contents_reload_ack.value=1;await tick(d);d.contents_reload_ack.value=0
    assert not value(d,'contents_lost')
    accepted=dict(phase='passed',image_bytes=len(image),axi_writes=wire.writes,axi_reads=wire.reads,
        hyperbus_register_transactions=4,write_cycles=write_cycles,read_cycles=read_cycles,
        image_sha256=expected_hash,wire_write_sha256=wire.write_hash.hexdigest(),
        wire_read_sha256=wire.read_hash.hexdigest(),axi_read_sha256=received_hash.hexdigest(),
        reset_destroyed_previous_image_verified=True,every_byte_programmed_and_read_back=True,
        no_vocabulary_or_address_range_reduction=True,contents_loss_ack_after_complete_readback=True,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,application_instantiation_verified=False,
        native_timing_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n')
    Path('wire-summary.json').write_text(json.dumps(dict(registers=wire.registers,last=wire.last,
        writes=wire.writes,reads=wire.reads,write_sha256=wire.write_hash.hexdigest(),read_sha256=wire.read_hash.hexdigest()),indent=2)+'\n')
    progress('passed',len(image),len(image))
