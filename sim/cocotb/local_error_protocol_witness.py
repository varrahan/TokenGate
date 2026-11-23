"""Hold the actual GOAWAY and host close for a native-reference error code."""
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from local_error_witness import LocalErrorWitness
from test_http2_prefill import value
from test_tokenizer_mmio import cycles


class LocalProtocolErrorWitness(LocalErrorWitness):
    def __init__(self, d, bench, error):
        super().__init__(d, bench)
        self.error = error

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
        expected = b'\0\0\x08\x07\0\0\0\0\0' + (1).to_bytes(4, 'big') + self.error.to_bytes(4, 'big')
        assert offered[1:] == (0x1ffff, 1, 0)
        assert offered[0].to_bytes(64, 'little')[:17] == expected
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
        assert close == (0, self.error, 1, 0, 0, 0)
        for _ in range(13):
            await cycles(d)
            assert value(d, 'transport_close_valid') and not value(d, 'packet_result_valid')
            assert tuple(value(d, 'transport_close_' + n) for n in fields) == close
            self.held_close_cycles += 1
        b.set(transport_close_ready=1)
        await cycles(d)
        b.set(transport_close_ready=0)

    def result(self):
        result = super().result()
        result['actual_goaway_and_host_close_http2_error'] = self.error
        return result
