"""New-RPC refusal must preserve existing HTTP/2 DATA and GPU work."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_http2_prefill import value
from test_raw_open_rpc_credit import RecordingBench
from test_raw_grpc_enveloped import varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


class FenceBench(RecordingBench):
    def record_fence_rejection(self):
        names = ('header_status', 'header_detail', 'header_memory_status', 'header_cleanup_status',
            'header_connection_error', 'header_http2_error', 'header_generation', 'header_model_epoch',
            'header_schema_epoch', 'header_application', 'header_address')
        observed = tuple(value(self.d, n) for n in names)
        assert observed == (4, 1, 0, 0, 0, 7, 0, 0, 0, 0, 0), observed
        self.fence_rejections.append(dict(stream=value(self.d, 'header_stream'), clock=self.clocks,
            **dict(zip(names, observed))))
        return True


def headers(stream, client):
    client.send_headers(stream, [(':method', 'POST'), (':scheme', 'https'),
        (':authority', 'parser.test'), (':path', '/parser.Tokenize/Proto'),
        ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    return client.data_to_send()


async def settled(b):
    for _ in range(100000):
        c = b.d.dut.core
        if not value(c, 'rc_pending') and not value(c, 'rc_busy') and value(b.d, 'idle'):
            return
        await cycles(b.d)
    raise AssertionError('Existing admission/capacity did not settle')


@cocotb.test(timeout_time=30, timeout_unit='ms')
async def new_rpc_fence_preserves_old_calls_and_sampled_begin(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    initial = b''.join(int(word, 16).to_bytes(8, 'little') for word in (folder / 'memory.mem').read_text().splitlines())
    assert len(initial) == 8388608 and hashlib.sha256(initial).hexdigest() == manifest['loaded_image_sha256']
    image = bytearray(initial)
    memory = SeparateMemory(d, image)
    b = FenceBench(d, layout, memory, reverse)
    b.expected_fence_stream = None
    b.fence_rejections = []
    b.set(rst=1, fault_client=-1, fault_target=-1, fault_arm=0, s_axis_generated_tvalid=0,
        response_result_ready=0, m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0,
        packet_result_ready=0, maintenance_grant=1, admit_packets=1, admit_messages=1,
        admit_new_rpcs=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    for worker in (Clock(d.clk, 4, unit='ns').start(), memory.parser.run(), memory.tokenizer.run(),
        b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), b.observe_private_credit()):
        cocotb.start_soon(worker)
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
    await b.packet(0, 2, headers(1, b.client), 1)
    await settled(b)
    assert (0, 1) in b.bindings and b.ids == b.messages == 0
    original_binding = (b.bindings[0, 1], b.handles[0, 1])
    body = b'\x0a\x0bhello world'
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    # Leave the old RPC in a durable partial-message state. The remaining
    # bytes, request trailers and every GPU descriptor arrive after the fence.
    b.client.send_data(1, record[:7])
    await b.packet(0, 3, b.client.data_to_send(), 1)
    before_refusal = bytes(image[original_binding[1]:original_binding[1] + 128])
    assert int.from_bytes(before_refusal[:4], 'little') == 0x47525331
    await FallingEdge(d.clk)
    b.set(admit_new_rpcs=0)
    b.expected_fence_stream = 3
    await b.packet(0, 4, headers(3, b.client), 0)
    b.expected_fence_stream = None
    assert len(b.fence_rejections) == 1 and (0, 3) not in b.bindings
    assert (b.bindings[0, 1], b.handles[0, 1]) == original_binding
    # Passive failure evidence is saved before the original preservation
    # assertion. No traffic, admission, result retirement or assertion changes.
    b.save_wire_evidence()
    Path('fence_refusal_observation.json').write_text(json.dumps(dict(
        old_stream=1, refused_stream=3, old_generation=original_binding[0],
        old_address=original_binding[1], before_record_hex=before_refusal.hex(),
        after_record_hex=bytes(image[original_binding[1]:original_binding[1] + 128]).hex(),
        header_rejections=b.fence_rejections, actual_dma_ids=b.ids,
        actual_generated_descriptors=b.generated_accepts,
        admit_new_rpcs=value(d,'admit_new_rpcs'), admit_packets=value(d,'admit_packets'),
        admit_messages=value(d,'admit_messages')), indent=2) + '\n')
    assert int.from_bytes(image[original_binding[1]:original_binding[1] + 4], 'little') == 0x47525331
    assert value(d, 'admit_packets') and value(d, 'admit_messages') and not value(d, 'admit_new_rpcs')
    b.client.send_data(1, record[7:])
    await b.packet(0, 5, b.client.data_to_send(), 1)
    await b.drain(0, 1, 101, [15339, 1917])
    first_dma = list(b.received)
    b.client.send_headers(1, [('request-finished', 'yes')], end_stream=True)
    await b.packet(0, 6, b.client.data_to_send(), 1)
    assert (b.bindings[0, 1], b.handles[0, 1]) == original_binding
    for ordinal, token in enumerate(first_dma):
        assert not value(d, 'admit_new_rpcs')
        await b.gpu(1, token, ordinal, int(ordinal == 1), 2)
    assert ('StreamEnded', 1) in b.client_events
    await b.directory(3, 0, 1)
    b.client.ping(b'fenced__')
    await b.packet(0, 7, b.client.data_to_send(), 1)
    assert ('PingAckReceived', 0) in b.client_events
    # A BEGIN accepted before the fence has a sampled permission. Lower the
    # gate before HPACK/candidate completion and then send its DATA later.
    b.set(admit_new_rpcs=1)
    begins = []
    async def close_fence_at_begin():
        forward = d.dut.core.forward
        for _ in range(100000):
            await RisingEdge(d.clk)
            if value(forward, 'a_begin_valid') and value(forward, 'a_begin_ready'):
                assert value(forward, 'a_begin_stream') == 5 and value(d, 'admit_new_rpcs')
                begins.append(dict(stream=5, clock=b.clocks, sampled_admit_new=value(forward, 'a_admit_new')))
                await FallingEdge(d.clk)
                b.set(admit_new_rpcs=0)
                return
        raise AssertionError('No actual accepted BEGIN for the fence-edge test')
    closing = cocotb.start_soon(close_fence_at_begin())
    await b.packet(0, 8, headers(5, b.client), 1)
    await closing
    assert len(begins) == 1 and begins[0]['sampled_admit_new'] == 1
    assert (0, 5) in b.bindings and not value(d, 'admit_new_rpcs')
    b.client.send_data(5, record, end_stream=True)
    await b.packet(0, 9, b.client.data_to_send(), 1)
    await b.drain(0, 5, 101, [15339, 1917])
    second_dma = list(b.received)
    for ordinal, token in enumerate(second_dma):
        await b.gpu(5, token, ordinal, int(ordinal == 1), 2)
    await b.directory(3, 0, 5)
    expected = bytearray()
    for chunk in reverse['cases'][0]['chunks']:
        raw = bytes.fromhex(chunk['bow_hex'])
        payload = varint(17 << 3 | 2) + varint(len(raw)) + raw
        expected.extend(b'\0' + len(payload).to_bytes(4, 'big') + payload)
    assert all(bytes(b.response_records[s]) == expected and ('StreamEnded', s) in b.client_events for s in (1, 5))
    await settled(b)
    assert b.ids == 4 and b.messages == 2 and len(b.generated_accepts) == 4
    assert not any(b.pending) and not b.packet_bytes
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    assert not value(d, 'receive_recovery_required') and not value(d, 'response_recovery_required')
    b.save_wire_evidence()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',
        existing_partial_rpc_survives_new_rpc_refusal=True, request_trailers_under_fence=True,
        actual_captured_dma_ids_returned={1: first_dma, 5: second_dma},
        fence_rejections=b.fence_rejections, sampled_begin=begins,
        actual_generated_descriptors=b.generated_accepts, native_complete_grpc_calls=2,
        byte_exact_response_hex=bytes(expected).hex(), actual_raw_packets=b.packets,
        complete_model_prefixes_immutable=True, native_vendor_runtime_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False, full_system_complete=False), indent=2) + '\n')
