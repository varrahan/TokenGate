"""Actual separate Parser return/Tokenizer inverse with four real memory clients."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from generate_bidirectional_application import ports
from generate_two_fpga_application import instance, named_instance

from rtl_paths import source_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = root / 'build/rpc-grpc-base-harness.sv'
    subprocess.run([sys.executable, str(root / 'tools/generate_cocotb_rpc_response_harness.py'), '--output', str(base)], check=True)
    source = base.read_text().replace('module cocotb_rpc_response_top;', 'module cocotb_rpc_grpc_top;')
    module_path = source_path(root, 'rtl/rpc_grpc_parser_response.v')
    public = ports(module_path.read_text(), 'rpc_grpc_parser_response')
    declarations = []
    for direction, width, name in public:
        driven = direction == 'input' and not name.startswith(('directory_', 'link_')) and name not in ('mem_ready', 'mem_rsp_valid', 'mem_rsp_data', 'mem_rsp_status')
        declarations.append(f"{'reg' if driven else 'wire'} {width} {name}{'=0' if driven else ''};")
    start = source.index('localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;') + len('localparam USER_WIDTH=16,MEMORY_ADDR_WIDTH=23;')
    end = re.search(r'\nreg\s+m_axi_arready', source).start()
    source = source[:start] + '\n' + '\n'.join(declarations) + source[end:]
    _, _, _, inverse = instance((source_path(root, 'rtl/tokenizer_fpga_application.v')).read_text(), 'inverse_tokenizer_partition', 'inverse')
    inverse.update(mem_rd_valid='inverse_valid', mem_rd_ready='all_ready[1]', mem_rd_addr='inverse_addr', mem_rd_bytes='inverse_bytes',
        mem_rsp_valid='all_rsp_valid[1]', mem_rsp_ready='inverse_rsp_ready', mem_rsp_data='fault_rsp_data[72+:72]', mem_rsp_status='fault_rsp_status[8+:8]')
    inverse_source = '\n'.join(['wire inverse_valid,inverse_rsp_ready;wire [22:0] inverse_addr;wire [3:0] inverse_bytes;',
        'rpc_grpc_parser_response dut(.*);', named_instance('inverse_tokenizer_partition',
            '.USER_WIDTH(USER_WIDTH),.MEMORY_ADDR_WIDTH(MEMORY_ADDR_WIDTH)', 'inverse', inverse)])
    source = source.replace('rpc_generated_response dut(.*);', inverse_source)
    replacements = {
        'assign all_valid[1:0]=mem_valid;': 'assign all_valid[1:0]={inverse_valid,mem_valid[0]};',
        'assign all_write[1:0]=mem_write;': "assign all_write[1:0]={1'b0,mem_write[0]};",
        'assign all_addr[45:0]=mem_addr;': 'assign all_addr[45:0]={inverse_addr,mem_addr[22:0]};',
        'assign all_bytes[7:0]=mem_bytes;': 'assign all_bytes[7:0]={inverse_bytes,mem_bytes[3:0]};',
        'assign all_data[143:0]=mem_data;': "assign all_data[143:0]={72'd0,mem_data[71:0]};",
        'assign all_rsp_ready[1:0]=mem_rsp_ready;': 'assign all_rsp_ready[1:0]={inverse_rsp_ready,mem_rsp_ready[0]};'}
    for before, after in replacements.items():
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    args.output.write_text(source)
    print('Generated separate Parser RPC/framer + actual Tokenizer inverse + directory/four-client fabric')


if __name__ == '__main__':
    main()
