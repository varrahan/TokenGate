"""Native XSim compilation/elaboration of the complete two-FPGA assembly."""
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
    parser.add_argument('--name', required=True)
    parser.add_argument('--assembly', default='dual-fpga-hyperram-native-order-v4')
    args = parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name) and re.fullmatch(r'[A-Za-z0-9_-]+', args.assembly)
    root = Path(__file__).resolve().parents[1]
    assembly = root / 'build/experiments' / args.assembly
    generation = json.loads((assembly / 'generation.json').read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert shutil.disk_usage(root).free >= 3 * 1024**3, 'Simulation elaboration needs 3 GiB headroom'
    assert all(sha(assembly / name) == digest for name, digest in generation['outputs_sha256'].items())
    generator = root / 'tools/generate_dual_fpga_hyperram_integration.py'
    assert sha(generator) == generation['generator_sha256']
    folder = root / 'build/validation' / args.name
    folder.mkdir(parents=True, exist_ok=False)
    frozen = folder / 'sources'
    for name in generation['outputs_sha256']:
        target = frozen / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assembly / name, target)
    shutil.copy2(assembly / 'generation.json', folder / 'generation.json')
    shutil.copy2(generator, folder / generator.name)
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    project = folder / 'rtl.prj'
    rtl_files = sorted((frozen / 'joint/rtl').glob('*.v')) + [frozen / 'joint/vendor/glbl.v']
    project.write_text(''.join('verilog work "' + path.relative_to(folder).as_posix() + '"\n' for path in rtl_files))
    report = dict(phase='compiling', started_utc=datetime.now(timezone.utc).isoformat(),
        inputs_sha256=generation['outputs_sha256'], generation_sha256=sha(folder / 'generation.json'),
        generator_sha256=sha(generator), driver_sha256=sha(Path(__file__)), commands=[],
        project_file_sha256=sha(project), production_rtl_compiled_as_verilog=True,
        exact_parser_modules=76, exact_tokenizer_modules=31, joint_modules=108,
        vendor_sources_unmodified=True, compatibility_defines=['OBSOLETE'],
        portable_memory_backend=False, global_startup_model_preserved=True,
        namespace_module_types_only=True, simulation_executed=False,
        native_timing_verified=False, full_system_complete=False)
    output = folder / 'report.json'
    def save():
        output.write_text(json.dumps(report, indent=2) + '\n')
    save()
    def run(command, name):
        report['commands'].append(command)
        save()
        with (folder / (name + '.log')).open('w') as stream:
            result = subprocess.run(command, cwd=folder, stdout=stream, stderr=subprocess.STDOUT)
        text = (folder / (name + '.log')).read_text(errors='replace')
        assert result.returncode == 0, (name, result.returncode)
        assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):', text, re.M), (name, 'Native compiler error')
        return text
    tools = Path('C:/AMDDesignTools/2025.2/Vivado/bin')
    try:
        run([str(tools / 'xvlog.bat'), '--sv', '--define', 'OBSOLETE', '--work', 'xpm_source', '--log', 'vendor-compile.log'] +
            [str(frozen / 'joint/vendor' / ('xpm_' + name + '.sv')) for name in ('cdc','memory','fifo')], 'vendor')
        run([str(tools / 'xvlog.bat'), '--log', 'rtl-compile.log', '--prj', str(project)], 'rtl')
        report['phase'] = 'elaborating'
        text = run([str(tools / 'xelab.bat'), '--debug', 'off', '--snapshot', 'dual_fpga_hyperram',
            '-L', 'xpm_source', '-L', 'unisims_ver', '-L', 'unimacro_ver', '--log', 'xelab.log',
            'work.two_fpga_hyperram_application'], 'elaboration')
        assert 'Built simulation snapshot dual_fpga_hyperram' in text
        assert all(sha(frozen / name) == digest for name, digest in report['inputs_sha256'].items())
        report.update(phase='native_joint_elaboration_verified', elaboration_verified=True, passed=True)
    except BaseException as error:
        report.update(phase='native_joint_elaboration_failed', passed=False, error=str(error))
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({key: report[key] for key in ('phase','passed','exact_parser_modules','exact_tokenizer_modules','simulation_executed')}))


if __name__ == '__main__':
    main()
