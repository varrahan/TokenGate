"""Exercise the production shared directory, remote inverse and actual framing."""
import argparse
from pathlib import Path
import subprocess
import sys

from generate_bidirectional_application import ports
from generate_two_fpga_application import named_instance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = root / 'build/rpc-leased-base-harness.sv'
    subprocess.run([sys.executable, str(root / 'tools/generate_cocotb_rpc_grpc_harness.py'), '--output', str(base)], check=True)
    source = base.read_text().replace('module cocotb_rpc_grpc_top;', 'module cocotb_rpc_leased_top;')
    public = ports((root / 'rtl/rpc_grpc_leased_return.v').read_text(), 'rpc_grpc_leased_return')
    connections = {n: n for _, _, n in public}
    host_map = dict(req_valid='host_valid', req_ready='host_ready', req_op='host_op',
        pool_base='host_pool_base', pool_bytes='host_pool_bytes', req_user='host_user', req_application='host_application',
        req_stream='host_stream', req_generation='host_generation', req_address='host_address', req_buffer_base='host_buffer_base',
        req_buffer_bytes='host_buffer_bytes', req_message_limit='host_message_limit', req_protobuf='host_protobuf',
        req_unsupported_encoding='host_encoding', req_maintenance='host_maintenance', req_state='host_state',
        rsp_valid='host_result_valid', rsp_ready='host_result_ready', rsp_status='host_status', rsp_detail='host_detail',
        rsp_memory_status='host_memory_status', rsp_op='host_result_op', rsp_address='host_result_address',
        rsp_buffer_base='host_result_buffer_base', rsp_buffer_bytes='host_result_buffer_bytes', rsp_user='host_result_user',
        rsp_application='host_result_application', rsp_stream='host_result_stream', rsp_generation='host_result_generation',
        rsp_message_limit='host_result_message_limit', rsp_protobuf='host_result_protobuf',
        rsp_unsupported_encoding='host_result_encoding', rsp_state='host_result_state')
    existing = {'host_result_valid', 'host_result_ready', 'host_status', 'host_result_address',
                'host_valid', 'host_ready', 'host_op', 'host_pool_base', 'host_pool_bytes', 'host_user',
                'host_application', 'host_stream', 'host_generation', 'host_address', 'host_buffer_base',
                'host_buffer_bytes', 'host_message_limit', 'host_protobuf', 'host_encoding', 'host_maintenance'}
    extra = []
    for direction, width, name in public:
        if name.startswith('control_'):
            mapped = host_map[name[8:]]
            connections[name] = mapped
            if mapped not in existing:
                extra.append(f"{'reg' if direction=='input' else 'wire'} {width} {mapped}{'=0' if direction=='input' else ''};")
                existing.add(mapped)
        elif name in ('record_lease_active', 'directory_recovery_required', 'directory_recovery_address'):
            extra.append(f'wire {width} {name};')
    source = source.replace('rpc_grpc_parser_response dut(.*);', '\n'.join(extra) + '\n' + named_instance(
        'rpc_grpc_leased_return', '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', 'dut', connections))
    start = source.index('assign directory_ready=store_ready;')
    end = source.index('assign all_valid[3]=program_valid;', start)
    old_directory_ports = [n for _, _, n in ports((root / 'rtl/rpc_grpc_parser_response.v').read_text(), 'rpc_grpc_parser_response')
                           if n.startswith('directory_') and n != 'directory_lease_active']
    replacement = ['assign ' + name + '=dut.' + name + ';' for name in old_directory_ports]
    replacement += [
        'assign all_valid[2]=mem_valid[1];assign all_write[2]=mem_write[1];',
        'assign all_addr[46+:23]=mem_addr[23+:23];assign all_bytes[8+:4]=mem_bytes[4+:4];',
        'assign all_data[144+:72]=mem_data[72+:72];assign all_rsp_ready[2]=mem_rsp_ready[1];',
        'assign store_recovery=directory_recovery_required;',
        'assign store_ready=host_ready;assign store_idle=dut.directory_service.backend_idle;']
    source = source[:start] + '\n'.join(replacement) + '\n' + source[end:]
    source = source.replace('assign mem_ready=all_ready[1:0];', 'assign mem_ready={all_ready[2],all_ready[0]};')
    source = source.replace('assign mem_rsp_valid=all_rsp_valid[1:0];', 'assign mem_rsp_valid={all_rsp_valid[2],all_rsp_valid[0]};')
    source = source.replace('assign mem_rsp_data=fault_rsp_data[143:0];', 'assign mem_rsp_data={fault_rsp_data[144+:72],fault_rsp_data[0+:72]};')
    source = source.replace('assign mem_rsp_status=fault_rsp_status[15:0];', 'assign mem_rsp_status={fault_rsp_status[16+:8],fault_rsp_status[0+:8]};')
    source = source.replace('if(rst)host_selected<=0;\n    else if((directory_valid||host_valid&&idle)&&store_ready)host_selected<=!directory_valid;\n    ', '')
    assert 'grpc_stream_store registry(' not in source
    args.output.write_text(source)
    print('Generated production leased return + remote inverse; four real fabric clients')


if __name__ == '__main__':
    main()
