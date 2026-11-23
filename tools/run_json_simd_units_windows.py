"""Native tests for the parallel JSON classes and actual 512-bit compactor."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--only-scanner',action='store_true');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    sources={name:root/name for name in('rtl/axis_compacting_window.v','rtl/json_simd_scanner.v',
        'sim/tb_compacting_window.sv','sim/tb_json_simd_scanner.sv')}
    sources['vendor/glbl.v']=Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v');inputs={}
    for name,source in sources.items():
        target=folder/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);inputs[name]=sha(target)
    # Independent byte-class lookup rather than HDL comparison expressions.
    groups=[b'"',b'\\',b':',b',',b'{',b'}',b'[',b']',b' \t\n\r',bytes(range(32)),bytes(range(128,256)),b':,{}[]']
    groups.append(bytes(value for value in range(32,128)if value not in b'"\\:,{}[]'))
    table=[sum(1<<index for index,values in enumerate(groups)if byte in values)for byte in range(256)]
    (folder/'json-classes.hex').write_text(''.join(f'{value:04x}\n'for value in table))
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        driver_sha256=sha(Path(__file__)),class_table_sha256=sha(folder/'json-classes.hex'),commands=[],acceptance={},
        native_global_reset_model=True,independent_testbench_assertions_enabled=True,only_scanner=args.only_scanner,
        parser_integration_verified=False,full_system_complete=False)
    output=folder/'report.json'
    def save():output.write_text(json.dumps(report,indent=2)+'\n')
    def run(command,label):
        report['commands'].append(command);save()
        with(folder/(label+'.log')).open('w')as log:
            process=subprocess.Popen(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
            report['active_process']=dict(label=label,pid=process.pid);save();code=process.wait()
        assert code==0,(label,code)
        text=(folder/(label+'.log')).read_text(errors='replace')
        assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),(label,'native failure')
        return text
    try:
        tools=Path('C:/AMDDesignTools/2025.2/Vivado/bin');frozen=folder/'sources'
        run([str(tools/'xvlog.bat'),'--log','rtl-compile.log']+[str(frozen/name)for name in inputs if name.endswith('.v')],'rtl')
        run([str(tools/'xvlog.bat'),'--sv','--log','testbench-compile.log']+[str(frozen/name)for name in inputs if name.endswith('.sv')],'testbench')
        for snapshot,top,marker in(('compact_window','tb_compacting_window','COMPACT_WINDOW_PASS'),
                                    ('json_scanner','tb_json_simd_scanner','JSON_SCANNER_PASS')):
            if args.only_scanner and snapshot!='json_scanner':continue
            run([str(tools/'xelab.bat'),'--debug','off','--snapshot',snapshot,'--log',snapshot+'-elaboration.log',
                'work.'+top,'work.glbl'],snapshot+'-elaboration')
            report['phase']='running_'+snapshot
            text=run('"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" '+snapshot+
                ' --runall --onerror quit --onfinish quit --maxlogsize 16 --log '+snapshot+'-xsim.log',snapshot+'-simulation')
            matches=re.findall('^'+marker+r' (.+)$',text,re.M);assert len(matches)==1,'Unit did not complete'
            values={key:int(value)for key,value in re.findall(r'(\w+)=(\d+)',matches[0])}
            if snapshot=='compact_window':
                assert values['source_words']==4096 and values['resets']==3 and values['discarded_words']>0
                assert values['source_holds']>100 and values['sink_holds']>100
            else:assert values==dict(windows=18441,lanes=8,byte_values=256,counts=9)
            report['acceptance'][snapshot]=values
        assert all(sha(frozen/name)==digest for name,digest in inputs.items())
        report.update(phase='native_json_scanner_passed'if args.only_scanner else'native_compacting_window_and_json_scanner_passed',passed=True)
    except BaseException as error:
        report.update(phase='native_json_simd_units_failed',passed=False,error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps(dict(phase=report['phase'],acceptance=report['acceptance'])))


if __name__=='__main__':main()
