"""Passive ownership checks on the actual shared directory and RX client."""
from cocotb.triggers import RisingEdge
from test_http2_prefill import value


async def observe_receive_pool(d, counts):
    c = d.dut.core
    owned = c.reverse.directory_service.owned
    directory = owned.directory
    active = None
    pending = False
    while True:
        await RisingEdge(d.clk)
        if value(d, 'rst'):
            assert active is None and not pending
            continue
        b_owned = value(c, 'receive_pool_active')
        if b_owned:
            counts['receive_lock_cycles'] += 1
            assert value(directory, 'pool_state') == 3
            assert value(directory, 'pool_lock_active')
            assert not value(directory, 'req_ready') and not value(directory, 'lease_ready')
            assert (value(directory, 'locked_base'), value(directory, 'locked_bytes')) == (
                value(c, 'receive_request_pool_base'), value(c, 'receive_request_pool_bytes'))
            assert not (value(d, 'mem_valid') & value(d, 'mem_ready') & 1)
            if value(c, 'service_control_req_valid') and value(c, 'service_control_req_op') == 2:
                assert not value(c, 'service_control_req_ready')
                counts['save_blocked_cycles'] += 1
        if value(c, 'receive_pool_result_valid') and value(c, 'receive_pool_result_ready'):
            assert value(c, 'receive_pool_status') == 0
            counts['receive_grants'] += 1
        if value(c, 'receive_pool_unlock_valid') and value(c, 'receive_pool_unlock_ready'):
            assert active is None and not pending
            counts['receive_unlocks'] += 1
        if value(c, 'rx_request_valid') and value(c, 'rx_request_ready'):
            assert active is None
            active = 'init' if value(c, 'rx_request_is_init') else 'close' if value(c, 'rx_request_is_close') else 'ordinary'
            assert value(c, 'rx_backend_valid') and value(c, 'rx_backend_ready')
            assert value(c, 'rx_backend_authority'), (active, value(c, 'rx_request_op'))
            counts[active + '_commands'] += 1
        if active is not None:
            if active == 'ordinary':
                assert b_owned and not value(c, 'receive_admission_lock_active')
            elif active == 'init':
                assert value(c, 'receive_admission_owned') and value(c, 'receive_admission_lock_active')
            else:
                assert value(c, 'receive_close_owned')
                assert value(c, 'service_control_rsp_valid') and not value(c, 'service_control_rsp_ready')
        if value(d, 'mem_rsp_valid') >> 26 & value(d, 'mem_rsp_ready') >> 26 & 1:
            assert active is not None and pending
            pending = False
            counts['receive_memory_acks'] += 1
        if value(d, 'mem_valid') >> 26 & value(d, 'mem_ready') >> 26 & 1:
            assert active is not None and not pending
            pending = True
            counts['receive_memory_commands'] += 1
        if value(c, 'rx_result_valid') and value(c, 'rx_result_ready'):
            assert active is not None and not pending
            assert value(c, 'rx_result_status') == 0
            active = None


def pool_counts():
    return dict(receive_lock_cycles=0, save_blocked_cycles=0, receive_grants=0,
                receive_unlocks=0, init_commands=0, close_commands=0,
                ordinary_commands=0, receive_memory_commands=0, receive_memory_acks=0)
