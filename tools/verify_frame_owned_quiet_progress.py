"""Audit no-early-idle, bounded quiet progress and a reachable quiet witness."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil


PROGRESS_LINES='''reg previous_quiet=0;
always @(posedge clk)if(rst)previous_quiet<=0;else previous_quiet<=reference_idle&&quiet_inputs;
assign settled_quiet_cover=past_valid&&!rst&&previous_quiet&&reference_idle&&quiet_inputs&&candidate_idle;
always @*if(past_valid&&!rst&&previous_quiet&&reference_idle&&quiet_inputs)assert(candidate_idle);
'''
COVER_COMMAND='sat -set-assumes -seq 4 -set-init-def -set-def-inputs -set-at 1 rst 1 -set-at 2 rst 0 -set-at 3 rst 0 -set-at 4 rst 0 -set-at 4 settled_quiet_cover 1 -show-ports -dump_vcd quiet_cover.vcd\n'


def witness(path):
    text=path.read_text()
    identifiers={name:re.search(r'\$var wire 1 (\S+) \\'+name+r' \$end',text)[1] for name in ('settled_quiet_cover','rst')}
    state={};samples={};time=None
    for line in text.splitlines():
        if line.startswith('#'):
            if time is not None:samples[time]=dict(state)
            time=int(line[1:])
        elif line and line[0] in ('0','1','x','z'):
            for name,identifier in identifiers.items():
                if line[1:]==identifier:state[name]=line[0]
    if time is not None:samples[time]=dict(state)
    assert samples[0]['rst']=='1'
    assert all(samples[t]['rst']=='0' for t in (2,3,4))
    assert samples[4]['settled_quiet_cover']=='1'
    return dict(initial_reset=True,reset_free_cover_steps=[2,3,4],quiet_cover_true_at_step=4)


def main():
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent=read(root/'build/validation/frame-owned-quiet-formal.json');assert parent['key']=='c56de709b9b5681a'
    native=read(root/'build/validation/http2-schema-owned-quiet-assembly.json');assert native['key']=='b602ab4f082fd7fe'
    assert native['canonical_owned_quiet_induction_verified']
    executions={};artifacts={Path(__file__)}
    for role,original_name,name in (
        ('implementation_candidate','frame_owned_quiet_formal_v1_20261122','frame_owned_quiet_progress_formal_20261122'),
        ('native_composed_candidate','joint_schema_owned_quiet_formal_20261122','joint_schema_owned_quiet_progress_formal_20261122')):
        original=root/'build/wsl-reports'/original_name;folder=root/'build/wsl-reports'/name
        before=read(original/'report.json');report=read(folder/'report.json')
        assert before['passed'] and report['passed']
        assert report['phase']=='frame_owned_quiet_safety_and_bounded_progress_induction_verified'
        assert report['generation_sha256']==before['generation_sha256']
        assert report['original_top_sha256']==before['original_top_sha256']
        if role=='implementation_candidate':assert report['generation_sha256']==parent['generation_sha256']
        else:assert report['generation_sha256']==native['generation_sha256']
        assert report['driver_sha256']==sha(folder/'run_frame_owned_quiet_formal_wsl.py')
        for n,h in report['inputs_sha256'].items():assert sha(folder/n)==h,n
        assert len(list((folder/'rtl').glob('*.v')))==7
        for p in (folder/'rtl').glob('*.v'):assert p.read_bytes()==(original/'rtl'/p.name).read_bytes()
        old_miter=(original/'miter.sv').read_text();end=old_miter.index(');')
        expected=old_miter[:end].rstrip('\n')+',\noutput wire settled_quiet_cover\n'+old_miter[end:]
        expected=expected.replace('endmodule',PROGRESS_LINES+'endmodule')
        assert (folder/'miter.sv').read_text()==expected
        assert expected.count('assume(')==1 and expected.count('assert(')==3
        script=(folder/'proof.ys').read_text()
        assert script==(original/'proof.ys').read_text()+COVER_COMMAND
        # Cover reset restrictions affect only the SAT witness command. The
        # preceding induction still permits every later reset/input trace.
        assert '-tempinduct -tempinduct-def -set-init-def -set-def-inputs' in script.splitlines()[-2]
        log=(folder/'proof.log').read_text()
        assert 'Base case for induction length 1 proven.' in log and 'Induction step proven: SUCCESS!' in log
        assert 'SAT solving finished - model found:' in log
        assert not re.search(r'^ERROR:',log,re.M)
        assert sha(folder/'proof.log')==report['proof_log_sha256']
        assert sha(folder/'netlist.json')==report['netlist_sha256']
        assert sha(folder/'quiet_cover.vcd')==report['quiet_cover_sha256']
        reached=witness(folder/'quiet_cover.vcd')
        assert report['bounded_quiet_progress_verified'] and report['nonvacuity_quiet_cover_reached']
        assert report['maximum_extra_idle_cycles_after_stable_quiet']==1
        executions[role]=dict(snapshot=name,original_snapshot=original_name,generation_sha256=report['generation_sha256'],
            original_top_sha256=report['original_top_sha256'],complete_owner_modules=7,
            safety_and_progress_induction_verified=True,reachable_quiet_witness=reached,
            report_sha256=sha(folder/'report.json'),proof_log_sha256=report['proof_log_sha256'],quiet_cover_sha256=report['quiet_cover_sha256'])
        artifacts.update(p for p in folder.rglob('*') if p.is_file())
    result=dict(phase='frame_owned_quiet_safety_progress_and_nonvacuity_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_owner_audit_key=parent['key'],native_assembly_audit_key=native['key'],executions=executions,
        no_early_idle_verified=True,maximum_extra_idle_cycles_after_stable_quiet=1,
        bounded_progress_requires_previous_and_current_reference_idle_and_no_offers=True,
        initial_reset_required=True,arbitrary_later_resets_in_induction=True,input_stability_assumptions=False,
        complete_production_owner_subtree=True,memory_model_substitution=False,two_state_formal=True,
        nonvacuous_quiet_witness_verified=True,full_application_liveness_verified=False,
        full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p) for p in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/frame-owned-quiet-progress-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation/frame-owned-quiet-progress.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','maximum_extra_idle_cycles_after_stable_quiet','nonvacuous_quiet_witness_verified')}))


if __name__=='__main__':main()
