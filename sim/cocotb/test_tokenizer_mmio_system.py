"""Real MMIO -> epoch/loader -> shared-cache tokenizer integration.

Initial complete weights are preloaded in the independent AXI memory BFM.
Runtime replacement bytes traverse actual AXI-Lite and external AXI writes.
Bulk cold loading and transport packet acceptance are separate pending tests.
"""
from pathlib import Path
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge,FallingEdge
from test_tokenizer_mmio import Host,cycles


class Memory:
    def __init__(self,dut,image):
        self.d=dut;self.data=image;self.rng=random.Random(555);self.reads=0;self.writes=0

    async def run(self):
        d=self.d;read=None;read_present=False;read_payload=0;aw=None;words=[];b_pending=False;b_present=False
        for name in("arready","rvalid","rdata","rresp","rlast","awready","wready","bvalid","bresp"):
            getattr(d,"m_axi_"+name).value=0
        while True:
            await FallingEdge(d.clk)
            reset=bool(d.rst.value)
            if reset:read=None;read_present=False;aw=None;words=[];b_pending=False;b_present=False
            d.m_axi_arready.value=not reset and read is None and not read_present and self.rng.randrange(4)!=0
            if not read_present and read is not None and self.rng.randrange(4)!=0:
                address,index,total=read;read_payload=int.from_bytes(self.data[address+8*index:address+8*index+8],"little");read_present=True
            d.m_axi_rvalid.value=not reset and read_present;d.m_axi_rdata.value=read_payload
            d.m_axi_rlast.value=read is not None and read[1]+1==read[2];d.m_axi_rresp.value=0
            d.m_axi_awready.value=not reset and aw is None and not b_pending and self.rng.randrange(3)!=0
            d.m_axi_wready.value=not reset and len(words)<2 and not b_pending and self.rng.randrange(3)!=0
            if b_pending and not b_present and self.rng.randrange(3)!=0:b_present=True
            d.m_axi_bvalid.value=not reset and b_present;d.m_axi_bresp.value=0
            await RisingEdge(d.clk)
            if reset:continue
            if read_present and int(d.m_axi_rready.value):
                address,index,total=read;read=(address,index+1,total)if index+1<total else None;read_present=False
            if int(d.m_axi_arvalid.value)and int(d.m_axi_arready.value):
                address=int(d.m_axi_araddr.value);total=int(d.m_axi_arlen.value)+1
                assert address%64==0 and total==8 and int(d.m_axi_arsize.value)==3 and int(d.m_axi_arburst.value)==1
                assert address+64<=len(self.data);read=(address,0,total);self.reads+=1
            if b_present and int(d.m_axi_bready.value):aw=None;words=[];b_pending=False;b_present=False
            if int(d.m_axi_awvalid.value)and int(d.m_axi_awready.value):
                address=int(d.m_axi_awaddr.value);total=int(d.m_axi_awlen.value)+1
                assert address%8==0 and 1<=total<=2 and address+8*total<=len(self.data)
                assert int(d.m_axi_awsize.value)==3 and int(d.m_axi_awburst.value)==1;aw=(address,total)
            if int(d.m_axi_wvalid.value)and int(d.m_axi_wready.value):
                words.append((int(d.m_axi_wdata.value),int(d.m_axi_wstrb.value),int(d.m_axi_wlast.value)))
            if aw is not None and words and words[-1][2]and not b_pending:
                address,total=aw;assert len(words)==total
                for beat,(data,keep,last)in enumerate(words):
                    assert last==int(beat+1==total)
                    for lane in range(8):
                        if keep>>lane&1:self.data[address+8*beat+lane]=data>>(8*lane)&255
                b_pending=True;self.writes+=1


async def send_text(d,raw,context):
    positions=list(range(0,len(raw),8))or[0]
    for position in positions:
        chunk=raw[position:position+8];data=sum(byte<<(16*i)for i,byte in enumerate(chunk));keep=sum(1<<(2*i)for i in range(len(chunk)))
        await FallingEdge(d.clk);d.s_axis_text_tdata.value=data;d.s_axis_text_tkeep.value=keep;d.s_axis_text_tlast.value=position+8>=len(raw);d.s_axis_text_tuser.value=context;d.s_axis_text_tvalid.value=1
        while True:
            await RisingEdge(d.clk)
            if int(d.s_axis_text_tready.value):break
        await FallingEdge(d.clk);d.s_axis_text_tvalid.value=0


async def send_ids(d,ids,context):
    for index,token in enumerate(ids):
        await FallingEdge(d.clk);d.s_axis_generated_tdata.value=token;d.s_axis_generated_tvalid.value=1;d.s_axis_generated_tlast.value=index+1==len(ids);d.s_axis_generated_tuser.value=context
        while True:
            await RisingEdge(d.clk)
            if int(d.s_axis_generated_tready.value):break
        await FallingEdge(d.clk);d.s_axis_generated_tvalid.value=0


async def capture_tokens(d,expected,context):
    actual=[];rng=random.Random(context);held=None
    while True:
        await FallingEdge(d.clk);d.m_axis_tokens_tready.value=rng.randrange(4)!=0
        await RisingEdge(d.clk)
        if held is not None:assert int(d.m_axis_tokens_tvalid.value)and held==(int(d.m_axis_tokens_tdata.value),int(d.m_axis_tokens_tkeep.value),int(d.m_axis_tokens_tlast.value),int(d.m_axis_tokens_tuser.value))
        held=None
        if int(d.m_axis_tokens_tvalid.value):
            data=int(d.m_axis_tokens_tdata.value);keep=int(d.m_axis_tokens_tkeep.value);last=int(d.m_axis_tokens_tlast.value);user=int(d.m_axis_tokens_tuser.value)
            if not int(d.m_axis_tokens_tready.value):held=(data,keep,last,user);continue
            assert user==context
            for lane in range(16):
                group=keep>>(lane*4)&15;assert group in(0,15)
                if group:actual.append(data>>(lane*32)&0xffffffff)
            if last:break
    assert actual==expected,(actual,expected)
    await FallingEdge(d.clk);d.m_axis_tokens_tready.value=0


async def capture_bytes(d,expected,context):
    actual=bytearray();rng=random.Random(context);held=None
    while True:
        await FallingEdge(d.clk);d.m_axis_text_tready.value=rng.randrange(4)!=0
        await RisingEdge(d.clk)
        if held is not None:assert int(d.m_axis_text_tvalid.value)and held==(int(d.m_axis_text_tdata.value),int(d.m_axis_text_tkeep.value),int(d.m_axis_text_tlast.value),int(d.m_axis_text_tuser.value))
        held=None
        if int(d.m_axis_text_tvalid.value):
            data=int(d.m_axis_text_tdata.value);keep=int(d.m_axis_text_tkeep.value);last=int(d.m_axis_text_tlast.value);user=int(d.m_axis_text_tuser.value)
            if not int(d.m_axis_text_tready.value):held=(data,keep,last,user);continue
            assert user==context
            actual.extend(data>>(lane*8)&255 for lane in range(16)if keep>>lane&1)
            if last:break
    assert actual==expected,(actual,expected)
    await FallingEdge(d.clk);d.m_axis_text_tready.value=0


async def watch_errors(d):
    while True:
        await RisingEdge(d.clk)
        if not int(d.rst.value):
            assert not int(d.forward_error_valid.value),(int(d.forward_error_stage.value),int(d.forward_error_detail.value),int(d.forward_error_status.value))
            assert not int(d.reverse_error_valid.value),int(d.reverse_error_code.value)


@cocotb.test(timeout_time=20,timeout_unit="ms")
async def host_programmed_bidirectional_tokenizer(d):
    fixture=Path(__file__).resolve().parents[2]/"build/tokenizer-engine"
    image=bytearray().join(int(line,16).to_bytes(8,"little")for line in(fixture/"memory.mem").read_text().splitlines())
    memory=Memory(d,image);cocotb.start_soon(Clock(d.clk,4,unit="ns").start());cocotb.start_soon(memory.run())
    for name in("s_axi_awaddr","s_axi_awvalid","s_axi_wdata","s_axi_wstrb","s_axi_wvalid","s_axi_bready","s_axi_araddr","s_axi_arvalid","s_axi_rready",
                 "s_axis_text_tdata","s_axis_text_tkeep","s_axis_text_tvalid","s_axis_text_tlast","s_axis_text_tuser","m_axis_tokens_tready","completion_ready",
                 "s_axis_generated_tdata","s_axis_generated_tvalid","s_axis_generated_tlast","s_axis_generated_tuser","m_axis_text_tready"):
        getattr(d,name).value=0
    d.forward_error_ready.value=1;d.reverse_error_ready.value=1;d.rst.value=1;await cycles(d,5);d.rst.value=0;await cycles(d,3)
    cocotb.start_soon(watch_errors(d));host=Host(d)
    assert await host.read(0)==0x50545831 and await host.read(0xc)==0
    await host.write(0x30,0,expected=2)
    cfg=list(map(int,(fixture/"config.txt").read_text().split()))

    async def begin_update():
        await host.write(8,1)
        for _ in range(100):
            if await host.read(4)&1:return
        raise AssertionError("No configuration grant")

    async def commit_image():
        previous=await host.read(0xc);await host.write(0x10,1);await host.write(8,8);await host.write(8,2)
        assert await host.read(0xc)==previous+1 and await host.read(4)&4

    async def run_packet(raw,ids,context):
        capture=cocotb.start_soon(capture_tokens(d,ids,context))
        reverse_capture=cocotb.start_soon(capture_bytes(d,raw,context^0x8000))if ids else None
        send=cocotb.start_soon(send_text(d,raw,context));reverse_send=cocotb.start_soon(send_ids(d,ids,context^0x8000))
        await send;await reverse_send;await capture
        if reverse_capture is not None:await reverse_capture
        while not int(d.completion_valid.value):await FallingEdge(d.clk)
        assert not int(d.completion_failed.value)and int(d.completion_count.value)==len(ids)and int(d.completion_user.value)==context
        assert not int(d.m_axis_tokens_tvalid.value)
        await cycles(d,5);d.completion_ready.value=1;await cycles(d);d.completion_ready.value=0
        while not int(d.idle.value):await FallingEdge(d.clk)

    records=[];lines=iter((fixture/"vectors.txt").read_text().splitlines())
    for header in lines:
        n,k,profile,context=map(int,header.split());raw=bytes(map(int,next(lines).split()));ids=list(map(int,next(lines).split()))
        assert len(raw)==n and len(ids)==k
        if (context-1)%91<11 and n<=512:records.append((profile,context,raw,ids))
    current_profile=None;cases=0
    for profile,context,raw,ids in records:
        if profile!=current_profile:
            await begin_update()
            if current_profile is None:
                for address,value in zip(range(0x34,0x68,4),cfg):await host.write(address,value)
                await host.write(0x68,0);await host.write(0x6c,0x100000);await host.write(0x70,0)
            await host.write(0x30,profile);await commit_image();current_profile=profile
        await run_packet(raw,ids,context);cases+=1
        if cases%9==0:d._log.info("Completed %d MMIO bidirectional reference packets",cases)
    # A changed special spelling is validated by the native reference fixture;
    # the actual replacement traverses every host and external-memory layer.
    values=list(map(int,(fixture/"reload.txt").read_text().split()));token,address,length=values[:3];old=bytes(values[3:3+length]);new=bytes(values[3+length:])
    assert image[address:address+length]==old
    capture=cocotb.start_soon(capture_bytes(d,old,0xface));await send_ids(d,[token],0xface);await capture
    await begin_update()
    for offset in range(0,length,9):
        chunk=new[offset:offset+9];word=int.from_bytes(chunk,"little")
        for register,value in [(0x18,address+offset),(0x1c,len(chunk)),(0x20,word&0xffffffff),(0x24,word>>32&0xffffffff),(0x28,word>>64)]:await host.write(register,value)
        await host.write(0x2c,1);assert await host.read(0x14)==0
    await commit_image();assert image[address:address+length]==new
    capture=cocotb.start_soon(capture_bytes(d,new,0xf00d));await send_ids(d,[token],0xf00d);await capture
    assert await host.read(0xc)==4 and not (await host.read(4))&0x60
    assert cases==27
    d._log.info("PASS: actual AXI-Lite/tokenizer integration: %d bidirectional packets, three profiles, four committed epochs, %d host writes/%d reads, full preloaded model and native-reference runtime special reload; external AXI %d refills/%d writes",cases,host.writes,host.reads,memory.reads,memory.writes)
