"""Native HTTP/2/HPACK packets for the real Parser/control/TX join."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

import hpack
from hyperframe.frame import HeadersFrame,SettingsFrame,PingFrame,WindowUpdateFrame


def main():
    root=Path(__file__).resolve().parents[1];preface=b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
    settings=SettingsFrame(0);settings.settings={1:4096,4:1000,5:32768,65000:42}
    ping=PingFrame(0);ping.opaque_data=b'journal!'
    header=HeadersFrame(1);header.flags.add('END_HEADERS')
    fields=[(b':method',b'POST'),(b':scheme',b'https'),(b':path',b'/parser.Tokenize/Json'),
        (b':authority',b'parser.test'),(b'content-type',b'application/grpc+json'),(b'te',b'trailers'),(b'content-length',b'0')]
    header.data=hpack.Encoder().encode(fields,huffman=True)
    assert hpack.Decoder().decode(header.data,raw=True)==fields
    stream=WindowUpdateFrame(1);stream.window_increment=37
    connection=WindowUpdateFrame(0);connection.window_increment=101
    changed=SettingsFrame(0);changed.settings={4:2000,5:16384,1:2048};wire=changed.serialize();cut=16
    ack=SettingsFrame(0);ack.flags.add('ACK');pingack=PingFrame(0);pingack.flags.add('ACK');pingack.opaque_data=ping.opaque_data
    empty=SettingsFrame(0)
    value=dict(phase='native_raw_control_references_passed',initial_packet=(preface+settings.serialize()+ping.serialize()).hex(),
        headers_packet=header.serialize().hex(),update_packet=(stream.serialize()+connection.serialize()).hex(),
        settings_first=wire[:cut].hex(),settings_last=wire[cut:].hex(),ping_packet=ping.serialize().hex(),
        restore_fault_packet=(ping.serialize()*6).hex(),
        abort_packet=(stream.serialize()+b'\0\0\x07\x06\0'+bytes(4)+b'1234567').hex(),
        reopen_preface=(preface+empty.serialize()).hex(),settings_ack=ack.serialize().hex(),ping_ack=pingack.serialize().hex(),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        packages={p:importlib.metadata.version(p)for p in('hpack','hyperframe')},full_system_complete=False)
    output=root/'build/bidirectional-fixtures/journaled_control_reference.json';output.write_text(json.dumps(value,indent=2)+'\n')
    print('Generated native raw controls/HPACK and exact SETTINGS/PING ACK references')


if __name__=='__main__':main()
