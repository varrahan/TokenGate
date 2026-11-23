"""Native full-vocabulary inverse and DATA references for an in-flight reset."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import ProtocolError
from hyperframe.frame import DataFrame,RstStreamFrame,GoAwayFrame
import tiktoken


def reset_references():
    headers=[(':method','POST'),(':scheme','https'),(':authority','parser.test'),(':path','/parser.Tokenize/Json')]
    cases=[]
    for name,highest,already_closed,stream in(('open',1,False,1),('duplicate',1,True,1),
        ('idle',1,True,3),('skipped_closed',5,False,3),('server_idle',5,False,2)):
        client=H2Connection(H2Configuration(client_side=True));server=H2Connection(H2Configuration(client_side=False))
        client.initiate_connection();server.initiate_connection();server.receive_data(client.data_to_send())
        client.receive_data(server.data_to_send());server.receive_data(client.data_to_send());server.data_to_send()
        client.send_headers(highest,headers);server.receive_data(client.data_to_send());server.data_to_send()
        if already_closed:
            client.reset_stream(highest,error_code=8);server.receive_data(client.data_to_send());server.data_to_send()
        frame=RstStreamFrame(stream);frame.error_code=8
        try:
            events=server.receive_data(frame.serialize());error=0
            assert not server.data_to_send()
            names=[type(event).__name__ for event in events]
        except ProtocolError as exc:
            error=int(exc.error_code);assert error==1;names=[]
        # hyper-h2 4.4.1 ignores unknown RST keys in its receive handler. Keep
        # this observed library behavior distinct from RFC 9113 section 6.4,
        # which requires a connection PROTOCOL_ERROR for an idle stream.
        assert error==0,(name,error)
        assert names==(['StreamReset']if name=='open'else []),(name,names)
        cases.append(dict(name=name,highest=highest,already_closed=already_closed,stream=stream,
            native_http2_error=error,rfc_http2_error=1 if name in('idle','server_idle')else 0,
            events=names,wire_hex=frame.serialize().hex()))
    return cases


def main():
    root=Path(__file__).resolve().parents[1];os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    folder=root/'build/bidirectional-fixtures';manifest=json.loads((folder/'fixture_manifest.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text());encoding=tiktoken.get_encoding('cl100k_base')
    text=' '*128;tokens=encoding.encode_ordinary(text);assert len(tokens)==1
    raw=encoding.decode_single_token_bytes(tokens[0]);assert raw==text.encode()
    image=b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines())
    assert hashlib.sha256(image).hexdigest()==manifest['loaded_image_sha256']
    entry=int.from_bytes(image[reverse['model_directory']['base']+tokens[0]*8:reverse['model_directory']['base']+tokens[0]*8+8],'little')
    offset=entry>>16&0xffffffff;length=entry>>48
    assert entry&2 and length==128 and image[reverse['string_pool']['base']+offset:reverse['string_pool']['base']+offset+length]==raw
    packet=json.dumps({'choices':[{'delta':{'content':text}}]},ensure_ascii=False,separators=(',',':')).encode()
    record=b'\0'+len(packet).to_bytes(4,'big')+packet;frame=DataFrame(7);frame.data=record[:100]
    result=dict(phase='native_shutdown_references_passed',model_image_sha256=manifest['loaded_image_sha256'],
        token=tokens[0],decoded_hex=raw.hex(),packet_hex=packet.hex(),first_frame_hex=frame.serialize().hex(),grant=100,
        packet_bytes=len(packet),record_bytes=len(record),native_tiktoken=importlib.metadata.version('tiktoken'),
        native_hyperframe=importlib.metadata.version('hyperframe'),native_h2=importlib.metadata.version('h2'),
        reset_cases=reset_references(),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    goaways=[]
    for last,error in((0,0),(2,11),(0x7fffffff,11)):
        frame=GoAwayFrame(0);frame.last_stream_id=last;frame.error_code=error
        goaways.append(dict(last_stream=last,error=error,wire_hex=frame.serialize().hex()))
    result['goaway_wire_cases']=goaways
    output=root/'build/http2-shutdown-fixtures';output.mkdir(parents=True,exist_ok=True)
    (output/'cases.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
