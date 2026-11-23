"""Native HPACK frames and complete hyper-h2 gRPC response exchanges."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

from h2.config import H2Configuration
from h2.connection import H2Connection
from hpack import Decoder,Encoder
from hyperframe.frame import DataFrame,HeadersFrame


TYPES=('application/grpc','application/grpc+proto','application/grpc+json')


def wire(kind,encoding,status,stream):
    fields=[]
    if kind!=1:fields+=[(':status','200'),('content-type',TYPES[encoding],True)]
    if kind!=0:fields+=[('grpc-status',str(status),True)]
    encoder=Encoder();block=encoder.encode(fields,huffman=False)
    assert not encoder.header_table.dynamic_entries
    decoder=Decoder();decoder.max_allowed_table_size=0;decoder.header_table_size=0
    decoded=decoder.decode(block);assert decoded==[(f[0],f[1])for f in fields]
    assert not decoder.header_table.dynamic_entries
    frame=HeadersFrame(stream);frame.flags.add('END_HEADERS');frame.data=block
    if kind:frame.flags.add('END_STREAM')
    raw=frame.serialize();assert len(raw)<64
    return raw


def client(encoding):
    caller=H2Connection(H2Configuration(client_side=True,header_encoding='utf-8'))
    server=H2Connection(H2Configuration(client_side=False,header_encoding='utf-8'))
    caller.initiate_connection();server.initiate_connection();server.receive_data(caller.data_to_send())
    caller.receive_data(server.data_to_send());server.receive_data(caller.data_to_send());server.data_to_send()
    caller.send_headers(1,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Generate/Stream'),('content-type',TYPES[encoding]),('te','trailers')],end_stream=True)
    server.receive_data(caller.data_to_send());return caller


def main():
    root=Path(__file__).resolve().parents[1];cases=[];exchanges=[]
    for encoding in range(3):
        initial=wire(0,encoding,0,1)
        cases.append(dict(kind=0,encoding=encoding,status=0,stream=1,wire_hex=initial.hex()))
        for status in range(17):
            trailers=wire(1,encoding,status,1)
            cases.append(dict(kind=1,encoding=encoding,status=status,stream=1,wire_hex=trailers.hex()))
            body=b'{"text":"hello"}'if encoding==2 else b'\x0a\x05hello'
            data=DataFrame(1);data.data=b'\0'+len(body).to_bytes(4,'big')+body
            caller=client(encoding);events=caller.receive_data(initial+data.serialize()+trailers)
            assert [type(e).__name__ for e in events]==['ResponseReceived','DataReceived','TrailersReceived','StreamEnded']
            assert events[0].headers==[(':status','200'),('content-type',TYPES[encoding])]
            assert events[1].data==data.data and events[2].headers==[('grpc-status',str(status))]
            exchanges.append(dict(encoding=encoding,status=status,wire_hex=(initial+data.serialize()+trailers).hex(),
                events=[type(e).__name__ for e in events],body_hex=body.hex(),trailers_only=False))
            if status:
                only=wire(2,encoding,status,1);cases.append(dict(kind=2,encoding=encoding,status=status,stream=1,wire_hex=only.hex()))
                events=client(encoding).receive_data(only)
                assert [type(e).__name__ for e in events]==['ResponseReceived','StreamEnded']
                assert events[0].headers==[(':status','200'),('content-type',TYPES[encoding]),('grpc-status',str(status))]
                exchanges.append(dict(encoding=encoding,status=status,wire_hex=only.hex(),events=[type(e).__name__ for e in events],trailers_only=True))
    # Independent high-bit stream IDs and a sparse set of user contexts exercise
    # every header byte without a connection-specific encoder table.
    for stream in(3,127,65537,0x40000001,0x7fffffff):
        for kind,status in((0,0),(1,0),(1,16),(2,13)):
            cases.append(dict(kind=kind,encoding=2,status=status,stream=stream,wire_hex=wire(kind,2,status,stream).hex()))
    result=dict(phase='native_grpc_header_references_passed',cases=cases,exchanges=exchanges,
        native_packages={p:importlib.metadata.version(p)for p in('h2','hpack','hyperframe')},
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        stateless_encoder_and_zero_dynamic_decoder_verified=True,normal_and_trailers_only_exchange_verified=True,
        protocol_reference='https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md#responses',full_system_complete=False)
    folder=root/'build/grpc-header-fixtures';folder.mkdir(parents=True,exist_ok=True)
    (folder/'cases.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Generated {len(cases)} native header frames and {len(exchanges)} complete native exchanges')


if __name__=='__main__':main()
