"""Bind isolated selection RTL, original native frames and unbounded proofs."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from generate_registered_frame_select import edits
from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe
from run_registered_frame_select_wsl import miter,proof_script,ready_cones
from verify_two_fpga_application import closure

from rtl_paths import source_relative


def source_gate(root):
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    candidate=root/'build/experiments/rpc-registered-frame-select-v1';g=read(candidate/'generation.json')
    parent=root/'build/experiments/rpc-stream-refusal-v7';old=read(parent/'generation.json')
    directed=read(root/'build/validation/rpc-stream-refusal-v7-directed.json')
    assert directed['key']=='950ce3b65ccb9b0a'and directed['generation_sha256']==sha(parent/'generation.json')
    assert directed['four_directed_application_runs_verified']and directed['full_pair_strict_vendor_elaboration_verified']
    assert g['parent_candidate']=='rpc-stream-refusal-v7'and g['parent_generation_sha256']==sha(parent/'generation.json')
    assert all(sha(candidate/n)==h for n,h in g['outputs_sha256'].items())
    assert all(sha(parent/n)==h for n,h in old['outputs_sha256'].items())
    cert=g['source_edit_certificate'];name='joint/rtl/axis_frame_arbiter.v';assert cert['path']==name
    original=(parent/name).read_bytes().decode();expected=original;replacements=edits()
    if '\r\n'in original:replacements=[(a.replace('\n','\r\n'),b.replace('\n','\r\n'))for a,b in replacements]
    assert cert['replacements']==[list(pair)for pair in replacements]
    for a,b in replacements:assert expected.count(a)==1;expected=expected.replace(a,b)
    assert expected==(candidate/name).read_bytes().decode()
    assert sha(parent/name)==cert['before_sha256']and sha(candidate/name)==cert['after_sha256']
    assert ports(original,'axis_frame_arbiter')==ports(expected,'axis_frame_arbiter')
    assert {n for n,h in old['outputs_sha256'].items()if sha(candidate/n)!=h}=={name}
    for top,key,count in(('http2_schema_mmio_application','canonical_parser_sha256',79),
        ('http2_enveloped_parser_application','non_mmio_parser_sha256',78),
        ('tokenizer_chiplet__tokenizer_hyperram_subsystem','canonical_tokenizer_sha256',31)):
        actual={n:sha(p)for n,p in closure(top,candidate/'joint').items()}
        assert actual==g[key]and len(actual)==count
    assert g['canonical_tokenizer_sha256']==old['canonical_tokenizer_sha256']
    return candidate,g


def require_unit_audit(root):
    candidate,g=source_gate(root)
    audit=json.loads((root/'build/validation/registered-frame-select-unit.json').read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert audit['generation_sha256']==sha(candidate/'generation.json')
    assert audit['actual_160_native_frames_verified']and audit['actual_wire_ack_safety_induction_verified']
    assert audit['full_512_bit_configuration_proven']and audit['registered_selection_ready_cones_verified']
    return audit


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text());candidate,g=source_gate(root)
    folder=root/'build/wsl-reports/registered_frame_select_registered_frame_select_v1_20261122'
    report=read(folder/'qualification.json');inputs=read(folder/'inputs.json')
    assert report['passed']and report['phase']=='registered_frame_selection_corpus_and_formal_safety_passed'
    assert report['generation_sha256']==sha(candidate/'generation.json')and inputs==report['inputs_sha256']
    assert all(sha(folder/n)==h for n,h in inputs.items())
    assert sha(folder/'rtl/axis_frame_arbiter.v')==sha(candidate/'joint/rtl/axis_frame_arbiter.v')
    parent=root/'build/wsl-reports/axis_frame_arbiter_actual_wire_frame_arbiter_fairness'
    original=read(parent/'inputs.json');assert original==report['original_inputs_sha256']
    assert {n for n,h in original.items()if inputs[n]!=h}=={'rtl/axis_frame_arbiter.v','sim/cocotb/test_axis_frame_arbiter.py'}
    test='sim/cocotb/test_axis_frame_arbiter.py';inverse=(folder/test).read_bytes().decode()
    for a,b in reversed(report['fixture_edits']):assert inverse.count(b)==1;inverse=inverse.replace(b,a)
    assert inverse==(parent/'execution-sources'/test).read_bytes().decode()
    runtime=read(folder/'build/test/report.json');accepted=read(folder/'build/test/acceptance.json')
    assert runtime['phase']=='passed'and runtime['input_sha256']==inputs
    assert accepted==report['unit_accepted']and accepted['phase']=='passed'
    assert runtime['acceptance_sha256']==sha(folder/'build/test/acceptance.json')
    assert accepted['native_frames']==accepted['output_frames']==160 and accepted['output_beats']==1070
    assert accepted['sustained_beats']==32 and accepted['selection_wait_cycles']==1
    assert all(accepted[n]>0 for n in('first_beat_stalls','locked_gap_cycles','fairness_boundaries','wire_retirement_checks'))
    xml=ET.parse(folder/'build/test/results.xml');tests=xml.findall('.//testcase')
    assert len(tests)==1 and tests[0].attrib['name']=='native_frames_never_interleave_and_retire_on_wire'
    assert not xml.findall('.//failure')and not xml.findall('.//error')
    source=(folder/'rtl/axis_frame_arbiter.v').read_text()
    observed=observe(source,'axis_frame_arbiter',[('','locked'),('','owner'),('','prefer_b')])
    assert [(p['data_width'],p['keep_width'],p['user_width'])for p in report['proofs']]==[(1,1,1),(512,64,16)]
    for p in report['proofs']:
        data,keep,user=p['data_width'],p['keep_width'],p['user_width'];slot=folder/'formal'/f'd{data}_k{keep}_u{user}'
        assert (slot/'observed.v').read_text()==observed and(slot/'miter.sv').read_text()==miter(source)
        assert (slot/'miter.sv').read_text().count('assume(')==5
        for name,induct in(('reset-base',False),('induction',True)):
            assert (slot/(name+'.ys')).read_text()==proof_script(induct,data,keep,user)
            text=(slot/(name+'.log')).read_text();assert not re.search(r'^ERROR:',text,re.M)
            assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in text
        assert ready_cones(read(slot/'netlist.json'))==p['ready_cones']
    result=dict(phase='registered_frame_selection_source_corpus_and_safety_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(candidate/'generation.json'),sole_changed_module='axis_frame_arbiter',
        exact_parser_modules=79,exact_non_mmio_parser_modules=78,exact_tokenizer_modules=31,
        actual_160_native_frames_verified=True,actual_wire_ack_safety_induction_verified=True,
        full_512_bit_configuration_proven=True,registered_selection_ready_cones_verified=True,
        assumptions='Initial reset; standard input AXIS VALID/payload stability while stalled, except across reset',
        arbitrary_later_resets=True,no_output_queue=True,first_selection_latency_cycles=1,
        sustained_in_frame_beats_per_clock=1,full_application_runtime_verified=False,
        native_timing_verified=False,retained_reset_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in folder.rglob('*')if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/registered-frame-select-unit-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    for path in(Path(__file__),root/'tools/run_registered_frame_select_wsl.py',root/'tools/generate_registered_frame_select.py'):
        shutil.copy2(path,evidence/path.name)
    for p in(evidence/'audit.json',root/'build/validation/registered-frame-select-unit.json'):
        p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=result['key'],actual_native_frames=160)))


if __name__=='__main__':main()
