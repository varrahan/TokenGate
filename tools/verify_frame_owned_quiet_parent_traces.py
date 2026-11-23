"""Compare every acceptance field with the immediate buffered parent."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def main():
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    prior=root/'build/validation/frame-event-buffer-protocol.json';current=root/'build/validation/frame-owned-quiet-protocol.json'
    before=read(prior);after=read(current)
    assert before['key']=='bf48760311bf3754' and after['key']=='f24de6688d09bbcc'
    assert before['executions'].keys()==after['executions'].keys() and len(after['executions'])==7
    old=before['executed_parser_sha256'];new=after['executed_parser_sha256']
    assert old.keys()==new.keys() and len(new)==76
    assert {name for name in new if old[name]!=new[name]}=={'http2_enveloped_frame_grants'}
    for case in after['executions']:
        assert before['executions'][case]['accepted']==after['executions'][case]['accepted'],case
    formal=read(root/'build/validation/frame-owned-quiet-formal.json')
    assert formal['key']=='c56de709b9b5681a' and formal['executed_parser_sha256']==new
    result=dict(phase='frame_owned_quiet_all_parent_acceptance_fields_equal',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_protocol_audit_key=before['key'],candidate_protocol_audit_key=after['key'],formal_audit_key=formal['key'],
        exact_parser_modules=76,cases=list(after['executions']),all_acceptance_fields_equal=True,
        all_timing_measurements_equal=True,only_changed_module='http2_enveloped_frame_grants',
        no_acceptance_fields_ignored=True,native_vendor_protocol_regressions_verified=False,
        full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        parent_audit_sha256=sha(prior),candidate_audit_sha256=sha(current),verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/frame-owned-quiet-parent-traces-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/frame-owned-quiet-parent-traces.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','all_acceptance_fields_equal','all_timing_measurements_equal')}))


if __name__=='__main__':main()
