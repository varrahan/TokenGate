"""Isolate removal of foreign-domain reset gates from packet handshakes."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'rtl/cdc_packet_fifo.v';text=source.read_text()
    assert sha(source)=='ad474cf5bf282d2819eb014370ba211f8e5fb698af245eea17b826386b3c1098'
    assert text.count('.SRC_INPUT_REG(0)')==2
    text=text.replace('.SRC_INPUT_REG(0)','.SRC_INPUT_REG(1)')
    for domain,signal in(('s','!source_up||!destination_up_s'),('m','!destination_up||!source_up_m')):
        old=f'assign {domain}_reset=reset_request||{signal};'
        assert text.count(old)==1
        text=text.replace(old,f'assign {domain}_reset={signal};')
    text=text.replace('// Full-packet CDC using the native AMD asynchronous FIFO.',
        '// Isolated qualified-reset experiment: no raw reset in data handshake gates.\n// Reset assertion/release is local-clock qualified; reset_request aborts outstanding work.\n// Full-packet CDC using the native AMD asynchronous FIFO.')
    folder=root/'build/experiments/hyperram-cdc-qualified-reset';(folder/'rtl').mkdir(parents=True,exist_ok=True)
    output=folder/'rtl/cdc_packet_fifo.v';output.write_text(text)
    result=dict(generator_sha256=sha(Path(__file__)),parent_sha256=sha(source),output_sha256=sha(output),
        source_readiness_registered_before_cdc=True,raw_reset_removed_from_handshake_gates=True,
        primary_rtl_modified=False,functional_verification_complete=False,native_verification_complete=False,
        shared_domain_reset_fanout_review_pending=True,full_system_complete=False)
    (folder/'generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
