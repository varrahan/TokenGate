"""Full raw ingress/actual DMA return with Tokenizer-owned real memory fabric."""
import cocotb
from test_bidirectional_application import JointBench, run_bidirectional
from test_two_fpga_application import SeparateMemory, separate_memory_acceptance


def bench(d, layout, memory, reverse):
    return JointBench(d, layout, memory, reverse, control=d.dut.core,
                      return_bow=d.tokenizer.application.inverse.bow)


def acceptance(memory, tested, initial):
    result = separate_memory_acceptance(memory, tested, initial)
    assert int(tested.d.tokenizer.memory_idle.value)
    result.update(tokenizer_memory_fabric_integrated=True, tokenizer_local_memory_clients=9,
                  tokenizer_physical_memory_controller_verified=False)
    return result


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def tokenizer_memory_raw_requests_and_actual_dma_returns(d):
    await run_bidirectional(d, bench_factory=bench, memory_factory=SeparateMemory, extra_result=acceptance)
