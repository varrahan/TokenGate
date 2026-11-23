"""Observe the private grant during actual send-ledger clear memory commands."""
import cocotb
from cocotb.triggers import RisingEdge
from test_http2_prefill import value
from window_format_witness import WindowFormatWitness


class PrivateWindowFormatWitness(WindowFormatWitness):
    def __init__(self,d):super().__init__(d);self.private_commands=0

    async def observe_private_authority(self):
        d=self.d;c=d.dut.core;owned=c.reverse.directory_service.owned
        while True:
            await RisingEdge(d.clk)
            if value(d,'rst'):continue
            if value(c,'rx_format_pending') and value(d,'mem_valid')>>22 & value(d,'mem_ready')>>22 & 1:
                assert value(owned.windows,'format_authority') and value(owned,'saved_req_global_format')
                assert value(owned.windows,'op')==12 and value(c,'window_owner')==12
                assert value(c,'rx_format_complete') and value(c,'rx_init_status')==0
                self.private_commands+=1

    async def observe(self):
        cocotb.start_soon(self.observe_private_authority())
        await super().observe()

    def result(self):
        result=super().result()
        assert self.private_commands==sum(len(r['commands']['22']) for r in result)
        return result
