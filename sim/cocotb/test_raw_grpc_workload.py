"""All original prompt references through native gRPC and actual DMA returns."""
import codecs
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'native-vendor'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import with_timeout
from test_raw_grpc_enveloped import Bench,varint
from test_http2_prefill import Bench as RawBench,value
from test_two_fpga_application import SeparateMemory
from test_tokenizer_mmio import cycles


class CorpusBench(Bench):
    async def wait(self,name):
        if name not in('completion_valid','packet_result_valid'):return await super().wait(name)
        # The small reset fixture's 400 us limit is shorter than a full BPE
        # merge on long repeated words or storage of the 16 KiB request packet.
        # Keep a finite full-workload bound for those two operations.
        try:await with_timeout(RawBench.wait(self,name),40,timeout_unit='ms')
        except cocotb.triggers.SimTimeoutError:
            raise AssertionError(('Full-corpus timeout',name,self.phase,self.statistics(),
                dict(forward_state=value(self.d.dut.core.forward,'state'),
                    return_pending=value(self.d.dut.core,'return_pending'),
                    fabric_idle=value(self.d,'fabric_idle'),
                    response_recovery_required=value(self.d,'response_recovery_required'))))


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def complete_prompt_corpus_uses_native_grpc_and_actual_dma(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text())
    references=json.loads((folder/'reference_cases.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    image=bytearray(b''.join(int(s,16).to_bytes(8,'little')for s in(folder/'memory.mem').read_text().splitlines()))
    assert hashlib.sha256(image).hexdigest()==manifest['loaded_image_sha256']
    initial=bytes(image);memory=SeparateMemory(d,image);b=CorpusBench(d,layout,memory,reverse)
    b.set(rst=1,s_axis_generated_tvalid=0,response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
        maintenance_grant=1,admit_packets=1,admit_messages=1,rpc_error_ready=1,queue_cfg_clear=1)
    b.configure();cocotb.start_soon(Clock(d.clk,4,unit='ns').start());cocotb.start_soon(memory.run())
    for worker in(b.ready_driver(),b.observe(),b.actual_observer(),b.observe_generated()):cocotb.start_soon(worker)
    await cycles(d,5);b.set(rst=0)
    for prefix in('queue','stream'):
        await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
        assert value(d,prefix+'_cfg_status')==0;await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
    await b.directory(4);await b.open()
    # Actual peer SETTINGS and WINDOW_UPDATE provision sufficient send credit
    # for the corpus. No fixture writes or out-of-band credit callbacks exist.
    b.client.update_settings({4:1<<20});b.client.increment_flow_control_window(1<<20)
    tag=1;await b.packet(0,tag,b.client.data_to_send(),1);tag+=1
    calls=[];returned=0
    for index,reference in enumerate(references['cases']):
        stream=2*index+1;mode=0 if index%2==0 else 2;application=100+int(mode==2)
        text=bytes.fromhex(reference['prompt_utf8_hex']);expected_ids=reference['token_ids']
        body=json.dumps({'prompt':text.decode()},ensure_ascii=False,separators=(',',':')).encode()if mode==0 else b'\x0a'+varint(len(text))+text
        b.client.send_headers(stream,[(':method','POST'),(':scheme','https'),(':authority','parser.test'),
            (':path','/parser.Tokenize/Json'if mode==0 else'/parser.Tokenize/Proto'),
            ('content-type','application/grpc+json'if mode==0 else'application/grpc+proto'),('te','trailers')])
        record=b'\0'+len(body).to_bytes(4,'big')+body
        for offset in range(0,len(record),16384):
            b.client.send_data(stream,record[offset:offset+16384],end_stream=offset+16384>=len(record))
        await b.packet(0,tag,b.client.data_to_send(),1);tag+=1
        await b.drain(0,stream,application,expected_ids);actual_ids=list(b.received)
        assert actual_ids==expected_ids
        decoder=codecs.getincrementaldecoder('utf8')('replace');expected=bytearray()
        for ordinal,token in enumerate(actual_ids):
            eos=int(ordinal+1==len(actual_ids))
            await b.gpu(stream,token,ordinal,eos,mode);returned+=1
            # Reconstruct from the independent native fixture's token bytes;
            # incremental decoding preserves partial UTF-8 across GPU chunks.
            original=reverse['cases'][index]['chunks'][ordinal]
            assert original['token']==token
            raw=bytes.fromhex(original['bow_hex']);decoded=decoder.decode(raw,final=bool(eos)).encode()
            payload=json.dumps({'choices':[{'delta':{'content':decoded.decode()}}]},ensure_ascii=False,separators=(',',':')).encode()if mode==0 else varint(17<<3|2)+varint(len(decoded))+decoded
            expected.extend(b'\0'+len(payload).to_bytes(4,'big')+payload)
            if returned%256==0:d._log.info('Returned %d actual DMA IDs through native gRPC',returned)
        assert bytes(b.response_records[stream])==expected
        assert('StreamEnded',stream)in b.client_events and not value(d,'response_recovery_required')
        calls.append(dict(reference_index=index,stream=stream,format=mode,tokens=len(actual_ids),
            response_record_bytes=len(expected),response_sha256=hashlib.sha256(expected).hexdigest()))
        # This is explicit host retirement through the actual directory service.
        # Automatic whole-RPC/GPU/image lifetime retirement remains unverified.
        await b.directory(3,0,stream)
        d._log.info('Completed native corpus call %d: %d actual DMA IDs',index,len(actual_ids))
    assert len(calls)==16 and returned==b.ids==2828 and len(b.generated_accepts)==2828
    assert len([e for e in b.client_events if e[0]=='StreamEnded'])==16
    assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
    assert not any(b.pending)and not b.packet_bytes and not value(d,'response_record_lease_active')
    accepted=dict(phase='passed',native_grpc_calls=calls,actual_forward_dma_ids=b.ids,actual_captured_dma_ids_returned=returned,
        actual_gpu_descriptors_accepted=len(b.generated_accepts),native_complete_grpc_calls=16,native_wire_frames=len(b.wire),
        actual_raw_packets=b.packets,actual_header_bindings=b.headers,parser_memory_clients=17,tokenizer_memory_clients=9,
        native_request_and_response_endpoints=True,actual_peer_settings_and_window_updates=True,
        original_prompt_corpus_verified=True,json_and_protobuf_response_fields_verified=True,
        complete_model_prefix_immutable=True,explicit_host_directory_retirement=True,
        sse_transport_verified=False,receive_flow_control_verified=False,whole_rpc_gpu_image_lease_verified=False,
        physical_interfaces_verified=False,full_system_complete=False)
    Path('acceptance.json').write_text(json.dumps(accepted,indent=2)+'\n');d._log.info('PASS: %s',accepted)
