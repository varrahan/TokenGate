"""Replay every qualified V4 protocol/extended fixture and full corpus on V6."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_two_fpga_application import closure


def main():
    driver_bytes=Path(__file__).read_bytes()
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    sys.path.insert(0,str(root/'scripts'))
    from run_raw_envelope_tests import freeze_model_image
    protocol=read(root/'build/validation/receive-capacity-v4-protocol.json')
    extended=read(root/'build/validation/receive-capacity-v4-extended.json')
    corpus=read(root/'build/validation/receive-capacity-v4-corpus.json')
    assert protocol['key']=='b1c48d1b7a873357' and len(protocol['executions'])==7
    assert extended['key']=='1ed454ad98c4122f' and len(extended['executions'])==5
    assert corpus['key']=='5c25325d35ca3718' and corpus['full_native_corpus_verified']
    cases={k:(v['run'],protocol['key']) for k,v in protocol['executions'].items()}
    cases.update({k:(v['snapshot'],extended['key']) for k,v in extended['executions'].items()})
    cases['corpus']=('receive_capacity_v4_corpus_owner_20261122',corpus['key'])
    ap=argparse.ArgumentParser();ap.add_argument('--cases',nargs='+',choices=tuple(cases),default=list(cases))
    ap.add_argument('--candidate',choices=('rpc-stream-refusal-v6','rpc-registered-frame-select-v1'),default='rpc-stream-refusal-v6')
    ap.add_argument('--prefix',default='rpc_refusal_v6');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.prefix) and len(set(args.cases))==len(args.cases)
    candidate=root/'build/experiments'/args.candidate;registered=args.candidate=='rpc-registered-frame-select-v1'
    generation=read(candidate/'generation.json')
    if registered:
        from verify_registered_frame_select import require_unit_audit
        from registered_selection_assertions import input_promise_assertions
        audit=require_unit_audit(root)
        gpu_audit=read(root/'build/validation/rpc-registered-select-gpu.json')
        assert gpu_audit['generation_sha256']==sha(candidate/'generation.json')and len(gpu_audit['executions'])==2
        expected_parser=generation['non_mmio_parser_sha256']
    else:
        audit=read(root/'build/validation/rpc-stream-refusal.json')
        assert audit['key']=='5112d79cf95b87c8' and audit['four_directed_application_runs_verified']
        assert sha(candidate/'generation.json')==audit['generation_sha256']
        expected_parser=audit['executed_parser_sha256']
    parser_sources=closure('http2_enveloped_parser_application',candidate/'joint')
    assert len(parser_sources)==78
    assert {n:sha(p) for n,p in parser_sources.items()}==expected_parser
    approved=Path.home()/'development/hardware/parser';assert approved.is_dir()
    assert min(shutil.disk_usage(root).free,shutil.disk_usage(approved).free)>2*1024**3
    for case in args.cases:
        base_run,base_key=cases[case]
        parent=root/'build/wsl-reports'/('raw_envelope_'+base_run)
        base_inputs=read(parent/'inputs.json');base_report=read(parent/'report.json')
        assert base_report['phase']=='passed' and base_report['input_sha256']==base_inputs
        profile=base_report['profile']
        run=args.prefix+'_'+case+'_20261122'
        target=approved/'build/raw-envelope-tests'/run
        archive=root/'build/wsl-reports'/('raw_envelope_'+run)
        launch=root/'build/validation'/(run+'-launch.json')
        assert not target.exists() and not archive.exists() and not launch.exists()
        target.mkdir(parents=True,exist_ok=False);inputs=dict(base_inputs)
        for name,digest in base_inputs.items():
            source=parent/'execution-sources'/name;assert sha(source)==digest,name
            p=target/name;p.parent.mkdir(parents=True,exist_ok=True)
            if name=='build/bidirectional-fixtures/memory.mem':freeze_model_image(source,p,approved)
            else:shutil.copy2(source,p)
        for module,source in parser_sources.items():
            name='rtl/'+source.name;p=target/name;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,p);inputs[name]=sha(p)
        top='sim/cocotb_two_fpga_enveloped_top.sv';p=target/top;original=p.read_bytes().decode()
        edits=[('reg  admit_messages=0;','reg  admit_messages=0;\nreg  admit_new_rpcs=1;'),
            ('.admit_messages(admit_messages),','.admit_messages(admit_messages),\n    .admit_new_rpcs(admit_new_rpcs),')]
        if registered:
            assert 'localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;'in original
            edits.append(('endmodule',input_promise_assertions()+'\nendmodule'))
        if '\r\n' in original:edits=[(a.replace('\n','\r\n'),b.replace('\n','\r\n')) for a,b in edits]
        updated=original
        for before,after in edits:
            assert updated.count(before)==1;updated=updated.replace(before,after)
        inverse=updated
        for before,after in reversed(edits):
            assert inverse.count(after)==1;inverse=inverse.replace(after,before)
        assert inverse==original
        p.write_bytes(updated.encode());inputs[top]=sha(p)
        assert {n:sha(p) for n,p in closure('http2_enveloped_parser_application',target).items()}==expected_parser
        tokenizer={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',target).items()}
        assert len(tokenizer)==22 and tokenizer=={n:sha(p) for n,p in closure('tokenizer_fpga_memory_subsystem',parent/'execution-sources').items()}
        for name,h in base_inputs.items():
            if not name.startswith('rtl/') and name!=top:assert inputs[name]==h,name
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        (target/'regression-runner-used.py').write_bytes(driver_bytes)
        shutil.copy2(candidate/'generation.json',target/'refusal-generation.json')
        state=dict(phase='running',name=run,case=case,profile=profile,baseline_run=base_run,baseline_audit_key=base_key,
            target=str(target),archive=str(archive),started_utc=datetime.now(timezone.utc).isoformat(),
            inputs_sha256=inputs,parent_inputs_sha256=base_inputs,generation_sha256=sha(candidate/'generation.json'),
            driver_sha256=hashlib.sha256(driver_bytes).hexdigest(),directed_runtime_audit_key=None if registered else audit['key'],
            parser_sha256=expected_parser,tokenizer_sha256=tokenizer,
            fixture_input_edit=dict(path=top,before_sha256=base_inputs[top],after_sha256=inputs[top],replacements=edits),
            all_original_protocol_test_sources_images_packages_and_assertions_unchanged=True,
            new_rpc_fence_default_open=True,portable_memory_backend=True,
            independent_runtime_audited=False,native_vendor_runtime_verified=False,full_system_complete=False)
        if registered:
            state.update(candidate=args.candidate,registered_selection_unit_audit_key=audit['key'],
                registered_selection_gpu_audit_key=gpu_audit['key'],actual_input_promise_assertions=8,
                passive_assertion_generator_sha256=sha(root/'tools/registered_selection_assertions.py'))
            shutil.copy2(root/'tools/registered_selection_assertions.py',target/'registered_selection_assertions.py')
        def save():launch.write_text(json.dumps(state,indent=2)+'\n')
        save();print('Frozen original V4 regression on refusal RTL: '+case,flush=True)
        try:
            with (target/'driver.log').open('w') as log:
                process=subprocess.Popen([sys.executable,str(target/'scripts/run_raw_envelope_tests.py'),
                    '--execute','--profile',profile],cwd=target,stdout=log,stderr=subprocess.STDOUT)
                state['process_pid']=process.pid;save();code=process.wait()
            state.update(phase='completed' if code==0 else 'failed',exit_code=code)
            assert code==0,(case,'Original regression failed; evidence preserved',code)
        except BaseException as error:
            state.update(phase='failed',error=str(error));raise
        finally:
            assert all(sha(target/n)==h for n,h in inputs.items())
            state['finished_utc']=datetime.now(timezone.utc).isoformat();save()
            archive.mkdir(parents=True,exist_ok=False)
            for name in inputs:
                p=archive/'execution-sources'/name;p.parent.mkdir(parents=True,exist_ok=True)
                if name=='build/bidirectional-fixtures/memory.mem':freeze_model_image(target/name,p,root)
                else:shutil.copy2(target/name,p)
            for name in ('inputs.json','refusal-generation.json','regression-runner-used.py','driver.log'):
                shutil.copy2(target/name,archive/name)
            if registered:shutil.copy2(target/'registered_selection_assertions.py',archive/'registered_selection_assertions.py')
            for p in (target/'build/test').glob('*'):
                if p.is_file() and p.suffix in ('.json','.log','.xml','.bin'):shutil.copy2(p,archive/p.name)
            shutil.copy2(launch,archive/'launch.json')
        print(json.dumps(dict(case=case,phase=state['phase'],exit_code=state['exit_code'])),flush=True)


if __name__=='__main__':main()
