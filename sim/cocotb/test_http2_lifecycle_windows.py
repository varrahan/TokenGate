"""Retain actual RPC bindings after send closure, including every close fault.

The first 28 commands use native hyper-h2 goldens. Closure-specific expectations
follow RFC 9113 sections 5.1 and 6.9.2: the send side is no longer active while
the actual binding may still be retained for GPU cleanup. No raw closing frame
or full HTTP/2 controller is instantiated here.
"""
import hashlib
import json
import os
from pathlib import Path
import struct

import cocotb
from cocotb.clock import Clock
from test_tokenizer_mmio import cycles
from test_http2_owned_windows import Bench, Memory


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def retained_binding_send_closure_and_all_close_faults(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text())
    image = (folder / 'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    memory = Memory(d, image, reference['layout'])
    b = Bench(d, memory, reference['layout'])
    b.set(rst=1, req_valid=0, rsp_ready=0, lease_valid=0, lease_rsp_ready=0,
          window_req_valid=0, window_rsp_ready=0)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    await b.fresh()
    for case in reference['cases']:
        if case.get('open'):
            await b.directory(0, case['stream'])
        result = await b.window(case['op'], case['stream'], case['amount'], status=case['status'])
        if not case.get('recovery'):
            for output, key in (('rsp_grant_bytes', 'grant'), ('rsp_connection_window', 'connection_window'),
                                ('rsp_initial_window', 'initial_window'), ('rsp_stream_window', 'stream_window'),
                                ('rsp_max_frame_bytes', 'max_frame'), ('rsp_affected_streams', 'affected')):
                assert result[output] == case[key] & 0xffffffff, ('Native h2', case, output, result)

    await b.fresh()
    await b.window(0)
    for stream in (1, 3, 5):
        await b.directory(0, stream)
        await b.window(1, stream)
    maximum = 0x7fffffff
    await b.window(2, 1, maximum - 65535)
    await b.lease(1)
    old_address = b.addresses[1]
    window_address = b.a['window_base'] + (old_address - b.a['stream_base']) // 8
    actual_binding = bytes(memory.data[old_address:old_address + 128])
    before = len(memory.trace)
    result = await b.window(8, 1)
    close_phases = memory.count[1] - sum(e['client'] == 1 for e in memory.trace[:before])
    assert close_phases == 14 and result['rsp_stream_window'] == maximum
    assert memory.data[window_address + 15] & 0x80
    assert bytes(memory.data[old_address:old_address + 128]) == actual_binding
    assert int(d.lease_rsp_valid.value) and int(d.lease_rsp_generation.value) == 101

    # Idempotent closure and ignored late positive WINDOW_UPDATE cannot reset
    # the window, mint credits, or overflow a retained closed MAX_INT window.
    for op, amount, status in ((8, 0, 0), (2, 100, 0), (5, 100, 8)):
        before = len(memory.trace)
        result = await b.window(op, 1, amount, status=status)
        assert not any(e['client'] == 1 and e['write'] for e in memory.trace[before:])
        assert result['rsp_stream_window'] == maximum and result['rsp_connection_window'] == 65535
        if op == 5:
            assert result['rsp_http2_error'] == 5 and not result['rsp_connection_error']
    result = await b.window(3, amount=70000)
    assert result['rsp_affected_streams'] == 2 and result['rsp_connection_window'] == 65535
    for stream in (3, 5):
        result = await b.window(6, stream)
        assert result['rsp_stream_window'] == 70000
    result = await b.window(6, 1)
    assert result['rsp_stream_window'] == maximum
    # Generic directory SAVE must preserve the separate closed-window arena.
    closed_record = bytes(memory.data[window_address:window_address + 16])
    await b.directory(2, 1)
    assert bytes(memory.data[window_address:window_address + 16]) == closed_record
    await b.retire('lease_rsp_ready')
    # The real directory reuses the freed physical slot with a new generation.
    await b.directory(3, 1)
    await b.directory(0, 7)
    assert b.addresses[7] == old_address
    await b.window(1, 7)
    assert not memory.data[window_address + 15] & 0x80
    result = await b.window(5, 7, 1)
    assert result['rsp_grant_bytes'] == 1 and result['rsp_stream_window'] == 69999
    for op, stream, patch, status in ((8, 0, {}, 2), (9, 0, {}, 2),
                                      (8, 7, {'req_generation': 101}, 3)):
        before = len(memory.trace)
        await b.window(op, stream, patch=patch, status=status)
        assert not any(e['client'] == 1 and e['write'] for e in memory.trace[before:])

    # Every read and the final physical close write may fail. In particular,
    # the BFM applies the write before its error ACK: no optimistic retry may
    # reinterpret that uncertain completion as a reusable active stream.
    for fault in range(close_phases):
        await b.fresh()
        await b.window(0)
        await b.directory(0, 1)
        await b.window(1, 1)
        memory.fail_client = 1
        memory.fail_at = memory.count[1] + fault
        await b.window(8, 1, status=5, retire=False)
        assert int(d.window_recovery_required.value) and int(d.directory_pool_lock_active.value)
        await b.retire('window_rsp_ready')
        while int(d.window_busy.value):
            await cycles(d)
        before = memory.count[1]
        await b.window(5, 1, 1, status=6)
        assert memory.count[1] == before
        memory.fail_client = -1
        await b.window(7)
        assert not int(d.window_recovery_required.value)
    await cycles(d, 4)
    assert int(d.idle.value) and not any(memory.pending)
    assert memory.data[:b.a['work_floor']] == image[:b.a['work_floor']]
    accepted = dict(phase='passed', native_window_commands=len(reference['cases']),
        total_window_commands=b.commands, close_memory_phases=close_phases, injected_close_faults=close_phases,
        actual_directory_allocation_verified=True, actual_pool_authority_verified=True,
        retained_closed_binding_verified=True, closed_max_window_settings_skip_verified=True,
        active_settings_affected_streams=2, idempotent_close_verified=True, late_positive_update_ignored=True,
        closed_data_grant_rejected=True, real_generation_reuse_reopens_window=True,
        model_prefix_immutable=True, actual_closing_wire_frame_integrated=False,
        actual_framer_grants_integrated=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
    d._log.info('PASS: %s', accepted)
