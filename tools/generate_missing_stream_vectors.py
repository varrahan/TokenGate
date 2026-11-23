"""Native hyper-h2 idle/closed WINDOW_UPDATE decisions after actual HEADERS/RST."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from hyperframe.frame import WindowUpdateFrame


def main():
    root=Path(__file__).resolve().parents[1];cases=[]
    headers=[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json')]
    for highest in(0,1,5,127,0x7fffffff):
        candidates={1,2,3,4,5,127,129,0x7ffffffe,0x7fffffff}
        if highest:candidates.add(highest)
        if highest>2:candidates.add(highest-2)
        if highest<0x7ffffffd:candidates.add(highest+2 or 2)
        for stream in sorted(candidates):
            client=H2Connection(H2Configuration(client_side=True));server=H2Connection(H2Configuration(client_side=False))
            client.initiate_connection();server.initiate_connection();server.receive_data(client.data_to_send())
            client.receive_data(server.data_to_send());server.receive_data(client.data_to_send());server.data_to_send()
            if highest:
                client.send_headers(highest,headers);server.receive_data(client.data_to_send())
                client.reset_stream(highest,error_code=8);server.receive_data(client.data_to_send())
            assert server.highest_inbound_stream_id==highest
            frame=WindowUpdateFrame(stream);frame.window_increment=1
            try:
                events=server.receive_data(frame.serialize());assert not events and not server.data_to_send();closed=True;error=0
            except ProtocolError as exc:closed=False;error=int(exc.error_code);assert error==1
            assert closed==bool(stream&1 and stream<=highest)
            cases.append(dict(last_stream=highest,stream=stream,closed=closed,http2_error=error,wire_hex=frame.serialize().hex()))
    result=dict(phase='native_missing_stream_references_passed',cases=cases,
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),packages={p:importlib.metadata.version(p)for p in('h2','hyperframe')},
        actual_headers_and_rst_used=True,server_initiated_streams_absent=True,full_system_complete=False)
    target=root/'build/http2-classifier-fixtures/cases.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2)+'\n')
    print(f'Generated {len(cases)} native missing-key WINDOW_UPDATE references')


if __name__=='__main__':main()
