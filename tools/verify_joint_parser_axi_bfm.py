"""Exercise the exact Parser AXI device model used in the native joint run."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--joint',required=True);args=ap.parse_args()
    assert all(re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in (args.name,args.joint))
    root=Path(__file__).resolve().parents[1];joint=root/'build/validation'/args.joint
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    report=json.loads((joint/'report.json').read_text())
    model=joint/'joint_parser_axi_memory.svh'
    assert sha(model)==report['inputs_sha256'][model.name]
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    shutil.copy2(model,folder/model.name)
    shutil.copy2(root/'sim/joint_parser_axi_memory_test.sv',folder/'test.sv')
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    result=dict(phase='running',joint_run=args.joint,started_utc=datetime.now(timezone.utc).isoformat(),
        model_sha256=sha(model),test_sha256=sha(folder/'test.sv'),driver_sha256=sha(Path(__file__)),passed=False,commands=[])
    native=Path('C:/AMDDesignTools/2025.2/Vivado/bin')
    def save(): (folder/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(command,name):
        result['commands'].append(command);save()
        with (folder/(name+'.log')).open('w') as stream:
            completed=subprocess.run(command,cwd=folder,stdout=stream,stderr=subprocess.STDOUT)
        log=(folder/(name+'.log')).read_text(errors='replace')
        assert completed.returncode==0 and not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',log,re.M),name
        return log
    try:
        run([str(native/'xvlog.bat'),'--sv','--include','.','test.sv'],'compile')
        run([str(native/'xelab.bat'),'--snapshot','parser_bfm','work.joint_parser_axi_memory_test'],'elaborate')
        output=run([str(native/'xsim.bat'),'parser_bfm','--runall','--log','xsim.log'],'simulate')
        assert output.count('JOINT_PARSER_AXI_MEMORY_TEST_PASS')==1
        actual=(folder/'xsim.log').read_text(errors='replace')
        assert actual.count('JOINT_PARSER_AXI_MEMORY_TEST_PASS')==1 and not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',actual,re.M)
        assert sha(folder/model.name)==sha(model)==result['model_sha256']
        result.update(phase='exact_joint_parser_axi_device_verified',passed=True,log_sha256=sha(folder/'xsim.log'),
            simultaneous_independent_read_write=True,read_write_backpressure=True,sparse_write_strobes=True,
            independent_full_bank_oracle=True,poisoned_address_after_acceptance=True)
    except BaseException as error: result.update(phase='failed',error=str(error));raise
    finally: result['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({k:result[k] for k in ('phase','passed','model_sha256')}))


if __name__=='__main__':main()
