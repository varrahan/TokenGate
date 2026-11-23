"""Native AXI-Lite -> real schema CAM -> full default decoder validation."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from verify_two_fpga_application import closure


def varint(value):
    data=bytearray()
    while value>=128:data.append(value&127|128);value>>=7
    data.append(value);return bytes(data)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--compile-only',action='store_true');args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    frozen=folder/'sources';inputs={}
    def freeze(source,name):
        target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);inputs[name]=sha(target)
    source=root/'FPGA/parser'
    decoder=closure('proto_json_decoder',source);assert len(decoder)==11
    for path in decoder.values():freeze(path,'rtl/'+path.name)
    freeze(root/'rtl/parser_schema_mmio.v','rtl/parser_schema_mmio.v')
    freeze(root/'rtl/parser_schema_mmio_decoder.v','rtl/parser_schema_mmio_decoder.v')
    freeze(root/'sim/tb_parser_schema_mmio.sv','sim/tb_parser_schema_mmio.sv')
    fixture=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources/build/bidirectional-fixtures/reference_cases.json'
    audit=json.loads((root/'build/validation/json-simd-corpus.json').read_text())
    assert audit['key']=='2509134d2630b47e' and sha(fixture)==audit['inputs_sha256']['build/bidirectional-fixtures/reference_cases.json']
    references=json.loads(fixture.read_text())['cases'];assert len(references)==16
    freeze(fixture,'reference_cases.json')
    records=[(0,b'{"prompt":"baseline"}',b'baseline')]
    for key,field in (('message',37),('content',2712)):
        for case in references:
            raw=bytes.fromhex(case['prompt_utf8_hex']);text=raw.decode('utf8')
            body=json.dumps({'prompt':'old schema must not select this',key:text,'ignored':'x'*137},ensure_ascii=False,separators=(',',':')).encode()
            assert json.loads(body)[key].encode()==raw
            records.append((0,body,raw))
            body=b'\x0a\x05wrong'+varint(field<<3|2)+varint(len(raw))+raw
            records.append((1,body,raw))
    assert len(records)==65 and max(len(r[2]) for r in records)==16200
    vectors=folder/'schema-vectors.txt'
    with vectors.open('w') as stream:
        stream.write(str(len(records))+'\n')
        for mode,raw,text in records:
            stream.write(f'{mode} {len(raw)} {len(text)}\n')
            stream.write(' '.join(map(str,raw))+'\n');stream.write(' '.join(map(str,text))+'\n')
    for name in ('cdc','memory','fifo'):
        freeze(Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+name)/'hdl'/('xpm_'+name+'.sv'),'vendor/xpm_'+name+'.sv')
    freeze(Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v'),'vendor/glbl.v')
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    project=folder/'production.prj'
    project.write_text(''.join('verilog work "'+p.relative_to(folder).as_posix()+'"\n' for p in sorted((frozen/'rtl').glob('*.v'))+[frozen/'vendor/glbl.v']))
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),inputs_sha256=inputs,
        driver_sha256=sha(Path(__file__)),vectors_sha256=sha(vectors),project_sha256=sha(project),commands=[],
        default_decoder_parameters=True,decoder_modules=11,additional_mmio_modules=2,expected_packets=65,
        original_prompt_references=16,expected_durable_applies=2,passed=False,
        elaboration_verified=False,simulation_executed=False,
        paired_transport_integration_verified=False,native_timing_verified=False,full_system_complete=False)
    def save(): (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    native=Path('C:/AMDDesignTools/2025.2/Vivado/bin')
    def run(command,name):
        report['commands'].append(command);save()
        with (folder/(name+'-stdout.log')).open('w') as output:
            result=subprocess.run(command,cwd=folder,stdout=output,stderr=subprocess.STDOUT)
        text=(folder/(name+'-stdout.log')).read_text(errors='replace')
        assert result.returncode==0 and not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):',text,re.M),(name,'native failure')
        return text
    save()
    try:
        run([str(native/'xvlog.bat'),'--sv','--define','OBSOLETE','--work','xpm_source','--log','vendor.log']+
            ['sources/vendor/xpm_'+name+'.sv' for name in ('cdc','memory','fifo')],'vendor')
        run([str(native/'xvlog.bat'),'--prj','production.prj','--log','production.log'],'production')
        run([str(native/'xvlog.bat'),'--sv','--log','testbench.log','sources/sim/tb_parser_schema_mmio.sv'],'testbench')
        run([str(native/'xelab.bat'),'--snapshot','parser_schema_mmio','-L','xpm_source','-L','unisims_ver',
            '-L','unimacro_ver','--log','xelab.log','work.tb_parser_schema_mmio'],'elaborate')
        report['elaboration_verified']=True
        if args.compile_only:
            report['phase']='native_parser_schema_mmio_elaborated'
        else:
            report.update(phase='simulating',simulation_executed=True);save()
            text=run([str(native/'xsim.bat'),'parser_schema_mmio','--runall','--log','xsim.log'],'simulate')
            assert text.count('PARSER_SCHEMA_MMIO_TEST_PASS')==1
            actual=(folder/'xsim.log').read_text(errors='replace')
            assert actual.count('PARSER_SCHEMA_MMIO_TEST_PASS')==1 and not re.search(r'^\s*(?:Fatal|Error|FATAL|ERROR):',actual,re.M)
            assert all(sha(frozen/n)==h for n,h in inputs.items())
            report.update(phase='native_parser_schema_mmio_verified',passed=True,log_sha256=sha(folder/'xsim.log'),
                result=re.search(r'^PARSER_SCHEMA_MMIO_TEST_PASS.*$',actual,re.M)[0],
                full_original_prompt_bytes=True,independent_aw_w_channels=True,partial_repeated_register_writes=True,
                held_cfg_b_r_and_text=True,apply_waits_for_durable_cam_rows=True,invalid_schema_apply_rejected=True)
    except BaseException as error:report.update(phase='failed',error=str(error));raise
    finally:report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({k:report[k] for k in ('phase','passed','elaboration_verified','simulation_executed','full_system_complete')}))


if __name__=='__main__':main()
