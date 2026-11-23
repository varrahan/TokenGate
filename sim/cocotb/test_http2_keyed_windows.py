"""Wire keys resolve real generations under actual pool ownership."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from test_http2_owned_windows import Bench, Memory
from test_tokenizer_mmio import cycles


async def keyed(b, stream, increment, *, status=0, retire=True):
    return await b.window(9, stream, increment, status=status, retire=retire,
        patch={'req_generation': 0, 'req_record_address': 0})


async def foreign_open(b):
    b.set(cfg_pool_base=b.a['stream_base'], cfg_pool_bytes=b.a['stream_bytes'], req_op=0,
        req_user=1, req_application=777, req_stream=1, req_generation=900, req_address=0,
        req_buffer_base=0x740800, req_buffer_bytes=256, req_message_limit=256,
        req_protobuf=0, req_unsupported_encoding=0, req_maintenance=0, req_state=0)
    await b.send('req_valid', 'req_ready'); await b.wait('rsp_valid')
    assert int(b.d.rsp_status.value) == 0 and int(b.d.rsp_address.value) == b.a['stream_base']
    await b.retire('rsp_ready')


async def prepare_search(b):
    await b.fresh(); await foreign_open(b)
    await b.directory(0, 3); await b.directory(0, 1)
    assert b.addresses[1] == b.a['stream_base'] + 256
    await b.window(0); await b.window(1, 1); await b.window(1, 3)


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def actual_keyed_updates_generation_reuse_and_every_search_fault(d):
    folder = Path(os.environ['PARSER_HTTP2_SEND_WINDOW_FIXTURES'])
    reference = json.loads((folder / 'cases.json').read_text()); image = (folder / 'model.bin').read_bytes()
    assert hashlib.sha256(image).hexdigest() == reference['original_image_sha256']
    m = Memory(d, image, reference['layout']); b = Bench(d, m, reference['layout'])
    b.set(rst=1, req_valid=0, rsp_ready=0, lease_valid=0, lease_rsp_ready=0, window_req_valid=0, window_rsp_ready=0)
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()); cocotb.start_soon(m.run())
    await b.fresh()
    native_updates = 0
    # Every native WINDOW_UPDATE now uses no caller address/generation.
    for case in reference['cases']:
        if case.get('open'): await b.directory(0, case['stream'])
        if case['op'] == 2:
            result = await keyed(b, case['stream'], case['amount'], status=case['status']); native_updates += 1
        else:
            result = await b.window(case['op'], case['stream'], case['amount'], status=case['status'])
        if not case.get('recovery'):
            for output, key in (('rsp_grant_bytes', 'grant'), ('rsp_connection_window', 'connection_window'),
                ('rsp_initial_window', 'initial_window'), ('rsp_stream_window', 'stream_window'),
                ('rsp_max_frame_bytes', 'max_frame'), ('rsp_affected_streams', 'affected')):
                assert result[output] == case[key] & 0xffffffff, ('Native keyed WINDOW_UPDATE', case, output, result)

    await prepare_search(b)
    foreign = bytes(m.data[b.a['stream_base']:b.a['stream_base'] + 128])
    before = m.count[1]; result = await keyed(b, 1, 37)
    search_phases = m.count[1] - before
    assert search_phases == 22 and result['rsp_stream_window'] == 65572
    assert bytes(m.data[b.a['stream_base']:b.a['stream_base'] + 128]) == foreign
    assert m.data[b.a['window_base']:b.a['window_base'] + 16] == bytes(16), 'Foreign same-number stream gained credits'
    await b.lease(1)
    cached = tuple(int(getattr(d, n).value) for n in ('lease_rsp_user', 'lease_rsp_stream', 'lease_rsp_generation', 'lease_rsp_address'))
    await keyed(b, 1, 1, retire=False)
    opening = cocotb.start_soon(b.directory(0, 5)); lookup = cocotb.start_soon(b.lease(3))
    await b.retire('lease_rsp_ready')
    before_trace = len(m.trace)
    for _ in range(40):
        await cycles(d)
        assert int(d.directory_pool_lock_active.value) and not int(d.req_ready.value) and not int(d.lease_ready.value)
        assert len(m.trace) == before_trace
    await b.retire('window_rsp_ready')
    await opening; await lookup; await b.retire('lease_rsp_ready')
    assert cached == (0, 1, 101, b.addresses[1])
    result = await keyed(b, 127, 10, status=3)
    assert result['rsp_detail'] == 10 and result['rsp_http2_error'] == 0 and not result['rsp_connection_error']
    assert not int(d.window_recovery_required.value), 'Missing key invented protocol classification'
    before = m.count[1]
    await b.window(9, 1, 1, status=2)
    assert m.count[1] == before, 'Key-only command accepted caller binding metadata'
    for stream, amount in ((0, 0), (1, 0), (1, 0x80000000)):
        before = m.count[1]; await keyed(b, stream, amount, status=4)
        assert m.count[1] == before
    await keyed(b, 1, 0x7fffffff - 65573)
    await b.window(8, 1)
    before = len(m.trace); result = await keyed(b, 1, 100)
    assert result['rsp_stream_window'] == 0x7fffffff and not any(e['client'] == 1 and e['write'] for e in m.trace[before:])
    old_address = b.addresses[1]
    await b.directory(3, 1); await b.directory(0, 7)
    assert b.addresses[7] == old_address
    await b.window(1, 7); result = await keyed(b, 7, 9)
    assert result['rsp_stream_window'] == 65544
    result = await keyed(b, 1, 1, status=3)
    assert result['rsp_detail'] == 10

    for fault in range(search_phases):
        await prepare_search(b)
        m.fail_client = 1; m.fail_at = m.count[1] + fault
        result = await keyed(b, 1, 37, status=5, retire=False)
        assert result['rsp_memory_status'] == 0x75 and int(d.window_recovery_required.value)
        failed = [e for e in m.trace if e['client'] == 1 and e['status'] == 0x75][-1]
        assert int(d.window_recovery_address.value) == failed['address']
        assert int(d.directory_pool_lock_active.value)
        await b.retire('window_rsp_ready')
        while int(d.window_busy.value): await cycles(d)
        m.fail_client = -1; before = m.count[1]
        await keyed(b, 1, 1, status=6)
        assert m.count[1] == before
        await b.window(7); assert not int(d.window_recovery_required.value)
    await cycles(d, 4)
    assert int(d.idle.value) and not any(m.pending)
    assert m.data[:b.a['work_floor']] == image[:b.a['work_floor']]
    accepted = dict(phase='passed', native_window_commands=len(reference['cases']), native_keyed_updates=native_updates,
        total_window_commands=b.commands, actual_directory_allocation_verified=True, actual_pool_authority_verified=True,
        searched_records_before_target=2, foreign_same_stream_untouched=True, held_result_excludes_open_and_load=True,
        retained_closed_update_ignored=True, real_generation_reuse_verified=True,
        missing_key_classification_deferred=True, caller_binding_metadata_rejected=True,
        search_memory_phases=search_phases, injected_search_faults=search_phases,
        model_prefix_immutable=True, raw_http2_control_integrated=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n'); d._log.info('PASS: %s', accepted)
