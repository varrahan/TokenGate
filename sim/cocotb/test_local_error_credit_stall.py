"""A fatal connection cancels a genuinely parked GPU return without new credit."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'native-vendor'))
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from h2.settings import SettingCodes
from local_error_witness import LocalErrorWitness
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench, varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory

FAULT_TARGET = None


async def verify_uncertain_fatal_close(d, b, image, memory, initial, before, command_start):
    core = d.dut.core
    for _ in range(6000):
        if value(core, 'local_abort_recovery_required'):
            break
        await cycles(d)
    else:
        raise AssertionError(('Fatal close ACK fault did not reach recovery', FAULT_TARGET))
    await cycles(d, 9)
    assert value(d, 'fault_injected') and value(d, 'window_recovery_required')
    assert (value(core, 'local_abort_status'), value(core, 'local_abort_detail'), value(core, 'local_abort_memory_status')) == (5, 2 if FAULT_TARGET == 13 else 1, 0x75)
    assert b.commands[22] - command_start == FAULT_TARGET + 1
    applied = int.from_bytes(image[0x7f0008:0x7f0010], 'little')
    assert bool(applied >> 63) == (FAULT_TARGET == 13)
    # An uncertain write must retain the actual freeze and GPU lease. Merely
    # removing the injected status cannot authorize replay, close or a reset.
    b.set(fault_client=-1, window_req_valid=1, window_req_op=11, window_req_user=0,
        window_req_stream=1, window_req_generation=0, window_req_record_address=0, window_req_amount=0)
    commands = b.commands[22]
    for _ in range(19):
        await cycles(d)
        assert value(core, 'local_abort_recovery_required') and value(core.local_return_abort, 'state') == 8
        assert value(core, 'local_freeze_owner') == 2 and value(core, 'local_freeze_granted')
        assert value(core.reverse, 'freeze_active') and value(core, 'return_pending')
        assert value(d, 'response_record_lease_active') and not value(d, 'response_result_valid')
        assert not value(d, 'packet_result_valid') and not value(d, 'transport_close_valid')
        for name in ('s_axis_rx_tready', 's_axis_generated_tready', 'control_ready', 'window_req_ready'):
            assert not value(d, name), (FAULT_TARGET, name)
        assert b.commands[22] == commands and len(b.wire) == before
    assert not any(b.pending) and value(d, 'fabric_idle')
    assert image[:b.layout[6]] == initial[:b.layout[6]] and memory.tokenizer_data[:b.layout[6]] == initial[:b.layout[6]]
    accepted = dict(phase='passed', actual_native_initial_stream_window=0, actual_fault_phase=FAULT_TARGET,
        actual_memory_commands=FAULT_TARGET + 1, actual_memory_error=0x75,
        actual_send_closed_write_applied=FAULT_TARGET == 13, actual_freeze_and_gpu_lease_retained=True,
        actual_new_admission_fenced=True, actual_no_error_replay_or_fabricated_completion=True,
        actual_goaway_and_host_close_not_published=True, recovery_after_uncertain_close_verified=False,
        complete_model_prefix_immutable=True, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')


async def observe_cancel(d, b, trace):
    clock = 0
    pending = None
    frozen = False
    while True:
        await RisingEdge(d.clk)
        clock += 1
        if value(d, 'rst'):
            continue
        c = d.dut.core
        if hasattr(c, 'local_return_abort') and value(c.local_return_abort, 'freeze_drained') and not frozen:
            frozen = True
            trace.append(dict(event='actual_freeze_drained', clock=clock))
        if value(c, 'service_window_req_valid') and value(c, 'service_window_req_ready') and value(c, 'service_window_req_op') == 11 and value(c, 'window_owner') == 9:
            assert frozen and not value(c.reverse, 'frame_wire_pending')
            trace.append(dict(event='actual_fatal_close_request', clock=clock,
                **{n: value(c, 'service_window_req_' + n) for n in ('user', 'stream', 'generation', 'record_address', 'amount')}))
        if value(d, 'mem_rsp_valid') >> 22 & value(d, 'mem_rsp_ready') >> 22 & 1:
            assert pending is not None
            address, write, data = pending
            if write and data >> 63:
                assert value(d, 'mem_rsp_status') >> (22 * 8) & 255 == 0
                trace.append(dict(event='actual_send_closed_write_ack', clock=clock, address=address, data=data))
            pending = None
        if value(d, 'mem_valid') >> 22 & value(d, 'mem_ready') >> 22 & 1:
            assert pending is None
            pending = (value(d, 'mem_addr') >> (22 * 23) & 0x7fffff,
                value(d, 'mem_write') >> 22 & 1, value(d, 'mem_data') >> (22 * 72) & ((1 << 64) - 1))
        if value(c, 'service_window_rsp_valid') and value(c, 'service_window_rsp_ready') and value(c, 'service_window_rsp_op') == 11 and value(c, 'window_owner') == 10:
            assert (value(c, 'service_window_rsp_status'), value(c, 'service_window_rsp_memory_status')) == (0, 0)
            assert value(c, 'service_window_rsp_binding_valid') and value(c, 'service_window_rsp_send_closed')
            trace.append(dict(event='actual_fatal_close_result_ack', clock=clock,
                user=value(c, 'service_window_rsp_user'), stream=value(c, 'service_window_rsp_stream'),
                generation=value(c, 'service_window_rsp_generation'), address=value(c, 'service_window_rsp_record_address')))
        if value(c.reverse, 'credit_error_valid'):
            trace.append(dict(event='actual_closed_reservation', clock=clock,
                status=value(c.reverse, 'credit_error_status'), error=value(c.reverse, 'credit_error_http2_error'),
                memory_status=value(c.reverse, 'credit_error_memory_status')))


@cocotb.test(timeout_time=5, timeout_unit='ms')
async def fatal_connection_cancels_native_zero_window_return(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    reference = json.loads((folder / 'reference_cases.json').read_text())['cases'][0]
    image = bytearray(b''.join(int(s, 16).to_bytes(8, 'little') for s in (folder / 'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest() == manifest['loaded_image_sha256']
    initial = bytes(image)
    memory = SeparateMemory(d, image)
    b = Bench(d, layout, memory, reverse)
    close = LocalErrorWitness(d, b)
    trace = []
    server = H2Connection(H2Configuration(client_side=False))
    server.initiate_connection()
    b.client.update_settings({SettingCodes.INITIAL_WINDOW_SIZE: 0})
    b.set(rst=1, fault_client=-1, fault_arm=0, s_axis_generated_tvalid=0, response_result_ready=0,
        m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
        maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    workers = [b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated()]
    if FAULT_TARGET is None:
        workers += [close.observe(), close.hold_and_close(), observe_cancel(d, b, trace)]
    for worker in workers:
        cocotb.start_soon(worker)
    await cycles(d, 5)
    b.set(rst=0)
    for prefix in ('queue', 'stream'):
        await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready')
        await b.wait(prefix + '_cfg_result_valid')
        assert value(d, prefix + '_cfg_status') == 0
        await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
    await b.directory(4)
    await b.open()
    raw = b.client.data_to_send()
    server.receive_data(raw)
    assert server.remote_settings.initial_window_size == 0
    await b.packet(0, 1, raw, 1)
    prompt = bytes.fromhex(reference['prompt_utf8_hex'])
    body = b'\x0a' + varint(len(prompt)) + prompt
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    b.client.send_data(1, b'\0' + len(body).to_bytes(4, 'big') + body, end_stream=True)
    raw = b.client.data_to_send()
    server.receive_data(raw)
    await b.packet(0, 2, raw, 1)
    await b.drain(0, 1, 101, reference['token_ids'])
    captured = list(b.received)
    await b.gpu_offer(1, captured[0], 0, 0, 2)
    await b.wait('credit_parked')
    address = b.handles[0, 1]
    window = 0x7f0000 + (address - layout[13]) // 8
    assert int.from_bytes(image[window + 8:window + 12], 'little') == 0
    assert value(d, 'response_record_lease_active') and not value(d, 'response_result_valid')
    before = len(b.wire)
    invalid = b'\0\0\x01\0\x08\0\0\0\x01\x01'
    try:
        server.receive_data(invalid)
    except ProtocolError as error:
        assert int(error.error_code) == 1
    else:
        raise AssertionError('Native server accepted invalid padding')
    b.phase = 'fatal packet while actual GPU return is credit parked'
    command_start = b.commands[22]
    if FAULT_TARGET is not None:
        b.set(fault_client=22, fault_target=FAULT_TARGET, fault_arm=1)
        await cycles(d)
        b.set(fault_arm=0)
    await b.raw_fragment(3, invalid, 1)
    if FAULT_TARGET is not None:
        await verify_uncertain_fatal_close(d, b, image, memory, initial, before, command_start)
        return
    for _ in range(6000):
        if value(d, 'response_result_valid'):
            break
        await cycles(d)
    else:
        failure = dict(phase='fatal_credit_park_deadlock', actual_native_initial_stream_window=0,
            actual_send_window=int.from_bytes(image[window + 8:window + 16], 'little'),
            actual_credit_parked=value(d, 'credit_parked'), actual_return_pending=value(d.dut.core, 'return_pending'),
            actual_gpu_lease=value(d, 'response_record_lease_active'), actual_forward_state=value(d.dut.core.forward, 'state'),
            actual_connection_closing=value(d.dut.core, 'receive_connection_closing'),
            actual_raw_context_header=image[layout[19]:layout[19] + 8].hex(),
            actual_wire_types=[p[3] for p in b.wire[before:]], actual_cancel_trace=trace,
            full_system_complete=False)
        Path('failure.json').write_text(json.dumps(failure, indent=2) + '\n')
        raise AssertionError(failure)
    await b.terminal(16, 5, 1, ack=False)
    assert value(d, 'response_result_credit_status') == 8 and value(d, 'response_result_credit_http2_error') == 5
    assert not value(d, 'response_recovery_required') and not value(d, 'packet_result_valid')
    assert value(d, 'response_record_lease_active') and not any(p[3] == 0 for p in b.wire[before:])
    # Hold an ordinary host request throughout the fatal owner. It must not
    # acquire that owner's capability, even with the same user and arena tuple.
    b.set(window_req_op=11,window_req_maintenance=0,window_req_user=0,window_req_stream=1,
        window_req_generation=0,window_req_record_address=0,window_req_amount=0,
        window_cfg_context_base=layout[19],window_cfg_context_bytes=layout[20],
        window_cfg_stream_base=layout[13],window_cfg_stream_bytes=layout[14],
        window_cfg_window_base=0x7f0000,window_cfg_window_bytes=layout[14]//8,
        window_cfg_work_floor=layout[6],window_req_valid=1)
    for _ in range(17):
        await cycles(d)
        assert value(d, 'response_record_lease_active') and not value(d, 'packet_result_valid')
        assert not value(d, 'window_req_ready')
    b.set(response_result_ready=1)
    await cycles(d)
    b.set(response_result_ready=0)
    b.current = None
    await b.wait('packet_result_valid')
    assert (value(d, 'packet_committed'), value(d, 'packet_status'), value(d, 'transport_packet_http2_error')) == (0, 4, 1)
    assert [p[3] for p in b.wire[before:]] == [7]
    assert not value(d, 'response_record_lease_active') and not any(b.pending)
    await b.ack('packet_result_valid', 'packet_result_ready', 13)
    proof = close.result()
    fatal_trace = list(trace)
    memory_before=b.commands[22]
    await b.send('window_req_valid','window_req_ready')
    await b.wait('window_rsp_valid')
    assert (value(d,'window_rsp_op'),value(d,'window_rsp_status'),value(d,'window_rsp_detail'),value(d,'window_rsp_memory_status'))==(11,7,14,0)
    assert b.commands[22]==memory_before,'Unauthorized fatal opcode issued a memory command'
    await b.ack('window_rsp_valid','window_rsp_ready',13)
    assert not value(d,'window_recovery_required') and not value(d,'response_recovery_required')
    # Reuse the actual closed connection/RPC/window arenas after the GPU lease
    # and fatal owner retire. A new native peer advertises its ordinary window;
    # there is no reset, memory patch or grant supplied by this test.
    old_generation = b.bindings[0, 1]
    old_address = b.handles[0, 1]
    b.client = H2Connection(H2Configuration(client_side=True, header_encoding='utf-8'))
    b.client.initiate_connection()
    await b.open()
    await b.packet(0, 4, b.client.data_to_send(), 1)
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    b.client.send_data(1, b'\0' + len(body).to_bytes(4, 'big') + body, end_stream=True)
    await b.packet(0, 5, b.client.data_to_send(), 1)
    assert b.handles[0, 1] == old_address and b.bindings[0, 1] == old_generation + 1
    await b.drain(0, 1, 101, reference['token_ids'])
    reopened = list(b.received)
    for ordinal, token in enumerate(reopened):
        await b.gpu(1, token, ordinal, int(ordinal + 1 == len(reopened)), 2)
    assert ('StreamEnded', 1) in b.client_events
    expected = bytearray()
    for ordinal in range(len(reopened)):
        raw = bytes.fromhex(reverse['cases'][0]['chunks'][ordinal]['bow_hex'])
        message = varint(17 << 3 | 2) + varint(len(raw)) + raw
        expected.extend(b'\0' + len(message).to_bytes(4, 'big') + message)
    assert bytes(b.response_records[1]) == bytes(expected)
    await b.directory(3, 0, 1)
    assert b.client.outbound_flow_control_window == 65535
    assert not value(d.dut.core, 'local_abort_busy') and not value(d.dut.core, 'local_abort_recovery_required')
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    accepted = dict(phase='passed', actual_native_initial_stream_window=0,
        actual_captured_dma_ids=captured, actual_cancelled_gpu_token=captured[0],
        actual_gpu_cancellation_result=[16, 5, 1], actual_closed_reservation_status=8,
        actual_cancel_trace=fatal_trace, local_error_ownership=proof,
        actual_gpu_lease_retained_until_result_ack=True, actual_no_new_credit_required=True,
        ordinary_host_fatal_opcode_denied_before_memory=True,
        actual_reopen_without_global_reset=True, actual_same_rpc_address=old_address,
        actual_reused_generation=b.bindings[0, 1], actual_reopened_dma_ids_returned=reopened,
        actual_reopened_native_response_hex=bytes(expected).hex(), actual_reopened_successful_close_refund=True,
        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,
        parser_memory_clients=len(d.p_mem_valid), full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
