"""Prepare both full images and the complete native HTTP/2 corpus for XSim."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace


def varint(value):
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128); value >>= 7
    output.append(value)
    return bytes(output)


def main():
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    read = lambda path: json.loads(path.read_text())
    corpus = read(root / 'build/validation/json-simd-corpus.json')
    assert corpus['key'] == '2509134d2630b47e' and corpus['full_native_corpus_verified']
    source = root / 'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    assert all(sha(source / name) == digest for name,digest in corpus['inputs_sha256'].items())
    sys.path.insert(0,str(source / 'sim/cocotb'))
    sys.path.insert(0,str(source / 'native-vendor'))
    from test_raw_grpc_enveloped import Bench
    from h2.config import H2Configuration
    from h2.connection import H2Connection
    from hyperframe.frame import SettingsFrame
    layout = list(map(int,(source / 'build/bidirectional-fixtures/layout.txt').read_text().split()))
    original_cases = read(source / 'build/bidirectional-fixtures/reference_cases.json')['cases']
    reverse = read(source / 'build/bidirectional-fixtures/response_reference.json')
    native = root / 'build/validation/tokenizer_hyperram_two_epoch_record_capacity'
    reference = read(native / 'reference.json')
    assert reference['no_vocabulary_reduction'] and reference['image_bytes_each'] == 8388608
    assert reference['ordinary_tokens_each'] == 100256 and reference['vocabulary_entries_each'] == 100261
    assert list(map(len,reference['cases'])) == [16,16]
    assert reference['tokens_per_epoch'] == [2828,8263]
    folder = root / 'build/experiments/joint-hyperram-grpc/fixtures'
    if folder.exists():
        assert folder.is_dir() and not any(folder.iterdir()), 'Preserve existing fixture evidence'
    else:
        folder.mkdir(parents=True,exist_ok=False)
    bench = object.__new__(Bench)
    bench.d = SimpleNamespace(cfg_receive_connection_base=0)
    bench.layout = layout; bench.reverse = reverse
    collected = {}
    bench.set = lambda **values: collected.update(values)
    bench.configure(); base = dict(collected); collected.clear()
    bench.response_configuration(0); response = dict(collected); collected.clear()
    bench.poison(); poison = dict(collected)
    defaults = {}
    fixture_text = (source / 'sim/cocotb_two_fpga_enveloped_top.sv').read_text()
    for name,value in re.findall(r'\breg\s+(?:\[[^\]]+\]\s*)?(\w+)\s*=\s*(\d+)\s*;',fixture_text):
        defaults[name] = int(value)
    assert defaults['cfg_token_profile'] == 0  # CL100K; LLAMA3 is profile 1.
    # Construct native requests with the same SETTINGS and flow-control setup.
    # A synthetic peer SETTINGS only queues the client's first empty ACK here.
    # Post-simulation verification must rebuild requests against ACTUAL hardware
    # SETTINGS and compare the request bytes before accepting the run.
    vectors = []
    epochs = []
    for epoch,cases in enumerate(reference['cases']):
        client = H2Connection(H2Configuration(client_side=True,header_encoding='utf8'))
        client.initiate_connection(); client.update_settings({4:1 << 20}); client.increment_flow_control_window(1 << 20)
        initial = client.data_to_send()
        peer = SettingsFrame(0); peer.settings = {1:4096,5:16384,6:32768}
        client.receive_data(peer.serialize())
        values = [len(initial),*initial,len(cases)]
        summaries = []
        for index,case in enumerate(cases):
            prompt = bytes.fromhex(case['prompt_hex'])
            assert case['prompt_hex'] == original_cases[index]['prompt_utf8_hex']
            if epoch == 0: assert case['token_ids'] == original_cases[index]['token_ids']
            stream = 2 * index + 1; mode = 2 if index & 1 else 0; application = 100 + int(mode == 2)
            body = json.dumps({'prompt':prompt.decode('utf8')},ensure_ascii=False,separators=(',',':')).encode() if mode == 0 else b'\x0a' + varint(len(prompt)) + prompt
            client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
                (':path','/parser.Tokenize/Proto' if mode == 2 else '/parser.Tokenize/Json'),
                ('content-type','application/grpc+proto' if mode == 2 else 'application/grpc+json'),('te','trailers')])
            record = b'\0' + len(body).to_bytes(4,'big') + body
            for offset in range(0,len(record),16384):
                client.send_data(stream,record[offset:offset + 16384],end_stream=offset + 16384 >= len(record))
            raw = client.data_to_send(); ids = case['token_ids']
            assert 0 < len(ids) <= 16384 and len(raw) < 32768
            values += [index,stream,mode,application,len(raw),len(ids),*raw,*ids]
            summaries.append(dict(index=index,stream=stream,mode=mode,application=application,
                prompt_bytes=len(prompt),raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),
                tokens=len(ids),native_token_ids=ids,raw_request_hex=raw.hex()))
        target = folder / ('epoch' + str(epoch) + '.vectors')
        target.write_text(' '.join(map(str,values)) + '\n')
        image = native / ('image' + str(epoch) + '.bin')
        assert image.stat().st_size == 8388608 and sha(image) == reference['image_sha256'][epoch]
        shutil.copy2(image,folder / image.name)
        epochs.append(dict(model_epoch=23 + epoch,initial_request_hex=initial.hex(),cases=summaries,
                           image_sha256=reference['image_sha256'][epoch]))
    image = b''.join(int(word,16).to_bytes(8,'little') for word in (source / 'build/bidirectional-fixtures/memory.mem').read_text().splitlines())
    assert len(image) == 8388608
    (folder / 'parser-image.bin').write_bytes(image)
    result = dict(phase='complete_joint_hyperram_grpc_vectors_prepared',
        parent_corpus_audit_key=corpus['key'],tokenizer_functional_audit_key='cac956b2d9ecf6f9',
        generator_sha256=sha(Path(__file__)),layout=layout,defaults=defaults,
        base_configuration=base,response_configuration=response,poison_configuration=poison,
        epochs=epochs,sequences=32,expected_actual_dma_ids=11091,complete_image_bytes_each=8388608,
        parser_initial_image_sha256=hashlib.sha256(image).hexdigest(),protected_model_bytes=layout[6],
        hardware_dma_ids_must_supply_gpu_returns=True,actual_hardware_settings_must_be_replayed=True,
        configuration_methods_executed_offline_without_dut=True,
        hardware_simulation_verified=False,full_system_complete=False,
        fixture_sha256={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
    (folder / 'reference.json').write_text(json.dumps(result,indent=2) + '\n')
    shutil.copy2(Path(__file__),folder / Path(__file__).name)
    print(json.dumps({name:result[name] for name in ('phase','sequences','expected_actual_dma_ids','complete_image_bytes_each')}))


if __name__ == '__main__':
    main()
