"""Audit one completed full epoch while the complete two-model job continues."""
import argparse
import codecs
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from h2.config import H2Configuration
from h2.connection import H2Connection
import tiktoken
from verify_joint_hyperram_grpc_native import request,varint


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--epoch',type=int,choices=(0,1),required=True);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_]+',args.name)
    root=Path(__file__).resolve().parents[1];folder=root/'build/validation'/args.name;e=args.epoch
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
    report=read(folder/'report.json');reference=read(folder/'reference.json')
    assert report['phase'] in ('simulating','native_simulation_completed_protocol_oracle_pending','native_joint_workload_failed')
    assert all(sha(folder/n)==h for n,h in report['inputs_sha256'].items())
    log=(folder/'simulation-stdout.log').read_text(errors='replace')
    completed=list(map(int,re.findall(r'^JOINT_CORPUS_CASE epoch='+str(e)+r' case=(\d+) ',log,re.M)))
    assert completed==list(range(16)),completed
    host_routes=report.get('real_host_route_configuration_client',False)
    if host_routes:
        assert report['parser_fabric_clients']==20 and report['parser_application_memory_clients']==19
        assert re.findall(r'^JOINT_ROUTE_EPOCH epoch='+str(e)+r' entry=(\d+) model_epoch=(\d+)',log,re.M)==[(str(i),str(23+e)) for i in range(2)]
    # The epoch bank dumps are emitted only after all sixteen cases retire.
    for side in ('parser','tokenizer'):assert (folder/(side+'-final'+str(e)+'.bin')).stat().st_size==8388608
    original=root/'build/wsl-reports/raw_envelope_json_simd_full_native_corpus_20261122/execution-sources'
    corpus=read(root/'build/validation/json-simd-corpus.json');assert corpus['key']=='2509134d2630b47e'
    prompts_path=original/'build/bidirectional-fixtures/reference_cases.json'
    assert sha(prompts_path)==corpus['inputs_sha256']['build/bidirectional-fixtures/reference_cases.json']
    prompts=read(prompts_path)['cases'];assert len(prompts)==16
    frames=defaultdict(list);partial=bytearray();owner=None;selected_wire=[]
    for line in (folder/'wire.log').read_text().splitlines():
        fields=line.split()
        if fields and int(fields[0])!=e:continue
        assert len(fields)==5,fields
        epoch,case,last=map(int,fields[:3]);keep=int(fields[3],16);data=int(fields[4],16)
        assert epoch==e and -1<=case<16 and last in (0,1) and keep>0
        if not partial:owner=case
        assert owner==case
        partial.extend(data>>(lane*8)&255 for lane in range(64) if keep>>lane&1);selected_wire.append(line)
        if last:
            raw=bytes(partial);assert len(raw)>=9 and int.from_bytes(raw[:3],'big')+9==len(raw)
            frames[case].append(raw);partial.clear();owner=None
    assert not partial and set(frames)==set(range(-1,16))
    dma=defaultdict(list);gpu=defaultdict(list);selected_dma=[];selected_gpu=[]
    for name,target,selected in (('dma.log',dma,selected_dma),('gpu.log',gpu,selected_gpu)):
        for line in (folder/name).read_text().splitlines():
            fields=list(map(int,line.split()))
            if fields[0]!=e:continue
            assert len(fields)==(4 if name=='dma.log' else 5)
            epoch,case,ordinal,token=fields[:4];assert 0<=case<16 and ordinal==len(target[case])
            target[case].append(token if name=='dma.log' else (token,fields[4]));selected.append(line)
    os.environ['TIKTOKEN_CACHE_DIR']=str(root/'build/tiktoken-cache')
    encoding=tiktoken.get_encoding('cl100k_base')
    if e==1:
        mapping=bytes.maketrans(b'eE',b'Ee')
        encoding=tiktoken.Encoding(name='joint_epoch_eE_swap',pat_str=encoding._pat_str,
            mergeable_ranks={k.translate(mapping):v for k,v in encoding._mergeable_ranks.items()},special_tokens=encoding._special_tokens)
    client=H2Connection(H2Configuration(client_side=True,header_encoding='utf8'))
    client.initiate_connection();client.update_settings({4:1<<20});client.increment_flow_control_window(1<<20)
    assert client.data_to_send().hex()==reference['epochs'][e]['initial_request_hex']
    initial_events=[]
    for raw in frames[-1]:initial_events+=client.receive_data(raw)
    assert sum(type(v).__name__=='RemoteSettingsChanged' for v in initial_events)==1
    calls=[]
    for index,prompt in enumerate(prompts):
        mode=2 if index&1 else 0;stream=index*2+1;text=bytes.fromhex(prompt['prompt_utf8_hex']).decode('utf8')
        assert request(client,stream,mode,text).hex()==reference['epochs'][e]['cases'][index]['raw_request_hex']
        ids=encoding.encode_ordinary(text);assert dma[index]==ids
        assert gpu[index]==[(token,int(i+1==len(ids))) for i,token in enumerate(ids)]
        decoder=codecs.getincrementaldecoder('utf8')('replace');expected=bytearray()
        for ordinal,token in enumerate(dma[index]):
            decoded=decoder.decode(encoding.decode_single_token_bytes(token),final=ordinal+1==len(ids));raw=decoded.encode()
            body=json.dumps({'choices':[{'delta':{'content':decoded}}]},ensure_ascii=False,separators=(',',':')).encode() if mode==0 else varint(17<<3|2)+varint(len(raw))+raw
            expected.extend(b'\0'+len(body).to_bytes(4,'big')+body)
        events=[]
        for raw in frames[index]:events+=client.receive_data(raw)
        kinds=lambda kind:[v for v in events if type(v).__name__==kind]
        responses=kinds('ResponseReceived');trailers=kinds('TrailersReceived');ended=kinds('StreamEnded')
        assert len(responses)==len(trailers)==len(ended)==1
        assert responses[0].headers==[(':status','200'),('content-type','application/grpc+proto' if mode==2 else 'application/grpc+json')]
        assert trailers[0].headers==[('grpc-status','0')]
        assert all(getattr(v,'stream_id',stream)==stream for v in events if type(v).__name__!='WindowUpdated')
        assert all(v.stream_id in (0,stream) for v in kinds('WindowUpdated'))
        assert not kinds('StreamReset') and not kinds('ConnectionTerminated')
        actual=b''.join(v.data for v in kinds('DataReceived'));assert actual==bytes(expected),(e,index)
        calls.append(dict(case=index,stream=stream,tokens=len(ids),response_record_bytes=len(actual),response_sha256=hashlib.sha256(actual).hexdigest()))
    expected_tokens=(2828,8263)[e];assert sum(len(ids) for ids in dma.values())==expected_tokens
    floor=reference['protected_model_bytes'];assert floor==6903552
    parser=(folder/'parser-image.bin').read_bytes();tokenizer=(folder/('image'+str(e)+'.bin')).read_bytes()
    assert (folder/('parser-final'+str(e)+'.bin')).read_bytes()[:floor]==parser[:floor]
    assert (folder/('tokenizer-final'+str(e)+'.bin')).read_bytes()[:floor]==tokenizer[:floor]
    if host_routes:
        final=(folder/('parser-final'+str(e)+'.bin')).read_bytes();base=reference['base_configuration']['cfg_route_base']
        for entry in range(2):
            start=base+32*entry;before=parser[start:start+32];after=final[start:start+32]
            assert after[:20]==before[:20] and after[24:]==before[24:] and int.from_bytes(after[20:24],'little')==23+e
    result=dict(phase='completed_native_joint_epoch_independently_verified',verified_utc=datetime.now(timezone.utc).isoformat(),
        run=args.name,epoch=e,model_epoch=23+e,native_complete_grpc_calls=16,actual_captured_dma_ids_returned=expected_tokens,
        actual_dma_ids=expected_tokens,native_wire_frames=sum(map(len,frames.values())),native_requests_rebuilt_against_actual_hardware_settings=True,
        full_image_bytes=8388608,protected_model_bytes=floor,complete_model_prefixes_immutable=True,
        actual_tokenizer_hyperram_controller=True,whole_two_epoch_workload_verified=False,full_system_complete=False,
        real_host_route_epoch_write_readback_verified=host_routes,
        calls=calls,input_hashes=report['inputs_sha256'],final_bank_sha256={side:sha(folder/(side+'-final'+str(e)+'.bin')) for side in ('parser','tokenizer')},
        verifier_sha256=sha(Path(__file__)),helper_sha256=sha(root/'tools/verify_joint_hyperram_grpc_native.py'))
    result['key']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()[:16]
    target=root/'build/validation/joint-hyperram-grpc-epoch-evidence'/result['key'];target.mkdir(parents=True,exist_ok=False)
    for name,lines in (('wire.log',selected_wire),('dma.log',selected_dma),('gpu.log',selected_gpu)):
        (target/name).write_text('\n'.join(lines)+'\n')
    shutil.copy2(Path(__file__),target/Path(__file__).name)
    shutil.copy2(root/'tools/verify_joint_hyperram_grpc_native.py',target/'verify_joint_hyperram_grpc_native.py')
    (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'build/validation'/('joint-hyperram-grpc-epoch'+str(e)+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','key','epoch','native_complete_grpc_calls','actual_dma_ids','native_wire_frames','whole_two_epoch_workload_verified')}))


if __name__=='__main__':main()
