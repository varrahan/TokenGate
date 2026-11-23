"""Generate native-XSim stimulus for the complete two-chiplet HTTP/2 workload.

Production sources are frozen from the already elaborated 76/31 assembly.
The Parser's real four-module memory fabric is included, as in its original
full-corpus test. Only the external AXI memory device is a behavioral model.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+', args.name)
    root = Path(__file__).resolve().parents[1]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    native = root / 'build/validation/dual_fpga_hyperram_order_v4_20261122'
    report = json.loads((native / 'report.json').read_text())
    assert report['passed'] and report['elaboration_verified']
    assert all(sha(native / 'sources' / n) == h for n,h in report['inputs_sha256'].items())
    fixtures = root / 'build/experiments/joint-hyperram-grpc/fixtures'
    ref = json.loads((fixtures / 'reference.json').read_text())
    assert ref['sequences'] == 32 and ref['expected_actual_dma_ids'] == 11091
    assert all(sha(fixtures / n) == h for n,h in ref['fixture_sha256'].items())
    target = root / 'build/experiments' / args.name
    target.mkdir(parents=True, exist_ok=False)
    shutil.copytree(native / 'sources/joint', target / 'joint')
    for name in ('epoch0.vectors','epoch1.vectors','image0.bin','image1.bin','parser-image.bin','reference.json'):
        shutil.copy2(fixtures / name, target / name)
    original = root / 'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    fabric = closure('external_memory_fabric', original)
    assert set(fabric) == {'external_memory_fabric','external_memory_arbiter','external_memory_cache','programmable_table_ram'}
    for name,path in fabric.items():
        assert not (target / 'joint/rtl' / path.name).exists(), name
        shutil.copy2(path, target / 'joint/rtl' / path.name)
    top = (target / 'joint/rtl/two_fpga_hyperram_application.v').read_text()
    interface = ports(top,'two_fpga_hyperram_application')
    fabric_ports = ports((original / 'rtl/external_memory_fabric.v').read_text(),'external_memory_fabric')
    memory_inputs = {n for d,w,n in fabric_ports if d == 'output' and n in
        ('s_ready','rsp_valid','rsp_data','rsp_status')}
    fabric_mapping = dict(clk='app_clk',rst='rst',invalidate_valid="1'b0",invalidate_ready='',
                          idle='parser_fabric_idle')
    fabric_mapping.update({n:'parser_mem_' + n[2:] for n in ('s_valid','s_ready','s_write','s_addr','s_bytes','s_data')})
    fabric_mapping.update({n:'parser_mem_' + n for n in ('rsp_valid','rsp_ready','rsp_data','rsp_status')})
    memory_driven = {fabric_mapping[n] for n in memory_inputs}
    # Real extra host client: route metadata is programmable configuration,
    # and must advance with the active model before new RPC admission.
    fabric_mapping.update(s_valid='{host_cfg_valid,parser_mem_valid}',s_ready='{host_cfg_ready,parser_mem_ready}',
        s_write='{host_cfg_write,parser_mem_write}',s_addr='{host_cfg_addr,parser_mem_addr}',
        s_bytes="{4'd4,parser_mem_bytes}",s_data="{40'd0,host_cfg_data,parser_mem_data}",
        rsp_valid='{host_cfg_rsp_valid,parser_mem_rsp_valid}',rsp_ready='{host_cfg_rsp_ready,parser_mem_rsp_ready}',
        rsp_data='{host_cfg_rsp_data,parser_mem_rsp_data}',rsp_status='{host_cfg_rsp_status,parser_mem_rsp_status}')
    lines = ['`timescale 1ps/1ps','`default_nettype none','module joint_hyperram_grpc_tb;',
             'localparam USER_WIDTH=16,CLIENTS=20,ADDR_WIDTH=23;',
             'integer current_epoch=0;']
    for direction,width,name in interface:
        kind = 'reg' if direction == 'input' and name not in memory_driven else 'wire'
        value = ref['defaults'].get(name.removeprefix('parser_'),0) if name.startswith('parser_') else 0
        if name == 'rst': value = 1
        lines.append(f'{kind} {width} {name}' + (f'={value};' if kind == 'reg' else ';'))
    lines += ['wire parser_fabric_idle;',
              'reg host_cfg_valid=0,host_cfg_write=0,host_cfg_rsp_ready=0;',
              'reg [22:0] host_cfg_addr=0;reg [31:0] host_cfg_data=0;',
              'wire host_cfg_ready,host_cfg_rsp_valid;wire [71:0] host_cfg_rsp_data;wire [7:0] host_cfg_rsp_status;']
    for d,w,n in fabric_ports:
        if n.startswith('m_axi_'):
            signal = 'p_axi_' + n[6:]
            fabric_mapping[n] = signal
            lines.append(f'{"reg" if d == "input" else "wire"} {w} {signal}' + ('=0;' if d == 'input' else ';'))
    lines += ['two_fpga_hyperram_application dut(', ',\n'.join(f'.{n}({n})' for _,_,n in interface),');',
              'external_memory_fabric #(.CLIENTS(20)) parser_fabric(',
              ',\n'.join(f'.{n}({fabric_mapping[n]})' for _,_,n in fabric_ports),');']
    for task,key in (('configure','base_configuration'),('response_configuration','response_configuration'),('poison','poison_configuration')):
        lines += [f'task automatic {task};']
        for name,value in ref[key].items():
            lines += [f'parser_{name}={value};']
        if task != 'poison': lines += ['parser_cfg_model_epoch=23+current_epoch;']
        lines += ['endtask']
    a = ref['layout']
    lines += ['task automatic setup_open;', 'configure();']
    command = dict(maintenance_grant=1,command_op=0,command_user=0,command_server_role=1,
                   command_allow_push=0,command_max_frame_bytes=16384,
                   command_buffer_base=a[28],command_buffer_bytes=a[29],command_table_base=a[30],command_table_bytes=a[31],
                   command_scratch_base=a[32],command_scratch_bytes=a[33],command_hpack_maximum=4096,command_hpack_allowed=4096,
                   command_header_list_limit=32768,command_required_maximum=4096,command_required_update=0)
    lines += [f'parser_{n}={v};' for n,v in command.items()]
    lines += ['endtask']
    # Change signal references only; hierarchical member names remain intact.
    device_path = root / 'build/validation/tokenizer_hyperram_two_epoch_record_capacity/sources/sim/hyperram_device_and_host.svh'
    model = device_path.read_text().replace('dut.memory.','dut.tokenizer.memory.')
    names = {n.removeprefix('tokenizer_'):n for _,_,n in interface if n.startswith('tokenizer_')}
    model = re.sub(r'(?<![.\w])(' + '|'.join(sorted(names,key=len,reverse=True)) + r')\b',lambda m:names[m[0]],model)
    (target / 'hyperram_device_and_host.svh').write_text(model)
    for name in ('joint_parser_axi_memory.svh','joint_hyperram_grpc_body.svh'):
        shutil.copy2(root / 'sim' / name,target / name)
    lines += ['`include "hyperram_device_and_host.svh"', '`include "joint_parser_axi_memory.svh"',
              '`include "joint_hyperram_grpc_body.svh"','endmodule','`default_nettype wire','']
    (target / 'joint_hyperram_grpc_tb.sv').write_text('\n'.join(lines))
    shutil.copy2(Path(__file__),target / Path(__file__).name)
    result = dict(phase='joint_hyperram_grpc_test_generated',generator_sha256=sha(Path(__file__)),
        native_assembly_inputs_sha256=report['inputs_sha256'],fixture_reference_sha256=sha(fixtures / 'reference.json'),
        independent_device_model_sha256=sha(device_path),parser_fabric_sha256={n:sha(p) for n,p in fabric.items()},
        parser_modules=76,tokenizer_modules=31,additional_parser_memory_fabric_modules=4,
        parser_application_memory_clients=19,parser_fabric_clients=20,real_host_route_configuration_client=True,
        complete_images=2,complete_image_bytes_each=8388608,full_corpus_sequences=32,
        expected_actual_dma_ids=11091,simulation_verified=False,full_system_complete=False,
        outputs_sha256={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()})
    (target / 'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','parser_modules','tokenizer_modules','full_corpus_sequences')}))


if __name__ == '__main__':
    main()
