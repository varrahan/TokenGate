"""Audit full-image reload through the real Tokenizer/cache/word-engine path."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from verify_two_fpga_application import closure

from rtl_paths import source_path, source_relative


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--native-run');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    folder=root/'build/validation'/args.run;report=read(folder/'report.json')
    assert report['phase']=='actual_tokenizer_hyperram_two_complete_images_passed'and report['passed']
    reference=read(folder/'reference.json');generation=read(folder/'generation.json')
    # Use this run's frozen fixture audit. The root JSON is only a latest-run
    # pointer and may already describe a different hardware revision.
    fixture_path=folder/'fixture-audit/verified.json';fixture=read(fixture_path)
    assert fixture['simulation']==args.run and fixture['forward_sequences']==32 and fixture['token_ids']==11091
    for name,digest in fixture['artifacts_sha256'].items():assert sha(source_path(root, name))==digest,name
    assert sha(folder/'reference.json')==report['reference_sha256']
    assert sha(folder/'generation.json')==report['generation_sha256']
    artifacts={folder/'report.json',folder/'reference.json',folder/'generation.json',Path(__file__),fixture_path}
    for name,digest in report['inputs_sha256'].items():
        assert sha(folder/'sources'/name)==digest,name;artifacts.add(folder/'sources'/name)
    rank_unit=None
    if 'PREPARE_ADDRESS=4,CHECK_ADDRESS=5' in (folder/'sources/rtl/bpe_rank_lookup.v').read_text():
        unit_folder=root/'build/validation/rank_lookup_pipeline_native_host'
        unit_path=unit_folder/'report.json';rank_unit=read(unit_path)
        assert rank_unit['phase']=='native_rank_lookup_pipeline_passed'and rank_unit['passed']
        assert rank_unit['inputs_sha256']['rtl/bpe_rank_lookup.v']==report['inputs_sha256']['rtl/bpe_rank_lookup.v']
        assert rank_unit['acceptance']==dict(completed_queries=11,reset_aborts=3,total_reads=262157,full_probe_reads=262144)
        for name,digest in rank_unit['inputs_sha256'].items():
            path=unit_folder/'sources'/name;assert sha(path)==digest;artifacts.add(path)
        unit_driver=unit_folder/'run_rank_lookup_windows.py';assert sha(unit_driver)==rank_unit['driver_sha256']
        artifacts.update((unit_path,unit_driver))
        for path in unit_folder.glob('*.log'):
            text=path.read_text(errors='replace');assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),path
            artifacts.add(path)
        for name in('simulation.log','xsim-rank.log'):
            text=(unit_folder/name).read_text()
            assert len(re.findall(r'^RANK_CASE_PASS ',text,re.M))==11
            assert 'RANK_PIPELINE_PASS completed_queries=11 reset_aborts=3 total_reads=262157 full_probe_reads=262144'in text
    capacity_proof=None
    if 'workspace_record_capacity' in (folder/'sources/rtl/bpe_pretokenizer.v').read_text():
        import z3
        proof_folder=root/'build/validation/pretokenizer-record-capacity-evidence/2488903b68e02864'
        proof_path=proof_folder/'verified.json';capacity_proof=read(proof_path)
        assert capacity_proof['new_module_sha256']==report['inputs_sha256']['rtl/bpe_pretokenizer.v']
        assert capacity_proof['memory_address_width']==23 and capacity_proof['range_checks_preserved']
        assert not capacity_proof['cycle_latency_changed']and not capacity_proof['state_and_handshake_updates_changed']
        assert capacity_proof['queries']==dict(reset_establishes_invariant='unsat',
            capture_and_hold_preserve_invariant='unsat',both_guards_equivalent='unsat')
        for name,digest in capacity_proof['artifacts_sha256'].items():
            path=source_path(root, name)
            if not path.is_file()or sha(path)!=digest:path=proof_folder/name
            assert sha(path)==digest,name
        for name,digest in capacity_proof['query_sha256'].items():
            path=proof_folder/(name+'.smt2');smt_text=path.read_text()
            # The proof producer hashes its UTF-8 SMT-LIB text before Windows
            # write_text expands LF to CRLF. Bind that normalized text here;
            # artifacts_sha256 below independently binds the exact disk bytes.
            assert hashlib.sha256(smt_text.encode()).hexdigest()==digest
            solver=z3.SolverFor('QF_BV');solver.set(timeout=60000);solver.from_string(smt_text)
            assert solver.check()==z3.unsat;artifacts.add(path)
        artifacts.add(proof_path)
    for name,digest in generation['outputs_sha256'].items():assert report['inputs_sha256'][name]==digest,name
    driver=folder/'run_tokenizer_hyperram_windows.py';assert sha(driver)==report['driver_sha256'];artifacts.add(driver)
    assert report['compatibility_defines']==['OBSOLETE']and not report['portable_memory_backend']and not report['vendor_sva_enabled']
    assert report['independent_assertions_enabled']and report['vendor_sources_unmodified']
    for macro in('cdc','memory','fifo'):
        name='vendor/xpm_'+macro+'.sv'
        source=Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+macro)/'hdl'/('xpm_'+macro+'.sv')
        assert sha(source)==report['inputs_sha256'][name]
    for command in report['commands']:
        assert 'PARSER_PORTABLE_SIM'not in str(command)and'--nosignalhandlers'not in str(command)
    elaboration=next(command for command in report['commands']if isinstance(command,list)and command[0].endswith('xelab.bat'))
    assert 'xpm_source'in elaboration and'xpm'not in elaboration and'work.glbl'in elaboration
    dependencies=closure('tokenizer_hyperram_subsystem',folder/'sources')
    assert len(dependencies)==31 and len(set(dependencies.values()))==30
    assert {'tokenizer_fpga_application','bpe_tokenizer_engine','detokenizer_engine','external_memory_fabric',
        'external_memory_cache','programmable_table_ram','hyperram_transaction_engine','hyperram_shared_domain_reset'}<=dependencies.keys()
    assert not {'http2_frame_reader','utf8_serialized_chunk','proto_json_serializer'}&dependencies.keys()
    serializer=closure('utf8_serialized_chunk',folder/'sources')
    assert 'proto_json_serializer'in serializer
    for name in('utf8_serialized_chunk','proto_json_serializer'):
        assert sha(serializer[name])==sha(source_path(root, Path('rtl') / (name+'.v')))
    testbench=(folder/'sources/sim/tb_tokenizer_hyperram.sv').read_text()
    assert 'tokenizer_hyperram_subsystem dut(.*);'in testbench and 'utf8_serialized_chunk #('in testbench
    assert 'test_serializer('in testbench
    body=(folder/'sources/sim/tokenizer_hyperram_test_body.svh').read_text()
    model=(folder/'sources/sim/hyperram_device_and_host.svh').read_text()
    expected_model=(root/'build/experiments/hyperram-shared-reset/sim/hyperram_async_test_body.svh').read_text().split('initial begin : test')[0]
    expected_model=expected_model.replace('dut.clock_bridge.','dut.memory.clock_bridge.').replace('dut.reset_request','dut.memory.reset_request')
    assert model==expected_model
    assert body.count('addr<8388608;addr+=64')==2
    assert 'epoch<2;epoch++'in body and 'i<8388608;i++)assert(device_memory[i]==image[i])'in body
    for text in('Revoked image grant activated model','Maintenance bypassed held BPE completion',
        'Local idle granted global image mutation','Maintenance/new-sequence priority',
        'Actual BPE token mismatch','Actual JSON/SSE/Protobuf byte mismatch',
        'Actual Tokenizer reset/cache/image fencing','Tokenizer replayed invalid image'):
        assert text in body
    assert '$fread(device_memory'not in body+model and not re.search(r'\bforce\s',body+model)
    source=(folder/'sources/rtl/tokenizer_hyperram_subsystem.v').read_text()
    assert 'ACTIVE:if(maintenance_request)state<=DRAIN;'in source
    assert 'DRAIN:if(!maintenance_request)state<=ACTIVE;else if(maintenance_fire)state<=BOOT;'in source
    assert 'assign image_active=base_active;'in source and 'external_image_grant&&local_quiescent&&controller_idle'in source
    if generation.get('registered_local_idle_samples'):
        assert 'idle_sample<={app_memory_idle,app_bpe_idle,app_pack_idle,app_inverse_idle};'in source
        assert 'drain_qualified<=state==DRAIN&&maintenance_request&&!cfg_invalidate_valid;'in source
        assert 'state==DRAIN&&drain_qualified&&external_image_grant'in source
    assert 'image_active=base_active&&!maintenance_fire'not in source
    for path in folder.glob('*.log'):
        text=path.read_text(errors='replace');assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),path;artifacts.add(path)
    runtime=(folder/'simulation.log').read_text()
    xsim=(folder/'xsim-integration.log').read_text()
    expected_cases=[(epoch,index,len(case['token_ids']),len(case['chunks']))for epoch,cases in enumerate(reference['cases'])for index,case in enumerate(cases)]
    accepted=report['acceptance']
    for text in(runtime,xsim):
        for phase in('WRITE','READ'):
            progress=[(int(epoch),int(count))for epoch,count in re.findall(r'^TOKENIZER_IMAGE_'+phase+r' epoch=(\d+) bytes=(\d+)',text,re.M)]
            assert progress==[(epoch,count)for epoch in range(2)for count in range(1048576,8388609,1048576)]
        actual_cases=[tuple(map(int,row))for row in re.findall(r'^TOKENIZER_CORPUS_CASE epoch=(\d+) case=(\d+) tokens=(\d+) inverse_chunks=(\d+)',text,re.M)]
        assert actual_cases==expected_cases
        lines=re.findall(r'^TOKENIZER_HYPERRAM_PASS (.+)$',text,re.M);assert len(lines)==1
        assert {key:int(value)for key,value in re.findall(r'(\w+)=(\d+)',lines[0])}==accepted
    for key,value in dict(image_epochs=2,image_bytes_each=8388608,full_writes=262144,full_reads=262144,
        sequences=32,inverse_chunks=11091,reset_epochs=2,grant_rejections=1,maintenance_switches=1).items():assert accepted[key]==value
    assert accepted['app_reads']>1000 and accepted['app_writes']>1000 and accepted['dma_holds']>100 and accepted['tx_holds']>100

    # Replay the actual integration generator using only frozen application and
    # audited controller inputs, rather than relying on a matching output name.
    parent_path=root/'build/validation/hyperram-shared-reset.json';parent=read(parent_path)
    assert generation['controller_functional_audit_key']==parent['key']=='07002b9a4dd73fb7'
    generator=folder/'integration-generator-used.py'
    if not generator.exists():generator=root/'tools/generate_tokenizer_hyperram_experiment.py'
    assert sha(generator)==generation['generator_sha256'];artifacts.add(generator)
    with tempfile.TemporaryDirectory(prefix='tg-',dir=root/'build')as temporary:
        replay=Path(temporary)
        assert replay.resolve().is_relative_to((root/'build').resolve())
        def copy(source,relative):
            target=replay/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        for name in('generate_tokenizer_hyperram_experiment','generate_hyperram_cdc_timing_harness',
                     'verify_two_fpga_application','generate_two_fpga_application','generate_bidirectional_application'):
            copy(generator if name=='generate_tokenizer_hyperram_experiment'else root/'tools'/(name+'.py'),'tools/'+name+'.py')
        for name,digest in generation['inputs_sha256'].items():
            assert report['inputs_sha256'][name]==digest;copy(folder/'sources'/name,name)
        copy(parent_path,'build/validation/hyperram-shared-reset.json')
        parent_sources=root/'build/experiments/hyperram-shared-reset/build/validation/shared_reset_full_image/sources'
        for name,digest in parent['inputs_sha256'].items():
            assert sha(parent_sources/name)==digest
            copy(parent_sources/name,'build/experiments/hyperram-shared-reset/build/validation/shared_reset_full_image/sources/'+name)
        subprocess.run([sys.executable,str(replay/'tools/generate_tokenizer_hyperram_experiment.py')],check=True,capture_output=True)
        reproduced=read(replay/'build/experiments/tokenizer-hyperram/generation.json')
        assert reproduced['outputs_sha256']==generation['outputs_sha256']
    native=None;cdc_review=None
    if args.native_run:
        path=root/'build/validation/tokenizer-hyperram-native.json';native=read(path)
        if native['run']!=args.native_run:
            candidates=[read(p)for p in(root/'build/validation/tokenizer-hyperram-native-evidence').glob('*/verified.json')]
            candidates=[candidate for candidate in candidates if candidate['run']==args.native_run]
            assert candidates,'No matching immutable native audit'
            native=max(candidates,key=lambda candidate:candidate['verified_utc'])
        assert native['run']==args.native_run
        for name,record in native['source_provenance']['files'].items():
            if name.startswith('rtl/'):assert report['inputs_sha256'][name]==record['sha256']
        for name,digest in native['artifacts_sha256'].items():
            current=source_path(root, name)
            if not current.is_file()or sha(current)!=digest:
                current=root/'build/validation/tokenizer-hyperram-native-evidence'/native['key']/name
            assert sha(current)==digest,name
        archived_native=root/'build/validation/tokenizer-hyperram-native-evidence'/native['key']/'verified.json'
        artifacts.add(archived_native)
        for path in(root/'build/validation/tokenizer-hyperram-cdc-evidence').glob('*/verified.json'):
            review=read(path)
            if review['native_audit_key']!=native['key']:continue
            assert review['all_remaining_warnings_classified']and review['critical_cdc_findings']==0
            for name,digest in review['artifacts_sha256'].items():
                current=source_path(root, name)
                if not current.is_file()or sha(current)!=digest:current=path.parent/name
                assert sha(current)==digest,name
            cdc_review=review;artifacts.add(path)
    for path in(folder/'xsim.dir/tokenizer_hyperram').iterdir():
        if path.is_file():artifacts.add(path)
    fix_path=root/'build/validation/bpe-native-declaration-order.json';fix=read(fix_path)
    assert fix['logic_expression_unchanged']and fix['normalized_only_change_is_assignment_placement']
    assert fix['new_sha256']==report['inputs_sha256']['rtl/bpe_tokenizer_engine.v'];artifacts.add(fix_path)
    result=dict(phase='actual_tokenizer_hyperram_two_complete_model_epochs_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        simulation=args.run,acceptance=accepted,fixture_audit_key=fixture['key'],image_sha256=reference['image_sha256'],
        exact_core_modules=list(dependencies),exact_core_rtl_files=30,inputs_sha256=report['inputs_sha256'],generator_replay_verified=True,
        actual_tokenizer_cache_and_word_engine_connected=True,actual_parser_application_serializer_in_fixture=True,
        native_reference_sequences=32,native_reference_tokens=11091,complete_images_programmed_and_read_back=2,
        pipelined_rank_full_probe_boundary_and_reset_unit_verified=bool(rank_unit),
        pretokenizer_record_capacity_source_guard_proof_key=capacity_proof['key']if capacity_proof else None,
        forward_dma_and_inverse_serialized_bytes_verified=True,maintenance_new_admission_priority_verified=True,
        held_completion_prevents_maintenance_ack_verified=True,revoked_activation_grant_rejected=True,
        actual_application_reset_and_cache_image_invalidation_verified=True,exclusive_loader_axi_verified=True,
        native_audit_key=native['key']if native else None,native_timing_verified=bool(native and native['timing_met']),
        native_cdc_warning_review_key=cdc_review['key']if cdc_review else None,
        native_resource_fit_verified=bool(native and native['resource_fit']),external_whole_rpc_image_grant_implementation_verified=False,
        atomic_global_model_epoch_commit_verified=False,full_http2_transport_in_this_test_verified=False,
        pin_level_ddr_phy_verified=False,rwds_cdc_verified=False,physical_link_verified=False,pcie_verified=False,
        sustained_throughput_verified=False,full_system_complete=False,
        artifacts_sha256={source_relative(p, root).as_posix():sha(p)for p in sorted(artifacts)})
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/tokenizer-hyperram.json';target.write_text(json.dumps(result,indent=2)+'\n')
    evidence=root/'build/validation/tokenizer-hyperram-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=True)
    for name,digest in result['artifacts_sha256'].items():
        if name.startswith('tools/')or(name.startswith('build/validation/')and name.count('/')==2):
            archived=evidence/name;archived.parent.mkdir(parents=True,exist_ok=True)
            if archived.exists():assert sha(archived)==digest
            else:archived.write_bytes((source_path(root, name)).read_bytes())
    shutil.copy2(target,evidence/'verified.json');shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    print(json.dumps({key:result[key]for key in('phase','key','acceptance','native_audit_key','native_timing_verified')}))


if __name__=='__main__':main()
