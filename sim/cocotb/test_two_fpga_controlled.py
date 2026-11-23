"""Full raw/DMA/framed-return workload with controls before HPACK dispatch."""
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge
from test_bidirectional_application import run_bidirectional
from test_two_fpga_application import SeparateMemory
from test_two_fpga_framed import FramedJointBench, acceptance as framed_acceptance


class ControlledBench(FramedJointBench):
    def __init__(self,*args):
        super().__init__(*args)
        self.flow_count=self.flow_stalls=self.flow_data_begins=0
        self.flow_updates=[]

    async def flow_ready(self):
        rng=random.Random(20261122)
        while True:
            await FallingEdge(self.d.clk)
            self.d.flow_event_ready.value=not int(self.d.rst.value) and self.clocks%47>=21 and rng.randrange(4)!=0

    async def ready_driver(self):
        cocotb.start_soon(self.flow_ready())
        await super().ready_driver()

    async def flow_observer(self):
        fields=('kind','data','arg0','arg1','length','type','flags','stream','user')
        held=None
        while True:
            await RisingEdge(self.d.clk)
            if int(self.d.rst.value):held=None;continue
            valid,ready=int(self.d.flow_event_valid.value),int(self.d.flow_event_ready.value)
            event=tuple(int(getattr(self.d,'flow_event_'+n).value)for n in fields)if valid else None
            if held is not None:assert event==held,'Full-parser flow metadata changed under backpressure'
            held=event if valid and not ready else None
            if valid:
                if not ready:self.flow_stalls+=1
                else:
                    self.flow_count+=1
                    kind,_,arg0,_,length,typ,flags,stream,user=event
                    if kind==0 and typ==0:self.flow_data_begins+=1
                    if kind==7:
                        assert self.credit_paused and int(self.d.response_record_lease_active.value)
                        assert length==4 and typ==8 and flags==0
                        self.flow_updates.append([user,stream,arg0])

    async def response_observer(self):
        cocotb.start_soon(self.flow_observer())
        await super().response_observer()


def acceptance(memory,tested,initial):
    result=framed_acceptance(memory,tested,initial)
    assert tested.flow_count>0 and tested.flow_stalls>0 and tested.flow_data_begins>0
    assert tested.flow_updates==[[0,0,101],[0,1,37]]
    result.update(full_metadata_control_fork_integrated=True,full_metadata_window_updates=tested.flow_updates,
        flow_control_events=tested.flow_count,flow_control_stall_cycles=tested.flow_stalls,
        flow_data_frame_begins=tested.flow_data_begins)
    return result


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def raw_requests_dma_framed_returns_and_ordered_full_controls(d):
    await run_bidirectional(d,bench_factory=ControlledBench,memory_factory=SeparateMemory,extra_result=acceptance)
