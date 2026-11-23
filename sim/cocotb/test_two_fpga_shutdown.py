"""Full raw request/return workload on the actual shutdown-capable join."""
import cocotb
from test_bidirectional_application import run_bidirectional
from test_two_fpga_application import SeparateMemory
from test_two_fpga_classified import ClassifiedBench,acceptance as classified_acceptance
from test_http2_prefill import value


class ShutdownBench(ClassifiedBench):
    def __init__(self,*args):
        super().__init__(*args);self.internal_retirement_cycles=0;self.clear_grace=0
    def check_return_owner(self):
        d=self.d;pending=bool(value(self.control,'return_pending'))
        actual_lease=value(d,'response_record_lease_active');buffered_ack=value(d,'response_result_retirement_pending')
        if self.gpu_owned:assert pending
        if not pending:assert not actual_lease and not buffered_ack
        else:
            assert not value(d,'cfg_quiescent')
            if not self.gpu_owned:
                self.internal_retirement_cycles+=1
                assert not any(value(d,n)for n in('s_axis_generated_tready','command_ready','stream_cfg_ready','queue_cfg_ready','cfg_schema_ready'))
        # An ACK may outlive the public GPU owner, but once the actual owners
        # have retired the parent must release admission promptly.
        if pending and not self.gpu_owned and not actual_lease and not buffered_ack:
            self.clear_grace+=1;assert self.clear_grace<=3
        else:self.clear_grace=0


def acceptance(memory,tested,initial):
    result=classified_acceptance(memory,tested,initial)
    result.update(actual_shutdown_return_joined=True,cancellation_supplied_externally=False,
        actual_internal_retirement_cycles=tested.internal_retirement_cycles,
        raw_reset_cases_in_this_workload=0,raw_goaway_cases_in_this_workload=0,
        full_system_complete=False)
    return result


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def full_raw_requests_and_dma_returns_use_actual_shutdown_join(d):
    await run_bidirectional(d,bench_factory=ShutdownBench,memory_factory=SeparateMemory,extra_result=acceptance)
