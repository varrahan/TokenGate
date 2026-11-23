"""Bind the conservative quiet proof to the complete unchanged owner subtree."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_frame_owned_quiet import quiet
from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe
from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/wsl-reports/frame_owned_quiet_formal_v1_20261122'
    candidate=root/'build/experiments/frame-owned-quiet';generation=read(candidate/'generation.json')
    report=read(folder/'report.json')
    assert report['passed'] and report['phase']=='frame_owned_quiet_conservative_idle_induction_verified'
    assert report['generation_sha256']==sha(candidate/'generation.json')
    assert report['driver_sha256']==sha(folder/'run_frame_owned_quiet_formal_wsl.py')
    for name,digest in report['inputs_sha256'].items():assert sha(folder/name)==digest,name
    for name,digest in generation['outputs_sha256'].items():assert sha(candidate/name)==digest,name
    parent=root/'build/experiments/frame-event-buffer'
    units=read(root/'build/validation/frame-event-buffer-units.json');assert units['key']=='0629d7b95661f8df'
    corpus=read(root/'build/validation/frame-event-buffer-corpus.json')
    assert corpus['key']=='8dc09b4c450eaa4f' and corpus['full_native_corpus_verified']
    assert corpus['executed_parser_sha256']==units['candidate_parser_sha256']
    old=(parent/'rtl/http2_enveloped_frame_grants.v').read_text();text,certificate=quiet(old)
    assert certificate==generation['source_edit_certificate']
    assert text.encode()==(candidate/'rtl/http2_enveloped_frame_grants.v').read_bytes()
    expected={n:sha(p) for n,p in closure('http2_enveloped_parser_application',candidate).items()}
    assert len(expected)==76
    assert {n for n in expected if expected[n]!=units['candidate_parser_sha256'][n]}=={'http2_enveloped_frame_grants'}
    assert generation['generator_sha256']==sha(candidate/'generate_frame_owned_quiet.py')
    dependencies=closure('http2_enveloped_frame_grants',candidate);assert len(dependencies)==7
    for name,path in dependencies.items():
        if name!='http2_enveloped_frame_grants':assert sha(folder/'rtl'/path.name)==sha(path)
    rhs=certificate['old'].removeprefix('assign idle=').removesuffix(';')
    declaration='wire reference_idle='+rhs+';\n'
    instrumented=text.replace('endmodule',declaration+'endmodule')
    instrumented=observe(instrumented,'http2_enveloped_frame_grants',
        [('','reference_idle'),('','owned_quiet'),('','owned_idle'),('','quiet_inputs')])
    assert instrumented==(folder/'rtl/http2_enveloped_frame_grants.v').read_text()
    assert report['original_top_sha256']==hashlib.sha256(text.encode()).hexdigest()
    miter=(folder/'miter.sv').read_text();script=(folder/'proof.ys').read_text()
    interface=[p for p in ports(text,'http2_enveloped_frame_grants') if p[0]=='input']
    assert ports(miter,'quiet_certificate_miter')==interface
    assert miter.count('assume(')==1 and 'if(!past_valid)assume(rst);' in miter
    assert miter.count('assert(')==2
    assert 'assert(!candidate_idle||reference_idle);' in miter
    assert 'assert(!(owned_quiet&&quiet_inputs)||owned_idle);' in miter
    for _,_,name in interface:assert miter.count('.'+name+'('+name+')')==1,name
    assert '.ENABLE_WINDOW_FORMAT(1),.ENABLE_LOCAL_FATAL(1),.ENABLE_RECEIVE_POOL(1),.ENABLE_CONTEXT_GUARD(1)' in miter
    assert 'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23' in miter
    assert '.formal_reference_idle(reference_idle)' in miter and '.formal_owned_idle(owned_idle)' in miter
    assert 'read_verilog -formal -sv rtl/*.v miter.sv' in script
    assert len(list((folder/'rtl').glob('*.v')))==7
    assert '-verify -prove-asserts -set-assumes -seq 2 -tempinduct -tempinduct-def -set-init-def -set-def-inputs' in script
    assert all(word not in script for word in ('blackbox','ignore_unknown','-baseonly','-skip','-prove-x','-set-init-zero'))
    log=(folder/'proof.log').read_text()
    assert 'Induction step proven: SUCCESS!' in log and 'Base case for induction length 1 proven.' in log
    assert sha(folder/'proof.log')==report['proof_log_sha256'] and sha(folder/'netlist.json')==report['netlist_sha256']
    assert not re.search(r'^ERROR:',log,re.M)
    result=dict(phase='frame_owned_quiet_complete_owner_induction_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_unit_audit_key=units['key'],parent_corpus_audit_key=corpus['key'],exact_parser_modules=76,
        exact_owner_modules=7,executed_parser_sha256=expected,source_edit_replay_verified=True,
        conservative_idle_induction_verified=True,all_existing_state_and_handshake_equations_preserved=True,
        no_existing_internal_consumer_of_exported_idle=True,complete_production_owner_subtree=True,
        initial_reset_required=True,arbitrary_later_resets=True,input_stability_assumptions=False,two_state_formal=True,
        qualified_user_width=16,qualified_memory_address_width=23,all_four_transport_feature_flags_enabled=True,
        full_native_corpus_verified=False,full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        generation_sha256=sha(candidate/'generation.json'),formal_report_sha256=sha(folder/'report.json'),
        proof_log_sha256=report['proof_log_sha256'],netlist_sha256=report['netlist_sha256'],
        generator_sha256=generation['generator_sha256'],verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/frame-owned-quiet-formal-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    for path in (Path(__file__),root/'tools/generate_frame_owned_quiet.py',folder/'run_frame_owned_quiet_formal_wsl.py',
        folder/'run_frame_fifo_equivalence_wsl.py',folder/'miter.sv',folder/'proof.ys',folder/'proof.log',folder/'report.json'):
        shutil.copy2(path,evidence/path.name)
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/frame-owned-quiet-formal.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','exact_owner_modules','conservative_idle_induction_verified')}))


if __name__=='__main__':main()
