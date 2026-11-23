"""Bind the complete native corpus to the executed 75/22-module cancellation build."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from verify_native_grpc_corpus_reference import verify_reference
from verify_two_fpga_application import closure


def main():
    parser=argparse.ArgumentParser()
    variants=parser.add_mutually_exclusive_group()
    variants.add_argument('--post-commit-retire',action='store_true',help='Audit the newer retirement variant full corpus')
    variants.add_argument('--receive-format',action='store_true',help='Audit the global receive FORMAT child full corpus')
    variants.add_argument('--window-authority',action='store_true',help='Audit private global window FORMAT and cleanup cause full corpus')
    variants.add_argument('--progress-format',action='store_true',help='Audit global response-progress initialization full corpus')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    variant='progress-format' if args.progress_format else 'window-authority' if args.window_authority else 'receive-format' if args.receive_format else 'post-commit-retire' if args.post_commit_retire else 'local-cancel'
    name=variant.replace('-','_')+'_full_native_corpus' if variant!='local-cancel' else 'local_cancel_full_native_corpus_observer_fixed'
    archive=root/'build/wsl-reports'/('raw_envelope_'+name)
    source=archive/'execution-sources'
    read=lambda n:json.loads((archive/n).read_text())
    inputs,report,state,accepted=(read(n) for n in ('inputs.json','report.json','snapshot.json','acceptance.json'))
    assert state['exit_code']==0 and report['phase']==accepted['phase']=='passed'
    assert report['profile']==state['profile']=='workload' and report['tests']==1 and report['failures']==0
    assert report['input_sha256']==inputs and report['acceptance_sha256']==sha(archive/'acceptance.json')
    for n,h in inputs.items():
        assert sha(source/n)==h,n
        if n.startswith('native-vendor/'):
            assert sha(root/'.venv312/Lib/site-packages'/n.split('/',1)[1])==h
    xml=ET.parse(archive/'results.xml')
    assert len(xml.findall('.//testcase'))==1 and not xml.findall('.//failure') and not xml.findall('.//error')
    assert xml.find('.//testcase').attrib['name']=='complete_prompt_corpus_uses_native_grpc_and_actual_dma'
    direct=json.loads((root/'build/validation'/ (variant+'-experiment.json')).read_text())
    dag=closure('http2_enveloped_parser_application',source)
    tokenizer=closure('tokenizer_fpga_memory_subsystem',source)
    assert len(dag)==75 and len(tokenizer)==22
    parser_hashes={n:sha(p) for n,p in dag.items()}
    assert parser_hashes==direct['executed_parser_sha256']
    direct_native=direct['executions']['retained_native' if args.progress_format else 'native']
    baseline_source=root/'build/wsl-reports'/('raw_envelope_'+direct_native['snapshot'])/'execution-sources'
    assert {n:sha(p) for n,p in tokenizer.items()}=={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',baseline_source).items()}
    generation=json.loads((root/'build/experiments/local-cancel/generation.json').read_text())
    adapted=None
    if args.progress_format:
        adapted=json.loads((root/'build/experiments/progress-format/regressions/generation.json').read_text())
        case=adapted['cases']['full_native_corpus']
        assert case['source_sha256']==generation['sim_sha256']['test_raw_grpc_workload.py']
        assert inputs['sim/cocotb/test_raw_grpc_workload.py']==case['fixture_sha256']
    else:assert inputs['sim/cocotb/test_raw_grpc_workload.py']==generation['sim_sha256']['test_raw_grpc_workload.py']
    assert inputs['sim/cocotb_two_fpga_enveloped_top.sv']==generation['sim_sha256']['cocotb_two_fpga_enveloped_top.sv']
    pool=accepted['actual_receive_pool_ownership']
    has_global_format=args.receive_format or args.window_authority or args.progress_format
    assert pool['receive_grants']==pool['receive_unlocks']==pool['ordinary_commands']==(17 if has_global_format else 16)
    assert pool['init_commands']==17 and pool['close_commands']==32
    assert pool['receive_memory_commands']==pool['receive_memory_acks']==(1398 if has_global_format else 1386)
    reference=verify_reference(root,source,accepted,parser_memory_clients=19,
        native_wire_frames=2828+2*16+3+16)
    result=dict(phase=variant.replace('-','_')+'_complete_native_corpus_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        snapshot=name,acceptance=accepted,independent_native_reference=reference,
        direct_audit_key=direct['key'],executed_parser_sha256=parser_hashes,
        executed_tokenizer_sha256={n:sha(p) for n,p in tokenizer.items()},
        exact_parser_modules=75,exact_tokenizer_modules=22,full_native_corpus_verified=True,
        inputs_sha256=inputs,archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()},
        actual_execution_sources_verified=True,full_image_and_native_tokenizer_verified=True,
        source_generation_sha256=sha(root/'build/experiments/local-cancel/generation.json'),
        verifier_sha256=sha(Path(__file__)),reference_verifier_sha256=sha(root/'tools/verify_native_grpc_corpus_reference.py'),
        full_protocol_acceptance=False,physical_interfaces_verified=False,full_system_complete=False)
    if adapted:result['adapted_corpus_generation_sha256']=sha(root/'build/experiments/progress-format/regressions/generation.json')
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation'/(variant+'-corpus-evidence')/key
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/verify_native_grpc_corpus_reference.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation'/(variant+'-corpus.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,calls=16,actual_dma_ids=2828,wire_frames=2879)))


if __name__=='__main__':main()
