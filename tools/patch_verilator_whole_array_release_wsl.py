"""Fix missing whole-array release lowering in a separate simulator copy."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    build=read(root/'build/validation/verilator-v5.054-build/report.json')
    assert build['phase']=='built_version_checked_selftests_pending'
    original=Path.home()/'development/hardware/parser/build/tools/verilator-v5.054'
    target=original.with_name('verilator-v5.054-whole-release-v1')
    assert sha(original/'bin/verilator_bin')==build['executable_sha256']
    evidence=root/'build/validation/verilator-v5.054-whole-release-v1';evidence.mkdir(parents=True,exist_ok=False)
    assert not target.exists()
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    test_source=root/'sim/tb_verilator_whole_array_release.sv'
    shutil.copy2(test_source,evidence/test_source.name)
    work=original.parent/'whole-release-regression-v1';work.mkdir(exist_ok=False)
    shutil.copy2(test_source,work/test_source.name)
    env=os.environ.copy();env['VERILATOR_ROOT']=str(original)
    record=dict(phase='negative_control',started_utc=datetime.now(timezone.utc).isoformat(),
        base_commit=build['commit'],base_simulator_binary_sha256=build['executable_sha256'],
        testbench_sha256=sha(test_source),driver_sha256=sha(Path(__file__)),target=str(target),
        original_released_tool_modified=False,amd_sources_modified=False,commands=[],
        full_fpga_workload_verified=False,full_system_complete=False)
    def save():(evidence/'report.json').write_text(json.dumps(record,indent=2)+'\n')
    def run(command,label,cwd,expected=0):
        record['commands'].append(command);save()
        with(evidence/(label+'.log')).open('w')as stream:
            process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
            record['process_pid']=process.pid;save();code=process.wait()
        assert (code!=0 if expected=='nonzero' else code==expected),(label,code)
        return(evidence/(label+'.log')).read_text(errors='replace')
    flags=['--binary','--timing','--assert','-Wno-fatal','-j','2',
           '--top-module','tb_verilator_whole_array_release',test_source.name]
    try:
        log=run([str(original/'bin/verilator')]+flags+['--Mdir','negative-obj'],'negative',work,'nonzero')
        assert 'Whole unpacked-array force/release should have been lowered via element selections' in log
        record['released_binary_reproduces_exact_failure']=True
        record['phase']='copying_isolated_tool';save()
        shutil.copytree(original,target,symlinks=True)
        path=target/'src/V3Force.cpp';before=path.read_text()
        anchor='''    void visit(AstRelease* nodep) override {
        UINFO(2, "Converting release statement: " << nodep << "\\n");

'''
        addition='''        // Lower a whole unpacked array (or subarray) release to its leaves.
        // The force discovery pass already represents array forces by leaf.
        if (AstUnpackArrayDType* const arrp
            = VN_CAST(nodep->lhsp()->dtypep()->skipRefp(), UnpackArrayDType)) {
            FileLine* const flp = nodep->fileline();
            AstNodeStmt* const releasesp = ForceState::foreachUnpackedLeaf(
                arrp->unpackDimensions(),
                [&](const std::vector<int>& indices, int /*flat*/) -> AstNodeStmt* {
                    return new AstRelease{
                        flp, ForceState::buildNestedArraySel(
                                 flp, nodep->lhsp()->cloneTreePure(false), indices)};
                });
            UASSERT_OBJ(releasesp, nodep, "Empty whole-array release");
            AstBegin* const beginp = new AstBegin{flp, "", releasesp, false};
            nodep->replaceWith(beginp);
            VL_DO_DANGLING(pushDeletep(nodep), nodep);
            iterateChildren(beginp);
            AstNode* const replacementp = beginp->stmtsp()->unlinkFrBackWithNext();
            beginp->replaceWith(replacementp);
            VL_DO_DANGLING(pushDeletep(beginp), beginp);
            return;
        }

'''
        assert before.count(anchor)==1
        after=before.replace(anchor,anchor+addition);assert after.replace(anchor+addition,anchor)==before
        path.write_text(after)
        record['source_edit']=dict(path='src/V3Force.cpp',before_sha256=hashlib.sha256(before.encode()).hexdigest(),
            after_sha256=sha(path),anchor=anchor,addition=addition,exact_inverse_verified=True)
        diff=subprocess.run(['git','diff','--','src/V3Force.cpp'],cwd=target,check=True,capture_output=True,text=True).stdout
        (evidence/'whole-array-release.patch').write_text(diff)
        assert subprocess.run(['git','diff','--name-only'],cwd=target,check=True,capture_output=True,text=True).stdout.splitlines()==['src/V3Force.cpp']
        env['VERILATOR_ROOT']=str(target);record['phase']='building_patched_tool';save()
        print('Reproduced exact upstream failure; building isolated whole-array release lowering',flush=True)
        run(['make','-C','src','-j','2','opt'],'build',target)
        record['simulator_binary_sha256']=sha(target/'bin/verilator_bin')
        record['phase']='positive_regression';save()
        run([str(target/'bin/verilator')]+flags+['--Mdir','positive-obj'],'positive-build',work)
        log=run([str(work/'positive-obj/Vtb_verilator_whole_array_release')],'positive-runtime',work)
        assert log.count('WHOLE_ARRAY_RELEASE_PASS checks=33')==1 and '%Error' not in log
        assert sha(original/'bin/verilator_bin')==build['executable_sha256']
        record.update(phase='focused_regression_passed_upstream_suite_pending',actual_semantic_checks=33,
            source_patch_sha256=sha(evidence/'whole-array-release.patch'),
            negative_control_log_sha256=sha(evidence/'negative.log'),positive_log_sha256=sha(evidence/'positive-runtime.log'))
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({k:record[k]for k in('phase','actual_semantic_checks','simulator_binary_sha256')}),flush=True)


if __name__=='__main__':main()
