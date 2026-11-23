"""Strictly elaborate the complete fenced pair with unchanged AMD models."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import re

from run_joint_capacity_verilator_wsl import check_dead_ecc_json


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',default='rpc-admission-fence-v1');args=ap.parse_args()
    registered=args.candidate=='rpc-registered-frame-select-v1'
    payload=args.candidate=='rpc-receive-payload-pipeline-v1'
    assert registered or payload or args.candidate=='rpc-admission-fence-v1' or re.fullmatch(r'rpc-stream-refusal-v[0-9]+',args.candidate)
    root = Path(__file__).resolve().parents[1]
    source = root / 'build/experiments' / args.candidate
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    generation = json.loads((source / 'generation.json').read_text())
    if registered:
        from verify_registered_frame_select import require_unit_audit
        selection_audit=require_unit_audit(root)
    if payload:
        from verify_receive_payload_settling import require_settling_audit
        settling_audit=require_settling_audit(root)
    tool_report = json.loads((root / 'build/validation/verilator-v5.054-whole-release-v1/report.json').read_text())
    tool = Path(tool_report['target'])
    assert sha(tool / 'bin/verilator_bin') == tool_report['simulator_binary_sha256']
    selected = json.loads((root / 'build/validation/verilator-v5.054-whole-release-v1-upstream-selected.json').read_text())
    assert selected['phase'] == 'passed' and selected['simulator_binary_sha256'] == tool_report['simulator_binary_sha256']
    approved = Path.home() / 'development/hardware/parser'
    assert approved.is_dir()
    target = approved / 'build' / args.candidate
    target.mkdir(parents=True, exist_ok=False)
    archive = root / 'build/wsl-reports' / (args.candidate.replace('-','_')+'_elaboration')
    assert not archive.exists()
    for name, digest in generation['outputs_sha256'].items():
        assert sha(source / name) == digest, name
        p = target / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, p)
    shutil.copy2(source / 'generation.json', target / 'generation.json')
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    env = os.environ.copy()
    env['VERILATOR_ROOT'] = str(tool)
    command = [str(tool / 'bin/verilator'), '--timing', '--assert', '-DOBSOLETE', '-Wno-fatal',
        '--top-module', 'joint_hyperram_grpc_tb', '-I.', '--Mdir', 'obj',
        '--json-only', '--flatten', '--json-only-output', 'elaboration.json',
        '--json-only-meta-output', 'elaboration.meta.json']
    command += [str(p.relative_to(target)) for p in sorted((target / 'joint/rtl').glob('*.v'))]
    command += ['joint/vendor/' + name for name in ('glbl.v', 'xpm_cdc.sv', 'xpm_memory.sv', 'xpm_fifo.sv')]
    command += ['joint_hyperram_grpc_tb.sv']
    record = dict(phase='elaborating', started_utc=datetime.now(timezone.utc).isoformat(),
        generation_sha256=sha(source / 'generation.json'),
        inputs_sha256=generation['outputs_sha256'], command=command,
        driver_sha256=sha(Path(__file__)), simulator_binary_sha256=tool_report['simulator_binary_sha256'],
        functional_runtime_verified=False, timing_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False, full_system_complete=False)
    def save():
        (target / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
        status='rpc-admission-fence-elaboration' if args.candidate=='rpc-admission-fence-v1' else args.candidate+'-elaboration'
        (root / 'build/validation' / (status+'.json')).write_text(json.dumps(record, indent=2) + '\n')
    save()
    try:
        with (target / 'elaboration.log').open('w') as log:
            code = subprocess.run(command, cwd=target, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        record['exit_code'] = code
        assert code == 0, ('Strict elaboration failed', code)
        record['vendor_elaboration_checks'] = check_dead_ecc_json(target)
        record['artifacts_sha256'] = {name: sha(target / name) for name in
            ('elaboration.json', 'elaboration.meta.json', 'elaboration.log')}
        record['phase'] = 'elaborated_independent_audit_pending'
    except BaseException as error:
        record.update(phase='failed', error=str(error))
        raise
    finally:
        assert all(sha(target / name) == digest for name, digest in generation['outputs_sha256'].items())
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        archive.mkdir(parents=True, exist_ok=False)
        for name in generation['outputs_sha256']:
            p = archive / 'execution-sources' / name
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / name, p)
        for name in ('report.json', 'generation.json', 'elaboration.log', 'elaboration.json', 'elaboration.meta.json', Path(__file__).name):
            if (target / name).exists():
                shutil.copy2(target / name, archive / name)
    print(json.dumps({k: record[k] for k in ('phase', 'exit_code')}), flush=True)


if __name__ == '__main__':
    main()
