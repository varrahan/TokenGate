"""Host protocol tests with independently delayed AXI and loader channels."""
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge,FallingEdge,Timer


async def cycles(dut,count=1):
    for _ in range(count):await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)


class Host:
    def __init__(self,dut):self.dut=dut;self.rng=random.Random(20261104);self.writes=0;self.reads=0

    async def write(self,address,value,strobes=15,order=None,hold=0,expected=0):
        d=self.dut;order=self.rng.randrange(3)if order is None else order
        await FallingEdge(d.clk);d.s_axi_bready.value=0;d.s_axi_awaddr.value=address;d.s_axi_wdata.value=value;d.s_axi_wstrb.value=strobes
        async def send(name):
            valid=getattr(d,"s_axi_"+name+"valid");ready=getattr(d,"s_axi_"+name+"ready")
            valid.value=1
            while True:
                await RisingEdge(d.clk)
                if int(ready.value):break
            await FallingEdge(d.clk);valid.value=0
        if order==0:
            await send("aw");await cycles(d,self.rng.randrange(1,5));await send("w")
        elif order==1:
            await send("w");await cycles(d,self.rng.randrange(1,5));await send("aw")
        else:
            a=cocotb.start_soon(send("aw"));b=cocotb.start_soon(send("w"));await a;await b
        while not int(d.s_axi_bvalid.value):await FallingEdge(d.clk)
        response=int(d.s_axi_bresp.value);assert response==expected,(hex(address),response,expected)
        for _ in range(hold):
            await FallingEdge(d.clk);assert int(d.s_axi_bvalid.value)and int(d.s_axi_bresp.value)==response
            assert not int(d.s_axi_awready.value)and not int(d.s_axi_wready.value)
        d.s_axi_bready.value=1;await cycles(d);d.s_axi_bready.value=0;self.writes+=1

    async def read(self,address,hold=0,expected_response=0):
        d=self.dut;await FallingEdge(d.clk);d.s_axi_araddr.value=address;d.s_axi_arvalid.value=1;d.s_axi_rready.value=0
        while True:
            await RisingEdge(d.clk)
            if int(d.s_axi_arready.value):break
        await FallingEdge(d.clk);d.s_axi_arvalid.value=0
        while not int(d.s_axi_rvalid.value):await FallingEdge(d.clk)
        value=int(d.s_axi_rdata.value);response=int(d.s_axi_rresp.value);assert response==expected_response
        for _ in range(hold):
            await FallingEdge(d.clk);assert int(d.s_axi_rvalid.value)and int(d.s_axi_rdata.value)==value and int(d.s_axi_rresp.value)==response
        d.s_axi_rready.value=1;await cycles(d);d.s_axi_rready.value=0;self.reads+=1;return value


@cocotb.test(timeout_time=100,timeout_unit="us")
async def independent_axi_and_completed_loader(d):
    cocotb.start_soon(Clock(d.clk,4,unit="ns").start())
    for name in("rst","s_axi_awvalid","s_axi_wvalid","s_axi_bready","s_axi_arvalid","s_axi_rready","cfg_unlock","epoch","vocabulary_valid","protocol_error","draining","datapath_idle","cfg_ready","cfg_rsp_valid","cfg_rsp_status","cfg_invalidate_ready"):
        getattr(d,name).value=0
    d.s_axi_awaddr.value=0;d.s_axi_wdata.value=0;d.s_axi_wstrb.value=0;d.s_axi_araddr.value=0
    d.rst.value=1;await cycles(d,5);d.rst.value=0;await cycles(d)
    host=Host(d);assert await host.read(0,hold=5)==0x50545831
    # Configuration is blocked outside the epoch grant and must not change.
    await host.write(0x34,0x123456,expected=2);assert await host.read(0x34)==0
    await host.write(8,1,order=1,hold=5)
    await host.write(8,3,expected=2)
    d.cfg_unlock.value=1;d.datapath_idle.value=1;await cycles(d)
    # Each byte strobe changes only its corresponding byte, independently of
    # AW/W ordering. Neighboring configuration registers must remain intact.
    await host.write(0x20,0x11223344,order=0)
    await host.write(0x20,0xaabbccdd,strobes=5,order=1,hold=7)
    assert await host.read(0x20,hold=9)==0x11bb33dd
    await host.write(0x24,0xdeadbeef,order=2)
    await host.write(0x28,0x5a)
    await host.write(0x34,0x440000);await host.write(0x38,0x200000)
    assert await host.read(0x34)==0x440000 and await host.read(0x38)==0x200000
    for address,value in [(0x18,0x800000),(0x1c,10),(0x28,0x100),(0x30,3),(0x70,2)]:await host.write(address,value,expected=2)
    assert await host.read(0x18)==0 and await host.read(0x1c)==0
    await host.write(0x34,0xffffffff,strobes=0);assert await host.read(0x34)==0x440000
    await host.write(0x35,1,expected=2);await host.write(0,1,expected=3)
    await host.read(0x78,expected_response=3);await host.read(1,expected_response=3)
    # A doorbell is outstanding until the loader result, while reads progress.
    await host.write(0x18,0x100003);await host.write(0x1c,9);await host.write(0x10,1)
    assert await host.read(0x10)==1
    command=cocotb.start_soon(host.write(0x2c,1,order=1,hold=8))
    while not int(d.cfg_valid.value):await FallingEdge(d.clk)
    held=(int(d.cfg_addr.value),int(d.cfg_bytes.value),int(d.cfg_data.value));assert held==(0x100003,9,0x5adeadbeef11bb33dd)
    assert await host.read(0x10)==0
    for _ in range(8):
        await FallingEdge(d.clk);assert int(d.cfg_valid.value)and not int(d.s_axi_bvalid.value)
        assert held==(int(d.cfg_addr.value),int(d.cfg_bytes.value),int(d.cfg_data.value))
    d.cfg_ready.value=1;await cycles(d);d.cfg_ready.value=0
    for _ in range(9):await cycles(d);assert not int(d.s_axi_bvalid.value)
    d.cfg_rsp_valid.value=1;d.cfg_rsp_status.value=0;await cycles(d);d.cfg_rsp_valid.value=0
    await command
    # A downstream failure must become SLVERR plus retained status/sticky flag.
    command=cocotb.start_soon(host.write(0x2c,1,order=0,expected=2))
    while not int(d.cfg_valid.value):await FallingEdge(d.clk)
    d.cfg_ready.value=1;await cycles(d);d.cfg_ready.value=0;await cycles(d,4)
    d.cfg_rsp_valid.value=1;d.cfg_rsp_status.value=4;await cycles(d);d.cfg_rsp_valid.value=0;await command
    assert await host.read(0x14)==4 and (await host.read(4))&64
    await host.write(0x74,2);assert not (await host.read(4))&64
    # Invalidation also holds B until the actual drain/invalidate handshake.
    command=cocotb.start_soon(host.write(8,8,order=2))
    while not int(d.cfg_invalidate_valid.value):await FallingEdge(d.clk)
    for _ in range(5):await cycles(d);assert not int(d.s_axi_bvalid.value)
    d.cfg_invalidate_ready.value=1;await cycles(d);d.cfg_invalidate_ready.value=0;await command
    # Validation dirties on register programming, and invalid commit is visible.
    await host.write(0x10,1);await host.write(0x44,216750);assert await host.read(0x10)==0
    await host.write(8,2,expected=2)
    d.protocol_error.value=1;await cycles(d);d.protocol_error.value=0
    assert (await host.read(4))&32;await host.write(0x74,1);assert not (await host.read(4))&32
    await host.write(0x10,1);await host.write(8,2)
    await host.write(8,4);assert await host.read(0x10)==0
    d._log.info("PASS: AXI-Lite bridge: %d writes/%d reads, independent AW/W, partial strobes, B/R stalls, range/grant protection, loader completion and errors, invalidation and validation dirtiness",host.writes,host.reads)
