"""An open RPC must replenish actual consumed application DATA credit."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from test_http2_prefill import value
from test_raw_grpc_enveloped import Bench, varint
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


class RecordingBench(Bench):
    def __init__(self, *args):
        super().__init__(*args)
        self.ingress_packets = []
        self.completion_wait_limit = None
        self.completion_wait_progress = []
        self.private_credit_trace = []
        self.private_credit_observer_enabled = False

    async def observe_private_credit(self):
        self.private_credit_observer_enabled = True
        core = self.d.dut.core
        pending = None
        while True:
            await RisingEdge(self.d.clk)
            if value(self.d, 'rst'):
                assert pending is None
                continue
            if value(core, 'rc_credit_valid') and value(core, 'rc_credit_ready'):
                assert pending is None and value(core, 'rc_lock_active') and value(core, 'receive_pool_active')
                assert value(core, 'rc_credit_owner') and not value(core, 'rc_memory_owner')
                pending = len(self.private_credit_trace)
                self.private_credit_trace.append(dict(event='request', clock=self.clocks,
                    **{n:value(core,'rc_credit_'+n) for n in ('op','user','stream','generation','address','amount')},
                    actual_private_and_shared_pool_locks=True))
            if value(core, 'rc_backend_result_valid') and value(core, 'rc_credit_owner') and value(core, 'rc_credit_result_ready'):
                assert pending is not None
                self.private_credit_trace.append(dict(event='result',clock=self.clocks,request=pending,
                    **{n:value(core,'rx_backend_'+n) for n in ('status','detail','memory_status')}))
                pending = None

    async def packet(self, user, tag, raw, commit):
        self.ingress_packets.append(dict(user=user, tag=tag, raw_hex=raw.hex(), expected_commit=commit))
        await super().packet(user, tag, raw, commit)

    def save_wire_evidence(self):
        Path('wire_frames.json').write_text(json.dumps([raw.hex() for raw in self.wire], indent=2) + '\n')
        Path('ingress_packets.json').write_text(json.dumps(self.ingress_packets, indent=2) + '\n')
        Path('receive_trace.json').write_text(json.dumps(self.receive_trace, indent=2) + '\n')
        if self.private_credit_observer_enabled:
            Path('private_credit_trace.json').write_text(json.dumps(self.private_credit_trace, indent=2) + '\n')

    def record_completion_progress(self, waited):
        core = self.d.dut.core
        application = core.forward.prefill.parser.application
        replay = application.replay
        parser = application.parser
        record = dict(waited_cycles=waited, phase=self.phase, axi_reads=self.memory.reads,
            axi_writes=self.memory.writes, actual_dma_ids=self.ids,
            replay={n:value(replay,n) for n in ('state','remaining','offset','m_axis_tvalid','m_axis_tready','mem_valid','mem_ready','mem_rsp_valid','mem_rsp_ready')},
            application={n:value(application,n) for n in ('state','replay_done','parser_done','replay_status','parser_status')},
            parser={n:value(parser,n) for n in ('state','text_count','outstanding','rx_packet_open','in_valid','window_valid','proto_idle','error_valid')},
            protobuf={n:value(parser.proto_parser,n) for n in ('state','remaining','status')},
            queued_count=value(core,'queued_count'),pending_count=value(core,'pending_count'),
            completion_valid=value(self.d,'completion_valid'),receive_recovery_required=value(self.d,'receive_recovery_required'))
        self.completion_wait_progress.append(record)
        Path('completion_wait_progress.json').write_text(json.dumps(self.completion_wait_progress,indent=2)+'\n')
        return record

    async def wait(self, name):
        if name != 'completion_valid' or self.completion_wait_limit is None:
            return await super().wait(name)
        for waited in range(self.completion_wait_limit):
            if value(self.d,name):
                self.record_completion_progress(waited)
                return
            if waited % 100000 == 0:
                progress=self.record_completion_progress(waited)
                self.d._log.info('Large-message replay: waited=%d offset=%d remaining=%d parser=%d',
                    waited,progress['replay']['offset'],progress['replay']['remaining'],progress['parser']['state'])
            await FallingEdge(self.d.clk)
        self.save_wire_evidence()
        raise AssertionError(('Payload-sized completion timeout',name,self.completion_wait_limit,self.record_completion_progress(self.completion_wait_limit)))

    async def drain_queued_record(self, expected, ordinal):
        # The ordinary first-message helper also queues a connection command
        # which requires all messages to drain. This variant deliberately has
        # another descriptor queued, so retain its DMA/held-completion/lease
        # assertions and ACK without that unrelated connection command.
        d = self.d
        self.phase = f'drain queued open-RPC record {ordinal}'
        self.received = []
        self.saw_last = False
        self.expected = (0, 1, 101, expected)
        self.expected_ordinal = ordinal
        self.draining = True
        await self.wait('completion_valid')
        assert self.saw_last and self.received == expected
        names = ('completion_status', 'completion_detail', 'completion_memory_status', 'completion_token_stage',
            'completion_count', 'completion_user', 'completion_stream', 'completion_application',
            'completion_generation', 'completion_ordinal', 'completion_packet_tag', 'payload_lease_active')
        observed = tuple(value(d, n) for n in names)
        assert observed == (0, 0, 0, 0, len(expected), 0, 1, 101, self.bindings[0, 1], ordinal, self.last_tag, 1)
        for _ in range(20):
            await cycles(d)
            assert tuple(value(d, n) for n in names) == observed, 'Completion/lease changed before ACK'
        self.set(completion_ready=1)
        await cycles(d)
        self.set(completion_ready=0)
        self.draining = False
        self.messages += 1
        self.expected = None


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def consumed_messages_replenish_credit_before_rpc_close(d):
    folder = Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout = list(map(int, (folder / 'layout.txt').read_text().split()))
    manifest = json.loads((folder / 'fixture_manifest.json').read_text())
    references = json.loads((folder / 'reference_cases.json').read_text())
    reverse = json.loads((folder / 'response_reference.json').read_text())
    image = bytearray(b''.join(int(word, 16).to_bytes(8, 'little')
        for word in (folder / 'memory.mem').read_text().splitlines()))
    assert len(image) == 8388608 and hashlib.sha256(image).hexdigest() == manifest['loaded_image_sha256']
    initial = bytes(image)
    prompt = bytes.fromhex(references['cases'][0]['prompt_utf8_hex'])
    ids = references['cases'][0]['token_ids']
    assert prompt == b'hello world' and ids == [15339, 1917]
    # A legal unselected field consumes real DATA credit and storage, while
    # each selected prompt produces only two real DMA IDs. Nine records fit
    # within the unchanged 128 KiB allocation but exceed the initial window.
    body = varint(99 << 3 | 2) + varint(8000) + b'U' * 8000 + b'\x0a' + varint(len(prompt)) + prompt
    record = b'\0' + len(body).to_bytes(4, 'big') + body
    assert len(record) == 8022 and 8 * len(record) < 65535 < 9 * len(record) < layout[18]
    message_count = int(os.environ.get('PARSER_OPEN_RPC_MESSAGES', '9'))
    partial_tail = int(os.environ.get('PARSER_OPEN_RPC_PARTIAL_TAIL', '0'))
    assert 9 <= message_count <= 1024 and 0 <= partial_tail < len(record)
    memory = SeparateMemory(d, image)
    b = RecordingBench(d, layout, memory, reverse)
    b.set(rst=1, fault_client=-1, fault_arm=0, s_axis_generated_tvalid=0,
        response_result_ready=0, m_axis_tx_tready=0, window_req_valid=0, window_rsp_ready=0,
        packet_result_ready=0, maintenance_grant=1, admit_packets=1, admit_messages=1,
        rpc_error_ready=1, queue_cfg_clear=1)
    b.configure()
    cocotb.start_soon(Clock(d.clk, 4, unit='ns').start())
    cocotb.start_soon(memory.run())
    for worker in (b.ready_driver(), b.observe(), b.actual_observer(), b.observe_generated()):
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
    b.client.send_headers(1, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'parser.test'),
        (':path', '/parser.Tokenize/Proto'), ('content-type', 'application/grpc+proto'), ('te', 'trailers')])
    await b.packet(0, 2, b.client.data_to_send(), 1)
    tag = 3
    sent = 0
    captured = []
    requests = []
    first_message = 0
    if partial_tail:
        # At the first DMA ACKs, two complete payloads and the beginning of a
        # third occupy the same allocation. Reclamation must preserve that
        # unconsumed suffix and its partial gRPC state, rather than clear it.
        batch = record * 2 + record[:partial_tail]
        assert len(batch) <= min(b.client.max_outbound_frame_size,
            b.client.local_flow_control_window(1))
        b.client.send_data(1, batch)
        raw = b.client.data_to_send()
        requests.append(dict(tag=tag, message=0, offset=0, data_bytes=len(batch),
            end_stream=False, raw_hex=raw.hex(), complete_records=2, partial_record_bytes=partial_tail))
        await b.packet(0, tag, raw, 1)
        tag += 1
        sent += len(batch)
        for message in range(2):
            await b.drain_queued_record(ids, message)
            captured.extend(b.received)
            assert not b.generated_accepts
        first_message = 2
    for message in range(first_message, message_count):
        offset = partial_tail if message == first_message and partial_tail else 0
        while offset < len(record):
            # Let native h2 enforce both peer windows. No BFM callback or
            # direct ledger write can supply credit to the sender.
            b.phase = f'open RPC message {message}, DATA offset {offset}'
            for _ in range(100000):
                if b.client.local_flow_control_window(1) > 0:
                    break
                await RisingEdge(d.clk)
            else:
                assert not b.generated_accepts and ('StreamEnded', 1) not in b.client_events
                assert not value(d, 'response_recovery_required') and not value(d, 'shutdown_recovery_required')
                assert image[:layout[6]] == initial[:layout[6]]
                assert memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
                failure = dict(phase='open_rpc_application_credit_starvation',
                    message=message, message_offset=offset, actual_data_bytes_sent=sent,
                    complete_messages_acknowledged=b.messages, actual_forward_dma_ids=b.ids,
                    actual_captured_dma_ids=captured,
                    native_connection_credit=b.client.outbound_flow_control_window,
                    native_stream_and_connection_credit=b.client.local_flow_control_window(1),
                    actual_window_update_frames=sum(raw[3] == 8 for raw in b.wire),
                    actual_gpu_descriptors=0, stream_ended=False,
                    complete_model_prefixes_immutable=True, full_system_complete=False)
                Path('failure.json').write_text(json.dumps(failure, indent=2) + '\n')
                Path('receive_trace.json').write_text(json.dumps(b.receive_trace, indent=2) + '\n')
                Path('requests.json').write_text(json.dumps(requests, indent=2) + '\n')
                b.save_wire_evidence()
                raise AssertionError(failure)
            size = min(len(record) - offset, b.client.max_outbound_frame_size,
                b.client.local_flow_control_window(1))
            end = message == message_count - 1 and offset + size == len(record)
            b.client.send_data(1, record[offset:offset + size], end_stream=end)
            raw = b.client.data_to_send()
            requests.append(dict(tag=tag, message=message, offset=offset, data_bytes=size,
                end_stream=end, raw_hex=raw.hex()))
            await b.packet(0, tag, raw, 1)
            tag += 1
            offset += size
            sent += size
        await b.drain(0, 1, 101, ids, ordinal=message)
        captured.extend(b.received)
        assert b.messages == message + 1 and not b.generated_accepts
    assert sent == message_count * len(record) and captured == ids * message_count
    # Only now return the actual captured DMA IDs through the production GPU
    # input. A successful test must also finish the complete native RPC.
    expected = bytearray()
    for ordinal, token in enumerate(captured):
        await b.gpu(1, token, ordinal, int(ordinal + 1 == len(captured)), 2)
        text = bytes.fromhex(reverse['cases'][0]['chunks'][ordinal % len(ids)]['bow_hex'])
        payload = varint(17 << 3 | 2) + varint(len(text)) + text
        expected.extend(b'\0' + len(payload).to_bytes(4, 'big') + payload)
    assert bytes(b.response_records[1]) == expected and ('StreamEnded', 1) in b.client_events
    assert image[:layout[6]] == initial[:layout[6]] and memory.tokenizer_data[:layout[6]] == initial[:layout[6]]
    assert not any(b.pending) and not b.packet_bytes and not value(d, 'response_record_lease_active')
    Path('requests.json').write_text(json.dumps(requests, indent=2) + '\n')
    Path('receive_trace.json').write_text(json.dumps(b.receive_trace, indent=2) + '\n')
    b.save_wire_evidence()
    accepted = dict(phase='passed', complete_messages_acknowledged=b.messages,
        requested_messages=message_count, initial_partial_record_bytes=partial_tail,
        application_bytes_exceeded_payload_allocation=sent > layout[18],
        actual_application_data_bytes=sent, actual_captured_dma_ids_returned=captured,
        actual_window_update_frames=sum(raw[3] == 8 for raw in b.wire),
        actual_gpu_descriptors=len(b.generated_accepts), native_complete_grpc_calls=1,
        credit_replenished_before_gpu_eos=True, complete_model_prefixes_immutable=True,
        physical_interfaces_verified=False, native_vendor_memory=False, full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted, indent=2) + '\n')
