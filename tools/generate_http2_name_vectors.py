"""Whole-string header policy references, independent of ROM layout/search."""
import argparse
import hashlib
import json
from pathlib import Path
import random
from generate_http2_request_vectors import KINDS

FORBIDDEN={b'connection',b'proxy-connection',b'keep-alive',b'transfer-encoding',b'upgrade'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);rng=random.Random(20261120)
    cases=[b'',b'x-custom',b':unknown',b'hostile',b'test',b'transfer',b':methodx']
    for name in sorted(set(KINDS)|FORBIDDEN):
        cases.extend([name,name.upper(),name+b'x',b'x'+name])
        cases.extend(name[:end]for end in range(1,len(name)))
        for index in range(len(name)):
            altered=bytearray(name);altered[index]^=1;cases.append(bytes(altered))
        cases.extend([name+b'\0',b'\0'+name,name+b'\xff',name+b'x'*300])
    cases.extend(bytes(rng.randrange(256)for _ in range(rng.randrange(0,80)))for _ in range(200))
    cases.extend([b'x'*20000,b'content-type'+b'x'*20000])
    with(args.output/'vectors.txt').open('w')as stream:
        stream.write(f'{len(cases)}\n')
        for name in cases:
            expected=11 if name in FORBIDDEN else KINDS.get(name,0)
            stream.write(f'{len(name)} {expected}\n'+' '.join(map(str,name))+'\n')
    (args.output/'fixture_manifest.json').write_text(json.dumps({'cases':len(cases),'policy':'whole-string exact bytes',
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'longest_name':max(map(len,cases))},indent=2)+'\n')
    print(f'Generated {len(cases)} independent exact header-name cases, including long unknown names')


if __name__=='__main__':main()
