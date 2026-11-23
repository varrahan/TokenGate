"""Actual raw/GPU arbitration must preserve every already offered AXIS beat."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


async def observe_promises(d, counts):
    held = {}
    probes = [('raw', d.dut.core.forward, 's_axis_rx_', ('tdata', 'tkeep', 'tlast', 'tuser'), ('s_axis_rx_tag',)),
              ('gpu', d.dut.core.reverse, 's_axis_tokens_', ('tdata', 'tkeep', 'tlast', 'tuser'),
               ('s_stream', 's_generation', 's_model_epoch', 's_schema_epoch', 's_ordinal'))]
    while True:
        await RisingEdge(d.clk)
        if value(d, 'rst'):
            held.clear()
            continue
        if value(d.dut.core, 'r_directory_valid') and value(d.dut.core, 'r_directory_ready'):
            counts['lookup_streams'].append(value(d.dut.core, 'return_stream'))
        reverse = d.dut.core.reverse; service = reverse.directory_service
        windows = service.owned.windows
        writer = d.dut.core.forward.transport.scheduler
        if value(windows, 'state') == 4:
            counts['raw_header_checks'].append(dict(
                header=value(windows, 'raw_header'), owner=value(windows, 'owner'),
                address=value(windows, 'context_address'), writer_state=value(writer, 'state'),
                writer_address=value(writer, 'record_address'), writer_user=value(writer, 'context_id'),
                writer_recovery=value(writer, 'recovery_required')))
        if value(reverse, 'frame_req_valid') and value(reverse, 'frame_req_ready'):
            grant = {n: value(reverse, n) for n in ('frame_req_stream', 'frame_req_max_bytes', 'frame_grant_bytes')}
            grant.update({n: value(service, n) for n in ('owned_window_rsp_status', 'owned_window_rsp_detail', 'owned_window_rsp_memory_status', 'owned_window_rsp_http2_error', 'frame_address', 'frame_generation')})
            for n in ('context_base', 'context_bytes', 'stream_base', 'stream_bytes', 'window_base', 'window_bytes', 'work_floor'):
                grant['saved_' + n] = value(service, 'saved_frame_cfg_' + n)
            counts['grant_trace'].append(grant)
        if value(d, 's_axis_rx_tvalid') and value(d, 's_axis_rx_tready') and value(d, 's_axis_rx_tag') == 8:
            assert counts['lookup_streams'] == [1, 3], 'Continuous raw packets overtook the pending real GPU lookup'
        for name, node, prefix, fields, extra in probes:
            valid, ready = value(node, prefix + 'tvalid'), value(node, prefix + 'tready')
            item = tuple(value(node, prefix + n) for n in fields) + tuple(value(node, n) for n in extra) if valid else None
            if name in held and item != held[name]:
                failure = dict(phase='axis_promise_violation', probe=name, held=held[name], observed=item,
                    valid=valid, ready=ready, return_pending=value(d.dut.core, 'return_pending'),
                    packet_result_valid=value(d, 'packet_result_valid'), packet_result_ready=value(d, 'packet_result_ready'))
                Path('failure.json').write_text(json.dumps(failure, indent=2) + '\n')
                raise AssertionError(f'{name} actual downstream AXIS promise changed: {failure}')
            if valid and not ready:
                counts[name + '_held_cycles'] += 1
                held[name] = item
            else:
                held.pop(name, None)
            if valid and ready: counts[name + '_handshakes'] += 1


async def exercise_duplex(d, fault_phase=None):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    image = bytearray(b''.join(int(s, 16).to_bytes(8, 'little') for s in (folder / 'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest() == manifest['loaded_image_sha256']
    initial = bytes(image); memory = SeparateMemory(d, image); b = Bench(d, layout, memory, reverse)
    b.allow_quarantine = fault_phase is not None
    counts = dict(raw_held_cycles=0, raw_handshakes=0, gpu_held_cycles=0, gpu_handshakes=0, lookup_streams=[], grant_trace=[], raw_header_checks=[])
    b.set(rst=1, fault_client=-1, fault_arm=0, s_axis_generated_tvalid=0, response_result_ready=0, m_axis_tx_tready=0,
        window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
        maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure(); workers = [cocotb.start_soon(Clock(d.clk, 4, unit='ns').start()), cocotb.start_soon(memory.run())]
    for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), observe_promises(d, counts)):
        workers.append(cocotb.start_soon(worker))
    await cycles(d, 5); b.set(rst=0)
    for prefix in ('queue', 'stream'):
        await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready'); await b.wait(prefix + '_cfg_result_valid')
        assert value(d, prefix + '_cfg_status') == 0
        await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
    await b.directory(4); await b.open(); await b.packet(0, 1, b.client.data_to_send(), 1)
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Json'), ('content-type', 'application/grpc+json'), ('te', 'trailers')])
    await b.packet(0, 2, b.client.data_to_send(), 1)
    # Hold a real completed raw result, then offer the next packet while the
    # actual forward receiver is still busy. No internal signal is forced.
    b.client.ping(b'first___'); await b.raw_fragment(3, b.client.data_to_send(), 1)
    await b.wait('packet_result_valid'); assert value(d, 'packet_tag') == 3 and value(d, 'packet_committed')
    b.phase = 'raw first beat offered behind held packet result'
    b.client.ping(b'second__'); offered = cocotb.start_soon(b.raw_fragment(4, b.client.data_to_send(), 1))
    for _ in range(8):
        await cycles(d)
        assert value(d, 'packet_result_valid') and not value(d, 'packet_result_ready')
    gpu = cocotb.start_soon(b.gpu_offer(1, 15339, 0, 1, 0))
    for _ in range(19): await cycles(d)
    assert b.generated_accepts == [(1, 15339, 0, 1)], b.generated_accepts
    assert value(d.dut.core, 'return_pending') and not value(d, 'response_record_lease_active')
    # Retire the older packet normally and let both real operations finish.
    await b.packet_result(3, 1); await offered; await gpu; await b.packet_result(4, 1)
    await b.terminal(0, 0, 0)
    while value(d.dut.core, 'return_pending'): await cycles(d)
    assert ('StreamEnded', 1) in b.client_events
    # A second real binding receives a GPU result while another raw result is
    # held. Keep later raw packets offered while results retire independently;
    # the actual LOAD must dispatch before the second packet in that train.
    b.client.send_headers(3, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Json'), ('content-type', 'application/grpc+json'), ('te', 'trailers')])
    await b.packet(0, 5, b.client.data_to_send(), 1)
    b.client.ping(b'hold____'); await b.raw_fragment(6, b.client.data_to_send(), 1)
    await b.wait('packet_result_valid'); assert value(d, 'packet_tag') == 6
    train = []
    for i in range(4):
        b.client.ping(('batch_%02d' % i).encode()); train.append(b.client.data_to_send())
    async def send_train():
        for i, packet in enumerate(train if fault_phase is None else train[:2]): await b.raw_fragment(7 + i, packet, 1)
    async def retire_train():
        retired = []
        await FallingEdge(d.clk); b.set(packet_result_ready=1)
        while len(retired) < (5 if fault_phase is None else 3):
            await RisingEdge(d.clk)
            if value(d, 'packet_result_valid') and value(d, 'packet_result_ready'):
                assert value(d, 'packet_tag') == 6 + len(retired)
                assert value(d, 'packet_user') == 0
                if fault_phase is not None and len(retired) == 2:
                    assert not value(d, 'packet_committed') and value(d, 'transport_packet_memory_status') == 0x75
                else: assert value(d, 'packet_committed')
                retired.append(value(d, 'packet_tag')); b.packets += 1
        await FallingEdge(d.clk); b.set(packet_result_ready=0)
    sending = cocotb.start_soon(send_train()); await cycles(d, 8)
    generated = cocotb.start_soon(b.gpu_offer(3, 15339, 0, 1, 0)); await cycles(d, 19)
    assert b.generated_accepts == [(1, 15339, 0, 1), (3, 15339, 0, 1)]
    retiring = cocotb.start_soon(retire_train())
    async def inject_write_fault():
        writer = d.dut.core.forward.transport.scheduler
        for _ in range(100000):
            await FallingEdge(d.clk)
            if value(writer, 'state') == 7 and counts['lookup_streams'] == [1, 3]: break
        else: raise AssertionError('Actual raw context invalidation did not start')
        assert b.pending[13] is None
        assert value(d, 'response_record_lease_active')
        b.set(fault_client=13, fault_target=fault_phase, fault_arm=1)
        await cycles(d); b.set(fault_arm=0)
    injecting = cocotb.start_soon(inject_write_fault()) if fault_phase is not None else None
    # A held GPU result deliberately retains the real directory LOAD. Let its
    # ordinary ACK run concurrently with raw retirement, rather than making
    # raw admission wait for an ACK that the test waits to send afterwards.
    async def finish_gpu():
        await b.wait('response_result_valid')
        if fault_phase is not None:
            names = ('response_result_stage', 'response_result_status', 'response_result_memory_status',
                'response_result_credit_status', 'response_result_credit_detail', 'response_result_credit_http2_error')
            expected = (16, 5, 0x75, 5, 13, 2)
            observed = tuple(value(d, n) for n in names)
            if observed != expected:
                Path('failure.json').write_text(json.dumps(dict(phase='context_fault_gpu_result',
                    fault_phase=fault_phase, expected=expected, observed=observed, counters=counts), indent=2) + '\n')
            assert observed == expected
            assert value(d, 'fault_injected') and value(d, 'response_record_lease_active')
            for _ in range(13):
                await cycles(d)
                assert value(d, 'response_result_valid') and value(d, 'response_record_lease_active')
                assert tuple(value(d, n) for n in names) == expected
            b.set(response_result_ready=1); await cycles(d); b.set(response_result_ready=0)
            return
        if value(d, 'response_result_stage') or value(d, 'response_result_status'):
            names = ('response_result_stage', 'response_result_status', 'response_result_memory_status',
                'response_result_stream', 'response_result_generation', 'response_result_credit_status',
                'response_result_credit_detail', 'response_result_credit_http2_error')
            diagnostic = dict(phase='duplex_gpu_error', result={n: value(d, n) for n in names}, counters=counts)
            Path('failure.json').write_text(json.dumps(diagnostic, indent=2) + '\n')
        await b.terminal(0, 0, 0)
    terminal = cocotb.start_soon(finish_gpu())
    tasks = (sending, generated, retiring, terminal)
    for _ in range(100000):
        if all(task.done() for task in tasks): break
        await cycles(d)
    else:
        diagnostic = dict(phase='duplex_train_completion_timeout', counters=counts,
            packet_tag=value(d, 'packet_tag'), packet_result_valid=value(d, 'packet_result_valid'),
            gpu_result_valid=value(d, 'response_result_valid'), gpu_result_ready=value(d, 'response_result_ready'),
            load_active=value(d, 'response_record_lease_active'), return_pending=value(d.dut.core, 'return_pending'))
        Path('failure.json').write_text(json.dumps(diagnostic, indent=2) + '\n')
        raise AssertionError(diagnostic)
    for task in tasks: await task
    if injecting is not None: await injecting
    while value(d.dut.core, 'return_pending'): await cycles(d)
    if fault_phase is not None:
        for _ in range(100000):
            if value(d, 'fabric_idle') and not any(b.pending): break
            await cycles(d)
        else: raise AssertionError('Actual context/return memory owners did not drain after fault ACK')
        raw_header = int.from_bytes(image[layout[19]:layout[19] + 8], 'little')
        # The actual raw error owner may already have completed its validated
        # CLOSE after the GPU ACK. Accept that explicit recovery, or quarantine;
        # an active unquarantined connection is never acceptable.
        recovery = dict(transport=value(d, 'transport_recovery_required'),
            windows=value(d, 'window_recovery_required'), header=raw_header)
        assert recovery['windows'] or raw_header == 0, recovery
        assert not value(d, 'response_record_lease_active') and not b.packet_bytes
        assert not any(raw[3] == 0 and int.from_bytes(raw[5:9], 'big') == 3 for raw in b.wire)
        assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data == initial
        result = dict(fault_phase=fault_phase, actual_error=0x75, credit_error_propagated=True,
            held_gpu_result_retained_actual_load=True, actual_load_released_after_gpu_ack=True,
            no_failed_stream_data_granted=True, actual_memory_owners_drained=True,
            cold_memory_initialization=True, final_recovery=recovery, **counts)
        for worker in workers: worker.cancel()
        d._log.info('Verified actual concurrent context write ACK fault %d', fault_phase)
        return result
    assert ('StreamEnded', 3) in b.client_events and counts['lookup_streams'] == [1, 3]
    expected_pings = [b'first___', b'second__', b'hold____'] + [('batch_%02d' % i).encode() for i in range(4)]
    assert [packet[9:] for packet in b.wire if packet[3] == 6 and packet[4] & 1] == expected_pings
    assert sum(name == 'PingAckReceived' for name, _ in b.client_events) == 7
    decoded = bytes.fromhex(reverse['cases'][0]['chunks'][0]['bow_hex']).decode()
    body = json.dumps({'choices': [{'delta': {'content': decoded}}]}, ensure_ascii=False, separators=(',', ':')).encode()
    expected_response = b'\0' + len(body).to_bytes(4, 'big') + body
    for stream in (1, 3): assert bytes(b.response_records[stream]) == expected_response
    assert counts['gpu_handshakes'] == 2 and counts['raw_held_cycles'] > 0 and not value(d, 'response_recovery_required')
    assert not any(b.pending) and not b.packet_bytes and not value(d, 'response_record_lease_active')
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    result = dict(phase='passed', actual_downstream_axis_promises_verified=True, **counts,
        actual_raw_packets=b.packets, actual_header_bindings=b.headers, actual_gpu_descriptors=2,
        held_prior_packet_result_during_gpu_arrival=True, actual_native_ping_acks=7,
        actual_native_completed_grpc_calls=2, byte_exact_rpc_responses_verified=True,
        pending_lookup_precedes_later_raw_packets=True, complete_model_prefix_immutable=True,
        forward_dma_workload_verified=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
    d._log.info('PASS: %s', result)
    for worker in workers: worker.cancel()
    return result


@cocotb.test(timeout_time=5, timeout_unit='ms')
async def actual_duplex_first_beat_promises_survive_gpu_arrival(d):
    await exercise_duplex(d)
