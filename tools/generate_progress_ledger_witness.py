"""Extend the frozen RX/TX witness with the new progress-error result."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'sim/cocotb/window_format_witness.py';text=source.read_text()
    text=text.replace('class WindowFormatWitness:','class ProgressLedgerWindowWitness:')
    needle="                    elif result[2]==0x75:"
    assert text.count(needle)==1
    text=text.replace(needle,"""                    elif result[:3]==(5,18,0x75):
                        for key in ('26','22'):
                            assert len(r['acks'][key])*8==r['sizes'][key]
                            assert all(a['status']==0 for a in r['acks'][key])
                    elif result[2]==0x75:""")
    target=root/'sim/cocotb/progress_ledger_window_witness.py';target.write_text(text)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),witness_sha256=sha(target))
    folder=root/'build/experiments/progress-format';folder.mkdir(parents=True,exist_ok=True)
    (folder/'ledger-witness-generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
