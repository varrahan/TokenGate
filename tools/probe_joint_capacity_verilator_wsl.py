"""Probe strict WSL support for the unchanged, full native joint workload."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('--assembly', default='joint-schema-capacity-success-v1')
    ap.add_argument('--dead-branch-probe', action='store_true')
    args = ap.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9_-]+', n) for n in (args.name, args.assembly))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    source = root / 'build/experiments' / args.assembly
    generation = json.loads((source / 'generation.json').read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert generation['parser_modules'] == 79 and generation['tokenizer_modules'] == 31
    assert generation['capacity_composed'] and generation['unchanged_original_workload_images_vectors_and_assertions']
    assert all(sha(source / n) == h for n, h in generation['outputs_sha256'].items())
    approved = Path.home() / 'development/hardware/parser'
    assert approved.is_dir() and approved != root
    target = approved / 'build/joint-capacity-verilator' / args.name
    archive = root / 'build/wsl-reports' / ('joint_capacity_verilator_' + args.name)
    target.mkdir(parents=True, exist_ok=False)
    assert not archive.exists()
    for n, h in generation['outputs_sha256'].items():
        p = target / n
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / n, p)
        assert sha(p) == h
    shutil.copy2(source / 'generation.json', target / 'generation.json')
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    command = ['verilator', '--lint-only', '--timing', '--assert', '-DOBSOLETE', '-Wno-fatal',
               '--top-module', 'joint_hyperram_grpc_tb', '-I.', '--Mdir', 'obj']
    command += [str(p.relative_to(target)) for p in sorted((target / 'joint/rtl').glob('*.v'))]
    command += ['joint/vendor/' + n for n in ('glbl.v', 'xpm_cdc.sv', 'xpm_memory.sv', 'xpm_fifo.sv')]
    command += ['joint_hyperram_grpc_tb.sv']
    if args.dead_branch_probe:
        command[1:2] = ['--xml-only', '--flatten', '--xml-output', 'elaboration.xml', '--bbox-unsup']
    record = dict(phase='strict_lint_running', name=args.name, assembly=args.assembly,
                  started_utc=datetime.now(timezone.utc).isoformat(), command=command,
                  simulator_version=subprocess.run(['verilator', '--version'], check=True,
                                                   capture_output=True, text=True).stdout.strip(),
                  simulator_two_state=True, generation_sha256=sha(source / 'generation.json'),
                  inputs_sha256=generation['outputs_sha256'], driver_sha256=sha(Path(__file__)),
                  parser_modules=79, tokenizer_modules=31, full_images=2, full_requests=32,
                  vendor_sources_unmodified=True, testbench_unmodified=True,
                  vendor_assertions_disabled=False, unsupported_construct_blackboxing=args.dead_branch_probe,
                  dead_branch_probe_only=args.dead_branch_probe,
                  simulation_passed=False, native_xsim_runtime_verified=False, full_system_complete=False)
    launch = root / 'build/validation' / (args.name + '-verilator-probe.json')
    assert not launch.exists()
    def save():
        (target / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
        launch.write_text(json.dumps(record, indent=2) + '\n')
    save()
    print('Frozen strict full-workload Verilator probe: ' + str(target), flush=True)
    try:
        with (target / 'lint.log').open('w') as output:
            result = subprocess.run(command, cwd=target, stdout=output, stderr=subprocess.STDOUT)
        record.update(phase='strict_lint_passed' if result.returncode == 0 else 'strict_lint_unsupported',
                      exit_code=result.returncode, lint_passed=result.returncode == 0,
                      lint_log_sha256=sha(target / 'lint.log'))
        if args.dead_branch_probe:
            record['phase'] = 'dead_branch_elaboration_probe_completed' if result.returncode == 0 else 'dead_branch_elaboration_probe_unsupported'
            record['functional_runtime_qualified'] = False
            if (target / 'elaboration.xml').exists():
                record['elaboration_xml_sha256'] = sha(target / 'elaboration.xml')
        assert all(sha(target / n) == h for n, h in generation['outputs_sha256'].items())
    except BaseException as error:
        record.update(phase='probe_error', error=str(error))
        raise
    finally:
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        archive.mkdir(parents=True, exist_ok=False)
        for n in generation['outputs_sha256']:
            p = archive / 'execution-sources' / n
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / n, p)
        for n in ('report.json', 'lint.log', 'generation.json', 'elaboration.xml', Path(__file__).name):
            if (target / n).exists():
                shutil.copy2(target / n, archive / n)
    print(json.dumps({k: record[k] for k in ('phase', 'exit_code', 'lint_passed')}), flush=True)
    raise SystemExit(record['exit_code'])


if __name__ == '__main__':
    main()
