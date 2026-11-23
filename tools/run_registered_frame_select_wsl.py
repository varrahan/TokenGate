"""Frozen original frame corpus plus actual-RTL safety and READY cone proofs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def miter(source):
    interface=ports(source,'axis_frame_arbiter')
    lines=['`default_nettype none','module proof_top #(parameter DATA_WIDTH=512,KEEP_WIDTH=64,USER_WIDTH=16)(',
        ',\n'.join(f'input wire {w} {n}'for d,w,n in interface if d=='input'),');']
    lines +=[f'wire {w} {n};'for d,w,n in interface if d=='output']
    lines+=['wire locked,owner,prefer_b;',
        'axis_frame_arbiter #(.DATA_WIDTH(DATA_WIDTH),.KEEP_WIDTH(KEEP_WIDTH),.USER_WIDTH(USER_WIDTH)) dut(',
        ',\n'.join(f'.{n}({n})'for d,w,n in interface)+',.formal_locked(locked),.formal_owner(owner),.formal_prefer_b(prefer_b));',
        '''localparam P=DATA_WIDTH+KEEP_WIDTH+USER_WIDTH+1;
wire [P-1:0] ap={a_axis_tdata,a_axis_tkeep,a_axis_tlast,a_axis_tuser};
wire [P-1:0] bp={b_axis_tdata,b_axis_tkeep,b_axis_tlast,b_axis_tuser};
wire [P-1:0] mp={m_axis_tdata,m_axis_tkeep,m_axis_tlast,m_axis_tuser};
wire af=a_axis_tvalid&&a_axis_tready,bf=b_axis_tvalid&&b_axis_tready;
wire mf=m_axis_tvalid&&m_axis_tready;
reg past_valid=0;
reg pr,pa,pb,par,pbr,pm,pmr,pml,pl,po,pp;
reg [P-1:0] pap,pbp,pmp;
always @(posedge clk)begin
    past_valid<=1;pr<=rst;pa<=a_axis_tvalid;pb<=b_axis_tvalid;par<=a_axis_tready;pbr<=b_axis_tready;
    pm<=m_axis_tvalid;pmr<=m_axis_tready;pml<=m_axis_tlast;pl<=locked;po<=owner;pp<=prefer_b;
    pap<=ap;pbp<=bp;pmp<=mp;
end
always @*begin
    if(!past_valid)assume(rst);
    if(past_valid&&!rst&&!pr)begin
        if(pa&&!par)begin assume(a_axis_tvalid);assume(ap==pap);end
        if(pb&&!pbr)begin assume(b_axis_tvalid);assume(bp==pbp);end
    end
    if(past_valid)begin
        assert(!(af&&bf));assert(mf==(af||bf));
        if(rst)assert(!m_axis_tvalid&&!a_axis_tready&&!b_axis_tready);
        if(!locked)assert(!m_axis_tvalid&&!a_axis_tready&&!b_axis_tready);
        if(m_axis_tvalid)begin
            assert(locked);
            if(owner)begin assert(b_axis_tvalid);assert(mp==bp);assert(!a_axis_tready);end
            else begin assert(a_axis_tvalid);assert(mp==ap);assert(!b_axis_tready);end
        end
        assert(idle==(!locked&&!a_axis_tvalid&&!b_axis_tvalid));
        if(!rst&&!pr)begin
            if(pm&&!pmr)begin assert(m_axis_tvalid);assert(mp==pmp);end
            if(pl&&!(pm&&pmr&&pml))begin assert(locked);assert(owner==po);end
            if(!pl&&(pa||pb))begin assert(locked);assert(owner==(pa&&pb?pp:pb));assert(m_axis_tvalid);end
            if(pm&&pmr&&pml)begin assert(!locked);assert(prefer_b==!po);end
        end
    end
end
endmodule
`default_nettype wire
''']
    return '\n'.join(lines)


def ready_cones(netlist):
    top=netlist['modules']['proof_top'];drivers={}
    for name,c in top['cells'].items():
        for p,d in c['port_directions'].items():
            if d=='output':
                for bit in c['connections'][p]:
                    if isinstance(bit,int):assert bit not in drivers;drivers[bit]=c
    forbidden=set(top['ports']['a_axis_tvalid']['bits']+top['ports']['b_axis_tvalid']['bits'])
    result={}
    for name in('a_axis_tready','b_axis_tready'):
        pending=list(top['netnames'][name]['bits']);visited=set();registers=[]
        while pending:
            bit=pending.pop()
            if bit in visited:continue
            visited.add(bit)
            if bit not in drivers:continue
            c=drivers[bit]
            if re.match(r'^\$(?:s?dff|adff)',c['type']):
                registers.append(c['type']);continue
            assert c['type']not in('$anyseq','$anyconst')
            for port,direction in c['port_directions'].items():
                if direction=='input':pending.extend(c['connections'][port])
        assert not visited.intersection(forbidden)and registers
        result[name]=dict(no_input_valid_in_combinational_cone=True,register_boundaries=registers,visited_bits=len(visited))
    return result


def proof_script(induct,data,keep,user):
    return ('read_verilog -formal -sv observed.v miter.sv\n'+
        f'hierarchy -top proof_top -chparam DATA_WIDTH {data} -chparam KEEP_WIDTH {keep} -chparam USER_WIDTH {user}\n'+
        'prep -top proof_top -flatten\nmemory_map\nopt\nwrite_json netlist.json\n'+
        'sat -verify -prove-asserts -set-assumes -seq 2 -set-init-def -set-def-inputs -set-def-formal -timeout 90'+
        (' -tempinduct -maxsteps 8'if induct else'')+'\n')


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    source=root/'build/experiments/rpc-registered-frame-select-v1';generation=read(source/'generation.json')
    assert all(sha(source/n)==h for n,h in generation['outputs_sha256'].items())
    approved=Path.home()/'development/hardware/parser';assert approved.is_dir()
    target=approved/'build/axis-frame-arbiter-tests'/args.name;target.mkdir(parents=True,exist_ok=False)
    archive=root/'build/wsl-reports'/('registered_frame_select_'+args.name);assert not archive.exists()
    parent=root/'build/wsl-reports/axis_frame_arbiter_actual_wire_frame_arbiter_fairness';original=read(parent/'inputs.json')
    for n,h in original.items():
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True);assert sha(parent/'execution-sources'/n)==h
        shutil.copy2(parent/'execution-sources'/n,p)
    inputs=dict(original);name='rtl/axis_frame_arbiter.v'
    shutil.copy2(source/'joint'/name,target/name);inputs[name]=sha(target/name)
    test='sim/cocotb/test_axis_frame_arbiter.py';raw=(target/test).read_bytes().decode()
    replacements=[('    for index in range(32):\n','    selection_wait_cycles=0\n    for index in range(32):\n'),
        ("        assert int(d.a_axis_tready.value)and int(d.m_axis_tvalid.value)and int(d.m_axis_tdata.value)==index",
         "        if index==0:\n            while not int(d.a_axis_tready.value):\n                selection_wait_cycles+=1\n                await FallingEdge(d.clk);await RisingEdge(d.clk)\n        assert int(d.a_axis_tready.value)and int(d.m_axis_tvalid.value)and int(d.m_axis_tdata.value)==index"),
        ('    accepted=dict(phase=\'passed\',native_frames=160,',
         '    assert selection_wait_cycles==1\n    accepted=dict(phase=\'passed\',selection_wait_cycles=selection_wait_cycles,native_frames=160,')]
    if '\r\n'in raw:replacements=[(a.replace('\n','\r\n'),b.replace('\n','\r\n'))for a,b in replacements]
    updated=raw
    for a,b in replacements:assert updated.count(a)==1;updated=updated.replace(a,b)
    inverse=updated
    for a,b in reversed(replacements):assert inverse.count(b)==1;inverse=inverse.replace(b,a)
    assert inverse==raw;(target/test).write_bytes(updated.encode());inputs[test]=sha(target/test)
    (target/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    record=dict(phase='testing',started_utc=datetime.now(timezone.utc).isoformat(),generation_sha256=sha(source/'generation.json'),
        inputs_sha256=inputs,original_inputs_sha256=original,fixture_edits=replacements,
        original_160_native_frames_and_assertions_retained=True,initial_selection_latency_explicit=True,
        actual_wire_ack_required=True,passed=False,proofs=[],full_application_runtime_verified=False,
        native_timing_verified=False,full_system_complete=False)
    def save():(target/'qualification.json').write_text(json.dumps(record,indent=2)+'\n')
    save()
    try:
        with(target/'unit-driver.log').open('w')as stream:
            code=subprocess.call([sys.executable,str(target/'scripts/run_http2_send_windows.py'),'--execute','--frame-arbiter'],
                cwd=target,stdout=stream,stderr=subprocess.STDOUT)
        assert code==0,('Original frame corpus failed',code)
        accepted=read(target/'build/test/acceptance.json');assert accepted['output_frames']==160 and accepted['sustained_beats']==32
        record['unit_accepted']=accepted;record['phase']='proving';save()
        formal=target/'formal';formal.mkdir();production=(target/'rtl/axis_frame_arbiter.v').read_text()
        observed=observe(production,'axis_frame_arbiter',[('','locked'),('','owner'),('','prefer_b')])
        for data,keep,user in((1,1,1),(512,64,16)):
            slot=formal/f'd{data}_k{keep}_u{user}';slot.mkdir()
            (slot/'observed.v').write_text(observed);(slot/'miter.sv').write_text(miter(production))
            for label,induct in(('reset-base',False),('induction',True)):
                (slot/(label+'.ys')).write_text(proof_script(induct,data,keep,user))
                with(slot/(label+'-stdout.log')).open('w')as stream:
                    code=subprocess.call(['yosys','-Q','-T','-l',label+'.log','-s',label+'.ys'],cwd=slot,stdout=stream,stderr=subprocess.STDOUT)
                log=(slot/(label+'.log')).read_text();assert code==0 and not re.search(r'^ERROR:',log,re.M),(data,label,code)
                assert ('Induction step proven: SUCCESS!'if induct else'SAT proof finished - no model found: SUCCESS!')in log
            cone=ready_cones(read(slot/'netlist.json'))
            record['proofs'].append(dict(data_width=data,keep_width=keep,user_width=user,
                actual_reset_base_verified=True,unbounded_safety_induction_verified=True,ready_cones=cone));save()
        assert all(sha(target/n)==h for n,h in inputs.items())
        record.update(phase='registered_frame_selection_corpus_and_formal_safety_passed',passed=True)
    except BaseException as error:record.update(phase='failed',error=str(error));raise
    finally:
        record['finished_utc']=datetime.now(timezone.utc).isoformat();save()
        shutil.copytree(target,archive,ignore=shutil.ignore_patterns('*.vvp','__pycache__'))
    print(json.dumps(dict(phase=record['phase'],passed=record['passed'],formal_configurations=len(record['proofs']))))


if __name__=='__main__':main()
