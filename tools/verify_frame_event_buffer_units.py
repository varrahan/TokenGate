"""Bind complete framing acceptance and drain coverage to the exact FIFO edit."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_frame_event_buffer import buffered


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    archive=root/'build/wsl-reports/frame_event_buffer_frames_20261122'
    report=read(archive/'report.json');assert report['passed'] and report['phase']=='frame_event_buffer_full_framing_corpus_verified'
    candidate=root/'build/experiments/frame-event-buffer';generation=read(candidate/'generation.json')
    assert sha(candidate/'generation.json')==report['generation_sha256']
    assert sha(candidate/'generate_frame_event_buffer.py')==generation['generator_sha256']
    assert sha(archive/'run_frame_event_buffer_units_wsl.py')==report['driver_sha256']
    assert sha(archive/'reference/generate.py')==report['generator_sha256']
    assert sha(archive/'reference/vectors.txt')==report['vectors_sha256']
    assert sha(archive/'tb_http2_frames.sv')==report['testbench_sha256']
    parent=read(root/'build/validation/json-simd-corpus.json');assert parent['key']==generation['parent_corpus_audit_key']=='2509134d2630b47e'
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    old=(original/'rtl/http2_axis_ingress.v').read_text();new,restored,certificate=buffered(old)
    assert restored==old and certificate==generation['source_edit_certificate']
    assert (candidate/'rtl/http2_axis_ingress.v').read_bytes()==new.encode()
    for name,digest in generation['outputs_sha256'].items():assert sha(candidate/name)==digest
    changed=[name for name in generation['outputs_sha256'] if generation['outputs_sha256'][name]!=parent['inputs_sha256'][name]]
    assert changed==['rtl/http2_axis_ingress.v']
    for revision,record in report['revisions'].items():
        assert record['passed'] and record['phase']=='passed'
        for name,digest in record['inputs_sha256'].items():assert sha(archive/revision/'rtl'/name)==digest
        assert sha(archive/revision/'vectors.txt')==report['vectors_sha256']
        assert sha(archive/revision/'tb_http2_frames.sv')==report['testbench_sha256']
        log=(archive/revision/'simulate.log').read_text()
        assert sha(archive/revision/'simulate.log')==record['simulation_log_sha256']
        assert not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):',log,re.M)
        assert all('PARSER_PORTABLE_SIM' not in str(command) for command in record['commands'])
    baseline=report['revisions']['baseline'];actual=report['revisions']['candidate']
    assert baseline['summary']==actual['summary']==[459,125212,120829,132,120564,132,1,76]
    assert actual['buffer_full_cycles']>100 and actual['completion_fence_cycles']>0
    module=(candidate/'rtl/axis_skid_buffer.v').read_text()
    assert 'assign s_axis_tready = count < 2;' in module
    assert 'assign m_axis_tvalid = count != 0;' in module
    assert ' = head_payload;' in module
    result=dict(phase='frame_event_buffer_full_framing_evidence_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_corpus_audit_key=parent['key'],fragments=459,wire_bytes=125212,exact_events=120829,protocol_failed_fragments=76,
        baseline_candidate_summaries_equal=True,buffer_full_cycles=actual['buffer_full_cycles'],
        completion_fence_cycles=actual['completion_fence_cycles'],source_edit_replay_verified=True,
        only_changed_module='http2_axis_ingress',exact_parser_modules=76,complete_event_context_preserved=True,
        no_memory_model_substitution=True,full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        generator_sha256=generation['generator_sha256'],generation_sha256=sha(candidate/'generation.json'),
        candidate_parser_sha256={Path(n).stem:h for n,h in generation['outputs_sha256'].items()},
        unit_report_sha256=sha(archive/'report.json'),verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/frame-event-buffer-units-evidence'/result['key'];target.mkdir(parents=True,exist_ok=False)
    for path in (Path(__file__),root/'tools/generate_frame_event_buffer.py'):
        shutil.copy2(path,target/path.name)
    shutil.copy2(archive/'report.json',target/'unit-report.json')
    shutil.copy2(archive/'candidate/simulate.log',target/'simulation.log')
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/frame-event-buffer-units.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','fragments','exact_events','completion_fence_cycles')}))


if __name__=='__main__':main()
