"""Exercise payload semantic errors and later journal/control failures."""
import hashlib
import json
from pathlib import Path

import h2
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from hyperframe.frame import Frame
from generate_local_protocol_cases import wire
from generate_receive_pool_experiment import replace

from rtl_paths import source_relative


def main():
    root = Path(__file__).resolve().parents[1]
    source = root/'sim/cocotb/test_local_error_credit_stall.py'
    folder = root/'build/experiments/local-semantic-cases'
    folder.mkdir(parents=True,exist_ok=True)
    sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    results = {}
    for name,invalid,error_code,native_code,section,packet_status in (
        ('initial_window_overflow',wire(4,payload=bytes.fromhex('000480000000')),3,3,'6.5.2',4),
        ('max_frame_too_small',wire(4,payload=bytes.fromhex('000500003fff')),1,1,'6.5.2',4),
        ('rst_idle_stream',wire(3,stream=3,payload=(8).to_bytes(4,'big')),1,None,'6.4',11),
        ('connection_window_overflow',wire(8,payload=(0x7fffffff).to_bytes(4,'big')),3,3,'6.9.1',11)):
        client = H2Connection(H2Configuration(client_side=True))
        server = H2Connection(H2Configuration(client_side=False))
        client.initiate_connection();server.initiate_connection()
        client.update_settings({4:0});server.receive_data(client.data_to_send())
        client.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Tokenize/Proto'),('content-type','application/grpc+proto'),('te','trailers')])
        body=b'\x0a\x0bhello world'
        client.send_data(1,b'\0'+len(body).to_bytes(4,'big')+body,end_stream=True)
        server.receive_data(client.data_to_send())
        caught = None
        try:server.receive_data(invalid)
        except ProtocolError as error:caught=int(error.error_code)
        assert caught == native_code,(name,caught)
        pending = server.data_to_send();goaway=[]
        while pending:
            frame,size=Frame.parse_frame_header(memoryview(pending[:9]));frame.parse_body(memoryview(pending[9:9+size]));pending=pending[9+size:]
            if frame.type==7:goaway.append([frame.last_stream_id,int(frame.error_code)])
        assert goaway == ([] if native_code is None else [[1,native_code]])
        text = source.read_text()
        text = replace(text,'from local_error_witness import LocalErrorWitness',
            'from local_semantic_error_witness import LocalSemanticErrorWitness as LocalErrorWitness')
        text = replace(text,'    close = LocalErrorWitness(d, b)',f"    close = LocalErrorWitness(d, b, {error_code}, '{name}')")
        text = replace(text,r"    invalid = b'\0\0\x01\0\x08\0\0\0\x01\x01'",f"    invalid = bytes.fromhex('{invalid.hex()}')")
        if native_code is None:
            text = replace(text,'assert int(error.error_code) == 1',"raise AssertionError('Native reference unexpectedly rejected idle RST')")
            text = replace(text,"raise AssertionError('Native server accepted invalid padding')",'pass  # Installed h2 ignores this; RFC 9113 6.4 requires a connection error.')
        else:
            text = replace(text,'assert int(error.error_code) == 1',f'assert int(error.error_code) == {native_code}')
        text = replace(text,"value(d, 'transport_packet_http2_error')) == (0, 4, 1)",
            f"value(d, 'transport_packet_http2_error')) == (0, {packet_status}, {error_code})")
        text = replace(text,"failure = dict(phase='fatal_credit_park_deadlock', actual_native_initial_stream_window=0,",
            "failure = close.diagnostic('late_semantic_connection_error_not_completed')\n        failure.update(actual_native_initial_stream_window=0,")
        text = replace(text,'    proof = close.result()',
            "    proof = close.result()\n    retired_header = image[address:address+8].hex()\n"
            "    if retired_header != '0000000000000000':\n"
            "        failure = close.diagnostic('late_semantic_error_left_active_rpc')\n"
            "        failure.update(local_error_ownership=proof, actual_cancel_trace=trace)\n"
            "        Path('failure.json').write_text(json.dumps(failure,indent=2)+'\\n')\n"
            "        raise AssertionError(failure)")
        text = replace(text,'        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,',
            f"        actual_semantic_case='{name}', actual_connection_http2_error={error_code}, native_reference_http2_error={native_code!r},\n"
            "        actual_rpc_header_after_fatal_hex=retired_header,\n"
            '        actual_goaway_after_gpu_retirement=True, complete_model_prefix_immutable=True,')
        destination=folder/name/'test_raw_grpc_duplex.py';destination.parent.mkdir(exist_ok=True);destination.write_text(text)
        results[name]=dict(invalid_frame_hex=invalid.hex(),expected_http2_error=error_code,expected_packet_status=packet_status,
            expected_detection_stage='payload' if packet_status==4 else 'control',
            native_http2_error=native_code,native_goaway=goaway,expected_goaway=[[1,error_code]],
            normative_source='https://www.rfc-editor.org/rfc/rfc9113.html#section-'+section,test_sha256=sha(destination))
    paths=[source,root/'sim/cocotb/local_semantic_error_witness.py',root/'sim/cocotb/local_error_protocol_witness.py',root/'tools/generate_local_protocol_cases.py']
    result=dict(phase='late_semantic_error_cases_generated',generator_sha256=sha(Path(__file__)),
        input_sha256={source_relative(p, root).as_posix():sha(p) for p in paths},native_h2_version=h2.__version__,
        cases=results,known_native_reference_deviations=['rst_idle_stream'],actual_rtl_cases_verified=False,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({n:dict(expected=c['expected_http2_error'],native=c['native_http2_error']) for n,c in results.items()}))


if __name__=='__main__':main()
