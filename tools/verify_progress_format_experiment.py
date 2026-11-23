"""Audit actual retained native responses and all three FORMAT ledger faults."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from generate_two_fpga_application import header_end
from verify_frozen_raw_execution import verify_execution

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=json.loads((root/'build/validation/window-authority-experiment.json').read_text())
    counter=json.loads((root/'build/validation/retained-native-progress-counterexample.json').read_text())
    folder=root/'build/experiments/progress-format'
    generation=json.loads((folder/'generation.json').read_text())
    cases=json.loads((folder/'case-generation.json').read_text())
    faults=json.loads((folder/'faults/generation.json').read_text())
    ledger=json.loads((folder/'ledger-witness-generation.json').read_text())
    executions={};parser_hashes=None
    for label,name,profile in (('retained_native','progress_format_retained_native_authority_v2','native'),
        ('all_ledger_faults','progress_format_all_ledger_ack_faults_v2','shutdown-faults')):
        record,archive,source=verify_execution(root,name,profile)
        assert parser_hashes is None or parser_hashes==record['parser_sha256']
        parser_hashes=record['parser_sha256'];assert record['tokenizer_sha256']==parent['executed_tokenizer_sha256']
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
            'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert record['inputs_sha256'][n]==parent['executions']['native']['inputs_sha256'][n]
        assert record['inputs_sha256']['sim/cocotb/progress_format_witness.py']==cases['witness_sha256']==faults['witness_sha256']
        assert record['inputs_sha256']['sim/cocotb/window_format_witness.py']==cases['base_witness_sha256']
        assert record['inputs_sha256']['sim/cocotb/progress_ledger_window_witness.py']==cases['ledger_witness_sha256']==ledger['witness_sha256']
        a=record['acceptance'];formats=a['actual_format_transactions']
        for item in formats:
            p=item['actual_progress_format']
            assert p['result']==item['result'][:3]
            if p['result']==[0,0,0]:
                assert p['base']==7786944 and p['bytes']==96
                assert len(p['acks'])==len(p['commands'])==12 and all(c['status']==0 for c in p['acks'])
            assert p['held_public_cycles']>=3
        if label=='retained_native':
            assert record['inputs_sha256']['sim/cocotb/test_raw_grpc_enveloped.py']==cases['fixture_sha256']
            assert a['native_rpc_round_trips']==4 and a['actual_dma_returns']==8 and len(formats)==2
            assert a['drained_global_reset_boundaries']==1 and a['both_memory_banks_retained_without_bfm_clear']
            assert a['same_rpc_addresses_and_generations_reused']
            assert len(a['epochs'])==2 and a['epochs'][0]['rpc_addresses']==a['epochs'][1]['rpc_addresses']==[7232000,7232128]
            for epoch in a['epochs']:
                old=counter['diagnostic']['completed_epochs'][0]
                for n in ('generations','actual_dma_ids','native_response_bodies'):assert epoch[n]==old[n]
                assert epoch['all_real_owners_drained']
        else:
            assert record['inputs_sha256']['sim/cocotb/test_raw_shutdown_faults.py']==faults['fixture_sha256']
            assert len(a['actual_receive_format_fault_cases'])==12 and len(a['actual_window_format_fault_cases'])==6
            assert [x['phase']for x in a['actual_progress_format_fault_cases']]==list(range(12))
            assert all(x['error']==0x75 and x['actual_commands_before_error']==x['phase']+1 and x['explicit_same_scope_retry_without_reset']for x in a['actual_progress_format_fault_cases'])
            assert len(formats)==68 and sum(item['result'][0]==0 for item in formats)==33
            pfailed=[item['actual_progress_format']for item in formats if item['result'][:3]==[5,18,0x75]]
            assert len(pfailed)==12
            for phase,p in enumerate(pfailed):
                assert len(p['commands'])==len(p['acks'])==phase+1
                assert [x['status']for x in p['acks']]==[0]*phase+[0x75]
            assert sum(item['result'][:3]==[2,20,0]for item in formats)==1
            assert sum(item['result'][:3]==[7,19,0]for item in formats)==1
        executions[label]=record
    changed=[n for n,h in parser_hashes.items()if h!=parent['executed_parser_sha256'][n]]
    assert changed==['http2_enveloped_parser_core']
    core=(folder/'rtl/http2_enveloped_parser_core.v').read_text()
    old=(root/'build/experiments/window-authority/rtl/http2_enveloped_parser_core.v').read_text()
    assert core[:header_end(core,'http2_enveloped_parser_core')]==old[:header_end(old,'http2_enveloped_parser_core')]
    replay=root/'build/validation/progress-format-generation-replay'
    paths=set(generation['input_sha256'])|{'tools/generate_progress_format_experiment.py','tools/generate_progress_format_fault_case.py',
        'tools/generate_receive_pool_experiment.py','tools/generate_two_fpga_application.py','tools/generate_bidirectional_application.py',
        'tools/generate_progress_ledger_witness.py','sim/cocotb/progress_ledger_window_witness.py',
        'sim/cocotb/progress_format_witness.py','sim/cocotb/window_format_witness.py',
        'build/experiments/retained-native-roundtrip/test_raw_grpc_enveloped.py',
        'build/experiments/window-format/sim/test_raw_shutdown_faults.py'}
    for n in paths:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path(root, n),p)
        assert n not in generation['input_sha256'] or sha(source_path(root, n))==generation['input_sha256'][n]
    for generator,manifest,expected in (('generate_progress_ledger_witness.py','ledger-witness-generation.json',ledger),
        ('generate_progress_format_experiment.py','generation.json',generation),
        ('generate_progress_format_fault_case.py','faults/generation.json',faults)):
        assert sha(root/'tools'/generator)==expected['generator_sha256']
        subprocess.run([sys.executable,str(replay/'tools'/generator)],check=True,capture_output=True,text=True)
        assert json.loads((replay/'build/experiments/progress-format'/manifest).read_text())==expected
    assert json.loads((replay/'build/experiments/progress-format/case-generation.json').read_text())==cases
    result=dict(phase='global_progress_format_and_retained_native_recovery_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,parent_audit_key=parent['key'],counterexample_audit_key=counter['key'],
        executed_parser_sha256=parser_hashes,executed_tokenizer_sha256=parent['executed_tokenizer_sha256'],
        exact_parser_modules=75,exact_tokenizer_modules=22,changed_parser_modules=changed,
        actual_30_format_ack_faults_and_retries_verified=True,actual_pool_authority_for_progress_writes_verified=True,
        retained_native_json_and_protobuf_recovery_verified=True,public_core_interface_unchanged=True,generator_replay_verified=True,
        whole_system_reset_fault_matrix_verified=False,full_39_retirement_ack_matrix_verified=False,
        full_native_corpus_verified=False,current_native_implementation_verified=False,full_system_complete=False,
        verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/progress-format-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_progress_format_experiment.py',root/'tools/generate_progress_format_fault_case.py',root/'sim/cocotb/progress_format_witness.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/progress-format-experiment.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,actual_format_ack_faults=30,native_rpc_round_trips=4)))


if __name__=='__main__':main()
