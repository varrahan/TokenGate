"""Real lookup policy under malformed history and unallocated DATA streams."""
import hashlib
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from hyperframe.frame import DataFrame,Frame
from test_http2_prefill import value
from test_rpc_admission_fence import headers,settled
from test_rpc_refusal_faults import FaultBench
from test_tokenizer_mmio import cycles
from test_two_fpga_application import SeparateMemory


async def trace_policy(b,trace):
    d=b.d;c=d.dut.core;pending=None
    while True:
        await RisingEdge(d.clk)
        if value(d,'rst'):
            assert pending is None
            continue
        if not trace['active']:continue
        if value(d,'mem_valid')>>26&value(d,'mem_ready')>>26&1:
            assert pending is None
            pending=len(trace['commands'])
            trace['commands'].append(dict(index=pending,clock=b.clocks,
                address=value(d,'mem_addr')>>(26*23)&0x7fffff,write=value(d,'mem_write')>>26&1,
                bytes=value(d,'mem_bytes')>>(26*4)&15,
                data_hex=format(value(d,'mem_data')>>(26*72)&((1<<72)-1),'018x'),
                flow_operation=value(c.receive_flow,'operation'),backend_state=value(c.receive_credits,'state'),
                private_owner=value(c,'rc_credit_owner')))
        if value(d,'mem_rsp_valid')>>26&value(d,'mem_rsp_ready')>>26&1:
            assert pending is not None
            trace['responses'].append(dict(index=pending,clock=b.clocks,
                data_hex=format(value(d,'mem_rsp_data')>>(26*72)&((1<<72)-1),'018x'),
                status=value(d,'mem_rsp_status')>>(26*8)&255));pending=None
        if value(c,'rx_result_valid')and value(c,'rx_result_ready'):
            trace['results'].append(dict(clock=b.clocks,discarded=value(c,'rx_discarded'),
                status=value(c,'rx_result_status'),detail=value(c,'rx_result_detail'),memory_status=value(c,'rx_result_memory_status')))
        if value(c,'rx_drop_valid'):trace['drop_observed']=True


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def actual_directory_binding_precedes_validated_closed_history(d):
    folder=Path(os.environ['PARSER_BIDIRECTIONAL_FIXTURES'])
    layout=list(map(int,(folder/'layout.txt').read_text().split()))
    manifest=json.loads((folder/'fixture_manifest.json').read_text())
    reverse=json.loads((folder/'response_reference.json').read_text())
    initial=b''.join(int(word,16).to_bytes(8,'little')for word in(folder/'memory.mem').read_text().splitlines())
    assert len(initial)==8388608 and hashlib.sha256(initial).hexdigest()==manifest['loaded_image_sha256']
    workers=[];previous=None;cases=[]
    cocotb.start_soon(Clock(d.clk,4,unit='ns').start())
    for mode in('active-binding','bad-magic','reserved-bit','future-stream','even-stream'):
        if previous is not None:
            assert not any(previous.pending)and not previous.packet_bytes and value(d,'fabric_idle')
            assert not value(d,'m_axis_tx_tvalid')and not value(d.dut.core,'return_pending')
        d.rst.value=1;await cycles(d,4)
        for worker in workers:worker.cancel()
        await cycles(d,2)
        image=bytearray(initial);memory=SeparateMemory(d,image);b=FaultBench(d,layout,memory,reverse)
        b.expected_fence_stream=None;b.fence_rejections=[];b.allow_quarantine=True;b.release_packet=True
        b.set(rst=1,fault_client=-1,fault_target=-1,fault_arm=0,s_axis_rx_tvalid=0,
            s_axis_generated_tvalid=0,control_valid=0,command_valid=0,queue_cfg_valid=0,stream_cfg_valid=0,
            cfg_schema_valid=0,cfg_unlock=0,control_result_ready=0,rsp_ready=0,completion_ready=0,
            response_result_ready=0,m_axis_tx_tready=0,window_req_valid=0,window_rsp_ready=0,
            packet_result_ready=0,maintenance_grant=1,admit_packets=1,admit_messages=1,
            admit_new_rpcs=1,rpc_error_ready=1,queue_cfg_clear=1)
        b.configure()
        workers=[cocotb.start_soon(w)for w in(memory.parser.run(),memory.tokenizer.run(),b.ready_driver(),
            b.observe(),b.actual_observer(),b.observe_generated(),b.observe_private_credit())]
        previous=b
        await cycles(d,5);b.set(rst=0)
        for prefix in('queue','stream'):
            await b.send(prefix+'_cfg_valid',prefix+'_cfg_ready');await b.wait(prefix+'_cfg_result_valid')
            assert value(d,prefix+'_cfg_status')==0
            await b.ack(prefix+'_cfg_result_valid',prefix+'_cfg_result_ready',0)
        b.response_configuration(2);await b.directory(4);await b.open()
        await b.packet(0,1,b.client.data_to_send(),1)
        await b.packet(0,2,headers(1,b.client),1);await settled(b)
        record=b'\0\0\0\0\r\x0a\x0bhello world'
        b.client.send_data(1,record[:7]);await b.packet(0,3,b.client.data_to_send(),1);await settled(b)
        b.set(admit_new_rpcs=0);b.expected_fence_stream=3
        request=headers(3,b.client)
        # These peer bytes exist before it receives the reset. Invalid future
        # and even stream frames deliberately bypass the native client's API.
        if mode=='active-binding':
            b.client.send_data(1,record[7:]);raw=b.client.data_to_send()
        elif mode in('bad-magic','reserved-bit'):
            b.client.send_data(3,record,pad_length=7,end_stream=True);raw=b.client.data_to_send()
        else:
            frame=DataFrame(5 if mode=='future-stream'else 2);frame.data=record;frame.flags.add('END_STREAM');raw=frame.serialize()
        await b.packet(0,4,request,1);await settled(b)
        b.expected_fence_stream=None
        assert len(b.fence_rejections)==1 and ('StreamReset',3)in b.client_events
        assert (0,3)not in b.bindings
        address=layout[19]+160;saved=int.from_bytes(image[address:address+8],'little')
        assert saved==0x48325731|(3<<32)
        changed=saved^1 if mode in('active-binding','bad-magic')else saved|(1<<63)if mode=='reserved-bit'else saved
        assert not any(b.pending)and value(d,'fabric_idle')
        image[address:address+8]=changed.to_bytes(8,'little')
        trace=dict(active=True,commands=[],responses=[],results=[],drop_observed=False);b.trace=trace
        workers.append(cocotb.start_soon(trace_policy(b,trace)))
        b.release_packet=False;before=len(b.wire)
        sending=cocotb.start_soon(b.packet(0,5,raw,int(mode=='active-binding')))
        await b.wait('packet_result_valid');trace['active']=False
        result={n:value(d,n)for n in('packet_committed','packet_status','packet_detail','packet_memory_status',
            'receive_fault_valid','receive_fault_status','receive_fault_detail','receive_fault_memory_status','receive_fault_http2_error','receive_recovery_required')}
        assert len(trace['commands'])==len(trace['responses'])and b.pending[26]is None
        assert not trace['drop_observed']and not any(r['discarded']for r in trace['results'])
        assert not value(d,'fault_injected')and all(r['status']==0 for r in trace['responses'])
        debits=[c for c in trace['commands']if c['flow_operation']==1 and not c['private_owner']]
        if mode=='active-binding':
            assert result['packet_committed']==1 and result['receive_fault_valid']==result['receive_recovery_required']==0
            assert not any(c['address']==address for c in debits)
            assert image[address:address+8]==changed.to_bytes(8,'little')
        else:
            assert result['packet_committed']==0 and result['receive_fault_valid']==1
            assert result['receive_fault_memory_status']==0 and result['receive_fault_http2_error']==2
            assert (result['receive_fault_status'],result['receive_fault_detail'])==((5,23)if mode in('bad-magic','reserved-bit')else(3,10))
            assert result['receive_recovery_required']==int(mode in('bad-magic','reserved-bit'))
            history=[c for c in debits if c['address']==address]
            assert len(history)==1 and history[0]['write']==0 and history[0]['bytes']==8
            assert not any(c['write']for c in debits)
            assert b.ids==len(b.generated_accepts)==value(d,'queued_count')==value(d,'pending_count')==0
            for raw_wire in b.wire[before:]:
                frame,size=Frame.parse_frame_header(memoryview(raw_wire[:9]));frame.parse_body(memoryview(raw_wire[9:]));assert frame.type!=8
        for _ in range(17):
            await cycles(d);assert value(d,'packet_result_valid')
            assert result=={n:value(d,n)for n in result}
        b.save_state(mode+'-result');b.release_packet=True;await sending
        captured=[]
        if mode=='active-binding':
            await b.drain(0,1,101,[15339,1917]);captured=list(b.received);await settled(b)
            assert not any(b.pending)and image[address:address+8]==changed.to_bytes(8,'little')
            # Test-only repair of the injected word after the successful live
            # lookup probe has drained; this is not a production recovery API.
            image[address:address+8]=saved.to_bytes(8,'little')
            b.client.send_headers(1,[('request-finished','yes')],end_stream=True)
            await b.packet(0,6,b.client.data_to_send(),1)
            for ordinal,token in enumerate(captured):await b.gpu(1,token,ordinal,int(ordinal==1),2)
            await b.directory(3,0,1);await settled(b)
            assert ('StreamEnded',1)in b.client_events and len(b.generated_accepts)==b.ids==2
        for _ in range(100000):
            if value(d,'fabric_idle')and not any(b.pending)and not value(d,'m_axis_tx_tvalid')and not value(d.dut.core,'rx_active'):break
            await cycles(d)
        else:
            b.save_state(mode+'-drain-timeout');raise AssertionError('History policy did not drain memory and wire')
        assert image[:layout[6]]==initial[:layout[6]]and memory.tokenizer_data[:layout[6]]==initial[:layout[6]]
        for side,data in(('parser',image),('tokenizer',memory.tokenizer_data)):
            Path('history-'+mode+'-'+side+'-final.bin').write_bytes(data)
        evidence=dict(mode=mode,history_address=address,history_before_hex=format(saved,'016x'),history_probe_hex=format(changed,'016x'),
            actual_probe_packet_hex=raw.hex(),trace=trace,result=result,held_packet_result_cycles=17,
            actual_captured_dma_ids_returned=captured,actual_generated_descriptors=b.generated_accepts,
            response_records_hex={str(s):bytes(data).hex()for s,data in b.response_records.items()},
            ingress_packets=b.ingress_packets,wire_frames=[w.hex()for w in b.wire],
            header_rejections=b.fence_rejections,complete_model_prefixes_immutable=True)
        cases.append(evidence);Path('history-'+mode+'.json').write_text(json.dumps(evidence,indent=2)+'\n')
        d._log.info('Verified actual closed-history policy %s',mode)
    Path('acceptance.json').write_text(json.dumps(dict(phase='passed',cases=cases,
        all_five_lookup_policy_cases_verified=True,explicit_test_root_resets_after_memory_and_wire_drain=True,
        active_case_history_fault_repaired_only_after_probe_drained=True,
        no_production_retained_reset_or_recovery_claim=True,native_vendor_runtime_verified=False,
        whole_rpc_gpu_maintenance_authority_verified=False,full_system_complete=False),indent=2)+'\n')
