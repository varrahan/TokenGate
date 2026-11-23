"""Run all four original refusal fixtures on one exact selection candidate."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from verify_registered_frame_select import require_unit_audit


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--candidate',choices=('rpc-registered-frame-select-v1','rpc-receive-payload-pipeline-v1'),default='rpc-registered-frame-select-v1')
    args=ap.parse_args();payload=args.candidate=='rpc-receive-payload-pipeline-v1'
    root=Path(__file__).resolve().parents[1]
    if payload:
        from verify_receive_payload_settling import require_settling_audit
        audit=require_settling_audit(root)
    else:audit=require_unit_audit(root)
    prefix='rpc_receive_payload_v1'if payload else'rpc_registered_select_v1'
    state_path=root/'build/validation'/('receive-payload-directed-batch-20261122.json'if payload else'registered-frame-select-directed-batch-20261122.json')
    assert not state_path.exists()
    cases=[('preservation','live'),('coalesced','coalesced'),('fragmented','fragmented'),('live-fragmented','live_fragmented')]
    for case,suffix in cases:
        name=prefix+'_'+suffix+'_20261122'
        assert not(root/'build/validation'/(name+'-launch.json')).exists()
    frozen=state_path.with_suffix('.py');assert not frozen.exists();shutil.copy2(Path(__file__),frozen)
    record=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),
        source_audit_key=audit['key'],candidate=args.candidate,driver_sha256=hashlib.sha256(frozen.read_bytes()).hexdigest(),cases=[])
    def save():state_path.write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        for case,suffix in cases:
            name=prefix+'_'+suffix+'_20261122'
            command=[sys.executable,str(root/'tools/run_rpc_admission_fence_wsl.py'),
                '--candidate',args.candidate,'--scenario',case,'--name',name]
            process=subprocess.Popen(command,cwd=root)
            record['process_pid']=process.pid;record['active_case']=case;save()
            code=process.wait();record['cases'].append(dict(case=case,run=name,exit_code=code));save()
            assert code==0,(case,'Original refusal fixture failed; preserved evidence',code)
        record['phase']='all_four_completed_independent_audit_pending'
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps(dict(phase=record['phase'],completed_cases=len(record['cases']))))


if __name__=='__main__':main()
