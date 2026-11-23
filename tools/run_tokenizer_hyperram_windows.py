"""Freeze and execute actual Tokenizer + cache + dual-clock physical word engine."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from generate_hyperram_cdc_timing_harness import ports
from verify_two_fpga_application import closure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--compile-only',action='store_true');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    experiment=root/'build/experiments/tokenizer-hyperram';fixtures=experiment/'fixtures'
    generation=json.loads((experiment/'generation.json').read_text());reference=json.loads((fixtures/'reference.json').read_text())
    for name,digest in generation['outputs_sha256'].items():assert sha(experiment/name)==digest,name
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    frozen=folder/'sources';inputs={}
    def freeze(source,name):
        target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);inputs[name]=sha(target);return target
    for name in generation['outputs_sha256']:freeze(experiment/name,name)
    # The Parser-side serializer is actual RTL in the test fixture. It does not
    # become part of the Tokenizer FPGA synthesis closure.
    for source in set(closure('utf8_serialized_chunk').values()):
        name='rtl/'+source.name
        if name in inputs:assert inputs[name]==sha(source)
        else:freeze(source,name)
    interface=ports((frozen/'rtl/tokenizer_hyperram_subsystem.v').read_text(),'tokenizer_hyperram_subsystem')
    lines=['`timescale 1ps/1ps','module tb_tokenizer_hyperram;',
        'localparam USER_WIDTH=16;',f'localparam EXPECTED_INVERSE_CHUNKS={sum(len(case["chunks"])for epoch in reference["cases"]for case in epoch)};']
    for direction,width,name in interface:
        kind='logic'if direction=='input'and not name.startswith('link_s_')else'wire'
        lines.append(f'{kind} {width} {name}'+('=0;'if kind=='logic'else';'))
    lines += ['wire [511:0] test_tx_data;wire [63:0] test_tx_keep;wire [15:0] test_tx_user;',
        'wire test_tx_valid,test_tx_last;logic test_tx_ready=0;',
        'tokenizer_hyperram_subsystem dut(.*);']
    serializer=ports((frozen/'rtl/utf8_serialized_chunk.v').read_text(),'utf8_serialized_chunk')
    mapping=dict(clk='app_clk',rst='application_reset',m_axis_tx_tdata='test_tx_data',m_axis_tx_tkeep='test_tx_keep',
        m_axis_tx_tvalid='test_tx_valid',m_axis_tx_tready='test_tx_ready',m_axis_tx_tlast='test_tx_last',m_axis_tx_tuser='test_tx_user')
    lines += ['utf8_serialized_chunk #(.USER_WIDTH(16),.MAX_TEXT_BYTES(16384)) test_serializer(',
        ',\n'.join(f'    .{name}({mapping.get(name,"link_s_"+name)})'for _,_,name in serializer),');',
        '`include "hyperram_device_and_host.svh"','`include "tokenizer_hyperram_test_body.svh"','endmodule','']
    tb=frozen/'sim/tb_tokenizer_hyperram.sv';tb.parent.mkdir(parents=True,exist_ok=True);tb.write_text('\n'.join(lines));inputs['sim/tb_tokenizer_hyperram.sv']=sha(tb)
    original=root/'build/experiments/hyperram-shared-reset/sim/hyperram_async_test_body.svh'
    text=original.read_text();assert text.count('initial begin : test')==1
    body=frozen/'sim/hyperram_device_and_host.svh';body.write_text(text[:text.index('initial begin : test')]
        .replace('dut.clock_bridge.','dut.memory.clock_bridge.').replace('dut.reset_request','dut.memory.reset_request'))
    inputs['sim/hyperram_device_and_host.svh']=sha(body)
    freeze(root/'sim/tokenizer_hyperram_test_body.svh','sim/tokenizer_hyperram_test_body.svh')
    freeze(fixtures/'tokenizer_config.svh','sim/tokenizer_config.svh')
    for macro in('cdc','memory','fifo'):
        freeze(Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+macro)/'hdl'/('xpm_'+macro+'.sv'),'vendor/xpm_'+macro+'.sv')
    freeze(Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v'),'vendor/glbl.v')
    for epoch in range(2):
        source=Path(reference['base_image_path']if epoch==0 else reference['swapped_image_path'])
        assert sha(source)==reference['image_sha256'][epoch]and source.stat().st_size==8388608
        shutil.copy2(source,folder/f'image{epoch}.bin');shutil.copy2(fixtures/f'epoch{epoch}.vectors',folder/f'epoch{epoch}.vectors')
    shutil.copy2(experiment/'generation.json',folder/'generation.json');shutil.copy2(fixtures/'reference.json',folder/'reference.json')
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    vendor_sva=False
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        driver_sha256=sha(Path(__file__)),generation_sha256=sha(folder/'generation.json'),reference_sha256=sha(folder/'reference.json'),
        image_sha256=reference['image_sha256'],commands=[],vendor_sources_unmodified=True,vendor_sva_enabled=vendor_sva,
        compatibility_defines=['OBSOLETE'],independent_assertions_enabled=True,portable_memory_backend=False,
        primary_integration_wiring_modified=False,bpe_declaration_order_fix=True,pin_level_phy_verified=False,full_system_complete=False)
    output=folder/'report.json';output.write_text(json.dumps(report,indent=2)+'\n')
    def run(command,label):
        report['commands'].append(command);output.write_text(json.dumps(report,indent=2)+'\n')
        with(folder/(label+'.log')).open('w')as log:
            result=subprocess.run(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode==0,(label,result.returncode)
        text=(folder/(label+'.log')).read_text(errors='replace')
        assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),(label,'Native simulator failure')
        return text
    try:
        tools=Path('C:/AMDDesignTools/2025.2/Vivado/bin')
        run([str(tools/'xvlog.bat'),'--sv','--define','OBSOLETE','--work','xpm_source','--log','vendor-compile.log']+
            [str(frozen/'vendor'/('xpm_'+name+'.sv'))for name in('cdc','memory','fifo')],'vendor')
        # Compile production .v sources as Verilog, matching read_verilog in
        # native synthesis. The independent .sv test uses SystemVerilog.
        run([str(tools/'xvlog.bat'),'--log','rtl-compile.log']+
            [str(p)for p in sorted((frozen/'rtl').glob('*.v'))]+[str(frozen/'vendor/glbl.v')],'rtl')
        run([str(tools/'xvlog.bat'),'--sv','--include',str(frozen/'sim'),'--log','testbench-compile.log',str(tb)],'testbench')
        report['phase']='elaborating'
        run([str(tools/'xelab.bat'),'--debug','off','--snapshot','tokenizer_hyperram','-L','xpm_source','-L','unisims_ver','-L','unimacro_ver',
             '--log','xelab.log','work.tb_tokenizer_hyperram','work.glbl'],'elaboration')
        if args.compile_only:
            report.update(phase='native_tokenizer_hyperram_elaborated',elaboration_verified=True,simulation_executed=False)
        else:
            report['phase']='running'
            text=run('"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" tokenizer_hyperram --runall --onerror quit --onfinish quit --maxlogsize 32 --log xsim-integration.log','simulation')
            matches=re.findall(r'^TOKENIZER_HYPERRAM_PASS (.+)$',text,re.M);assert len(matches)==1,'Integration did not finish'
            values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',matches[0])}
            assert values['image_epochs']==2 and values['image_bytes_each']==8388608
            assert values['full_writes']==values['full_reads']==262144 and values['sequences']==32
            assert values['inverse_chunks']==sum(len(case['chunks'])for epoch in reference['cases']for case in epoch)
            assert values['grant_rejections']==values['maintenance_switches']==1 and values['reset_epochs']==2
            report.update(phase='actual_tokenizer_hyperram_two_complete_images_passed',passed=True,acceptance=values)
        assert all(sha(frozen/name)==digest for name,digest in inputs.items())
    except BaseException as error:
        report.update(phase='native_tokenizer_hyperram_failed',passed=False,error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],acceptance=report.get('acceptance'),evidence_folder=str(folder))))


if __name__=='__main__':main()
