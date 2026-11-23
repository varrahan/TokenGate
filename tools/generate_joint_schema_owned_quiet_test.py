"""Compose native schema programming with the qualified FIFO/owner changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_frame_event_buffer import buffered
from generate_frame_owned_quiet import quiet
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    schema=read(root/'build/validation/joint-hyperram-schema.json')
    assert schema['key']=='292670e03a24501d' and schema['full_http2_schema_mmio_functional_workload_verified']
    owner=read(root/'build/validation/frame-owned-quiet-formal.json')
    assert owner['key']=='c56de709b9b5681a' and owner['conservative_idle_induction_verified']
    frames=read(root/'build/validation/frame-event-buffer-corpus.json')
    assert frames['key']=='8dc09b4c450eaa4f' and frames['full_native_corpus_verified']
    parent=root/'build/validation'/schema['run'];report=read(parent/'report.json')
    assert sha(parent/'report.json')==schema['report_sha256'] and report['simulation_passed']
    target=root/'build/experiments'/args.name;target.mkdir(parents=True,exist_ok=False)
    for name,digest in report['inputs_sha256'].items():
        assert sha(parent/name)==digest,name
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/name,path)
    certificates={}
    for name,transform in [('http2_axis_ingress.v',buffered),('http2_enveloped_frame_grants.v',quiet)]:
        path=target/'joint/rtl'/name;old=path.read_text()
        if name=='http2_axis_ingress.v':
            new,restored,edits=transform(old);assert restored==old
        else:
            new,edit=transform(old);edits=[edit]
        inverse=new
        for edit in reversed(edits):
            assert inverse.count(edit['new'])==1
            inverse=inverse.replace(edit['new'],edit['old'])
        assert inverse==old
        raw_digest=sha(path);path.write_bytes(new.encode())
        certificates[name]=dict(parent_raw_sha256=raw_digest,parent_normalized_sha256=hashlib.sha256(old.encode()).hexdigest(),
            candidate_sha256=sha(path),inverse_normalized_sha256=hashlib.sha256(inverse.encode()).hexdigest(),edits=edits)
    parser=closure('http2_schema_mmio_application',target/'joint')
    tokenizer=closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',target/'joint')
    assert len(parser)==77 and len(tokenizer)==31
    changed={n for n,h in report['inputs_sha256'].items() if sha(target/n)!=h}
    assert changed=={'joint/rtl/http2_axis_ingress.v','joint/rtl/http2_enveloped_frame_grants.v'}
    generation=read(parent/'generation.json')
    generation.update(phase='joint_schema_owned_quiet_full_corpus_generated',owned_quiet=True,
        parent_schema_audit_key=schema['key'],parent_schema_report_sha256=sha(parent/'report.json'),
        parent_schema_inputs_sha256=report['inputs_sha256'],owner_formal_audit_key=owner['key'],
        buffered_corpus_audit_key=frames['key'],native_source_edit_certificates=certificates,
        owned_quiet_source_edit_certificate=certificates['http2_enveloped_frame_grants.v']['edits'][0],
        canonical_owner_induction_verified=False,simulation_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=sha(Path(__file__)))
    generation['unchanged_parent_inputs_sha256']={n:h for n,h in generation['parent_inputs_sha256'].items() if sha(target/n)==h}
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    generation['outputs_sha256']={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
    (target/'generation.json').write_text(json.dumps(generation,indent=2)+'\n')
    print(json.dumps({k:generation[k] for k in ('phase','parser_modules','tokenizer_modules','schema_mmio','owned_quiet')}))


if __name__=='__main__':main()
