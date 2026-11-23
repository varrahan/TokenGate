"""Expose the actual asynchronous controller to an independent SV bus model."""
import hashlib
import json
from pathlib import Path
from generate_hyperram_cdc_timing_harness import ports

from rtl_paths import source_path


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=source_path(root, 'rtl/axi_hyperram_async_controller.v');body=root/'sim/hyperram_async_test_body.svh'
    interface=ports(source.read_text(),'axi_hyperram_async_controller')
    lines=['`timescale 1ps/1ps','module tb_axi_hyperram_async;']
    lines +=[f'{"logic"if d=="input"else"wire"} {w} {n}'+('=0;'if d=='input'else';')for d,w,n in interface]
    lines +=['axi_hyperram_async_controller dut(.*);','`include "hyperram_async_test_body.svh"','endmodule','']
    target=root/'sim/tb_axi_hyperram_async.sv';target.write_text('\n'.join(lines))
    result=dict(generator_sha256=sha(Path(__file__)),source_sha256=sha(source),body_sha256=sha(body),
        parser_sha256=sha(root/'tools/generate_hyperram_cdc_timing_harness.py'),output_sha256=sha(target),
        actual_full_assembly_instantiated=True,pin_level_phy_present=False,full_system_complete=False)
    folder=root/'build/hyperram-async';folder.mkdir(parents=True,exist_ok=True)
    (folder/'testbench-generation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
