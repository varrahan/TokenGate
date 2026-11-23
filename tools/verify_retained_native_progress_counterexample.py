"""Bind retained response-progress rejection to the actual full-model RTL run."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from verify_frozen_raw_execution import verify_execution


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    name='window_authority_retained_native_progress_capture'
    record,archive,source=verify_execution(root,name,'native',passed=False)
    direct=json.loads((root/'build/validation/window-authority-experiment.json').read_text())
    assert record['parser_sha256']==direct['executed_parser_sha256']
    assert record['tokenizer_sha256']==direct['executed_tokenizer_sha256']
    for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
        'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
        assert record['inputs_sha256'][n]==direct['executions']['native']['inputs_sha256'][n]
    diagnostic=json.loads((archive/'failure.json').read_text())
    assert [diagnostic[n]for n in ('epoch','stream','token','ordinal','rpc_address','generation','progress_address')]==[1,1,15339,0,7232000,1,7786944]
    assert diagnostic['actual_result']==[4,4,0,1,0]
    assert diagnostic['both_memory_bank_objects_retained']
    progress=diagnostic['actual_hardware_progress']
    assert progress.to_bytes(32,'little').hex()==diagnostic['actual_hardware_progress_hex']==diagnostic['progress_before_hex']
    assert [progress&0xffffffff,progress>>32&0xffffffff,progress>>64&0xffffffff,
        progress>>96&0xffffffff,progress>>128&0xffffffff]==[0x52535031,1,23,9,2]
    assert all(progress>>bit&1 for bit in (186,188,190))
    epochs=diagnostic['completed_epochs'];assert len(epochs)==1 and epochs[0]['all_real_owners_drained']
    assert epochs[0]['rpc_addresses']==[7232000,7232128] and epochs[0]['generations']==[1,2]
    assert epochs[0]['actual_dma_ids']==[[1,15339,0,0],[1,1917,1,1],[3,15339,0,0],[3,1917,1,1]]
    formats=diagnostic['actual_format_transactions'];assert len(formats)==2
    for item in formats:
        assert item['result'][:3]==[0,0,0]
        assert len(item['acks']['26'])==12 and len(item['acks']['22'])==6
        assert all(a['status']==0 for a in item['acks']['26']+item['acks']['22'])
    generation=json.loads((root/'build/experiments/retained-native-roundtrip/generation.json').read_text())
    assert generation['fixture_sha256']==record['inputs_sha256']['sim/cocotb/test_raw_grpc_enveloped.py']
    assert generation['generator_sha256']==sha(source/'tools/generate_retained_native_roundtrip_case.py')
    replay=root/'build/validation/retained-native-progress-generation-replay'
    for n,p in (('tools/generate_retained_native_roundtrip_case.py',source/'tools/generate_retained_native_roundtrip_case.py'),
        ('build/experiments/post-commit-retire/sim/test_raw_grpc_enveloped.py',root/'build/experiments/post-commit-retire/sim/test_raw_grpc_enveloped.py')):
        target=replay/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    assert sha(replay/'build/experiments/post-commit-retire/sim/test_raw_grpc_enveloped.py')==generation['source_sha256']
    subprocess.run([sys.executable,str(replay/'tools/generate_retained_native_roundtrip_case.py')],check=True,capture_output=True,text=True)
    assert json.loads((replay/'build/experiments/retained-native-roundtrip/generation.json').read_text())==generation
    result=dict(phase='retained_native_progress_counterexample_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        snapshot=name,execution=record,diagnostic=diagnostic,direct_audit_key=direct['key'],
        actual_prior_eos_progress_loaded_with_reused_generation=True,actual_rx_tx_global_format_completed=True,
        actual_initial_native_json_and_protobuf_calls_passed=True,generator_replay_verified=True,
        retained_native_recovery_verified=False,full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/retained-native-progress-counterexample-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),source/'tools/generate_retained_native_roundtrip_case.py',archive/'failure.json'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/retained-native-progress-counterexample.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key)))


if __name__=='__main__':main()
