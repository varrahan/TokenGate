"""Audit first-memory-cause preservation and retain the separate reset counterexample."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/retire-cause';generation=json.loads((folder/'generation.json').read_text())
    probe=root/'build/experiments/retire-cause-countercase';probe_generation=json.loads((probe/'generation.json').read_text())
    base=json.loads((root/'build/validation/pending-idle-experiment.json').read_text())
    previous=json.loads((root/'build/validation/post-commit-retire-experiment.json').read_text())
    cases=[('native','retire_cause_native','native',base['executions']['native']),
        ('new_ack_fault','retire_cause_new_ack_fault','duplex',previous['executions']['first_directory_ack_fault']),
        ('original_error','retire_cause_original_error_retained','shutdown-faults',None)]
    cache={};executions={};parser_hashes=tokenizer_hashes=None
    for label,name,profile,reference in cases:
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
            for p in top.values():assert inputs[p.as_posix()]==generation['generated_sha256'].get(p.name,sha(root/p))
        baseline_inputs=base['executions']['native']['inputs_sha256']
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n]==baseline_inputs[n]
        assert accepted['complete_model_prefix_immutable'] and accepted['full_system_complete'] is False
        if reference:
            assert accepted==reference['acceptance']
            test='test_raw_grpc_enveloped.py' if profile=='native' else 'test_raw_grpc_duplex.py'
            assert inputs['sim/cocotb/'+test]==reference['inputs_sha256']['sim/cocotb/'+test]
        else:
            assert inputs['sim/cocotb/test_raw_shutdown_faults.py']==probe_generation['fixture_sha256']
            assert accepted['actual_original_control_error']==accepted['actual_public_control_error']
            assert accepted['actual_original_control_error'][2]==0x75
            assert accepted['actual_later_cleanup_rejection']==[13,0x86,0]
            assert accepted['actual_transport_memory_status']==0x75 and accepted['actual_transport_http2_error']==2
            for key in ('original_cause_preserved_after_no_memory_cleanup_rejection',
                        'actual_retirement_pending_and_recovery_retained','new_admission_fenced',
                        'actual_memory_and_wire_promises_drained'):assert accepted[key]
            assert accepted['reset_recovery_verified'] is False
        executions[label]=dict(snapshot=name,acceptance=accepted,inputs_sha256=inputs,
            archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()})
    assert [n for n,h in parser_hashes.items() if h!=base['executed_parser_sha256'][n]]==['http2_classified_parser_transport']
    assert tokenizer_hashes==base['executed_tokenizer_sha256']
    counter=root/'build/wsl-reports/raw_envelope_post_commit_retire_shutdown_faults'
    assert json.loads((counter/'snapshot.json').read_text())['exit_code']==1
    xml=ET.parse(counter/'results.xml');failure=xml.find('.//failure')
    assert failure is not None and 'packet_control_memory_status' in failure.attrib['message'] and '0 == 117' in failure.attrib['message']
    trace=json.loads((counter/'receive_trace.json').read_text())
    responses=[e for e in trace if e['event']=='service_control_rsp']
    assert [(e['op'],e['status'],e['memory_status']) for e in responses[-2:]]==[(3,2,0x75),(6,6,0)]
    warm=root/'build/wsl-reports/raw_envelope_retire_cause_shutdown_faults'
    assert json.loads((warm/'snapshot.json').read_text())['exit_code']==1
    log=(warm/'simulation.log').read_text()
    assert 'Verified shutdown fault directory/0' in log and "('header status', 5, 22, 0, 0" in log
    trace=json.loads((warm/'receive_trace.json').read_text())
    assert any(e['event']=='rx_result' and (e['status'],e['detail'],e['memory_status'])==(3,3,0) for e in trace)
    replay=root/'build/validation/retire-cause-generation-replay'
    paths=set(generation['input_sha256'])|{'tools/generate_retire_cause_experiment.py','tools/generate_retire_cause_countercase.py',
        'tools/generate_receive_pool_experiment.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
        'sim/cocotb/test_raw_shutdown_faults.py'}
    assert generation['generator_sha256']==sha(root/'tools/generate_retire_cause_experiment.py')
    assert probe_generation['generator_sha256']==sha(root/'tools/generate_retire_cause_countercase.py')
    assert probe_generation['source_sha256']==sha(root/'sim/cocotb/test_raw_shutdown_faults.py')
    for n in paths:
        assert n not in generation['input_sha256'] or sha(root/n)==generation['input_sha256'][n]
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,p)
    for generator,subfolder,manifest in (('generate_retire_cause_experiment.py','retire-cause',generation),
        ('generate_retire_cause_countercase.py','retire-cause-countercase',probe_generation)):
        subprocess.run([sys.executable,str(replay/'tools'/generator)],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/experiments'/subfolder/'generation.json').read_text())==manifest
    result=dict(phase='original_memory_cause_survives_retirement_rejection_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,executed_parser_sha256=parser_hashes,executed_tokenizer_sha256=tokenizer_hashes,
        exact_parser_modules=75,exact_tokenizer_modules=22,baseline_idle_guard_audit_key=base['key'],
        original_memory_cause_erasure_reproduced=True,actual_original_cause_and_new_fault_paths_verified=True,
        actual_secondary_recovery_ownership_retained=True,generator_replay_verified=True,
        counterexample_sha256={p.name:sha(p) for p in counter.iterdir() if p.is_file()},
        retained_receive_reset_counterexample_sha256={p.name:sha(p) for p in warm.iterdir() if p.is_file()},
        generation_sha256=sha(folder/'generation.json'),full_shutdown_fault_matrix_verified=False,
        retained_receive_arena_reset_verified=False,current_native_implementation_verified=False,
        full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/retire-cause-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_retire_cause_experiment.py',root/'tools/generate_retire_cause_countercase.py',folder/'generation.json'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/retire-cause-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=3,retained_receive_reset_verified=False)))


if __name__=='__main__':main()
