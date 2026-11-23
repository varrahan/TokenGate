"""Inductive equivalence of the actual two-slot FIFO RTL, plus cone checks.

Observability ports expose state without modifying any original statement.
Only valid payloads are compared, as required by AXI-Stream. Input data and
handshakes are otherwise unrestricted; reset is required at the initial step
and may occur arbitrarily later. This is a two-state formal proof, separately
complemented by the four-state framing corpus.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from generate_hyperram_cdc_timing_harness import ports


def observe(source, module, signals):
    position=source.index(');')
    declarations=',\n'+',\n'.join(f'output wire {width} formal_{name}' for width,name in signals)+'\n'
    assignments='\n'.join(f'assign formal_{name}={name};' for _,name in signals)+'\n'
    result=source[:position]+declarations+source[position:]
    result=result.replace('endmodule',assignments+'endmodule')
    assert result.count(assignments)==1 and result.count(declarations)==1
    assert result.replace(assignments,'').replace(declarations,'')==source
    assert len(ports(result,module))==len(ports(source,module))+len(signals)
    return result


def miter(data,keep,user):
    width=data+keep+user+1
    lines=[f'''`default_nettype none
module fifo_equivalence(input wire clk,input wire rst,
input wire [{data-1}:0] data,input wire [{keep-1}:0] keep,
input wire [{user-1}:0] user,input wire last,input wire valid,input wire ready);
wire old_ready,new_ready,old_valid,new_valid;
wire [{width-1}:0] old_payload,new_payload;
wire [1:0] old_count,new_count;
wire [{width-1}:0] old_head,old_tail,slot0,slot1;
wire read_slot,write_slot;
reg past_valid=0;
always @(posedge clk)past_valid<=1;
always @*if(!past_valid)assume(rst);
''']
    for module,instance in [('axis_skid_buffer','baseline'),('axis_pingpong_skid_buffer','candidate')]:
        old=instance=='baseline';prefix='old' if old else 'new'
        mapping=dict(clk='clk',rst='rst',s_axis_tdata='data',s_axis_tkeep='keep',s_axis_tvalid='valid',
            s_axis_tready=prefix+'_ready',s_axis_tlast='last',s_axis_tuser='user',m_axis_tvalid=prefix+'_valid',m_axis_tready='ready',
            m_axis_tdata=f'{prefix}_payload[0+:{data}]',m_axis_tkeep=f'{prefix}_payload[{data}+:{keep}]',
            m_axis_tlast=f'{prefix}_payload[{data+keep}]',m_axis_tuser=f'{prefix}_payload[{data+keep+1}+:{user}]',
            formal_count=prefix+'_count')
        if old:mapping.update(formal_head_payload='old_head',formal_tail_payload='old_tail')
        else:mapping.update(formal_slot0_payload='slot0',formal_slot1_payload='slot1',formal_read_slot='read_slot',formal_write_slot='write_slot')
        lines += [f'{module} #(.DATA_WIDTH({data}),.KEEP_WIDTH({keep}),.USER_WIDTH({user})) {instance}(',
            ',\n'.join(f'.{n}({v})' for n,v in mapping.items()),');']
    lines += ['''always @*if(past_valid)begin
    assert(old_count<=2);assert(new_count<=2);assert(old_count==new_count);
    assert(write_slot==(read_slot^(new_count==1)));
    assert(old_ready==new_ready);assert(old_valid==new_valid);
    if(old_count!=0)begin
        assert(old_head==(read_slot?slot1:slot0));
        assert(old_payload==new_payload);
    end
    if(old_count==2)assert(old_tail==(read_slot?slot0:slot1));
end
endmodule
`default_nettype wire
''']
    return '\n'.join(lines)


def cones(netlist):
    top=netlist['modules']['fifo_equivalence'];cells=top['cells'];drivers={}
    sequential=lambda cell:bool(re.match(r'^\$(?:s?dff|adff)',cell['type']))
    for name,cell in cells.items():
        for port,direction in cell['port_directions'].items():
            if direction=='output':
                for bit in cell['connections'][port]:
                    if isinstance(bit,int):assert bit not in drivers;drivers[bit]=(name,cell)
    ready=set(top['ports']['ready']['bits'])
    def reaches_ready(seeds):
        pending=list(seeds);visited=set()
        while pending:
            bit=pending.pop()
            if bit in visited:continue
            visited.add(bit)
            if bit in ready:return True
            if not isinstance(bit,int) or bit not in drivers:continue
            _,cell=drivers[bit]
            if sequential(cell):continue
            for port,direction in cell['port_directions'].items():
                if direction=='input':pending.extend(cell['connections'][port])
        return False
    result={}
    for signal in ('baseline.head_payload','candidate.slot0_payload','candidate.slot1_payload'):
        bits=set(top['netnames'][signal]['bits']);storage=[]
        for name,cell in cells.items():
            if sequential(cell) and bits.intersection(cell['connections'].get('Q',[])):
                seeds=[]
                for port,direction in cell['port_directions'].items():
                    if direction=='input' and port not in ('CLK',):seeds.extend(cell['connections'][port])
                storage.append(dict(cell=name,type=cell['type'],downstream_ready_in_next_state_cone=reaches_ready(seeds)))
        assert storage,signal
        result[signal]=storage
    assert any(c['downstream_ready_in_next_state_cone'] for c in result['baseline.head_payload'])
    assert all(not c['downstream_ready_in_next_state_cone'] for n,records in result.items() if n.startswith('candidate.') for c in records)
    return result


def main():
    import resource
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True)
    ap.add_argument('--candidate',choices=('frame-event-pingpong','payload-event-buffer'),default='frame-event-pingpong');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'build/experiments'/args.candidate;generation=read(source/'generation.json')
    assert all(sha(source/n)==h for n,h in generation['outputs_sha256'].items())
    approved=Path('/home/varrahan/development/hardware/parser');assert approved.is_dir()
    folder=approved/'build/frame-fifo-equivalence'/args.name;folder.mkdir(parents=True,exist_ok=False)
    archive=root/'build/wsl-reports'/args.name;assert not archive.exists()
    baseline=source/'rtl/axis_skid_buffer.v';candidate=source/'rtl/axis_pingpong_skid_buffer.v'
    wide='[DATA_WIDTH+KEEP_WIDTH+USER_WIDTH:0]'
    old=baseline.read_text();new=candidate.read_text()
    observed_old=observe(old,'axis_skid_buffer',[('[1:0]','count'),(wide,'head_payload'),(wide,'tail_payload')])
    observed_new=observe(new,'axis_pingpong_skid_buffer',[('[1:0]','count'),(wide,'slot0_payload'),(wide,'slot1_payload'),('','read_slot'),('','write_slot')])
    (folder/'baseline-original.v').write_bytes(baseline.read_bytes());(folder/'candidate-original.v').write_bytes(candidate.read_bytes())
    (folder/'baseline.v').write_text(observed_old);(folder/'candidate.v').write_text(observed_new)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    result=dict(phase='proving',started_utc=datetime.now(timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),
        parent_generation_sha256=sha(source/'generation.json'),baseline_sha256=sha(baseline),candidate_sha256=sha(candidate),
        witness_instrumentation_inverse_verified=True,reset_initially_required=True,arbitrary_later_resets=True,
        input_stability_assumptions=False,payload_comparison_only_when_valid=True,two_state_formal=True,
        yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip(),proofs=[],passed=False,
        full_framing_corpus_verified=False,full_protocol_verified=False,native_timing_verified=False,full_system_complete=False)
    def save():(folder/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        configurations=((147,1,16),) if args.candidate=='payload-event-buffer' else ((1,1,1),(8,1,16),(114,1,16),(128,16,16),(512,64,16))
        for data,keep,user in configurations:
            name=f'd{data}_k{keep}_u{user}';target=folder/name;target.mkdir()
            for source_name in ('baseline.v','candidate.v'):shutil.copy2(folder/source_name,target/source_name)
            (target/'miter.sv').write_text(miter(data,keep,user))
            script='''read_verilog -formal -sv baseline.v candidate.v miter.sv
prep -top fifo_equivalence -flatten
memory_map
opt
write_json netlist.json
sat -verify -prove-asserts -set-assumes -seq 2 -tempinduct -tempinduct-def -set-init-def -set-def-inputs -maxsteps 6 -timeout 30 -show-ports -dump_vcd counterexample.vcd
'''
            (target/'proof.ys').write_text(script)
            with (target/'stdout.log').open('w') as output:
                code=subprocess.call(['yosys','-Q','-T','-l','proof.log','-s','proof.ys'],cwd=target,stdout=output,stderr=subprocess.STDOUT)
            text=(target/'proof.log').read_text()
            assert code==0 and 'Induction step proven: SUCCESS!' in text,(name,code,'Inspect the retained formal trace')
            cone=cones(read(target/'netlist.json'))
            result['proofs'].append(dict(data_width=data,keep_width=keep,user_width=user,
                unbounded_induction_passed=True,payload_register_cones=cone,
                inputs_sha256={n:sha(target/n) for n in ('baseline.v','candidate.v','miter.sv','proof.ys')},
                proof_log_sha256=sha(target/'proof.log'),netlist_sha256=sha(target/'netlist.json')))
            save()
        result.update(phase='frame_fifo_unbounded_equivalence_and_payload_cones_verified',passed=True)
    except BaseException as error:result.update(phase='failed',error=str(error));raise
    finally:
        result['finished_utc']=datetime.now(timezone.utc).isoformat();save()
        archive.mkdir(parents=True,exist_ok=False);shutil.copytree(folder,archive,dirs_exist_ok=True)
    print(json.dumps(dict(phase=result['phase'],passed=result['passed'],configurations=len(result['proofs']))))


if __name__=='__main__':main()
