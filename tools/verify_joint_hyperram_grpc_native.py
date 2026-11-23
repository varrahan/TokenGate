"""Independent native h2/tiktoken oracle for the full 76/31 controller test.

Reads actual accepted wire beats, DMA IDs and GPU descriptors. Native HTTP/2
request bytes are rebuilt using actual hardware SETTINGS, not a synthetic peer.
"""
import argparse
import codecs
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import shutil

from h2.config import H2Configuration
from h2.connection import H2Connection
import tiktoken


def varint(value):
    result=bytearray()
    while value>127:result.append(value&127|128);value>>=7
    result.append(value)
    return bytes(result)


def request(client,stream,mode,text):
    client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
        (':path','/parser.Tokenize/Proto' if mode==2 else '/parser.Tokenize/Json'),
        ('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json'),('te','trailers')])
    raw=text.encode('utf8')
    body=json.dumps({'prompt':text},ensure_ascii=False,separators=(',',':')).encode() if mode==0 else b'\x0a'+varint(len(raw))+raw
    record=b'\0'+len(body).to_bytes(4,'big')+body
    for offset in range(0,len(record),16384):
        client.send_data(stream,record[offset:offset+16384],end_stream=offset+16384>=len(record))
    return client.data_to_send()


def load_frames(path):
    frames=defaultdict(list);partial=bytearray();owner=None;beats=0
    for line in path.read_text().splitlines():
        epoch,case,last,keep,data=line.split();key=(int(epoch),int(case))
        assert int(last) in (0,1)
        keep=int(keep,16);data=int(data,16)
        assert keep>0
        if not partial:owner=key
        assert owner==key,'A hardware frame crossed the test scheduling boundary'
        partial.extend(data>>(8*lane)&255 for lane in range(64) if keep>>lane&1)
        beats+=1
        if int(last):
            raw=bytes(partial)
            assert len(raw)>=9 and int.from_bytes(raw[:3],'big')+9==len(raw),'Actual AXIS TLAST did not delimit one HTTP/2 frame'
            frames[key].append(raw);partial.clear();owner=None
    assert not partial
    assert set(frames)=={(epoch,case) for epoch in range(2) for case in range(-1,16)}
    return frames,beats


def load_ids(path,*,gpu=False):
    result=defaultdict(list)
    for line in path.read_text().splitlines():
        values=list(map(int,line.split()));assert len(values)==(5 if gpu else 4)
        epoch,case,ordinal,token=values[:4]
        assert epoch in (0,1) and 0<=case<16 and ordinal==len(result[epoch,case]) and 0<=token<100277
        result[epoch,case].append((token,values[4]) if gpu else token)
    assert set(result)=={(epoch,case) for epoch in range(2) for case in range(16)}
    return result


def verify(folder,root):
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read=lambda p:json.loads(p.read_text())
    report=read(folder/'report.json');generation=read(folder/'generation.json');ref=read(folder/'reference.json')
    assert report['phase']=='native_simulation_completed_protocol_oracle_pending' and report['simulation_passed']
    assert report['generation_sha256']==sha(folder/'generation.json')
    assert report['inputs_sha256']==generation['outputs_sha256']
    for n,h in report['inputs_sha256'].items():assert sha(folder/n)==h,n
    for n,h in report['outputs_sha256'].items():assert sha(folder/n)==h,n
    assert report['driver_sha256']==sha(folder/'run_joint_hyperram_grpc_native.py')
    assert report['production_compiled_as_verilog'] and report['native_vendor_memory'] and not report['portable_backend']
    assert report['normal_global_startup'] and report['testbench_assertions_enabled'] and report['compatibility_defines']==['OBSOLETE']
    assert (report['parser_modules'],report['tokenizer_modules'],report['parser_memory_fabric_modules'])==(76,31,4)
    assert report['parser_application_memory_clients']==19 and report['parser_fabric_clients']==20
    assert report['real_host_route_configuration_client']
    production=sorted((folder/'joint/rtl').glob('*.v'))+[folder/'joint/vendor/glbl.v']
    expected_project=''.join('verilog work "'+p.relative_to(folder).as_posix()+'"\n' for p in production)
    assert (folder/'production.prj').read_text()==expected_project
    compile_log=(folder/'production.log').read_text(errors='replace')
    assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',compile_log,re.M)
    assert all(p.name in compile_log for p in production)
    bfm_folder=root/'build/validation/joint_parser_axi_bfm_v2_20261122'
    bfm=read(bfm_folder/'report.json')
    assert bfm['passed']
    assert bfm['model_sha256']==sha(folder/'joint_parser_axi_memory.svh')==sha(bfm_folder/'joint_parser_axi_memory.svh')
    assert bfm['test_sha256']==sha(bfm_folder/'test.sv') and bfm['log_sha256']==sha(bfm_folder/'xsim.log')
    assert bfm['driver_sha256']==sha(bfm_folder/'verify_joint_parser_axi_bfm.py')
    assert (bfm_folder/'xsim.log').read_text().count('JOINT_PARSER_AXI_MEMORY_TEST_PASS')==1
    pair=read(root/'build/validation/dual-fpga-hyperram.json')
    assert pair['key']=='f3b6d1f0079b34d7'
    native=root/'build/validation/dual_fpga_hyperram_order_v4_20261122'
    parent=read(native/'report.json')
    assert parent['passed'] and parent['elaboration_verified']
    assert generation['native_assembly_inputs_sha256']==parent['inputs_sha256']
    for n,h in parent['inputs_sha256'].items():
        if n.startswith('joint/'):assert sha(folder/n)==h,n
    vendor=Path('C:/AMDDesignTools/2025.2/Vivado/data/ip/xpm')
    for name in ('cdc','memory','fifo'):
        assert sha(folder/'joint/vendor'/('xpm_'+name+'.sv'))==sha(vendor/('xpm_'+name)/'hdl'/('xpm_'+name+'.sv'))
    log=(folder/'xsim.log').read_text(errors='replace')
    assert log.count('JOINT_HYPERRAM_GRPC_FULL_CORPUS_PASS')==1
    assert not re.search(r'^\s*(?:Fatal|Error|ERROR|FATAL):',log,re.M)
    assert len(re.findall(r'^JOINT_CORPUS_CASE ',log,re.M))==32
    for epoch in range(2):
        for operation in ('WRITE','READ'):
            progress=list(map(int,re.findall(r'^JOINT_IMAGE_'+operation+' epoch='+str(epoch)+r' bytes=(\d+)',log,re.M)))
            assert progress==list(range(1048576,8388609,1048576))
        assert re.findall(r'^JOINT_ROUTE_EPOCH epoch='+str(epoch)+r' entry=(\d+) model_epoch=(\d+)',log,re.M)==[(str(i),str(23+epoch)) for i in range(2)]
    corpus=read(root/'build/validation/json-simd-corpus.json')
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    assert corpus['key']=='2509134d2630b47e' and corpus['full_native_corpus_verified']
    reference_path=original/'build/bidirectional-fixtures/reference_cases.json'
    assert sha(reference_path)==corpus['inputs_sha256']['build/bidirectional-fixtures/reference_cases.json']
    prompts=read(reference_path)['cases'];assert len(prompts)==16
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    base=tiktoken.get_encoding('cl100k_base')
    mapping=bytes.maketrans(b'eE',b'Ee')
    swapped=tiktoken.Encoding(name='joint_native_eE_swap',pat_str=base._pat_str,
        mergeable_ranks={key.translate(mapping):value for key,value in base._mergeable_ranks.items()},special_tokens=base._special_tokens)
    encodings=(base,swapped)
    assert all(len(e._mergeable_ranks)==100256 and len(e._special_tokens)==5 for e in encodings)
    frames,beats=load_frames(folder/'wire.log');dma=load_ids(folder/'dma.log');gpu=load_ids(folder/'gpu.log',gpu=True)
    assert sum(map(len,dma.values()))==sum(map(len,gpu.values()))==11091
    calls=[];complete=0
    for epoch,encoding in enumerate(encodings):
        client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'))
        client.initiate_connection();client.update_settings({4:1<<20});client.increment_flow_control_window(1<<20)
        initial=client.data_to_send()
        assert initial==bytes.fromhex(ref['epochs'][epoch]['initial_request_hex'])
        # These are the ACTUAL hardware server SETTINGS and initialization ACKs.
        initial_events=[]
        for raw in frames[epoch,-1]:initial_events+=client.receive_data(raw)
        assert sum(type(e).__name__=='RemoteSettingsChanged' for e in initial_events)==1
        values=iter(map(int,(folder/('epoch'+str(epoch)+'.vectors')).read_text().split()))
        size=next(values);assert bytes(next(values) for _ in range(size))==initial
        assert next(values)==16
        for index,prompt in enumerate(prompts):
            stream=index*2+1;mode=2 if index&1 else 0;text=bytes.fromhex(prompt['prompt_utf8_hex']).decode('utf8')
            expected_ids=encoding.encode_ordinary(text)
            if epoch==0:assert expected_ids==prompt['token_ids']
            expected_request=request(client,stream,mode,text)
            case=ref['epochs'][epoch]['cases'][index]
            assert case['raw_request_hex']==expected_request.hex(),'Request differs when actual hardware SETTINGS are applied'
            assert case['raw_sha256']==hashlib.sha256(expected_request).hexdigest()
            assert case['native_token_ids']==expected_ids
            fields=[next(values) for _ in range(6)]
            assert fields==[index,stream,mode,100+int(mode==2),len(expected_request),len(expected_ids)]
            assert bytes(next(values) for _ in range(fields[4]))==expected_request
            assert [next(values) for _ in range(fields[5])]==expected_ids
            actual_ids=dma[epoch,index]
            assert actual_ids==expected_ids
            assert gpu[epoch,index]==[(token,int(i+1==len(actual_ids))) for i,token in enumerate(actual_ids)]
            decoder=codecs.getincrementaldecoder('utf8')('replace');expected=bytearray()
            for ordinal,token in enumerate(actual_ids):
                decoded=decoder.decode(encoding.decode_single_token_bytes(token),final=ordinal+1==len(actual_ids))
                raw=decoded.encode('utf8')
                payload=json.dumps({'choices':[{'delta':{'content':decoded}}]},ensure_ascii=False,separators=(',',':')).encode() if mode==0 else varint(17<<3|2)+varint(len(raw))+raw
                expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
            events=[]
            for frame in frames[epoch,index]:events+=client.receive_data(frame)
            responses=[e for e in events if type(e).__name__=='ResponseReceived']
            trailers=[e for e in events if type(e).__name__=='TrailersReceived']
            ended=[e for e in events if type(e).__name__=='StreamEnded']
            assert len(responses)==len(trailers)==len(ended)==1
            assert all(getattr(e,'stream_id',stream)==stream for e in events if type(e).__name__!='WindowUpdated'),'Response escaped its original stream'
            assert all(e.stream_id in (0,stream) for e in events if type(e).__name__=='WindowUpdated')
            assert responses[0].headers==[(':status','200'),('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json')]
            assert trailers[0].headers==[('grpc-status','0')]
            actual=b''.join(e.data for e in events if type(e).__name__=='DataReceived')
            assert actual==bytes(expected),('Native response differs',epoch,index)
            assert not any(type(e).__name__ in ('StreamReset','ConnectionTerminated') for e in events)
            complete+=1
            calls.append(dict(epoch=epoch,case=index,stream=stream,format=mode,tokens=len(actual_ids),
                raw_request_bytes=len(expected_request),response_record_bytes=len(actual),response_sha256=hashlib.sha256(actual).hexdigest(),
                native_wire_frames=len(frames[epoch,index])))
        assert next(values,None) is None
        initial_parser=(folder/'parser-image.bin').read_bytes()
        final_parser=(folder/('parser-final'+str(epoch)+'.bin')).read_bytes()
        initial_tokenizer=(folder/('image'+str(epoch)+'.bin')).read_bytes()
        final_tokenizer=(folder/('tokenizer-final'+str(epoch)+'.bin')).read_bytes()
        assert len(initial_parser)==len(final_parser)==len(initial_tokenizer)==len(final_tokenizer)==8388608
        floor=ref['protected_model_bytes'];assert floor==6903552
        assert final_parser[:floor]==initial_parser[:floor] and final_tokenizer[:floor]==initial_tokenizer[:floor]
        route_base=ref['base_configuration']['cfg_route_base']
        for entry in range(2):
            start=route_base+32*entry
            before=initial_parser[start:start+32];after=final_parser[start:start+32]
            assert before[:20]==after[:20] and before[24:]==after[24:]
            assert int.from_bytes(after[20:24],'little')==23+epoch
        assert hashlib.sha256(initial_tokenizer).hexdigest()==ref['epochs'][epoch]['image_sha256']
    assert complete==32 and [sum(c['tokens'] for c in calls if c['epoch']==e) for e in range(2)]==[2828,8263]
    return dict(phase='native_joint_hyperram_grpc_full_corpus_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        parser_modules=76,tokenizer_modules=31,parser_memory_fabric_modules=4,native_complete_grpc_calls=32,
        actual_dma_ids=11091,actual_captured_dma_ids_returned=11091,full_image_bytes_each=8388608,
        full_image_program_bursts=262144,full_image_readback_bursts=262144,native_wire_frames=sum(map(len,frames.values())),
        parser_application_memory_clients=19,parser_fabric_clients=20,actual_host_route_epoch_write_readback_commands=8,
        accepted_wire_beats=beats,native_tokenizer_version=version('tiktoken'),native_http2_version=version('h2'),
        native_requests_rebuilt_against_actual_hardware_settings=True,both_full_models_verified=True,
        complete_model_prefixes_immutable=True,actual_parser_cache_and_arbiter=True,actual_tokenizer_hyperram_controller=True,
        explicit_host_directory_retirement=True,whole_rpc_gpu_image_authority_verified=False,
        physical_interfaces_verified=False,full_protocol_fault_matrix_verified=False,sustained_line_rate_verified=False,
        full_pair_timing_verified=False,full_system_complete=False,calls=calls,
        exact_parser_axi_device_test_sha256=sha(bfm_folder/'report.json'),production_project_sha256=sha(folder/'production.prj'),
        report_sha256=sha(folder/'report.json'),generation_sha256=sha(folder/'generation.json'),
        actual_inputs_sha256=report['inputs_sha256'],actual_outputs_sha256=report['outputs_sha256'])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.name)
    root=Path(__file__).resolve().parents[1];folder=root/'build/validation'/args.name
    result=verify(folder,root)
    result['verifier_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    evidence=root/'build/validation/joint-hyperram-grpc-evidence'/result['key'];evidence.mkdir(parents=True,exist_ok=False)
    (evidence/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    shutil.copy2(Path(__file__),evidence/Path(__file__).name)
    (root/'build/validation/joint-hyperram-grpc.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','native_complete_grpc_calls','actual_dma_ids','full_system_complete')}))


if __name__=='__main__':main()
