"""A fatal packet waits for an offered trailer and the actual GPU result ACK."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'native-vendor'))
import cocotb
from cocotb.clock import Clock
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from hyperframe.frame import GoAwayFrame
from local_error_witness import LocalErrorWitness
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench, varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


@cocotb.test(timeout_time=5, timeout_unit='ms')
async def fatal_packet_drains_offered_trailer_and_gpu_owner(d):
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
    witness = LocalErrorWitness(d, b)
    server = H2Connection(H2Configuration(client_side=False))
    server.initiate_connection()
    b.set(rst=1, fault_client=-1, fault_arm=0, s_axis_generated_tvalid=0, response_result_ready=0,
        m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0, packet_result_ready=0,
        maintenance_grant=1, admit_packets=1, admit_messages=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), witness.observe(), witness.hold_and_close()):
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
    await b.packet(0, 1, raw, 1)
    text = bytes.fromhex(reference['prompt_utf8_hex'])
    body = b'\x0a' + varint(len(text)) + text
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    b.client.send_data(1, b'\0' + len(body).to_bytes(4, 'big') + body, end_stream=True)
    raw = b.client.data_to_send()
    server.receive_data(raw)
    await b.packet(0, 2, raw, 1)
    await b.drain(0, 1, 101, reference['token_ids'])
    captured = list(b.received)
    assert len(captured) == 2
    await b.gpu(1, captured[0], 0, 0, 2)
    await b.gpu_offer(1, captured[1], 1, 1, 2)
    for _ in range(100000):
        if value(d.dut.core.reverse.response.envelope, 'state') == 10:
            break
        await cycles(d)
    else:
        raise AssertionError('The actual final trailer did not start')
    b.ready_wire = False
    d.m_axis_tx_tready.value = 0
    await b.wait('m_axis_tx_tvalid')
    offered = tuple(value(d, 'm_axis_tx_' + n) for n in ('tdata', 'tkeep', 'tlast', 'tuser'))
    assert offered[0] >> 24 & 255 == 1 and offered[0] >> 32 & 255 == 5
    before = len(b.wire)
    invalid = b'\0\0\x01\0\x08\0\0\0\x01\x01'
    try:
        server.receive_data(invalid)
    except ProtocolError as error:
        assert int(error.error_code) == 1
    else:
        raise AssertionError('Native server accepted invalid padding')
    await b.raw_fragment(3, invalid, 1)
    for _ in range(100000):
        if value(d.dut.core.forward, 'state') == 3:
            break
        await cycles(d)
    else:
        raise AssertionError('Fatal packet did not reach actual prefill preparation')
    held = 0
    for _ in range(17):
        await cycles(d)
        assert value(d, 'm_axis_tx_tvalid') and not value(d, 'm_axis_tx_tready')
        assert offered == tuple(value(d, 'm_axis_tx_' + n) for n in ('tdata', 'tkeep', 'tlast', 'tuser'))
        assert value(d.dut.core.forward, 'state') == 3 and not value(d.dut.core.forward, 'p_prepare_valid')
        assert value(d, 'response_record_lease_active') and value(d.dut.core, 'return_pending')
        assert not value(d, 'response_result_valid') and not value(d, 'packet_result_valid')
        assert not value(d.dut.core, 'local_error_started')
        assert not (value(d.dut.core, 'service_control_req_valid') and value(d.dut.core, 'service_control_req_ready')
            and value(d.dut.core, 'service_control_req_op') == 3)
        held += 1
    b.ready_wire = True
    await b.terminal(0, 0, 0)
    b.current = None
    await b.wait('packet_result_valid')
    assert (value(d, 'packet_committed'), value(d, 'packet_status'), value(d, 'transport_packet_http2_error')) == (0, 4, 1)
    assert not value(d, 'response_record_lease_active') and not value(d.dut.core, 'return_pending')
    assert [p[3] for p in b.wire[before:]] == [1, 7]
    expected_goaway = GoAwayFrame(0)
    expected_goaway.last_stream_id = 1
    expected_goaway.error_code = 1
    assert b.wire[-1] == expected_goaway.serialize()
    assert ('StreamEnded', 1) in b.client_events and not value(d, 'response_recovery_required')
    assert not any(b.pending) and not b.packet_bytes
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    await b.ack('packet_result_valid', 'packet_result_ready', 13)
    accepted = dict(phase='passed', actual_failed_packet_waited_for_gpu_and_wire_drain=True,
        held_prior_final_trailer_cycles=held, actual_captured_dma_ids_returned=captured,
        actual_successful_gpu_result_preserved=True, actual_native_stream_completed_before_goaway=True,
        actual_wire_types_after_fatal_packet=[p[3] for p in b.wire[before:]],
        local_error_ownership=witness.result(), parser_memory_clients=len(d.p_mem_valid),
        complete_model_prefix_immutable=True, stalled_send_credit_abort_verified=False,
        full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
