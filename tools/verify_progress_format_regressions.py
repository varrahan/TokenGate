"""Bind inherited protocol/reset scenarios to the global progress FORMAT child."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from verify_frozen_raw_execution import verify_execution


TIMING_KEYS={'clock','ack_clock','request_clock','first_offer_clock','result_ack_clock',
    'receive_lock_cycles','held_original_result_cycles','host_close_retired_clock',
    'wire_retired_clock','first_public_packet_result_clock'}


def semantic(value):
    if isinstance(value,dict):return {k:semantic(v)for k,v in value.items()if k not in TIMING_KEYS and k!='actual_progress_format'}
    if isinstance(value,list):return [semantic(v)for v in value]
    return value


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    current=json.loads((root/'build/validation/progress-format-experiment.json').read_text())
    parent=json.loads((root/'build/validation/window-authority-experiment.json').read_text())
    manifest_path=root/'build/experiments/progress-format/regressions/generation.json'
    generation=json.loads(manifest_path.read_text());executions={}
    for label in ('native','other_connection','owned_gpu_drain','external_denial','retained_shutdown'):
        case=generation['cases'][label]
        record,archive,source=verify_execution(root,'progress_format_'+label,case['profile'])
        assert record['parser_sha256']==current['executed_parser_sha256']
        assert record['tokenizer_sha256']==current['executed_tokenizer_sha256']
        test='sim/cocotb/'+Path(case['fixture']).name
        assert record['inputs_sha256'][test]==case['fixture_sha256']
        baseline=parent['executions']['external_denial_witness'if label=='external_denial'else label]
        assert case['source_sha256']==baseline['inputs_sha256'][test]
        for n in ('build/bidirectional-fixtures/memory.mem','build/bidirectional-fixtures/reference_cases.json',
            'build/bidirectional-fixtures/response_reference.json','sim/cocotb_two_fpga_enveloped_top.sv'):
            assert record['inputs_sha256'][n]==baseline['inputs_sha256'][n]
        a=record['acceptance'];assert semantic(a)==semantic(baseline['acceptance']),label
        if label=='native':
            assert [a[n]for n in ('native_complete_grpc_calls','actual_forward_dma_ids','actual_gpu_descriptors_accepted','actual_captured_dma_ids_returned','native_wire_frames')]==[2,6,8,4,16]
            assert a['actual_receive_pool_ownership']['receive_lock_cycles']>0
        elif label=='other_connection':
            assert [a[n]for n in ('actual_other_connection_user','actual_other_stream','actual_other_rpc_address','actual_other_generation','actual_same_rpc_address','actual_reused_generation')]==[1,1,7232128,2,7232000,3]
            assert a['actual_other_regions_unchanged_through_reopen']and a['actual_other_rpc_closed_after_its_own_response']
            assert a['actual_post_commit_retirement']['held_original_result_cycles']>=13
            o=a['local_error_ownership']
            assert o['wire_retired_clock']<o['host_close_retired_clock']<o['first_public_packet_result_clock']
        elif label=='owned_gpu_drain':
            assert a['held_wire_cycles']==17 and a['actual_ordering'][0]['event']=='actual_gpu_result_ack'
            assert a['actual_ordering'][1]['event']=='actual_format_request_ack'
            assert a['actual_ordering'][0]['clock']<a['actual_ordering'][1]['clock']
        elif label=='external_denial':
            assert a['actual_external_format_denials']==[dict(maintenance=m,result=[7,16,0],memory_commands=0)for m in (1,0)]
        else:
            assert [a[n]for n in ('directory_close_faults','window_close_faults','peer_goaway_faults')]==[9,14,18]
            assert len(a['actual_raw_fault_cases'])==41 and a['retained_window_arena_warm_reset_verified']
            trace=json.loads((archive/'window_trace.json').read_text())
            init=[r for r in trace if r['event']=='actual_admission_window_request'and r['op']==1]
            assert len(init)==42 and all(r['generation']==1 and r['record_address']==7232000 and r['window_address']==0x7f0000 and r['retained_window_hex']==bytes(16).hex()for r in init)
            assert all(r['status']==r['detail']==r['memory_status']==0 for r in trace if r['event']=='actual_admission_window_result')
        if label in ('native','other_connection'):
            events=a['actual_post_commit_retirement']['actual_trace']
            assert all(x['clock']<=y['clock']for x,y in zip(events,events[1:]))
        if label in ('owned_gpu_drain','external_denial'):
            assert record['inputs_sha256']['sim/cocotb/progress_format_witness.py']==generation['witness_sha256']
            assert len(a['actual_format_transactions'])==2
            for transaction in a['actual_format_transactions']:
                p=transaction['actual_progress_format']
                assert p['result']==[0,0,0] and p['base']==7786944 and p['bytes']==96
                assert len(p['commands'])==len(p['acks'])==12 and all(x['status']==0 for x in p['acks'])
                assert p['held_public_cycles']>=13
        executions[label]=record
    replay=root/'build/validation/progress-format-regression-generation-replay'
    paths={'tools/generate_progress_format_regressions.py','sim/cocotb/progress_format_witness.py',
        'build/experiments/post-retire-fault-matrix/generation.json'}|{v['source']for v in generation['cases'].values()}
    assert sha(root/'tools/generate_progress_format_regressions.py')==generation['generator_sha256']
    for n in paths:
        p=replay/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,p)
    subprocess.run([sys.executable,str(replay/'tools/generate_progress_format_regressions.py')],check=True,capture_output=True,text=True)
    assert json.loads((replay/'build/experiments/progress-format/regressions/generation.json').read_text())==generation
    result=dict(phase='global_progress_format_inherited_protocol_and_shutdown_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        executions=executions,direct_audit_key=current['key'],parent_audit_key=parent['key'],
        executed_parser_sha256=current['executed_parser_sha256'],executed_tokenizer_sha256=current['executed_tokenizer_sha256'],
        generator_replay_verified=True,semantic_acceptance_matches_parent=True,
        timing_fields_compared_by_required_ordering_not_cycle_equality=sorted(TIMING_KEYS),
        all_41_retained_window_shutdown_faults_verified=True,actual_other_connection_scope_verified=True,
        actual_owned_gpu_drain_before_format_verified=True,external_global_format_opcode_denied=True,
        full_39_retirement_ack_matrix_verified=False,full_native_corpus_verified=False,
        whole_system_reset_fault_matrix_verified=False,current_native_implementation_verified=False,
        full_system_complete=False,verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/progress-format-regression-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/progress-format-regressions.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,executions=5,shutdown_faults=41)))


if __name__=='__main__':main()
