"""Run the unchanged full HTTP/2/native-tokenizer corpus with SIMD Parser RTL."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
from verify_two_fpga_application import closure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert args.name.replace('_','').isalnum()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    approved=Path.home()/'development/hardware/parser'
    assert approved.resolve()==Path('/home/varrahan/development/hardware/parser')and approved.is_dir()and root!=approved
    assert shutil.which('iverilog')and shutil.which('vvp')
    import cocotb
    sys.path.insert(0,str(root/'scripts'));from run_raw_envelope_tests import freeze_model_image
    parent_path=root/'build/validation/progress-format-corpus.json';parent=json.loads(parent_path.read_text())
    assert parent['key']=='6dd529d376e06926'and parent['full_native_corpus_verified']
    parent_archive=root/'build/wsl-reports/raw_envelope_progress_format_full_native_corpus'
    original=parent_archive/'execution-sources';original_inputs=json.loads((parent_archive/'inputs.json').read_text())
    assert original_inputs==parent['inputs_sha256']
    target=approved/'build/raw-envelope-tests'/args.name
    archive=root/'build/wsl-reports'/('raw_envelope_'+args.name)
    assert not target.exists()and not archive.exists()
    assert shutil.disk_usage(root).free>=512*1024**2 and shutil.disk_usage(approved).free>=2*1024**3
    target.mkdir(parents=True,exist_ok=False);inputs={}
    for name,digest in original_inputs.items():
        source=original/name;assert sha(source)==digest,name
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        if name=='build/bidirectional-fixtures/memory.mem':freeze_model_image(source,destination,approved)
        else:shutil.copy2(source,destination)
        assert sha(destination)==digest;inputs[name]=digest
    candidate=root/'build/experiments/json-simd';generation=json.loads((candidate/'generation.json').read_text())
    changed=[];added=[]
    for name,digest in generation['outputs_sha256'].items():
        assert sha(candidate/name)==digest
        if name in inputs and inputs[name]==digest:continue
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True)
        (changed if name in inputs else added).append(name)
        shutil.copy2(candidate/name,destination);inputs[name]=sha(destination)
    assert sorted(changed)==['rtl/json_string_normalizer.v','rtl/proto_json_decoder.v','rtl/speculative_json_fsm.v']
    assert sorted(added)==['rtl/axis_compacting_window.v','rtl/json_simd_scanner.v']
    parser_modules=closure('http2_enveloped_parser_application',target)
    tokenizer_modules=closure('tokenizer_fpga_memory_subsystem',target)
    assert len(parser_modules)==76 and len(tokenizer_modules)==22
    assert {name:sha(path)for name,path in tokenizer_modules.items()}==parent['executed_tokenizer_sha256']
    for name in('sim/cocotb_two_fpga_enveloped_top.sv','sim/cocotb/test_raw_grpc_workload.py'):
        assert inputs[name]==original_inputs[name],'The original full-corpus fixture must remain unchanged'
    (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    shutil.copy2(Path(__file__),target/'protocol-runner-used.py')
    shutil.copy2(candidate/'generation.json',target/'simd-generation.json')
    launch_path=root/'build/validation'/(args.name+'-launch.json')
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),name=args.name,
        target=str(target),archive=str(archive),parent_corpus_audit_key=parent['key'],
        changed_rtl=changed,added_rtl=added,exact_parser_modules=76,exact_tokenizer_modules=22,
        tokenizer_sources_unchanged=True,protocol_fixture_sources_unchanged=True,cocotb_version=cocotb.__version__,
        driver_sha256=sha(Path(__file__)),inputs_sha256=inputs,full_system_complete=False)
    def save():launch_path.write_text(json.dumps(report,indent=2)+'\n')
    save();print('Frozen SIMD full native corpus: '+str(target),flush=True)
    try:
        with(target/'driver.log').open('w')as log:
            process=subprocess.Popen([sys.executable,str(target/'scripts/run_raw_envelope_tests.py'),'--execute','--profile','workload'],
                cwd=target,stdout=log,stderr=subprocess.STDOUT)
            report['launcher_pid']=process.pid;save();code=process.wait()
        assert all(sha(target/name)==digest for name,digest in inputs.items())
        archive.mkdir(parents=True,exist_ok=False)
        for name,digest in inputs.items():
            destination=archive/'execution-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
            if name=='build/bidirectional-fixtures/memory.mem':freeze_model_image(target/name,destination,root)
            else:shutil.copy2(target/name,destination)
            assert sha(destination)==digest
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for filename in('report.json','acceptance.json','simulation.log','build.log','results.xml','progress.json','failure.json'):
            source=target/'build/test'/filename
            if source.is_file():shutil.copy2(source,archive/filename)
        for filename in('driver.log','protocol-runner-used.py','simd-generation.json'):shutil.copy2(target/filename,archive/filename)
        snapshot=dict(name=args.name,profile='workload',exit_code=code,finished_utc=datetime.now(timezone.utc).isoformat(),
            parent_corpus_audit_key=parent['key'],changed_rtl=changed,added_rtl=added,exact_parser_modules=76,
            exact_tokenizer_modules=22,protocol_fixture_sources_unchanged=True,tokenizer_sources_unchanged=True)
        (archive/'snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        report.update(phase='completed'if code==0 else'failed',exit_code=code)
        assert code==0,('Full native corpus failed; execution and failure evidence retained',code)
    except BaseException as error:
        report.update(phase='stopped_with_error',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({key:report[key]for key in('phase','name','exit_code','exact_parser_modules','exact_tokenizer_modules')}))


if __name__=='__main__':main()
