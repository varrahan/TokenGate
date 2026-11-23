"""Prove actual formatter output equivalence after reset using installed Yosys."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rtl_paths import source_path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name');parser.add_argument('--gate',type=Path)
    parser.add_argument('--gold',type=Path);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if not args.execute:
        assert args.name and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name)
        approved=Path.home()/'development/hardware/parser';assert approved.is_dir()and approved!=root
        target=approved/'build/grpc-header-equivalence'/args.name;target.mkdir(parents=True,exist_ok=False)
        gold=args.gold or source_path(root, 'rtl/grpc_response_headers.v');gate=args.gate or root/'build/experiments/compact-grpc-headers/rtl/grpc_response_headers.v'
        sources={'rtl/gold_input.v':gold,'rtl/gate_input.v':gate}
        for n in('scripts/run_grpc_header_equivalence.py','tools/generate_bidirectional_application.py','tools/generate_two_fpga_application.py', 'tools/rtl_paths.py'):sources[n]=source_path(root, n)
        inputs={}
        for n,p in sources.items():
            destination=target/n;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination);inputs[n]=sha(destination)
        (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        print('Frozen actual RTL equivalence: '+str(target),flush=True)
        result=subprocess.run([sys.executable,str(target/'scripts/run_grpc_header_equivalence.py'),'--execute'],check=False)
        assert all(sha(target/n)==h for n,h in inputs.items())
        archive=root/'build/wsl-reports'/('grpc_header_equivalence_'+args.name);archive.mkdir(parents=True,exist_ok=False)
        for n in inputs:
            p=archive/'execution-sources'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/n,p)
        shutil.copy2(target/'inputs.json',archive/'inputs.json')
        for n in('report.json','yosys.log','gold.v','gate.v','miter.v','proof.ys','counterexample.vcd'):
            if(target/'build/proof'/n).is_file():shutil.copy2(target/'build/proof'/n,archive/n)
        (archive/'snapshot.json').write_text(json.dumps(dict(exit_code=result.returncode,finished_utc=datetime.now(timezone.utc).isoformat(),
            original_production_source=str(gold.resolve()),isolated_gate_source=str(gate.resolve())),indent=2)+'\n')
        print('Archived actual RTL equivalence: '+str(archive),flush=True);raise SystemExit(result.returncode)
    assert root.parent==Path.home()/'development/hardware/parser/build/grpc-header-equivalence'
    inputs=json.loads((root/'inputs.json').read_text());assert all(sha(source_path(root, n))==h for n,h in inputs.items())
    sys.path.insert(0,str(root/'tools'));from generate_bidirectional_application import ports
    from generate_two_fpga_application import add_ports,rename
    original=(source_path(root, 'rtl/gold_input.v')).read_text();gate=(source_path(root, 'rtl/gate_input.v')).read_text()
    public=ports(original,'grpc_response_headers');assert public==ports(gate,'grpc_response_headers')
    helpers=[('output','[2:0]','formal_state'),('output','[1:0]','formal_encoding'),('output','[31:0]','formal_status_code')]
    folder=root/'build/proof';folder.mkdir(parents=True,exist_ok=True)
    for name,source in(('gold',original),('gate',gate)):
        source=add_ports(source,'grpc_response_headers',helpers)
        source=source.replace('endmodule','assign formal_state=state;assign formal_encoding=encoding;assign formal_status_code=status_code;\nendmodule')
        (folder/(name+'.v')).write_text(rename(source,'grpc_response_headers','header_'+name))
    lines=['`default_nettype none','module header_equivalence #(parameter USER_WIDTH=16)(',
        ',\n'.join('input wire '+w+' '+n for d,w,n in public if d=='input'),');']
    outputs=[p for p in public if p[0]=='output']+helpers
    for name in('gold','gate'):
        lines +=['wire '+w+' '+name+'_'+n+';'for _,w,n in outputs]
        connections=[f'.{n}({n if d=="input"else name+"_"+n})'for d,_,n in public+helpers]
        lines +=[f'header_{name} #(.USER_WIDTH(USER_WIDTH)) {name}('+','.join(connections)+');']
    lines +=['reg initialized=0;','always @(posedge clk)begin','initialized<=1;',
        'if(!initialized)assume(rst);','if(initialized)begin']
    lines +=[f'assert(gold_{n}==gate_{n});'for _,_,n in outputs]
    # These are asserted induction lemmas over actual internal registers, not
    # environmental assumptions. They must pass both reset base and step cases.
    lines +=['assert(gold_formal_state<=4);','if(gold_formal_state==2)begin',
        'assert(gold_result_kind<=2&&gold_formal_encoding<=2&&gold_formal_status_code<=16);',
        'assert(gold_result_stream!=0&&gold_result_stream[0]);',
        'assert(gold_result_kind!=0||gold_formal_status_code==0);',
        'assert(gold_result_kind!=2||gold_formal_status_code!=0);','end','end','end','endmodule','`default_nettype wire']
    (folder/'miter.v').write_text('\n'.join(lines)+'\n')
    # Map and simplify the original variable-shift packet builder before SAT.
    # This changes the proof representation without restricting RTL inputs.
    proof='read_verilog -formal gold.v gate.v miter.v\nprep -top header_equivalence -flatten\ntechmap\nopt -full\nabc -g simple\nopt_clean\nsat -seq 1 -tempinduct -maxsteps 12 -set-assumes -prove-asserts -verify -timeout 60 -dump_vcd counterexample.vcd\n'
    (folder/'proof.ys').write_text(proof)
    version=subprocess.run(['yosys','-V'],check=True,capture_output=True,text=True).stdout.strip()
    report=dict(phase='running',input_sha256=inputs,started_utc=datetime.now(timezone.utc).isoformat(),yosys_version=version,
        actual_public_outputs=len(public)-sum(d=='input'for d,_,_ in public),asserted_internal_lemmas=True,
        only_environment_assumption='reset on the initial sampled clock; all later inputs unconstrained',
        maximum_induction_steps=12,timeout_per_sat_instance_seconds=60,technology_mapped_proof_model=True)
    try:
        with(folder/'yosys.log').open('w')as output:result=subprocess.run(['yosys','-T','-s','proof.ys'],cwd=folder,stdout=output,stderr=subprocess.STDOUT,check=False)
        report['yosys_exit_code']=result.returncode
        assert result.returncode==0 and 'Induction step proven: SUCCESS!'in(folder/'yosys.log').read_text()
        assert all(sha(source_path(root, n))==h for n,h in inputs.items())
        report.update(phase='passed',unbounded_post_reset_equivalence_proven=True,physical_timing_verified=False,full_system_complete=False)
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        report['generated_sha256']={n:sha(folder/n)for n in('gold.v','gate.v','miter.v','proof.ys','yosys.log')}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
