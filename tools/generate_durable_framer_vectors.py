"""Native hyper-h2 stream-starvation and partial DATA-frame references."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import DataReceived
from h2.settings import SettingCodes
from hyperframe.frame import DataFrame


def main():
    root = Path(__file__).resolve().parents[1]
    client = H2Connection(H2Configuration(client_side=True, header_encoding='utf-8'))
    server = H2Connection(H2Configuration(client_side=False, header_encoding='utf-8'))
    client.initiate_connection(); server.initiate_connection()
    server.receive_data(client.data_to_send()); client.receive_data(server.data_to_send())
    server.receive_data(client.data_to_send())
    client.update_settings({SettingCodes.INITIAL_WINDOW_SIZE: 0})
    server.receive_data(client.data_to_send()); client.receive_data(server.data_to_send())
    for stream in (1, 3):
        client.send_headers(stream, [(':method', 'POST'), (':scheme', 'https'), (':authority', 'credit.test'),
            (':path', '/generate'), ('content-type', 'application/grpc')], end_stream=True)
        server.receive_data(client.data_to_send())
        server.send_headers(stream, [(':status', '200'), ('content-type', 'application/grpc')])
        client.receive_data(server.data_to_send())
    message = bytes((i * 37 + i // 19) % 256 for i in range(20000))
    record = b'\0' + len(message).to_bytes(4, 'big') + message
    position = 0; frames = []; received = bytearray()
    for increment in (1, 2, 16384, len(record) - 16387):
        assert server.local_flow_control_window(1) == 0
        client.increment_flow_control_window(increment, stream_id=1)
        server.receive_data(client.data_to_send())
        amount = min(len(record) - position, server.max_outbound_frame_size, server.local_flow_control_window(1))
        assert amount == increment
        data = record[position:position + amount]
        server.send_data(1, data)
        wire = server.data_to_send()
        check = DataFrame(1); check.data = data
        assert wire == check.serialize()
        events = client.receive_data(wire)
        for event in events:
            if isinstance(event, DataReceived): received.extend(event.data)
        frames.append(dict(increment=increment, wire_hex=wire.hex(), payload_bytes=amount,
            connection_window=server.outbound_flow_control_window, stream_window=server.streams[1].outbound_flow_control_window))
        position += amount
    assert position == len(record) and received == record
    result = dict(phase='native_durable_framer_reference_passed', h2_version=importlib.metadata.version('h2'),
        hyperframe_version=importlib.metadata.version('hyperframe'), generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        message_hex=message.hex(), initial_window=0, peer_max_frame=server.max_outbound_frame_size,
        frames=frames, data_frames=len(frames), wire_bytes=sum(len(bytes.fromhex(f['wire_hex'])) for f in frames),
        grpc_record_bytes=len(record), complete_http2_endpoint_implemented=False)
    folder = root / 'build/http2-durable-framer-fixtures'; folder.mkdir(exist_ok=True)
    (folder / 'frames.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Native h2 verified {len(frames)} partial DATA frames and {len(record)} gRPC bytes')


if __name__ == '__main__':
    main()
