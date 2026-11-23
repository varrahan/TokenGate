"""Actual RPC/inverse/owned windows over a five-client production fabric."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

from generate_bidirectional_application import ports
from generate_rpc_durable_return import once
from generate_two_fpga_application import MEMORY, instance, named_instance


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--keyed',action='store_true')
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    return_top='rpc_grpc_keyed_return'if args.keyed else'rpc_grpc_durable_return'
    harness_top='cocotb_rpc_keyed_top'if args.keyed else'cocotb_rpc_durable_top'
    base = root / 'build/rpc-durable-base-harness.sv'
    subprocess.run([sys.executable, str(root / 'tools/generate_cocotb_rpc_leased_harness.py'), '--output', str(base)], check=True)
    source = base.read_text().replace('module cocotb_rpc_leased_top;', f'module {harness_top};')
    start, end, parameters, connections = instance(source, 'rpc_grpc_leased_return', 'dut')
    old = ports((root / 'rtl/rpc_grpc_leased_return.v').read_text(), 'rpc_grpc_leased_return')
    new = ports((root / f'rtl/{return_top}.v').read_text(), return_top)
    original_names = {n for _, _, n in old}; new_names = {n for _, _, n in new}
    connections = {n: value for n, value in connections.items() if n in new_names}
    extra = []
    for d, w, n in new:
        if n in original_names: continue
        connections[n] = n
        extra.append(f"{'reg' if d=='input' else 'wire'} {w} {n}{'=0' if d=='input' else ''};")
    source = source[:start] + '\n'.join(extra) + '\n' + named_instance(return_top, parameters, 'dut', connections) + source[end:]
    for _, w, n in new:
        if n in MEMORY:
            source, count = re.subn(r'wire\s+(?:\[[^\]]+\]\s*)?' + n + r'\s*;', f'wire {w} {n};', source)
            assert count == 1, n
    # Old external credit drivers become passive hierarchical monitors.
    for n in ('frame_req_ready', 'frame_grant_bytes'):
        source, count = re.subn(r'reg\s+(\[[^\]]+\]\s*)?' + n + r'=0;', lambda m: f'wire {m[1] or ""}{n};', source)
        assert count == 1, n
    monitor = '\n'.join(f'assign {n}=dut.{n};' for n in ('frame_req_valid', 'frame_req_ready', 'frame_req_user',
        'frame_req_stream', 'frame_req_max_bytes', 'frame_grant_bytes'))
    source = once(source, 'assign directory_valid=dut.directory_valid;', monitor + '\nassign directory_valid=dut.directory_valid;')
    replacements = {
        'wire [3:0] all_valid,all_ready,all_write,all_rsp_valid,all_rsp_ready;': 'wire [4:0] all_valid,all_ready,all_write,all_rsp_valid,all_rsp_ready;',
        'wire [91:0] all_addr;wire [15:0] all_bytes;wire [287:0] all_data,normal_rsp_data;': 'wire [114:0] all_addr;wire [19:0] all_bytes;wire [359:0] all_data,normal_rsp_data;',
        'wire [31:0] normal_rsp_status;': 'wire [39:0] normal_rsp_status;',
        'wire [287:0] fault_rsp_data=normal_rsp_data;': 'wire [359:0] fault_rsp_data=normal_rsp_data;',
        'reg [1:0] fault_client=0;': 'reg [2:0] fault_client=0;',
        'wire [31:0] fault_rsp_status=injecting?': 'wire [39:0] fault_rsp_status=injecting?',
        "(normal_rsp_status&~(32'hff<<(fault_client*8)))|(32'h75<<(fault_client*8)):normal_rsp_status;": "(normal_rsp_status&~(40'hff<<(fault_client*8)))|(40'h75<<(fault_client*8)):normal_rsp_status;",
        'assign mem_ready={all_ready[2],all_ready[0]};': 'assign mem_ready={all_ready[4],all_ready[2],all_ready[0]};',
        'assign mem_rsp_valid={all_rsp_valid[2],all_rsp_valid[0]};': 'assign mem_rsp_valid={all_rsp_valid[4],all_rsp_valid[2],all_rsp_valid[0]};',
        'assign mem_rsp_data={fault_rsp_data[144+:72],fault_rsp_data[0+:72]};': 'assign mem_rsp_data={fault_rsp_data[288+:72],fault_rsp_data[144+:72],fault_rsp_data[0+:72]};',
        'assign mem_rsp_status={fault_rsp_status[16+:8],fault_rsp_status[0+:8]};': 'assign mem_rsp_status={fault_rsp_status[32+:8],fault_rsp_status[16+:8],fault_rsp_status[0+:8]};',
        'assign store_idle=dut.directory_service.backend_idle;': 'assign store_idle=dut.directory_service.owned.directory.backend_idle;',
        'external_memory_fabric #(.CLIENTS(4)) fabric(': 'external_memory_fabric #(.CLIENTS(5)) fabric(',
    }
    for old, new in replacements.items(): source = once(source, old, new)
    source = once(source, 'assign all_valid[3]=program_valid;', '\n'.join([
        'assign all_valid[4]=mem_valid[2];assign all_write[4]=mem_write[2];',
        'assign all_addr[92+:23]=mem_addr[46+:23];assign all_bytes[16+:4]=mem_bytes[8+:4];',
        'assign all_data[288+:72]=mem_data[144+:72];assign all_rsp_ready[4]=mem_rsp_ready[2];',
        'assign all_valid[3]=program_valid;']))
    args.output.write_text(source)
    if args.keyed:
        test=(root/'sim/cocotb/test_rpc_durable_response.py').read_text()
        test=test.replace('class DurableBench(', 'class KeyedBench(').replace('exercise_rpc_fixture(d, DurableBench)', 'exercise_rpc_fixture(d, KeyedBench)')
        test=once(test,'async def actual_rpc_progress_then_durable_credit_and_data(d):', 'async def actual_keyed_rpc_progress_credit_and_data(d):')
        test=once(test,'self.contexts = set(); self.credit_job = 0; self.credit_fault_active = False',
            'self.contexts = set(); self.credit_job = 0; self.credit_fault_active = False; self.keyed_updates = 0')
        test=once(test,'d = self.d; a = self.a\n        self.set(window_req_op=op,',
            'd = self.d; a = self.a\n        if op==2:op=9;self.keyed_updates+=1\n        self.set(window_req_op=op,')
        test=once(test,"window_req_generation=binding.get('generation', 0),", "window_req_generation=0 if op==9 else binding.get('generation', 0),")
        test=once(test,"window_req_record_address=a['stream_base'] + binding.get('slot', 0) * 128,", "window_req_record_address=0 if op==9 else a['stream_base'] + binding.get('slot', 0) * 128,")
        test=once(test,"post_commit_credit_fault_cases=2, complete_model_prefix_immutable=True,", 
            'post_commit_credit_fault_cases=2, complete_model_prefix_immutable=True,\n        key_only_window_updates=bench.keyed_updates, actual_keyed_window_update_commands=True,')
        (root/'sim/cocotb/test_rpc_keyed_response.py').write_text('# Generated from the full durable RPC matrix; control updates use wire keys.\n'+test)
    print('Generated actual RPC/durable windows + remote inverse + five real fabric clients')


if __name__ == '__main__':
    main()
