"""Prove the new quiet certificate cannot assert idle before the actual owner."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess

from generate_hyperram_cdc_timing_harness import ports
from run_frame_fifo_equivalence_wsl import observe
from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--assembly')
    ap.add_argument('--candidate',choices=('frame-owned-quiet','open-rpc-reclaim'),default='frame-owned-quiet')
    ap.add_argument('--progress',action='store_true');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    if args.assembly:assert re.fullmatch(r'[A-Za-z0-9_-]+',args.assembly)
    if args.assembly:assert args.candidate=='frame-owned-quiet'
    candidate=root/'build/experiments'/(args.assembly or args.candidate);generation=read(candidate/'generation.json')
    assert all(sha(candidate/n)==h for n,h in generation['outputs_sha256'].items())
    parser_source=candidate/'joint' if args.assembly else candidate
    if args.assembly:assert generation['owned_quiet']
    approved=Path('/home/varrahan/development/hardware/parser');assert approved.is_dir()
    folder=approved/'build/frame-owned-quiet-formal'/args.name;folder.mkdir(parents=True,exist_ok=False)
    archive=root/'build/wsl-reports'/args.name;assert not archive.exists()
    dependencies=closure('http2_enveloped_frame_grants',parser_source);assert len(dependencies)==7
    (folder/'rtl').mkdir()
    for path in dependencies.values():shutil.copy2(path,folder/'rtl'/path.name)
    target=folder/'rtl/http2_enveloped_frame_grants.v';original=target.read_text()
    reference_generation=read(root/'build/experiments/frame-owned-quiet/generation.json') if args.candidate=='open-rpc-reclaim' else generation
    before=reference_generation['owned_quiet_source_edit_certificate' if args.assembly else 'source_edit_certificate']['old'];rhs=before.removeprefix('assign idle=').removesuffix(';')
    declaration='wire reference_idle='+rhs+';\n'
    extended=original.replace('endmodule',declaration+'endmodule');assert extended.replace(declaration,'')==original
    augmented=observe(extended,'http2_enveloped_frame_grants',[('','reference_idle'),('','owned_quiet'),('','owned_idle'),('','quiet_inputs')])
    target.write_text(augmented)
    interface=[p for p in ports(original,'http2_enveloped_frame_grants') if p[0]=='input']
    lines=['`default_nettype none','module quiet_certificate_miter #(',
        'parameter integer USER_WIDTH=16,MEMORY_ADDR_WIDTH=23',')(',
        ',\n'.join(f'input wire {w} {n}' for _,w,n in interface)+(',\noutput wire settled_quiet_cover' if args.progress else ''),');',
        'wire candidate_idle,reference_idle,owned_quiet,owned_idle,quiet_inputs;',
        'reg past_valid=0;always @(posedge clk)past_valid<=1;',
        'always @*if(!past_valid)assume(rst);',
        'http2_enveloped_frame_grants #(.ENABLE_WINDOW_FORMAT(1),.ENABLE_LOCAL_FATAL(1),.ENABLE_RECEIVE_POOL(1),.ENABLE_CONTEXT_GUARD(1),.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)) dut(',
        ',\n'.join([f'.{n}({n})' for _,_,n in interface]+['.idle(candidate_idle)',
            '.formal_reference_idle(reference_idle)','.formal_owned_quiet(owned_quiet)',
            '.formal_owned_idle(owned_idle)','.formal_quiet_inputs(quiet_inputs)']),');',
        'always @*if(past_valid)begin',
        'assert(!candidate_idle||reference_idle);',
        'assert(!(owned_quiet&&quiet_inputs)||owned_idle);',
        'end','endmodule','`default_nettype wire','']
    if args.progress:
        position=lines.index('endmodule')
        lines[position:position]=[
            'reg previous_quiet=0;',
            'always @(posedge clk)if(rst)previous_quiet<=0;else previous_quiet<=reference_idle&&quiet_inputs;',
            'assign settled_quiet_cover=past_valid&&!rst&&previous_quiet&&reference_idle&&quiet_inputs&&candidate_idle;',
            'always @*if(past_valid&&!rst&&previous_quiet&&reference_idle&&quiet_inputs)assert(candidate_idle);']
    (folder/'miter.sv').write_text('\n'.join(lines))
    script='''read_verilog -formal -sv rtl/*.v miter.sv
prep -top quiet_certificate_miter -flatten
memory_map
opt
write_json netlist.json
sat -verify -prove-asserts -set-assumes -seq 2 -tempinduct -tempinduct-def -set-init-def -set-def-inputs -maxsteps 6 -timeout 45 -show-ports -dump_vcd counterexample.vcd
'''
    if args.progress:
        script+='sat -set-assumes -seq 4 -set-init-def -set-def-inputs -set-at 1 rst 1 -set-at 2 rst 0 -set-at 3 rst 0 -set-at 4 rst 0 -set-at 4 settled_quiet_cover 1 -show-ports -dump_vcd quiet_cover.vcd\n'
    (folder/'proof.ys').write_text(script)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    shutil.copy2(root/'tools/run_frame_fifo_equivalence_wsl.py',folder/'run_frame_fifo_equivalence_wsl.py')
    result=dict(phase='proving',started_utc=datetime.now(timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),
        generation_sha256=sha(candidate/'generation.json'),original_top_sha256=hashlib.sha256(original.encode()).hexdigest(),
        native_assembly=args.assembly,
        candidate_variant=args.candidate,reference_generation_sha256=sha(root/'build/experiments/frame-owned-quiet/generation.json') if args.candidate=='open-rpc-reclaim' else sha(candidate/'generation.json'),
        bounded_quiet_progress_requested=args.progress,
        witness_instrumentation_inverse_verified=True,reference_idle_expression=rhs,exact_owner_modules=7,
        complete_production_owner_subtree=True,memory_model_substitution=False,two_state_formal=True,
        initial_reset_required=True,arbitrary_later_resets=True,input_stability_assumptions=False,
        yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip(),passed=False,
        full_protocol_verified=False,native_timing_verified=False,full_system_complete=False,
        inputs_sha256={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file()})
    def save():(folder/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        with (folder/'stdout.log').open('w') as output:
            code=subprocess.call(['yosys','-Q','-T','-l','proof.log','-s','proof.ys'],cwd=folder,stdout=output,stderr=subprocess.STDOUT)
        log=(folder/'proof.log').read_text()
        assert code==0 and 'Induction step proven: SUCCESS!' in log,(code,'Actual owner proof failed; inspect preserved counterexample')
        if args.progress:
            assert 'SAT solving finished - model found:' in log
            assert (folder/'quiet_cover.vcd').is_file() and (folder/'quiet_cover.vcd').stat().st_size>0
        result.update(phase='frame_owned_quiet_safety_and_bounded_progress_induction_verified' if args.progress else 'frame_owned_quiet_conservative_idle_induction_verified',passed=True,
            proof_log_sha256=sha(folder/'proof.log'),netlist_sha256=sha(folder/'netlist.json'))
        if args.progress:
            result.update(bounded_quiet_progress_verified=True,maximum_extra_idle_cycles_after_stable_quiet=1,
                nonvacuity_quiet_cover_reached=True,quiet_cover_sha256=sha(folder/'quiet_cover.vcd'),
                full_application_liveness_verified=False)
    except BaseException as error:result.update(phase='failed',error=str(error));raise
    finally:
        result['finished_utc']=datetime.now(timezone.utc).isoformat();save()
        archive.mkdir(parents=True,exist_ok=False);shutil.copytree(folder,archive,dirs_exist_ok=True)
    print(json.dumps({k:result[k] for k in ('phase','passed','exact_owner_modules')}))


if __name__=='__main__':main()
