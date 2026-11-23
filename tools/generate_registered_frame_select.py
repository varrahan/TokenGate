"""Isolate registered frame arbitration; preserve actual wire ACK semantics."""
import hashlib
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def edits():
    return [
        ('// Frame-level round robin. A presented first beat locks the source even before\n// READY; gaps inside a frame never allow the other source to interleave.',
         '// Frame-level round robin with registered selection before presenting a\n// first beat. Gaps inside a frame retain that source through actual TLAST.'),
        ('    wire selected=locked?owner:a_axis_tvalid&&b_axis_tvalid?prefer_b:b_axis_tvalid;',
         '    wire selected=owner;\n    wire choose_b=a_axis_tvalid&&b_axis_tvalid?prefer_b:b_axis_tvalid;'),
        ('assign m_axis_tvalid=!rst&&(selected?b_axis_tvalid:a_axis_tvalid);',
         'assign m_axis_tvalid=!rst&&locked&&(selected?b_axis_tvalid:a_axis_tvalid);'),
        ('assign a_axis_tready=!rst&&!selected&&m_axis_tready;',
         'assign a_axis_tready=!rst&&locked&&!selected&&m_axis_tready;'),
        ('assign b_axis_tready=!rst&&selected&&m_axis_tready;',
         'assign b_axis_tready=!rst&&locked&&selected&&m_axis_tready;'),
        ('''        else if(m_axis_tvalid)begin
            if(m_axis_tready&&m_axis_tlast)begin locked<=0;prefer_b<=!selected;end
            else begin locked<=1;owner<=selected;end
        end''',
         '''        else if(!locked)begin
            if(a_axis_tvalid||b_axis_tvalid)begin locked<=1;owner<=choose_b;end
        end else if(m_axis_tvalid&&m_axis_tready&&m_axis_tlast)begin
            locked<=0;prefer_b<=!owner;
        end''')]


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=root/'build/experiments/rpc-stream-refusal-v7';generation=json.loads((parent/'generation.json').read_text())
    directed=json.loads((root/'build/validation/rpc-stream-refusal-v7-directed.json').read_text())
    assert directed['key']=='950ce3b65ccb9b0a'and directed['generation_sha256']==sha(parent/'generation.json')
    target=root/'build/experiments/rpc-registered-frame-select-v1';target.mkdir(parents=True,exist_ok=False)
    for n,h in generation['outputs_sha256'].items():
        assert sha(parent/n)==h
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/n,p)
    name='joint/rtl/axis_frame_arbiter.v';original=(target/name).read_bytes().decode();updated=original
    replacements=edits()
    if '\r\n'in original:replacements=[(a.replace('\n','\r\n'),b.replace('\n','\r\n'))for a,b in replacements]
    for a,b in replacements:
        assert updated.count(a)==1,a;updated=updated.replace(a,b)
    inverse=updated
    for a,b in reversed(replacements):assert inverse.count(b)==1;inverse=inverse.replace(b,a)
    assert inverse==original and ports(original,'axis_frame_arbiter')==ports(updated,'axis_frame_arbiter')
    (target/name).write_bytes(updated.encode())
    parser=closure('http2_schema_mmio_application',target/'joint');plain=closure('http2_enveloped_parser_application',target/'joint')
    tokenizer=closure('tokenizer_chiplet__tokenizer_hyperram_subsystem',target/'joint')
    assert len(parser)==79 and len(plain)==78 and len(tokenizer)==31
    changed={n for n,h in generation['outputs_sha256'].items()if sha(target/n)!=h};assert changed=={name}
    assert {n:sha(p)for n,p in tokenizer.items()}==generation['canonical_tokenizer_sha256']
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    report=dict(phase='registered_frame_selection_generated_unverified',parent_generation_sha256=sha(parent/'generation.json'),
        parent_candidate='rpc-stream-refusal-v7',parent_directed_audit_key=directed['key'],
        source_edit_certificate=dict(path=name,before_sha256=sha(parent/name),after_sha256=sha(target/name),replacements=replacements),
        parser_modules=79,non_mmio_parser_modules=78,tokenizer_modules=31,
        canonical_parser_sha256={n:sha(p)for n,p in parser.items()},non_mmio_parser_sha256={n:sha(p)for n,p in plain.items()},
        canonical_tokenizer_sha256={n:sha(p)for n,p in tokenizer.items()},
        first_frame_selection_adds_latency=True,no_output_queue=True,input_acceptance_must_remain_actual_wire_handshake=True,
        functional_runtime_verified=False,formal_safety_verified=False,native_timing_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,full_system_complete=False,generator_sha256=sha(Path(__file__)))
    report['outputs_sha256']={p.relative_to(target).as_posix():sha(p)for p in target.rglob('*')if p.is_file()}
    (target/'generation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k]for k in('phase','parser_modules','non_mmio_parser_modules','tokenizer_modules')}))


if __name__=='__main__':main()
