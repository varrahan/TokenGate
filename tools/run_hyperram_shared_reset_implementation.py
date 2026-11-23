"""Route the isolated shared-reset assembly without modifying primary RTL."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    name='hyperram_async_250_200_shared_reset'
    experiment=root/'build/experiments/hyperram-shared-reset'
    syntax=json.loads((experiment/'build/validation/shared_reset_full_image/report.json').read_text())
    assert syntax['phase']=='syntax_compilation_passed'
    for path,digest in syntax['inputs_sha256'].items():
        assert sha(experiment/'build/validation/shared_reset_full_image/sources'/path)==digest
    output=root/'build/validation'/(name+'-launch.json');assert not output.exists()
    free=shutil.disk_usage(root).free;assert free>=2*1024**3
    subprocess.run([str(root/'.venv312/Scripts/python.exe'),str(experiment/'tools/generate_hyperram_async_timing_harness.py')],check=True,capture_output=True)
    source=root/'scripts/implement_hyperram_async_controller.tcl';text=source.read_text()
    replacements={
        'build validation hyperram_async_windows_full_image_wide_timeout sources rtl':
            'build experiments hyperram-shared-reset build validation shared_reset_full_image sources rtl',
        'scripts implement_hyperram_async_controller.tcl':'scripts implement_hyperram_shared_reset.tcl',
        'build hyperram-async timing_harness.v':'build experiments hyperram-shared-reset build hyperram-async timing_harness.v',
        '# Consume the audited frozen simulation sources, including its explicit FIFO\n# override. Do not silently fall back to the different primary FIFO source.':
            '# Consume the frozen shared-reset experiment, including all matching RTL.\n# Functional regression runs separately; routing alone is not completion.'}
    for old,new in replacements.items():
        assert text.count(old)==1,old;text=text.replace(old,new)
    script=root/'scripts/implement_hyperram_shared_reset.tcl';assert not script.exists();script.write_text(text)
    command=['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace','-source',str(script),
        '-log',str(root/'build'/(name+'.log')),'-journal',str(root/'build'/(name+'.jou')),'-tclargs',name]
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),command=command,
        free_bytes_before=free,parent_functional_audit_key='cdd643b6c5c660c7',
        inputs_sha256=syntax['inputs_sha256'],script_sha256=sha(script),driver_sha256=sha(Path(__file__)),
        primary_rtl_modified=False,functional_completion_pending=True,full_system_complete=False)
    output.write_text(json.dumps(report,indent=2)+'\n')
    with(root/'build'/(name+'-stdout.log')).open('w')as log:
        result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
    report.update(phase='native_process_completed'if result.returncode==0 else'stopped_with_error',exit_code=result.returncode,
        finished_utc=datetime.now(timezone.utc).isoformat(),free_bytes_after=shutil.disk_usage(root).free)
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));raise SystemExit(result.returncode)


if __name__=='__main__':main()
