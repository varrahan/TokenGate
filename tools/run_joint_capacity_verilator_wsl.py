"""Run the full composed workload with unchanged models and checked dead ECC."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def check_dead_ecc(folder):
    """Every unsupported source construct must lie outside the elaborated design."""
    vendor = folder / 'joint/vendor/xpm_memory.sv'
    lines = vendor.read_text().splitlines()
    start = next(i for i, line in enumerate(lines, 1) if 'if (ECC_MODE != 0) begin : ecc_behav_logic' in line)
    end = next(i for i, line in enumerate(lines, 1) if 'end : ecc_behav_logic' in line)
    unsupported = [i for i, line in enumerate(lines, 1) if re.search(r'\bdeassign\b', line)]
    assert len(unsupported) == 8 and all(start < i < end for i in unsupported)
    xml = ET.parse(folder / 'elaboration.xml')
    files = {e.attrib['id']: e.attrib['filename'] for e in xml.findall('.//file')}
    file_id = next(k for k, v in files.items() if v == 'joint/vendor/xpm_memory.sv')
    reached = []
    for e in xml.iter():
        location = e.attrib.get('loc', '').split(',')
        if len(location) > 1 and location[0] == file_id and start <= int(location[1]) <= end:
            reached.append((e.tag, location))
        assert not any(word in e.tag.lower() for word in ('deassign', 'unsupported', 'blackbox'))
    assert not reached, reached[:5]
    modes = [e for e in xml.findall('.//var') if e.attrib.get('origName') == 'ECC_MODE'
             and 'xpm_memory_base_inst' in e.attrib.get('name', '')]
    assert len(modes) == 8
    assert all(len(e) == 1 and e[0].tag == 'const' and e[0].attrib['name'] == "32'sh0" for e in modes)
    xml_text = (folder / 'elaboration.xml').read_text()
    assert 'ecc_behav_logic' not in xml_text and 'deassign' not in xml_text
    assert 'glbl.GSR_int' in xml_text and 'glblGSR_xpmcdc' in xml_text
    # Testbench assertions are lowered to conditional fatal/stop operations.
    stops = xml.findall('.//stop')
    assert len(stops) >= 300
    return dict(all_eight_instantiated_memories_have_ecc_disabled=True,
                unsupported_deassign_lines=unsupported, dead_ecc_source_interval=[start, end],
                no_elaborated_node_in_unsupported_ecc_branch=True,
                normal_global_startup_retained=True, lowered_fatal_stop_nodes=len(stops),
                vendor_sources_edited=False, vendor_assertions_disabled=False)


def check_dead_ecc_json(folder,source_folder=None):
    """Check the current tool's actual flattened AST, including source positions."""
    lines=((source_folder or folder)/'joint/vendor/xpm_memory.sv').read_text().splitlines()
    start=next(i for i,line in enumerate(lines,1) if 'if (ECC_MODE != 0) begin : ecc_behav_logic' in line)
    end=next(i for i,line in enumerate(lines,1) if 'end : ecc_behav_logic' in line)
    unsupported=[i for i,line in enumerate(lines,1) if re.search(r'\bdeassign\b',line)]
    assert len(unsupported)==8 and all(start<i<end for i in unsupported)
    tree=json.loads((folder/'elaboration.json').read_text())
    metadata=json.loads((folder/'elaboration.meta.json').read_text())
    file_id=next(k for k,v in metadata['files'].items() if v['filename']=='joint/vendor/xpm_memory.sv')
    nodes=[];stack=[tree]
    while stack:
        value=stack.pop()
        if isinstance(value,dict):
            if 'type' in value:nodes.append(value)
            stack.extend(v for v in value.values() if isinstance(v,(dict,list)))
        elif isinstance(value,list):stack.extend(value)
    reached=[]
    for node in nodes:
        loc=node.get('loc','').split(',')
        if len(loc)>1 and loc[0]==file_id and start<=int(loc[1].split(':')[0])<=end:
            reached.append((node['type'],node['loc']))
        assert not any(word in node['type'].lower() for word in ('deassign','unsupported','blackbox'))
    assert not reached,reached[:5]
    modes=[n for n in nodes if n['type']=='VAR' and n.get('origName')=='ECC_MODE'
           and 'xpm_memory_base_inst' in n.get('name','')]
    assert len(modes)==8,[(n.get('name'),n.get('valuep')) for n in modes]
    assert all(len(n.get('valuep',[]))==1 and n['valuep'][0]['type']=='CONST'
               and n['valuep'][0]['name']=="32'sh0" for n in modes)
    names=[n.get('name','') for n in nodes]
    assert any('glbl.GSR_int' in n for n in names)
    assert any('glblGSR_xpmcdc' in n for n in names)
    assert not any('ecc_behav_logic' in n for n in names)
    stops=sum(n['type']=='STOP' for n in nodes);assert stops>=300,stops
    return dict(all_eight_instantiated_memories_have_ecc_disabled=True,
        unsupported_deassign_lines=unsupported,dead_ecc_source_interval=[start,end],
        no_elaborated_node_in_unsupported_ecc_branch=True,normal_global_startup_retained=True,
        lowered_fatal_stop_nodes=stops,vendor_sources_edited=False,vendor_assertions_disabled=False,
        elaboration_format='pinned_5_054_flattened_json',instantiated_memory_parameters=[n['name'] for n in modes])


def main():
    import resource
    ap = argparse.ArgumentParser(); ap.add_argument('--name', required=True)
    ap.add_argument('--candidate',choices=('joint-schema-capacity-success-v1','joint-rpc-refusal-v7-v2','joint-rpc-registered-select-v1','joint-rpc-receive-payload-v1'),default='joint-schema-capacity-success-v1')
    ap.add_argument('--consistent-memory-driver', action='store_true')
    ap.add_argument('--isolated', action='store_true')
    ap.add_argument('--whole-release-fix',action='store_true')
    ap.add_argument('--allow-dead-ecc-syntax', action='store_true'); args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+', args.name)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    source = root / 'build/experiments' / args.candidate
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    generation = read(source / 'generation.json')
    payload=args.candidate=='joint-rpc-receive-payload-v1'
    registered=payload or args.candidate=='joint-rpc-registered-select-v1'
    refusal=registered or args.candidate=='joint-rpc-refusal-v7-v2'
    if refusal:
        if registered:
            from generate_registered_selection_execution_pack import validate_pack
        else:
            from generate_rpc_refusal_execution_pack import validate_pack
        native=validate_pack(root,source)
        assert args.isolated and args.whole_release_fix and not args.allow_dead_ecc_syntax
        assert generation['parser_modules']==79 and generation['tokenizer_modules']==31
    else:
        native = read(root / 'build/validation/joint-capacity-success-native-assembly.json')
        assert native['key'] == 'e346244ae567e5d1' and native['native_elaboration_verified']
        assert generation['parser_modules'] == native['parser_modules'] == 79
        assert generation['tokenizer_modules'] == native['tokenizer_modules'] == 31
    assert generation['unchanged_original_workload_images_vectors_and_assertions']
    assert sha(source / 'generation.json') == native['generation_sha256']
    assert all(sha(source / n) == h for n, h in generation['outputs_sha256'].items())
    approved = Path.home() / 'development/hardware/parser'; assert approved.is_dir()
    env=os.environ.copy();simulator='verilator';tool_build=None;tool_patch=None;binary_sha=None
    if args.whole_release_fix:assert args.isolated
    if args.isolated:
        tool_build=read(root/'build/validation/verilator-v5.054-build/report.json')
        assert tool_build['phase']=='built_version_checked_selftests_pending'
        assert tool_build['commit']=='bbb60a403932a9f695cb6ff001ceb73de6ad9234'
        tool=approved/'build/tools/verilator-v5.054'
        assert sha(tool/'bin/verilator_bin')==tool_build['executable_sha256']
        binary_sha=tool_build['executable_sha256'];label='verilator-v5.054'
        if args.whole_release_fix:
            tool_patch=read(root/'build/validation/verilator-v5.054-whole-release-v1/report.json')
            assert tool_patch['phase']=='focused_regression_passed_upstream_suite_pending' and tool_patch['actual_semantic_checks']==33
            assert tool_patch['base_simulator_binary_sha256']==binary_sha
            tool=Path(tool_patch['target']);binary_sha=tool_patch['simulator_binary_sha256'];label+='-whole-release-v1'
            assert sha(tool/'bin/verilator_bin')==binary_sha
            assert subprocess.run(['git','diff','--name-only'],cwd=tool,check=True,capture_output=True,text=True).stdout.splitlines()==['src/V3Force.cpp']
            edit=tool_patch['source_edit'];text=(tool/edit['path']).read_text()
            assert sha(tool/edit['path'])==edit['after_sha256']
            assert hashlib.sha256(text.replace(edit['anchor']+edit['addition'],edit['anchor']).encode()).hexdigest()==edit['before_sha256']
        tests=read(root/'build/validation'/(label+'-upstream-selected.json'))
        assert tests['phase']=='passed' and tests['simulator_binary_sha256']==binary_sha
        env['VERILATOR_ROOT']=str(tool);simulator=str(tool/'bin/verilator')
    target = approved / 'build/joint-capacity-verilator' / args.name
    archive = root / 'build/wsl-reports' / ('joint_capacity_verilator_' + args.name)
    assert not archive.exists(); target.mkdir(parents=True, exist_ok=False)
    for n, h in generation['outputs_sha256'].items():
        p = target / n; p.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source / n, p)
        assert sha(p) == h
    inputs=dict(generation['outputs_sha256']);driver_edit=None
    if args.consistent_memory_driver:
        name='joint_parser_axi_memory.svh';path=target/name;original=path.read_bytes().decode()
        replacements=[('if(parser_b_accepted)p_axi_bvalid=0;', 'if(parser_b_accepted)p_axi_bvalid<=0;'),
                      ('p_axi_rlast=pr_index+1==pr_beats;p_axi_rvalid=1;', 'p_axi_rlast=pr_index+1==pr_beats;p_axi_rvalid<=1;')]
        updated=original
        for before,after in replacements:
            assert updated.count(before)==1;updated=updated.replace(before,after)
        inverse=updated
        for before,after in reversed(replacements):
            assert inverse.count(after)==1;inverse=inverse.replace(after,before)
        assert inverse==original
        path.write_bytes(updated.encode());inputs[name]=sha(path)
        driver_edit=dict(path=name,old_sha256=generation['outputs_sha256'][name],new_sha256=inputs[name],
            replacements=replacements,exact_inverse_verified=True,
            assertions_and_memory_transactions_unchanged=True,
            scheduling_change='Falling-edge valid updates use NBA; AW may stall one additional cycle after a B handshake')
    shutil.copy2(source / 'generation.json', target / 'generation.json')
    if refusal:
        shutil.copy2(source/'source-assembly.json',target/'source-assembly.json')
        checker='generate_registered_selection_execution_pack.py'if registered else'generate_rpc_refusal_execution_pack.py'
        shutil.copy2(root/'tools'/checker,target/'execution-pack-checker-used.py')
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    common = [simulator, '--timing', '--assert', '-DOBSOLETE', '-Wno-fatal',
              '--top-module', 'joint_hyperram_grpc_tb', '-I.', '--Mdir', 'obj']
    blackbox=args.allow_dead_ecc_syntax or not args.isolated
    if blackbox:common.append('--bbox-unsup')
    sources = [str(p.relative_to(target)) for p in sorted((target / 'joint/rtl').glob('*.v'))]
    sources += ['joint/vendor/' + n for n in ('glbl.v', 'xpm_cdc.sv', 'xpm_memory.sv', 'xpm_fifo.sv')]
    sources += ['joint_hyperram_grpc_tb.sv']
    record = dict(phase='elaborating', name=args.name, started_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(source / 'generation.json'), inputs_sha256=inputs,
        original_generation_inputs_sha256=generation['outputs_sha256'],testbench_memory_driver_edit=driver_edit,
        driver_sha256=sha(Path(__file__)), native_assembly_audit_key=native['key'],
        source_candidate=args.candidate,source_assembly_kind='strict_two_state_elaboration'if refusal else'native_xsim_elaboration',
        refusal_execution_pack=refusal,registered_selection_execution_pack=registered,payload_pipeline_execution_pack=payload,
        simulator_version=subprocess.run([simulator, '--version'],env=env,check=True,capture_output=True,text=True).stdout.strip(),
        isolated_simulator_build=tool_build,isolated_simulator_patch=tool_patch,simulator_binary_sha256=binary_sha,
        simulator_two_state=True, parser_modules=79, tokenizer_modules=31, full_images=2, full_requests=32,
        source_and_testbench_unmodified=driver_edit is None, vendor_sources_unmodified=True,
        all_production_rtl_unmodified=True, all_original_assertions_and_traffic_preserved=True,
        testbench_assertions_enabled=True, vendor_assertions_disabled=False,
        unsupported_parser_flag_used_only_with_dead_branch_gate=blackbox,
        simulation_passed=False, independent_protocol_oracle_verified=False,
        native_xsim_runtime_verified=False, native_timing_verified=False, full_system_complete=False, commands=[])
    launch = root / 'build/validation' / (args.name + '-verilator-run.json'); assert not launch.exists()
    def save():
        (target / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
        launch.write_text(json.dumps(record, indent=2) + '\n')
    def run(command, name):
        record['commands'].append(command); save()
        with (target / (name + '.log')).open('w') as output:
            process = subprocess.Popen(command, cwd=target,env=env,stdout=output, stderr=subprocess.STDOUT)
            record['process_pid'] = process.pid; save(); code = process.wait()
        assert code == 0, (name, code)
    save(); print('Frozen full 79/31-module two-image, 32-call WSL workload: ' + str(target), flush=True)
    try:
        if args.isolated:
            run(common+['--json-only','--flatten','--json-only-output','elaboration.json',
                        '--json-only-meta-output','elaboration.meta.json']+sources,'elaboration')
            record['dead_ecc_gate']=check_dead_ecc_json(target)
        else:
            run(common + ['--xml-only', '--flatten', '--xml-output', 'elaboration.xml'] + sources, 'elaboration')
            record['dead_ecc_gate'] = check_dead_ecc(target)
        record['elaboration_artifacts_sha256']={n:sha(target/n) for n in
            (['elaboration.json','elaboration.meta.json','elaboration.log'] if args.isolated else ['elaboration.xml','elaboration.log'])}
        record['phase'] = 'building'; save()
        print('Verified all eight memories use no ECC; unsupported branch absent; global startup and assertions retained', flush=True)
        run(common + ['--binary', '-j', '2', '--output-split', '10000', '--output-split-cfuncs', '200'] + sources, 'build')
        binary = target / 'obj/Vjoint_hyperram_grpc_tb'; record['binary_sha256'] = sha(binary)
        record['build_log_sha256']=sha(target/'build.log')
        record['phase'] = 'simulating'; save()
        print('Running full unchanged joint workload', flush=True)
        run([str(binary)], 'simulation')
        log = (target / 'simulation.log').read_text(errors='replace')
        assert log.count('JOINT_HYPERRAM_GRPC_FULL_CORPUS_PASS') == 1
        assert len(re.findall(r'^JOINT_CORPUS_CASE ', log, re.M)) == 32
        assert not re.search(r'^\s*(?:%Error|Fatal|Error|FATAL|ERROR):', log, re.M)
        record.update(phase='full_workload_completed_independent_oracle_pending', simulation_passed=True)
        names = ['wire.log', 'dma.log', 'gpu.log', 'schema.log', 'simulation.log']
        names += [side + '-final' + str(epoch) + '.bin' for side in ('parser', 'tokenizer') for epoch in range(2)]
        record['outputs_sha256'] = {n: sha(target / n) for n in names}
    except BaseException as error:
        record.update(phase='full_workload_failed', error=str(error)); raise
    finally:
        assert all(sha(target / n) == h for n, h in inputs.items())
        record['finished_utc'] = datetime.now(timezone.utc).isoformat(); save()
        archive.mkdir(parents=True, exist_ok=False)
        for n in generation['outputs_sha256']:
            p = archive / 'execution-sources' / n; p.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target / n, p)
        for p in target.iterdir():
            if p.is_file() and (p.suffix in ('.log', '.json', '.xml', '.bin') or p.name == Path(__file__).name):
                shutil.copy2(p, archive / p.name)
    print(json.dumps({k: record[k] for k in ('phase', 'simulation_passed')}), flush=True)


if __name__ == '__main__':
    main()
