"""Register the status-zero predicate on the measured response/recovery path."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def edits():
    return {
        'rpc_http2_response_partition': [
            ('output wire result_valid,input wire result_ready,',
             'output wire result_valid,output wire result_successful,input wire result_ready,'),
            ('reg base_complete,transport_active;', 'reg base_complete,transport_active;\n    reg status_zero;\n    assign result_successful=result_valid&&status_zero;'),
            ('result_status<=status_code;', 'result_status<=status_code;status_zero<=status_code==0;'),
            ('result_status<=child_status;', 'result_status<=child_status;status_zero<=child_status==0;'),
            ('result_status<=0;', 'result_status<=0;status_zero<=1;'),
        ],
        'rpc_grpc_http2_parser_response': [
            ('wire [7:0] rpc_stage,rpc_status,rpc_memory;', 'wire [7:0] rpc_stage,rpc_status,rpc_memory;\nwire rpc_result_successful;'),
            ('.result_valid(rpc_result_valid),', '.result_valid(rpc_result_valid),\n    .result_successful(rpc_result_successful),'),
            ('wire authorized=rpc_result_valid&&rpc_status==0&&', 'wire authorized=rpc_result_successful&&'),
            ('assign result_progress_committed=rpc_result_valid&&rpc_status==0;', 'assign result_progress_committed=rpc_result_successful;'),
            ('wire transport_failure=active&&rpc_result_valid&&rpc_status==0&&', 'wire transport_failure=active&&rpc_result_successful&&'),
        ],
    }


def apply(original, replacements):
    text=original.replace('\r\n','\n')
    certificate=[]
    for before,after in replacements:
        count=text.count(before)
        assert count>0,before
        text=text.replace(before,after)
        certificate.append(dict(old=before,new=after,count=count))
    inverse=text
    for item in reversed(certificate):
        assert inverse.count(item['new'])==item['count'],item
        inverse=inverse.replace(item['new'],item['old'])
    assert inverse==original.replace('\r\n','\n')
    return text,certificate


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',default='rpc-success-predicate-v2');args=ap.parse_args()
    assert args.name=='rpc-success-predicate-v2'
    root=Path(__file__).resolve().parents[1]
    read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    corpus=read(root/'build/validation/rpc-completion-flags-corpus.json')
    native=read(root/'build/validation/rpc-completion-flags-parser-native.json')
    assert corpus['key']=='5e0925fc997e1e08' and corpus['full_native_corpus_verified']
    assert native['key']=='57c84d760ff80e9f' and native['setup_slack_ns']==-1.073 and not native['timing_met']
    parent=root/'build/experiments/rpc-completion-flags'
    target=root/'build/experiments'/args.name;target.mkdir(parents=True,exist_ok=False)
    for n,h in corpus['executed_parser_sha256'].items():
        source=parent/'rtl'/(n+'.v');assert sha(source)==h
        destination=target/'rtl'/source.name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    certificates={}
    for n,replacements in edits().items():
        p=target/'rtl'/(n+'.v');original=p.read_bytes().decode()
        text,certificate=apply(original,replacements)
        newline='\r\n' if '\r\n' in original else '\n'
        old_ports=ports(original,n);new_ports=ports(text,n)
        if n=='rpc_http2_response_partition':
            assert [port for port in new_ports if port[2]!='result_successful']==old_ports
            assert [port for port in new_ports if port[2]=='result_successful']==[('output','','result_successful')]
            assert [x['count'] for x in certificate]==[1,1,1,1,2]
        else:
            assert new_ports==old_ports and [x['count'] for x in certificate]==[1,1,1,1,1]
        p.write_bytes(text.replace('\n',newline).encode())
        certificates[n]=dict(original_sha256=corpus['executed_parser_sha256'][n],original_newline=newline,edits=certificate)
    actual={n:sha(p) for n,p in closure('http2_enveloped_parser_application',target).items()}
    assert len(actual)==77 and {n for n,h in actual.items() if h!=corpus['executed_parser_sha256'][n]}==set(edits())
    result=dict(phase='rpc_success_predicate_generated',parent_corpus_audit_key=corpus['key'],parent_native_audit_key=native['key'],
        exact_parser_modules=77,changed_existing_modules=sorted(edits()),source_edit_certificates=certificates,
        added_private_child_output='result_successful',public_application_ports_unchanged=True,
        predicate_reference='result_valid && result_status == 0',state_transitions_and_existing_assignments_preserved=True,
        actual_subtree_formal_verified=False,native_timing_verified=False,full_system_complete=False,
        outputs_sha256={'rtl/'+n+'.v':h for n,h in actual.items()},generator_sha256=sha(Path(__file__)))
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    (target/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],exact_parser_modules=77)))


if __name__=='__main__':main()
