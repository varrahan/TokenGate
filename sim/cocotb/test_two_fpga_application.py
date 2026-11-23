"""Full wire/DMA/return oracle over separately instantiated FPGA applications."""
import hashlib

import cocotb
from test_bidirectional_application import JointBench, run_bidirectional
from test_tokenizer_mmio_system import Memory


class AXIPorts:
    def __init__(self, dut, prefix):
        self.dut = dut
        self.prefix = prefix

    def __getattr__(self, name):
        return getattr(self.dut, self.prefix + name[6:] if name.startswith('m_axi_') else name)


class SeparateMemory:
    def __init__(self, dut, image):
        self.data = image
        self.tokenizer_data = bytearray(image)
        self.parser = Memory(AXIPorts(dut, 'p_axi_'), self.data)
        self.tokenizer = Memory(AXIPorts(dut, 't_axi_'), self.tokenizer_data)
        # Independent response timing, in addition to distinct storage objects.
        self.tokenizer.rng.seed(20261120)

    @property
    def reads(self):
        return self.parser.reads + self.tokenizer.reads

    @property
    def writes(self):
        return self.parser.writes + self.tokenizer.writes

    async def run(self):
        cocotb.start_soon(self.tokenizer.run())
        await self.parser.run()


def bench(d, layout, memory, reverse):
    return JointBench(d, layout, memory, reverse, control=d.dut.core, return_bow=d.tokenizer.inverse.bow)


def separate_memory_acceptance(memory, tested, initial):
    floor = tested.layout[6]
    assert memory.data is not memory.tokenizer_data
    assert memory.tokenizer_data[:floor] == initial[:floor], 'Tokenizer model region changed'
    assert memory.parser.reads and memory.parser.writes and memory.tokenizer.reads and memory.tokenizer.writes
    return dict(separate_parser_and_tokenizer_applications_verified=True,
        separate_memory_banks_verified=True, parser_memory_clients=13, tokenizer_memory_clients=9,
        parser_axi_refills=memory.parser.reads, parser_axi_writes=memory.parser.writes,
        tokenizer_axi_refills=memory.tokenizer.reads, tokenizer_axi_writes=memory.tokenizer.writes,
        tokenizer_model_prefix_sha256=hashlib.sha256(memory.tokenizer_data[:floor]).hexdigest(),
        independent_clock_domains_verified=False, physical_link_implemented=False)


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def separate_fpgas_raw_requests_and_actual_dma_returns(d):
    await run_bidirectional(d, bench_factory=bench, memory_factory=SeparateMemory,
                            extra_result=separate_memory_acceptance)
