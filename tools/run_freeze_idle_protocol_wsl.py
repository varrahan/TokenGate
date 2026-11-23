"""Replay unchanged full-model protocol/fault fixtures on the freeze-idle guard."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys

from verify_two_fpga_application import closure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', nargs='+', required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    approved = Path.home() / 'development/hardware/parser'
    assert approved.resolve() == Path('/home/varrahan/development/hardware/parser') and approved.is_dir()
    assert shutil.which('iverilog') and shutil.which('vvp')
    import cocotb
    sys.path.insert(0, str(root / 'scripts'))
    from run_raw_envelope_tests import freeze_model_image
    read = lambda path: json.loads(path.read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    cases = {}
    for audit_name, expected in [('progress-format-regressions', '736eec1fa78adf7d'),
                                 ('progress-format-experiment', 'c7aebf98ee6f7e25')]:
        audit = read(root / 'build/validation' / (audit_name + '.json'))
        assert audit['key'] == expected
        for name, record in audit['executions'].items():
            assert name not in cases
            cases[name] = (expected, record)
    assert len(set(args.cases)) == len(args.cases) and set(args.cases) <= cases.keys()
    generation_path = root / 'build/experiments/freeze-idle/generation.json'
    generation = read(generation_path)
    for name in args.cases:
        baseline_key, baseline = cases[name]
        run = 'freeze_idle_' + name + '_20261122'
        target = approved / 'build/raw-envelope-tests' / run
        archive = root / 'build/wsl-reports' / ('raw_envelope_' + run)
        assert not target.exists() and not archive.exists(), run
        assert shutil.disk_usage(root).free >= 3 * 1024**3
        assert shutil.disk_usage(approved).free >= 3 * 1024**3
        original = root / 'build/wsl-reports' / ('raw_envelope_' + baseline['snapshot'])
        inputs = read(original / 'inputs.json')
        assert inputs == baseline['inputs_sha256']
        target.mkdir(parents=True, exist_ok=False)
        for relative, digest in inputs.items():
            source = original / 'execution-sources' / relative
            assert sha(source) == digest
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative == 'build/bidirectional-fixtures/memory.mem':
                freeze_model_image(source, destination, approved)
            else:
                shutil.copy2(source, destination)
        changed = []
        for relative, digest in generation['outputs_sha256'].items():
            source = generation_path.parent / relative
            assert sha(source) == digest
            assert relative in inputs
            if digest != inputs[relative]:
                shutil.copy2(source, target / relative)
                inputs[relative] = digest
                changed.append(relative)
        assert changed == ['rtl/rpc_grpc_http2_return.v']
        assert len(closure('http2_enveloped_parser_application', target)) == 75
        assert len(closure('tokenizer_fpga_memory_subsystem', target)) == 22
        (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        shutil.copy2(Path(__file__), target / 'protocol-runner-used.py')
        shutil.copy2(generation_path, target / 'freeze-idle-generation.json')
        launch_path = root / 'build/validation' / (run + '-launch.json')
        state = dict(phase='running', name=run, case=name, profile=baseline['profile'],
            target=str(target), archive=str(archive), baseline_audit_key=baseline_key,
            baseline_snapshot=baseline['snapshot'], generation_sha256=sha(generation_path),
            driver_sha256=sha(Path(__file__)), inputs_sha256=inputs,
            changed_rtl=changed, cocotb_version=cocotb.__version__,
            started_utc=datetime.now(timezone.utc).isoformat(), full_system_complete=False)
        def save():
            launch_path.write_text(json.dumps(state, indent=2) + '\n')
        save()
        print('Frozen freeze-idle case: ' + name, flush=True)
        try:
            with (target / 'driver.log').open('w') as log:
                process = subprocess.Popen([sys.executable, str(target / 'scripts/run_raw_envelope_tests.py'),
                    '--execute', '--profile', baseline['profile']], cwd=target, stdout=log, stderr=subprocess.STDOUT)
                state['launcher_pid'] = process.pid
                save()
                code = process.wait()
            assert all(sha(target / relative) == digest for relative, digest in inputs.items())
            archive.mkdir(parents=True, exist_ok=False)
            for relative, digest in inputs.items():
                destination = archive / 'execution-sources' / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if relative == 'build/bidirectional-fixtures/memory.mem':
                    freeze_model_image(target / relative, destination, root)
                else:
                    shutil.copy2(target / relative, destination)
                assert sha(destination) == digest
            for filename in ('report.json', 'acceptance.json', 'simulation.log', 'build.log', 'results.xml',
                             'progress.json', 'failure.json', 'receive_trace.json', 'window_trace.json'):
                if (target / 'build/test' / filename).is_file():
                    shutil.copy2(target / 'build/test' / filename, archive / filename)
            for filename in ('inputs.json', 'protocol-runner-used.py', 'freeze-idle-generation.json', 'driver.log'):
                shutil.copy2(target / filename, archive / filename)
            (archive / 'snapshot.json').write_text(json.dumps(dict(name=run, profile=baseline['profile'],
                exit_code=code, baseline_audit_key=baseline_key, baseline_snapshot=baseline['snapshot'],
                finished_utc=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
            state.update(phase='completed' if code == 0 else 'failed', exit_code=code)
            assert code == 0, (name, code)
        except BaseException as error:
            state.update(phase='stopped_with_error', error=str(error))
            raise
        finally:
            state['finished_utc'] = datetime.now(timezone.utc).isoformat()
            save()
        print(json.dumps(dict(case=name, phase=state['phase'], exit_code=code)), flush=True)


if __name__ == '__main__':
    main()
