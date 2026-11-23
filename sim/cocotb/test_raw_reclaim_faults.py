"""Real raw/DMA reclamation, actual receive ledger and every ACK failure."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_http2_prefill import value
from test_raw_grpc_enveloped import varint
from test_raw_open_rpc_credit import RecordingBench
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


async def observe_reclaim(d, trace):
    core = d.dut.core
    active = False
    pending = None
    while True:
        await RisingEdge(d.clk)
        if value(d, 'rst'):
            assert pending is None, 'Reset abandoned an actual memory response'
            active = False
            continue
        if value(core, 'rc_start') and value(core, 'rc_start_ready'):
            assert not active
            trace['starts'] += 1
            active = True
            # rc_busy reflects the state before this start handshake. The
            # first memory command follows pool acquisition on later cycles.
            continue
        if not active:
            continue
        if value(core, 'mem_rsp_valid') >> 26 & value(core, 'mem_rsp_ready') >> 26 & 1:
            assert pending is not None
            status = value(core, 'mem_rsp_status') >> (26 * 8) & 255
            trace['responses'].append(dict(command=pending, status=status))
            pending = None
        if value(core, 'mem_valid') >> 26 & value(core, 'mem_ready') >> 26 & 1:
            assert pending is None
            command = dict(write=value(core, 'mem_write') >> 26 & 1,
                address=value(core, 'mem_addr') >> (26 * 23) & 0x7fffff,
                bytes=value(core, 'mem_bytes') >> (26 * 4) & 15,
                data=value(core, 'mem_data') >> (26 * 72) & ((1 << 72) - 1),
                owner='credit' if value(core, 'rc_credit_owner') else 'compactor')
            pending = len(trace['commands'])
            trace['commands'].append(command)
        if value(core, 'rc_credit_valid') and value(core, 'rc_credit_ready'):
            trace['credit_commands'].append(tuple(value(core, name) for name in
                ('rc_credit_op', 'rc_credit_user', 'rc_credit_stream', 'rc_credit_generation', 'rc_credit_address', 'rc_credit_amount')))
        if value(core, 'rc_result_valid') and not value(core, 'rc_recovery'):
            assert pending is None
            trace['successful_result'] = tuple(value(core, name) for name in ('rc_status', 'rc_detail', 'rc_memory_status'))
        if not value(core, 'rc_busy'):
            assert pending is None
            active = False


async def arm_reclaim_fault(d, phase):
    core = d.dut.core
    for _ in range(100000):
        await RisingEdge(d.clk)
        if value(core, 'rc_start') and value(core, 'rc_start_ready'):
            break
    else:
        raise AssertionError('No actual ACK-derived reclaim start')
    await FallingEdge(d.clk)
    if phase is not None:
        assert not value(d, 'mem_rsp_valid') >> 26 & 1
        d.fault_client.value = 26
        d.fault_target.value = phase
        d.fault_arm.value = 1
        await cycles(d)
        d.fault_arm.value = 0


@cocotb.test(timeout_time=200, timeout_unit='ms')
async def actual_reclaim_ack_faults_preserve_ownership_and_close(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    metadata = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    initial = b''.join(int(word, 16).to_bytes(8, 'little') for word in (folder / 'memory.mem').read_text().splitlines())
    assert len(initial) == 8388608 and hashlib.sha256(initial).hexdigest() == metadata['loaded_image_sha256']
    ids = [15339, 1917]
    small_body = b'\x0a\x0bhello world'
    small_record = b'\0' + len(small_body).to_bytes(4, 'big') + small_body
    # The selected text is inside the retained partial prefix, making a lost
    # or corrupted move observable in the eventual real token IDs as well.
    large_body = small_body + varint(99 << 3 | 2) + varint(8000) + b'U' * 8000
    large_record = b'\0' + len(large_body).to_bytes(4, 'big') + large_body
    batch = small_record * 2 + large_record[:128]
    assert len(small_record) == 18 and len(large_record) == 8022 and len(batch) == 164
    workers = []
    clock_task = cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())

    async def setup():
        nonlocal workers
        d.rst.value = 1
        await cycles(d, 4)
        for task in workers:
            task.cancel()
        await cycles(d, 2)
        image = bytearray(initial)
        memory = SeparateMemory(d, image)
        b = RecordingBench(d, layout, memory, reverse)
        b.set(rst=1, fault_client=-1, fault_target=-1, fault_arm=0,
            s_axis_rx_tvalid=0, s_axis_generated_tvalid=0, control_valid=0, command_valid=0,
            queue_cfg_valid=0, stream_cfg_valid=0, cfg_schema_valid=0, cfg_unlock=0,
            control_result_ready=0, rsp_ready=0, completion_ready=0,
            response_result_ready=0, m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0,
            packet_result_ready=0, maintenance_grant=1, admit_packets=1, admit_messages=1,
            rpc_error_ready=1, queue_cfg_clear=1)
        b.configure()
        trace = dict(starts=0, commands=[], responses=[], credit_commands=[])
        # SeparateMemory.run starts an unreturned child coroutine. Track both
        # physical models directly so a reset cannot leave an old AXI driver.
        workers = [cocotb.start_soon(memory.parser.run()), cocotb.start_soon(memory.tokenizer.run())]
        for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), observe_reclaim(d, trace)):
            workers.append(cocotb.start_soon(worker))
        await cycles(d, 5)
        b.set(rst=0)
        for prefix in ('queue', 'stream'):
            await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready')
            await b.wait(prefix + '_cfg_result_valid')
            assert value(d, prefix + '_cfg_status') == 0
            await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
        b.response_configuration(0)
        await b.directory(4)
        await b.open()
        await b.packet(0, 1, b.client.data_to_send(), 1)
        b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
            (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
        await b.packet(0, 2, b.client.data_to_send(), 1)
        return b, memory, image, trace

    async def begin(b, phase):
        armed = cocotb.start_soon(arm_reclaim_fault(d, phase))
        b.client.send_data(1, batch)
        await b.packet(0, 3, b.client.data_to_send(), 1)
        captured = []
        for ordinal in range(2):
            await b.drain_queued_record(ids, ordinal)
            captured.extend(b.received)
        await armed
        assert captured == ids * 2 and not b.generated_accepts
        return captured

    b, memory, image, baseline = await setup()
    captured = await begin(b, None)
    core = d.dut.core
    for _ in range(100000):
        if not value(core, 'rc_pending') and not value(core, 'rc_busy'):
            break
        await cycles(d)
    else:
        raise AssertionError(('Successful reclaim did not drain', value(core.payload_reclaimer, 'state')))
    assert baseline['starts'] == 1 and baseline['successful_result'] == (0, 0, 0)
    assert len(baseline['commands']) == len(baseline['responses']) and all(r['status'] == 0 for r in baseline['responses'])
    assert baseline['credit_commands'] == [(3, 0, 1, b.bindings[0, 1], b.handles[0, 1], 36),
        (4, 0, 1, b.bindings[0, 1], b.handles[0, 1], 0), (4, 0, 0, 0, 0, 0)]
    assert image[layout[17]:layout[17] + 123] == large_body[:123]
    progress = int.from_bytes(image[b.handles[0, 1] + 32:b.handles[0, 1] + 64], 'little')
    assert (progress & 0xffffffff, progress >> 32 & 0xffffffff, progress >> 128 & 0xffffffff, progress >> 165 & ((1 << 33) - 1)) == (123, 0, 2, 2)
    baseline_commands = list(baseline['commands'])
    baseline_credit_wire = [raw.hex() for raw in b.wire if raw[3] == 8]
    assert len(baseline_credit_wire) == 2 and b.client.outbound_flow_control_window == 65535 - 128
    # Finish the partial message through the real Parser/BPE, then echo actual
    # DMA IDs and explicitly retire the directory as the original corpus does.
    b.client.send_data(1, large_record[128:], end_stream=True)
    await b.packet(0, 4, b.client.data_to_send(), 1)
    await b.drain(0, 1, 101, ids, ordinal=2)
    captured.extend(b.received)
    expected = bytearray()
    for ordinal, token in enumerate(captured):
        await b.gpu(1, token, ordinal, int(ordinal + 1 == len(captured)), 2)
        raw = bytes.fromhex(reverse['cases'][0]['chunks'][ordinal % 2]['bow_hex'])
        payload = varint(17 << 3 | 2) + varint(len(raw)) + raw
        expected.extend(b'\0' + len(payload).to_bytes(4, 'big') + payload)
    assert bytes(b.response_records[1]) == expected and ('StreamEnded', 1) in b.client_events
    await b.directory(3, 0, 1)
    for _ in range(100000):
        if b.client.outbound_flow_control_window == 65535:
            break
        await cycles(d)
    else:
        raise AssertionError('Actual directory CLOSE did not return remaining connection credit')
    assert image[b.handles[0, 1]:b.handles[0, 1] + 8] == bytes(8)
    assert not any(b.pending) and not b.packet_bytes
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    success = dict(actual_captured_dma_ids_returned=captured, native_complete_grpc_calls=1,
        explicit_directory_close=True, final_connection_credit=65535,
        selected_text_in_compacted_partial_record_verified=True,
        actual_reclaim_commands=baseline_commands, actual_credit_commands=baseline['credit_commands'],
        actual_initial_window_updates=baseline_credit_wire,
        actual_ingress_packets=b.ingress_packets, actual_wire_frames=[raw.hex() for raw in b.wire],
        response_sha256=hashlib.sha256(expected).hexdigest())
    failures = []
    for phase in range(len(baseline_commands)):
        d._log.info('Starting reclaim memory ACK fault %d/%d', phase + 1, len(baseline_commands))
        b, memory, image, trace = await setup()
        captured = await begin(b, phase)
        for _ in range(100000):
            if value(core, 'rc_recovery') and value(d, 'receive_fault_valid'):
                break
            await cycles(d)
        else:
            raise AssertionError(('Missing actual reclaim quarantine', phase, value(core.payload_reclaimer, 'state'), trace))
        await cycles(d, 5)
        assert value(d, 'fault_injected') and value(d, 'receive_recovery_required')
        assert value(d, 'receive_fault_memory_status') == 0x75
        assert value(core, 'rc_lock_active') and value(core, 'receive_pool_active')
        assert trace['starts'] == 1 and len(trace['commands']) == len(trace['responses']) == phase + 1
        assert trace['commands'] == baseline_commands[:phase + 1]
        assert [r['status'] for r in trace['responses']] == [0] * phase + [0x75]
        assert not any(b.pending) and not b.packet_bytes and not b.generated_accepts
        updates = [raw.hex() for raw in b.wire if raw[3] == 8]
        assert updates == baseline_credit_wire[:len(updates)] and len(updates) <= 2
        assert all(raw[3] in (4, 8) for raw in b.wire), 'Fault emitted application data'
        before = len(trace['commands']), len(b.wire), len(b.generated_accepts)
        # Offer new raw/GPU/host work after the private failure. Every offer
        # remains stable until the subsequent test reset, with no acceptance.
        b.configure()
        b.set(s_axis_rx_tdata=0x1122, s_axis_rx_tkeep=3, s_axis_rx_tlast=1, s_axis_rx_tuser=0,
            s_axis_rx_tag=99, s_axis_rx_tvalid=1, s_axis_generated_tdata=15339,
            s_axis_generated_tkeep=15, s_axis_generated_tlast=1, s_axis_generated_tuser=0,
            generated_stream=1, generated_generation=b.bindings[0, 1], generated_model_epoch=23,
            generated_schema_epoch=9, generated_ordinal=0, s_axis_generated_tvalid=1,
            control_op=1, control_user=0, control_stream=1, control_valid=1)
        error = tuple(value(d, n) for n in ('receive_fault_status', 'receive_fault_detail', 'receive_fault_memory_status'))
        for _ in range(23):
            await cycles(d)
            assert not value(d, 's_axis_rx_tready') and not value(d, 's_axis_generated_tready') and not value(d, 'control_ready')
            assert value(d, 'receive_recovery_required') and value(core, 'rc_lock_active')
            assert error == tuple(value(d, n) for n in ('receive_fault_status', 'receive_fault_detail', 'receive_fault_memory_status'))
        assert before == (len(trace['commands']), len(b.wire), len(b.generated_accepts))
        assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
        failures.append(dict(phase=phase, failed_command=baseline_commands[phase], actual_error=error,
            actual_window_updates=updates, actual_commands=trace['commands'],
            actual_responses=trace['responses'], actual_credit_commands=trace['credit_commands'],
            actual_pool_retained=True, new_work_denied=True, model_prefixes_immutable=True))
        if phase % 10 == 0:
            d._log.info('Reclaim fault %d/%d: retained owner, no replay, error %s', phase + 1, len(baseline_commands), error)
    d.rst.value = 1
    await cycles(d, 4)
    for task in workers:
        task.cancel()
    clock_task.cancel()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed', success=success,
        actual_memory_ack_faults=failures, complete_original_image_bytes=len(initial),
        actual_reclaimer_and_receive_backend_executed=True, actual_prefix_compaction_verified=True,
        explicit_host_close_with_new_watermark_verified=True,
        retained_memory_reset_verified=False, native_vendor_memory=False,
        full_protocol_fault_matrix_verified=False, full_system_complete=False), indent=2) + '\n')
