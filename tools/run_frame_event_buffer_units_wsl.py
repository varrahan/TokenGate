"""Compare original and buffered framing on the unchanged native h2 corpus."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys

from verify_two_fpga_application import closure


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True)
    ap.add_argument('--candidate',choices=('frame-event-buffer','frame-event-pingpong'),default='frame-event-buffer');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    candidate=root/'build/experiments'/args.candidate
    generation=json.loads((candidate/'generation.json').read_text())
    assert all(sha(candidate/n)==h for n,h in generation['outputs_sha256'].items())
    approved=Path('/home/varrahan/development/hardware/parser');assert approved.is_dir()
    folder=approved/'build/frame-event-buffer-units'/args.name;folder.mkdir(parents=True,exist_ok=False)
    archive=root/'build/wsl-reports'/args.name;assert not archive.exists()
    reference=folder/'reference';reference.mkdir()
    shutil.copy2(root/'tools/generate_http2_frame_vectors.py',reference/'generate.py')
    shutil.copytree(original/'native-vendor',reference/'native-vendor',ignore=shutil.ignore_patterns('__pycache__'))
    env=dict(os.environ,PYTHONPATH=str(reference/'native-vendor'))
    with (reference/'generation.log').open('w') as out:
        code=subprocess.call([sys.executable,str(reference/'generate.py'),'--output',str(reference)],env=env,stdout=out,stderr=subprocess.STDOUT)
    assert code==0
    tb=(root/'sim/tb_http2_frames.sv').read_text()
    tb=tb.replace('always @(negedge clk)event_ready=$urandom_range(0,3)!=0;',
        'integer ready_cycle=0;always @(negedge clk)begin ready_cycle++;event_ready=ready_cycle%71>=43;end')
    assert 'ready_cycle%71>=43' in tb
    where='    task beat('
    assert tb.count(where)==1
    tb=tb.replace(where,'''`ifdef BUFFER_CANDIDATE
    integer buffer_full_cycles=0,completion_fence_cycles=0;
    always @(posedge clk)if(!rst)begin
        if(dut.event_buffer.count==2)buffer_full_cycles++;
        if(dut.reader_completion_valid&&!dut.event_buffer_empty)completion_fence_cycles++;
        if(completion_valid)assert(dut.event_buffer_empty)else $fatal(1,"Completion escaped buffered events");
        if(!dut.event_buffer_empty)assert(!start_ready&&!idle)else $fatal(1,"Buffered ownership omitted from idle/start");
    end
`endif
    task beat(''')
    assert tb.count('$finish;')==1
    tb=tb.replace('$finish;','''
`ifdef BUFFER_CANDIDATE
        assert(buffer_full_cycles>100&&completion_fence_cycles>0)else $fatal(1,"Event buffer/drain fence not exercised");
        $display("EVENT_BUFFER_COVERAGE full_cycles=%0d completion_fence_cycles=%0d",buffer_full_cycles,completion_fence_cycles);
`endif
        $finish;''')
    (folder/'tb_http2_frames.sv').write_text(tb)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    shutil.copy2(candidate/'generation.json',folder/'candidate-generation.json')
    result=dict(phase='building',started_utc=datetime.now(timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),
        generator_sha256=sha(reference/'generate.py'),vectors_sha256=sha(reference/'vectors.txt'),testbench_sha256=sha(folder/'tb_http2_frames.sv'),
        generation_sha256=sha(candidate/'generation.json'),candidate_variant=args.candidate,
        exact_parser_modules=generation['exact_parser_modules'],revisions={},no_memory_model_substitution=True,
        native_vendor_memory_needed=False,full_protocol_verified=False,native_timing_verified=False,full_system_complete=False)
    def save(): (folder/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        for revision,source in (('baseline',original),('candidate',candidate)):
            run=folder/revision;run.mkdir();rtl=run/'rtl';rtl.mkdir()
            modules=closure('http2_axis_ingress',source)
            assert len(modules)==(3 if revision=='baseline' else 4)
            for name,path in modules.items():shutil.copy2(path,rtl/path.name)
            shutil.copy2(reference/'vectors.txt',run/'vectors.txt')
            shutil.copy2(folder/'tb_http2_frames.sv',run/'tb_http2_frames.sv')
            commands=[['iverilog','-g2012','-s','tb_http2_frames','-o','simulation.vvp']+
                (['-DBUFFER_CANDIDATE'] if revision=='candidate' else [])+
                [str(path) for path in sorted(rtl.glob('*.v'))]+['tb_http2_frames.sv'],['vvp','simulation.vvp']]
            state=dict(phase='building',commands=commands,inputs_sha256={p.name:sha(p) for p in rtl.glob('*.v')},passed=False)
            result['revisions'][revision]=state;save()
            for label,command in zip(('compile','simulate'),commands):
                with (run/(label+'.log')).open('w') as stream:code=subprocess.call(command,cwd=run,stdout=stream,stderr=subprocess.STDOUT)
                text=(run/(label+'.log')).read_text(errors='replace')
                assert code==0 and not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),(revision,label)
            text=(run/'simulate.log').read_text()
            summary=re.search(r'PASS: HTTP/2 512-bit ingress: (\d+) fragments/(\d+) wire bytes/(\d+) exact events \((\d+) headers/(\d+) body/(\d+) ends/(\d+) stream errors\), (\d+) failed fragments',text)
            assert summary,(revision,'No frame acceptance marker')
            state.update(phase='passed',passed=True,summary=list(map(int,summary.groups())),simulation_log_sha256=sha(run/'simulate.log'))
            if revision=='candidate':
                coverage=re.search(r'EVENT_BUFFER_COVERAGE full_cycles=(\d+) completion_fence_cycles=(\d+)',text);assert coverage
                state.update(buffer_full_cycles=int(coverage[1]),completion_fence_cycles=int(coverage[2]))
            save()
        assert result['revisions']['baseline']['summary']==result['revisions']['candidate']['summary']
        result.update(phase=('frame_event_buffer_full_framing_corpus_verified' if args.candidate=='frame-event-buffer'
            else 'frame_event_pingpong_full_framing_corpus_verified'),passed=True)
    except BaseException as error:result.update(phase='failed',passed=False,error=str(error));raise
    finally:
        result['finished_utc']=datetime.now(timezone.utc).isoformat();save()
        archive.mkdir(parents=True,exist_ok=False)
        shutil.copytree(folder,archive,dirs_exist_ok=True,ignore=shutil.ignore_patterns('simulation.vvp','__pycache__'))
    print(json.dumps({k:result[k] for k in ('phase','passed','no_memory_model_substitution')}))


if __name__=='__main__':main()
