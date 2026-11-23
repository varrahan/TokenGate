"""Run unchanged upstream array-force and flattened-JSON regression tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--whole-release',action='store_true');args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    build=read(root/'build/validation/verilator-v5.054-build/report.json')
    assert build['phase']=='built_version_checked_selftests_pending'
    assert build['commit']=='bbb60a403932a9f695cb6ff001ceb73de6ad9234'
    tool=Path.home()/'development/hardware/parser/build/tools/verilator-v5.054'
    assert str(tool)==build['target'] and sha(tool/'bin/verilator_bin')==build['executable_sha256']
    assert subprocess.run(['git','diff','--quiet'],cwd=tool).returncode==0
    patch=None;binary_sha=build['executable_sha256'];label='verilator-v5.054'
    if args.whole_release:
        patch=read(root/'build/validation/verilator-v5.054-whole-release-v1/report.json')
        assert patch['phase']=='focused_regression_passed_upstream_suite_pending' and patch['actual_semantic_checks']==33
        assert patch['base_simulator_binary_sha256']==binary_sha
        tool=Path(patch['target']);binary_sha=patch['simulator_binary_sha256'];label+='-whole-release-v1'
        assert sha(tool/'bin/verilator_bin')==binary_sha
    def check_sources():
        if patch:
            assert subprocess.run(['git','diff','--name-only'],cwd=tool,check=True,capture_output=True,text=True).stdout.splitlines()==['src/V3Force.cpp']
            edit=patch['source_edit'];text=(tool/edit['path']).read_text()
            assert sha(tool/edit['path'])==edit['after_sha256']
            assert hashlib.sha256(text.replace(edit['anchor']+edit['addition'],edit['anchor']).encode()).hexdigest()==edit['before_sha256']
        else:assert subprocess.run(['git','diff','--quiet'],cwd=tool).returncode==0
    check_sources()
    selected=('t_force_unpacked','t_force_array_element_index','t_force_unpacked_bitsel',
              't_force_unpacked_struct','t_json_only_flat')
    evidence=root/'build/validation'/(label+'-upstream-selected-evidence')
    evidence.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    env=os.environ.copy();env['VERILATOR_ROOT']=str(tool)
    env['PATH']=str(tool/'bin')+os.pathsep+env['PATH']
    command=['/usr/bin/python3','driver.py','--vlt','-j','2','--quiet']+['t/'+n+'.py' for n in selected]
    record=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),command=command,
        simulator_commit=build['commit'],simulator_binary_sha256=binary_sha,local_whole_release_patch=patch,
        selected_tests=list(selected),driver_sha256=sha(Path(__file__)),
        entire_upstream_test_suite_verified=False,full_system_complete=False)
    output=root/'build/validation'/(label+'-upstream-selected.json')
    assert not output.exists()
    def save():output.write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        with(evidence/'driver.log').open('w')as stream:
            process=subprocess.Popen(command,cwd=tool/'test_regress',env=env,stdout=stream,stderr=subprocess.STDOUT)
            record['process_pid']=process.pid;save();code=process.wait()
        log=(evidence/'driver.log').read_text(errors='replace')
        assert code==0,code
        assert re.search(r'^==TESTS DONE, PASSED: .*\bPassed 5\b',log,re.M),log[-2000:]
        assert 'PASSED w/SKIPS' not in log and not re.search(r'^==TESTS DONE, FAILED',log,re.M)
        artifacts={}
        for n in selected:
            for p in sorted((tool/'test_regress/t').glob(n+'.*')):
                destination=evidence/'upstream-sources'/p.name;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(p,destination);artifacts[str(p.relative_to(tool))]=sha(p)
        assert sha(tool/'bin/verilator_bin')==binary_sha
        check_sources()
        record.update(phase='passed',exit_code=code,skipped_tests=0,passed_tests=5,
            unchanged_upstream_sources_sha256=artifacts,driver_log_sha256=sha(evidence/'driver.log'))
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    shutil.copy2(output,evidence/'audit.json')
    print(json.dumps({k:record[k]for k in('phase','passed_tests','skipped_tests')}),flush=True)


if __name__=='__main__':main()
