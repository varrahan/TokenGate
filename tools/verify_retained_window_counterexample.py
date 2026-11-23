"""Verify the real retained send-window reset failure without changing memory."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from verify_two_fpga_application import closure


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    name='receive_format_retained_window_binding'
    archive=root/'build/wsl-reports'/('raw_envelope_'+name);source=archive/'execution-sources'
    read=lambda n:json.loads((archive/n).read_text())
    inputs,report,state=(read(n) for n in ('inputs.json','report.json','snapshot.json'))
    assert state['exit_code']==1 and report['phase']=='failed' and report['profile']=='shutdown-faults'
    assert report['input_sha256']==inputs and not (archive/'acceptance.json').exists()
    for n,h in inputs.items():assert sha(source/n)==h,(name,n)
    audit=json.loads((root/'build/validation/receive-format-experiment.json').read_text())
    for top,label in (('http2_enveloped_parser_application','parser'),('tokenizer_fpga_memory_subsystem','tokenizer')):
        assert {n:sha(p) for n,p in closure(top,source).items()}==audit['executed_'+label+'_sha256']
    generation=json.loads((root/'build/experiments/retained-window-reset/generation.json').read_text())
    assert inputs['sim/cocotb/test_raw_shutdown_faults.py']==generation['fixture_sha256']
    assert inputs['sim/cocotb/retained_window_witness.py']==generation['witness_sha256']
    assert inputs['build/bidirectional-fixtures/memory.mem']==audit['executions']['shutdown']['inputs_sha256']['build/bidirectional-fixtures/memory.mem']
    xml=ET.parse(archive/'results.xml');assert len(xml.findall('.//testcase'))==1
    failure=xml.find('.//failure');assert failure is not None and 'header status' in failure.attrib['message']
    log=(archive/'simulation.log').read_text();assert 'Verified shutdown fault directory/0' in log
    trace=read('window_trace.json')
    requests=[e for e in trace if e['event']=='actual_admission_window_request']
    results=[e for e in trace if e['event']=='actual_admission_window_result']
    assert [r['op'] for r in requests]==[0,1,0,1]
    assert [(r['status'],r['detail'],r['memory_status']) for r in results]==[(0,0,0)]*3+[(3,7,0)]
    old,new=requests[1],requests[-1]
    for r in (old,new):
        assert (r['user'],r['stream'],r['generation'],r['record_address'],r['window_address'])==(0,1,1,7232000,0x7f0000)
    assert old['retained_window_hex']=='00'*16
    retained=int.from_bytes(bytes.fromhex(new['retained_window_hex']),'little')
    assert retained&0xffffffff==0x48325357 and retained>>32&0xffffffff==1
    assert retained>>96&0x7fffffff==1
    assert new['clock']<results[-1]['clock']
    result=dict(phase='retained_send_window_generation_reuse_counterexample_verified',
        verified_utc=datetime.now(timezone.utc).isoformat(),snapshot=name,terminal_test_exit_code=1,
        passing_receive_format_audit_key=audit['key'],actual_window_trace=trace,
        actual_retained_window_rejects_reused_generation=True,actual_window_error=[3,7,0],
        identical_original_window_arena=True,no_bfm_memory_writes_added=True,
        retained_window_recovery_verified=False,full_system_complete=False,
        input_sha256=inputs,archive_files_sha256={p.name:sha(p) for p in archive.iterdir() if p.is_file()},
        generation_sha256=sha(root/'build/experiments/retained-window-reset/generation.json'),
        verifier_sha256=sha(Path(__file__)))
    key=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/retained-window-reset-evidence'/key;evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in (Path(__file__),root/'tools/generate_retained_window_reset_case.py',root/'sim/cocotb/retained_window_witness.py'):
        shutil.copy2(p,evidence/p.name)
    result.update(key=key,evidence_folder=str(evidence))
    (root/'build/validation/retained-window-reset-counterexample.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(phase=result['phase'],key=key,actual_window_error=[3,7,0])))


if __name__=='__main__':main()
