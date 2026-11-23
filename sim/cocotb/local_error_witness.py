"""Observe actual history reads, held GOAWAY and external close retirement."""
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from test_http2_prefill import value
from test_tokenizer_mmio import cycles


class LocalErrorWitness:
    def __init__(self, d, bench):
        self.d, self.b = d, bench
        self.clock = 0
        self.pending = None
        self.reads = []
        self.acks = []
        self.wire_clock = self.close_clock = self.packet_clock = None
        self.held_wire_cycles = self.held_close_cycles = 0
        bench.set(transport_close_ready=0)

    async def observe(self):
        d = self.d
        while True:
            await RisingEdge(d.clk)
            self.clock += 1
            if value(d, 'rst'):
                continue
            if value(d, 'mem_rsp_valid') >> 27 & value(d, 'mem_rsp_ready') >> 27 & 1:
                assert self.pending is not None
                assert value(d, 'mem_rsp_status') >> (27 * 8) & 255 == 0
                self.acks.append(dict(address=self.pending, clock=self.clock,
                    data=value(d, 'mem_rsp_data') >> (27 * 72) & ((1 << 64) - 1)))
                self.pending = None
            if value(d, 'mem_valid') >> 27 & value(d, 'mem_ready') >> 27 & 1:
                assert self.pending is None and not (value(d, 'mem_write') >> 27 & 1)
                assert value(d, 'mem_bytes') >> (27 * 4) & 15 == 8
                self.pending = value(d, 'mem_addr') >> (27 * 23) & 0x7fffff
                self.reads.append(dict(address=self.pending, clock=self.clock))
                assert not value(d, 'packet_result_valid')
            if value(d, 'm_axis_tx_tvalid') and value(d, 'm_axis_tx_tready') and value(d, 'm_axis_tx_tdata') >> 24 & 255 == 7:
                assert len(self.acks) == 2 and self.clock > self.acks[-1]['clock']
                assert not value(d, 'transport_close_valid') and not value(d, 'packet_result_valid')
                assert not value(d.dut.core, 'return_pending')
                self.wire_clock = self.clock
            if value(d, 'transport_close_valid') and value(d, 'transport_close_ready'):
                assert self.wire_clock is not None and self.clock > self.wire_clock
                assert not value(d, 'packet_result_valid')
                self.close_clock = self.clock
            if value(d, 'packet_result_valid') and value(d, 'packet_tag') == 3:
                assert self.close_clock is not None and self.clock > self.close_clock
                if self.packet_clock is None:
                    self.packet_clock = self.clock

    async def hold_and_close(self):
        d, b = self.d, self.b
        while True:
            await FallingEdge(d.clk)
            await Timer(1, unit='ns')
            if not value(d, 'rst') and value(d, 'm_axis_tx_tvalid') and value(d, 'm_axis_tx_tdata') >> 24 & 255 == 7:
                break
        b.ready_wire = False
        d.m_axis_tx_tready.value = 0
        fields = ('tdata', 'tkeep', 'tlast', 'tuser')
        offered = tuple(value(d, 'm_axis_tx_' + n) for n in fields)
        assert offered[1:] == (0x1ffff, 1, 0)
        for _ in range(17):
            await RisingEdge(d.clk)
            assert value(d, 'm_axis_tx_tvalid') and not value(d, 'm_axis_tx_tready')
            assert tuple(value(d, 'm_axis_tx_' + n) for n in fields) == offered
            assert not value(d, 'transport_close_valid') and not value(d, 'packet_result_valid')
            self.held_wire_cycles += 1
        b.ready_wire = True
        while not value(d, 'transport_close_valid'):
            await FallingEdge(d.clk)
        fields = ('user', 'http2_error', 'last_stream', 'status', 'detail', 'memory_status')
        close = tuple(value(d, 'transport_close_' + n) for n in fields)
        assert close == (0, 1, 1, 0, 0, 0)
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
        assert [r['address'] for r in self.reads] == [base, base + 160]
        assert [r['address'] for r in self.acks] == [base, base + 160]
        assert [r['data'] for r in self.acks] == [0, (1 << 32) | 0x48325731]
        assert self.pending is None and self.held_wire_cycles == 17 and self.held_close_cycles == 13
        assert self.acks[-1]['clock'] < self.wire_clock < self.close_clock < self.packet_clock
        return dict(actual_reads=self.reads, actual_read_acks=self.acks,
            held_goaway_cycles=self.held_wire_cycles, held_host_close_cycles=self.held_close_cycles,
            wire_retired_clock=self.wire_clock, host_close_retired_clock=self.close_clock,
            first_public_packet_result_clock=self.packet_clock,
            actual_highwater_and_closed_marker_verified=True, physical_host_adapter_verified=False)
