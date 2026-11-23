"""Replay the original semantic transport corpus and memory faults on both RTLs."""
import argparse
from datetime import datetime, timezone
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
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+', args.name)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text())
    original = root / 'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    parent = root / 'build/experiments/frame-owned-quiet'
    candidate = root / 'build/experiments/payload-event-buffer'
    generation = read(candidate / 'generation.json')
    assert all(sha(candidate / n) == h for n, h in generation['outputs_sha256'].items())
    prior_fifo = read(root / 'build/validation/frame-event-pingpong.json')
    assert prior_fifo['key'] == '806c3d55fa92d7b8'
    assert sha(candidate / 'rtl/axis_pingpong_skid_buffer.v') == prior_fifo['executed_parser_sha256']['axis_pingpong_skid_buffer']
    approved = Path('/home/varrahan/development/hardware/parser')
    assert approved.is_dir()
    folder = approved / 'build/payload-event-buffer-units' / args.name
    folder.mkdir(parents=True, exist_ok=False)
    archive = root / 'build/wsl-reports' / args.name
    assert not archive.exists()
    reference = folder / 'reference'
    reference.mkdir()
    for name in ('generate_http2_transport_vectors.py', 'generate_http2_frame_vectors.py'):
        shutil.copy2(root / 'tools' / name, reference / name)
    shutil.copytree(original / 'native-vendor', reference / 'native-vendor', ignore=shutil.ignore_patterns('__pycache__'))
    with (reference / 'generate.log').open('w') as out:
        code = subprocess.call([sys.executable, str(reference / 'generate_http2_transport_vectors.py'),
            '--output', str(reference)], env=dict(os.environ, PYTHONPATH=str(reference / 'native-vendor')),
            stdout=out, stderr=subprocess.STDOUT)
    assert code == 0
    original_tb = (root / 'sim/tb_http2_connections.sv').read_bytes().decode()
    edits = [
        ('always @(negedge clk)event_ready=$urandom_range(0,3)!=0;',
         'integer ready_cycle=0;always @(negedge clk)begin ready_cycle++;event_ready=ready_cycle%83>=61;end'),
        ('    task acknowledge;', '''`ifdef PAYLOAD_BUFFER_CANDIDATE
    integer payload_full_cycles=0,payload_fence_cycles=0;
    always @(posedge clk)if(!rst)begin
        if(semantic_path.dut.payload.semantic_event_buffer.count==2)payload_full_cycles++;
        if(semantic_path.dut.payload.state==6&&!semantic_path.dut.payload.event_buffer_empty)payload_fence_cycles++;
        if(semantic_path.dut.payload.result_valid)assert(semantic_path.dut.payload.event_buffer_empty)
            else $fatal(1,"Semantic result escaped buffered events");
        if(!semantic_path.dut.payload.event_buffer_empty)assert(!semantic_path.dut.payload.start_ready&&!semantic_path.dut.payload.idle)
            else $fatal(1,"Semantic buffered ownership omitted from start/idle");
    end
`endif
    task acknowledge;'''),
        ('$finish;', '''
`ifdef PAYLOAD_BUFFER_CANDIDATE
        assert(payload_full_cycles>100&&payload_fence_cycles>0)else $fatal(1,"Semantic buffer coverage missing");
        $display("PAYLOAD_EVENT_COVERAGE full_cycles=%0d fence_cycles=%0d",payload_full_cycles,payload_fence_cycles);
`endif
        $finish;''')]
    tb = original_tb
    for old, new in edits:
        assert tb.count(old) == 1
        tb = tb.replace(old, new)
    inverse = tb
    for old, new in reversed(edits):
        assert inverse.count(new) == 1
        inverse = inverse.replace(new, old)
    assert inverse == original_tb
    (folder / 'tb_http2_connections.sv').write_bytes(tb.encode())
    shutil.copy2(root / 'sim/tb_http2_transport.sv', folder / 'tb_http2_transport.sv')
    shutil.copy2(root / 'sim/axi_external_memory_model.sv', folder / 'axi_external_memory_model.sv')
    shutil.copy2(Path(__file__), folder / Path(__file__).name)
    shutil.copy2(candidate / 'generation.json', folder / 'candidate-generation.json')
    result = dict(phase='running', started_utc=datetime.now(timezone.utc).isoformat(),
        driver_sha256=sha(Path(__file__)), generation_sha256=sha(candidate / 'generation.json'),
        reference_sha256={p.name: sha(p) for p in reference.iterdir() if p.is_file()},
        testbench_edits=edits, original_testbench_sha256=hashlib.sha256(original_tb.encode()).hexdigest(),
        exact_testbench_inverse_verified=True, revisions={},
        portable_memory_backend=True, native_vendor_memory=False,
        full_application_corpus_verified=False, native_timing_verified=False, full_system_complete=False)
    def save():
        (folder / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    save()
    try:
        for revision, source in (('baseline', parent), ('candidate', candidate)):
            run = folder / revision
            design = run / 'design'
            shutil.copytree(original / 'rtl', design / 'rtl', ignore=shutil.ignore_patterns('__pycache__'))
            for path in (source / 'rtl').glob('*.v'):
                shutil.copy2(path, design / 'rtl' / path.name)
            modules = closure('http2_transport_ingress', design)
            modules.update(closure('external_memory_fabric', design))
            rtl = run / 'rtl'
            rtl.mkdir()
            for path in set(modules.values()):
                shutil.copy2(path, rtl / path.name)
            for filename in ('tb_http2_connections.sv', 'tb_http2_transport.sv', 'axi_external_memory_model.sv'):
                shutil.copy2(folder / filename, run / filename)
            shutil.copy2(reference / 'vectors.txt', run / 'vectors.txt')
            commands = [['iverilog', '-g2012', '-DPARSER_PORTABLE_SIM=1', '-s', 'tb_http2_transport', '-o', 'simulation.vvp'] +
                (['-DPAYLOAD_BUFFER_CANDIDATE'] if revision == 'candidate' else []) +
                [str(p) for p in sorted(rtl.glob('*.v'))] +
                ['axi_external_memory_model.sv', 'tb_http2_connections.sv', 'tb_http2_transport.sv'], ['vvp', 'simulation.vvp']]
            state = dict(phase='building', commands=commands,
                inputs_sha256={p.relative_to(run).as_posix(): sha(p) for p in run.rglob('*') if p.is_file() and 'design' not in p.relative_to(run).parts})
            result['revisions'][revision] = state
            save()
            for label, command in zip(('compile', 'simulate'), commands):
                with (run / (label + '.log')).open('w') as out:
                    code = subprocess.call(command, cwd=run, stdout=out, stderr=subprocess.STDOUT)
                text = (run / (label + '.log')).read_text(errors='replace')
                assert code == 0 and not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):', text, re.M), (revision, label)
            text = (run / 'simulate.log').read_text()
            summary = re.search(r'PASS: external HTTP/2 ingress semantic=1: (\d+) packets/(\d+) exact events/(\d+) protocol failures/(\d+) controls/(\d+) injected memory phases;', text)
            assert summary
            state.update(phase='passed', summary=list(map(int, summary.groups())),
                simulation_log_sha256=sha(run / 'simulate.log'))
            if revision == 'candidate':
                coverage = re.search(r'PAYLOAD_EVENT_COVERAGE full_cycles=(\d+) fence_cycles=(\d+)', text)
                assert coverage
                state.update(buffer_full_cycles=int(coverage[1]), completion_fence_cycles=int(coverage[2]))
            save()
        assert result['revisions']['baseline']['summary'] == result['revisions']['candidate']['summary']
        result.update(phase='payload_event_buffer_semantic_transport_corpus_verified', passed=True)
    except BaseException as error:
        result.update(phase='failed', passed=False, error=str(error))
        raise
    finally:
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
        archive.mkdir(parents=True, exist_ok=False)
        shutil.copytree(folder, archive, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('simulation.vvp', '__pycache__', 'design'))
    print(json.dumps({k: result[k] for k in ('phase', 'passed', 'portable_memory_backend')}))


if __name__ == '__main__':
    main()
