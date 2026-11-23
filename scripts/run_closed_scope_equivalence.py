"""Prove the actual close-scope capture/comparison cone without protocol assumptions."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


SCOPE=('context_base','context_bytes','window_base','window_bytes','work_floor')
EVENTS=(r'if\(([^()]*)\)begin\s*(?:held_credit_\w+<=0;\s*)*saved_frame_cfg_context_base<=cfg_context_base;',
    r'if\(([^()]*)\)begin\s*closing_pool_base<=window_cfg_stream_base;',
    r'if\(([^()]*)\)begin\s*saved_closed_valid<=1;')


def model(source,name):
    conditions=[re.search(pattern,source)[1]for pattern in EVENTS]
    groups=(('saved_frame_cfg_','cfg_',conditions[0]),('closing_','window_cfg_',conditions[1]),('saved_closed_','closing_',conditions[2]))
    inputs=[('','clk'),('','rst'),('','s_axis_tokens_tvalid'),('','s_axis_tokens_tready'),
        ('','window_req_valid'),('','window_req_ready'),('','window_rsp_valid'),('','window_rsp_ready'),
        ('[7:0]','window_rsp_status'),('','window_rsp_binding_valid'),('','window_rsp_send_closed')]
    for prefix in('cfg_','window_cfg_'):
        inputs +=[('[MEMORY_ADDR_WIDTH:0]'if n.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]',prefix+n)for n in SCOPE]
    lines=[f'module closed_scope_{name} #(parameter MEMORY_ADDR_WIDTH=23)(',
        ',\n'.join('input wire '+w+' '+n for w,n in inputs)+',',
        'output wire scope_value,output wire [3*(5*MEMORY_ADDR_WIDTH+2)-1:0] observed_scope',');']
    resets=[];captures=[];observed=[]
    for prefix,rhs,condition in groups:
        assignments=[]
        for n in SCOPE:
            variable=prefix+n;width='[MEMORY_ADDR_WIDTH:0]'if n.endswith('bytes')else'[MEMORY_ADDR_WIDTH-1:0]'
            lines.append('reg '+width+' '+variable+';');observed.append(variable)
            values=re.findall(r'\b'+variable+r'\s*<=([^;]+);',source)
            assert values==['0',rhs+n],(variable,values)
            resets.append(variable+'<=0;');assignments.append(variable+'<='+values[1]+';')
        captures.append('if('+condition+')begin '+''.join(assignments)+'end')
    lines +=['always @(posedge clk)begin','if(rst)begin '+''.join(resets)+'end',
        'else begin','\n'.join(captures),'end','end']
    if name=='gold':
        comparison=re.search(r'^wire closed_scope_matches=[^;]+;',source,re.M)[0]
    else:
        start=source.index('reg closed_scope_matches;');end=source.index('\nend',start)+len('\nend');comparison=source[start:end]
        assert len(re.findall(r'\bclosed_scope_matches\s*<=',source))==4
    lines +=[comparison,'assign scope_value=closed_scope_matches;',
        'assign observed_scope={'+','.join(observed)+'};','endmodule']
    return '\n'.join(lines)+'\n',inputs,conditions


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and root!=approved
        target=approved/'build/closed-scope-equivalence'/args.name;target.mkdir(parents=True,exist_ok=False)
        sources={'rtl/gold_input.v':root/'rtl/rpc_grpc_http2_return.v',
            'rtl/gate_input.v':root/'build/experiments/registered-close-scope/rtl/rpc_grpc_http2_return.v',
            'scripts/run_closed_scope_equivalence.py':Path(__file__)};inputs={}
        for n,p in sources.items():
            destination=target/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination);inputs[n]=sha(destination)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n');print('Frozen actual close-scope cone: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_closed_scope_equivalence.py'),'--execute'],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('closed_scope_equivalence_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in inputs:
            destination=archive/'execution-sources'/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,destination)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for n in('report.json','yosys.log','gold.v','gate.v','miter.v','proof.ys','counterexample.vcd'):
            if(target/'build/proof'/n).is_file():shutil.copy2(target/'build/proof'/n,archive/n)
        (archive/'snapshot.json').write_text(json.dumps(dict(exit_code=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat()),indent=2)+'\n')
        print('Archived close-scope proof: '+str(archive),flush=True);raise SystemExit(result.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/closed-scope-equivalence'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(root/n)==h for n,h in inputs.items())
    folder=root/'build/proof';folder.mkdir(parents=True,exist_ok=True);definitions=[]
    for name in('gold','gate'):
        text,public,conditions=model((root/f'rtl/{name}_input.v').read_text(),name);(folder/(name+'.v')).write_text(text);definitions.append((public,conditions))
    assert definitions[0]==definitions[1]
    public,conditions=definitions[0]
    lines=['module scope_equivalence #(parameter MEMORY_ADDR_WIDTH=23)(',',\n'.join('input wire '+w+' '+n for w,n in public),');',
        'wire gold_value,gate_value;wire [3*(5*MEMORY_ADDR_WIDTH+2)-1:0] gold_observed,gate_observed;']
    for name in('gold','gate'):
        lines +=['closed_scope_'+name+' #(.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) '+name+'('+','.join('.'+n+'('+n+')'for _,n in public)+
            ',.scope_value('+name+'_value),.observed_scope('+name+'_observed));']
    lines +=['reg initialized=0;always @(posedge clk)begin initialized<=1;',
        'if(!initialized)assume(rst);','if(initialized)begin assert(gold_observed==gate_observed);assert(gold_value==gate_value);end','end','endmodule']
    (folder/'miter.v').write_text('\n'.join(lines)+'\n')
    (folder/'proof.ys').write_text('read_verilog -formal gold.v gate.v miter.v\nprep -top scope_equivalence -flatten\nsat -seq 1 -tempinduct -maxsteps 8 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n')
    report=dict(phase='running',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat(),actual_capture_conditions=conditions,
        yosys_version=subprocess.run(['yosys','-V'],check=True,capture_output=True,text=True).stdout.strip(),
        only_environment_assumption='reset on the initial sampled clock; all later capture events and scope fields unconstrained',
        memory_address_width=23,proof_scope='projected actual stored-scope capture assignments and comparison; full-module integration requires separate simulation')
    try:
        with(folder/'yosys.log').open('w')as output:result=subprocess.run(['yosys','-T','-s','proof.ys'],cwd=folder,stdout=output,stderr=subprocess.STDOUT,check=False)
        report['yosys_exit_code']=result.returncode
        assert result.returncode==0 and 'Induction step proven: SUCCESS!'in(folder/'yosys.log').read_text()
        assert all(sha(root/n)==h for n,h in inputs.items())
        report.update(phase='passed',unbounded_post_reset_scope_comparison_equivalence=True,simultaneous_capture_events_unconstrained=True,
            whole_module_equivalence_verified=False,physical_timing_verified=False,full_system_complete=False)
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();report['generated_sha256']={n:sha(folder/n)for n in('gold.v','gate.v','miter.v','proof.ys','yosys.log')}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
