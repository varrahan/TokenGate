"""Native hyperframe references for the complete two-FPGA return workload."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

from hyperframe.frame import DataFrame, Frame, WindowUpdateFrame


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'build/bidirectional-fixtures'
    source=folder/'response_reference.json'
    references=json.loads(source.read_text())
    frames={}
    for case in references['cases']:
        for chunk in case['chunks']:
            body=bytes.fromhex(chunk['packet_hex'])
            record=b'\0'+len(body).to_bytes(4,'big')+body
            for pattern in ('normal','prefix_split'):
                grants=[];wire=[];offset=0
                while offset<len(record):
                    limit=(1,2,16384)[min(len(grants),2)] if pattern=='prefix_split' else 16384
                    size=min(limit,len(record)-offset)
                    frame=DataFrame(case['stream']);frame.data=record[offset:offset+size]
                    raw=frame.serialize()
                    parsed,length=Frame.parse_frame_header(memoryview(raw[:9]));parsed.parse_body(memoryview(raw[9:]))
                    assert parsed.data==record[offset:offset+size] and length==size and 'END_STREAM' not in parsed.flags
                    grants.append(size);wire.append(raw.hex());offset+=size
                frames[f"{case['stream']}:{body.hex()}:{pattern}"]=dict(grants=grants,wire=wire)
    control=[]
    for stream,increment in ((0,101),(references['cases'][0]['stream'],37)):
        frame=WindowUpdateFrame(stream);frame.window_increment=increment
        control.append(frame.serialize().hex())
    result=dict(phase='native_references_passed',hyperframe_version=importlib.metadata.version('hyperframe'),
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        frames=frames,window_update_wire_hex=''.join(control),
        window_updates=[[0,101],[references['cases'][0]['stream'],37]])
    (folder/'framed_reference.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Native hyperframe verified {len(frames)} return patterns and two raw WINDOW_UPDATE frames')


if __name__=='__main__':
    main()
