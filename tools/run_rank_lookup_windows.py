"""Freeze and run the production external rank lookup in native XSim."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);args=parser.parse_args()
    assert args.name.replace('_','').isalnum()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    sources={name:source_path(root, name) for name in('rtl/bpe_rank_lookup.v','rtl/programmable_table_ram.v','sim/tb_rank_lookup_pipeline.sv')}
    sources['vendor/glbl.v']=Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v')
    inputs={}
    for name,source in sources.items():
        target=folder/'sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);inputs[name]=sha(target)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        driver_sha256=sha(Path(__file__)),commands=[],table_address_bits=18,token_id_bits=17,
        memory_address_bits=23,independent_memory_responder=True,full_tokenizer_regression=False,full_system_complete=False)
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
        run([str(tools/'xvlog.bat'),'--log','rtl-compile.log',str(frozen/'rtl/programmable_table_ram.v'),
            str(frozen/'rtl/bpe_rank_lookup.v'),str(frozen/'vendor/glbl.v')],'rtl')
        run([str(tools/'xvlog.bat'),'--sv','--log','testbench-compile.log',str(frozen/'sim/tb_rank_lookup_pipeline.sv')],'testbench')
        run([str(tools/'xelab.bat'),'--debug','off','--snapshot','rank_pipeline','--log','xelab.log',
            'work.tb_rank_lookup_pipeline','work.glbl'],'elaboration')
        report['phase']='running'
        text=run('"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" rank_pipeline --runall --onerror quit --onfinish quit --maxlogsize 16 --log xsim-rank.log','simulation')
        markers=re.findall(r'^RANK_PIPELINE_PASS (.+)$',text,re.M);assert len(markers)==1,'No completion marker'
        values={key:int(value)for key,value in re.findall(r'(\w+)=(\d+)',markers[0])}
        assert values==dict(completed_queries=11,reset_aborts=3,total_reads=262157,full_probe_reads=262144)
        assert all(sha(frozen/name)==digest for name,digest in inputs.items())
        report.update(phase='native_rank_lookup_pipeline_passed',passed=True,acceptance=values)
    except BaseException as error:
        report.update(phase='native_rank_lookup_pipeline_failed',passed=False,error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps(dict(phase=report['phase'],acceptance=report['acceptance'])))


if __name__=='__main__':main()
