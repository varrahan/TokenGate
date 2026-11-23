"""Raw HEADERS/CONTINUATION packets, native HPACK bytes and request expectations.

The fixture supplies the initial/trailer decision that a future stream directory
must make. It does not claim to implement that directory or RPC routing.
"""
import argparse
import json
import itertools
from pathlib import Path
import random
import re

from hpack import Encoder, Decoder
from hyperframe.frame import HeadersFrame, ContinuationFrame, SettingsFrame
from h2.utilities import HeaderValidationFlags, validate_headers

MAGIC = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
KINDS = {b":method": 1, b":scheme": 2, b":path": 3, b":authority": 4,
         b"content-type": 5, b"te": 6, b"content-length": 7,
         b"grpc-encoding": 8, b"grpc-timeout": 9, b"host": 10}
TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9a-z-]+\Z")
BASE = [(b":method", b"POST"), (b":scheme", b"https"),
        (b":path", b"/example.Generate/Call"), (b":authority", b"localhost"),
        (b"te", b"trailers"), (b"content-type", b"application/grpc")]


def reference(headers, trailers=False, end_stream=False):
    """Independent whole-string/regular-expression policy, not the RTL FSM."""
    bad = False
    pseudo = {}
    ordinary = False
    ordinary_values = {}
    for name, value in headers:
        if name.startswith(b":"):
            bad |= trailers or ordinary or name not in (b":method", b":scheme", b":path", b":authority") or name in pseudo
            pseudo[name] = value
            bad |= not bool(NAME.fullmatch(name[1:]))
        else:
            ordinary = True
            bad |= not bool(NAME.fullmatch(name))
            ordinary_values.setdefault(name, []).append(value)
        bad |= any(c in (0, 10, 13, 127) or c < 32 and c != 9 for c in value)
        bad |= bool(value) and (value[:1] in (b" ", b"\t") or value[-1:] in (b" ", b"\t"))
        bad |= name in (b"connection", b"proxy-connection", b"keep-alive", b"transfer-encoding", b"upgrade")
        if name == b"te":
            bad |= not all(x.strip().lower() == b"trailers" for x in value.split(b","))
    method, scheme, path, authority = (pseudo.get(k) for k in (b":method", b":scheme", b":path", b":authority"))
    if trailers:
        bad |= not end_stream
    else:
        bad |= method is None or not bool(TOKEN.fullmatch(method or b""))
        if method == b"CONNECT":
            bad |= not authority or scheme is not None or path is not None
        else:
            bad |= scheme is None or path is None
        if scheme is not None:
            bad |= not bool(re.fullmatch(rb"[A-Za-z][A-Za-z0-9+.-]*", scheme))
        if path is not None:
            bad |= not path or any(c <= 32 or c in (35, 127) for c in path)
        if authority is not None:
            bad |= any(c <= 32 or c == 127 for c in authority)
        if (scheme or b"").lower() in (b"http", b"https"):
            bad |= not (path or b"").startswith(b"/") and not (method == b"OPTIONS" and path == b"*")
            bad |= b"@" in (authority or b"")
        if method == b"CONNECT":
            bad |= b"@" in (authority or b"")
    lengths = []
    for value in ordinary_values.get(b"content-length", []):
        for item in value.split(b","):
            item = item.strip()
            if not re.fullmatch(rb"[0-9]+", item) or int(item) > 2**64 - 1:
                bad = True
            else:
                lengths.append(int(item))
    bad |= len(set(lengths)) > 1
    # Summary fields are consumed only for accepted requests. They are still
    # recorded for successes so RTL cannot pass by merely returning a status.
    fmt, identity, timeout_valid, timeout, unit = 0, 1, 0, 0, 0
    unsupported, http_status = False, 0
    types = ordinary_values.get(b"content-type", [])
    if types:
        if len(types) != 1:
            unsupported, http_status = True, 400
        media = types[-1].split(b";", 1)[0].strip().lower()
        if media not in (b"application/grpc", b"application/grpc+proto", b"application/grpc+json"):
            unsupported, http_status, fmt = True, http_status or 415, 2
        elif media.endswith(b"+json"):
            fmt = 1
    encodings = ordinary_values.get(b"grpc-encoding", [])
    if encodings:
        identity = int(encodings[-1] == b"identity")
        if len(encodings) != 1 or not TOKEN.fullmatch(encodings[-1]):
            unsupported, http_status = True, http_status or 400
    timeouts = ordinary_values.get(b"grpc-timeout", [])
    if timeouts:
        match = re.fullmatch(rb"([0-9]{1,8})([HMSmun])", timeouts[-1])
        if len(timeouts) != 1 or not match or int(match[1]) == 0:
            unsupported, http_status = True, http_status or 400
        else:
            timeout_valid, timeout, unit = 1, int(match[1]), b"HMSmun".index(match[2])
    if not trailers:
        if method != b"POST":
            unsupported, http_status = True, http_status or 405
        elif (scheme or b"").lower() not in (b"http", b"https"):
            unsupported, http_status = True, http_status or 400
        elif not types:
            unsupported, http_status = True, http_status or 415
        elif b"te" not in ordinary_values:
            unsupported, http_status = True, http_status or 400
    return [1 if bad else 2 if unsupported else 0, 0 if bad else http_status,
            fmt, identity, int(bool(lengths)), lengths[-1] if lengths else 0,
            timeout_valid, timeout, unit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-route-cases", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []

    def emit(headers=None, *, trailers=False, end=False, mode=0, fault=-1, abort=False, check_h2=False):
        h = list(BASE if headers is None else headers)
        expected = reference(h, trailers, end)
        if check_h2:
            list(validate_headers(h, HeaderValidationFlags(False, trailers, False, False)))
        cases.append((h, trailers, end, mode, fault, abort, expected))

    def replace(name, value):
        return [(n, value if n == name else v) for n, v in BASE]

    emit(check_h2=True)
    for pseudo in itertools.permutations(BASE[:4]):
        emit([*pseudo, *BASE[4:]], check_h2=True)
    for media in (b"application/grpc+proto", b"application/grpc+json", b"Application/GRPC+JSON;charset=utf-8", b"application/grpc;v=1",
                  b"application/grpc \t ; v=1", b"application/grpc+proto\t; v=1", b"application/grpc+json \t; charset=utf-8"):
        emit(replace(b"content-type", media), check_h2=True)
    for unit in b"HMSmun":
        emit(BASE + [(b"grpc-timeout", b"99999999" + bytes([unit]))], check_h2=True)
    for value in (b"0", b"18446744073709551615", b"123, 000123", b"42,\t42,42"):
        emit(BASE + [(b"content-length", value)])
    emit(BASE + [(b"content-length", b"42"), (b"content-length", b"042")])
    for encoding in (b"identity", b"gzip", b"deflate", b"custom-codec"):
        emit(BASE + [(b"grpc-encoding", encoding)], check_h2=True)
    emit(replace(b"te", b"Trailers,\ttrailers"))
    emit(BASE + [(b"x-obs", b"\x80\xffok"), (b"x-tab", b"a\tb"), (b"x-bin", b"AA==,Zg")], check_h2=True)
    emit(BASE + [(b"x" * 200, b"q" * 17001)], check_h2=True)
    emit([], trailers=True, end=True, check_h2=True)
    emit([(b"x-final", b"ok")], trailers=True, end=True, check_h2=True)
    for name in (b"", b"X-UPPER", b"bad name", b"bad:name", b"x\x00", b":status", b":protocol", b":"):
        emit(BASE + [(name, b"ok")])
    for value in (b" leading", b"trailing ", b"\tvalue", b"value\t", b"x\x00y", b"x\ry", b"x\ny", b"x\x01y", b"x\x7fy"):
        emit(BASE + [(b"x-meta", value)])
    for name in (b"connection", b"proxy-connection", b"keep-alive", b"transfer-encoding", b"upgrade"):
        emit(BASE + [(name, b"close")])
    for name in (b":method", b":scheme", b":path", b":authority"):
        emit([BASE[0], *[(n, v) for n, v in BASE if n != name], (name, b"POST")])
        emit([(n, v) for n, v in BASE if n != name])
    for value in (b"", b"gzip", b"trailers,", b"trail ers", b"trailers,gzip", b"trailer"):
        emit(replace(b"te", value))
    for value in (b"", b"-1", b"1,2", b"18446744073709551616", b"1x", b"1 2", b",1"):
        emit(BASE + [(b"content-length", value)])
    emit(BASE + [(b"content-length", b"1"), (b"content-length", b"2")])
    emit(replace(b":method", b"GET"))
    emit(replace(b":method", b""))
    emit(replace(b":method", b"P OST"))
    emit(replace(b":scheme", b"custom+v1"))
    emit(replace(b":scheme", b"9https"))
    emit(replace(b":path", b""))
    emit(replace(b":path", b"relative"))
    emit(replace(b":path", b"/bad path"))
    emit(replace(b":path", b"/bad#fragment"))
    emit(replace(b":path", b"/valid%23path?query=yes"), check_h2=True)
    emit(replace(b":path", b"*tail"))
    emit(replace(b":authority", b"user@localhost"))
    emit([(b":method", b"CONNECT"), (b":authority", b"localhost:443")])
    emit([(b":method", b"OPTIONS"), (b":scheme", b"http"), (b":path", b"*")])
    for value in (b"text/plain", b"application/grpc+custom", b"application/grpcXYZ", b"application/grpc+jsonx", b"application/grpc x;v=1"):
        emit(replace(b"content-type", value))
    emit(BASE + [(b"content-type", b"application/grpc")])
    emit(BASE + [(b"grpc-encoding", b"gzip"), (b"grpc-encoding", b"identity")])
    emit(BASE + [(b"grpc-encoding", b"gzip,identity")])
    for value in (b"0n", b"123456789n", b"12x", b"n", b"2nn", b"1.5S", b"123"):
        emit(BASE + [(b"grpc-timeout", value)])
    emit(BASE + [(b"grpc-timeout", b"1S"), (b"grpc-timeout", b"2S")])
    emit(replace(b"content-type", b"text/plain") + [(b"x-meta", b"bad\x00value")])
    emit([(b":path", b"/bad")], trailers=True, end=True)
    emit([(b"x-final", b"ok")], trailers=True, end=False)
    # Semantic rejection followed by an indexed good block must retain HPACK.
    rng = random.Random(20261120)
    for i in range(160):
        h = replace(b":path", f"/service{i % 7}/Method{i % 11}".encode())
        h += [(b"x-persistent", f"dictionary-{i % 13}".encode()), (b"x-ordinal", str(i).encode())]
        if i % 5 == 0:
            h += [(b"connection", b"close")]
        if i % 7 == 0:
            h = [(n, b"application/grpc+json" if n == b"content-type" else v) for n, v in h]
        if i % 3 == 0:
            h += [(b"content-length", str(rng.randrange(2**40)).encode())]
        emit(h, check_h2=i % 5 != 0)
    for target in (0, 1, 4, 9):
        emit(mode=1, fault=target)
        emit(check_h2=True)
    emit(BASE + [(b"connection", b"close"), (b"x-after", b"read-fault")], mode=1, fault=20)
    emit(check_h2=True)
    for mode in (2, 3, 4, 5, 6):
        emit(mode=mode)
        emit(check_h2=True)
    if args.include_route_cases:
        for path in (b"/example.Generate/Cal", b"/example.Generate/call", b"/EXAMPLE.Generate/Call", b"/" + b"x" * 6000,
                     b"/service0/Method0", b"/service1/Method1", b"/unknown/method"):
            emit(replace(b":path", path), check_h2=True)
        for label in (b"empty", b"bad-config", b"bad-record", b"duplicate", b"reload", b"bad-pointer", b"bad-formats", b"bad-reserved", b"zero-limit"):
            emit(BASE + [(b"x-route-case", label)], check_h2=True)
            emit(check_h2=True)
        for target in (0, 3, 4, 5, 6, 7, 10, 20):
            emit(BASE + [(b"x-route-case", f"fault-{target}".encode())], check_h2=True)
            emit(check_h2=True)
    emit(BASE + [(b"connection", b"close")], abort=True)
    # Compression failure has connection scope and overrides field diagnostics.
    emit(abort=True)

    encoders = [Encoder() for _ in range(3)]
    decoders = [Decoder(max_header_list_size=262144) for _ in range(3)]
    fresh = [True] * 3
    counts = [0] * 5
    with (args.output / "vectors.txt").open("w", encoding="ascii") as out:
        for i, (headers, trailers, end, mode, fault, abort, expected) in enumerate(cases):
            ctx = i % 3
            encoded = encoders[ctx].encode(headers, huffman=bool(i & 1))
            assert list(decoders[ctx].decode(encoded, raw=True)) == headers
            # A semantic failure must not replace this connection's decoder.
            chunk = 79 if i % 3 == 0 else 8192
            pieces = [encoded[n:n+chunk] for n in range(0, len(encoded), chunk)] or [b""]
            stream_id = i * 2 + 1
            wire = MAGIC + SettingsFrame(0).serialize() if fresh[ctx] else b""
            fresh[ctx] = False
            if abort:
                # Invalid index zero after a literal prefix. No following use
                # of this connection's dictionary is made in this fixture.
                pieces[-1] += b"\x80"
            for n, piece in enumerate(pieces):
                frame = HeadersFrame(stream_id) if n == 0 else ContinuationFrame(stream_id)
                frame.data = piece
                if n == 0 and end:
                    frame.flags.add("END_STREAM")
                if n == len(pieces) - 1:
                    frame.flags.add("END_HEADERS")
                wire += frame.serialize()
            status = 4 if abort else 3 if mode else expected[0]
            counts[status] += 1
            fwd = len(headers)
            if mode == 1:
                reads = 0
                fwd = 0
                for name, value in headers:
                    reads += (len(name) + 8) // 9 + (len(value) + 8) // 9
                    if reads > fault:
                        break
                    fwd += 1
            elif mode >= 2:
                fwd = 0
            # ctx, stream, trailers, END_STREAM, mode, fault, upstream-error,
            # status, HTTP status, format, identity, length flag/value,
            # timeout flag/value/unit, forwarded count, header count, wire size.
            record = [ctx, stream_id, int(trailers), int(end), mode, fault, int(abort),
                      status, *expected[1:], fwd, len(headers), len(wire)]
            out.write(" ".join(map(str, record)) + "\n")
            out.write(" ".join(f"{b:02x}" for b in wire) + "\n")
            for name, value in headers:
                out.write(f"{len(name)} {len(value)} {KINDS.get(name, 0)}\n")
                out.write(" ".join(f"{b:02x}" for b in name + value) + "\n")
    summary = {"packets": len(cases), "status_counts": counts,
               "scope": "raw HTTP/2 through HPACK and request-field checker; fixture supplies trailer state"}
    (args.output / "fixture_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
