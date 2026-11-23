"""Isolate a payload-write-independent event FIFO on the buffered Parser."""
import hashlib
import json
from pathlib import Path
import shutil

from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    parent=root/'build/experiments/frame-event-buffer';generation=read(parent/'generation.json')
    units=read(root/'build/validation/frame-event-buffer-units.json')
    assert units['key']=='0629d7b95661f8df'
    assert units['generation_sha256']==sha(parent/'generation.json')
    target=root/'build/experiments/frame-event-pingpong';target.mkdir(parents=True,exist_ok=False)
    for name,digest in generation['outputs_sha256'].items():
        assert sha(parent/name)==digest
        path=target/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/name,path)
    path=target/'rtl/http2_axis_ingress.v';old=path.read_text()
    before='axis_skid_buffer #(.DATA_WIDTH(114),.KEEP_WIDTH(1),.USER_WIDTH(USER_WIDTH)) event_buffer('
    after=before.replace('axis_skid_buffer','axis_pingpong_skid_buffer',1)
    assert old.count(before)==1
    new=old.replace(before,after);assert new.replace(after,before)==old
    path.write_bytes(new.encode())
    fifo=root/'rtl/axis_pingpong_skid_buffer.v';shutil.copy2(fifo,target/'rtl'/fifo.name)
    dependencies=closure('http2_enveloped_parser_application',target);assert len(dependencies)==77
    for name,p in dependencies.items():
        if name not in ('http2_axis_ingress','axis_pingpong_skid_buffer'):assert sha(p)==units['candidate_parser_sha256'][name]
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    result=dict(phase='frame_event_pingpong_generated',parent_unit_audit_key=units['key'],
        parent_generation_sha256=sha(parent/'generation.json'),exact_parser_modules=77,
        source_edit_certificate=dict(old=before,new=after),only_replaced_instance='http2_axis_ingress.event_buffer',
        event_payload_bits=114,event_context_bits=16,event_keep_bits=1,
        no_reader_state_or_snapshot_layout_changed=True,no_other_existing_module_changed=True,
        completion_and_idle_drain_fence_preserved=True,functional_equivalence_verified=False,
        full_framing_corpus_verified=False,full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=sha(Path(__file__)),outputs_sha256={'rtl/'+p.name:sha(p) for p in (target/'rtl').glob('*.v')})
    (target/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','exact_parser_modules','only_replaced_instance')}))


if __name__=='__main__':main()
