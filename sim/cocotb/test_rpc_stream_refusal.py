"""Coalesced refused streams retain connection accounting and live RPCs."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from hyperframe.frame import Frame
from test_http2_prefill import value
from test_rpc_admission_fence import FenceBench, settled
from test_raw_grpc_enveloped import varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


class MultipleRefusals(FenceBench):
    def record_fence_rejection(self):
        super().record_fence_rejection()
        self.expected_fence_stream = 5 if len(self.fence_rejections) == 1 else None
        return True


def request_headers(client, stream):
    fields=[(':method', 'POST'), (':scheme', 'https'),
        (':authority', 'parser.test'), (':path', '/parser.Tokenize/Proto'),
        ('content-type', 'application/grpc+proto'), ('te', 'trailers')]
    if stream!=1:fields.append(('x-refusal-shared', 'dynamic-entry-from-refused-request'))
    client.send_headers(stream,fields)
    return client.data_to_send()


@cocotb.test(timeout_time=30, timeout_unit='ms')
async def coalesced_refusals_discard_real_data_and_preserve_hpack(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    initial = b''.join(int(word, 16).to_bytes(8, 'little') for word in (folder / 'memory.mem').read_text().splitlines())
    assert len(initial) == 8388608 and hashlib.sha256(initial).hexdigest() == manifest['loaded_image_sha256']
    image = bytearray(initial); memory = SeparateMemory(d, image)
    b = MultipleRefusals(d, layout, memory, reverse)
    b.expected_fence_stream = None; b.fence_rejections = []
    b.set(rst=1, fault_client=-1, fault_target=-1, fault_arm=0, s_axis_generated_tvalid=0,
        response_result_ready=0, m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0,
        packet_result_ready=0, maintenance_grant=1, admit_packets=1, admit_messages=1,
        admit_new_rpcs=1, rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    for worker in (Clock(d.clk, 4, unit='ns').start(), memory.parser.run(), memory.tokenizer.run(),
        b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated(), b.observe_private_credit()):
        cocotb.start_soon(worker)
    await cycles(d, 5); b.set(rst=0)
    for prefix in ('queue', 'stream'):
        await b.send(prefix + '_cfg_valid', prefix + '_cfg_ready'); await b.wait(prefix + '_cfg_result_valid')
        assert value(d, prefix + '_cfg_status') == 0
        await b.ack(prefix + '_cfg_result_valid', prefix + '_cfg_result_ready', 0)
    b.response_configuration(0); await b.directory(4); await b.open()
    await b.packet(0, 1, b.client.data_to_send(), 1)
    await b.packet(0, 2, request_headers(b.client, 1), 1)
    await settled(b)
    body = b'\x0a\x0bhello world'; record = b'\0' + len(body).to_bytes(4, 'big') + body
    b.client.send_data(1, record[:7]); await b.packet(0, 3, b.client.data_to_send(), 1)
    before = bytes(image[b.handles[0, 1]:b.handles[0, 1] + 128])
    assert before[:4] == (0x47525331).to_bytes(4, 'little')
    b.set(admit_new_rpcs=0); b.expected_fence_stream = 3
    # Both request headers and DATA are queued by the real native peer before
    # it can receive either RST_STREAM. Refused stream5 indexes HPACK state
    # installed by stream3; neither receives a durable RPC allocation.
    raw = request_headers(b.client, 3)
    fragment_offset=len(raw)+9+19
    refused = [(3, b'X' * 4097, 0), (3, b'Y' * 17, 255), (5, b'Z' * 1025, 7)]
    b.client.send_data(3, refused[0][1]); raw += b.client.data_to_send()
    b.client.send_data(3, refused[1][1], pad_length=255, end_stream=True); raw += b.client.data_to_send()
    raw += request_headers(b.client, 5)
    b.client.send_data(5, refused[2][1], pad_length=7, end_stream=True); raw += b.client.data_to_send()
    b.client.send_data(1, record[7:]); raw += b.client.data_to_send()
    expected_discard_bytes = 4097 + (17 + 256) + (1025 + 8)
    b.ready_wire = False
    sending = cocotb.start_soon(b.packet(0, 4, raw, 1))
    await b.wait('m_axis_tx_tvalid')
    snapshot = tuple(value(d, 'm_axis_tx_' + n) for n in ('tdata','tkeep','tlast','tuser'))
    wire = snapshot[0].to_bytes(64, 'little')[:snapshot[1].bit_count()]
    reset, size = Frame.parse_frame_header(memoryview(wire[:9])); reset.parse_body(memoryview(wire[9:]))
    assert reset.type == 3 and reset.stream_id == 3 and reset.error_code == 7 and len(wire) == 13
    for _ in range(37):
        await FallingEdge(d.clk)
        assert value(d, 'm_axis_tx_tvalid') and not value(d, 'm_axis_tx_tready')
        assert tuple(value(d, 'm_axis_tx_' + n) for n in ('tdata','tkeep','tlast','tuser')) == snapshot
    b.ready_wire = True
    await sending
    assert [r['stream'] for r in b.fence_rejections] == [3, 5]
    assert (0, 3) not in b.bindings and (0, 5) not in b.bindings
    assert image[b.handles[0,1]:b.handles[0,1]+4] == (0x47525331).to_bytes(4,'little')
    assert ('StreamReset',3) in b.client_events and ('StreamReset',5) in b.client_events
    assert not any(kind == 'ConnectionTerminated' for kind, stream in b.client_events)
    await b.drain(0, 1, 101, [15339, 1917]); captured = {1:list(b.received)}
    b.client.send_headers(1, [('request-finished','yes')], end_stream=True)
    await b.packet(0, 5, b.client.data_to_send(), 1)
    for ordinal, token in enumerate(captured[1]): await b.gpu(1, token, ordinal, int(ordinal==1), 2)
    await b.directory(3,0,1); await settled(b)
    capacity = layout[14]//128*(layout[18]+5)
    assert b.client.outbound_flow_control_window == capacity
    # Admission resumes on the same connection and uses dynamic HPACK entries
    # from the refused requests. No connection reset, FORMAT or image reload.
    b.set(admit_new_rpcs=1)
    raw = request_headers(b.client, 7)
    b.client.send_data(7,record,end_stream=True); raw += b.client.data_to_send()
    await b.packet(0,6,raw,1); await b.drain(0,7,101,[15339,1917]); captured[7]=list(b.received)
    for ordinal, token in enumerate(captured[7]): await b.gpu(7, token, ordinal, int(ordinal==1), 2)
    await b.directory(3,0,7); await settled(b)
    expected = bytearray()
    for chunk in reverse['cases'][0]['chunks']:
        decoded=bytes.fromhex(chunk['bow_hex']); payload=varint(17<<3|2)+varint(len(decoded))+decoded
        expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
    assert all(bytes(b.response_records[s])==expected and ('StreamEnded',s) in b.client_events for s in (1,7))
    assert b.ids == 4 and b.messages == 2 and len(b.generated_accepts) == 4
    assert b.client.outbound_flow_control_window == capacity
    assert image[:layout[6]]==initial[:layout[6]] and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    assert not value(d,'receive_recovery_required') and not value(d,'response_recovery_required')
    b.save_wire_evidence()
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',
        refused_streams=[3,5],already_queued_discarded_data_bytes=expected_discard_bytes,
        held_reset_cycles=37,actual_captured_dma_ids_returned=captured,
        actual_generated_descriptors=b.generated_accepts,header_rejections=b.fence_rejections,
        native_complete_grpc_calls=2,byte_exact_response_hex=bytes(expected).hex(),
        final_connection_credit=capacity,complete_model_prefixes_immutable=True,
        shared_hpack_state_preserved=True,native_vendor_runtime_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,full_system_complete=False),indent=2)+'\n')
