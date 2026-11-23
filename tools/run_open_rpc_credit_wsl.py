"""Freeze the full qualified design for a new open-RPC credit regression."""
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

from verify_two_fpga_application import closure


def ordinal_edits(text):
    edits = [
        ('async def drain(self,user,stream,application,expected):',
         'async def drain(self,user,stream,application,expected,ordinal=0):'),
        ('self.expected=(user,stream,application,expected);self.draining=True',
         'self.expected=(user,stream,application,expected);self.expected_ordinal=ordinal;self.draining=True'),
        ('(eu,es,ea,self.bindings[eu,es],0,self.last_tag)',
         '(eu,es,ea,self.bindings[eu,es],self.expected_ordinal,self.last_tag)'),
        ('len(expected),user,stream,application,self.bindings[user,stream],0,self.last_tag,1)',
         'len(expected),user,stream,application,self.bindings[user,stream],ordinal,self.last_tag,1)'),
    ]
    original = text
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    inverse = text
    for old, new in reversed(edits):
        assert inverse.count(new) == 1
        inverse = inverse.replace(new, old)
    assert inverse == original
    return text, edits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('--candidate', choices=('frame-owned-quiet', 'frame-event-buffer','open-rpc-reclaim','receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4'), default='frame-owned-quiet')
    ap.add_argument('--messages', type=int, default=9)
    ap.add_argument('--partial-tail', type=int, default=0)
    ap.add_argument('--profile', choices=('open-rpc-credit', 'reclaim-faults', 'large-message-credit','capacity-streams','capacity-grant-faults','capacity-large-reuse','capacity-format-owner'), default='open-rpc-credit')
    args = ap.parse_args()
    assert args.profile == 'open-rpc-credit' or args.candidate in ('open-rpc-reclaim','receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4')
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    assert 9 <= args.messages <= 1024 and 0 <= args.partial_tail <= 300
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    approved = Path('/home/varrahan/development/hardware/parser')
    assert approved.is_dir()
    read = lambda p: json.loads(p.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    source = root / 'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122'
    audit = read(root / 'build/validation/json-simd-corpus.json')
    assert audit['key'] == '2509134d2630b47e'
    inputs = read(source / 'inputs.json')
    assert inputs == audit['inputs_sha256']
    candidate = root / 'build/experiments' / args.candidate
    generation = read(candidate / 'generation.json')
    assert all(sha(candidate / n) == h for n, h in generation['outputs_sha256'].items())
    target = approved / 'build/raw-envelope-tests' / args.name
    output = root / 'build/wsl-reports' / ('raw_envelope_' + args.name)
    assert not target.exists() and not output.exists()
    assert min(shutil.disk_usage(root).free, shutil.disk_usage(approved).free) > 3 * 1024**3
    sys.path.insert(0, str(root / 'scripts'))
    from run_raw_envelope_tests import freeze_model_image
    target.mkdir(parents=True)
    baseline = dict(inputs)
    for name, digest in baseline.items():
        original = source / 'execution-sources' / name
        assert sha(original) == digest, name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if name == 'build/bidirectional-fixtures/memory.mem':
            freeze_model_image(original, destination, approved)
        else:
            shutil.copy2(original, destination)
    changed_rtl = []
    added_rtl = []
    for name, digest in generation['outputs_sha256'].items():
        if inputs.get(name) == digest:
            continue
        assert name.startswith('rtl/')
        shutil.copy2(candidate / name, target / name)
        inputs[name] = digest
        (changed_rtl if name in baseline else added_rtl).append(name)
    expected_changes = {'rtl/http2_axis_ingress.v'}
    if args.candidate in ('frame-owned-quiet','open-rpc-reclaim','receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4'):
        expected_changes.add('rtl/http2_enveloped_frame_grants.v')
    if args.candidate in ('open-rpc-reclaim','receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4'):
        expected_changes.update('rtl/'+name+'.v' for name in generation['changed_existing_modules'])
    assert set(changed_rtl) == expected_changes
    assert set(added_rtl)==({'rtl/grpc_payload_reclaimer.v'} if args.candidate in ('open-rpc-reclaim','receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4') else set())
    edits = []
    name = 'sim/cocotb/test_http2_prefill.py'
    path = target / name
    text, replacements = ordinal_edits(path.read_text())
    path.write_bytes(text.encode())
    inputs[name] = sha(path)
    edits.append(dict(path=name, old_sha256=baseline[name], new_sha256=inputs[name],
        replacements=replacements, exact_inverse_verified=True,
        purpose='Parameterize the expected message ordinal; preserve all identity, held-promise and ACK assertions'))
    name = 'scripts/run_raw_envelope_tests.py'
    path = target / name
    text = path.read_text()
    module = {'open-rpc-credit': 'test_raw_open_rpc_credit', 'reclaim-faults': 'test_raw_reclaim_faults',
              'large-message-credit': 'test_raw_large_message_credit','capacity-streams':'test_raw_capacity_streams',
              'capacity-grant-faults':'test_raw_capacity_grant_faults',
              'capacity-large-reuse':'test_raw_capacity_large_reuse','capacity-format-owner':'test_raw_capacity_format_owner'}[args.profile]
    replacements = [("'receive-flow','receive-errors')", "'receive-flow','receive-errors','" + args.profile + "')"),
        ("'receive-errors':'test_raw_receive_errors'", "'receive-errors':'test_raw_receive_errors','" + args.profile + "':'" + module + "'")]
    original = text
    for old, new in replacements:
        assert text.count(old) == 1
        text = text.replace(old, new)
    inverse = text
    for old, new in reversed(replacements):
        inverse = inverse.replace(new, old)
    assert inverse == original
    path.write_bytes(text.encode())
    inputs[name] = sha(path)
    edits.append(dict(path=name, old_sha256=baseline[name], new_sha256=inputs[name],
        replacements=replacements, exact_inverse_verified=True, purpose='Add only the new test profile'))
    added_sources = ['sim/cocotb/test_raw_open_rpc_credit.py', 'tools/run_open_rpc_credit_wsl.py']
    if args.profile in ('reclaim-faults','capacity-grant-faults'):
        added_sources.append('sim/cocotb/test_raw_reclaim_faults.py')
    if args.profile == 'large-message-credit':
        added_sources.append('sim/cocotb/test_raw_large_message_credit.py')
    if args.profile == 'capacity-streams':
        added_sources.append('sim/cocotb/test_raw_capacity_streams.py')
    if args.profile == 'capacity-grant-faults':
        added_sources.append('sim/cocotb/test_raw_capacity_grant_faults.py')
    if args.profile == 'capacity-large-reuse':
        added_sources.append('sim/cocotb/test_raw_capacity_large_reuse.py')
    if args.profile == 'capacity-format-owner':
        added_sources.append('sim/cocotb/test_raw_capacity_format_owner.py')
    for name in added_sources:
        destination = target / name
        shutil.copy2(root / name, destination)
        inputs[name] = sha(destination)
    modified_tests = {e['path'] for e in edits}
    for name, digest in baseline.items():
        if name not in changed_rtl and name not in modified_tests:
            assert inputs[name] == digest, name
    parser_modules=77 if args.candidate in ('open-rpc-reclaim','receive-capacity','receive-capacity-v2','receive-capacity-v3','receive-capacity-v4') else 76
    assert len(closure('http2_enveloped_parser_application', target)) == parser_modules
    assert len(closure('tokenizer_fpga_memory_subsystem', target)) == 22
    (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    launch = root / 'build/validation' / (args.name + '-launch.json')
    state = dict(phase='running', name=args.name, profile=args.profile, candidate=args.candidate,
        requested_messages=args.messages, initial_partial_record_bytes=args.partial_tail,
        baseline_audit_key=audit['key'], target=str(target), archive=str(output),
        exact_parser_modules=parser_modules, exact_tokenizer_modules=22, inputs_sha256=inputs,
        changed_rtl=changed_rtl,added_rtl=added_rtl,fixture_edits=edits, generation_sha256=sha(candidate / 'generation.json'),
        driver_sha256=sha(Path(__file__)), full_model_image_preserved=True,
        native_http2_client_sources_unchanged=True, portable_memory_backend=True,
        native_timing_verified=False, full_system_complete=False,
        started_utc=datetime.now(timezone.utc).isoformat())
    def save():
        launch.write_text(json.dumps(state, indent=2) + '\n')
    save()
    print('Frozen actual open-RPC credit test: ' + str(target), flush=True)
    try:
        with (target / 'driver.log').open('w') as stream:
            process = subprocess.Popen([sys.executable, str(target / 'scripts/run_raw_envelope_tests.py'),
                '--execute', '--profile', args.profile], cwd=target, stdout=stream, stderr=subprocess.STDOUT,
                env=dict(os.environ, PARSER_OPEN_RPC_MESSAGES=str(args.messages), PARSER_OPEN_RPC_PARTIAL_TAIL=str(args.partial_tail)))
            state['launcher_pid'] = process.pid
            save()
            code = process.wait()
        assert all(sha(target / n) == h for n, h in inputs.items())
        output.mkdir(parents=True, exist_ok=False)
        for name, digest in inputs.items():
            destination = output / 'execution-sources' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if name == 'build/bidirectional-fixtures/memory.mem':
                freeze_model_image(target / name, destination, root)
            else:
                shutil.copy2(target / name, destination)
            assert sha(destination) == digest
        for filename in ('report.json', 'acceptance.json', 'failure.json', 'requests.json', 'receive_trace.json',
                         'wire_frames.json', 'ingress_packets.json',
                         'completion_wait_progress.json', 'reuse_progress.json', 'ownership_progress.json', 'private_credit_trace.json',
                         'progress.json', 'results.xml', 'simulation.log', 'build.log'):
            path = target / 'build/test' / filename
            if path.is_file():
                shutil.copy2(path, output / filename)
        for filename in ('inputs.json', 'driver.log'):
            shutil.copy2(target / filename, output / filename)
        state.update(phase='completed' if code == 0 else 'failed', exit_code=code)
        (output / 'snapshot.json').write_text(json.dumps(state, indent=2) + '\n')
    except BaseException as error:
        state.update(phase='stopped_with_error', error=str(error))
        raise
    finally:
        state['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps(dict(name=args.name, phase=state['phase'], exit_code=code)), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
