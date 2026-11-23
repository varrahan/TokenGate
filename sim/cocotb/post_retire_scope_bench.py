"""Native second-connection adapter; all requests still use the real public ports."""
from h2.config import H2Configuration
from h2.connection import H2Connection
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench
from test_tokenizer_mmio import cycles


class ScopedBench(Bench):
    def __init__(self,*args):
        super().__init__(*args)
        self.other=H2Connection(H2Configuration(client_side=True,header_encoding='utf-8'))
        self.other.initiate_connection();self.other_events=[];self.other_response=bytearray()

    def observe_wire_frame(self,user,frame,raw):
        if user==0:return super().observe_wire_frame(user,frame,raw)
        assert user==1
        for event in self.other.receive_data(raw):
            kind=type(event).__name__
            if kind=='ResponseReceived':
                assert self.current['user']==1
                assert event.headers==[(':status','200'),('content-type','application/grpc+proto')]
            elif kind=='TrailersReceived':assert event.headers==[('grpc-status','0')]
            elif kind=='DataReceived':self.other_response.extend(event.data)
            self.other_events.append((kind,getattr(event,'stream_id',0)))

    def check_progress_before_positive_grant(self):
        assert self.current is not None and self.metadata_acks==(10 if self.current['ordinal']==0 else 5)
        user=self.current.get('user',0);stream=self.current['stream']
        address=self.reverse['response_progress']['base']+(self.handles[user,stream]-self.layout[13])//4
        progress=int.from_bytes(self.memory.data[address:address+32],'little')
        assert progress>>188&1 and not(progress>>187&1)

    async def other_gpu(self,token,ordinal,eos):
        self.current=dict(user=1,stream=1,ordinal=ordinal,eos=eos,format=2)
        self.response_configuration(2)
        self.set(s_axis_generated_tdata=token,s_axis_generated_tkeep=15,s_axis_generated_tlast=eos,s_axis_generated_tuser=1,
            generated_stream=1,generated_generation=self.bindings[1,1],generated_model_epoch=23,generated_schema_epoch=9,generated_ordinal=ordinal)
        await self.send('s_axis_generated_tvalid','s_axis_generated_tready')
        self.set(s_axis_generated_tdata=0xffffffff,generated_stream=0,generated_generation=0,
            cfg_response_progress_base=0x7fffff,cfg_response_progress_bytes=0,cfg_response_format=3)
        await self.terminal(0,0,0)
        while value(self.d.dut.core,'return_pending'):await cycles(self.d)
        self.current=None
