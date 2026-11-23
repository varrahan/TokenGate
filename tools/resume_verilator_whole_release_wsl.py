"""Resume the terminal copy-guard failure after preserving its failed report."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    evidence=root/'build/validation/verilator-v5.054-whole-release-v1'
    report=evidence/'report.json';record=json.loads(report.read_text())
    assert record['phase']=='failed' and record['released_binary_reproduces_exact_failure']
    correction='--correct-visitor-api' in sys.argv
    block='--correct-visitor-block' in sys.argv
    unwrap='--unwrap-visitor-block' in sys.argv
    assert sum((correction,block,unwrap))<=1
    failure_label='visitor-unwrap' if unwrap else 'visitor-block' if block else 'visitor-api' if correction else 'copy-guard'
    assert not(evidence/('failed-'+failure_label+'-report.json')).exists()
    shutil.copy2(report,evidence/('failed-'+failure_label+'-report.json'))
    shutil.copy2(Path(__file__),evidence/(('unwrap-' if unwrap else 'block-' if block else 'corrected-' if correction else '')+Path(__file__).name))
    target=Path(record['target']);original=target.with_name('verilator-v5.054')
    assert sha(original/'bin/verilator_bin')==record['base_simulator_binary_sha256']
    name='test_regress/t/t_sys_file_basic_cover_expr.out'
    source=original/name;destination=target/name
    assert source.is_symlink()
    if not destination.is_symlink():
        assert destination.is_file() and destination.read_bytes()==source.read_bytes()
        assert destination.resolve().is_relative_to(target.resolve())
        destination.unlink();destination.symlink_to(os.readlink(source))
    assert os.readlink(destination)==os.readlink(source)
    assert subprocess.run(['git','diff','--name-only'],cwd=target,check=True,capture_output=True,text=True).stdout.splitlines()==['src/V3Force.cpp']
    edit=record['source_edit'];text=(target/edit['path']).read_text()
    assert sha(target/edit['path'])==edit['after_sha256']
    assert hashlib.sha256(text.replace(edit['anchor']+edit['addition'],edit['anchor']).encode()).hexdigest()==edit['before_sha256']
    if correction:
        assert text.count('            iterateAndNext(releasesp);')==1
        text=text.replace('            iterateAndNext(releasesp);','            iterateAndNextNull(releasesp);')
        (target/edit['path']).write_text(text)
        edit['addition']=edit['addition'].replace('iterateAndNext(releasesp);','iterateAndNextNull(releasesp);')
        edit['after_sha256']=sha(target/edit['path'])
        assert hashlib.sha256(text.replace(edit['anchor']+edit['addition'],edit['anchor']).encode()).hexdigest()==edit['before_sha256']
        shutil.copy2(evidence/'build.log',evidence/'failed-visitor-api-build.log')
        diff=subprocess.run(['git','diff','--','src/V3Force.cpp'],cwd=target,check=True,capture_output=True,text=True).stdout
        (evidence/'whole-array-release.patch').write_text(diff)
    if block:
        before='''            nodep->replaceWith(releasesp);
            VL_DO_DANGLING(pushDeletep(nodep), nodep);
            iterateAndNextNull(releasesp);'''
        after='''            AstBegin* const beginp = new AstBegin{flp, "", releasesp, false};
            nodep->replaceWith(beginp);
            VL_DO_DANGLING(pushDeletep(nodep), nodep);
            iterateChildren(beginp);'''
        assert text.count(before)==1;text=text.replace(before,after)
        (target/edit['path']).write_text(text)
        edit['addition']=edit['addition'].replace(before,after);edit['after_sha256']=sha(target/edit['path'])
        assert hashlib.sha256(text.replace(edit['anchor']+edit['addition'],edit['anchor']).encode()).hexdigest()==edit['before_sha256']
        for name in ('build.log','positive-build.log'):
            shutil.copy2(evidence/name,evidence/('before-visitor-block-'+name))
        diff=subprocess.run(['git','diff','--','src/V3Force.cpp'],cwd=target,check=True,capture_output=True,text=True).stdout
        (evidence/'whole-array-release.patch').write_text(diff)
    if unwrap:
        before='            iterateChildren(beginp);'
        after='''            iterateChildren(beginp);
            AstNode* const replacementp = beginp->stmtsp()->unlinkFrBackWithNext();
            beginp->replaceWith(replacementp);
            VL_DO_DANGLING(pushDeletep(beginp), beginp);'''
        assert text.count(before)==1;text=text.replace(before,after)
        (target/edit['path']).write_text(text)
        edit['addition']=edit['addition'].replace(before,after);edit['after_sha256']=sha(target/edit['path'])
        assert hashlib.sha256(text.replace(edit['anchor']+edit['addition'],edit['anchor']).encode()).hexdigest()==edit['before_sha256']
        for name in ('build.log','positive-build.log'):
            shutil.copy2(evidence/name,evidence/('before-visitor-unwrap-'+name))
        diff=subprocess.run(['git','diff','--','src/V3Force.cpp'],cwd=target,check=True,capture_output=True,text=True).stdout
        (evidence/'whole-array-release.patch').write_text(diff)
    record.update(phase='building_patched_tool',resumed_utc=datetime.now(timezone.utc).isoformat(),
        copy_symlink_repair=name,resume_driver_sha256=sha(Path(__file__)))
    record.pop('error',None);record.pop('finished_utc',None)
    env=os.environ.copy();env['VERILATOR_ROOT']=str(target)
    work=target.parent/'whole-release-regression-v1'
    assert sha(work/'tb_verilator_whole_array_release.sv')==record['testbench_sha256']
    def save():report.write_text(json.dumps(record,indent=2)+'\n')
    def run(command,label,cwd):
        record['commands'].append(command);save()
        with(evidence/(label+'.log')).open('w')as stream:
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
            record['process_pid']=process.pid;save();code=process.wait()
        assert code==0,(label,code)
        return(evidence/(label+'.log')).read_text(errors='replace')
    try:
        run(['make','-C','src','-j','2','opt'],'build',target)
        record['simulator_binary_sha256']=sha(target/'bin/verilator_bin')
        record['phase']='positive_regression';save()
        run([str(target/'bin/verilator'),'--binary','--timing','--assert','-Wno-fatal','-j','2',
            '--top-module','tb_verilator_whole_array_release','tb_verilator_whole_array_release.sv',
            '--Mdir','positive-obj'],'positive-build',work)
        log=run([str(work/'positive-obj/Vtb_verilator_whole_array_release')],'positive-runtime',work)
        assert log.count('WHOLE_ARRAY_RELEASE_PASS checks=33')==1 and '%Error' not in log
        assert sha(original/'bin/verilator_bin')==record['base_simulator_binary_sha256']
        record.update(phase='focused_regression_passed_upstream_suite_pending',actual_semantic_checks=33,
            source_patch_sha256=sha(evidence/'whole-array-release.patch'),
            negative_control_log_sha256=sha(evidence/'negative.log'),positive_log_sha256=sha(evidence/'positive-runtime.log'))
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({k:record[k]for k in('phase','actual_semantic_checks','simulator_binary_sha256')}),flush=True)


if __name__=='__main__':main()
