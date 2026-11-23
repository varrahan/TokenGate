"""Freeze and run the entire 32-request joint workload on native XSim."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--name',required=True)
    ap.add_argument('--assembly',required=True)
    args=ap.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in (args.name,args.assembly))
    root=Path(__file__).resolve().parents[1]
    source=root/'build/experiments'/args.assembly
    generation=json.loads((source/'generation.json').read_text())
    assert generation['parser_modules'] in (76,77,79) and generation['tokenizer_modules']==31
    if generation['parser_modules']==77:assert generation['schema_mmio']
    if generation['parser_modules']==79:
        assert generation['schema_mmio'] and generation['capacity_composed'] and generation['success_predicate_integrated']
        assert generation['capacity_assembly_audit_key']=='69a29b3c155b339f'
        assert generation['capacity_directed_runtime_audit_key']=='2ad2339cea44fec0'
        assert generation['success_predicate_audit_key']=='a4f36fdbbab5143f'
        assert generation['unchanged_original_workload_images_vectors_and_assertions']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert all(sha(source/n)==h for n,h in generation['outputs_sha256'].items())
    assert shutil.disk_usage(root).free>5*1024**3
    folder=root/'build/validation'/args.name
    folder.mkdir(parents=True,exist_ok=False)
    for n in generation['outputs_sha256']:
        target=folder/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,target)
    shutil.copy2(source/'generation.json',folder/'generation.json')
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    project=folder/'production.prj'
    project.write_text(''.join('verilog work "'+p.relative_to(folder).as_posix()+'"\n'
        for p in sorted((folder/'joint/rtl').glob('*.v'))+[folder/'joint/vendor/glbl.v']))
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(folder/'generation.json'),driver_sha256=sha(Path(__file__)),
        inputs_sha256=generation['outputs_sha256'],commands=[],parser_modules=generation['parser_modules'],tokenizer_modules=31,
        parser_memory_fabric_modules=4,images=2,sequences=32,expected_actual_dma_ids=11091,
        parser_application_memory_clients=19,parser_fabric_clients=20,real_host_route_configuration_client=True,
        production_compiled_as_verilog=True,native_vendor_memory=True,portable_backend=False,
        testbench_assertions_enabled=True,normal_global_startup=True,compatibility_defines=['OBSOLETE'],
        simulation_passed=False,independent_protocol_oracle_verified=False,full_system_complete=False)
    if generation.get('schema_mmio'):
        report.update(schema_mmio=True,expected_schema_durable_applies=generation['expected_schema_durable_applies'],
            expected_host_route_configuration_commands=generation['expected_host_route_configuration_commands'],
            global_schema_maintenance_authority_verified=False)
    if generation.get('owned_quiet'):report.update(owned_quiet=True,frame_event_buffer_integrated=True)
    if generation.get('capacity_composed'):
        report.update(capacity_composed=True,semantic_payload_buffer_integrated=True,success_predicate_integrated=True,
            complete_component_protocol_matrix_verified=False,global_model_rpc_gpu_maintenance_authority_verified=False)
    def save():
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(command,name):
        report['commands'].append(command);save()
        with (folder/(name+'-stdout.log')).open('w') as output:
            result=subprocess.run(command,cwd=folder,stdout=output,stderr=subprocess.STDOUT)
        log=(folder/(name+'-stdout.log')).read_text(errors='replace')
        assert result.returncode==0,(name,result.returncode)
        assert not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):',log,re.M),(name,'Native error; inspect preserved log')
        return log
    native=Path('C:/AMDDesignTools/2025.2/Vivado/bin')
    save()
    try:
        run([str(native/'xvlog.bat'),'--sv','--define','OBSOLETE','--work','xpm_source','--log','vendor.log']+
            ['joint/vendor/xpm_'+n+'.sv' for n in ('cdc','memory','fifo')],'vendor')
        run([str(native/'xvlog.bat'),'--prj','production.prj','--log','production.log'],'production')
        run([str(native/'xvlog.bat'),'--sv','--include','.','--log','testbench.log','joint_hyperram_grpc_tb.sv'],'testbench')
        report['phase']='elaborating';save()
        text=run([str(native/'xelab.bat'),'--debug','off','--snapshot','joint_hyperram_grpc',
            '-L','xpm_source','-L','unisims_ver','-L','unimacro_ver','--log','xelab.log','work.joint_hyperram_grpc_tb'],'elaboration')
        assert 'Built simulation snapshot joint_hyperram_grpc' in text
        report.update(phase='simulating',simulation_started_utc=datetime.now(timezone.utc).isoformat());save()
        text=run([str(native/'xsim.bat'),'joint_hyperram_grpc','--runall','--log','xsim.log'],'simulation')
        assert text.count('JOINT_HYPERRAM_GRPC_FULL_CORPUS_PASS')==1
        actual=(folder/'xsim.log').read_text(errors='replace')
        assert actual.count('JOINT_HYPERRAM_GRPC_FULL_CORPUS_PASS')==1 and not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):',actual,re.M)
        assert len(re.findall(r'^JOINT_CORPUS_CASE ',actual,re.M))==32
        assert all(sha(folder/n)==h for n,h in report['inputs_sha256'].items())
        report.update(phase='native_simulation_completed_protocol_oracle_pending',simulation_passed=True,
            outputs_sha256={n:sha(folder/n) for n in ['wire.log','dma.log','gpu.log','xsim.log']+(['schema.log'] if generation.get('schema_mmio') else [])+
                [side+'-final'+str(epoch)+'.bin' for side in ('parser','tokenizer') for epoch in range(2)]})
    except BaseException as error:
        report.update(phase='native_joint_workload_failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({k:report[k] for k in ('phase','simulation_passed','independent_protocol_oracle_verified')}))


if __name__=='__main__':main()
