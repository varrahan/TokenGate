"""Retry the archived, unchanged complete miter with word-level SMT."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess


PREPARE = '''read_verilog -formal -sv memory_command_slot.v reference.v candidate.v miter.sv
hierarchy -top proof_top -chparam ENABLE_CAPACITY 1 -chparam ENABLE_STREAM_FORMAT 1
prep -top proof_top -flatten
memory_map
opt
dffunmap
write_smt2 -wires model.smt2
'''


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    parent = root/'build/wsl-reports/rpc_receive_payload_pipeline_v1_20261122'
    previous = json.loads((parent/'report.json').read_text())
    assert not previous['passed'] and previous['phase'] == 'failed'
    assert 'SAT proof finished - no model found: SUCCESS!' in (parent/'reset-base.log').read_text()
    assert 'Interrupted SAT solver: TIMEOUT!' in (parent/'induction.log').read_text()
    assert all(sha(parent/n) == h for n,h in previous['artifacts_sha256'].items())
    name = 'rpc_receive_payload_pipeline_smt_v1_20261122'
    folder = Path.home()/'development/hardware/parser/build/receive-payload-formal'/name
    archive = root/'build/wsl-reports'/name
    launch = root/'build/validation'/(name+'-launch.json')
    assert not archive.exists() and not launch.exists()
    folder.mkdir(parents=True,exist_ok=False)
    names = ('memory_command_slot.v','reference.v','candidate.v','miter.sv',
             'reference-original.v','candidate-original.v','generation.json')
    for filename in names:
        shutil.copy2(parent/filename,folder/filename)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    shutil.copy2(parent/'report.json',folder/'previous-sat-report.json')
    (folder/'prepare.ys').write_text(PREPARE)
    report = dict(previous)
    report.update(phase='preparing_word_level_model',passed=False,
        started_utc=datetime.now(timezone.utc).isoformat(),solver='z3',bounded_base_steps=12,
        induction_steps=12,previous_sat_induction_timed_out=True,
        previous_report_sha256=sha(parent/'report.json'),
        exact_original_miter_sources_preserved=True,commands=[],lemmas={})
    report.pop('artifacts_sha256',None)
    report.pop('error',None)
    report.pop('finished_utc',None)
    inputs = {p.name:sha(p) for p in folder.iterdir() if p.is_file()}
    report['inputs_sha256'] = inputs
    def save():
        raw = json.dumps(report,indent=2)+'\n'
        (folder/'report.json').write_text(raw)
        launch.write_text(raw)
    def run(label,command):
        report['commands'].append(command)
        with (folder/(label+'.log')).open('w') as log:
            process = subprocess.Popen(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
            report['process_pid'] = process.pid
            save()
            code = process.wait()
        assert code == 0,(label,code)
    save()
    try:
        run('prepare',['yosys','-Q','-T','-s','prepare.ys'])
        assert not any(word in (folder/'prepare.log').read_text() for word in ('ERROR:','Warning: Wire'))
        report['model_sha256'] = sha(folder/'model.smt2')
        for label,induct in (('reset-base',False),('induction',True)):
            report['phase'] = 'proving_'+label
            command = ['yosys-smtbmc','-s','z3','-t','12','--timeout','180','--noprogress','--presat']
            if induct:
                command.append('-i')
            command += ['--dump-vcd',label+'-counterexample.vcd','model.smt2']
            run(label,command)
            assert 'Status: PASSED' in (folder/(label+'.log')).read_text()
            report['lemmas'][label] = 'passed'
            save()
            print(json.dumps(dict(lemma=label,solver='z3',passed=True)),flush=True)
        report.update(phase='receive_payload_pipeline_full_controller_equivalence_proven',passed=True)
    except BaseException as error:
        report.update(phase='word_level_proof_failed',error=str(error))
        raise
    finally:
        assert all(sha(folder/n) == h for n,h in inputs.items())
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['artifacts_sha256'] = {p.name:sha(p) for p in folder.iterdir() if p.is_file() and p.name != 'report.json'}
        save()
        shutil.copytree(folder,archive)
    print(json.dumps(dict(phase=report['phase'],passed=report['passed'])))


if __name__ == '__main__':
    main()
