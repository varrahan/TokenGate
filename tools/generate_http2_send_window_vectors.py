"""Native hyper-h2 outbound-window reference sequence over three live streams."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.exceptions import FlowControlError
from h2.settings import SettingCodes


def main():
    root=Path(__file__).resolve().parents[1];folder=root/'build/http2-send-window-fixtures';folder.mkdir(exist_ok=True)
    original=root/'build/scu35/image/external_memory.bin'
    client=H2Connection(H2Configuration(client_side=True,header_encoding='utf-8'))
    server=H2Connection(H2Configuration(client_side=False,header_encoding='utf-8'))
    client.initiate_connection();server.initiate_connection();server.receive_data(client.data_to_send());client.receive_data(server.data_to_send());server.receive_data(client.data_to_send())
    cases=[];opened=[]

    def record(op,stream=0,amount=0,status=0,grant=0,affected=0,**extra):
        cases.append(dict(op=op,stream=stream,amount=amount,status=status,grant=grant,
            connection_window=server.outbound_flow_control_window,
            stream_window=server.streams[stream].outbound_flow_control_window if stream else 0,
            initial_window=server.remote_settings.initial_window_size,max_frame=server.max_outbound_frame_size,
            affected=affected,**extra))

    def open_stream(stream):
        client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','window.test'),(':path','/generate'),('content-type','application/grpc')],end_stream=True)
        server.receive_data(client.data_to_send());server.send_headers(stream,[(':status','200'),('content-type','application/grpc')])
        client.receive_data(server.data_to_send());opened.append(stream);record(1,stream,open=True)

    def reserve(stream,maximum):
        size=max(0,min(maximum,server.max_outbound_frame_size,server.local_flow_control_window(stream)))
        if size:server.send_data(stream,bytes(size));client.receive_data(server.data_to_send())
        record(5,stream,maximum,status=int(size==0),grant=size)

    def setting(identifier,value):
        client.update_settings({identifier:value});server.receive_data(client.data_to_send());client.receive_data(server.data_to_send())
        record(3 if identifier==SettingCodes.INITIAL_WINDOW_SIZE else 4,amount=value,affected=len(opened) if identifier==SettingCodes.INITIAL_WINDOW_SIZE else 0)

    def update(stream,increment):
        client.increment_flow_control_window(increment,stream_id=stream or None)
        server.receive_data(client.data_to_send());record(2,stream,increment)

    record(0)
    open_stream(1);open_stream(3)
    remaining=60000
    while remaining:
        before=server.outbound_flow_control_window;reserve(1,remaining)
        remaining-=before-server.outbound_flow_control_window
    setting(SettingCodes.INITIAL_WINDOW_SIZE,16384)
    record(6,1);record(6,3)
    assert server.streams[1].outbound_flow_control_window==-43616
    reserve(1,100);update(1,43617);reserve(1,100)
    reserve(3,20000);reserve(3,20000);update(0,20000);reserve(3,20000)
    setting(SettingCodes.INITIAL_WINDOW_SIZE,0)
    open_stream(5);reserve(5,100);update(5,1);reserve(5,100)
    setting(SettingCodes.MAX_FRAME_SIZE,65536)
    setting(SettingCodes.INITIAL_WINDOW_SIZE,70000)
    update(0,1000000);reserve(1,0xffffff)
    update(5,0x7fffffff-server.streams[5].outbound_flow_control_window)
    # The last slot overflows only after two other live windows were updated.
    client.update_settings({SettingCodes.INITIAL_WINDOW_SIZE:70001})
    try:server.receive_data(client.data_to_send())
    except FlowControlError as error:
        assert int(error.error_code)==3
    else:raise AssertionError('Native h2 accepted an overflowing initial-window change')
    cases.append(dict(op=3,stream=0,amount=70001,status=4,http2_error=3,connection_error=1,recovery=True,affected=2))
    result=dict(phase='native_send_window_references_passed',h2_version=importlib.metadata.version('h2'),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_image_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        layout=dict(context_base=0x700000,context_bytes=768,stream_base=0x710000,stream_bytes=512,
            window_base=0x720000,window_bytes=64,work_floor=0x695700),
        cases=cases,streams=opened)
    assert original.stat().st_size==8388608
    shutil.copy2(original,folder/'model.bin')
    (folder/'cases.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Native hyper-h2 verified {len(cases)} window commands, signed starvation/recovery, three-stream settings and overflow')


if __name__=='__main__':
    main()
