"""Guard and launch the small, source-frozen native memory assembly build."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from datetime import datetime,timezone


def main():
    root=Path(__file__).resolve().parents[1]
    name='hyperram_async_250_200_qualified_reset'
    report_path=root/'build/validation'/(name+'-launch.json')
    assert not report_path.exists(),'Keep previous launch evidence'
    free=shutil.disk_usage(root).free
    assert free>=2*1024**3,'Need at least 2 GiB for this small isolated build'
    audited=json.loads((root/'build/validation/hyperram-async-native.json').read_text())
    assert audited['key']=='cdd643b6c5c660c7'
    tested=root/'build/validation/hyperram_async_windows_full_image_wide_timeout/sources'
    for path,digest in audited['inputs_sha256'].items():
        assert hashlib.sha256((tested/path).read_bytes()).hexdigest()==digest
    subprocess.run([str(root/'.venv312/Scripts/python.exe'),str(root/'tools/generate_hyperram_async_timing_harness.py')],check=True,capture_output=True)
    command=['C:/AMDDesignTools/2025.2/Vivado/bin/vivado.bat','-mode','batch','-notrace',
             '-source',str(root/'scripts/implement_hyperram_async_controller.tcl'),
             '-log',str(root/'build'/(name+'.log')),'-journal',str(root/'build'/(name+'.jou')),'-tclargs',name]
    report=dict(phase='running',started_utc=datetime.now(timezone.utc).isoformat(),command=command,
                free_bytes_before=free,functional_audit_key=audited['key'],full_system_complete=False)
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    with (root/'build'/(name+'-stdout.log')).open('w')as log:
        result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
    report.update(phase='native_process_completed'if result.returncode==0 else'stopped_with_error',
                  exit_code=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat(),
                  free_bytes_after=shutil.disk_usage(root).free)
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
