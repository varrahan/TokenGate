"""Independently bind three conditional lemmas to the exact V6/V7 pair."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from run_rpc_refusal_default_open_formal_wsl import generate,cut_children,proof_script

from rtl_paths import source_relative


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    old=root/'build/experiments/rpc-stream-refusal-v6';new=root/'build/experiments/rpc-stream-refusal-v7'
    generations=[read(p/'generation.json')for p in (old,new)]
    for base,g in zip((old,new),generations):
        assert all(sha(base/n)==h for n,h in g['outputs_sha256'].items())
    oldg,newg=generations
    assert oldg['canonical_parser_sha256'].keys()==newg['canonical_parser_sha256'].keys()
    changed={n for n,h in newg['canonical_parser_sha256'].items()if h!=oldg['canonical_parser_sha256'][n]}
    assert changed=={'http2_receive_flow_controller'}
    assert oldg['canonical_tokenizer_sha256']==newg['canonical_tokenizer_sha256']
    directed=read(root/'build/validation/rpc-stream-refusal-v7-directed.json')
    assert directed['key']=='950ce3b65ccb9b0a' and directed['generation_sha256']==sha(new/'generation.json')
    assert directed['four_directed_application_runs_verified']
    folder=root/'build/wsl-reports'/args.name;report=read(folder/'report.json')
    assert report['passed'] and report['phase']=='default_open_compositional_equivalence_proven'
    assert report['parent_generation_sha256']==sha(old/'generation.json')
    assert report['candidate_generation_sha256']==sha(new/'generation.json')
    for field in ('inputs_sha256','artifacts_sha256'):
        assert all(sha(folder/n)==h for n,h in report[field].items())
    assert sha(folder/'run_rpc_refusal_default_open_formal_wsl.py')==sha(root/'tools/run_rpc_refusal_default_open_formal_wsl.py')
    assert report['initial_reset_required'] and report['later_inputs_and_resets_arbitrary']
    assert not report['input_stability_assumptions'] and not report['production_register_initial_values_forced']
    with tempfile.TemporaryDirectory(prefix='refusal-formal-replay-')as raw:
        replay=Path(raw);records=generate(old/'joint/rtl',new/'joint/rtl',replay)
        assert json.loads(json.dumps(records))==report['lemmas']
        for p in replay.rglob('*'):
            if p.is_file():assert p.read_text()==(folder/p.relative_to(replay)).read_text(),p
    proofs={}
    for label,record in records.items():
        slot=folder/label;miter=(slot/'miter.sv').read_text()
        assert miter.count('assume(')==1 and 'always @*if(!past_valid)assume(rst);'in miter
        assert 'always @*if(past_valid)begin'in miter
        if label!='controller':
            original=(slot/'original.v').read_text();observed=(slot/'observed.v').read_text()
            additions=',\n'+',\n'.join(f'output wire {w} formal_{n}'for w,n in record['signals'])+'\n'
            assignments='\n'.join('assign formal_'+n+'='+n+';'for w,n in record['signals'])+'\n'
            assert observed.count(additions)==observed.count(assignments)==1
            assert observed.replace(additions,'').replace(assignments,'')==original
            uncut=read(slot/'uncut.json');cut,certificate=cut_children(uncut,record['children'])
            assert cut==read(slot/'cut.json') and certificate==read(slot/'cut-certificate.json')
            # No parent cell or connection may be altered by the overapproximation.
            before=uncut['modules']['proof_top'];after=cut['modules']['proof_top']
            assert {k:v for k,v in before.items()if k!='cells'}=={k:v for k,v in after.items()if k!='cells'}
            removed={c['cell_name']for c in certificate}
            assert all(after['cells'][n]==c for n,c in before['cells'].items()if n not in removed)
            assert all(c['type']=='$anyseq'for n,c in after['cells'].items()if n not in before['cells'])
            assert re.findall(r'assert\(([^;]+)\);',miter)==record['claims']
        else:
            outputs=[n for d,w,n in record['interface']if d=='output']
            assert re.findall(r'assert\(([^;]+)\);',miter)==[
                'old_'+n+'==new_'+n for n in outputs]+[
                'old_internal_'+n+'==new_internal_'+n for w,n in record['signals']]+record['claims']
            assert len(record['signals'])==16
        for name,induct in [('reset-base',False),('induction',True)]:
            script=(slot/(name+'.ys')).read_text();assert script==proof_script(label,induct)
            assert not any(flag in script for flag in ('-ignore_unknown_cells','-set-init-zero','-tempinduct-skip','-tempinduct-inductonly'))
            log=(slot/(name+'.log')).read_text()
            assert not re.search(r'^ERROR:',log,re.M)
            assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log
        proofs[label]=dict(reset_base_verified=True,unbounded_induction_verified=True,
            compared_output_ports=sum(d=='output'for d,w,n in record['interface'])if label=='controller'else 0,
            internal_registers_compared=16 if label=='controller'else 0,
            child_outputs_unconstrained=label!='controller')
    def connections(source,module):
        match=re.search(r'\b'+module+r'\s*#\(.*?\)\s+\w+\s*\((.*?)\);',source,re.S)
        assert match,module
        result=re.findall(r'\.(\w+)\(([^()]*)\)',match[1])
        assert len({n for n,v in result})==len(result)
        return {n:v.strip()for n,v in result}
    core=(new/'joint/rtl/http2_enveloped_parser_core.v').read_text()
    app=(new/'joint/rtl/http2_enveloped_parser_application.v').read_text()
    assert connections(app,'http2_enveloped_parser_core')['admit_new_rpcs']=='admit_new_rpcs'
    transport=connections(core,'http2_classified_parser_transport')
    keyed=connections(core,'http2_keyed_receive_credit_store')
    controller=connections(core,'http2_receive_flow_controller')
    assert transport['admit_new_rpcs']=='admit_new_rpcs' and transport['refusal_history']=='refusal_history'
    assert keyed['allow_closed_discard']=='refusal_history' and keyed['rsp_discarded']=='rx_discarded'
    assert controller['result_discarded']=='rx_discarded'
    assert len(re.findall(r'\brefusal_history\b',core))==4
    assert len(re.findall(r'\brx_discarded\b',core))==3
    result=dict(phase='rpc_refusal_default_open_conditional_equivalence_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,parent_generation_sha256=sha(old/'generation.json'),candidate_generation_sha256=sha(new/'generation.json'),
        sole_changed_parser_module='http2_receive_flow_controller',exact_parser_modules=79,exact_tokenizer_modules=31,
        proofs=proofs,actual_composition_wiring_verified=True,all_other_rtl_byte_identical=True,
        default_open_conditional_equivalence_verified=True,initial_reset_required=True,
        later_inputs_and_resets_arbitrary=True,input_stability_assumptions=False,two_state_formal=True,
        condition='admit_new_rpcs stays 1 from initial reset; ENABLE_CAPACITY=1 and ENABLE_STREAM_FORMAT=1',
        new_refusal_fault_behavior_verified=False,native_runtime_verified=False,native_timing_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in folder.rglob('*')if p.is_file()},
        verifier_sha256=sha(Path(__file__)))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/rpc-refusal-default-open-equivalence-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    shutil.copy2(root/'tools/run_rpc_refusal_default_open_formal_wsl.py',evidence/'run_rpc_refusal_default_open_formal_wsl.py')
    for p in (evidence/'audit.json',root/'build/validation/rpc-refusal-default-open-equivalence.json'):
        p.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ('phase','key','default_open_conditional_equivalence_verified')}))


if __name__=='__main__':main()
