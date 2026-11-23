"""Freeze and run the response-framing component in the approved WSL project."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


SOURCES = ('rtl/grpc_http2_response_framer.v', 'rtl/axis_byte_unpacker.v', 'rtl/axis_byte_packer.v',
           'sim/cocotb/test_grpc_response_frames.py', 'tools/generate_grpc_response_frame_vectors.py',
           'scripts/run_grpc_response_frames.py', 'build/grpc-response-frame-fixtures/cases.json', 'tools/rtl_paths.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name')
    parser.add_argument('--execute', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--simulator', choices=('icarus', 'verilator'), default='icarus')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name)
        approved = Path.home() / 'development/hardware/parser'
        assert approved.is_dir() and root != approved
        target = approved / 'build/grpc-response-frame-tests' / args.name
        target.mkdir(parents=True, exist_ok=False)
        inputs = {}
        for name in SOURCES:
            source, destination = source_path(root, name), target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            inputs[name] = sha(destination)
        fixture = json.loads((target / SOURCES[-1]).read_text())
        assert fixture['phase'] == 'native_references_passed'
        assert fixture['generator_sha256'] == inputs['tools/generate_grpc_response_frame_vectors.py']
        (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        print('Frozen response-frame test: ' + str(target), flush=True)
        completed = subprocess.run([sys.executable, str(target / 'scripts/run_grpc_response_frames.py'),
                                    '--execute', '--simulator', args.simulator], check=False)
        assert all(sha(target / name) == digest for name, digest in inputs.items()), 'Frozen execution input changed'
        archive = root / 'build/wsl-reports' / ('grpc_response_frames_' + args.name)
        archive.mkdir(parents=True, exist_ok=False)
        for name in SOURCES:
            destination = archive / 'execution-sources' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / name, destination)
        shutil.copy2(target / 'inputs.json', archive / 'inputs.json')
        for name in ('report.json', 'results.xml', 'acceptance.json', 'simulation.log', 'build.log'):
            if (target / 'build/test' / name).is_file():
                shutil.copy2(target / 'build/test' / name, archive / name)
        (archive / 'snapshot.json').write_text(json.dumps(dict(name=args.name, exit_code=completed.returncode,
            current_primary_changed_inputs=[name for name, digest in inputs.items()
                                            if not (source_path(root, name)).is_file() or sha(source_path(root, name)) != digest],
            finished_utc=datetime.now(timezone.utc).isoformat()), indent=2) + '\n')
        print('Archived response-frame execution: ' + str(archive), flush=True)
        raise SystemExit(completed.returncode)
    assert root.parent == Path.home() / 'development/hardware/parser/build/grpc-response-frame-tests'
    from cocotb_tools.runner import get_runner
    inputs = json.loads((root / 'inputs.json').read_text())
    assert all(sha(source_path(root, name)) == digest for name, digest in inputs.items())
    build = root / 'build/test'
    build.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / 'sim/cocotb'))
    runner = get_runner(args.simulator)
    record = dict(phase='running', simulator=args.simulator, input_sha256=inputs,
                  started_utc=datetime.now(timezone.utc).isoformat())
    try:
        runner.build(sources=[source_path(root, name) for name in SOURCES if name.endswith('.v')],
                     hdl_toplevel='grpc_http2_response_framer', build_dir=build, always=True,
                     build_args=['-Wno-fatal'] if args.simulator == 'verilator' else [], log_file=build / 'build.log')
        runner.test(hdl_toplevel='grpc_http2_response_framer', test_module='test_grpc_response_frames',
                    test_dir=build, build_dir=build, results_xml=build / 'results.xml',
                    extra_env={'PARSER_GRPC_FRAME_FIXTURES': str(root / 'build/grpc-response-frame-fixtures')},
                    log_file=build / 'simulation.log')
        xml = ET.parse(build / 'results.xml')
        cases = xml.findall('.//testcase')
        assert len(cases) == 1 and not xml.findall('.//failure') and not xml.findall('.//error')
        acceptance = json.loads((build / 'acceptance.json').read_text())
        assert acceptance['phase'] == 'passed'
        assert all(sha(source_path(root, name)) == digest for name, digest in inputs.items())
        record.update(phase='passed', acceptance_sha256=sha(build / 'acceptance.json'),
                      tests=1, failures=0, finished_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        record.update(phase='failed', error=str(error), finished_utc=datetime.now(timezone.utc).isoformat())
        raise
    finally:
        (build / 'report.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
