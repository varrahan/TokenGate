"""Reuse native-checked wire/payload events to test the ordered control fork."""
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys

from generate_http2_frame_vectors import MAGIC, Reference, frame
from generate_http2_transport_vectors import Payload


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'build/http2-control-fixtures';folder.mkdir(exist_ok=True)
    transport=folder/'transport'
    generator=root/'tools/generate_http2_transport_vectors.py'
    subprocess.run([sys.executable,str(generator),'--output',str(transport)],check=True)
    words=iter((transport/'vectors.txt').read_text().split())
    events=[];packets=0;controls=[]
    while (first:=next(words,None)) is not None:
        header=[int(first)]+[int(next(words))for _ in range(11)]
        for _ in range(header[6]):next(words)
        for _ in range(header[7]):
            event=[int(next(words))for _ in range(10)]
            row=event[:8]+[header[0]]
            events.append(row)
            if row[0]in(0,3)or row[0]>=4:controls.append(row)
        packets+=1
    # The inherited wire corpus has connection WINDOW_UPDATE but no valid
    # stream update. Add a native-parsed syntax case rather than inventing
    # semantic events; stream lifecycle remains the controller's responsibility.
    wire=(MAGIC+frame(4,0,struct.pack('>HIHIHI',4,65535,4,0,4,0x7fffffff))+
          frame(8,3,(128).to_bytes(4,'big'))+frame(4,0,b'',1)+
          frame(6,0,b'ctrltest')+frame(6,0,b'ctrltest',1))
    raw,_=Reference(True,False).feed(wire)
    added=Payload(True).feed(raw)
    for event in added:
        row=list(event[:8])+[37];events.append(row)
        if row[0]in(0,3)or row[0]>=4:controls.append(row)
    packets+=1
    assert any(row[0]==3 and row[5]==4 and row[6]&1 for row in controls),'Missing SETTINGS ACK'
    assert any(row[0]==5 and row[6]&1 for row in controls),'Missing PING ACK'
    assert any(row[0]==7 and row[7]==0 for row in controls) and any(row[0]==7 and row[7]!=0 for row in controls)
    hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in
        (Path(__file__),generator,root/'tools/generate_http2_frame_vectors.py')}
    result=dict(phase='native_wire_payload_references_passed',inputs_sha256=hashes,packets=packets,
        semantic_events=len(events),control_events=len(controls),events=events)
    (folder/'events.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    print(f'Control fork references: {packets} wire fragments, {len(events)} semantic events, {len(controls)} controls')


if __name__=='__main__':
    main()
