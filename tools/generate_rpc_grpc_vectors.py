"""Keep the complete vocabulary; add unused-slot capacity cases and native frames."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from hyperframe.frame import DataFrame, Frame
from generate_rpc_response_vectors import packet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(root / 'tools/generate_rpc_response_vectors.py'), '--output', str(args.output)], check=True)
    reference = json.loads((args.output / 'rpc_cases.json').read_text())
    manifest = json.loads((args.output / 'model_manifest.json').read_text())
    original = (args.output / 'memory.bin').read_bytes()
    memory = bytearray(original)
    pool = reference['layout']['pool_base']
    directory = reference['layout']['directory_base']
    pool_offset = 900000
    capacity_tokens = []
    for index, length in enumerate((16384, 16385)):
        token = 120000 + index
        assert directory + (token + 1) * 8 <= directory + reference['layout']['directory_bytes']
        assert struct.unpack_from('<Q', original, directory + token * 8)[0] == 0
        struct.pack_into('<Q', memory, directory + token * 8, 2 | pool_offset << 16 | length << 48)
        capacity_tokens.append(token)
    memory[pool + pool_offset:pool + pool_offset + 16385] = bytes(16385)
    # The original native compiler checked every ordinary token. All of its
    # used model regions must remain byte-identical after adding reserved slots.
    for region in manifest['regions']:
        start, size = region['base'], region['bytes']
        if region['name'] == 'directory':
            restored = bytearray(memory[start:start + size])
            for token in capacity_tokens:
                restored[token * 8:token * 8 + 8] = original[start + token * 8:start + token * 8 + 8]
            assert restored == original[start:start + size], 'Original populated directory entry changed'
        else:
            assert memory[start:start + size] == original[start:start + size], region['name']
        if region['name'] == 'string_pool':
            region['bytes'] = max(size, pool_offset + 16385)
        region['sha256'] = hashlib.sha256(memory[start:start + region['bytes']]).hexdigest()
    reference['original_complete_image_sha256'] = reference['model_image_sha256']
    reference['model_image_sha256'] = hashlib.sha256(memory).hexdigest()
    reference['capacity_tokens'] = capacity_tokens
    manifest['image_sha256'] = reference['model_image_sha256']
    (args.output / 'memory.bin').write_bytes(memory)
    (args.output / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (args.output / 'rpc_cases.json').write_text(json.dumps(reference, indent=2) + '\n')
    frames = {}

    def add(stream, body):
        key = str(stream) + ':' + body.hex()
        if key in frames:
            return
        record = b'\x00' + struct.pack('>I', len(body)) + body
        offset = 0
        wire, maxima, grants = [], [], []
        while offset < len(record):
            limit = min(16384, len(record) - offset)
            grant = min(limit, (1, 2, 7, 16384)[len(grants) % 4])
            frame = DataFrame(stream_id=stream)
            frame.data = record[offset:offset + grant]
            serialized = frame.serialize()
            decoded, length = Frame.parse_frame_header(memoryview(serialized[:9]))
            decoded.parse_body(memoryview(serialized[9:]))
            assert decoded.data == frame.data and decoded.stream_id == stream and length == grant
            wire.append(serialized.hex()); maxima.append(limit); grants.append(grant)
            offset += grant
        assert b''.join(bytes.fromhex(value)[9:] for value in wire) == record
        frames[key] = dict(frames=wire, maxima=maxima, grants=grants, body=body.hex(), complete=True)

    for group in reference['groups']:
        for binding in group:
            for chunk in binding['chunks']:
                add(binding['stream'], bytes.fromhex(chunk['packet_hex']))
    add(1, bytes.fromhex(reference['ascii_packet_hex']))
    capacity = []
    for mode in (0, 2):
        body = packet(bytes(16384), mode, 17)
        add(1, body)
        capacity.append(dict(mode=mode, token=capacity_tokens[0], decoded_bytes=16384, packet_hex=body.hex(), bow_hex=bytes(16384).hex()))
    body = bytes.fromhex(reference['ascii_packet_hex'])
    record = b'\x00' + struct.pack('>I', len(body)) + body
    first = DataFrame(stream_id=1); first.data = record[:1]
    result = dict(phase='native_references_passed', frames=frames, capacity_cases=capacity,
        original_used_model_regions_unchanged=True, ordinary_entries_verified=100256,
        original_complete_image_sha256=reference['original_complete_image_sha256'],
        model_image_sha256=reference['model_image_sha256'],
        zero_grant=dict(frames=[], maxima=[len(record)], grants=[0], body='', complete=False),
        late_zero_grant=dict(frames=[first.serialize().hex()], maxima=[len(record), len(record) - 1], grants=[1, 0], body='', complete=False),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output / 'frame_cases.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Native framed RPC references: {len(frames)} unique payload/stream pairs, full ordinary vocabulary unchanged')


if __name__ == '__main__':
    main()
