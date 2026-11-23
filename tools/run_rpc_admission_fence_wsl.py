"""Freeze a full-vocabulary, actual 78/22 application fence-transition test."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_two_fpga_application import closure

from rtl_paths import source_path


def main():
    driver_bytes=Path(__file__).read_bytes()
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('--candidate', default='rpc-admission-fence-v1')
    ap.add_argument('--scenario',choices=('preservation','coalesced','fragmented','live-fragmented','faults','gpu-first','reset-first','history'),default='preservation')
    args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+', args.name)
    registered=args.candidate=='rpc-registered-frame-select-v1'
    payload=args.candidate=='rpc-receive-payload-pipeline-v1'
    assert registered or payload or args.candidate=='rpc-admission-fence-v1' or re.fullmatch(r'rpc-stream-refusal-v[0-9]+',args.candidate)
    if args.scenario!='preservation':assert args.candidate!='rpc-admission-fence-v1'
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'scripts'))
    from run_raw_envelope_tests import freeze_model_image
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    parent = root / 'build/wsl-reports/raw_envelope_receive_capacity_v4_native_owner_admission_20261122'
    inputs = read(parent / 'inputs.json')
    assert read(parent / 'report.json')['phase'] == 'passed'
    candidate = root / 'build/experiments' / args.candidate
    assembly = read(root / 'build/validation/rpc-admission-fence.json')
    assert assembly['key'] == '1e606bcd79f8f20a' and assembly['assembly_and_strict_elaboration_verified']
    generation = read(candidate / 'generation.json')
    changed_policy=args.candidate!='rpc-admission-fence-v1'
    if changed_policy:
        if payload:
            from verify_receive_payload_settling import require_settling_audit
            settling_audit=require_settling_audit(root)
        elif registered:
            from verify_registered_frame_select import require_unit_audit
            selection_audit=require_unit_audit(root)
            assert generation['parent_directed_audit_key']=='950ce3b65ccb9b0a'
        else:
            assert generation['parent_assembly_audit_key']==assembly['key']
            assert generation['counterexample_audit_key']=='d246ef849f723296'
        assert generation['parser_modules']==79 and generation['non_mmio_parser_modules']==78
        assert all(sha(candidate/n)==h for n,h in generation['outputs_sha256'].items())
    else:
        assert sha(candidate / 'generation.json') == assembly['generation_sha256']
    approved = Path.home() / 'development/hardware/parser'
    assert approved.is_dir()
    target = approved / 'build/raw-envelope-tests' / args.name
    archive = root / 'build/wsl-reports' / ('raw_envelope_' + args.name)
    assert not archive.exists()
    target.mkdir(parents=True, exist_ok=False)
    for name, digest in inputs.items():
        source = parent / 'execution-sources' / name
        assert sha(source) == digest, name
        p = target / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if name == 'build/bidirectional-fixtures/memory.mem':
            freeze_model_image(source, p, approved)
        else:
            shutil.copy2(source, p)
    originals = dict(inputs)
    expected_parser = closure('http2_enveloped_parser_application', candidate / 'joint')
    assert len(expected_parser) == 78
    for module, source in expected_parser.items():
        if changed_policy:
            assert sha(source)==generation['non_mmio_parser_sha256'][module]
        elif module == 'http2_enveloped_parser_application':
            # The non-MMIO application replaces the schema wrapper; it is
            # explicitly covered by that assembly's fifth RTL inverse.
            assert sha(source) == generation['source_edit_certificates']['joint/rtl/' + module + '.v']['after_sha256']
        else:
            assert sha(source) == assembly['executed_parser_sha256'][module]
        name = 'rtl/' + source.name
        p = target / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, p)
        inputs[name] = sha(p)
    parser = {n: sha(p) for n, p in closure('http2_enveloped_parser_application', target).items()}
    tokenizer = {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', target).items()}
    assert parser == {n: sha(p) for n, p in expected_parser.items()} and len(tokenizer) == 22
    assert tokenizer == {n: sha(p) for n, p in closure('tokenizer_fpga_memory_subsystem', parent / 'execution-sources').items()}
    selected_test=('test_rpc_refusal_history'if args.scenario=='history'else
        'test_rpc_refusal_gpu'if args.scenario in('gpu-first','reset-first')else
        'test_rpc_refusal_faults'if args.scenario=='faults'else
        'test_rpc_stream_refusal'if args.scenario!='preservation'else'test_rpc_admission_fence')
    edits = {
        'sim/cocotb_two_fpga_enveloped_top.sv': [
            ('reg  admit_messages=0;', 'reg  admit_messages=0;\nreg  admit_new_rpcs=1;'),
            ('.admit_messages(admit_messages),', '.admit_messages(admit_messages),\n    .admit_new_rpcs(admit_new_rpcs),')],
        'sim/cocotb/test_http2_prefill.py': [
            ('assert status==3 or(value(d,\'fault_client\')==19',
             "assert (getattr(self,'expected_fence_stream',None)==stream and status==4 and self.record_fence_rejection()) or status==3 or(value(d,'fault_client')==19")],
        'scripts/run_raw_envelope_tests.py': [
            ("test_module={'native':'test_raw_grpc_enveloped'", "test_module={'native':'"+selected_test+"'")],
    }
    certificates = {}
    for name, replacements in edits.items():
        p = target / name
        original = p.read_bytes().decode()
        updated = original
        # Preserve the frozen fixture's exact original newline convention.
        if '\r\n' in original:
            replacements = [(a.replace('\n', '\r\n'), b.replace('\n', '\r\n')) for a, b in replacements]
        for before, after in replacements:
            assert updated.count(before) == 1, (name, before)
            updated = updated.replace(before, after)
        inverse = updated
        for before, after in reversed(replacements):
            assert inverse.count(after) == 1
            inverse = inverse.replace(after, before)
        assert inverse == original
        p.write_bytes(updated.encode())
        inputs[name] = sha(p)
        certificates[name] = dict(before_sha256=originals[name], after_sha256=inputs[name], replacements=replacements)
    name = 'sim/cocotb/test_rpc_admission_fence.py'
    shutil.copy2(source_path(root, name), target / name)
    inputs[name] = sha(target / name)
    if changed_policy and args.scenario=='preservation':
        p=target/name;original=p.read_bytes().decode()
        before='await b.packet(0, 4, headers(3, b.client), 0)'
        after='await b.packet(0, 4, headers(3, b.client), 1)'
        assert original.count(before)==1
        updated=original.replace(before,after)
        assert updated.replace(after,before)==original
        negative=root/'build/wsl-reports/raw_envelope_rpc_admission_fence_live_v4_observed_20261122'
        assert sha(p)==read(negative/'inputs.json')[name]
        p.write_bytes(updated.encode())
        certificates[name]=dict(before_sha256=inputs[name],after_sha256=sha(p),replacements=[[before,after]],
            purpose='A successfully refused stream consumes/commits its HEADERS packet and HPACK state; retain every old-RPC preservation assertion')
        inputs[name]=sha(p)
    if args.scenario!='preservation':
        name='sim/cocotb/'+selected_test+'.py'
        shutil.copy2(source_path(root, name),target/name);inputs[name]=sha(target/name)
        if args.scenario in('gpu-first','reset-first'):
            helper_name='sim/cocotb/test_rpc_stream_refusal.py'
            shutil.copy2(source_path(root, helper_name),target/helper_name);inputs[helper_name]=sha(target/helper_name)
        if args.scenario=='history':
            helper_name='sim/cocotb/test_rpc_refusal_faults.py'
            shutil.copy2(source_path(root, helper_name),target/helper_name);inputs[helper_name]=sha(target/helper_name)
        if args.scenario=='reset-first':
            p=target/name;original=p.read_bytes().decode();before="ORDER='gpu-first'";after="ORDER='reset-first'"
            assert original.count(before)==1;updated=original.replace(before,after)
            assert updated.replace(after,before)==original
            p.write_bytes(updated.encode());certificates[name]=dict(before_sha256=inputs[name],after_sha256=sha(p),
                replacements=[[before,after]],purpose='Exercise the same actual interfaces with reset offered before GPU response')
            inputs[name]=sha(p)
        if args.scenario in ('fragmented','live-fragmented'):
            p=target/name;original=p.read_bytes().decode()
            before='sending = cocotb.start_soon(b.packet(0, 4, raw, 1))'
            after='''async def send_fragments():
        await b.packet(0,4,raw[:fragment_offset],1)
        b.save_wire_evidence()
        Path('fragment_checkpoint.json').write_text(json.dumps(dict(
            first_fragment_bytes=fragment_offset,discard_valid=value(d.dut.core,'rx_drop_valid'),
            reclaim_pending=value(d.dut.core,'rc_pending'),reclaim_busy=value(d.dut.core,'rc_busy'),
            receive_controller_idle=value(d.dut.core,'receive_controller_idle'),
            live_receive_frame=value(d.dut.core.receive_flow,'frame_active')))+'\\n')
        await b.packet(0,40,raw[fragment_offset:],1)
    sending = cocotb.start_soon(send_fragments())'''
            if args.scenario=='live-fragmented':
                after=after.replace('async def send_fragments():\n','async def send_fragments():\n        fragment_offset=len(raw)-8\n')
            assert original.count(before)==1;updated=original.replace(before,after)
            assert updated.replace(after,before)==original
            p.write_bytes(updated.encode());certificates[name]=dict(before_sha256=inputs[name],after_sha256=sha(p),replacements=[[before,after]],
                purpose='Split the same native peer bytes inside refused DATA across two AXI packets; preserve all payloads and assertions')
            inputs[name]=sha(p)
    # The older native fixture predates this recording helper. Include its
    # qualified full-capacity version explicitly in this snapshot's inputs.
    name = 'sim/cocotb/test_raw_open_rpc_credit.py'
    helper = root / 'build/wsl-reports/raw_envelope_receive_capacity_v4_three_streams_20261122'
    assert read(root / 'build/validation/receive-capacity-v4-runtime.json')['key'] == '402f77aa5ca47074'
    assert sha(helper / 'execution-sources' / name) == read(helper / 'inputs.json')[name] == 'a3c8a242b6d7553c53e01c1a9e8b2ba2f276ab2d306e83f4057eb56984793e2a'
    shutil.copy2(helper / 'execution-sources' / name, target / name)
    inputs[name] = sha(target / name)
    name = 'tools/rtl_paths.py'
    (target / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / name, target / name); inputs[name] = sha(target / name)
    (target / 'inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
    shutil.copy2(candidate / 'generation.json', target / 'fence-generation.json')
    (target / Path(__file__).name).write_bytes(driver_bytes)
    launch = root / 'build/validation' / (args.name + '-launch.json')
    assert not launch.exists()
    record = dict(phase='running', name=args.name, target=str(target), archive=str(archive),
        started_utc=datetime.now(timezone.utc).isoformat(), inputs_sha256=inputs,
        parent_inputs_sha256=originals, fixture_edits=certificates,
        parser_sha256=parser, tokenizer_sha256=tokenizer, assembly_audit_key=assembly['key'],
        candidate=args.candidate,stream_refusal_policy_changed=changed_policy,
        scenario=args.scenario,
        driver_sha256=hashlib.sha256(driver_bytes).hexdigest(), generation_sha256=sha(candidate / 'generation.json'),
        portable_memory_backend=True, native_vendor_runtime_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False, full_system_complete=False)
    if registered:record['registered_selection_unit_audit_key']=selection_audit['key']
    if payload:
        record['settling_source_audit_key']=settling_audit['key']
        record['registered_selection_unit_audit_key']=generation['parent_unit_audit_key']
    def save():
        launch.write_text(json.dumps(record, indent=2) + '\n')
    save()
    print('Frozen actual 78/22-module full-vocabulary fence transitions: ' + args.name, flush=True)
    try:
        with (target / 'driver.log').open('w') as log:
            process = subprocess.Popen([sys.executable, str(target / 'scripts/run_raw_envelope_tests.py'),
                '--execute', '--profile', 'native'], cwd=target, stdout=log, stderr=subprocess.STDOUT)
            record['process_pid'] = process.pid
            save()
            code = process.wait()
        record.update(phase='completed' if code == 0 else 'failed', exit_code=code)
        assert code == 0, ('Fence-transition regression failed; preserving evidence', code)
    except BaseException as error:
        record.update(phase='failed', error=str(error))
        raise
    finally:
        assert all(sha(target / name) == digest for name, digest in inputs.items())
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        archive.mkdir(parents=True, exist_ok=False)
        for name in inputs:
            p = archive / 'execution-sources' / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if name == 'build/bidirectional-fixtures/memory.mem':
                freeze_model_image(target / name, p, root)
            else:
                shutil.copy2(target / name, p)
        for name in ('inputs.json', 'fence-generation.json', 'driver.log', Path(__file__).name):
            shutil.copy2(target / name, archive / name)
        for p in (target / 'build/test').glob('*'):
            if p.is_file() and p.suffix in ('.log', '.json', '.xml', '.bin'):
                shutil.copy2(p, archive / p.name)
        shutil.copy2(launch, archive / 'launch.json')
    print(json.dumps({k: record[k] for k in ('phase', 'exit_code')}), flush=True)


if __name__ == '__main__':
    main()
