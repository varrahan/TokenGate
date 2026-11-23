"""Native-reference connection errors during an actual zero-window GPU return."""
import hashlib
import json
from pathlib import Path

import h2
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from h2.settings import SettingCodes
from hyperframe.frame import Frame
from generate_receive_pool_experiment import replace


def wire(kind, flags=0, stream=0, payload=b''):
    return len(payload).to_bytes(3, 'big') + bytes([kind, flags]) + stream.to_bytes(4, 'big') + payload


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'sim/cocotb/test_local_error_credit_stall.py'
    folder = root / 'build/experiments/local-protocol-cases'
    folder.mkdir(parents=True, exist_ok=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    cases = [
        ('ping_short', wire(6, payload=bytes(7)), 6),
        ('settings_ack_nonempty', wire(4, 1, payload=bytes.fromhex('000300000001')), 6),
        ('data_stream_zero', wire(0), 1),
        ('headers_stream_zero', wire(1, 4), 1),
        ('continuation_without_block', wire(9, 4, 1), 1),
        ('window_update_short', wire(8, stream=1, payload=b'\0\0\1'), 6),
        ('settings_stream_nonzero', wire(4, stream=1), 1),
    ]
    results = {}
    for name, invalid, error_code in cases:
        client = H2Connection(H2Configuration(client_side=True))
        server = H2Connection(H2Configuration(client_side=False))
        client.initiate_connection()
        server.initiate_connection()
        client.update_settings({SettingCodes.INITIAL_WINDOW_SIZE: 0})
        server.receive_data(client.data_to_send())
        client.send_headers(1, [(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
        body = b'\x0a\x0bhello world'
        client.send_data(1, b'\0' + len(body).to_bytes(4,'big') + body, end_stream=True)
        server.receive_data(client.data_to_send())
        assert server.remote_settings.initial_window_size == 0
        try:
            server.receive_data(invalid)
        except ProtocolError as error:
            native_code = int(error.error_code)
            # h2 4.4.1 maps hyperframe's nonempty SETTINGS ACK InvalidDataError
            # to generic PROTOCOL_ERROR. RFC 9113 section 6.5 requires code 6.
            assert native_code == (1 if name == 'settings_ack_nonempty' else error_code), (name, error)
        else:
            raise AssertionError(('Native reference accepted connection error',name))
        native = server.data_to_send()
        goaway = []
        while native:
            frame, size = Frame.parse_frame_header(memoryview(native[:9]))
            frame.parse_body(memoryview(native[9:9+size]))
            native = native[9+size:]
            if frame.type == 7:
                goaway.append([frame.last_stream_id,int(frame.error_code)])
        assert goaway == [[1,native_code]], (name, goaway)
        text = source.read_text()
        text = replace(text, 'from local_error_witness import LocalErrorWitness',
            'from local_error_protocol_witness import LocalProtocolErrorWitness as LocalErrorWitness')
        text = replace(text, '    close = LocalErrorWitness(d, b)', f'    close = LocalErrorWitness(d, b, {error_code})')
        text = replace(text, r"    invalid = b'\0\0\x01\0\x08\0\0\0\x01\x01'", f"    invalid = bytes.fromhex('{invalid.hex()}')")
        text = replace(text, 'assert int(error.error_code) == 1', f'assert int(error.error_code) == {native_code}')
        text = replace(text, "value(d, 'transport_packet_http2_error')) == (0, 4, 1)",
            f"value(d, 'transport_packet_http2_error')) == (0, 4, {error_code})")
        text = replace(text, '        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,',
            f"        actual_protocol_case='{name}', actual_connection_http2_error={error_code}, native_reference_http2_error={native_code}, invalid_frame_hex='{invalid.hex()}',\n"
            '        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,')
        destination = folder / name / 'test_raw_grpc_duplex.py'
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(text)
        results[name] = dict(invalid_frame_hex=invalid.hex(), expected_goaway=[[1,error_code]], native_goaway=goaway,
            native_http2_error=native_code, expected_http2_error=error_code,
            native_error_code_matches_normative_requirement=native_code==error_code,
            normative_source='https://www.rfc-editor.org/rfc/rfc9113.html#section-' + (
                '6.7' if name.startswith('ping') else '6.9' if name.startswith('window') else
                '6.1' if name.startswith('data') else '6.2' if name.startswith('headers') else
                '6.10' if name.startswith('continuation') else '6.5'), test_sha256=sha(destination))
    result = dict(phase='native_connection_error_cases_generated', generator_sha256=sha(Path(__file__)),
        input_sha256={source.relative_to(root).as_posix():sha(source),
            'sim/cocotb/local_error_protocol_witness.py':sha(root/'sim/cocotb/local_error_protocol_witness.py')},
        cases=results, native_h2_version=h2.__version__, known_native_reference_error_code_deviations=['settings_ack_nonempty'],
        actual_rtl_protocol_matrix_verified=False, full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({n:c['expected_goaway'] for n,c in results.items()}))


if __name__=='__main__':
    main()
