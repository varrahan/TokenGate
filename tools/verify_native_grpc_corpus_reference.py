"""Independently reconstruct the complete native gRPC corpus from tiktoken."""
import codecs
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

import tiktoken


def varint(number):
    encoded = bytearray()
    while number > 127:
        encoded.append((number & 127) | 128)
        number >>= 7
    encoded.append(number)
    return bytes(encoded)


def verify_reference(root, source, accepted, *, parser_memory_clients=17, native_wire_frames=2863):
    root, source = Path(root), Path(source)
    fixture = source / 'build/bidirectional-fixtures'
    layout = list(map(int, (fixture / 'layout.txt').read_text().split()))
    manifest = json.loads((fixture / 'fixture_manifest.json').read_text())
    references = json.loads((fixture / 'reference_cases.json').read_text())['cases']
    reverse = json.loads((fixture / 'response_reference.json').read_text())['cases']
    loaded = b''.join(int(word, 16).to_bytes(8, 'little') for word in (fixture / 'memory.mem').read_text().splitlines())
    original = (root / 'build/scu35/image/external_memory.bin').read_bytes()
    digest = lambda data: hashlib.sha256(data).hexdigest()
    assert digest(original) == 'c78a595768d15967d1490cae21a1f37ecf326c46ba6a119d4f6f7fc00c01d10c'
    assert len(loaded) == len(original) == 8 * 1024 * 1024
    assert digest(loaded) == manifest['loaded_image_sha256']
    assert layout[6] == 6903552 and loaded[:layout[6]] == original[:layout[6]]
    assert accepted['phase'] == 'passed'
    names = ('native_complete_grpc_calls', 'actual_forward_dma_ids', 'actual_captured_dma_ids_returned',
             'actual_gpu_descriptors_accepted', 'actual_header_bindings', 'parser_memory_clients', 'tokenizer_memory_clients')
    assert tuple(accepted[n] for n in names) == (16, 2828, 2828, 2828, 16, parser_memory_clients, 9)
    assert accepted['native_wire_frames'] == native_wire_frames and accepted['actual_raw_packets'] == 17
    for name in ('native_request_and_response_endpoints', 'actual_peer_settings_and_window_updates',
                 'original_prompt_corpus_verified', 'json_and_protobuf_response_fields_verified',
                 'complete_model_prefix_immutable', 'explicit_host_directory_retirement'):
        assert accepted[name], name
    for name in ('sse_transport_verified', 'receive_flow_control_verified', 'whole_rpc_gpu_image_lease_verified',
                 'physical_interfaces_verified', 'full_system_complete'):
        assert accepted[name] is False, name
    os.environ['TIKTOKEN_CACHE_DIR'] = str(root / 'build/tiktoken-cache')
    encoding = tiktoken.get_encoding('cl100k_base')
    assert len(encoding._mergeable_ranks) == 100256
    calls = accepted['native_grpc_calls']
    assert len(calls) == len(references) == len(reverse) == 16
    verified = []
    for index, (call, reference, response) in enumerate(zip(calls, references, reverse)):
        text = bytes.fromhex(reference['prompt_utf8_hex']).decode('utf8')
        ids = encoding.encode_ordinary(text)
        assert ids == reference['token_ids']
        mode = 2 if index & 1 else 0
        assert (call['reference_index'], call['stream'], call['format'], call['tokens']) == (index, 2 * index + 1, mode, len(ids))
        chunks = response['chunks']; assert len(chunks) == len(ids)
        decoder = codecs.getincrementaldecoder('utf8')('replace')
        records = bytearray()
        for ordinal, (token, chunk) in enumerate(zip(ids, chunks)):
            raw = encoding.decode_single_token_bytes(token)
            assert chunk['token'] == token and bytes.fromhex(chunk['bow_hex']) == raw
            decoded = decoder.decode(raw, final=ordinal + 1 == len(ids))
            if mode == 0:
                payload = json.dumps({'choices': [{'delta': {'content': decoded}}]},
                    ensure_ascii=False, separators=(',', ':')).encode('utf8')
            else:
                data = decoded.encode('utf8')
                payload = varint((17 << 3) | 2) + varint(len(data)) + data
            records.extend(b'\x00' + len(payload).to_bytes(4, 'big') + payload)
        assert len(records) == call['response_record_bytes'] and digest(records) == call['response_sha256']
        verified.append(dict(reference_index=index, native_tokens=len(ids), response_bytes=len(records), response_sha256=digest(records)))
    assert sum(call['native_tokens'] for call in verified) == 2828
    return dict(independent_reference_verified=True, native_tokenizer='tiktoken', native_tokenizer_version=version('tiktoken'),
        encoding='cl100k_base', complete_mergeable_vocabulary_entries=100256, protected_model_bytes=layout[6],
        model_image_sha256=digest(original), loaded_image_sha256=digest(loaded), calls=verified,
        full_system_complete=False)
