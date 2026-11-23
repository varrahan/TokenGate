"""Audit the isolated shared reset, complete image and qualification-loss tests."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from run_hyperram_shared_reset_faults import FAULT_BODY


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    experiment=root/'build/experiments/hyperram-shared-reset'
    assembly=experiment/'build/validation/shared_reset_full_image'
    profiles=experiment/'build/validation/shared_reset_clock_profiles'
    faults=root/'build/experiments/hyperram-shared-reset-faults'
    parent=read(root/'build/validation/hyperram-async-native.json')
    generation=read(experiment/'generation.json')
    syntax=read(assembly/'report.json');elaboration=read(assembly/'elaboration-report.json')
    run=read(assembly/'simulation-full_image-report.json');clocks=read(profiles/'report.json')
    fault=read(faults/'report.json');artifacts=set()
    def pin(path,digest):
        assert sha(path)==digest,path;artifacts.add(path)
    def clean(path):
        text=path.read_text(errors='replace')
        assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),path
        artifacts.add(path);return text
    assert generation['parent_audit_key']==parent['key']=='cdd643b6c5c660c7'
    for name,digest in generation['outputs_sha256'].items():pin(experiment/name,digest)
    assert sha(root/'rtl/cdc_packet_fifo.v')=='ad474cf5bf282d2819eb014370ba211f8e5fb698af245eea17b826386b3c1098'
    assert syntax['exit_code']==elaboration['exit_code']==run['exit_code']==0
    assert syntax['phase']=='syntax_compilation_passed' and elaboration['elaboration_verified']
    assert run['simulation_passed']and run['phase']=='native_full_image_async_memory_passed'
    assert clocks['passed']and clocks['phase']=='native_four_state_clock_profiles_passed'
    assert fault['passed']and fault['phase']=='qualification_loss_passed'
    assert run['input_sha256']==syntax['inputs_sha256']
    changed=[]
    for name,digest in syntax['inputs_sha256'].items():
        pin(assembly/'sources'/name,digest)
        if name.startswith(('rtl/','sim/')):pin(experiment/name,digest)
        if digest!=parent['inputs_sha256'][name]:changed.append(name)
    assert set(changed)=={'rtl/cdc_packet_fifo.v','rtl/hyperram_clock_bridge.v','rtl/axi_hyperram_async_controller.v'}
    for name,digest in clocks['inputs_sha256'].items():
        pin(profiles/'sources'/name,digest)
        if name in syntax['inputs_sha256']:assert syntax['inputs_sha256'][name]==digest
    for report in (run,clocks):assert report['vendor_sva_enabled']is False
    assert syntax['vendor_compatibility_defines']==clocks['compatibility_defines']==['OBSOLETE']
    assert run['independent_testbench_assertions_enabled']and clocks['independent_assertions_enabled']
    assert not run['runtime_options_changed_for_security']
    assert 'xpm_source'in elaboration['commands'][-1]and'xpm'not in elaboration['commands'][-1]
    assert 'work.glbl'in elaboration['commands'][-1]
    pin(assembly/'sources/vendor/glbl.v',elaboration['glbl_sha256'])
    for name,digest in run['snapshot_files_sha256'].items():pin(assembly/name,digest)
    for macro in('cdc','memory','fifo'):
        name='vendor/xpm_'+macro+'.sv';digest=syntax['inputs_sha256'][name]
        pin(Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+macro)/'hdl'/('xpm_'+macro+'.sv'),digest)
    for name,report,copy in(
        ('check_async_hyperram_windows',syntax,assembly/'check_async_hyperram_windows.py'),
        ('elaborate_async_hyperram_windows',elaboration,assembly/'elaborate_async_hyperram_windows.py'),
        ('run_async_hyperram_windows',run,assembly/'run_async_hyperram_windows-full_image.py'),
        ('run_hyperram_cdc_windows',clocks,profiles/'run_hyperram_cdc_windows.py')):
        pin(experiment/'tools'/(name+'.py'),report['driver_sha256']);pin(copy,report['driver_sha256'])
    image_sha=parent['image_sha256'];pin(assembly/'image.bin',image_sha)
    pin(root/'build/scu35/image/external_memory.bin',image_sha)
    assert run['acceptance']==parent['acceptance']
    for name in('simulator-output-full_image.log','xsim-full_image.log'):
        text=clean(assembly/name)
        line=re.findall(r'^ASYNC_HYPERRAM_PASS (.+)$',text,re.M);assert len(line)==1
        assert {k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line[0])}==parent['acceptance']
        for phase in('WRITE','READ'):
            assert [int(n)for n in re.findall(r'^ASYNC_'+phase+r'_PROGRESS bytes=(\d+)',text,re.M)]==list(range(1048576,8388609,1048576))
    for label,values in clocks['profiles'].items():
        assert values['epochs']==4 and values['completed']>=3000
        assert values['source_holds']>=50 and values['response_holds']>=50
        for name in(label+'.log','xsim-'+label+'.log'):
            text=clean(profiles/name);line=re.findall(r'^CDC_TEST_PASS (.+)$',text,re.M);assert len(line)==1
            assert {k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',line[0])}==values
    assert len(clocks['profiles'])==4
    assert sum(case['completed']for case in clocks['profiles'].values())==12115
    fault_folder=faults/'build/validation/qualification_loss'
    fault_syntax=read(fault_folder/'report.json');fault_elaboration=read(fault_folder/'elaboration-report.json')
    assert fault_syntax['exit_code']==fault_elaboration['exit_code']==0
    for name,digest in fault_syntax['inputs_sha256'].items():
        pin(fault_folder/'sources'/name,digest)
        if name!='sim/hyperram_async_test_body.svh':assert syntax['inputs_sha256'][name]==digest
    body=(experiment/'sim/hyperram_async_test_body.svh').read_text()
    assert (fault_folder/'sources/sim/hyperram_async_test_body.svh').read_text()==body[:body.index('    full_phase=1;')]+FAULT_BODY
    pin(root/'tools/run_hyperram_shared_reset_faults.py',fault['generator_and_driver_sha256'])
    for name,digest in fault['artifact_sha256'].items():pin(faults/name,digest)
    assert fault['acceptance']==dict(reset_epochs=3,completed_reads=3,supply_losses=1,phy_losses=1)
    for name in('qualification-output.log','xsim-qualification.log'):
        text=clean(fault_folder/name)
        assert len(re.findall(r'^QUALIFICATION_LOSS_PASS ',text,re.M))==1
        assert 'QUALIFICATION_SUPPLY_RECOVERED reset_epochs=2'in text
    for folder in(assembly,profiles,fault_folder):
        for path in folder.glob('*.log'):clean(path)

    # The transformation is replayed independently against the exact parent
    # archive. Output hashes cover changed RTL, unchanged models and copied tools.
    with tempfile.TemporaryDirectory(prefix='shared-reset-generator-replay-')as temporary:
        replay=Path(temporary)
        def copy(source,relative):
            target=replay/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        copy(root/'build/validation/hyperram-async-native.json','build/validation/hyperram-async-native.json')
        parent_folder=root/'build/validation/hyperram_async_windows_full_image_wide_timeout'
        for name in parent['inputs_sha256']:
            relative='build/validation/hyperram_async_windows_full_image_wide_timeout/sources/'+name
            copy(parent_folder/'sources'/name,relative)
        for name in generation['outputs_sha256']:
            if name.startswith('tools/')or name=='sim/tb_hyperram_clock_bridge.sv':copy(root/name,name)
        copy(root/'tools/generate_hyperram_shared_reset_experiment.py','tools/generate_hyperram_shared_reset_experiment.py')
        copy(root/'build/frozen-hyperram-images'/image_sha/'external_memory.bin','build/frozen-hyperram-images/'+image_sha+'/external_memory.bin')
        subprocess.run([sys.executable,str(replay/'tools/generate_hyperram_shared_reset_experiment.py')],check=True,capture_output=True)
        replay_outputs=read(replay/'build/experiments/hyperram-shared-reset/generation.json')['outputs_sha256']
        assert replay_outputs==generation['outputs_sha256']
    artifacts.update((experiment/'generation.json',assembly/'report.json',assembly/'elaboration-report.json',
        assembly/'simulation-full_image-report.json',profiles/'report.json',faults/'report.json',fault_folder/'report.json',
        fault_folder/'elaboration-report.json',root/'tools/generate_hyperram_shared_reset_experiment.py',Path(__file__)))
    result=dict(phase='shared_reset_async_memory_functionally_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parent_audit_key=parent['key'],inputs_sha256=syntax['inputs_sha256'],acceptance=run['acceptance'],
        clock_profiles=clocks['profiles'],completed_clock_test_responses=12115,qualification_loss_acceptance=fault['acceptance'],
        generator_replay_verified=True,changed_sources=changed,vendor_sources_unmodified=True,vendor_sva_enabled=False,
        independent_assertions_enabled=True,primary_rtl_modified=False,native_timing_verified=False,cdc_signoff_verified=False,
        tokenizer_instantiation_verified=False,pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,full_system_complete=False,
        artifacts_sha256={str(p.relative_to(root))if p.is_relative_to(root)else str(p):sha(p)for p in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    output=root/'build/validation/hyperram-shared-reset.json';output.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/hyperram-shared-reset-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(output,evidence/'verified.json');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    print(json.dumps({key:result[key]for key in('phase','key','acceptance','qualification_loss_acceptance','completed_clock_test_responses')}))


if __name__=='__main__':main()
