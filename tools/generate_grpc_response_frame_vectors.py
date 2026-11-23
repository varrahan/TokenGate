"""Independent hyperframe wire oracle for uncompressed gRPC DATA records."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import struct

from hyperframe.frame import DataFrame, Frame


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261120)
    cases = []

    def append(payload, maximum=16384, stream=1, status=0, fault=None, grant_limits=()):
        record = struct.pack('>BI', 0, len(payload)) + payload
        packets = []
        maxima = []
        grants = []
        if status in (0, 5):
            offset = 0
            while offset < len(record):
                eligible = min(maximum, len(record) - offset)
                permitted = min(eligible, grant_limits[len(packets) % len(grant_limits)]) if grant_limits else eligible
                maxima.append(eligible)
                if fault in ('zero_grant', 'large_grant') or fault == 'late_zero_grant' and packets:
                    grants.append(eligible + 1 if fault == 'large_grant' else 0)
                    break
                grants.append(permitted)
                frame = DataFrame(stream_id=stream)
                frame.data = record[offset:offset + permitted]
                offset += permitted
                wire = frame.serialize()
                decoded, length = Frame.parse_frame_header(memoryview(wire[:9]))
                decoded.parse_body(memoryview(wire[9:]))
                assert decoded.stream_id == stream and decoded.data == frame.data and not decoded.flags
                assert length == len(frame.data) and len(wire) == length + 9
                packets.append(wire.hex())
            if status == 0:
                joined = b''.join(bytes.fromhex(wire)[9:] for wire in packets)
                compressed, size = struct.unpack('>BI', joined[:5])
                assert compressed == 0 and size == len(payload) and joined[5:] == payload
        cases.append(dict(index=len(cases), user=17 + len(cases), stream=stream, maximum=maximum,
                          payload=payload.hex(), frames=packets, request_maxima=maxima, grant_values=grants,
                          status=status, fault=fault))

    for size in (0, 1, 7, 54, 55, 56, 63, 64, 65, 127, 128, 16378, 16379, 16380,
                 16384, 32763, 32764, 49147, 65530, 65531, 65535):
        append(rng.randbytes(size), stream=1 + 2 * len(cases))
    for maximum in (16385, 32768, 65535, 0xffffff):
        append(rng.randbytes(65535), maximum=maximum, stream=0x7fffffff)
    for text in ('', 'hello', 'hello "world"\n', '東京 👋\u0000', 'e\u0301' * 100):
        encoded = text.encode('utf-8')
        append(b'\x0a' + varint(len(encoded)) + encoded, stream=135)
    append(b'', grant_limits=(1,))
    append(b'prefix split across small windows', grant_limits=(1, 2, 1, 3, 5))
    append(rng.randbytes(32768), grant_limits=(1, 2, 16384, 7, 8192))
    append(rng.randbytes(65536), status=2)
    append(b'must not emit', stream=0, status=1)
    append(b'must not emit', maximum=16383, status=1)
    append(rng.randbytes(257), status=3, fault='context')
    append(rng.randbytes(257), status=4, fault='abort')
    append(b'', status=4, fault='abort')
    append(b'credit contract error', status=5, fault='zero_grant')
    append(b'credit contract error', status=5, fault='large_grant')
    append(rng.randbytes(100), status=5, fault='late_zero_grant', grant_limits=(10,))
    result = dict(phase='native_references_passed', capacity=65535, cases=cases,
                  generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  native_oracle='hyperframe', native_version=importlib.metadata.version('hyperframe'),
                  valid_cases=sum(c['status'] == 0 for c in cases),
                  invalid_cases=sum(c['status'] != 0 for c in cases),
                  native_frames=sum(len(c['frames']) for c in cases), full_http2_transport_verified=False)
    (args.output / 'cases.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f"Native frame references: {result['valid_cases']} valid/{result['invalid_cases']} rejected messages, "
          f"{result['native_frames']} exact HTTP/2 frames")


if __name__ == '__main__':
    main()
