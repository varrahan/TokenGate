"""Audit native linkage, declaration-only changes and the actual device projects."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def lexical(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', ' ', text, flags=re.S)


def tokens(text):
    return re.sub(r'\s+', '', lexical(text))


def verify_order(original, ordered, certificate):
    assert hashlib.sha256(original.encode()).hexdigest() == certificate['original_sha256']
    assert hashlib.sha256(ordered.encode()).hexdigest() == certificate['reordered_sha256']
    insertion = certificate['insertion_offset']; injected = certificate['injected_text']
    assert ordered[insertion:insertion + len(injected)] == injected
    assert original[:insertion] == ordered[:insertion]
    remaining = ordered[:insertion] + ordered[insertion + len(injected):]
    masked = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"',lambda m:' ' * len(m[0]),original,flags=re.S)
    events = iter(re.finditer(r'\b(begin|end|function|endfunction|task|endtask|generate|endgenerate|fork|join|join_any|join_none)\b',masked[insertion:]))
    event = next(events,None); depth = 0
    result = ''; cursor = offset = 0
    for block in certificate['blocks']:
        while event is not None and event.start() + insertion < block['start']:
            depth += 1 if event[0] in ('begin','function','task','generate','fork') else -1
            assert depth >= 0
            event = next(events,None)
        assert depth == 0,'Only module-scope declarations may move'
        assert cursor <= block['start'] < block['end']
        assert original[block['start']:block['end']] == block['text']
        assert block['kind'] in ('reg','wire','localparam')
        assert re.match(r'\b' + block['kind'] + r'\b',block['text'])
        assert not re.search(r'\b(?:always|initial|begin|end|function|task)\b',lexical(block['text']))
        if block['kind'] != 'wire':
            assert block['declaration'] == block['text'] and not block['continuation']
            if block['kind'] == 'reg': assert '=' not in block['text']
        else:
            stripped = block['text']
            for driver in block['continuous_net_drivers']:
                pattern = r'\b' + re.escape(driver['name']) + r'\s*=' + re.escape(driver['rhs'])
                stripped, count = re.subn(pattern,lambda match: driver['name'],stripped)
                assert count == 1, driver['name']
            assert tokens(stripped) == tokens(block['declaration'])
            expected = ''.join('assign ' + d['name'] + '=' + d['rhs'] + ';\n' for d in block['continuous_net_drivers'])
            assert block['continuation'] == expected
        length = block['start'] - cursor
        result += remaining[offset:offset + length] + block['text']
        replacement = block['continuation']
        assert remaining[offset + length:offset + length + len(replacement)] == replacement
        offset += length + len(replacement); cursor = block['end']
    result += remaining[offset:]
    assert result == original


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--projects',default='dual_fpga_workspace_projects_20261122')
    args = parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.projects)
    root = Path(__file__).resolve().parents[1]
    read = lambda path: json.loads(path.read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    native = root / 'build/validation/dual_fpga_hyperram_order_v4_20261122'
    projects = root / 'build/validation' / args.projects
    sources = native / 'sources'; report = read(native / 'report.json')
    generation = read(native / 'generation.json'); created = read(projects / 'report.json')
    assert report['passed'] and report['phase'] == 'native_joint_elaboration_verified'
    assert report['simulation_executed'] is False and report['portable_memory_backend'] is False
    assert sha(native / 'generation.json') == report['generation_sha256']
    assert report['inputs_sha256'] == generation['outputs_sha256']
    artifacts = {native / 'report.json',native / 'generation.json',Path(__file__),projects / 'report.json'}
    for name,digest in report['inputs_sha256'].items():
        path = sources / name; assert sha(path) == digest; artifacts.add(path)
    for name,digest in generation['inputs_sha256'].items(): assert sha(root / name) == digest
    used_generator = native / 'generate_dual_fpga_hyperram_integration.py'
    assert sha(used_generator) == generation['generator_sha256'] == report['generator_sha256']
    artifacts.add(used_generator)
    driver = native / 'run_dual_fpga_hyperram_elaboration.py'
    assert sha(driver) == report['driver_sha256']; artifacts.add(driver)
    assert sha(native / 'rtl.prj') == report['project_file_sha256']; artifacts.add(native / 'rtl.prj')
    records = re.findall(r'^verilog work "([^"]+)"$',(native / 'rtl.prj').read_text(),re.M)
    expected = sorted((sources / 'joint/rtl').glob('*.v')) + [sources / 'joint/vendor/glbl.v']
    assert [native / name for name in records] == expected
    for name in ('vendor.log','rtl.log','elaboration.log','vendor-compile.log','rtl-compile.log','xelab.log'):
        path = native / name; text = path.read_text(errors='replace')
        assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M); artifacts.add(path)
    assert 'Built simulation snapshot dual_fpga_hyperram' in (native / 'elaboration.log').read_text()
    for macro in ('cdc','memory','fifo'):
        vendor = sources / 'joint/vendor' / ('xpm_' + macro + '.sv')
        installed = Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm') / ('xpm_' + macro) / 'hdl' / vendor.name
        assert sha(vendor) == sha(installed)
    assert sha(sources / 'joint/vendor/glbl.v') == sha(Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v'))
    assert 'glbl glbl();' in (sources / 'joint/rtl/two_fpga_hyperram_application.v').read_text()
    original_parser = root / 'build/experiments/json-simd/rtl'
    assert len(generation['parser_declaration_order_fixes']) == 11
    for path in (sources / 'parser/rtl').glob('*.v'):
        original = (original_parser / path.name).read_bytes().decode()
        actual = path.read_bytes().decode()
        if path.name in generation['parser_declaration_order_fixes']:
            verify_order(original,actual,generation['parser_declaration_order_fixes'][path.name])
        else: assert original == actual
        assert path.read_bytes() == (sources / 'joint/rtl' / path.name).read_bytes()
    tokenizer_audit = read(root / 'build/validation/tokenizer-hyperram.json')
    assert tokenizer_audit['key'] == generation['tokenizer_functional_audit_key'] == 'cac956b2d9ecf6f9'
    pclosure = closure('http2_enveloped_parser_application',sources / 'parser')
    tclosure = closure('tokenizer_hyperram_subsystem',sources / 'tokenizer')
    joint = closure('two_fpga_hyperram_application',sources / 'joint')
    assert (len(pclosure),len(tclosure),len(joint)) == (76,31,108)
    prefix = 'tokenizer_chiplet__'
    pattern = r'\b(?:' + '|'.join(map(re.escape,tclosure)) + r')\b'
    for path in set(tclosure.values()):
        assert sha(path) == tokenizer_audit['inputs_sha256']['rtl/' + path.name]
        renamed = (sources / 'joint/rtl' / ('tokenizer_' + path.name)).read_bytes().decode()
        assert not re.search(pattern,lexical(renamed))
        assert re.sub(r'\b' + prefix + r'(\w+)\b',lambda m:m[1],renamed) == path.read_bytes().decode()
    pp = {n:(d,w) for d,w,n in ports((sources / 'parser/rtl/http2_enveloped_parser_application.v').read_text(),'http2_enveloped_parser_application') if n.startswith('link_')}
    tp = {n:(d,w) for d,w,n in ports((sources / 'tokenizer/rtl/tokenizer_hyperram_subsystem.v').read_text(),'tokenizer_hyperram_subsystem') if n.startswith('link_')}
    assert pp.keys() == tp.keys() and len(pp) == 91
    for name,(direction,width) in pp.items():
        assert direction != tp[name][0] and tokens(width.replace('MEMORY_ADDR_WIDTH','23')) == tokens(tp[name][1])
    # Reproduce the source assembly with the generator that actually produced it.
    helpers = [root / 'tools' / name for name in ('generate_hyperram_cdc_timing_harness.py',
        'generate_two_fpga_application.py','generate_bidirectional_application.py','verify_two_fpga_application.py')]
    artifacts.update(helpers)
    with tempfile.TemporaryDirectory(prefix='df-',dir=root / 'build') as temporary:
        replay = Path(temporary); assert replay.resolve().is_relative_to((root / 'build').resolve())
        files = list(generation['inputs_sha256']) + ['build/experiments/json-simd/generation.json',
            'build/validation/json-simd-decoder.json','build/validation/tokenizer-hyperram.json',
            'build/validation/parser_native_declaration_scan_20261122/report.json']
        for name in files:
            path = replay / name; path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(root / name,path)
        for helper in helpers:
            path = replay / helper.relative_to(root); path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(helper,path)
        target = replay / 'tools/generate_dual_fpga_hyperram_integration.py'; shutil.copy2(used_generator,target)
        result = subprocess.run([sys.executable,str(target)],capture_output=True,text=True)
        assert result.returncode == 0,(result.stdout,result.stderr)
        rebuilt = read(replay / 'build/experiments/dual-fpga-hyperram-native-order-v4/generation.json')
        assert rebuilt == generation
    assert created['passed'] and created['phase'] == 'separate_fpga_source_projects_created'
    assert created['elaboration_report_sha256'] == sha(native / 'report.json')
    project_sources = Path(created.get('source_bundle',str(sources)))
    assert project_sources.resolve().is_relative_to(root.resolve())
    for name,digest in created.get('bundle_inputs_sha256',{}).items():
        path = project_sources / name
        assert sha(path) == digest == sha(sources / name)
        artifacts.add(path)
    if created.get('bundle_inputs_sha256'):
        assert len(created['bundle_inputs_sha256']) == 108
        manifest = project_sources / 'source-manifest.json'; artifacts.add(manifest)
        assert read(manifest)['bundle_inputs_sha256'] == created['bundle_inputs_sha256']
    project_records = {}
    for label,project_name,part,top,count in [('parser','Parser_AU15P','xcau15p-ffvb676-2-e','http2_enveloped_parser_application',76),
                                           ('tokenizer','Tokenizer_SCU35','xcsu35p-sbvb625-2-e','tokenizer_hyperram_subsystem',30)]:
        record = created['projects'][project_name]; xpr = Path(record['path'])
        assert sha(xpr) == record['project_sha256']; artifacts.add(xpr)
        tree = ET.parse(xpr)
        options = {n.attrib['Name']:n.attrib.get('Val') for n in tree.findall('.//Option') if n.attrib['Name'] in ('Part','BoardPart','TopModule')}
        assert options == dict(Part=part,BoardPart='',TopModule=top)
        source_set = tree.find('.//FileSet[@Name="sources_1"]')
        files = [Path(n.attrib['Path'].replace('$PPRDIR',xpr.parent.as_posix())).resolve() for n in source_set.findall('File')]
        assert len(files) == count and set(files) == {p.resolve() for p in (project_sources / label / 'rtl').glob('*.v')}
        constraints = tree.find('.//FileSet[@Name="constrs_1"]').findall('File'); assert len(constraints) == 1
        assert Path(constraints[0].attrib['Path'].replace('$PPRDIR',xpr.parent.as_posix())).resolve() == (project_sources / label / 'clocks.xdc').resolve()
        project_records[project_name] = dict(part=part,top=top,rtl_files=count,path=str(xpr))
    for path in (projects / 'create_projects.tcl',projects / 'stdout.log',projects / 'vivado.log',projects / 'create_dual_fpga_source_projects.py'):
        artifacts.add(path)
    warnings = [line for line in (native / 'elaboration.log').read_text().splitlines() if line.startswith('WARNING:')]
    assert len(warnings) == 9 and all('[VRFC 10-3091]' in line for line in warnings)
    result = dict(phase='dual_fpga_hyperram_sources_native_elaboration_and_projects_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(), native_run=native.name,
        exact_parser_modules=76, exact_tokenizer_modules=31, joint_modules=108,link_signals=91,
        parser_declaration_only_modules=sorted(generation['parser_declaration_order_fixes']),
        parser_initializers_preserved_as_same_continuous_assignments=True,
        tokenizer_canonical_sources_byte_identical=True,tokenizer_namespace_round_trip_verified=True,
        no_unprefixed_tokenizer_modules_in_joint_source=True,generator_replay_verified=True,
        native_vendor_sources_unmodified=True,global_startup_model_preserved=True,
        production_rtl_compiled_as_verilog=True,projects=project_records,project_job=args.projects,
        self_contained_source_bundle=bool(created.get('bundle_inputs_sha256')),elaboration_warnings=warnings,
        joint_traffic_simulation_verified=False,joint_async_fifo_runtime_verified=False,
        global_image_grant_authority_implemented=False,full_parser_native_timing_verified=False,
        physical_interfaces_verified=False,full_system_complete=False,
        artifacts_sha256={p.relative_to(root).as_posix():sha(p) for p in sorted(artifacts)})
    result['key'] = hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence = root / 'build/validation/dual-fpga-hyperram-evidence' / result['key']; evidence.mkdir(parents=True)
    for path in [Path(__file__),*helpers]:
        destination = evidence / path.relative_to(root); destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,destination)
    output = root / 'build/validation/dual-fpga-hyperram.json'; output.write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(output,evidence / 'verified.json')
    print(json.dumps({key:result[key] for key in ('phase','key','exact_parser_modules','exact_tokenizer_modules','joint_traffic_simulation_verified')}))


if __name__ == '__main__':
    main()
