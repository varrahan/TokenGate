"""Bind a reachable settling lemma and sole-consumer certificate to actual RTL."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from generate_receive_payload_pipeline import MODULE,NAME,edits
from verify_registered_frame_select import source_gate as parent_gate
from verify_two_fpga_application import closure


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())


def source_gate(root):
    parent,previous=parent_gate(root);candidate=root/'build/experiments'/NAME
    generation=read(candidate/'generation.json');path='joint/rtl/'+MODULE+'.v'
    assert generation['parent_generation_sha256']==sha(parent/'generation.json')
    assert all(sha(candidate/n)==h for n,h in generation['outputs_sha256'].items())
    assert {n for n,h in previous['outputs_sha256'].items()if sha(candidate/n)!=h}=={path}
    original=(parent/path).read_bytes().decode();updated=(candidate/path).read_bytes().decode()
    replacements=edits()
    if '\r\n'in original:replacements=[(a.replace('\n','\r\n'),b.replace('\n','\r\n'))for a,b in replacements]
    expected=original
    for before,after in replacements:
        assert expected.count(before)==1;expected=expected.replace(before,after)
    assert expected==updated
    cert=generation['source_edit_certificate']
    assert cert==dict(path=path,before_sha256=sha(parent/path),after_sha256=sha(candidate/path),replacements=[list(p)for p in replacements])
    interface=ports(original,MODULE);assert interface==ports(updated,MODULE)
    text=updated.replace('\r\n','\n')
    counts={'expected_rpc_payload':4,'rpc_backing_good':4,'rpc_good':3,'retired_rpc_good':3}
    for name,count in counts.items():
        assert len(re.findall(r'\b'+name+r'\b',text))==count,(name,count)
    assert 'RPC_CHECK=7,'in text
    statements=(
        'assign rpc_backing_good=!capacity_mode||\n        ({32\'d0,rpc_record[159:128]}==expected_rpc_payload&&',
        'assign rpc_good=rpc_record[31:0]==RPC_MAGIC&&rpc_record[32]&&rpc_record[63:35]==0&&rpc_identity&&rpc_backing_good;',
        'assign retired_rpc_good=rpc_record[63:0]==0&&rpc_identity&&rpc_backing_good;',
        'RPC_CHECK:if((operation==9||operation==10)?!retired_rpc_good:!rpc_good)fail(3,2,2,1);else read_words(RSTREAM,stream_address,4);')
    assert all(text.count(statement)==1 for statement in statements)
    assert not set(counts).intersection(n for d,w,n in interface)
    maps={}
    for top,key,count in (
        ('http2_schema_mmio_application','canonical_parser_sha256',79),
        ('http2_enveloped_parser_application','non_mmio_parser_sha256',78),
        ('tokenizer_chiplet__tokenizer_hyperram_subsystem','canonical_tokenizer_sha256',31)):
        sources=closure(top,candidate/'joint');actual={n:sha(p)for n,p in sources.items()}
        assert actual==generation[key]and len(actual)==count;maps[key]=actual
        for name,path in sources.items():
            if name!=MODULE:
                assert not re.search(r'\.\s*(?:expected_rpc_payload|rpc_backing_good|rpc_good|retired_rpc_good)\b',path.read_text()),name
    assert maps['canonical_tokenizer_sha256']==previous['canonical_tokenizer_sha256']
    core=(candidate/'joint/rtl/http2_enveloped_parser_core.v').read_text()
    assert core.count('http2_keyed_receive_credit_store #(.ENABLE_CAPACITY(1),.ENABLE_STREAM_FORMAT(1),')==1
    consumer=dict(sole_consumption_state='RPC_CHECK',state_encoding=7,internal_identifier_occurrences=counts,
        exact_consumer_statements=statements,original_public_ports_unchanged=True,
        all_other_production_statements_byte_identical_by_inverse=True,
        no_hierarchical_reads_from_other_production_modules=True)
    return candidate,generation,consumer


def require_settling_audit(root):
    candidate,generation,consumer=source_gate(root)
    audit=read(root/'build/validation/receive-payload-settling.json')
    assert audit['generation_sha256']==sha(candidate/'generation.json')
    assert audit['settling_unbounded_induction_verified']and audit['actual_reset_base_verified']
    assert audit['source_consumer_certificate']==json.loads(json.dumps(consumer))
    assert audit['functional_equivalence_derived_from_settling_and_exact_source_inverse']
    assert audit['candidate_parser_sha256']==generation['non_mmio_parser_sha256']
    return audit


def main():
    from run_receive_payload_settling_wsl import leaf_sources,record_cuts,PREPARE,proof_script
    root=Path(__file__).resolve().parents[1];candidate,generation,consumer=source_gate(root)
    folder=root/'build/wsl-reports/rpc_receive_payload_settling_v1_20261122'
    report=read(folder/'report.json')
    assert report['phase']=='receive_payload_pipeline_settling_proven'and report['passed']
    assert report['candidate_generation_sha256']==sha(candidate/'generation.json')
    assert read(folder/'generation.json')==generation
    for group in('inputs_sha256','artifacts_sha256'):
        for name,h in report[group].items():assert sha(folder/name)==h,name
    parent=root/'build/experiments/rpc-registered-frame-select-v1'
    assert (folder/'reference-original.v').read_bytes()==(parent/('joint/rtl/'+MODULE+'.v')).read_bytes()
    assert (folder/'candidate-original.v').read_bytes()==(candidate/('joint/rtl/'+MODULE+'.v')).read_bytes()
    old=(folder/'reference-original.v').read_text();new=(folder/'candidate-original.v').read_text()
    slot=(candidate/'joint/rtl/memory_command_slot.v').read_text()
    sources,arithmetic=leaf_sources(old,new,slot)
    assert read(folder/'arithmetic-certificate.json')==json.loads(json.dumps(arithmetic))
    for name,text in sources.items():assert (folder/name).read_text()==text,name
    assert (folder/'prepare.ys').read_text()==PREPARE
    miter=sources['miter.sv']
    assert miter.count('assert(')==3 and miter.count('assume(')==6
    assert 'if(new_internal_state==4||new_internal_state==7)assert(pipe_expected==reference_expected);'in miter
    assert 'USER_WIDTH=16,MEMORY_ADDR_WIDTH=23'in miter
    cut,certificate=record_cuts(read(folder/'uncut.json'))
    assert cut==read(folder/'cut.json')
    assert certificate==read(folder/'record-cut-certificate.json')
    assert [(c['record'],c['width'])for c in certificate]==[('connection_record',512),('rpc_record',256),('stream_record',256)]
    for label,induct in(('reset-base',False),('induction',True)):
        assert (folder/(label+'.ys')).read_text()==proof_script(induct)
        log=(folder/(label+'.log')).read_text();assert not re.search(r'^ERROR:',log,re.M)
        assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log
    negatives={}
    for name in('rpc_receive_payload_pipeline_v1_20261122','rpc_receive_payload_pipeline_smt_v1_20261122','rpc_receive_payload_pipeline_compositional_v1_20261122'):
        previous=root/'build/wsl-reports'/name;failed=read(previous/'report.json');assert not failed['passed']
        negatives[name]=dict(report_sha256=sha(previous/'report.json'),log_sha256={p.name:sha(p)for p in previous.glob('*.log')})
    result=dict(phase='receive_payload_settling_and_consumption_equivalence_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        candidate=NAME,generation_sha256=sha(candidate/'generation.json'),parent_generation_sha256=generation['parent_generation_sha256'],
        sole_additional_changed_module=MODULE,source_consumer_certificate=consumer,
        settling_unbounded_induction_verified=True,actual_reset_base_verified=True,
        functional_equivalence_derived_from_settling_and_exact_source_inverse=True,
        direct_all_public_output_induction_verified=False,
        initial_reset_required=True,later_resets_and_external_inputs_arbitrary=True,
        real_candidate_control_and_memory_slot_retained=True,
        metadata_record_data_overapproximated=['connection_record','rpc_record','stream_record'],
        internal_arithmetic_congruence_assumptions=5,external_input_stability_assumptions=0,
        no_assumed_pipeline_settling=True,arithmetic_bitblast_proven=False,
        arithmetic_scope='Unsigned64 multiplication replaced by arbitrary results consistent at equal arguments in same/adjacent samples; three other product results arbitrary. Concrete RTL arithmetic is a subset.',
        production_address_width=23,production_context_width=16,capacity_and_stream_format_enabled=True,
        candidate_parser_sha256=generation['non_mmio_parser_sha256'],canonical_parser_sha256=generation['canonical_parser_sha256'],
        canonical_tokenizer_sha256=generation['canonical_tokenizer_sha256'],
        exact_non_mmio_parser_modules=78,exact_schema_parser_modules=79,exact_native_tokenizer_modules=31,
        earlier_unsuccessful_proof_attempts=negatives,actual_candidate_runtime_verified=False,
        retained_owner_recovery_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p)for p in folder.iterdir()if p.is_file()},verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/receive-payload-settling-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    for name in('verify_receive_payload_settling.py','run_receive_payload_settling_wsl.py','run_receive_payload_pipeline_compositional_wsl.py','run_receive_payload_pipeline_formal_wsl.py','generate_receive_payload_pipeline.py'):
        shutil.copy2(root/'tools'/name,evidence/name)
    for path in(evidence/'audit.json',root/'build/validation/receive-payload-settling.json'):
        path.write_text(json.dumps(result,indent=2)+'\n')
    require_settling_audit(root)
    print(json.dumps(dict(phase=result['phase'],key=result['key'])))


if __name__=='__main__':main()
