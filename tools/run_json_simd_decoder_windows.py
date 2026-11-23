"""Compare the scalar and SIMD transactional decoders with independent bytes."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from verify_two_fpga_application import closure


def varint(value):
    result=bytearray()
    while value>=128:result.append((value&127)|128);value>>=7
    result.append(value);return bytes(result)


def records_from_file(path):
    words=iter(map(int,path.read_text().split()));count=next(words);records=[]
    for _ in range(count):
        mode,profile,nraw,ntext,code=[next(words)for _ in range(5)]
        records.append((mode,profile,bytes(next(words)for _ in range(nraw)),bytes(next(words)for _ in range(ntext)),code,0))
    assert next(words,None)is None;return records


def fixture(root,folder,kind):
    if kind=='mixed':
        subprocess.run([sys.executable,str(root/'tools/generate_decoder_vectors.py'),'--output',str(folder/'original-vectors.mem')],check=True,capture_output=True)
        records=records_from_file(folder/'original-vectors.mem')
        for offset in(0,1,7,8,31,63):
            raw=(b' \t\r\n'*32)[offset:]+json.dumps({'ignored':'a'*1024+':{}[],'+'b'*257+' ☃ U0001f680 '+ 'c'*193,
                'content':'kept ☃ U0001f680'},ensure_ascii=False).encode()
            value=json.loads(raw);records.append((0,1,raw,value['content'].encode(),0,0))
        for bad in(b'\xe2plain',b'\\q',b'\\ud800plain',b'\x1f',b'\xc0\xaf',b'\\u12'):
            raw=b'{"content":"tentative","ignored":"'+b'a'*129+bad+b'"}'
            records.append((0,1,raw,b'',255,0))
        for length in(128,129):
            raw=json.dumps({'ignored':'ignored words '*80,'content':'x'*length}).encode()
            records.append((0,1,raw,b'x'*length if length==128 else b'',0 if length==128 else 128,0))
        records.append((0,1,b'{"content":"abort","ignored":"'+b'a'*159+b'"}',b'',129,1))
        raw=varint((17<<3)|2)+varint(159)+b'a'*159;records.append((1,1,raw,b'',129,1))
    else:
        reference=json.loads((root/'build/experiments/tokenizer-hyperram/fixtures/reference.json').read_text());records=[]
        for case in reference['cases'][0]:
            # Keep the exact original prompt bytes, including the 16200-byte
            # case. Additional unselected text exercises the discard path.
            raw_text=bytes.fromhex(case['prompt_hex'])
            raw=b' \t\n\r'*16+json.dumps({'ignored':'discard this ASCII value '*16,'prompt':raw_text.decode('utf8')},ensure_ascii=False).encode()
            records.append((0,0,raw,raw_text,0,0))
            raw=varint((17<<3)|2)+varint(len(raw_text))+raw_text;records.append((1,0,raw,raw_text,0,0))
        records.append((0,0,b'{"prompt":"abort","ignored":"'+b'z'*159+b'"}',b'',129,1))
        records.append((1,0,varint((17<<3)|2)+varint(159)+b'z'*159,b'',129,1))
    assert len(records)<=512 and sum(len(r[2])for r in records)<=262144 and sum(len(r[3])for r in records)<=262144
    output=folder/'decoder_vectors.mem'
    with output.open('w')as stream:
        stream.write(str(len(records))+'\n')
        for mode,profile,raw,text,code,abort in records:
            stream.write(f'{mode} {profile} {len(raw)} {len(text)} {code} {abort}\n')
            stream.write(' '.join(map(str,raw))+'\n');stream.write(' '.join(map(str,text))+'\n')
    return dict(packets=len(records),committed=sum(r[4]==0 for r in records),discarded=sum(r[4]!=0 for r in records),
        raw_bytes=sum(len(r[2])for r in records),text_bytes=sum(len(r[3])for r in records),maximum_text_bytes=max(len(r[3])for r in records))


def adapt_testbench(source,kind):
    def change(before,after):
        nonlocal source
        assert source.count(before)==1,(before[:90],source.count(before));source=source.replace(before,after)
    change('    logic held_valid=0,error_held_valid=0;','''    integer current_packet=0,abort_packet[0:511];
    integer cycles=0,rx_beats=0,white_bulk=0,plain_bulk=0,max_step=0;
    wire input_abort=sl&&abort_packet[current_packet]!=0;
    logic held_valid=0,error_held_valid=0;''')
    change(".s_axis_rx_tlast(sl),.s_axis_rx_tuser(su),.s_axis_rx_abort(1'b0),",'.s_axis_rx_tlast(sl),.s_axis_rx_tuser(su),.s_axis_rx_abort(input_abort),')
    change('    always @(posedge clk)if(!rst)begin','''    always @(posedge clk)if(!rst)begin
        cycles++;if(sv&&sr)rx_beats++;
`ifdef SIMD_CANDIDATE
        if(dut.json_parser.s_valid&&dut.json_parser.s_ready&&dut.json_parser.consumed>1)begin
            if(dut.json_parser.state==0)white_bulk++;
            else if(dut.json_parser.plain_discard)plain_bulk++;
            if(dut.json_parser.consumed>max_step)max_step=dut.json_parser.consumed;
        end
`endif''')
    change('            response_idx++;errors++;','            $display("DECODER_ERROR_RESULT packet=%0d code=%0d",response_idx,error_code);\n            response_idx++;errors++;')
    change('result=$fscanf(fd,"%d %d %d %d %d",format_id[p],profile_id[p],raw_len[p],out_len[p],expected_code[p]);',
        'result=$fscanf(fd,"%d %d %d %d %d %d",format_id[p],profile_id[p],raw_len[p],out_len[p],expected_code[p],abort_packet[p]);')
    change('if(result!=5)$fatal','if(result!=6)$fatal')
    change('repeat(5)@(negedge clk);rst=0;','repeat(40)@(negedge clk);rst=0;')
    change("@(negedge clk);mode=format_id[p]!=0;su=16'h5000+p;offset=0;","@(negedge clk);current_packet=p;mode=format_id[p]!=0;su=16'h5000+p;offset=0;")
    change('$urandom_range(0,2)!=0','(p*17+offset+lane*13)%5!=0')
    if kind=='full':
        change('.FIFO_DEPTH(16),.MAX_TEXT_BYTES(128),.MAX_FIELD_BYTES(256),.MAX_JSON_DEPTH(8),.MAX_PROTO_GROUP_DEPTH(4)',
            '.FIFO_DEPTH(512),.MAX_TEXT_BYTES(16384),.MAX_FIELD_BYTES(16384),.MAX_JSON_DEPTH(32),.MAX_PROTO_GROUP_DEPTH(16)')
        change('if(successes<150 || errors<50 || rx_stalls<100)$fatal(1,"Insufficient decoder coverage");',
            'if(successes!=32 || errors!=2)$fatal(1,"Incomplete full-default corpus");')
    change('        $finish;','''`ifdef SIMD_CANDIDATE
        assert(white_bulk>0&&plain_bulk>0&&max_step==8)else $fatal(1,"SIMD path was not exercised");
`endif
        $display("SIMD_DECODER_PASS packets=%0d committed=%0d discarded=%0d rx_beats=%0d rx_stalls=%0d cycles=%0d white_bulk=%0d plain_bulk=%0d max_step=%0d",packet_count,successes,errors,rx_beats,rx_stalls,cycles,white_bulk,plain_bulk,max_step);
        $finish;''')
    return source


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--case-set',choices=('mixed','full'),required=True);args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    folder=root/'build/validation'/args.name;folder.mkdir(parents=True,exist_ok=False)
    expected=fixture(root,folder,args.case_set);tb=adapt_testbench((root/'sim/tb_decoder.sv').read_text(),args.case_set)
    shutil.copy2(Path(__file__),folder/Path(__file__).name)
    report=dict(phase='compiling',started_utc=datetime.now(timezone.utc).isoformat(),case_set=args.case_set,
        fixture_sha256=sha(folder/'decoder_vectors.mem'),driver_sha256=sha(Path(__file__)),expected=expected,revisions={},
        full_default_decoder_parameters=args.case_set=='full',full_parser_transport_verified=False,
        full_system_complete=False)
    output=folder/'report.json'
    def save():output.write_text(json.dumps(report,indent=2)+'\n')
    try:
        for revision in('baseline','candidate'):
            source=root/'build/wsl-reports/raw_envelope_progress_format_full_native_corpus/execution-sources'if revision=='baseline'else root/'build/experiments/json-simd'
            run_folder=folder/revision;frozen=run_folder/'sources';run_folder.mkdir();inputs={}
            def freeze(path,name):
                target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);inputs[name]=sha(target)
            for path in set(closure('proto_json_decoder',source).values()):freeze(path,'rtl/'+path.name)
            (frozen/'sim').mkdir();testbench=frozen/'sim/tb_decoder.sv';testbench.write_text(tb);inputs['sim/tb_decoder.sv']=sha(testbench)
            for macro in('cdc','memory','fifo'):
                freeze(Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')/('xpm_'+macro)/'hdl'/('xpm_'+macro+'.sv'),'vendor/xpm_'+macro+'.sv')
            freeze(Path('C:/AMDDesignTools/2025.2/Vivado/data/verilog/src/glbl.v'),'vendor/glbl.v')
            shutil.copy2(folder/'decoder_vectors.mem',run_folder/'decoder_vectors.mem')
            state=dict(phase='compiling',inputs_sha256=inputs,commands=[],passed=False);report['revisions'][revision]=state;save()
            def run(command,label):
                state['commands'].append(command);save()
                with(run_folder/(label+'.log')).open('w')as log:
                    process=subprocess.Popen(command,cwd=run_folder,stdout=log,stderr=subprocess.STDOUT)
                    state['active_process']=dict(label=label,pid=process.pid);save();code=process.wait()
                assert code==0,(revision,label,code)
                text=(run_folder/(label+'.log')).read_text(errors='replace')
                assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',text,re.M),(revision,label,'native failure')
                return text
            tools=Path('C:/AMDDesignTools/2025.2/Vivado/bin')
            run([str(tools/'xvlog.bat'),'--sv','--define','OBSOLETE','--work','xpm_source','--log','vendor-compile.log']+
                [str(frozen/'vendor'/('xpm_'+macro+'.sv'))for macro in('cdc','memory','fifo')],'vendor')
            run([str(tools/'xvlog.bat'),'--log','rtl-compile.log']+[str(path)for path in sorted((frozen/'rtl').glob('*.v'))]+
                [str(frozen/'vendor/glbl.v')],'rtl')
            run([str(tools/'xvlog.bat'),'--sv']+(['--define','SIMD_CANDIDATE']if revision=='candidate'else[])+
                ['--log','testbench-compile.log',str(testbench)],'testbench')
            run([str(tools/'xelab.bat'),'--debug','off','--snapshot','decoder','-L','xpm_source','-L','unisims_ver',
                '--log','xelab.log','work.tb_decoder','work.glbl'],'elaboration')
            state['phase']='running'
            text=run('"C:\\AMDDesignTools\\2025.2\\Vivado\\bin\\xsim.bat" decoder --runall --onerror quit --onfinish quit --maxlogsize 16 --log xsim-decoder.log','simulation')
            matches=re.findall(r'^SIMD_DECODER_PASS (.+)$',text,re.M);assert len(matches)==1,'Decoder did not complete'
            values={key:int(value)for key,value in re.findall(r'(\w+)=(\d+)',matches[0])}
            assert all(values[key]==expected[key]for key in('packets','committed','discarded'))
            if revision=='candidate':assert values['white_bulk']>0 and values['plain_bulk']>0 and values['max_step']==8
            assert all(sha(frozen/name)==digest for name,digest in inputs.items())
            state.update(phase='passed',passed=True,acceptance=values,error_results=re.findall(r'^DECODER_ERROR_RESULT (.+)$',text,re.M));save()
        baseline=report['revisions']['baseline'];candidate=report['revisions']['candidate']
        assert baseline['error_results']==candidate['error_results']
        assert baseline['acceptance']['rx_beats']==candidate['acceptance']['rx_beats']
        report.update(phase='native_scalar_and_simd_decoders_passed',passed=True,
            scalar_to_simd_cycle_ratio=baseline['acceptance']['cycles']/candidate['acceptance']['cycles'])
    except BaseException as error:
        report.update(phase='native_json_simd_decoder_failed',passed=False,error=str(error));raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps(dict(phase=report['phase'],case_set=args.case_set,expected=expected,
        acceptance={name:record['acceptance']for name,record in report['revisions'].items()},scalar_to_simd_cycle_ratio=report['scalar_to_simd_cycle_ratio'])))


if __name__=='__main__':main()
