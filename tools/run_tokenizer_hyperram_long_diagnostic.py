"""Reproduce the slow custom-model case without replacing the full regression."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


FOCUSED_TEST='''
initial begin : custom_long_diagnostic
    integer file,cases,value,token,keep,eos,raw_length,serialized_length,decoded,carry,carry_count,loaded;
    `include "tokenizer_config.svh"
    current_epoch=1;current_case=15;
    link_f_bpe_admit_sequences=1;link_f_bpe_error_ready=1;
    link_r_cfg_strip_special=1;link_r_cfg_replace_invalid=1;link_r_cfg_protobuf_field=17;link_r_cfg_active_model_epoch=24;
    file=$fopen("epoch1.vectors","r");assert(file!=0)else $fatal(1,"Missing full custom corpus");
    scan_value(file,cases);assert(cases==16)else $fatal(1,"Unexpected source corpus");
    for(integer index=0;index<16;index++)begin
        load_case(file);
        if(index!=15)begin
            for(integer chunk=0;chunk<case_chunks;chunk++)begin
                scan_value(file,token);scan_value(file,keep);scan_value(file,eos);scan_value(file,raw_length);
                scan_value(file,serialized_length);scan_value(file,decoded);scan_value(file,carry);scan_value(file,carry_count);
                repeat(raw_length+serialized_length)scan_value(file,value);
            end
        end
    end
    assert(prompt_bytes==16200&&expected_count==8101)else $fatal(1,"Long case was reduced");
    prepare_text_beat(0);rst=1;power_good_mem=0;phy_ready_mem=0;
    #150000;power_good_mem=1;phy_ready_mem=1;rst=0;wait(!app_reset);
    read_burst(0,1,0,0,23);
    begin : image_load
        integer image_file;
        image_file=$fopen("image1.bin","rb");assert(image_file!=0)else $fatal(1,"Missing full custom model");
        loaded=$fread(image,image_file);$fclose(image_file);assert(loaded==8388608)else $fatal(1,"Custom model was reduced");
    end
    full_phase=1;
    for(integer addr=0;addr<8388608;addr+=64)begin
        write_burst(addr);if((addr+64)%1048576==0)$display("LONG_DIAGNOSTIC_IMAGE_WRITE bytes=%0d",addr+64);
    end
    full_phase=0;assert(full_wire_writes==131072)else $fatal(1,"Incomplete custom image write");
    for(integer i=0;i<8388608;i++)assert(device_memory[i]==image[i])else $fatal(1,"Custom image physical bytes mismatch");
    full_phase=2;
    for(integer addr=0;addr<8388608;addr+=64)begin
        read_burst(addr);if((addr+64)%1048576==0)$display("LONG_DIAGNOSTIC_IMAGE_READ bytes=%0d",addr+64);
    end
    full_phase=0;assert(full_wire_reads==131072)else $fatal(1,"Incomplete custom image readback");
    activate_image(0);complete_forward(1);
    $display("LONG_DIAGNOSTIC_FORWARD_PASS prompt_bytes=%0d token_ids=%0d",prompt_bytes,dma_received);
    run_inverse(file);$fclose(file);
    assert(total_forward==1&&total_inverse==8101)else $fatal(1,"Diagnostic chunk count");
    $display("TOKENIZER_LONG_DIAGNOSTIC_PASS image_bytes=8388608 prompt_bytes=16200 token_ids=8101 inverse_chunks=8101 full_corpus=0 app_reads=%0d app_writes=%0d",app_reads,app_writes);
    $finish;
end
initial begin #(64'd2000000000000);$fatal(1,"Long custom-model diagnostic timeout");end
'''


def main():
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'build/validation/tokenizer_hyperram_two_epoch_encoding_progress'
    original=json.loads((source/'report.json').read_text())
    name='tokenizer_hyperram_custom_long_diagnostic';folder=root/'build/validation'/name;folder.mkdir(parents=True,exist_ok=False)
    inputs={}
    for relative,digest in original['inputs_sha256'].items():
        path=source/'sources'/relative;assert sha(path)==digest
        target=folder/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        inputs[relative]=sha(target)
    body=folder/'sources/sim/tokenizer_hyperram_test_body.svh';text=body.read_text()
    assert text.count('initial begin : integrated_test')==1
    body.write_text(text.split('initial begin : integrated_test')[0]+FOCUSED_TEST)
    inputs['sim/tokenizer_hyperram_test_body.svh']=sha(body)
    for filename in('image1.bin','epoch1.vectors','reference.json'):
        (folder/filename).write_bytes((source/filename).read_bytes())
    assert sha(folder/'image1.bin')=='18260f8582bbed7334748a94b7f7c324c163d0d658d5d2303d1793ea49f6e0ee'
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),parent_simulation=source.name,
        inputs_sha256=inputs,driver_sha256=sha(Path(__file__)),full_corpus_executed=False,
        complete_8mib_custom_model=True,target_prompt_bytes=16200,target_token_ids=8101,
        vendor_sva_enabled=False,independent_assertions_enabled=True,full_system_complete=False,commands=[])
    output=folder/'report.json';output.write_text(json.dumps(report,indent=2)+'\n')
    (folder/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    def run(command,label):
        report['commands'].append(command);output.write_text(json.dumps(report,indent=2)+'\n')
        with(folder/(label+'.log')).open('w')as log:
            process=subprocess.Popen(command,cwd=folder,stdout=log,stderr=subprocess.STDOUT)
            report['active_process']=dict(label=label,pid=process.pid);output.write_text(json.dumps(report,indent=2)+'\n');code=process.wait()
        assert code==0,(label,code)
        text=(folder/(label+'.log')).read_text(errors='replace');assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),label
        return text
    try:
        frozen=folder/'sources';tools=Path('C:/AMDDesignTools/2025.2/Vivado/bin')
        run([str(tools/'xvlog.bat'),'--sv','--define','OBSOLETE','--work','xpm_source','--log','vendor-compile.log']+
            [str(frozen/'vendor'/('xpm_'+macro+'.sv'))for macro in('cdc','memory','fifo')],'vendor')
        run([str(tools/'xvlog.bat'),'--log','rtl-compile.log']+[str(path)for path in sorted((frozen/'rtl').glob('*.v'))]+
            [str(frozen/'vendor/glbl.v')],'rtl')
        run([str(tools/'xvlog.bat'),'--sv','--include',str(frozen/'sim'),'--log','testbench-compile.log',str(frozen/'sim/tb_tokenizer_hyperram.sv')],'testbench')
        run([str(tools/'xelab.bat'),'--debug','off','--snapshot','tokenizer_long','-L','xpm_source','-L','unisims_ver','-L','unimacro_ver',
            '--log','xelab.log','work.tb_tokenizer_hyperram','work.glbl'],'elaboration')
        report['phase']='running'
        text=run('"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" tokenizer_long --runall --onerror quit --onfinish quit --maxlogsize 32 --log xsim-diagnostic.log','simulation')
        markers=re.findall(r'^TOKENIZER_LONG_DIAGNOSTIC_PASS (.+)$',text,re.M);assert len(markers)==1
        values={key:int(value)for key,value in re.findall(r'(\w+)=(\d+)',markers[0])}
        assert values['full_corpus']==0 and values['token_ids']==values['inverse_chunks']==8101
        assert values['prompt_bytes']==16200 and values['image_bytes']==8388608
        report.update(phase='targeted_custom_long_diagnostic_passed',passed=True,acceptance=values)
    except BaseException as error:
        report.update(phase='targeted_custom_long_diagnostic_failed',passed=False,error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(phase=report['phase'],acceptance=report.get('acceptance'),full_corpus_executed=False)))


if __name__=='__main__':main()
