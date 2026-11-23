"""Verify FIFO induction, actual payload cones and the full framing corpus."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from run_frame_fifo_equivalence_wsl import observe, miter, cones
from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    candidate=root/'build/experiments/frame-event-pingpong';generation=read(candidate/'generation.json')
    units=read(root/'build/validation/frame-event-buffer-units.json');assert units['key']=='0629d7b95661f8df'
    parent=root/'build/experiments/frame-event-buffer'
    before=generation['source_edit_certificate']['old'];after=generation['source_edit_certificate']['new']
    old=(parent/'rtl/http2_axis_ingress.v').read_text();new=(candidate/'rtl/http2_axis_ingress.v').read_text()
    assert old.count(before)==1 and new==old.replace(before,after) and new.replace(after,before)==old
    for name,digest in generation['outputs_sha256'].items():assert sha(candidate/name)==digest,name
    dependencies={n:sha(p) for n,p in closure('http2_enveloped_parser_application',candidate).items()}
    assert len(dependencies)==77
    for name,digest in units['candidate_parser_sha256'].items():
        if name!='http2_axis_ingress':assert dependencies[name]==digest
    formal=root/'build/wsl-reports/frame_fifo_equivalence_v1_20261122';proof=read(formal/'report.json')
    assert proof['passed'] and proof['phase']=='frame_fifo_unbounded_equivalence_and_payload_cones_verified'
    assert proof['parent_generation_sha256']==sha(candidate/'generation.json')
    assert proof['driver_sha256']==sha(formal/'run_frame_fifo_equivalence_wsl.py')
    assert sha(formal/'baseline-original.v')==proof['baseline_sha256']==sha(candidate/'rtl/axis_skid_buffer.v')
    assert sha(formal/'candidate-original.v')==proof['candidate_sha256']==sha(candidate/'rtl/axis_pingpong_skid_buffer.v')
    wide='[DATA_WIDTH+KEEP_WIDTH+USER_WIDTH:0]'
    assert (formal/'baseline.v').read_text()==observe((formal/'baseline-original.v').read_text(),'axis_skid_buffer',
        [('[1:0]','count'),(wide,'head_payload'),(wide,'tail_payload')])
    assert (formal/'candidate.v').read_text()==observe((formal/'candidate-original.v').read_text(),'axis_pingpong_skid_buffer',
        [('[1:0]','count'),(wide,'slot0_payload'),(wide,'slot1_payload'),('','read_slot'),('','write_slot')])
    assert [(p['data_width'],p['keep_width'],p['user_width']) for p in proof['proofs']]==[(1,1,1),(8,1,16),(114,1,16),(128,16,16),(512,64,16)]
    for record in proof['proofs']:
        data,keep,user=(record[n] for n in ('data_width','keep_width','user_width'))
        path=formal/f'd{data}_k{keep}_u{user}'
        for name,digest in record['inputs_sha256'].items():assert sha(path/name)==digest
        assert (path/'baseline.v').read_bytes()==(formal/'baseline.v').read_bytes()
        assert (path/'candidate.v').read_bytes()==(formal/'candidate.v').read_bytes()
        assert (path/'miter.sv').read_text()==miter(data,keep,user)
        script=(path/'proof.ys').read_text()
        assert '-verify -prove-asserts -set-assumes -seq 2 -tempinduct -tempinduct-def -set-init-def -set-def-inputs' in script
        assert all(word not in script for word in ('blackbox','ignore_unknown','-baseonly','-skip','-prove-x','-set-init-zero'))
        assert sha(path/'proof.log')==record['proof_log_sha256'] and sha(path/'netlist.json')==record['netlist_sha256']
        log=(path/'proof.log').read_text()
        assert 'Induction step proven: SUCCESS!' in log and 'Base case for induction length 1 proven.' in log
        assert cones(read(path/'netlist.json'))==record['payload_register_cones']
    framing=root/'build/wsl-reports/frame_event_pingpong_frames_20261122';report=read(framing/'report.json')
    assert report['passed'] and report['phase']=='frame_event_pingpong_full_framing_corpus_verified'
    assert report['candidate_variant']=='frame-event-pingpong' and report['no_memory_model_substitution']
    assert sha(framing/'candidate-generation.json')==report['generation_sha256']==sha(candidate/'generation.json')
    assert sha(framing/'run_frame_event_buffer_units_wsl.py')==report['driver_sha256']
    assert sha(framing/'reference/generate.py')==report['generator_sha256']
    assert sha(framing/'reference/vectors.txt')==report['vectors_sha256']
    assert sha(framing/'tb_http2_frames.sv')==report['testbench_sha256']
    for revision,record in report['revisions'].items():
        assert record['passed'] and record['summary']==[459,125212,120829,132,120564,132,1,76]
        for name,digest in record['inputs_sha256'].items():assert sha(framing/revision/'rtl'/name)==digest
        assert sha(framing/revision/'tb_http2_frames.sv')==report['testbench_sha256']
        assert sha(framing/revision/'vectors.txt')==report['vectors_sha256']
        assert sha(framing/revision/'simulate.log')==record['simulation_log_sha256']
        assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',(framing/revision/'simulate.log').read_text(),re.M)
        assert all('PARSER_PORTABLE_SIM' not in str(c) for c in record['commands'])
    coverage=report['revisions']['candidate']
    assert coverage['buffer_full_cycles']>100 and coverage['completion_fence_cycles']>0
    result=dict(phase='frame_event_pingpong_induction_and_complete_framing_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_unit_audit_key=units['key'],exact_parser_modules=77,executed_parser_sha256=dependencies,
        unbounded_fifo_equivalence_configurations=5,event_width_configuration_verified=True,
        witness_instrumentation_inverse_verified=True,input_stability_assumptions=False,
        initial_reset_required=True,arbitrary_later_resets=True,two_state_formal=True,
        downstream_ready_excluded_from_payload_register_next_state_cones=True,
        four_state_framing_fragments=459,exact_framing_events=120829,framing_protocol_failures=76,
        buffer_full_cycles=coverage['buffer_full_cycles'],completion_fence_cycles=coverage['completion_fence_cycles'],
        full_protocol_verified=False,native_timing_verified=False,selected_for_next_implementation=False,
        selection_reason='Finished parent route moves the worst path to ownership/idle feedback; that path is being addressed first',
        full_system_complete=False,generation_sha256=sha(candidate/'generation.json'),
        formal_report_sha256=sha(formal/'report.json'),framing_report_sha256=sha(framing/'report.json'),verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/frame-event-pingpong-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    for path in (Path(__file__),candidate/'generate_frame_event_pingpong.py',formal/'run_frame_fifo_equivalence_wsl.py'):
        shutil.copy2(path,evidence/path.name)
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/frame-event-pingpong.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','unbounded_fifo_equivalence_configurations','exact_framing_events')}))


if __name__=='__main__':main()
