"""Capture real admission-window requests/results and retained record bytes."""
import json
from pathlib import Path
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


class RetainedWindowWitness:
    def __init__(self,d,b):self.d=d;self.b=b;self.events=[];self.clock=0

    async def observe(self):
        d=self.d;c=d.dut.core
        while True:
            await RisingEdge(d.clk);self.clock+=1
            if value(d,'rst'):continue
            if value(c,'window_owner') not in (1,2):continue
            event=None
            if value(c,'service_window_req_valid') and value(c,'service_window_req_ready'):
                event=dict(event='actual_admission_window_request',clock=self.clock,
                    **{n:value(c,'service_window_req_'+n) for n in ('op','user','stream','generation','record_address')})
                if event['op']==1:
                    address=self.b.window_base+(event['record_address']-self.b.layout[13])//8
                    event.update(window_address=address,retained_window_hex=bytes(self.b.memory.data[address:address+16]).hex())
            if value(c,'service_window_rsp_valid') and value(c,'service_window_rsp_ready'):
                event=dict(event='actual_admission_window_result',clock=self.clock,
                    **{n:value(c,'service_window_rsp_'+n) for n in ('status','detail','memory_status')})
            if event:
                self.events.append(event)
                Path('window_trace.json').write_text(json.dumps(self.events,indent=2)+'\n')
