"""Bind cocotb execution, independent native oracle and native RTL snapshot."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser()
    parser.add_argument('--reports',type=Path,default=root/'build/wsl-reports/cocotb_http2_prefill')
    parser.add_argument('--reference',type=Path,default=root/'build/cocotb-prefill-reference-validation.json')
    parser.add_argument('--output',type=Path,default=root/'build/validation/cocotb-http2-prefill.json')
    args=parser.parse_args();reports=args.reports
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    report=json.loads((reports/'report.json').read_text())
    acceptance=json.loads((reports/'acceptance.json').read_text())
    oracle=json.loads(args.reference.read_text())
    assert report['phase']=='passed'and report['tests']==1 and report['failures']==0
    assert not report.get('changed_inputs')
    assert acceptance['phase']==oracle['phase']=='passed'
    assert sha(reports/'acceptance.json')==report['acceptance_sha256']
    assert oracle['verifier_sha256']==sha(root/'tools/verify_http2_prefill_references.py')
    model_folder=root/'build/scu35/image'
    assert oracle['complete_model_prefix_matches_image']
    assert oracle['model_image_sha256']==sha(model_folder/'external_memory.bin')
    assert oracle['model_manifest_sha256']==sha(model_folder/'external_manifest.json')
    tree=ET.parse(reports/'results.xml');cases=tree.findall('.//testcase')
    assert len(cases)==1 and cases[0].attrib['name']=='raw_http2_grpc_to_full_model_token_dma'
    assert not tree.findall('.//failure')and not tree.findall('.//error')
    native_name='http2_grpc_prefill_indexed_word_selectors'
    native=root/'build/implementation/xcsu35p-sbvb625-2-e'/native_name
    rtl_count=0
    for name,digest in report['source_sha256'].items():
        assert sha(source_path(root, name))==digest,('Current source differs',name)
        if name.startswith('rtl/'):
            assert sha(native/'sources'/name)==digest,('Native RTL differs',name)
            rtl_count+=1
    assert rtl_count>50
    assert set(oracle['fixture_sha256'])=={Path(name).name for name in report['fixture_sha256']}
    for name,digest in report['fixture_sha256'].items():
        assert sha(source_path(root, name))==digest,('Current fixture differs',name)
        assert oracle['fixture_sha256'][Path(name).name]==digest,('Native/simulation fixture differs',name)
    assert(acceptance['packets'],acceptance['headers'],acceptance['messages'],acceptance['token_ids'],
           acceptance['packet_aborts'],acceptance['rejected'],acceptance['connection_opens'],acceptance['memory_faults'])==(38,21,16,2828,4,3,7,2)
    assert(oracle['wire_packets'],oracle['grpc_messages'],oracle['native_token_ids'])==(38,16,2828)
    assert acceptance['dma_stall_cycles']>0 and acceptance['axi_line_refills']>0 and acceptance['axi_writes']>0
    assert acceptance['model_and_policy_immutable']and acceptance['full_model_bytes']==8388608
    assert not acceptance['complete_http2_transport_verified']and not acceptance['reverse_path_verified']
    assert not oracle['rtl_execution_verified']and not oracle['full_transport_verified']
    assert 'PASS: cocotb raw HTTP/2/gRPC' in(reports/'simulation.log').read_text()
    # Preserve completed evidence before future runs replace latest-report paths.
    evidence_key=hashlib.sha256((sha(reports/'report.json')+sha(args.reference)+sha(Path(__file__))).encode()).hexdigest()[:16]
    evidence=root/'build/validation/cocotb-http2-prefill-evidence'/evidence_key
    for name,digest in {**report['source_sha256'],**report['fixture_sha256']}.items():
        target=evidence/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==digest,('Evidence directory belongs to another revision',name)
        else:shutil.copy2(source_path(root, name),target)
    for name in('report.json','acceptance.json','results.xml','simulation.log','build.log'):
        target=evidence/'reports'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(reports/name),('Evidence already differs',name)
        else:shutil.copy2(reports/name,target)
    target=evidence/'native-reference.json'
    if target.exists():assert sha(target)==sha(args.reference)
    else:shutil.copy2(args.reference,target)
    for name in('verify_cocotb_prefill.py','verify_http2_prefill_references.py'):
        target=evidence/'verification'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(root/'tools'/name)
        else:shutil.copy2(root/'tools'/name,target)
    for name in('external_manifest.json','external_memory.bin'):
        target=evidence/'model'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(model_folder/name)
        else:shutil.copy2(model_folder/name,target)
    result=dict(phase='passed',verified_utc=datetime.now(timezone.utc).isoformat(),
                sources_verified=len(report['source_sha256']),fixtures_verified=len(report['fixture_sha256']),
                native_rtl_files_matched=rtl_count,native_rtl_snapshot=native_name,
                simulator=report['simulator'],cocotb_version=report['cocotb_version'],simulated_clock_period_ns=4,
                acceptance=acceptance,native_reference_packages=oracle['packages'],
                complete_model_prefix_verified=True,model_ordinary_tokens=oracle['model_ordinary_tokens'],
                model_trie_nodes=oracle['model_trie_nodes'],model_trie_edges=oracle['model_trie_edges'],
                source_and_fixture_inputs_preserved=str(evidence),
                verifier_sha256=sha(Path(__file__)),
                evidence_sha256={name:sha(reports/name)for name in('report.json','acceptance.json','results.xml','simulation.log','build.log')},
                native_reference_sha256=sha(args.reference),
                native_source_provenance_sha256=sha(native/'source-provenance.json'),
                forward_fixture_acceptance_verified=True,complete_http2_transport_verified=False,
                reverse_acceptance_verified=False,physical_adapters_verified=False,
                sustained_throughput_verified=False,full_system_complete=False)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
