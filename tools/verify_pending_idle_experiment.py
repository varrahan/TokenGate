"""Bind the conservative idle guard to actual joined behavior and source replay."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--extra-scenarios',action='store_true')
    parser.add_argument('--close-phases',nargs='+',type=int,default=[])
    args=parser.parse_args()
    assert len(set(args.close_phases))==len(args.close_phases) and all(0<=n<14 for n in args.close_phases)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/pending-idle';generation=json.loads((folder/'generation.json').read_text())
    baseline=json.loads((root/'build/validation/post-commit-retire-experiment.json').read_text())
    matrix=json.loads((root/'build/validation/post-retire-fault-matrix.json').read_text())
    packer=json.loads((root/'build/validation/packer-keep-experiment.json').read_text())
    scope_archive=root/'build/wsl-reports/raw_envelope_post_retire_other_connection_scope'
    scope_inputs=json.loads((scope_archive/'inputs.json').read_text())
    cases=[('native','pending_idle_native','native',baseline['executions']['native']),
        ('late_rst','pending_idle_late_rst','duplex',baseline['executions']['rst_idle_stream']),
        ('other_connection','pending_idle_other_connection','duplex',dict(
            acceptance=matrix['second_connection_acceptance'],inputs_sha256=scope_inputs))]
    if args.extra_scenarios:
        cases.extend([('early_zero_window','pending_idle_early_zero_window','duplex',packer['executions']['credit_cancel']),
            ('held_trailer','pending_idle_held_trailer','duplex',baseline['executions']['held_trailer'])])
    cases.extend(('close_fault_'+str(n),'pending_idle_close_fault_'+str(n),'duplex',packer['executions']['close_fault_'+str(n)])
        for n in args.close_phases)
    executions={};cache={};parser_hashes=tokenizer_hashes=None
    for label,name,profile,previous in cases:
        archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
        read=lambda n:json.loads((archive/n).read_text())
        inputs,report,state,accepted=(read(n) for n in ('inputs.json','report.json','snapshot.json','acceptance.json'))
        assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
        assert report['profile']==state['profile']==profile and report['tests']==1 and report['failures']==0
        assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
        for n,h in inputs.items():
            assert sha(source/n)==h,(name,n)
            if n.startswith('native-vendor/'):assert sha(root/'.venv312/Lib/site-packages'/n.split('/',1)[1])==h
        xml=ET.parse(archive/'results.xml')
        assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure') and not xml.findall('.//error')
        signature=tuple(sorted((n,h) for n,h in inputs.items() if n.startswith('rtl/') and n.endswith('.v')))
        if signature not in cache:
            cache[signature]={top:{n:p.relative_to(source) for n,p in closure(top,source).items()}
                for top in ('http2_enveloped_parser_application','tokenizer_fpga_memory_subsystem')}
        hashes=[{n:sha(source/p) for n,p in cache[signature][top].items()}
            for top in ('http2_enveloped_parser_application','tokenizer_fpga_memory_subsystem')]
        assert tuple(map(len,hashes))==(75,22)
        assert parser_hashes is None or parser_hashes==hashes[0]
        assert tokenizer_hashes is None or tokenizer_hashes==hashes[1]
        parser_hashes,tokenizer_hashes=hashes
        for top in cache[signature].values():
            for p in top.values():assert inputs[p.as_posix()]==generation['generated_sha256'].get(p.name,sha(source_path(root, p)))
        assert accepted==previous['acceptance'],label
        test='test_raw_grpc_enveloped.py' if profile=='native' else 'test_raw_grpc_duplex.py'
        for n in ('sim/cocotb/'+test,'sim/cocotb_two_fpga_enveloped_top.sv','build/bidirectional-fixtures/memory.mem',
                  'build/bidirectional-fixtures/reference_cases.json','build/bidirectional-fixtures/response_reference.json'):
            assert inputs[n]==previous['inputs_sha256'][n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        executions[label]=dict(snapshot=name,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    assert set(parser_hashes)==set(baseline['executed_parser_sha256'])
    assert [n for n,h in parser_hashes.items() if h!=baseline['executed_parser_sha256'][n]]==['http2_enveloped_frame_grants']
    assert tokenizer_hashes==baseline['executed_tokenizer_sha256']
    before=root/'build/experiments/post-commit-retire/rtl/http2_enveloped_frame_grants.v'
    after=folder/'rtl/http2_enveloped_frame_grants.v'
    assert after.read_text().replace(generation['new_assignment'],generation['old_assignment'])==before.read_text()
    text=re.sub(r'//[^\n]*|/\*.*?\*/','',after.read_text(),flags=re.S)
    assert len(re.findall(r'(?<!\.)\bidle\b',text))==2  # Output declaration and assignment only; no local feedback.
    replay=root/'build/validation/pending-idle-generation-replay'
    assert generation['generator_sha256']==sha(root/'tools/generate_pending_idle_experiment.py')
    paths=set(generation['input_sha256'])|{'tools/generate_pending_idle_experiment.py','tools/generate_receive_pool_experiment.py',
        'tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py'}
    for n in paths:
        assert n not in generation['input_sha256'] or sha(source_path(root, n))==generation['input_sha256'][n]
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, n),p)
    subprocess.run([sys.executable,str(replay/'tools/generate_pending_idle_experiment.py')],check=True,capture_output=True,text=True)
    assert json.loads((replay/'build/experiments/pending-idle/generation.json').read_text())==generation
    result=dict(phase='pending_window_idle_guard_joined_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,executed_parser_sha256=parser_hashes,executed_tokenizer_sha256=tokenizer_hashes,
        exact_parser_modules=75,exact_tokenizer_modules=22,baseline_direct_audit_key=baseline['key'],
        baseline_fault_matrix_key=matrix['key'],all_selected_acceptance_records_equal_baselines=True,
        only_changed_module='http2_enveloped_frame_grants',only_module_idle_output_equation_changed=True,
        no_module_state_or_handshake_equations_changed=True,no_internal_idle_feedback=True,
        generator_replay_verified=True,complete_model_and_native_packages_verified=True,
        generation_sha256=sha(folder/'generation.json'),actual_close_fault_phases=sorted(args.close_phases),
        all_fourteen_fatal_close_ack_faults_verified=set(args.close_phases)==set(range(14)),
        new_retirement_ack_matrix_on_candidate_verified=False,full_native_corpus_on_candidate_verified=False,
        native_timing_improvement_verified=False,current_native_implementation_verified=False,
        formal_equivalence_claimed=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/pending-idle-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_pending_idle_experiment.py',folder/'generation.json'):shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/pending-idle-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=len(executions),close_fault_phases=sorted(args.close_phases))))


if __name__=='__main__':main()
