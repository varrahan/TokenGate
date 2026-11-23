"""Freeze the actual reclaimer and full original 8 MiB image for component tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name')
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    approved = Path('/home/varrahan/development/hardware/parser')
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9_]+', args.name)
        sys.path.insert(0, str(root / 'scripts'))
        from run_raw_envelope_tests import freeze_model_image
        original = root / 'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
        target = approved / 'build/payload-reclaimer-units' / args.name
        output = root / 'build/wsl-reports' / args.name
        assert not target.exists() and not output.exists()
        target.mkdir(parents=True)
        inputs = {}
        for name in ('rtl/grpc_payload_reclaimer.v', 'rtl/memory_command_slot.v',
                     'sim/cocotb/test_payload_reclaimer.py', 'tools/run_payload_reclaimer_units_wsl.py'):
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, destination)
            inputs[name] = sha(destination)
        for leaf in ('memory.mem', 'layout.txt', 'fixture_manifest.json'):
            name = 'build/bidirectional-fixtures/' + leaf
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if leaf == 'memory.mem':
                freeze_model_image(original / name, destination, approved)
            else:
                shutil.copy2(original / name, destination)
            inputs[name] = sha(destination)
        (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        with (target / 'driver.log').open('w') as out:
            result = subprocess.run([sys.executable, str(target / 'tools/run_payload_reclaimer_units_wsl.py'),
                '--execute'], cwd=target, stdout=out, stderr=subprocess.STDOUT)
        assert all(sha(target / n) == h for n, h in inputs.items())
        output.mkdir(parents=True, exist_ok=False)
        for name in inputs:
            destination = output / 'execution-sources' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith('/memory.mem'):
                freeze_model_image(target / name, destination, root)
            else:
                shutil.copy2(target / name, destination)
        shutil.copy2(target / 'inputs.json', output / 'inputs.json')
        shutil.copy2(target / 'driver.log', output / 'driver.log')
        for name in ('report.json', 'acceptance.json', 'results.xml', 'simulation.log', 'build.log'):
            if (target / 'build/test' / name).exists():
                shutil.copy2(target / 'build/test' / name, output / name)
        (output / 'snapshot.json').write_text(json.dumps(dict(name=args.name, exit_code=result.returncode,
            finished_utc=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
        print(json.dumps(dict(name=args.name, exit_code=result.returncode)), flush=True)
        raise SystemExit(result.returncode)
    assert root.parent == approved / 'build/payload-reclaimer-units'
    inputs = json.loads((root / 'inputs.json').read_text())
    assert all(sha(root / n) == h for n, h in inputs.items())
    from cocotb_tools.runner import get_runner
    sys.path.insert(0, str(root / 'sim/cocotb'))
    build = root / 'build/test'
    build.mkdir(parents=True)
    report = dict(phase='building', inputs_sha256=inputs, passed=False,
        started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner = get_runner('icarus')
        runner.build(sources=[root / 'rtl/grpc_payload_reclaimer.v', root / 'rtl/memory_command_slot.v'],
            hdl_toplevel='grpc_payload_reclaimer', build_dir=build, always=True, log_file=build / 'build.log')
        runner.test(hdl_toplevel='grpc_payload_reclaimer', test_module='test_payload_reclaimer',
            test_dir=build, build_dir=build, results_xml=build / 'results.xml', seed=20261122,
            extra_env={'RECLAIM_FIXTURES': str(root / 'build/bidirectional-fixtures')}, log_file=build / 'simulation.log')
        xml = ET.parse(build / 'results.xml')
        assert len(xml.findall('.//testcase')) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        assert json.loads((build / 'acceptance.json').read_text())['phase'] == 'passed'
        assert all(sha(root / n) == h for n, h in inputs.items())
        report.update(phase='passed', passed=True, acceptance_sha256=sha(build / 'acceptance.json'))
    except BaseException as error:
        report.update(phase='failed', error=str(error))
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (build / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
