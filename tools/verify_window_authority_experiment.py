"""Audit retained-window recovery, private FORMAT authority and error causes."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from generate_two_fpga_application import header_end
from verify_frozen_raw_execution import verify_execution


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/experiments/window-authority'
    generation=json.loads((folder/'generation.json').read_text())
    cases=json.loads((folder/'case-generation.json').read_text())
    cause_generation=json.loads((root/'build/experiments/window-cause/generation.json').read_text())
    parent=json.loads((root/'build/validation/window-format-experiment.json').read_text())
    baseline=json.loads((root/'build/validation/post-retire-fault-matrix.json').read_text())
    original=json.loads((root/'build/validation/retire-cause-experiment.json').read_text())
    executions={};parser_hashes=tokenizer_hashes=None
    checks=[('external_denial_witness','shutdown-faults','test_raw_shutdown_faults.py'),
        ('native','native','test_raw_grpc_enveloped.py'),('other_connection','duplex','test_raw_grpc_duplex.py'),
        ('ledger_faults','shutdown-faults','test_raw_shutdown_faults.py'),
        ('owned_gpu_drain','shutdown-faults','test_raw_shutdown_faults.py'),
        ('retained_shutdown','shutdown-faults','test_raw_shutdown_faults.py'),
        ('receive_ack_0','duplex','test_raw_grpc_duplex.py'),('receive_ack_18','duplex','test_raw_grpc_duplex.py'),
        ('original_error','shutdown-faults','test_raw_shutdown_faults.py')]
    for label,profile,test in checks:
        record,archive,source=verify_execution(root,'window_authority_'+label,profile)
        inputs=record['inputs_sha256'];accepted=record['acceptance']
        assert parser_hashes is None or parser_hashes==record['parser_sha256']
        assert tokenizer_hashes is None or tokenizer_hashes==record['tokenizer_sha256']
        parser_hashes,tokenizer_hashes=record['parser_sha256'],record['tokenizer_sha256']
        for module,h in parser_hashes.items():
            expected=generation['generated_sha256'].get(module+'.v')
            assert h==(expected or parent['executed_parser_sha256'][module])
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
                  'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert inputs[n]==parent['executions']['native']['inputs_sha256'][n]
        if label in parent['executions']:
            assert accepted==parent['executions'][label]['acceptance'],label
            if label in ('ledger_faults','owned_gpu_drain'):
                which='sim' if label=='ledger_faults' else 'drain'
                assert inputs['sim/cocotb/'+test]==cases['files'][which]['fixture_sha256']
            else:
                assert inputs['sim/cocotb/'+test]==parent['executions'][label]['inputs_sha256']['sim/cocotb/'+test]
        elif label=='external_denial_witness':
            assert inputs['sim/cocotb/'+test]==cases['files']['external']['fixture_sha256']
            assert [c['maintenance'] for c in accepted['actual_external_format_denials']]==[1,0]
            assert all(c['result']==[7,16,0] and c['memory_commands']==0 for c in accepted['actual_external_format_denials'])
            assert accepted['actual_authorized_format_and_admission_after_denial'] and accepted['external_denials_issue_no_window_memory']
            assert len(accepted['actual_format_transactions'])==2
            for r in accepted['actual_format_transactions']:
                assert r['result'][0]==0 and len(r['acks']['26'])==12 and len(r['acks']['22'])==6
        elif label.startswith('receive_ack_'):
            phase=int(label.rsplit('_',1)[1]);reference=baseline['executions'][f'client_26_ack_{phase}']
            assert accepted==reference['acceptance']
            assert inputs['sim/cocotb/'+test]==reference['inputs_sha256']['sim/cocotb/'+test]
            assert accepted['actual_retirement_error']==[13,0x85,0x75]
            assert accepted['actual_selected_client_commands_after_request']==phase+1
            assert accepted['actual_no_replay_after_injection_cleared'] and accepted['actual_retirement_pending_and_recovery_retained']
        else:
            reference=original['executions']['original_error'];assert accepted==reference['acceptance']
            assert inputs['sim/cocotb/'+test]==reference['inputs_sha256']['sim/cocotb/'+test]
            assert accepted['actual_original_control_error']==accepted['actual_public_control_error']==[8,2,0x75]
            assert accepted['actual_later_cleanup_rejection']==[13,0x86,0]
        if label in ('external_denial_witness','ledger_faults','owned_gpu_drain'):
            assert inputs['sim/cocotb/private_window_format_witness.py']==cases['witness_sha256']
            assert inputs['sim/cocotb/window_format_witness.py']==cases['base_witness_sha256']
        executions[label]=record
    assert tokenizer_hashes==parent['executed_tokenizer_sha256']
    changed=sorted(n for n,h in parser_hashes.items() if h!=parent['executed_parser_sha256'][n])
    assert changed==['http2_classified_parser_transport','http2_enveloped_frame_grants','http2_enveloped_parser_core',
        'http2_owned_pipelined_cancel_windows','http2_pipelined_cancel_window_store','rpc_grpc_http2_return']
    text=(folder/'rtl/http2_enveloped_parser_core.v').read_text()
    previous=(root/'build/experiments/window-format/rtl/http2_enveloped_parser_core.v').read_text()
    assert text[:header_end(text,'http2_enveloped_parser_core')]==previous[:header_end(previous,'http2_enveloped_parser_core')]
    counterexamples={}
    for label,name,profile in (
        ('external_opcode','window_format_external_opcode_counterexample','shutdown-faults'),
        ('late_receive_cause','window_format_late_receive_cause_counterexample','duplex')):
        counter,archive,source=verify_execution(root,name,profile,passed=False)
        assert counter['parser_sha256']==parent['executed_parser_sha256']
        assert counter['tokenizer_sha256']==parent['executed_tokenizer_sha256']
        diagnostic=json.loads((archive/'failure.json').read_text())
        if label=='external_opcode':
            assert diagnostic==dict(actual_external_result=[0,0,0,6],maintenance=1)
        else:
            assert diagnostic['actual_cleanup_result']==[13,0x85,0x75]
            assert diagnostic['actual_public_result']==[0,8,0,2]
            assert diagnostic['actual_raw_memory']==0x75 and diagnostic['actual_receive_error']==[5,1,0x75]
            assert len(diagnostic['actual_ack_prefix'])==1 and diagnostic['actual_ack_prefix'][0]['status']==0x75
        counter['actual_diagnostic']=diagnostic;counterexamples[label]=counter
    replay=root/'build/validation/window-authority-generation-replay'
    paths=set(generation['input_sha256'])|set(cause_generation['input_sha256'])|{
        'tools/generate_window_authority_experiment.py','tools/generate_window_cause_experiment.py',
        'tools/generate_private_window_cases.py','tools/generate_window_authority_case.py',
        'tools/generate_late_receive_cause_countercase.py','tools/generate_receive_pool_experiment.py',
        'tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
        'sim/cocotb/private_window_format_witness.py','sim/cocotb/window_format_witness.py',
        'build/experiments/post-retire-fault-matrix/client_26_ack_0/test_raw_grpc_duplex.py'}
    paths|={record['source'] for record in cases['files'].values()}
    for n in paths:
        expected=generation['input_sha256'].get(n) or cause_generation['input_sha256'].get(n)
        assert not expected or sha(root/n)==expected
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,p)
    manifests=[('generate_window_cause_experiment.py','window-cause/generation.json',cause_generation),
        ('generate_window_authority_experiment.py','window-authority/generation.json',generation),
        ('generate_window_authority_case.py','window-authority-case/generation.json',json.loads((root/'build/experiments/window-authority-case/generation.json').read_text())),
        ('generate_private_window_cases.py','window-authority/case-generation.json',cases),
        ('generate_late_receive_cause_countercase.py','late-receive-cause-countercase/generation.json',json.loads((root/'build/experiments/late-receive-cause-countercase/generation.json').read_text()))]
    for generator,manifest_path,manifest in manifests:
        assert manifest['generator_sha256']==sha(root/'tools'/generator)
        subprocess.run([sys.executable,str(replay/'tools'/generator)],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/experiments'/manifest_path).read_text())==manifest
    result=dict(phase='private_window_format_and_cleanup_cause_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,counterexamples=counterexamples,executed_parser_sha256=parser_hashes,
        executed_tokenizer_sha256=tokenizer_hashes,exact_parser_modules=75,exact_tokenizer_modules=22,
        changed_parser_modules=changed,parent_audit_key=parent['key'],public_core_interface_unchanged=True,
        private_format_authority_captured_and_observed=True,external_opcode_denied_without_memory=True,
        actual_18_format_ack_faults_and_retries_verified=True,full_41_retained_window_shutdown_faults_verified=True,
        first_and_final_cleanup_receive_ack_faults_verified=True,earlier_memory_cause_preserved=True,
        actual_owned_response_drain_and_other_connection_scope_verified=True,generator_replay_verified=True,
        full_39_retirement_ack_matrix_verified=False,current_native_implementation_verified=False,
        full_native_corpus_verified=False,whole_system_retained_state_recovery_verified=False,
        formal_induction_verified=False,full_system_complete=False,generation_sha256=sha(folder/'generation.json'),
        case_generation_sha256=sha(folder/'case-generation.json'),verifier_sha256=sha(Path(__file__)),
        execution_verifier_sha256=sha(root/'tools/verify_frozen_raw_execution.py'))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/window-authority-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/verify_frozen_raw_execution.py',root/'tools/generate_window_authority_experiment.py',
        root/'tools/generate_window_cause_experiment.py',root/'tools/generate_private_window_cases.py',
        root/'sim/cocotb/private_window_format_witness.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/window-authority-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=len(executions),counterexamples=len(counterexamples))))


if __name__=='__main__':main()
