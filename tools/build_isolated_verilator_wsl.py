"""Build a pinned upstream simulator in-place without changing system packages."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    root=Path(__file__).resolve().parents[1]
    approved=Path.home()/'development/hardware/parser';assert approved.is_dir()
    target=approved/'build/tools/verilator-v5.054'
    target.parent.mkdir(parents=True,exist_ok=True)
    assert not target.exists()
    evidence=root/'build/validation/verilator-v5.054-build';evidence.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    record=dict(phase='cloning',started_utc=datetime.now(timezone.utc).isoformat(),
        repository='https://github.com/verilator/verilator.git',release='v5.054',target=str(target),
        driver_sha256=sha(Path(__file__)),system_packages_modified=False,commands=[])
    env=os.environ.copy();env['VERILATOR_ROOT']=str(target)
    def save():(evidence/'report.json').write_text(json.dumps(record,indent=2)+'\n')
    def run(command,name,cwd=None):
        record['commands'].append(command);save()
        with(evidence/(name+'.log')).open('w')as output:
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT)
            record['process_pid']=process.pid;save();code=process.wait()
        assert code==0,(name,code)
    save()
    try:
        run(['git','clone','--depth','1','--branch','v5.054',record['repository'],str(target)],'clone')
        record['commit']=subprocess.run(['git','rev-parse','HEAD'],cwd=target,check=True,capture_output=True,text=True).stdout.strip()
        record['phase']='configuring';save();run(['autoconf'],'autoconf',target)
        run(['./configure','CXXFLAGS=-O2 -g0'],'configure',target)
        assert '\nopt:' in(target/'src/Makefile').read_text()
        record['phase']='building';save();print('Building isolated Verilator v5.054 commit '+record['commit'],flush=True)
        run(['make','-C','src','-j','2','opt'],'build',target)
        version=subprocess.run([str(target/'bin/verilator'),'--version'],env=env,check=True,capture_output=True,text=True).stdout.strip()
        assert 'Verilator 5.054' in version
        assert subprocess.run(['git','diff','--quiet'],cwd=target).returncode==0
        record.update(phase='built_version_checked_selftests_pending',version=version,
            executable_sha256=sha(target/'bin/verilator_bin'),source_version_control_clean=True,
            simulator_selftests_verified=False,full_system_complete=False)
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({k:record[k]for k in('phase','version','commit')}),flush=True)


if __name__=='__main__':main()
