"""Real closed-context/high-water read ACK faults must not invent GOAWAY."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value
from test_tokenizer_mmio import cycles
from local_error_witness import LocalErrorWitness


class LocalErrorFaultWitness(LocalErrorWitness):
    def __init__(self, d, bench, target):
        super().__init__(d, bench)
        assert target in (0, 1)
        self.target = target

    async def observe(self):
        d = self.d
        while True:
            await RisingEdge(d.clk)
            self.clock += 1
            if value(d, 'rst'):
                continue
            if value(d, 'mem_rsp_valid') >> 27 & value(d, 'mem_rsp_ready') >> 27 & 1:
                assert self.pending is not None
                status = value(d, 'mem_rsp_status') >> (27 * 8) & 255
                assert status == (0x75 if len(self.acks) == self.target else 0)
                self.acks.append(dict(address=self.pending, clock=self.clock, status=status))
                self.pending = None
            if value(d, 'mem_valid') >> 27 & value(d, 'mem_ready') >> 27 & 1:
                assert self.pending is None and not (value(d, 'mem_write') >> 27 & 1)
                self.pending = value(d, 'mem_addr') >> (27 * 23) & 0x7fffff
                self.reads.append(dict(address=self.pending, clock=self.clock))
                assert len(self.reads) <= self.target + 1 and not value(d, 'packet_result_valid')
            if value(d, 'm_axis_tx_tvalid') and value(d, 'm_axis_tx_tdata') >> 24 & 255 == 7:
                raise AssertionError('GOAWAY used history whose actual memory ACK failed')
            if value(d, 'transport_close_valid') and value(d, 'transport_close_ready'):
                assert len(self.acks) == self.target + 1 and self.clock > self.acks[-1]['clock']
                assert not value(d, 'packet_result_valid')
                self.close_clock = self.clock
            if value(d, 'packet_result_valid') and value(d, 'packet_tag') == 3:
                assert self.close_clock is not None and self.clock > self.close_clock
                if self.packet_clock is None:
                    self.packet_clock = self.clock

    async def hold_and_close(self):
        d, b = self.d, self.b
        while True:
            await RisingEdge(d.clk)
            if not value(d, 'rst'):
                break
        await b.wait('transport_close_valid')
        fields = ('user', 'http2_error', 'last_stream', 'status', 'detail', 'memory_status')
        close = tuple(value(d, 'transport_close_' + n) for n in fields)
        assert close == (0, 1, 0, 5, self.target + 1, 0x75)
        for _ in range(13):
            await cycles(d)
            assert value(d, 'transport_close_valid') and not value(d, 'packet_result_valid')
            assert tuple(value(d, 'transport_close_' + n) for n in fields) == close
            self.held_close_cycles += 1
        b.set(transport_close_ready=1)
        await cycles(d)
        b.set(transport_close_ready=0)

    def result(self):
        base = self.b.layout[19]
        assert [r['address'] for r in self.reads] == [base, base + 160][:self.target + 1]
        assert len(self.acks) == self.target + 1 and self.acks[-1]['status'] == 0x75
        assert self.pending is None and self.wire_clock is None and self.held_close_cycles == 13
        assert self.acks[-1]['clock'] < self.close_clock < self.packet_clock
        assert value(self.d, 'fault_injected')
        return dict(actual_fault_target=self.target, actual_reads=self.reads, actual_read_acks=self.acks,
            actual_memory_error=0x75, goaway_not_offered=True, held_host_close_cycles=self.held_close_cycles,
            host_close_retired_clock=self.close_clock, first_public_packet_result_clock=self.packet_clock,
            physical_host_adapter_verified=False)
