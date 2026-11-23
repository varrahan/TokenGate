"""Keep precise diagnostics if a late semantic error bypasses fatal cleanup."""
import json
from pathlib import Path

from local_error_protocol_witness import LocalProtocolErrorWitness
from test_http2_prefill import value


class LocalSemanticErrorWitness(LocalProtocolErrorWitness):
    def __init__(self, d, bench, error, name):
        super().__init__(d, bench, error)
        self.name = name

    def diagnostic(self, phase):
        d, b, c = self.d, self.b, self.d.dut.core
        address = b.handles.get((0,1), b.layout[13])
        return dict(phase=phase,case=self.name,expected_http2_error=self.error,
            actual_packet_status=value(d,'packet_status'),actual_packet_committed=value(d,'packet_committed'),
            actual_packet_http2_error=value(d,'transport_packet_http2_error'),
            actual_control_status=value(d,'packet_control_status'),actual_control_detail=value(d,'packet_control_detail'),
            actual_control_memory_status=value(d,'packet_control_memory_status'),
            actual_forward_state=value(c.forward,'state'),actual_shutdown_state=value(c.shutdown,'state'),
            actual_shutdown_busy=value(c,'shutdown_busy'),actual_shutdown_recovery_required=value(d,'shutdown_recovery_required'),
            actual_abort_state=value(c.local_return_abort,'state'),actual_freeze_owner=value(c,'local_freeze_owner'),
            actual_window_owner=value(c,'window_owner'),actual_connection_closing=value(c,'receive_connection_closing'),
            actual_gpu_lease=value(d,'response_record_lease_active'),actual_return_pending=value(c,'return_pending'),
            actual_credit_parked=value(d,'credit_parked'),actual_raw_context_header_hex=b.memory.data[b.layout[19]:b.layout[19]+8].hex(),
            actual_rpc_header_hex=b.memory.data[address:address+8].hex(),actual_rpc_address=address,
            actual_wire_types=[p[3] for p in b.wire],full_system_complete=False)

    async def observe(self):
        try:
            await super().observe()
        except AssertionError:
            Path('failure.json').write_text(json.dumps(self.diagnostic('late_semantic_error_completion_order_failure'),indent=2)+'\n')
            raise

    async def hold_and_close(self):
        try:
            await super().hold_and_close()
        except AssertionError:
            Path('failure.json').write_text(json.dumps(self.diagnostic('late_semantic_error_wire_or_close_failure'),indent=2)+'\n')
            raise
