"""Check an actual injected ACK against the successful retirement transaction prefix."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


class PostRetireFaultWitness:
    def __init__(self,d,client,phase,expected):
        self.d=d;self.client=client;self.phase=phase;self.expected=expected
        self.active=False;self.pending=None;self.acks=[]

    async def observe(self):
        d=self.d;leaf=d.dut.core.forward.prefill.parser.ingress;n=self.client
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            if value(leaf,'post_abort_valid') and value(leaf,'post_abort_ready'):
                assert not self.active
                self.active=True
            if not self.active:continue
            if value(d,'mem_rsp_valid')>>n & value(d,'mem_rsp_ready')>>n & 1:
                assert self.pending is not None
                k=len(self.acks);assert k<=self.phase
                status=value(d,'mem_rsp_status')>>(8*n)&255
                assert status==(0x75 if k==self.phase else 0)
                response=value(d,'mem_rsp_data')>>(72*n)&((1<<72)-1)
                assert response==self.expected[k]['response_data']
                self.acks.append(dict(**self.pending,status=status,response_data=response))
                self.pending=None
            if value(d,'mem_valid')>>n & value(d,'mem_ready')>>n & 1:
                assert self.pending is None
                k=len(self.acks);assert k<=self.phase
                request=dict(write=value(d,'mem_write')>>n&1,address=value(d,'mem_addr')>>(23*n)&0x7fffff,
                    bytes=value(d,'mem_bytes')>>(4*n)&15,data=value(d,'mem_data')>>(72*n)&((1<<72)-1))
                assert request=={key:self.expected[k][key] for key in request}
                self.pending=request

    def result(self):
        assert self.pending is None and len(self.acks)==self.phase+1
        return self.acks
