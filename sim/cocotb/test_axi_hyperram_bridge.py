"""AXI frontend contract against an independently stalled transaction backend."""
import hashlib
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge,RisingEdge


def val(d,n):return int(getattr(d,n).value)


async def tick(d,n=1):
    for _ in range(n):await RisingEdge(d.clk)
    await FallingEdge(d.clk)


class Backend:
    def __init__(self,d,image):
        self.d=d;self.memory=bytearray(image);self.rng=random.Random(20261122)
        self.fail_next=False;self.allow=True;self.commands=[];self.held_cycles=0

    async def run(self):
        d=self.d;pending=None;present=False;held=None;held_r=None;held_b=None
        fields=('hb_cmd_write','hb_cmd_address','hb_cmd_bytes','hb_cmd_data','hb_cmd_strobes')
        while True:
            await FallingEdge(d.clk)
            reset=val(d,'rst')
            d.hb_cmd_ready.value=int(not reset and pending is None and self.allow and self.rng.randrange(4)!=0)
            if pending is not None and pending['delay']>0:pending['delay']-=1
            if pending is not None and pending['delay']==0:present=True
            d.hb_rsp_valid.value=int(not reset and present)
            d.hb_rsp_data.value=pending['data'] if pending else 0
            d.hb_rsp_error.value=int(pending['error']) if pending else 0
            await RisingEdge(d.clk)
            if reset:pending=None;present=False;held=None;held_r=None;held_b=None;continue
            item=tuple(val(d,n)for n in fields)if val(d,'hb_cmd_valid')else None
            if held is not None:assert item==held,'Buffered memory command changed under backpressure'
            held=item if item is not None and not val(d,'hb_cmd_ready')else None
            if held is not None:self.held_cycles+=1
            for prefix,saved in (('r',held_r),('b',held_b)):
                valid=val(d,'s_axi_'+prefix+'valid')
                names=('rdata','rresp','rlast')if prefix=='r'else('bresp',)
                current=tuple(val(d,'s_axi_'+n)for n in names)if valid else None
                if saved is not None:assert current==saved,('AXI response changed while held',prefix)
                saved=current if valid and not val(d,'s_axi_'+prefix+'ready')else None
                if prefix=='r':held_r=saved
                else:held_b=saved
            if val(d,'hb_rsp_valid')and val(d,'hb_rsp_ready'):pending=None;present=False
            if item is not None and val(d,'hb_cmd_ready'):
                assert pending is None
                write,address,size,data,strobes=item
                assert size in range(8,65,8) and address%8==0 and address+size<=len(self.memory)
                assert address//4096==(address+size-1)//4096
                assert data>>(8*size)==0 and strobes>>size==0
                if write:
                    for i in range(size):
                        if strobes>>i&1:self.memory[address+i]=data>>(8*i)&255
                    result=0
                else:
                    assert data==strobes==0
                    result=int.from_bytes(self.memory[address:address+size],'little')
                error=self.fail_next;self.fail_next=False
                self.commands.append(dict(write=write,address=address,bytes=size,error=error))
                pending=dict(data=result,error=error,delay=self.rng.randrange(1,12))


class Host:
    def __init__(self,d,backend):self.d=d;self.backend=backend;self.rng=random.Random(20261123);self.reads=0;self.writes=0

    async def send(self,channel):
        d=self.d;await FallingEdge(d.clk);getattr(d,'s_axi_'+channel+'valid').value=1
        for _ in range(10000):
            await RisingEdge(d.clk)
            if val(d,'s_axi_'+channel+'ready'):break
        else:raise AssertionError(('AXI input timeout',channel))
        await FallingEdge(d.clk);getattr(d,'s_axi_'+channel+'valid').value=0

    async def read(self,address,beats,*,size=3,burst=1,status=0,expected=None):
        d=self.d;d.s_axi_rready.value=0;d.s_axi_araddr.value=address;d.s_axi_arlen.value=beats-1
        d.s_axi_arsize.value=size;d.s_axi_arburst.value=burst
        await self.send('ar');d.s_axi_araddr.value=0x7fffff;d.s_axi_arlen.value=255;d.s_axi_arsize.value=0;d.s_axi_arburst.value=2
        await tick(d,13);received=[]
        for _ in range(20000):
            d.s_axi_rready.value=int(self.rng.randrange(4)!=0)
            await RisingEdge(d.clk)
            if val(d,'s_axi_rvalid')and val(d,'s_axi_rready'):
                assert val(d,'s_axi_rresp')==status
                assert val(d,'s_axi_rlast')==int(len(received)+1==beats)
                received.append(val(d,'s_axi_rdata'))
            await FallingEdge(d.clk)
            if len(received)==beats:break
        else:raise AssertionError('AXI read did not finish')
        d.s_axi_rready.value=0;self.reads+=1
        raw=b''.join(word.to_bytes(8,'little')for word in received)
        assert raw==(bytes(8*beats)if status else expected)

    async def write(self,address,data,strobes,*,order=0,length=None,size=3,burst=1,status=0):
        d=self.d;beats=len(data)//8;assert len(data)==8*len(strobes) and beats>0
        d.s_axi_bready.value=0
        async def address_channel():
            if order==1:await tick(d,17)
            d.s_axi_awaddr.value=address;d.s_axi_awlen.value=beats-1 if length is None else length
            d.s_axi_awsize.value=size;d.s_axi_awburst.value=burst
            await self.send('aw');d.s_axi_awaddr.value=0x7fffff;d.s_axi_awlen.value=255;d.s_axi_awsize.value=0;d.s_axi_awburst.value=2
        async def data_channel():
            if order==0:await tick(d,17)
            for index in range(beats):
                await tick(d,self.rng.randrange(1,4))
                d.s_axi_wdata.value=int.from_bytes(data[8*index:8*index+8],'little');d.s_axi_wstrb.value=strobes[index]
                d.s_axi_wlast.value=int(index+1==beats);await self.send('w')
                d.s_axi_wdata.value=(1<<64)-1;d.s_axi_wstrb.value=0;d.s_axi_wlast.value=0
        aw=cocotb.start_soon(address_channel());w=cocotb.start_soon(data_channel());await aw;await w
        for _ in range(10000):
            if val(d,'s_axi_bvalid'):break
            await tick(d)
        else:raise AssertionError('AXI write result did not arrive')
        for _ in range(17):await tick(d);assert val(d,'s_axi_bvalid')and val(d,'s_axi_bresp')==status
        d.s_axi_bready.value=1;await tick(d);d.s_axi_bready.value=0;self.writes+=1


@cocotb.test(timeout_time=10,timeout_unit='ms')
async def buffered_axi_transactions_preserve_data_and_errors(d):
    image=Path(os.environ['PARSER_HYPERRAM_IMAGE']).read_bytes();assert len(image)==8*1024*1024
    expected=bytearray(image);backend=Backend(d,image);h=Host(d,backend);rng=random.Random(20261124)
    d.clk.value=0;d.rst.value=1
    for name in ('s_axi_arvalid','s_axi_awvalid','s_axi_wvalid','s_axi_rready','s_axi_bready',
        's_axi_araddr','s_axi_arlen','s_axi_arsize','s_axi_arburst','s_axi_awaddr','s_axi_awlen',
        's_axi_awsize','s_axi_awburst','s_axi_wdata','s_axi_wstrb','s_axi_wlast','hb_cmd_ready','hb_rsp_valid','hb_rsp_data','hb_rsp_error'):
        getattr(d,name).value=0
    cocotb.start_soon(Clock(d.clk,5,unit='ns').start());cocotb.start_soon(backend.run())
    await tick(d,5);d.rst.value=0;await tick(d)
    for i in range(80):
        beats=1+i%8;address=(rng.randrange(len(image)//64)*64)
        await h.read(address,beats,expected=bytes(expected[address:address+8*beats]))
        address=(rng.randrange(len(image)//64)*64);data=rng.randbytes(8*beats)
        strobes=[rng.randrange(256)for _ in range(beats)] if i%5 else [0]*beats
        await h.write(address,data,strobes,order=i%3)
        for b in range(beats):
            for lane in range(8):
                if strobes[b]>>lane&1:expected[address+8*b+lane]=data[8*b+lane]
        await h.read(address,beats,expected=bytes(expected[address:address+8*beats]))
    rejected=[]
    for address,beats,size,burst in ((1,1,3,1),(0,1,2,1),(0,1,3,0),(0,1,3,2),
        (0,9,3,1),(0,256,3,1),(4096-8,2,3,1),(len(image)-8,2,3,1)):
        before=len(backend.commands);await h.read(address,beats,size=size,burst=burst,status=3)
        assert len(backend.commands)==before;rejected.append(dict(address=address,beats=beats,size=size,burst=burst))
    for kwargs,data_beats in ((dict(address=1),1),(dict(address=0,size=2),1),(dict(address=0,burst=0),1),
        (dict(address=4096-8),2),(dict(address=len(image)-8),2),(dict(address=0,length=7),2),
        (dict(address=0,length=7),9)):
        before=len(backend.commands)
        malformed=kwargs.get('length')==7
        await h.write(data=rng.randbytes(data_beats*8),strobes=[255]*data_beats,status=2 if malformed else 3,**kwargs)
        assert len(backend.commands)==before
    # A stalled read command must remain stable while independent AW/W arrive.
    backend.allow=False
    r=cocotb.start_soon(h.read(0,8,expected=bytes(expected[:64])))
    for _ in range(1000):
        if val(d,'hb_cmd_valid'):break
        await tick(d)
    else:raise AssertionError('No buffered read command')
    data=rng.randbytes(16);address=0x700000
    w=cocotb.start_soon(h.write(address,data,[255,255],order=2))
    await tick(d,37);backend.allow=True;await r;await w;expected[address:address+16]=data
    for i in range(32):
        beats=1+i%8;read_address=0x1000+i*64;write_address=0x700000+i*64
        data=rng.randbytes(8*beats);strobes=[rng.randrange(256)for _ in range(beats)]
        r=cocotb.start_soon(h.read(read_address,beats,expected=bytes(expected[read_address:read_address+8*beats])))
        w=cocotb.start_soon(h.write(write_address,data,strobes,order=i%3))
        await r;await w
        for b in range(beats):
            for lane in range(8):
                if strobes[b]>>lane&1:expected[write_address+8*b+lane]=data[8*b+lane]
    # Errors may follow physically applied writes. Never acknowledge them OK.
    backend.fail_next=True;await h.read(0,8,status=2)
    backend.fail_next=True;data=rng.randbytes(8);await h.write(len(image)-8,data,[255],status=2,order=1)
    expected[-8:]=data
    await h.read(len(image)-8,1,expected=data)
    await tick(d,5);assert val(d,'idle') and backend.memory==expected and backend.held_cycles>=37
    result=dict(phase='passed',axi_reads=h.reads,axi_writes=h.writes,actual_backend_commands=len(backend.commands),
        rejected_read_cases=rejected,rejected_write_cases=7,backend_errors=2,
        independently_stalled_channels=True,write_data_before_address_verified=True,held_read_and_write_results_verified=True,
        full_8mib_image_loaded=True,initial_image_sha256=hashlib.sha256(image).hexdigest(),
        final_memory_sha256=hashlib.sha256(backend.memory).hexdigest(),held_command_cycles=backend.held_cycles,
        partial_strobes_and_zero_strobes_verified=True,malformed_bursts_never_reach_backend=True,
        simultaneous_read_write_rounds=33,
        physical_hyperbus_phy_verified=False,axi_cdc_verified=False,native_timing_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result,indent=2)+'\n')
