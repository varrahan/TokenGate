"""Create separate device projects from the native-elaborated source assembly."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--elaboration', default='dual_fpga_hyperram_order_v4_20261122')
    parser.add_argument('--name', default='dual_fpga_source_projects_20261122')
    parser.add_argument('--bundle', help='New self-contained folder directly under the workspace')
    args = parser.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9_]+', value) for value in (args.elaboration,args.name))
    root = Path(__file__).resolve().parents[1]
    native = root / 'build/validation' / args.elaboration
    read = lambda path: json.loads(path.read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = read(native / 'report.json')
    assert report['passed'] and report['phase'] == 'native_joint_elaboration_verified'
    sources = native / 'sources'
    for name, digest in report['inputs_sha256'].items():
        assert sha(sources / name) == digest
    assert shutil.disk_usage(root).free >= 3 * 1024**3
    folder = root / 'build/validation' / args.name
    folder.mkdir(parents=True, exist_ok=False)
    source_bundle = sources
    bundle_inputs = {}
    if args.bundle:
        assert re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',args.bundle)
        source_bundle = root / args.bundle
        assert not source_bundle.exists() and source_bundle.resolve().is_relative_to(root.resolve())
        source_bundle.mkdir()
        for label in ('parser','tokenizer'):
            for path in sorted((sources / label / 'rtl').glob('*.v')) + [sources / label / 'clocks.xdc']:
                relative = path.relative_to(sources)
                target = source_bundle / relative; target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,target); assert sha(target) == sha(path)
                bundle_inputs[relative.as_posix()] = sha(target)
    projects = source_bundle / 'projects' if args.bundle else folder / 'projects'
    original = (sources / 'create_projects.tcl').read_text()
    first = 'set bundle [file dirname [file normalize [info script]]]'
    target = 'set project_dir [file join $bundle projects $name]'
    clocks = 'add_files -fileset constrs_1 -norecurse [file join $bundle $label clocks.xdc]'
    quoted_clocks = 'add_files -fileset constrs_1 -norecurse [list [file join $bundle $label clocks.xdc]]'
    assert original.count(first) == original.count(target) == 1
    assert original.count(clocks) + original.count(quoted_clocks) == 1
    assert all(char not in str(path) for path in (source_bundle,projects) for char in '{}')
    script = original.replace(first,'set bundle {' + source_bundle.as_posix() + '}\nset project_output_root {' + projects.as_posix() + '}\nset_param general.maxThreads 1')
    script = script.replace(target,'set project_dir [file join $project_output_root $name]')
    script = script.replace(clocks,quoted_clocks)
    tcl = folder / 'create_projects.tcl'
    tcl.write_text(script)
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    command = ['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace',
               '-source',str(tcl),'-log',str(folder / 'vivado.log'),'-journal',str(folder / 'vivado.jou')]
    state = dict(phase='creating', started_utc=datetime.now(timezone.utc).isoformat(),
        elaboration=args.elaboration, elaboration_report_sha256=sha(native / 'report.json'),
        generated_tcl_sha256=sha(tcl), original_tcl_sha256=sha(sources / 'create_projects.tcl'),
        command=command, driver_sha256=sha(Path(__file__)), native_implementation_executed=False,
        source_bundle=str(source_bundle), bundle_inputs_sha256=bundle_inputs,
        board_part_assigned=False, package_pins_assigned=False, full_system_complete=False)
    output = folder / 'report.json'
    def save():
        output.write_text(json.dumps(state, indent=2) + '\n')
    save()
    try:
        with (folder / 'stdout.log').open('w') as stream:
            result = subprocess.run(command,cwd=folder,stdout=stream,stderr=subprocess.STDOUT)
        state['exit_code'] = result.returncode
        text = (folder / 'stdout.log').read_text(errors='replace')
        assert result.returncode == 0 and 'ERROR:' not in text
        expected = [('Parser_AU15P','xcau15p-ffvb676-2-e','http2_enveloped_parser_application'),
                    ('Tokenizer_SCU35','xcsu35p-sbvb625-2-e','tokenizer_hyperram_subsystem')]
        for name,part,top in expected:
            assert 'DUAL_FPGA_SOURCE_PROJECT_CREATED NAME=' + name + ' PART=' + part + ' TOP=' + top + ' IMPLEMENTATION_NOT_RUN=1' in text
        state['projects'] = {name: dict(part=part,top=top,path=str(projects / name / (name + '.xpr')),
            project_sha256=sha(projects / name / (name + '.xpr'))) for name,part,top in expected}
        state.update(phase='separate_fpga_source_projects_created',passed=True)
        if args.bundle:
            (source_bundle / 'source-manifest.json').write_text(json.dumps(state,indent=2)+'\n')
    except BaseException as error:
        state.update(phase='source_project_creation_failed',passed=False,error=str(error))
        raise
    finally:
        state['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps(dict(phase=state['phase'],projects=state['projects'])))


if __name__ == '__main__':
    main()
