"""Full native 32-call corpus with real AXI-Lite schema programming.

Preserves the passed native two-image workload, controller and device models.
Only schema payload keys/tags, their actual host configuration, and production
configuration wiring change. All original prompt/model combinations remain.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from h2.config import H2Configuration
from h2.connection import H2Connection
from hyperframe.frame import SettingsFrame

from generate_hyperram_cdc_timing_harness import ports
from generate_http2_schema_mmio_application import BUS, MANUAL, render
from generate_joint_hyperram_grpc_vectors import varint
from verify_two_fpga_application import closure


SCHEMAS = [dict(json_key='message',protobuf_field=37,transport_schema_epoch=10),
           dict(json_key='content',protobuf_field=2712,transport_schema_epoch=11)]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    audit=read(root/'build/validation/joint-hyperram-grpc.json');assert audit['key']=='2e24ad59fccef5f2'
    parent=root/'build/validation/joint_hyperram_grpc_full_v5_20261122'
    report=read(parent/'report.json');assert sha(parent/'report.json')==audit['report_sha256']
    assert report['simulation_passed']
    target=root/'build/experiments'/args.name;target.mkdir(parents=True,exist_ok=False)
    for name,digest in report['inputs_sha256'].items():
        assert sha(parent/name)==digest,name
        destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/name,destination)
    application=root/'build/experiments/http2-schema-mmio-application-v2'
    app_generation=read(application/'generation.json')
    assert all(sha(application/n)==h for n,h in app_generation['outputs_sha256'].items())
    generated,_,body=render((parent/'joint/rtl/http2_enveloped_parser_application.v').read_text())
    assert generated.encode()==(application/'rtl/http2_schema_mmio_application.v').read_bytes()
    for name in ('http2_schema_mmio_application.v','parser_schema_mmio.v'):
        shutil.copy2(application/'rtl'/name,target/'joint/rtl'/name)
    route_source=(parent/'joint/rtl/http2_route_lookup.v').read_text()
    route_offsets={}
    for name in ('schema','model'):
        field=re.search(r'result_'+name+r'_epoch<=record_data\[(\d+):(\d+)\]',route_source)
        assert field and int(field[1])-int(field[2])==31 and int(field[2])%8==0
        route_offsets[name+'_epoch']=int(field[2])//8
    assert route_offsets==dict(schema_epoch=16,model_epoch=20)
    assert 'record_data[255:192]==0' in route_source
    joint_path=target/'joint/rtl/two_fpga_hyperram_application.v';joint=joint_path.read_text()
    old_interface=ports(joint,'two_fpga_hyperram_application')
    removed={'parser_'+n for n in MANUAL}
    added=[(d,w,'parser_'+n) for d,w,n in BUS]
    interface=[p for p in old_interface if p[2] not in removed]+added
    end=joint.index(');')+2;prefix=joint[:joint.index(')(\n')+3]
    new_body=joint[end:]
    a=new_body.index('http2_enveloped_parser_application #(');b=new_body.index('\n);',a)
    instance=new_body[a:b].replace('http2_enveloped_parser_application','http2_schema_mmio_application',1)
    for name in sorted(MANUAL):
        instance,count=re.subn(r'^\s*\.'+name+r'\(parser_'+name+r'\),?\n','\n',instance,flags=re.M);assert count==1,name
    instance += ',\n'+',\n'.join(f'    .{n}(parser_{n})' for _,_,n in BUS)
    new_body=new_body[:a]+instance+new_body[b:]
    joint_new=prefix+',\n'.join(f'    {d} wire {w} {n}' for d,w,n in interface)+'\n);'+new_body
    assert ports(joint_new,'two_fpga_hyperram_application')==interface
    joint_path.write_bytes(joint_new.encode())
    parser_dependencies=closure('http2_schema_mmio_application',target/'joint');assert len(parser_dependencies)==77
    ref=read(target/'reference.json');ref['schemas']=SCHEMAS
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    prompts=read(original/'build/bidirectional-fixtures/reference_cases.json')['cases']
    assert len(prompts)==16
    for epoch,schema in enumerate(SCHEMAS):
        client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'))
        client.initiate_connection();client.update_settings({4:1<<20});client.increment_flow_control_window(1<<20)
        initial=client.data_to_send();assert initial.hex()==ref['epochs'][epoch]['initial_request_hex']
        peer=SettingsFrame(0);peer.settings={1:4096,5:16384,6:32768};client.receive_data(peer.serialize())
        values=[len(initial),*initial,16]
        for index,(prompt,case) in enumerate(zip(prompts,ref['epochs'][epoch]['cases'])):
            raw_text=bytes.fromhex(prompt['prompt_utf8_hex']);stream=case['stream'];mode=case['mode']
            payload=(json.dumps({schema['json_key']:raw_text.decode('utf8')},ensure_ascii=False,separators=(',',':')).encode()
                if mode==0 else varint(schema['protobuf_field']<<3|2)+varint(len(raw_text))+raw_text)
            client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
                (':path','/parser.Tokenize/Proto' if mode==2 else '/parser.Tokenize/Json'),
                ('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json'),('te','trailers')])
            record=b'\0'+len(payload).to_bytes(4,'big')+payload
            for offset in range(0,len(record),16384):client.send_data(stream,record[offset:offset+16384],end_stream=offset+16384>=len(record))
            raw=client.data_to_send();ids=case['native_token_ids']
            values += [index,stream,mode,case['application'],len(raw),len(ids),*raw,*ids]
            case.update(raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),raw_request_hex=raw.hex())
        (target/f'epoch{epoch}.vectors').write_text(' '.join(map(str,values))+'\n')
    ref.update(schema_mmio_programming=True,parent_joint_audit_key=audit['key'],
        schema_payloads_changed_only=True,route_schema_epochs_programmed_through_actual_host_client=True,
        fixture_sha256={n:sha(target/n) for n in ('epoch0.vectors','epoch1.vectors','image0.bin','image1.bin','parser-image.bin')})
    (target/'reference.json').write_text(json.dumps(ref,indent=2)+'\n')
    tb_path=target/'joint_hyperram_grpc_tb.sv';tb=tb_path.read_text()
    tb=tb.replace('localparam USER_WIDTH=16,CLIENTS=20,ADDR_WIDTH=23;',
        'localparam USER_WIDTH=16,CLIENTS=20,ADDR_WIDTH=23;\n'+
        f'localparam ROUTE_SCHEMA_EPOCH_OFFSET={route_offsets["schema_epoch"]},ROUTE_MODEL_EPOCH_OFFSET={route_offsets["model_epoch"]};')
    for name in sorted(removed):
        tb,count=re.subn(r'^(?:reg|wire)\s+(?:\[[^\]]+\]\s+)?'+name+r'(?:=[^;]+)?;\n','',tb,flags=re.M);assert count==1,name
        tb,count=re.subn(r'^\.'+name+r'\('+name+r'\),?\n','',tb,flags=re.M);assert count==1,name
    declarations='\n'.join(f'{"reg" if d=="input" else "wire"} {w} {n}'+('=0;' if d=='input' else ';') for d,w,n in added)
    needle='two_fpga_hyperram_application dut(';assert tb.count(needle)==1
    tb=tb.replace(needle,declarations+'\n'+needle)
    a=tb.index(needle);b=tb.index('\n);',a)
    tb=tb[:b]+',\n'+',\n'.join(f'.{n}({n})' for _,_,n in added)+tb[b:]
    assert tb.count('parser_cfg_schema_epoch=9;')==2
    tb=tb.replace('parser_cfg_schema_epoch=9;','parser_cfg_schema_epoch=10+current_epoch;')
    tb=tb.replace('`include "joint_hyperram_grpc_body.svh"','`include "joint_hyperram_grpc_schema_body.svh"')
    tb_path.write_bytes(tb.encode())
    stimulus=(parent/'joint_hyperram_grpc_body.svh').read_text()
    for before,after in [('parser_header_schema_epoch==9','parser_header_schema_epoch==10+current_epoch'),
        ('parser_generated_schema_epoch=9;','parser_generated_schema_epoch=10+current_epoch;'),
        ('parser_response_result_schema_epoch==9','parser_response_result_schema_epoch==10+current_epoch'),
        ('total_host_configuration_commands==8','total_host_configuration_commands==16&&total_schema_accepts==4&&total_schema_applies==4')]:
        assert stimulus.count(before)==1,before;stimulus=stimulus.replace(before,after)
    before='    configure_route_epochs();';assert stimulus.count(before)==1
    stimulus=stimulus.replace(before,'    program_runtime_schema();\n'+before)
    a=stimulus.index('    for(integer entry=0;entry<2;entry++)begin',stimulus.index('task automatic configure_route_epochs;'))
    b=stimulus.index('\nendtask',a)
    route='''    for(integer entry=0;entry<2;entry++)begin
        for(integer field_index=0;field_index<2;field_index++)begin
            route=integer'(parser_cfg_route_base)+entry*32+(field_index==0?ROUTE_MODEL_EPOCH_OFFSET:ROUTE_SCHEMA_EPOCH_OFFSET);
            @(negedge app_clk);host_cfg_addr=23'(route);host_cfg_data=field_index==0?32'(23+current_epoch):32'(10+current_epoch);host_cfg_write=1;
            `JOINT_SEND(host_cfg_valid,host_cfg_ready)
            `JOINT_WAIT(host_cfg_rsp_valid,2000000)
            assert(host_cfg_rsp_status==0)else $fatal(1,"Host route epoch write failed");
            `JOINT_ACK(host_cfg_rsp_valid,host_cfg_rsp_ready,9)
            @(negedge app_clk);host_cfg_write=0;
            `JOINT_SEND(host_cfg_valid,host_cfg_ready)
            `JOINT_WAIT(host_cfg_rsp_valid,2000000)
            assert(host_cfg_rsp_status==0&&host_cfg_rsp_data[31:0]==host_cfg_data)else $fatal(1,"Host route epoch readback mismatch");
            `JOINT_ACK(host_cfg_rsp_valid,host_cfg_rsp_ready,9)
        end
        $display("JOINT_ROUTE_EPOCH epoch=%0d entry=%0d model_epoch=%0d",current_epoch,entry,23+current_epoch);
        $display("JOINT_ROUTE_SCHEMA epoch=%0d entry=%0d schema_epoch=%0d",current_epoch,entry,10+current_epoch);
    end'''
    stimulus=stimulus[:a]+route+stimulus[b:]
    host=(root/'sim/joint_hyperram_schema_host.svh').read_text()
    # The macros must precede the host tasks, and declarations precede their
    # use in the established test's initial/observer blocks.
    insertion=stimulus.index('\nalways @(negedge app_clk)begin')
    stimulus=stimulus[:insertion]+'\n'+host+stimulus[insertion:]
    # Open the trace in its own time-zero block; all schema activity begins
    # only after the full memory loader and explicit store initialization.
    stimulus+='\ninitial schema_file=$fopen("schema.log","w");\n'
    needle='    $fclose(wire_file);$fclose(dma_file);$fclose(gpu_file);';assert stimulus.count(needle)==1
    stimulus=stimulus.replace(needle,needle+'$fclose(schema_file);')
    (target/'joint_hyperram_grpc_schema_body.svh').write_bytes(stimulus.encode())
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    unchanged={n:h for n,h in report['inputs_sha256'].items() if sha(target/n)==h}
    result=dict(phase='joint_hyperram_schema_full_corpus_generated',parent_joint_audit_key=audit['key'],
        parent_report_sha256=sha(parent/'report.json'),parent_inputs_sha256=report['inputs_sha256'],
        unchanged_parent_inputs_sha256=unchanged,application_generation_sha256=sha(application/'generation.json'),
        generator_sha256=sha(Path(__file__)),parser_modules=77,tokenizer_modules=31,
        additional_parser_memory_fabric_modules=4,parser_application_memory_clients=19,parser_fabric_clients=20,
        real_host_route_configuration_client=True,schema_mmio=True,host_published_schema_epoch_preserved=True,
        expected_schema_durable_applies=4,expected_host_route_configuration_commands=16,
        route_word_offsets=route_offsets,route_layout_source_sha256=sha(parent/'joint/rtl/http2_route_lookup.v'),
        complete_images=2,complete_image_bytes_each=8388608,full_corpus_sequences=32,expected_actual_dma_ids=11091,
        simulation_verified=False,global_schema_maintenance_authority_verified=False,native_timing_verified=False,full_system_complete=False,
        outputs_sha256={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()})
    (target/'generation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','parser_modules','schema_mmio','full_corpus_sequences')}))


if __name__=='__main__':main()
